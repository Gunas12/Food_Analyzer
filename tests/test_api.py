"""Offline tests for src/api.py.

Everything here runs without network access and without a real Postgres
instance: the repository, the VLM and the nutrition provider are all fakes
injected via `create_app(...)`. `AIService` is overridden with zero retry
delay so a failing lookup doesn't slow the suite down with real backoff.
"""

from __future__ import annotations

import io
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ai.providers.base import ProviderError, VLMProvider
from ai.nutrition import NutritionProvider
from ai.schemas import NutritionFacts

from src.api import create_app
from src.models import AnalysisRecord
from src.services import AIService

# A minimal valid 1x1 PNG, reused from the ai/ test fixtures pattern.
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000"
    "00907753de0000000c4944415408d7636000000000000400000146a13a"
    "020000000049454e44ae426082"
)

# No retries, no sleeping — keeps tests fast and deterministic.
_FAST_AI_SERVICE_KWARGS = {"max_attempts": 1, "base_delay": 0.0}


class FakeVLM(VLMProvider):
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload or {
            "meal_recognized": True,
            "ingredients": [
                {"name": "white rice (cooked)", "estimated_grams": 200.0, "confidence": 0.9},
            ],
        }

    def describe(self, image_path: str, prompt: str, *, json_schema=None) -> str:
        return json.dumps(self.payload)


class FakeNutrition(NutritionProvider):
    DB = {
        "white rice (cooked)": NutritionFacts(
            name="Rice, white, cooked",
            kcal_per_100g=130, protein_g_per_100g=2.7,
            carbs_g_per_100g=28, fat_g_per_100g=0.3,
            source="fake",
        ),
    }

    def __init__(self) -> None:
        self.calls: list[str] = []

    def lookup(self, ingredient_name: str) -> NutritionFacts:
        self.calls.append(ingredient_name)
        if ingredient_name not in self.DB:
            raise ProviderError(f"unknown ingredient: {ingredient_name!r}")
        return self.DB[ingredient_name]


class FakeRepository:
    """In-memory stand-in for User #2's Repository (same async surface)."""

    def __init__(self) -> None:
        self._store: dict[int, AnalysisRecord] = {}
        self._next_id = 1

    async def init_models(self) -> None:
        return None

    async def save(self, record: AnalysisRecord) -> AnalysisRecord:
        if record.id is None:
            record = record.model_copy(update={"id": self._next_id})
            self._next_id += 1
        self._store[record.id] = record
        return record

    async def get(self, record_id: int) -> AnalysisRecord | None:
        return self._store.get(record_id)

    async def list_recent(self, limit: int = 20) -> list[AnalysisRecord]:
        return list(self._store.values())[:limit]


@pytest.fixture
def client(tmp_path):
    repo = FakeRepository()
    app = create_app(
        repository=repo,
        upload_dir=tmp_path / "uploads",
        max_image_size_mb=5,
        get_vlm_fn=lambda: FakeVLM(),
        get_nutrition_fn=lambda: FakeNutrition(),
        ai_service=AIService(**_FAST_AI_SERVICE_KWARGS),
    )
    with TestClient(app) as c:
        yield c, repo


def test_health(client):
    c, _ = client
    resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_analyze_happy_path(client):
    c, _ = client
    files = {"file": ("meal.png", io.BytesIO(_PNG_BYTES), "image/png")}
    resp = c.post("/analyze", files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["meal_recognized"] is True
    assert body["totals"]["kcal"] > 0
    assert body["ingredients"][0]["name"] == "white rice (cooked)"
    assert "id" in body


def test_analyze_unknown_meal(client):
    _, repo = client
    files = {"file": ("blue.png", io.BytesIO(_PNG_BYTES), "image/png")}
    fresh = create_app(
        repository=repo,
        upload_dir=None,
        max_image_size_mb=5,
        get_vlm_fn=lambda: FakeVLM({"meal_recognized": False, "ingredients": []}),
        get_nutrition_fn=lambda: FakeNutrition(),
        ai_service=AIService(**_FAST_AI_SERVICE_KWARGS),
    )
    with TestClient(fresh) as c2:
        resp = c2.post("/analyze", files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["meal_recognized"] is False
    assert body["ingredients"] == []


def test_analyze_unknown_ingredient_still_returns_ok(client):
    files = {"file": ("meal.png", io.BytesIO(_PNG_BYTES), "image/png")}
    fresh_vlm = FakeVLM(
        {
            "meal_recognized": True,
            "ingredients": [
                {"name": "mystery sauce", "estimated_grams": 50.0, "confidence": 0.4}
            ],
        }
    )
    app = create_app(
        repository=FakeRepository(),
        upload_dir=None,
        max_image_size_mb=5,
        get_vlm_fn=lambda: fresh_vlm,
        get_nutrition_fn=lambda: FakeNutrition(),
        ai_service=AIService(**_FAST_AI_SERVICE_KWARGS),
    )
    with TestClient(app) as c2:
        resp = c2.post("/analyze", files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["meal_recognized"] is True
    assert body["ingredients"][0]["kcal"] == 0.0
    assert body["totals"]["kcal"] == 0.0


def test_analyze_reuses_cache_across_requests(client):
    """Second /analyze with the same ingredient should hit the shared cache,
    i.e. the underlying provider is called at most once for that name."""
    c, _ = client
    fake_nutrition = FakeNutrition()
    app = create_app(
        repository=FakeRepository(),
        upload_dir=None,
        max_image_size_mb=5,
        get_vlm_fn=lambda: FakeVLM(),
        get_nutrition_fn=lambda: fake_nutrition,
        ai_service=AIService(**_FAST_AI_SERVICE_KWARGS),
    )
    with TestClient(app) as c2:
        files1 = {"file": ("meal1.png", io.BytesIO(_PNG_BYTES), "image/png")}
        files2 = {"file": ("meal2.png", io.BytesIO(_PNG_BYTES), "image/png")}
        c2.post("/analyze", files=files1)
        c2.post("/analyze", files=files2)
    assert fake_nutrition.calls.count("white rice (cooked)") == 1


def test_analyze_rejects_bad_content_type(client):
    c, _ = client
    files = {"file": ("meal.txt", io.BytesIO(b"not an image"), "text/plain")}
    resp = c.post("/analyze", files=files)
    assert resp.status_code == 400


def test_analyze_rejects_oversized_file(client):
    c, _ = client
    big = io.BytesIO(b"0" * (6 * 1024 * 1024))
    files = {"file": ("meal.png", big, "image/png")}
    resp = c.post("/analyze", files=files)
    assert resp.status_code == 400


def test_get_analysis_not_found(client):
    c, _ = client
    resp = c.get("/analyses/999999")
    assert resp.status_code == 404


def test_get_analysis_returns_saved_record(client):
    c, _ = client
    files = {"file": ("meal.png", io.BytesIO(_PNG_BYTES), "image/png")}
    created = c.post("/analyze", files=files).json()
    resp = c.get(f"/analyses/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]
