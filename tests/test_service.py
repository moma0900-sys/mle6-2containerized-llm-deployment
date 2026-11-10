"""Tests for caching, cost accounting, and bounded service output."""

import asyncio

from deployment_service.config import Settings
from deployment_service.models import GenerateRequest, ProviderResult, TokenUsage
from deployment_service.service import GenerationService, estimate_cost


class CountingProvider:
    """Deterministic provider that records invocation count."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: GenerateRequest) -> ProviderResult:
        self.calls += 1
        return ProviderResult(
            text=f"answer:{request.prompt}",
            model="test-model",
            usage=TokenUsage(input_tokens=100, output_tokens=50),
        )


def test_repeated_request_uses_cache() -> None:
    provider = CountingProvider()
    settings = Settings(model="test-model", cache_ttl_seconds=60)
    service = GenerationService(provider, settings)
    request = GenerateRequest(prompt="same")

    first = asyncio.run(service.generate(request))
    second = asyncio.run(service.generate(request))

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert provider.calls == 1


def test_cost_uses_configured_rates() -> None:
    settings = Settings(input_usd_per_million=2, output_usd_per_million=4)
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=500_000)

    assert estimate_cost(usage, settings) == 4
