"""Offline tests for src/core/analyzer.py — fully offline: fake AI service,
fake pipeline, in-memory SQLite repository."""
from __future__ import annotations

import pytest
import pytest_asyncio

from ai.schemas import Ingredient, NutritionFacts

from src.core.analyzer import FoodAnalyzer
from src.storage.repository import Repository
from src.validation import ValidationError

_PNG_MAGIC = bytes.fromhex("89504e470d0a1a0a")


class FakeAIService:
    """Stands in for AIService — no real ai.* calls, no event-loop thread hop."""

    def __init__(self, ingredients: list[Ingredient]):
        self._ingredients = ingredients
        self.calls = 0

    async def identify_ingredients(self, image_path: str, **kwargs):
        self.calls += 1
        return self._ingredients


class FakePipeline:
    """Stands in for NutritionPipeline.lookup — returns a fixed mapping."""

    def __init__(self, facts_by_name: dict[str, NutritionFacts]):
        self._facts_by_name = facts_by_name

    async def lookup(self, ingredients):
        return self._facts_by_name


def _rice_ingredient() -> Ingredient:
    return Ingredient(name="rice", estimated_grams=180.0, confidence=0.9)


def _rice_facts() -> NutritionFacts:
    return NutritionFacts(
        name="rice", kcal_per_100g=130, protein_g_per_100g=2.7,
        carbs_g_per_100g=28.0, fat_g_per_100g=0.3,
    )


@pytest_asyncio.fixture
async def repository():
    repo = Repository("sqlite+aiosqlite:///:memory:")
    await repo.init_models()
    return repo


@pytest.fixture
def sample_image(tmp_path):
    p = tmp_path / "meal.png"
    p.write_bytes(_PNG_MAGIC + b"\x00" * 20)
    return str(p)


@pytest.mark.asyncio
async def test_happy_path_recognized_meal(repository, sample_image):
    ai_service = FakeAIService([_rice_ingredient()])
    pipeline = FakePipeline({"rice": _rice_facts()})
    analyzer = FoodAnalyzer(ai_service, pipeline, repository)

    record = await analyzer.analyze(sample_image)

    assert record.meal_recognized is True
    assert record.id is not None
    assert len(record.ingredients) == 1
    assert record.totals.kcal > 0


@pytest.mark.asyncio
async def test_unrecognized_meal_does_not_crash(repository, sample_image):
    ai_service = FakeAIService([])  # VLM found nothing
    pipeline = FakePipeline({})
    analyzer = FoodAnalyzer(ai_service, pipeline, repository)

    record = await analyzer.analyze(sample_image)

    assert record.meal_recognized is False
    assert record.ingredients == []
    assert record.totals.kcal == 0.0


@pytest.mark.asyncio
async def test_missing_nutrition_data_is_reported_not_fatal(repository, sample_image):
    ai_service = FakeAIService([_rice_ingredient()])
    pipeline = FakePipeline({})  # lookup failed for every ingredient
    analyzer = FoodAnalyzer(ai_service, pipeline, repository)

    record = await analyzer.analyze(sample_image)

    assert record.meal_recognized is True
    assert record.ingredients[0].kcal == 0.0  # no facts found, zeroed not crashed


@pytest.mark.asyncio
async def test_invalid_image_path_raises_validation_error(repository):
    ai_service = FakeAIService([_rice_ingredient()])
    pipeline = FakePipeline({"rice": _rice_facts()})
    analyzer = FoodAnalyzer(ai_service, pipeline, repository)

    with pytest.raises(ValidationError):
        await analyzer.analyze("/does/not/exist.png")


@pytest.mark.asyncio
async def test_result_is_persisted_and_retrievable(repository, sample_image):
    ai_service = FakeAIService([_rice_ingredient()])
    pipeline = FakePipeline({"rice": _rice_facts()})
    analyzer = FoodAnalyzer(ai_service, pipeline, repository)

    record = await analyzer.analyze(sample_image)
    fetched = await repository.get(record.id)

    assert fetched is not None
    assert fetched.id == record.id