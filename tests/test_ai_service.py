"""Offline retry tests using scripted providers and injected async waits."""

from __future__ import annotations

import asyncio
import logging
import threading
from unittest.mock import AsyncMock

import pytest

import ai
from ai.nutrition import NutritionProvider
from ai.providers.base import ProviderError, VLMProvider
from ai.schemas import Ingredient, NutritionFacts
from src.services import AIService


_MEAL_RESPONSE = (
    '{"meal_recognized": true, "ingredients": '
    '[{"name": "rice", "estimated_grams": 100, "confidence": 0.9}]}'
)


class ScriptedVLM(VLMProvider):
    """Return or raise the next predetermined outcome without network access."""

    def __init__(self, outcomes: list[str | Exception]) -> None:
        self.outcomes = iter(outcomes)
        self.calls: list[str] = []
        self.thread_ids: list[int] = []

    def describe(
        self,
        image_path: str,
        prompt: str,
        *,
        json_schema: dict | None = None,
    ) -> str:
        self.calls.append(image_path)
        self.thread_ids.append(threading.get_ident())
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_identification_succeeds_on_first_attempt() -> None:
    provider = ScriptedVLM([_MEAL_RESPONSE])
    sleep = AsyncMock()

    ingredients = await AIService(sleep=sleep).identify_ingredients(
        "meal.png", vlm=provider,
    )

    assert ingredients == [Ingredient(name="rice", estimated_grams=100, confidence=0.9)]
    assert provider.calls == ["meal.png"]
    assert provider.thread_ids == [provider.thread_ids[0]]
    assert provider.thread_ids[0] != threading.get_ident()
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_fake_vlm_integration(fake_vlm, sample_image: str) -> None:
    result = await AIService().identify_ingredients(sample_image, vlm=fake_vlm)

    assert len(result) == 3
    assert all(isinstance(ingredient, Ingredient) for ingredient in result)
    assert fake_vlm.calls[0][0] == sample_image


@pytest.mark.asyncio
async def test_unrecognized_meal_stays_empty() -> None:
    provider = ScriptedVLM(['{"meal_recognized": false, "ingredients": []}'])
    sleep = AsyncMock()

    assert await AIService(sleep=sleep).identify_ingredients("meal.png", vlm=provider) == []
    sleep.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failures", [1, 2, 3])
async def test_provider_failures_recover_with_exponential_backoff(failures: int) -> None:
    provider = ScriptedVLM(
        [ProviderError("temporary failure") for _ in range(failures)] + [_MEAL_RESPONSE]
    )
    sleep = AsyncMock()
    service = AIService(max_attempts=4, base_delay=0.25, sleep=sleep)

    result = await service.identify_ingredients("meal.png", vlm=provider)

    assert result[0].name == "rice"
    assert len(provider.calls) == failures + 1
    assert [call.args[0] for call in sleep.await_args_list] == [
        0.25 * 2**index for index in range(failures)
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("max_attempts", [1, 2, 4])
async def test_attempt_limit_reraises_the_original_final_error(max_attempts: int) -> None:
    errors = [ProviderError(f"failure {index}") for index in range(max_attempts)]
    provider = ScriptedVLM(errors)
    sleep = AsyncMock()
    service = AIService(max_attempts=max_attempts, base_delay=2, sleep=sleep)

    with pytest.raises(ProviderError) as caught:
        await service.identify_ingredients("meal.png", vlm=provider)

    assert caught.value is errors[-1]
    assert len(provider.calls) == max_attempts
    assert [call.args[0] for call in sleep.await_args_list] == [
        2 * 2**index for index in range(max_attempts - 1)
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [ValueError, TypeError, RuntimeError])
async def test_non_provider_errors_are_not_retried(error_type: type[Exception]) -> None:
    original = error_type("programming error")
    provider = ScriptedVLM([original, _MEAL_RESPONSE])
    sleep = AsyncMock()

    with pytest.raises(error_type) as caught:
        await AIService(sleep=sleep).identify_ingredients("meal.png", vlm=provider)

    assert caught.value is original
    assert len(provider.calls) == 1
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_logs_record_lifecycle_without_provider_error_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_payload = "fake-secret-token-and-private-response"
    provider = ScriptedVLM([ProviderError(private_payload), _MEAL_RESPONSE])
    service = AIService(sleep=AsyncMock())

    with caplog.at_level(logging.INFO, logger="src.services.ai_service"):
        await service.identify_ingredients("private-image.png", vlm=provider)

    assert "Starting identify_ingredients" in caplog.text
    assert "Retrying identify_ingredients" in caplog.text
    assert "Succeeded identify_ingredients" in caplog.text
    assert private_payload not in caplog.text
    assert "private-image.png" not in caplog.text
    assert all(record.levelno == logging.INFO for record in caplog.records)


@pytest.mark.asyncio
async def test_default_identification_function_can_be_replaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, VLMProvider | None]] = []

    def identify(image_path: str, *, vlm: VLMProvider | None = None) -> list[Ingredient]:
        calls.append((image_path, vlm))
        return []

    monkeypatch.setattr(ai, "identify_ingredients", identify)

    assert await AIService().identify_ingredients("meal.png") == []
    assert calls == [("meal.png", None)]


@pytest.mark.asyncio
async def test_nutrition_lookup_uses_the_same_retry_policy(fake_nutrition) -> None:
    expected = fake_nutrition.lookup("broccoli")

    class RecoveringNutrition(NutritionProvider):
        def __init__(self) -> None:
            self.calls: list[str] = []
            self.thread_ids: list[int] = []

        def lookup(self, ingredient_name: str) -> NutritionFacts:
            self.calls.append(ingredient_name)
            self.thread_ids.append(threading.get_ident())
            if len(self.calls) < 3:
                raise ProviderError("temporary failure")
            return expected

    provider = RecoveringNutrition()
    sleep = AsyncMock()
    result = await AIService(base_delay=0.125, sleep=sleep).lookup_nutrition(
        provider, "broccoli",
    )

    assert result is expected
    assert provider.calls == ["broccoli"] * 3
    assert all(thread_id != threading.get_ident() for thread_id in provider.thread_ids)
    assert [call.args[0] for call in sleep.await_args_list] == [0.125, 0.25]


@pytest.mark.asyncio
async def test_event_loop_progresses_while_identification_is_blocked() -> None:
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()

    class BlockingVLM(VLMProvider):
        def describe(
            self,
            image_path: str,
            prompt: str,
            *,
            json_schema: dict | None = None,
        ) -> str:
            loop.call_soon_threadsafe(started.set)
            if not release.wait(timeout=10):
                raise AssertionError("The event loop did not release the provider")
            return _MEAL_RESPONSE

    task = asyncio.create_task(
        AIService().identify_ingredients("meal.png", vlm=BlockingVLM())
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=10)
        assert not task.done()
    finally:
        release.set()
        result = await asyncio.wait_for(task, timeout=10)

    assert result[0].name == "rice"


@pytest.mark.asyncio
async def test_cancellation_during_backoff_stops_retries() -> None:
    waiting = asyncio.Event()
    hold = asyncio.Event()
    delays: list[float] = []
    provider = ScriptedVLM([ProviderError("temporary failure"), _MEAL_RESPONSE])

    async def controlled_sleep(delay: float) -> None:
        delays.append(delay)
        waiting.set()
        await hold.wait()

    task = asyncio.create_task(
        AIService(sleep=controlled_sleep).identify_ingredients("meal.png", vlm=provider)
    )
    try:
        await asyncio.wait_for(waiting.wait(), timeout=10)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert len(provider.calls) == 1
    assert delays == [0.5]


@pytest.mark.parametrize("max_attempts", [0, -1, 1.5, True])
def test_invalid_attempt_limit_is_rejected(max_attempts: int) -> None:
    with pytest.raises(ValueError, match="max_attempts must be an integer of at least 1"):
        AIService(max_attempts=max_attempts)


@pytest.mark.parametrize("delay", [-1, float("inf"), float("nan")])
def test_invalid_base_delay_is_rejected(delay: float) -> None:
    with pytest.raises(ValueError, match="base_delay must be finite and non-negative"):
        AIService(base_delay=delay)


@pytest.mark.asyncio
async def test_zero_delay_uses_injected_sleep_without_waiting() -> None:
    provider = ScriptedVLM([ProviderError("temporary failure"), _MEAL_RESPONSE])
    sleep = AsyncMock()

    await AIService(base_delay=0, sleep=sleep).identify_ingredients("meal.png", vlm=provider)

    sleep.assert_awaited_once_with(0)
