from __future__ import annotations

import argparse
import asyncio
import time

from ai.schemas import Ingredient, NutritionFacts
from src.concurrency import NutritionPipeline
from src.services import AIService, NutritionCache


class _SlowFakeProvider:
    """Stands in for a real NutritionProvider with a fixed simulated latency.

    `lookup` is called inside AIService's asyncio.to_thread, so blocking
    with time.sleep here behaves like a real blocking network call would.
    """

    def __init__(self, latency_seconds: float) -> None:
        self._latency = latency_seconds

    def lookup(self, ingredient_name: str) -> NutritionFacts:
        time.sleep(self._latency)
        return NutritionFacts(
            name=ingredient_name, kcal_per_100g=100, protein_g_per_100g=10,
            carbs_g_per_100g=10, fat_g_per_100g=1,
        )


def _make_ingredients(n: int) -> list[Ingredient]:
    return [
        Ingredient(name=f"ingredient_{i}", estimated_grams=100.0, confidence=0.9)
        for i in range(n)
    ]


async def run_sequential(ingredients, provider, ai_service) -> float:
    start = time.monotonic()
    for ing in ingredients:
        await ai_service.lookup_nutrition(provider, ing.name)
    return time.monotonic() - start


async def run_concurrent(ingredients, provider, max_parallel: int) -> float:
    # Fresh cache/ai_service per run so no result is served from cache --
    # we're measuring raw lookup latency, not cache hits.
    cache = NutritionCache()
    ai_service = AIService()
    pipeline = NutritionPipeline(
        provider, cache=cache, ai_service=ai_service, max_parallel=max_parallel
    )
    start = time.monotonic()
    await pipeline.lookup(ingredients)
    return time.monotonic() - start


async def _main_async(n: int, latency_ms: float, max_parallel: int) -> None:
    ingredients = _make_ingredients(n)
    provider = _SlowFakeProvider(latency_ms / 1000.0)

    seq_ai_service = AIService()
    seq_seconds = await run_sequential(ingredients, provider, seq_ai_service)
    conc_seconds = await run_concurrent(ingredients, provider, max_parallel)

    speedup = seq_seconds / conc_seconds if conc_seconds > 0 else float("inf")

    print(f"{'mode':<12}{'seconds':>10}")
    print("-" * 22)
    print(f"{'sequential':<12}{seq_seconds:>10.3f}")
    print(f"{'concurrent':<12}{conc_seconds:>10.3f}")
    print("-" * 22)
    print(
        f"speed-up: {speedup:.1f}x "
        f"(ingredients={n}, latency={latency_ms}ms, max_parallel={max_parallel})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ingredients", type=int, default=10)
    parser.add_argument("--latency-ms", type=float, default=150.0)
    parser.add_argument("--max-parallel", type=int, default=10)
    args = parser.parse_args()

    asyncio.run(_main_async(args.ingredients, args.latency_ms, args.max_parallel))


if __name__ == "__main__":
    main()