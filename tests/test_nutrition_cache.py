"""Deterministic nutrition cache tests with an injected monotonic clock."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from ai.schemas import NutritionFacts
from src.services import NutritionCache
from src.services import nutrition_cache


class FakeClock:
    """A manually advanced clock that never waits for real time."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def facts() -> NutritionFacts:
    return NutritionFacts(
        name="Rice, cooked", kcal_per_100g=130, protein_g_per_100g=2.7,
        carbs_g_per_100g=28, fat_g_per_100g=0.3, source="fake",
    )


def test_unknown_name_is_a_cache_miss(clock: FakeClock) -> None:
    assert NutritionCache(clock=clock).get("rice") is None


def test_set_returns_the_stored_facts(clock: FakeClock, facts: NutritionFacts) -> None:
    cache = NutritionCache(clock=clock)
    cache.set("rice", facts)

    assert cache.get("rice") is facts
    assert cache.get("broccoli") is None


def test_default_ttl_is_exactly_24_hours(clock: FakeClock, facts: NutritionFacts) -> None:
    cache = NutritionCache(clock=clock)
    cache.set("rice", facts)
    clock.advance(86399)
    assert cache.get("rice") is facts

    clock.advance(1)
    assert cache.get("rice") is None


@pytest.mark.parametrize("elapsed", [10, 11])
def test_expired_entry_is_removed(
    clock: FakeClock, facts: NutritionFacts, elapsed: float,
) -> None:
    cache = NutritionCache(ttl_seconds=10, clock=clock)
    cache.set(" RICE ", facts)
    clock.advance(elapsed)

    assert cache.get("rice") is None
    assert "rice" not in cache._entries
    assert cache.get("rice") is None


def test_refresh_replaces_facts_and_resets_ttl(
    clock: FakeClock, facts: NutritionFacts,
) -> None:
    cache = NutritionCache(ttl_seconds=10, clock=clock)
    cache.set("rice", facts)
    clock.advance(8)
    updated = facts.model_copy(update={"kcal_per_100g": 140})
    cache.set(" RICE ", updated)
    clock.advance(2)

    assert cache.get("rice") is updated
    clock.advance(8)
    assert cache.get("rice") is None


@pytest.mark.parametrize(
    ("stored_name", "queried_name"),
    [(" RICE ", "rice"), ("rice", "\tRiCe\n"), ("Straße", "STRASSE")],
)
def test_name_normalization(
    clock: FakeClock, facts: NutritionFacts, stored_name: str, queried_name: str,
) -> None:
    cache = NutritionCache(clock=clock)
    cache.set(stored_name, facts)

    assert cache.get(queried_name) is facts


def test_internal_whitespace_is_preserved(clock: FakeClock, facts: NutritionFacts) -> None:
    cache = NutritionCache(clock=clock)
    cache.set("white  rice", facts)

    assert cache.get("WHITE  RICE") is facts
    assert cache.get("white rice") is None


def test_zero_ttl_expires_immediately(clock: FakeClock, facts: NutritionFacts) -> None:
    cache = NutritionCache(ttl_seconds=0, clock=clock)
    cache.set("rice", facts)

    assert cache.get("rice") is None
    assert "rice" not in cache._entries


@pytest.mark.parametrize("ttl", [-1, -0.1, float("inf"), float("nan")])
def test_invalid_ttl_is_rejected(ttl: float) -> None:
    with pytest.raises(ValueError, match="ttl_seconds must be finite and non-negative"):
        NutritionCache(ttl_seconds=ttl)


def test_default_clock_uses_monotonic(
    monkeypatch: pytest.MonkeyPatch, clock: FakeClock, facts: NutritionFacts,
) -> None:
    monkeypatch.setattr(nutrition_cache.time, "monotonic", clock)
    cache = NutritionCache(ttl_seconds=1)
    cache.set("rice", facts)

    assert cache.get("rice") is facts
    clock.advance(1)
    assert cache.get("rice") is None


def test_concurrent_reads_and_writes_preserve_cache_state(
    clock: FakeClock, facts: NutritionFacts,
) -> None:
    cache = NutritionCache(clock=clock)

    def store_and_read(index: int) -> NutritionFacts | None:
        name = f"ingredient {index % 8}"
        cache.set(f" {name.upper()} ", facts)
        return cache.get(name)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(store_and_read, range(128)))

    assert all(result is facts for result in results)
    for index in range(8):
        assert cache.get(f"ingredient {index}") is facts
