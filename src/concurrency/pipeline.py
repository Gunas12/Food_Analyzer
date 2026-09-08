"""Bounded parallel nutrition lookups with caching and partial results."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable

from ai.nutrition import NutritionProvider
from ai.providers.base import ProviderError
from ai.schemas import Ingredient, NutritionFacts
from src.services.ai_service import AIService
from src.services.nutrition_cache import NutritionCache, normalize_ingredient_name


logger = logging.getLogger(__name__)


class NutritionPipeline:
    """Look up one batch of ingredients and preserve their original names.

    Duplicate normalized names share a lookup within each batch, even with
    zero cache TTL. One instance bounds calls across batches on the same
    event loop. Concurrent batches may independently fetch the same miss.
    Inject a provider safe for concurrent calls, or use ``max_parallel=1``.
    """

    def __init__(
        self,
        provider: NutritionProvider,
        *,
        cache: NutritionCache | None = None,
        ai_service: AIService | None = None,
        max_parallel: int = 10,
    ) -> None:
        if (
            isinstance(max_parallel, bool)
            or not isinstance(max_parallel, int)
            or max_parallel < 1
        ):
            raise ValueError("max_parallel must be an integer of at least 1")
        self._provider = provider
        self._cache = NutritionCache() if cache is None else cache
        self._ai_service = AIService() if ai_service is None else ai_service
        self._semaphore = asyncio.Semaphore(max_parallel)

    async def lookup(
        self,
        ingredients: Iterable[Ingredient],
    ) -> dict[str, NutritionFacts]:
        """Return successful facts keyed exactly as required by compute_totals.

        Provider failures are logged and omitted, while other errors propagate.
        Missing names therefore contribute nothing to ``ai.compute_totals``;
        callers can compare the mapping with their inputs to report gaps.
        """
        names_by_key: dict[str, list[str]] = {}
        for ingredient in ingredients:
            key = normalize_ingredient_name(ingredient.name)
            names_by_key.setdefault(key, []).append(ingredient.name)

        groups = list(names_by_key.values())
        results = await asyncio.gather(
            *(self._lookup_one(names[0]) for names in groups)
        )
        facts_by_name: dict[str, NutritionFacts] = {}
        for names, facts in zip(groups, results):
            if facts is not None:
                for name in names:
                    facts_by_name[name] = facts
        return facts_by_name

    async def _lookup_one(self, name: str) -> NutritionFacts | None:
        facts = self._cache.get(name)
        if facts is not None:
            return facts

        async with self._semaphore:
            # Another batch may have populated the cache while we waited.
            facts = self._cache.get(name)
            if facts is not None:
                return facts
            try:
                facts = await self._ai_service.lookup_nutrition(self._provider, name)
            except ProviderError:
                logger.warning("Nutrition lookup failed for ingredient %r", name)
                return None
            self._cache.set(name, facts)
            return facts
