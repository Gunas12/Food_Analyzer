"""Composition root: build the SE-layer object graph from Settings.

`api.py` currently builds its own objects inline inside `create_app()`
(that's fine — FastAPI's app factory is itself a composition root for the
HTTP entry point). This module exists so `cli.py` doesn't have to repeat
that same construction logic by hand; both end up wiring the same three
pieces (repository, AI service, nutrition cache) from the same Settings.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai import get_nutrition_provider
from ai.nutrition import NutritionProvider

from src.concurrency import NutritionPipeline
from src.config import Settings
from src.services import AIService, NutritionCache
from src.storage.repository import Repository


@dataclass
class Components:
    """Everything a caller (CLI, scripts, tests) needs to run one analysis."""

    repository: Repository
    ai_service: AIService
    nutrition_provider: NutritionProvider
    pipeline: NutritionPipeline


def build_components(settings: Settings) -> Components:
    """Construct the object graph described by `settings`.

    Each call builds fresh objects — callers that want to share state
    (e.g. the cache) across many analyses, like the API does per-process,
    should build once and reuse the returned Components.
    """
    repository = Repository(settings.database_url)
    ai_service = AIService()
    nutrition_provider = get_nutrition_provider()
    cache = NutritionCache(ttl_seconds=settings.nutrition_cache_ttl_seconds)
    pipeline = NutritionPipeline(
        nutrition_provider,
        cache=cache,
        ai_service=ai_service,
        max_parallel=settings.max_parallel,
    )
    return Components(
        repository=repository,
        ai_service=ai_service,
        nutrition_provider=nutrition_provider,
        pipeline=pipeline,
    )