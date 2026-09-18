"""The business-logic orchestrator: photo -> ingredients -> nutrition ->
totals -> persisted AnalysisRecord.

This is the one place that wires validation, AI identification, the
concurrent nutrition pipeline, and storage together. `cli.py` is a thin
adapter over `FoodAnalyzer.analyze`. The HTTP API's `/analyze` endpoint
does not call this class directly (it needs to interleave upload-specific
steps — content-type checks, per-step 503s — with the pipeline calls),
but it shares the same ingredient/totals-building logic via
`src.core.lines.build_ingredient_lines`, so that piece cannot drift
between the two entry points.
"""

from __future__ import annotations

from src.core.lines import build_ingredient_lines
from src.models import AnalysisRecord
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
        lines, totals = build_ingredient_lines(ingredients, facts_by_name)

        record = AnalysisRecord(
            image_path=str(validated_path),
            meal_recognized=True,
            ingredients=lines,
            totals=totals,
        )
        return await self._repository.save(record)