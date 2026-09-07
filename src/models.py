"""Pydantic models for the SE layer's own data shapes.

Why not just reuse ai/schemas.py everywhere?
----------------------------------------------
ai/schemas.py belongs to the provided AI module (Ingredient, NutritionFacts,
Nutrition) and is off-limits — we treat it as a frozen external contract.
The models here describe what OUR layer produces and stores: a per-ingredient
row enriched with computed nutrition, the full response for one image, and
the row we persist to Postgres. Splitting "response" from "stored record"
keeps the API free to change without touching the storage schema, and vice
versa.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class IngredientLine(BaseModel):
    """A single ingredient as shown to the caller — name/portion from the VLM,
    plus nutrition already scaled to the estimated grams."""

    model_config = ConfigDict(extra="forbid")

    name: str
    estimated_grams: float
    confidence: float
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float


class MealTotals(BaseModel):
    """Summed macros across every ingredient in the meal."""

    model_config = ConfigDict(extra="forbid")

    kcal: float = 0.0
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0


class AnalysisResult(BaseModel):
    """What the CLI prints and the API returns for one analyzed photo.

    meal_recognized=False means the VLM found nothing edible in the image —
    ingredients/totals stay empty and callers must not treat this as an error.
    """

    model_config = ConfigDict(extra="forbid")

    meal_recognized: bool
    image_path: str
    ingredients: list[IngredientLine] = Field(default_factory=list)
    totals: MealTotals = Field(default_factory=MealTotals)

    @property
    def ingredient_count(self) -> int:
        return len(self.ingredients)


class AnalysisRecord(BaseModel):
    """One row of the history log, as stored in / read from Postgres.

    id and created_at are filled in by the database on insert — they stay
    None on a record you're about to write.
    """

    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    created_at: datetime | None = None
    image_path: str
    ingredients: list[IngredientLine] = Field(default_factory=list)
    totals: MealTotals = Field(default_factory=MealTotals)

    @classmethod
    def from_result(cls, result: AnalysisResult) -> "AnalysisRecord":
        """Turn a fresh AnalysisResult into a record ready for insertion."""
        return cls(
            image_path=result.image_path,
            ingredients=result.ingredients,
            totals=result.totals,
        )
