"""In-memory token bucket rate limiting for Yggdrasil HTTP endpoints."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import ceil
from threading import Lock
from time import monotonic

HEALTH_RATE_LIMIT_CAPACITY = 60
HEALTH_RATE_LIMIT_REFILL_RATE = 1.0


@dataclass
class _TokenBucket:
    """Mutable state for one endpoint and client IP pair."""

    tokens: float
    updated_at: float


class TokenBucketRateLimiter:
    """Limit each client IP independently for each endpoint."""

    def __init__(
        self,
        *,
        capacity: int = HEALTH_RATE_LIMIT_CAPACITY,
        refill_rate: float = HEALTH_RATE_LIMIT_REFILL_RATE,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._clock = clock
        self._buckets: dict[tuple[str, str], _TokenBucket] = {}
        self._lock = Lock()

    def retry_after(self, *, endpoint: str, client_ip: str) -> int | None:
        """Consume a token and return a retry delay when the bucket is empty."""
        with self._lock:
            now = self._clock()
            bucket = self._buckets.get((endpoint, client_ip))
            if bucket is None:
                bucket = _TokenBucket(tokens=float(self._capacity), updated_at=now)
                self._buckets[(endpoint, client_ip)] = bucket

            elapsed = max(0.0, now - bucket.updated_at)
            bucket.tokens = min(self._capacity, bucket.tokens + elapsed * self._refill_rate)
            bucket.updated_at = now
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return None

            return max(1, ceil((1.0 - bucket.tokens) / self._refill_rate))
