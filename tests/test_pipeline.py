"""Offline pipeline tests with event gates instead of timing assertions."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import Counter
from unittest.mock import AsyncMock

import pytest

from ai import compute_totals
from ai.nutrition import NutritionProvider
from ai.providers.base import ProviderError
from ai.schemas import Ingredient, NutritionFacts
from src.concurrency import NutritionPipeline
from src.services import AIService, NutritionCache
from src.services.nutrition_cache import normalize_ingredient_name


_FACTS = NutritionFacts(
    name="Provider description of cooked rice", kcal_per_100g=130,
    protein_g_per_100g=2.7, carbs_g_per_100g=28, fat_g_per_100g=0.3, source="fake",
)


def ingredient(name: str, grams: float = 100) -> Ingredient:
    """Make an ingredient without relying on an image or VLM."""
    return Ingredient(name=name, estimated_grams=grams, confidence=0.9)


class RecordingNutrition(NutritionProvider):
    """Return fixed facts after any scripted errors, recording each call."""

    def __init__(self, failures: dict[str, list[Exception]] | None = None) -> None:
        self.failures = {} if failures is None else failures
        self.calls: list[str] = []
        self.thread_ids: list[int] = []
        self.lock = threading.Lock()

    def lookup(self, ingredient_name: str) -> NutritionFacts:
        key = normalize_ingredient_name(ingredient_name)
        with self.lock:
            self.calls.append(ingredient_name)
            self.thread_ids.append(threading.get_ident())
            failures = self.failures.get(key, [])
            if failures:
                raise failures.pop(0)
        return _FACTS


@pytest.mark.asyncio
async def test_sync_lookups_overlap_and_allow_event_loop_progress() -> None:
    loop = asyncio.get_running_loop()
    both_started = asyncio.Event()
    release = threading.Event()
    state_lock = threading.Lock()
    active = 0
    peak = 0
    worker_threads: set[int] = set()

    class GatedNutrition(NutritionProvider):
        def lookup(self, ingredient_name: str) -> NutritionFacts:
            nonlocal active, peak
            with state_lock:
                worker_threads.add(threading.get_ident())
                active += 1
                peak = max(peak, active)
                if active == 2:
                    loop.call_soon_threadsafe(both_started.set)
            try:
                if not release.wait(timeout=10):
                    raise AssertionError("The event loop did not release parallel lookups")
                return _FACTS
            finally:
                with state_lock:
                    active -= 1

    pipeline = NutritionPipeline(GatedNutrition(), max_parallel=2)
    task = asyncio.create_task(pipeline.lookup([ingredient("rice"), ingredient("broccoli")]))
    try:
        await asyncio.wait_for(both_started.wait(), timeout=10)
        assert not task.done()
        assert peak == 2
        assert len(worker_threads) == 2
        assert threading.get_ident() not in worker_threads
    finally:
        release.set()
        result = await asyncio.wait_for(task, timeout=10)

    assert set(result) == {"rice", "broccoli"}
    assert active == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("max_parallel", [1, 2, 3])
async def test_max_parallel_bounds_calls_across_concurrent_batches(max_parallel: int) -> None:
    release = asyncio.Event()
    saturated = asyncio.Event()

    class GatedService(AIService):
        """Use coroutine gates to inspect semaphore limits deterministically."""

        def __init__(self) -> None:
            super().__init__()
            self.active = 0
            self.peak = 0
            self.calls: list[str] = []

        async def lookup_nutrition(
            self, provider: NutritionProvider, ingredient_name: str,
        ) -> NutritionFacts:
            self.calls.append(ingredient_name)
            self.active += 1
            self.peak = max(self.peak, self.active)
            if self.active >= max_parallel:
                saturated.set()
            try:
                await release.wait()
                return _FACTS
            finally:
                self.active -= 1

    service = GatedService()
    pipeline = NutritionPipeline(
        RecordingNutrition(), ai_service=service, max_parallel=max_parallel,
    )
    tasks = [
        asyncio.create_task(pipeline.lookup([ingredient(f"food {index}") for index in batch]))
        for batch in [range(4), range(4, 8)]
    ]
    try:
        await asyncio.wait_for(saturated.wait(), timeout=10)
        assert service.active == max_parallel
        assert len(service.calls) == max_parallel
    finally:
        release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)

    assert service.peak == max_parallel
    assert service.active == 0
    assert len(service.calls) == 8
    assert sum(map(len, results)) == 8


@pytest.mark.asyncio
async def test_provider_failure_preserves_other_results_and_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_error = "fake-api-key-and-provider-payload"
    provider = RecordingNutrition({"unknown": [ProviderError(private_error) for _ in range(3)]})
    sleep = AsyncMock()
    cache = NutritionCache()
    pipeline = NutritionPipeline(provider, cache=cache, ai_service=AIService(sleep=sleep))
    inputs = [ingredient("rice"), ingredient("unknown"), ingredient("broccoli")]

    with caplog.at_level(logging.INFO):
        results = await pipeline.lookup(inputs)

    assert results == {"rice": _FACTS, "broccoli": _FACTS}
    assert Counter(provider.calls) == {"rice": 1, "broccoli": 1, "unknown": 3}
    assert cache.get("unknown") is None
    assert compute_totals(inputs, results).kcal == 260
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "unknown" in warnings[0].getMessage()
    assert private_error not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.asyncio
async def test_all_provider_failures_return_empty_mapping() -> None:
    provider = RecordingNutrition({"rice": [ProviderError("unavailable")]})
    pipeline = NutritionPipeline(provider, ai_service=AIService(max_attempts=1))

    assert await pipeline.lookup([ingredient("rice"), ingredient("RICE")]) == {}
    assert provider.calls == ["rice"]


@pytest.mark.asyncio
async def test_cache_hit_skips_provider_on_later_batch() -> None:
    provider = RecordingNutrition()
    pipeline = NutritionPipeline(provider)

    first = await pipeline.lookup([ingredient("rice")])
    second = await pipeline.lookup([ingredient(" RICE ")])

    assert first == {"rice": _FACTS}
    assert second == {" RICE ": _FACTS}
    assert provider.calls == ["rice"]


@pytest.mark.asyncio
async def test_prepopulated_cache_avoids_provider() -> None:
    cache = NutritionCache()
    cache.set("rice", _FACTS)
    provider = RecordingNutrition()

    result = await NutritionPipeline(provider, cache=cache).lookup([ingredient("RICE")])

    assert result == {"RICE": _FACTS}
    assert provider.calls == []


@pytest.mark.asyncio
async def test_expired_cache_triggers_a_new_lookup() -> None:
    now = 0.0
    cache = NutritionCache(ttl_seconds=10, clock=lambda: now)
    provider = RecordingNutrition()
    pipeline = NutritionPipeline(provider, cache=cache)

    await pipeline.lookup([ingredient("rice")])
    now = 9
    await pipeline.lookup([ingredient("rice")])
    assert provider.calls == ["rice"]
    now = 10
    assert await pipeline.lookup([ingredient("rice")]) == {"rice": _FACTS}
    assert provider.calls == ["rice", "rice"]


@pytest.mark.asyncio
@pytest.mark.parametrize("ttl_seconds", [0, 86400])
async def test_duplicates_share_lookup_and_preserve_all_portions(ttl_seconds: float) -> None:
    provider = RecordingNutrition()
    pipeline = NutritionPipeline(provider, cache=NutritionCache(ttl_seconds=ttl_seconds))
    inputs = [ingredient(" Rice ", 100), ingredient("rice", 50), ingredient("rice", 25)]

    result = await pipeline.lookup(inputs)

    assert result == {" Rice ": _FACTS, "rice": _FACTS}
    assert provider.calls == [" Rice "]
    assert compute_totals(inputs, result).kcal == pytest.approx(227.5)
    assert _FACTS.name not in result


@pytest.mark.asyncio
async def test_lookup_recovers_after_retries_and_caches_success() -> None:
    provider = RecordingNutrition({"rice": [ProviderError("first"), ProviderError("second")]})
    sleep = AsyncMock()
    cache = NutritionCache()
    service = AIService(max_attempts=3, base_delay=0.2, sleep=sleep)
    pipeline = NutritionPipeline(provider, cache=cache, ai_service=service)

    assert await pipeline.lookup([ingredient("rice")]) == {"rice": _FACTS}
    assert cache.get("rice") is _FACTS
    assert await pipeline.lookup([ingredient("RICE")]) == {"RICE": _FACTS}
    assert provider.calls == ["rice"] * 3
    assert [call.args[0] for call in sleep.await_args_list] == [0.2, 0.4]


@pytest.mark.asyncio
async def test_failed_lookup_can_be_attempted_in_a_later_batch() -> None:
    provider = RecordingNutrition({"rice": [ProviderError("temporary failure")]})
    pipeline = NutritionPipeline(provider, ai_service=AIService(max_attempts=1))

    assert await pipeline.lookup([ingredient("rice")]) == {}
    assert await pipeline.lookup([ingredient("rice")]) == {"rice": _FACTS}
    assert provider.calls == ["rice", "rice"]


@pytest.mark.asyncio
async def test_cache_is_rechecked_after_waiting_for_a_semaphore_slot() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    cache = NutritionCache()
    provider = RecordingNutrition()

    class PausedService(AIService):
        async def lookup_nutrition(
            self, provider: NutritionProvider, ingredient_name: str,
        ) -> NutritionFacts:
            entered.set()
            await release.wait()
            return await super().lookup_nutrition(provider, ingredient_name)

    pipeline = NutritionPipeline(provider, cache=cache, ai_service=PausedService(), max_parallel=1)
    task = asyncio.create_task(pipeline.lookup([ingredient("rice"), ingredient("broccoli")]))
    try:
        await asyncio.wait_for(entered.wait(), timeout=10)
        # Both batch coroutines have started; broccoli is waiting on the slot.
        cache.set("broccoli", _FACTS)
    finally:
        release.set()
        result = await asyncio.wait_for(task, timeout=10)

    assert result == {"rice": _FACTS, "broccoli": _FACTS}
    assert provider.calls == ["rice"]


@pytest.mark.asyncio
async def test_non_provider_error_propagates_without_retry() -> None:
    original = ValueError("invalid ingredient")
    provider = RecordingNutrition({"rice": [original]})
    sleep = AsyncMock()
    pipeline = NutritionPipeline(provider, ai_service=AIService(sleep=sleep))

    with pytest.raises(ValueError) as caught:
        await pipeline.lookup([ingredient("rice")])

    assert caught.value is original
    assert provider.calls == ["rice"]
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_input_never_calls_provider() -> None:
    provider = RecordingNutrition()

    assert await NutritionPipeline(provider).lookup([]) == {}
    assert provider.calls == []


@pytest.mark.asyncio
async def test_generator_input_and_existing_fake_provider(fake_nutrition) -> None:
    inputs = [ingredient("white rice (cooked)", 200), ingredient("broccoli", 80)]
    result = await NutritionPipeline(fake_nutrition).lookup(item for item in inputs)

    assert set(result) == {item.name for item in inputs}
    assert compute_totals(inputs, result).kcal == pytest.approx(287.2)


@pytest.mark.parametrize("max_parallel", [0, -1, -10, 1.5, True])
def test_invalid_parallel_limit_is_rejected(max_parallel: int) -> None:
    with pytest.raises(ValueError, match="max_parallel must be an integer of at least 1"):
        NutritionPipeline(RecordingNutrition(), max_parallel=max_parallel)
