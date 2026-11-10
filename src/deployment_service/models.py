"""Typed request, usage, and response contracts."""

from pydantic import BaseModel, ConfigDict, Field


class GenerateRequest(BaseModel):
    """Generation parameters accepted by the public endpoint."""

    model_config = ConfigDict(str_strip_whitespace=True)

    prompt: str = Field(min_length=1, max_length=8000)
    max_tokens: int = Field(default=1024, ge=1, le=2048)
    temperature: float = Field(default=0.2, ge=0, le=2)


class TokenUsage(BaseModel):
    """Provider-independent token accounting."""

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class ProviderResult(BaseModel):
    """Normalized output returned by a provider implementation."""

    text: str
    model: str
    usage: TokenUsage


class GenerateResponse(BaseModel):
    """Observable response returned to API clients."""

    text: str
    model: str
    usage: TokenUsage
    cache_hit: bool
    latency_ms: float = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
