"""Concurrency, caching, latency, and cost accounting for generation."""

import asyncio
import time

from deployment_service.cache import TTLCache
from deployment_service.config import Settings
from deployment_service.models import GenerateRequest, GenerateResponse, TokenUsage
from deployment_service.provider import Provider


def estimate_cost(usage: TokenUsage, settings: Settings) -> float:
    """Estimate provider cost from configurable per-million-token prices."""
    input_cost = usage.input_tokens * settings.input_usd_per_million / 1_000_000
    output_cost = usage.output_tokens * settings.output_usd_per_million / 1_000_000
    return round(input_cost + output_cost, 8)


class GenerationService:
    """Coordinate bounded provider calls and exact-match caching."""

    def __init__(self, provider: Provider, settings: Settings) -> None:
        self.provider = provider
        self.settings = settings
        self.cache = TTLCache(settings.cache_ttl_seconds)
        self.semaphore = asyncio.Semaphore(settings.max_concurrent_requests)

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        started = time.perf_counter()
        key = self.cache.key(request, self.settings.model)
        cached = self.cache.get(key)
        if cached is not None:
            return GenerateResponse(
                text=cached.text,
                model=cached.model,
                usage=cached.usage,
                cache_hit=True,
                latency_ms=(time.perf_counter() - started) * 1000,
                estimated_cost_usd=0,
            )

        # The deadline includes queueing, not only the upstream HTTP call.
        async with asyncio.timeout(self.settings.request_timeout_seconds):
            async with self.semaphore:
                result = await self.provider.generate(request)
        if not result.text.strip():
            raise ValueError("Provider returned no answer")
        self.cache.set(key, result)
        return GenerateResponse(
            text=result.text,
            model=result.model,
            usage=result.usage,
            cache_hit=False,
            latency_ms=(time.perf_counter() - started) * 1000,
            estimated_cost_usd=estimate_cost(result.usage, self.settings),
        )
