"""The load probe must count failed requests and use a nearest-rank p95."""

import asyncio
import importlib.util
from pathlib import Path

import httpx
import pytest

spec = importlib.util.spec_from_file_location("load_test", Path("scripts/load_test.py"))
assert spec is not None and spec.loader is not None
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_transport_failure_counts_as_a_request():
    async def run():
        def fail(request):
            raise httpx.ConnectError("offline")

        async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
            status, latency = await probe.send(client, "http://test", "hello")
        assert status == 0
        assert latency >= 0

    asyncio.run(run())


def test_small_sample_p95_uses_the_maximum(monkeypatch, capsys):
    results = iter([(200, 10.0), (0, 100.0)])

    async def send(*args):
        return next(results)

    monkeypatch.setattr(probe, "send", send)
    asyncio.run(probe.run("http://test", requests=2, concurrency=1))
    output = capsys.readouterr().out
    assert "p95_latency_ms=100.00" in output
    assert "error_rate=50.00%" in output
    assert "successful_requests=1" in output


def test_outage_does_not_look_like_successful_throughput(monkeypatch, capsys):
    async def send(*args):
        return 503, 1.0

    monkeypatch.setattr(probe, "send", send)
    asyncio.run(probe.run("http://test", requests=2, concurrency=1))
    output = capsys.readouterr().out
    assert "successful_requests=0" in output
    assert "successful_throughput_rps=0.00" in output
    assert "error_rate=100.00%" in output


def test_cache_is_bounded_and_removes_expired_entries(monkeypatch):
    from deployment_service.cache import TTLCache
    from deployment_service.models import ProviderResult, TokenUsage

    now = 10.0
    monkeypatch.setattr("deployment_service.cache.time.monotonic", lambda: now)
    cache = TTLCache(10, max_entries=2)
    result = ProviderResult(
        text="answer", model="test", usage=TokenUsage(input_tokens=1, output_tokens=1)
    )
    for key in ("a", "b", "c"):
        cache.set(key, result)
    assert len(cache._entries) == 2
    assert cache.get("a") is None
    now = 30.0
    cache.set("d", result)
    assert list(cache._entries) == ["d"]


@pytest.mark.parametrize("rate", [-1, float("nan"), float("inf")])
def test_invalid_prices_are_rejected(rate):
    from deployment_service.config import Settings

    with pytest.raises(ValueError):
        Settings(input_usd_per_million=rate)


def test_cache_requires_positive_capacity():
    from deployment_service.cache import TTLCache

    with pytest.raises(ValueError, match="max_entries"):
        TTLCache(10, max_entries=0)
