# Contribution Statement

**Team:** Team #1
**Topic:** Topic 2 — AI Food Analyzer
**Repository:** https://github.com/Gunas12/Food_Analyzer
**Final tag:** `v1.0-final`
**Submission date:** 2026-09-19

---

## Member 1 — Gunash Mammadova (`@Gunas12`)

**Owned (sole author of these files / PRs):**

- `src/config.py`, `src/models.py` — `pydantic-settings` typed `Settings` class + SE-layer Pydantic models (`AnalysisRecord`, status field: `ok` / `unknown_meal` / `error`)
- `src/wiring.py` (composition root) — builds the full object graph from `Settings` (AIService → pipeline → FoodAnalyzer + repository)
- `src/cli.py` — `python -m src.cli analyze <path>` command-line entry point
- `Dockerfile`, `docker-compose.yml`, `.dockerignore` — multi-stage production image + local Postgres/API stack
- `README.md`, `data/_make_samples.py` — project documentation + sample meal-image generator for offline testing
- Render.com deployment (`https://food-analyzer-tx9l.onrender.com/`) — live web UI + `/docs`
- PRs: #1 (typed settings & pydantic models), #2 (docker-compose for local PostgreSQL), #3 (preserve meal_recognized flag + config coverage), #11 (Gunash/validation), #14 (fix: src/wiring.py), #20 (Dockerfile: remove requirements-ai.txt), #21 (Revise README for Food Analyzer project)

**Co-owned (paired or substantially edited):**

- `requirements.txt` (with the whole team) — shared dependency list, kept in sync as each module added packages
- `src/core/analyzer.py` (merged with A. Muradov's pipeline) — main pipeline orchestration (validate → VLM → nutrition → totals → persist); wired Ali's `NutritionPipeline` into it

**Reviewed:**

- Every PR was reviewed and approved by another team member before merging; the PR author then merged it themselves once approved.

**Approximate share of commits:** ~25%

---

## Member 2 — Punhan Murselov (`@Punhan0`)

**Owned:**

- `src/storage/repository.py` — SQLAlchemy/asyncpg async repository: `init_models()`, `save()`, `get()`, `list_recent()` against PostgreSQL
- `tests/test_repository.py` — CRUD tests for the repository (against sqlite+aiosqlite in-memory DB)

**Co-owned:**

- `requirements.txt`, `requirements-ai.txt` — storage deps (`sqlalchemy`, `asyncpg`, `aiosqlite`, `pytest-asyncio`)
- `Dockerfile` (with Member 1) — Postgres service wiring in `docker-compose.yml`

**PRs:** #4 (Repository asinxron funksiyaları və testləri), #5 (fix: Repository testlərinin yeni modelə uyğunlaşdırılması), #12 (feat: CLI, Dockerfile, API service in docker-compose), #16 (Fix mypy errors), #17 (docs: README fayli elave edildi)

**Reviewed:**

- Every PR was reviewed and approved by another team member before merging; the PR author then merged it themselves once approved.

**Approximate share of commits:** ~25%

---

## Member 3 — Ali Muradov (`@Ali-Muradov`)

**Owned:**

- `src/services/ai_service.py` — retry wrapper around `ai.identify_ingredients()`: exponential backoff on `ProviderError`, logged at each attempt
- `src/services/nutrition_cache.py` — in-memory TTL cache (24h default) for nutrition lookups, avoids re-querying the same ingredient
- `src/concurrency/pipeline.py` — `NutritionPipeline`: `asyncio.gather` + `Semaphore(MAX_PARALLEL)` to look up N ingredients concurrently without one failure sinking the rest
- `tests/test_ai_service.py`, `tests/test_nutrition_cache.py`, `tests/test_pipeline.py` — retry-path, cache hit/miss/TTL, and concurrency/semaphore-bound tests

**Co-owned:**

- `src/core/analyzer.py` (with Member 1) — his `NutritionPipeline` was wired into the main pipeline here
- `requirements.txt` (with the whole team) — retry/cache/concurrency deps kept in sync

**PRs:** #6 (add: cache nutrition facts with a TTL), #7 (add: retry synchronous AI provider calls), #8 (add: run nutrition lookups in parallel), #9 (test: cover provider and pipeline edge cases)

**Reviewed:**

- Every PR was reviewed and approved by another team member before merging; the PR author then merged it themselves once approved.

**Approximate share of commits:** ~25%

---

## Member 4 — Esmira Mammadli (`@EsmiraMammadli`)

**Owned:**

- `src/api.py` — FastAPI app: `POST /analyze`, `GET /health`, `GET /analyses/{id}`, error mapping (`ValidationError`→400, `ProviderError`→503), startup/shutdown lifespan hooks
- `static/index.html` — single-page browser demo UI: drag-and-drop image upload, nutrition-facts results table, analysis history
- `tests/test_api.py` — endpoint tests via FastAPI `TestClient` (`/health`, `/analyze` offline, `/analyses/{id}`)
- `scripts/bench.py` — sequential vs. concurrent nutrition-lookup benchmark, results fed into the README

**Co-owned:**

- `requirements.txt` (with the whole team) — API deps (`fastapi`, `uvicorn`, `python-multipart`, `httpx`) kept in sync
- Template/doc files (`.github/pull_request_template.md`) — team PR-description checklist

**PRs:** #10 (add: FastAPI endpoints for analyze/health/get), #13 (add: google-genai dependency, static web UI, PR template), #15, #18 (fix(api): assert database_url before Repository construction), #19 (user4/fix-api-mypy)

**Reviewed:**

- Every PR was reviewed and approved by another team member before merging; the PR author then merged it themselves once approved.

**Approximate share of commits:** ~25%

---

## Signatures

| Member           | Signature                            | Date             |
| ---------------- | ------------------------------------ | ---------------- |
| Gunash Mammadova | ****\*\*\*\*****\_\_****\*\*\*\***** | \***\*\_\_\*\*** |
| Punhan Murselov  | ****\*\*\*\*****\_\_****\*\*\*\***** | \***\*\_\_\*\*** |
| Ali Muradov      | ****\*\*\*\*****\_\_****\*\*\*\***** | \***\*\_\_\*\*** |
| Esmira Mammadli  | ****\*\*\*\*****\_\_****\*\*\*\***** | \***\*\_\_\*\*** |
