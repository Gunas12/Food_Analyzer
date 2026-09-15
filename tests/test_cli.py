"""CLI tests — build_components is monkeypatched so nothing here touches
real network/DB. We only exercise our own code."""
from __future__ import annotations

import pytest

from ai.schemas import Ingredient, NutritionFacts

from src.cli import _render, main
from src.models import AnalysisRecord, IngredientLine, MealTotals
from src.storage.repository import Repository
from src.wiring import Components

_PNG_MAGIC = bytes.fromhex("89504e470d0a1a0a")


class FakeAIService:
    def __init__(self, ingredients):
        self._ingredients = ingredients

    async def identify_ingredients(self, image_path, **kwargs):
        return self._ingredients


class FakePipeline:
    def __init__(self, facts_by_name):
        self._facts_by_name = facts_by_name

    async def lookup(self, ingredients):
        return self._facts_by_name


def test_render_recognized_meal():
    record = AnalysisRecord(
        image_path="x.png", meal_recognized=True,
        ingredients=[IngredientLine(
            name="rice", estimated_grams=180.0, confidence=0.9,
            kcal=234.0, protein_g=4.9, carbs_g=50.4, fat_g=0.5,
        )],
        totals=MealTotals(kcal=234.0, protein_g=4.9, carbs_g=50.4, fat_g=0.5),
    )
    out = _render(record)
    assert "rice" in out
    assert "TOTAL" in out
    assert "kcal=234" in out


def test_render_unknown_meal():
    record = AnalysisRecord(image_path="x.png", meal_recognized=False)
    assert _render(record) == "Meal not recognized in image."


def _fake_build_components(settings):
    repo = Repository("sqlite+aiosqlite:///:memory:")
    ai_service = FakeAIService(
        [Ingredient(name="rice", estimated_grams=180.0, confidence=0.9)]
    )
    pipeline = FakePipeline({
        "rice": NutritionFacts(
            name="rice", kcal_per_100g=130, protein_g_per_100g=2.7,
            carbs_g_per_100g=28.0, fat_g_per_100g=0.3,
        ),
    })
    return Components(
        repository=repo, ai_service=ai_service,
        nutrition_provider=None, pipeline=pipeline,
    )


def test_main_exits_zero_on_success(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("src.cli.build_components", _fake_build_components)
    p = tmp_path / "meal.png"
    p.write_bytes(_PNG_MAGIC + b"\x00" * 20)

    with pytest.raises(SystemExit) as exc_info:
        main(["analyze", str(p)])

    assert exc_info.value.code == 0
    assert "TOTAL" in capsys.readouterr().out


def test_main_exits_two_on_missing_file(monkeypatch, capsys):
    monkeypatch.setattr("src.cli.build_components", _fake_build_components)

    with pytest.raises(SystemExit) as exc_info:
        main(["analyze", "/no/such/file.png"])

    assert exc_info.value.code == 2
    assert "error:" in capsys.readouterr().err
