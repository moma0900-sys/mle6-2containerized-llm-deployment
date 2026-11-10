"""Deterministic and optional provider-backed generation."""

from typing import Any, Protocol

from langchain.chat_models import init_chat_model
from langchain_core.exceptions import ModelTimeoutError
from pydantic import SecretStr

from deployment_service.config import Settings
from deployment_service.models import GenerateRequest, ProviderResult, TokenUsage


class Provider(Protocol):
    """Interface required by the service layer."""

    async def generate(self, request: GenerateRequest) -> ProviderResult: ...


class DryProvider:
    """Stable local provider for tests and deployment checks."""

    def __init__(self, model: str) -> None:
        self.model = f"dry:{model}"

    async def generate(self, request: GenerateRequest) -> ProviderResult:
        words = request.prompt.split()
        text = f"Dry response: {request.prompt[:120]}"
        return ProviderResult(
            text=text,
            model=self.model,
            usage=TokenUsage(
                input_tokens=max(1, len(words)),
                output_tokens=max(1, len(text.split())),
            ),
        )


class ChatProvider:
    """One generation path for the configured live provider."""

    def __init__(self, settings: Settings) -> None:
        api_key = getattr(settings, f"{settings.provider}_api_key")
        if not api_key:
            raise ValueError(
                f"{settings.provider.upper()}_API_KEY is required for live mode"
            )
        self.model = settings.model
        self.token_limit_key = (
            "max_output_tokens" if settings.provider == "google" else "max_tokens"
        )
        fallback = settings.openrouter_fallback_model.strip()
        options: dict[str, Any] = (
            {
                "model_kwargs": {
                    "retries": None,
                    "models": [settings.model, fallback] if fallback else None,
                },
                "openrouter_provider": {"require_parameters": True},
            }
            if settings.provider == "openrouter"
            else {"vertexai": False}
            if settings.provider == "google"
            else {"reasoning_effort": "none"}
            if settings.provider == "openai"
            else {}
        )
        self.client = init_chat_model(
            model=self.model,
            model_provider={"mistral": "mistralai", "google": "google_genai"}.get(
                settings.provider, settings.provider
            ),
            api_key=SecretStr(api_key),
            timeout=int(settings.request_timeout_seconds * 1000)
            if settings.provider == "openrouter"
            else settings.request_timeout_seconds,
            max_retries=0,
            **options,
        )

    async def generate(self, request: GenerateRequest) -> ProviderResult:
        try:
            response = await self.client.ainvoke(
                [("user", request.prompt)],
                temperature=request.temperature,
                **{self.token_limit_key: request.max_tokens},
            )
        except ModelTimeoutError as error:
            raise TimeoutError("Model request timed out") from error
        except IndexError as error:
            raise ValueError("Provider returned no choices") from error
        if str(response.response_metadata.get("finish_reason")).lower() != "stop":
            raise ValueError("Provider returned an incomplete answer")
        text = response.text
        if not text.strip():
            raise ValueError("Provider returned no answer")
        usage = response.usage_metadata or {}
        return ProviderResult(
            text=text,
            model=response.response_metadata.get("model_name") or self.model,
            usage=TokenUsage(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            ),
        )


def build_provider(settings: Settings) -> Provider:
    """Select a provider from validated deployment configuration."""
    if settings.provider == "dry":
        return DryProvider(settings.model)
    if settings.provider in {"groq", "mistral", "openrouter", "google", "openai"}:
        return ChatProvider(settings)
    raise ValueError(f"Unsupported MODEL_PROVIDER: {settings.provider}")
