"""Shared helper for turning identified ingredients + nutrition facts into
the SE-layer response shape (IngredientLine list + MealTotals).

Both `FoodAnalyzer.analyze` (used by the CLI) and the HTTP API's
`/analyze` endpoint call this same function, so this piece of business
logic cannot silently diverge between the two entry points.
"""

from __future__ import annotations

from ai import Ingredient, NutritionFacts, compute_totals

from src.models import IngredientLine, MealTotals


def build_ingredient_lines(
    ingredients: list[Ingredient],
    facts_by_name: dict[str, NutritionFacts],
) -> tuple[list[IngredientLine], MealTotals]:
    """Turn ingredients + looked-up facts into the SE-layer response shape.

    An ingredient with no entry in `facts_by_name` (lookup failed even
    after the pipeline's retries) is still listed, just with zero macros —
    one bad lookup must not sink the rest of the meal.
    """
    lines: list[IngredientLine] = []
    for ing in ingredients:
        facts = facts_by_name.get(ing.name)
        if facts is None:
            lines.append(
                IngredientLine(
                    name=ing.name,
                    estimated_grams=ing.estimated_grams,
                    confidence=ing.confidence,
                    kcal=0.0,
                    protein_g=0.0,
                    carbs_g=0.0,
                    fat_g=0.0,
                )
            )
            continue

        # facts are per-100g; scale to this ingredient's estimated portion.
        portion = facts.for_grams(ing.estimated_grams)
        lines.append(
            IngredientLine(
                name=ing.name,
                estimated_grams=ing.estimated_grams,
                confidence=ing.confidence,
                kcal=portion.kcal,
                protein_g=portion.protein_g,
                carbs_g=portion.carbs_g,
                fat_g=portion.fat_g,
            )
        )

    # Reuse the ai/ package's own totals function rather than summing by hand.
    totals_nutrition = compute_totals(ingredients, facts_by_name)
    totals = MealTotals(**totals_nutrition.to_dict())
    return lines, totals