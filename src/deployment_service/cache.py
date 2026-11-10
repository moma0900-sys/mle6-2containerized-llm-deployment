"""Small exact-match TTL cache used to expose deployment trade-offs."""

import hashlib
import time
from dataclasses import dataclass

from deployment_service.models import GenerateRequest, ProviderResult


@dataclass
class CacheEntry:
    """Cached provider result and monotonic expiry timestamp."""

    result: ProviderResult
    expires_at: float


class TTLCache:
    """Process-local cache suitable for the single-instance starter service."""

    def __init__(self, ttl_seconds: int, max_entries: int = 1024) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: dict[str, CacheEntry] = {}

    @staticmethod
    def key(request: GenerateRequest, model: str) -> str:
        """Hash all parameters that can affect output."""
        raw = f"{model}:{request.temperature}:{request.max_tokens}:{request.prompt}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, key: str) -> ProviderResult | None:
        """Return an unexpired result and remove stale entries."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= time.monotonic():
            self._entries.pop(key, None)
            return None
        return entry.result

    def set(self, key: str, result: ProviderResult) -> None:
        """Store a provider result until its configured expiry."""
        if self.ttl_seconds <= 0:
            return
        expired = [
            key
            for key, entry in self._entries.items()
            if entry.expires_at <= time.monotonic()
        ]
        for stale in expired:
            self._entries.pop(stale)
        if key not in self._entries and len(self._entries) >= self.max_entries:
            self._entries.pop(next(iter(self._entries)))
        self._entries[key] = CacheEntry(
            result=result,
            expires_at=time.monotonic() + self.ttl_seconds,
        )
