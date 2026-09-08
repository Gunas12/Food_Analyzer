"""Thread-safe in-memory nutrition cache with monotonic expiration times."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from threading import Lock

from ai.schemas import NutritionFacts


def normalize_ingredient_name(name: str) -> str:
    """Strip outer whitespace and case-fold; preserve internal whitespace."""
    return name.strip().casefold()


class NutritionCache:
    """Store immutable nutrition facts for 24 hours by default.

    Keys use ``normalize_ingredient_name``. Expired entries are removed on
    access. A zero TTL disables retention; ``clock`` must be monotonic.
    """

    def __init__(
        self,
        ttl_seconds: float = 86400,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if not math.isfinite(ttl_seconds) or ttl_seconds < 0:
            raise ValueError("ttl_seconds must be finite and non-negative")
        self._ttl_seconds = ttl_seconds
        self._clock = time.monotonic if clock is None else clock
        self._entries: dict[str, tuple[NutritionFacts, float]] = {}
        self._lock = Lock()

    def get(self, name: str) -> NutritionFacts | None:
        """Return unexpired facts or remove an expired entry and return None."""
        key = normalize_ingredient_name(name)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            facts, expires_at = entry
            if self._clock() >= expires_at:
                del self._entries[key]
                return None
            return facts

    def set(self, name: str, facts: NutritionFacts) -> None:
        """Store facts and reset their expiration using the current clock."""
        key = normalize_ingredient_name(name)
        with self._lock:
            self._entries[key] = (facts, self._clock() + self._ttl_seconds)
