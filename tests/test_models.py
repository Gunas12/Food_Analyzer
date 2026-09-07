"""Unit tests for src/models.py — fully offline, no DB or network."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models import AnalysisRecord, AnalysisResult, IngredientLine, MealTotals


def _rice_line(**overrides) -> IngredientLine:
    base = dict(
        name="rice", estimated_grams=180.0, confidence=0.9,
        kcal=234.0, protein_g=4.9, carbs_g=50.4, fat_g=0.5,
    )
    base.update(overrides)
    return IngredientLine(**base)


def test_ingredient_line_holds_expected_values():
    line = _rice_line()
    assert line.name == "rice"
    assert line.kcal == 234.0


def test_ingredient_line_rejects_unknown_field():
    with pytest.raises(ValidationError):
        _rice_line(mystery_field="not allowed")


def test_meal_totals_defaults_to_zero():
    totals = MealTotals()
    assert totals.kcal == 0.0
    assert totals.protein_g == 0.0


def test_unrecognized_meal_has_no_ingredients_or_totals():
    result = AnalysisResult(meal_recognized=False, image_path="blue.png")
    assert result.ingredients == []
    assert result.ingredient_count == 0
    assert result.totals == MealTotals()


def test_recognized_meal_reports_ingredient_count():
    result = AnalysisResult(
        meal_recognized=True, image_path="meal.png", ingredients=[_rice_line()],
    )
    assert result.ingredient_count == 1


def test_record_from_result_has_no_id_before_insert():
    result = AnalysisResult(
        meal_recognized=True, image_path="meal.png",
        ingredients=[_rice_line()],
        totals=MealTotals(kcal=234.0, protein_g=4.9, carbs_g=50.4, fat_g=0.5),
    )
    record = AnalysisRecord.from_result(result)
    assert record.id is None
    assert record.created_at is None
    assert record.image_path == "meal.png"
    assert record.totals.kcal == 234.0

def test_record_from_result_preserves_meal_recognized_flag():
    result = AnalysisResult(meal_recognized=False, image_path="blue.png")
    record = AnalysisRecord.from_result(result)
    assert record.meal_recognized is False