"""Offline tests for src/wiring.py.

We patch `get_nutrition_provider` so these tests never need a real
USDA_API_KEY or network access — the whole point of testing the wiring
is to prove the objects are connected correctly, not to exercise the
providers themselves (that's ai_service/pipeline's job).
"""
from __future__ import annotations

from unittest.mock import patch

from src.concurrency import NutritionPipeline
from src.config import Settings
from src.services import AIService, NutritionCache
from src.storage.repository import Repository
from src.wiring import Components, build_components


def _test_settings(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite:///:memory:",
        **overrides,
    )


@patch("src.wiring.get_nutrition_provider")
def test_build_components_returns_expected_types(mock_get_provider):
    mock_get_provider.return_value = object()  # a stand-in NutritionProvider

    components = build_components(_test_settings())

    assert isinstance(components, Components)
    assert isinstance(components.repository, Repository)
    assert isinstance(components.ai_service, AIService)
    assert isinstance(components.pipeline, NutritionPipeline)


@patch("src.wiring.get_nutrition_provider")
def test_build_components_uses_settings_database_url(mock_get_provider):
    mock_get_provider.return_value = object()

    components = build_components(_test_settings())

    assert str(components.repository.engine.url) == "sqlite+aiosqlite:///:memory:"


@patch("src.wiring.get_nutrition_provider")
def test_pipeline_respects_configured_max_parallel(mock_get_provider):
    mock_get_provider.return_value = object()

    components = build_components(_test_settings(max_parallel=3))

    # asyncio.Semaphore doesn't expose its limit publicly; _value is the
    # pragmatic (if slightly implementation-dependent) way to check it
    # right after construction, before anything has acquired a slot.
    assert components.pipeline._semaphore._value == 3


@patch("src.wiring.get_nutrition_provider")
def test_each_call_builds_fresh_components(mock_get_provider):
    mock_get_provider.return_value = object()
    settings = _test_settings()

    first = build_components(settings)
    second = build_components(settings)

    assert first.repository is not second.repository
    assert first.ai_service is not second.ai_service