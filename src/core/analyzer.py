"""The business-logic orchestrator: photo -> ingredients -> nutrition ->
totals -> persisted AnalysisRecord.

This is the one place that wires validation, AI identification, the
concurrent nutrition pipeline, and storage together. `cli.py` is a thin
adapter over `FoodAnalyzer.analyze` — it doesn't duplicate this logic
(the API doesn't call this class today; it builds its own inline flow in
create_app(), but the steps mirror each other 1:1).
"""

from __future__ import annotations

from ai.calculator import compute_totals

from src.models import AnalysisRecord, IngredientLine, MealTotals
from src.services import AIService, NutritionCache
from src.storage.repository import Repository
from src.validation import ValidationError, validate_image_path


class FoodAnalyzer:
    def __init__(
        self,
        ai_service: AIService,
        pipeline,  # NutritionPipeline — typed loosely to avoid a hard import cycle
        repository: Repository,
        *,
        max_image_size_mb: float = 5.0,
    ) -> None:
        self._ai_service = ai_service
        self._pipeline = pipeline
        self._repository = repository
        self._max_image_size_mb = max_image_size_mb

    async def analyze(self, image_path: str) -> AnalysisRecord:
        """Run the full pipeline for one image and persist the result.

        Only ValidationError (bad input) propagates to the caller — an
        unrecognized meal or a partial nutrition lookup are normal outcomes,
        represented in the returned AnalysisRecord, not exceptions.
        """
        validated_path = validate_image_path(
            image_path, max_size_mb=self._max_image_size_mb
        )

        ingredients = await self._ai_service.identify_ingredients(str(validated_path))

        if not ingredients:
            record = AnalysisRecord(
                image_path=str(validated_path),
                meal_recognized=False,
            )
            return await self._repository.save(record)

        facts_by_name = await self._pipeline.lookup(ingredients)

        lines: list[IngredientLine] = []
        for ing in ingredients:
            facts = facts_by_name.get(ing.name)
            if facts is None:
                lines.append(
                    IngredientLine(
                        name=ing.name,
                        estimated_grams=ing.estimated_grams,
                        confidence=ing.confidence,
                        kcal=0.0, protein_g=0.0, carbs_g=0.0, fat_g=0.0,
                    )
                )
                continue
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

        totals_nutrition = compute_totals(ingredients, facts_by_name)
        totals = MealTotals(**totals_nutrition.to_dict())

        record = AnalysisRecord(
            image_path=str(validated_path),
            meal_recognized=True,
            ingredients=lines,
            totals=totals,
        )
        return await self._repository.save(record)