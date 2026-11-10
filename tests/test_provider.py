"""Native async-provider contracts without real API calls."""

import asyncio
import json
from pathlib import Path
from runpy import run_path

import httpx
import httpx2
import pytest
from groq import RateLimitError
from openai import APIError as OpenAIAPIError
from openrouter.errors import OpenRouterError

from deployment_service.config import Settings
from deployment_service.models import GenerateRequest
from deployment_service.provider import ChatProvider, build_provider


@pytest.mark.parametrize("api_key", ["", "test-only"])
def test_default_provider_is_groq_and_requires_its_key(monkeypatch, api_key):
    monkeypatch.delenv("MODEL_PROVIDER")
    monkeypatch.setenv("GROQ_API_KEY", api_key)
    path = Path(__file__).parents[1] / "src/deployment_service/config.py"
    configured = run_path(str(path))["settings"]
    assert configured.provider == "groq"
    assert configured.model == "openai/gpt-oss-20b"
    if api_key:
        assert isinstance(build_provider(configured), ChatProvider)
    else:
        with pytest.raises(ValueError, match="GROQ_API_KEY"):
            build_provider(configured)


@pytest.mark.parametrize(
    "provider_name", ["dry", "groq", "mistral", "openrouter", "google", "openai"]
)
def test_environment_selects_the_matching_default_and_model_override(
    monkeypatch, provider_name
):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("MODEL_PROVIDER", provider_name)
    for name in (
        "GROQ_MODEL",
        "MISTRAL_MODEL",
        "OPENROUTER_MODEL",
        "GOOGLE_MODEL",
        "OPENAI_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    path = Path(__file__).parents[1] / "src/deployment_service/config.py"
    expected = {
        "google": "gemma-4-26b-a4b-it",
        "openai": "gpt-6-luna",
        "mistral": "ministral-14b-latest",
        "openrouter": "google/gemma-4-26b-a4b-it:free",
    }.get(provider_name, "openai/gpt-oss-20b")
    assert run_path(str(path))["settings"].model == expected
    variable = (
        f"{provider_name.upper()}_MODEL" if provider_name != "dry" else "GROQ_MODEL"
    )
    monkeypatch.setenv(variable, "custom-model")
    assert run_path(str(path))["settings"].model == "custom-model"


@pytest.mark.parametrize(
    "usage", [None, {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19}]
)
@pytest.mark.parametrize("provider_name", ["groq", "mistral", "openrouter", "openai"])
def test_native_async_generation_preserves_usage_and_limits(
    monkeypatch, usage, provider_name
):
    requests = []

    transport = httpx2 if provider_name == "openai" else httpx

    async def respond(client, request, **kwargs):
        requests.append(request)
        return transport.Response(
            200,
            request=request,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "system_fingerprint": None,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "Approved answer",
                        },
                    }
                ],
                "usage": usage,
            },
        )

    monkeypatch.setattr(transport.AsyncClient, "send", respond)
    provider = ChatProvider(
        Settings(
            provider=provider_name,
            groq_api_key="test-only",
            mistral_api_key="test-only",
            openrouter_api_key="test-only",
            openai_api_key="test-only",
        )
    )
    result = asyncio.run(
        provider.generate(
            GenerateRequest(
                prompt="Question",
                max_tokens=123,
                temperature=0.4,
            )
        )
    )
    assert result.text == "Approved answer"
    assert result.model == (
        "test-model" if provider_name in {"openrouter", "openai"} else provider.model
    )
    assert result.usage.input_tokens == (12 if usage else 0)
    assert result.usage.output_tokens == (7 if usage else 0)
    assert len(requests) == 1
    body = json.loads(requests[0].content)
    token_key = "max_completion_tokens" if provider_name == "openai" else "max_tokens"
    assert body[token_key] == 123
    if provider_name == "openai":
        assert body["reasoning_effort"] == "none"
    assert body["temperature"] == 0.4
    if provider_name == "openrouter":
        assert body["models"] == [body["model"], "openrouter/free"]
    else:
        assert "models" not in body
    assert body["messages"] == [{"role": "user", "content": "Question"}]
    assert requests[0].extensions["timeout"]["read"] == 30
    assert provider.client.model_dump()["max_retries"] == 0


@pytest.mark.parametrize(
    "reason,content",
    [
        ("length", "Partial"),
        ("content_filter", "Blocked"),
        (None, "Partial"),
        ("stop", None),
        ("stop", ""),
        ("stop", "  "),
    ],
)
@pytest.mark.parametrize("provider_name", ["groq", "mistral", "openrouter", "openai"])
def test_native_async_generation_rejects_unusable_answers(
    monkeypatch, reason, content, provider_name
):
    transport = httpx2 if provider_name == "openai" else httpx

    async def respond(client, request, **kwargs):
        return transport.Response(
            200,
            request=request,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "system_fingerprint": None,
                "model": "test",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": reason,
                        "message": {
                            "role": "assistant",
                            "content": content,
                        },
                    }
                ],
            },
        )

    monkeypatch.setattr(transport.AsyncClient, "send", respond)
    provider = ChatProvider(
        Settings(
            provider=provider_name,
            groq_api_key="test-only",
            mistral_api_key="test-only",
            openrouter_api_key="test-only",
            openai_api_key="test-only",
        )
    )
    with pytest.raises((ValueError, OpenRouterError)):
        asyncio.run(provider.generate(GenerateRequest(prompt="Question")))


@pytest.mark.parametrize("status", [200, 429])
@pytest.mark.parametrize("provider_name", ["groq", "mistral", "openrouter", "openai"])
def test_native_async_generation_does_not_retry_or_invent_an_answer(
    monkeypatch, status, provider_name
):
    calls = []

    transport = httpx2 if provider_name == "openai" else httpx

    async def respond(client, request, **kwargs):
        calls.append(request)
        return transport.Response(status, request=request, json={"choices": []})

    monkeypatch.setattr(transport.AsyncClient, "send", respond)
    provider = ChatProvider(
        Settings(
            provider=provider_name,
            groq_api_key="test-only",
            mistral_api_key="test-only",
            openrouter_api_key="test-only",
            openai_api_key="test-only",
        )
    )
    with pytest.raises(
        (ValueError, OpenRouterError)
        if status == 200
        else (RateLimitError, OpenAIAPIError, httpx.HTTPStatusError, OpenRouterError)
    ):
        asyncio.run(provider.generate(GenerateRequest(prompt="Question")))
    assert len(calls) == 1
