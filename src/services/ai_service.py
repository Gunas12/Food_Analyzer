"""Async wrappers for synchronous AI calls with logging and bounded retries."""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Awaitable, Callable
from functools import partial
from typing import TypeVar

import ai
from ai.nutrition import NutritionProvider
from ai.providers.base import ProviderError, VLMProvider
from ai.schemas import Ingredient, NutritionFacts


logger = logging.getLogger(__name__)
_Result = TypeVar("_Result")


class AIService:
    """Retry provider failures without blocking the event loop.

    ``max_attempts`` includes the initial call. Backoff starts at
    ``base_delay`` seconds and doubles after each retry. Inject ``sleep``
    to control waiting in tests and pass providers explicitly when needed.
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 0.5,
        *,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        if (
            isinstance(max_attempts, bool)
            or not isinstance(max_attempts, int)
            or max_attempts < 1
        ):
            raise ValueError("max_attempts must be an integer of at least 1")
        if not math.isfinite(base_delay) or base_delay < 0:
            raise ValueError("base_delay must be finite and non-negative")
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._sleep = asyncio.sleep if sleep is None else sleep

    async def identify_ingredients(
        self,
        image_path: str,
        *,
        vlm: VLMProvider | None = None,
    ) -> list[Ingredient]:
        """Identify a meal using an injected VLM or the existing AI factory."""
        return await self._call_with_retry(
            partial(ai.identify_ingredients, image_path, vlm=vlm),
            operation="identify_ingredients",
        )

    async def lookup_nutrition(
        self,
        provider: NutritionProvider,
        ingredient_name: str,
    ) -> NutritionFacts:
        """Look up nutrition with the same retry policy as identification."""
        return await self._call_with_retry(
            partial(provider.lookup, ingredient_name),
            operation="nutrition_lookup",
        )

    async def _call_with_retry(
        self,
        call: Callable[[], _Result],
        *,
        operation: str,
    ) -> _Result:
        attempt = 1
        delay = self._base_delay
        while True:
            logger.info(
                "Starting %s (attempt %d/%d)",
                operation, attempt, self._max_attempts,
            )
            try:
                result = await asyncio.to_thread(call)
            except ProviderError:
                if attempt == self._max_attempts:
                    raise
                # Provider errors can contain API keys or raw responses.
                logger.info(
                    "Retrying %s after attempt %d/%d in %.3f seconds",
                    operation, attempt, self._max_attempts, delay,
                )
                await self._sleep(delay)
                attempt += 1
                delay *= 2
            else:
                logger.info("Succeeded %s on attempt %d", operation, attempt)
                return result
