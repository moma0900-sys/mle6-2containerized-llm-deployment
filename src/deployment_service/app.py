"""FastAPI entry point for the containerized LLM service."""

import logging

from fastapi import FastAPI, HTTPException
from groq import APITimeoutError
from httpx import TimeoutException

from deployment_service.config import settings
from deployment_service.models import GenerateRequest, GenerateResponse
from deployment_service.provider import build_provider
from deployment_service.service import GenerationService

logger = logging.getLogger(__name__)

app = FastAPI(title="Containerized LLM Service", version="1.0.0")
service = GenerationService(build_provider(settings), settings)


@app.get("/")
def root() -> dict[str, str]:
    """Confirm that the service is reachable and point to the real routes."""
    return {
        "message": "Containerized LLM service is running. "
        "Use GET /health, GET /ready, or POST /generate."
    }


@app.get("/health")
def health() -> dict[str, str]:
    """Confirm that the process and HTTP router are alive."""
    return {"status": "healthy"}


@app.get("/ready")
def ready() -> dict[str, str]:
    """Expose configuration readiness without calling the provider."""
    return {"status": "ready", "provider": settings.provider, "model": settings.model}


@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest) -> GenerateResponse:
    """Generate text with bounded concurrency and exact-match caching."""
    try:
        return await service.generate(request)
    except (TimeoutError, APITimeoutError, TimeoutException) as exc:
        raise HTTPException(
            status_code=504, detail="Generation request timed out"
        ) from exc
    except Exception as exc:
        logger.exception("Generation provider failed")
        raise HTTPException(
            status_code=502,
            detail="Generation provider unavailable",
        ) from exc
