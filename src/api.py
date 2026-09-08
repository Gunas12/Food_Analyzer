"""HTTP API for the Food Analyzer — User #4 deliverable.

Endpoints
---------
POST /analyze          multipart image upload -> AnalysisRecord (JSON)
GET  /health            -> {"status": "ok"}
GET  /analyses/{id}     -> AnalysisRecord (JSON) or 404

Wiring: VLM identification goes through User #3's `AIService`
(retries w/ backoff); per-ingredient nutrition lookups go through
User #3's `NutritionPipeline` (bounded parallel + shared TTL cache).
Storage is User #2's `Repository`, config is User #1's `Settings`.
`ai/` is never modified or called directly, per the project contract.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import ValidationError

from ai import Ingredient, NutritionFacts, NutritionProvider, compute_totals, get_nutrition_provider
from ai.providers.base import ProviderError, VLMProvider

from src.concurrency import NutritionPipeline
from src.config import get_settings
from src.models import AnalysisRecord, IngredientLine, MealTotals
from src.services import AIService, NutritionCache
from src.storage.repository import Repository

logger = logging.getLogger(__name__)

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
_ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png"}


def _safe_upload_path(upload_dir: Path, original_filename: str) -> Path:
    """Build a collision-free, traversal-safe path for an uploaded image.

    Never trusts the client-supplied filename beyond its extension —
    the actual on-disk name is a fresh UUID (see docs/COMMON_PITFALLS.md #11).
    """
    suffix = Path(original_filename or "").suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        suffix = ".bin"
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Generate the on-disk name ourselves (UUID) — never trust user input,
    # so a filename like "../../etc/passwd" can't do anything.
    candidate = (upload_dir / f"{uuid.uuid4().hex}{suffix}").resolve()
    if not str(candidate).startswith(str(upload_dir.resolve())):
        raise ValueError("resolved path escapes the upload directory")
    return candidate


async def _validate_and_save_image(
    file: UploadFile, upload_dir: Path, max_size_mb: float
) -> Path:
    """Reject anything that isn't a small JPEG/PNG, then write it to disk."""
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported content type: {file.content_type!r}. "
            "Only image/jpeg and image/png are accepted.",
        )

    max_bytes = int(max_size_mb * 1024 * 1024)
    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds the {max_size_mb} MB limit.",
        )

    path = _safe_upload_path(upload_dir, file.filename or "")
    path.write_bytes(contents)
    return path


def _build_ingredient_lines(
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


def create_app(
    *,
    repository: Optional[Repository] = None,
    upload_dir: Optional[Path] = None,
    max_image_size_mb: Optional[float] = None,
    get_vlm_fn: Optional[Callable[[], VLMProvider]] = None,
    get_nutrition_fn: Optional[Callable[[], NutritionProvider]] = None,
    ai_service: Optional[AIService] = None,
    nutrition_cache: Optional[NutritionCache] = None,
    max_parallel: Optional[int] = None,
) -> FastAPI:
    """Build the FastAPI app.

    All parameters are optional overrides for testing. In production,
    everything is derived from `get_settings()`.
    """
    settings = get_settings()
    repo = repository or Repository(settings.database_url)
    upload_dir = upload_dir or Path(settings.upload_dir)
    max_mb = max_image_size_mb if max_image_size_mb is not None else settings.max_image_size_mb
    vlm_factory = get_vlm_fn  # None -> ai.identify_ingredients picks the configured provider
    nutrition_factory = get_nutrition_fn or get_nutrition_provider
    parallel_limit = max_parallel if max_parallel is not None else settings.max_parallel

    # Shared across every request on this app instance — a fresh cache per
    # request would never get a hit, and AIService itself is stateless/cheap
    # to share (its retry policy is app-wide, not per-call).
    shared_ai_service = ai_service or AIService()
    shared_cache = nutrition_cache or NutritionCache(ttl_seconds=settings.nutrition_cache_ttl_seconds)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await repo.init_models()
        logger.info("api_startup")
        yield
        close = getattr(repo, "close", None)
        if callable(close):
            await close()
        elif hasattr(repo, "engine"):
            await repo.engine.dispose()
        logger.info("api_shutdown")

    app = FastAPI(title="Food Analyzer API", lifespan=lifespan)
    app.state.repository = repo
    app.state.ai_service = shared_ai_service
    app.state.nutrition_cache = shared_cache

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.post("/analyze")
    async def analyze(file: UploadFile = File(...)):
        image_path = await _validate_and_save_image(file, upload_dir, max_mb)

        vlm = vlm_factory() if vlm_factory else None
        try:
            ingredients = await shared_ai_service.identify_ingredients(str(image_path), vlm=vlm)
        except ProviderError as e:
            logger.warning("vlm_call_failed", extra={"error": str(e)})
            raise HTTPException(status_code=503, detail="AI provider unavailable.") from e

        if not ingredients:
            record = AnalysisRecord(
                image_path=str(image_path),
                meal_recognized=False,
                ingredients=[],
                totals=MealTotals(),
            )
            saved = await repo.save(record)
            return saved.model_dump(mode="json")

        try:
            nutrition = nutrition_factory()
        except ProviderError as e:
            logger.warning("nutrition_provider_unavailable", extra={"error": str(e)})
            raise HTTPException(status_code=503, detail="Nutrition provider unavailable.") from e

        pipeline = NutritionPipeline(
            nutrition,
            cache=shared_cache,
            ai_service=shared_ai_service,
            max_parallel=parallel_limit,
        )
        facts_by_name = await pipeline.lookup(ingredients)
        lines, totals = _build_ingredient_lines(ingredients, facts_by_name)

        try:
            record = AnalysisRecord(
                image_path=str(image_path),
                meal_recognized=True,
                ingredients=lines,
                totals=totals,
            )
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        saved = await repo.save(record)
        return saved.model_dump(mode="json")

    @app.get("/analyses/{analysis_id}")
    async def get_analysis(analysis_id: int):
        record = await repo.get(analysis_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Analysis not found.")
        return record.model_dump(mode="json")

    return app


app = create_app()
