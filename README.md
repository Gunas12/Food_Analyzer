# Food Analyzer

> Upload a meal photo → AI identifies ingredients with portion sizes → USDA nutrition
> lookup → calories and macronutrient totals.

**Team:** Team #1
**Topic:** Topic 2 — AI Food Analyzer
**Course:** AI-ENG-110 Software Engineering, AI Academy
**Repository:** https://github.com/Gunas12/Food_Analyzer
**Final tag:** `v1.0-final`

---

## Quick start (Docker)

```bash
git clone https://github.com/Gunas12/Food_Analyzer.git
cd Food_Analyzer
cp .env.example .env
# fill in LLM_PROVIDER / API keys / USDA_API_KEY in .env

docker compose up --build
```

This starts PostgreSQL and the API together. Open **http://localhost:8000**
for the demo UI, or use the API directly (below).

## Running without Docker

```bash
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\Activate.ps1     # Windows PowerShell

pip install -r requirements.txt
cp .env.example .env

PYTHONPATH=. uvicorn src.api:app --reload --port 8000
```

### CLI (offline, no API keys needed)

```bash
python data/_make_samples.py
PYTHONPATH=. python -m src.cli analyze data/rice_chicken_broccoli.png
```

---

## API usage

### Health check

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### Analyze a meal photo

```bash
curl -X POST http://localhost:8000/analyze -F "file=@data/rice_chicken_broccoli.png"
```

```json
{
  "id": 6,
  "created_at": "2026-09-18T09:47:52.747432Z",
  "image_path": "/app/uploads/8328acf4af0144c1aa8e3b0f650b7ca9.png",
  "meal_recognized": true,
  "ingredients": [
    {"name": "grilled beef patty", "estimated_grams": 150.0, "confidence": 0.8,
     "kcal": 1860.0, "protein_g": 34.5, "carbs_g": 0.0, "fat_g": 32.7},
    {"name": "white rice", "estimated_grams": 120.0, "confidence": 0.85,
     "kcal": 430.8, "protein_g": 8.328, "carbs_g": 95.76, "fat_g": 1.56},
    {"name": "steamed broccoli", "estimated_grams": 40.0, "confidence": 0.85,
     "kcal": 648.0, "protein_g": 3.888, "carbs_g": 30.08, "fat_g": 2.072}
  ],
  "totals": {"kcal": 2938.8, "protein_g": 46.716, "carbs_g": 125.84, "fat_g": 36.332}
}
```

### Fetch a past analysis

```bash
curl http://localhost:8000/analyses/1
```

```json
{
  "id": 1,
  "created_at": "2026-09-15T11:10:02.563577Z",
  "image_path": "/app/uploads/8cfee6f29d3c44bb89de0d9049e92156.png",
  "meal_recognized": true,
  "ingredients": [
    {"name": "beef patty", "estimated_grams": 110.0, "confidence": 0.75,
     "kcal": 1364.0, "protein_g": 25.3, "carbs_g": 0.0, "fat_g": 23.98},
    {"name": "hard-boiled egg", "estimated_grams": 50.0, "confidence": 0.85,
     "kcal": 77.5, "protein_g": 6.3, "carbs_g": 0.56, "fat_g": 5.3}
  ],
  "totals": {"kcal": 1441.5, "protein_g": 31.6, "carbs_g": 0.56, "fat_g": 29.28}
}
```

404 is returned for an unknown id.

---

## Tests

```bash
PYTHONPATH=. pytest
PYTHONPATH=. pytest tests/test_ai_smoke.py -v
PYTHONPATH=. pytest --cov=src --cov-report=term-missing
```

All tests run offline (AI module and HTTP calls mocked). Latest results:

- 143/143 tests passing
- `src/` coverage: **97%** (`src/api.py` 89%, `src/cli.py` 98%, rest 100%)
- `tests/test_ai_smoke.py` untouched, passing
- `mypy src/` — 0 errors (one pre-existing warning in the provided `ai/providers/openai.py`)

---

## Docker

```bash
docker compose up --build   # start PostgreSQL + API
docker compose down         # stop, keep data
docker compose down -v      # stop and delete data
```

---

## Project layout

```
Food_Analyzer/
├── ai/                          # PROVIDED — not modified
│   ├── providers/                # Anthropic, OpenAI, Gemini adapters
│   ├── vlm.py                    # identify_ingredients()
│   ├── nutrition.py               # NutritionProvider / USDAProvider
│   ├── calculator.py              # compute_totals()
│   └── schemas.py                 # Ingredient, NutritionFacts
│
├── src/
│   ├── config.py                  # typed Settings via pydantic-settings
│   ├── models.py                  # AnalysisRecord, IngredientLine, MealTotals
│   ├── validation.py              # image format / size checks
│   ├── wiring.py                  # composition root
│   ├── cli.py                     # python -m src.cli analyze <path>
│   ├── api.py                     # FastAPI: POST /analyze, GET /analyses/{id}, GET /health
│   ├── core/analyzer.py           # pipeline: validate → VLM → nutrition → totals → save
│   ├── services/
│   │   ├── ai_service.py           # retry wrapper around ai.*
│   │   └── nutrition_cache.py      # TTL cache (24h default)
│   ├── concurrency/pipeline.py    # asyncio.gather + Semaphore for parallel lookups
│   └── storage/repository.py      # SQLAlchemy async repository, PostgreSQL
│
├── tests/                        # 143 tests, all offline
├── data/                          # sample meal images
├── static/index.html              # demo UI
├── scripts/bench.py                # sequential vs concurrent benchmark
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── TOPIC.md
```

---

## Architecture

```
Browser / curl
      │
      ▼
FastAPI  src/api.py
  ├── POST /analyze
  │     ├── validation.py          → format/size checks
  │     ├── AIService.identify_ingredients()   ← retry
  │     │       └── ai.vlm.identify_ingredients()   (Gemini / Anthropic / OpenAI)
  │     ├── NutritionPipeline.lookup()          ← asyncio.gather + Semaphore
  │     │       ├── NutritionCache (TTL)
  │     │       └── ai.nutrition.USDAProvider.lookup()
  │     ├── ai.calculator.compute_totals()
  │     └── repository.save()                    ← PostgreSQL
  │
  └── GET /analyses/{id}  → repository.get() → PostgreSQL
```

Full diagram and design rationale: [`docs/architecture.md`](docs/architecture.md).

---

## Sequential vs concurrent benchmark

| Workload | N (ingredients) | Sequential | Concurrent (semaphore=10) | Speedup |
|---|---|---|---|---|
| Nutrition lookup, simulated 150 ms latency per call | 10 | 1.522 s | 0.168 s | **9.0×** |

**Reproduce:**

```bash
python scripts/bench.py     # set PYTHONPATH=. first if running outside Docker
```

---

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | VLM provider (`anthropic` / `openai` / `gemini`) |
| `LLM_MODEL` | — | Model id |
| `GOOGLE_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | — | key for the chosen provider |
| `USDA_API_KEY` | — | USDA FoodData Central key |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:dev@localhost:5432/foodanalyzer` | PostgreSQL connection |
| `NUTRITION_CACHE_TTL_SECONDS` | `86400` | Cache TTL |
| `MAX_IMAGE_SIZE_MB` | `5` | Upload size limit |
| `MAX_PARALLEL` | `10` | Semaphore bound for nutrition lookups |
| `HTTP_PORT` | `8000` | API port |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

Full list: `.env.example`.

---

## SE layer — what we built

| Requirement | Implementation |
|---|---|
| Typed config | `pydantic-settings` `Settings`, `get_settings()` |
| Image validation | MIME/suffix check, size limit, safe filename (UUID) |
| Structured logging | `logging` module |
| Retries | `AIService` — 3 attempts, exponential backoff |
| Cache | `NutritionCache` — in-memory TTL cache |
| Concurrency | `asyncio.gather` + `Semaphore` — `src/concurrency/pipeline.py` |
| Storage | PostgreSQL, `src/storage/repository.py` |
| HTTP API | FastAPI `POST /analyze`, `GET /analyses/{id}`, `GET /health` |
| CLI | `python -m src.cli analyze <path>` |
| Tests | 143 tests, offline, `pytest-asyncio` |
| Docker | `docker-compose.yml` (PostgreSQL + API) + `Dockerfile` |
| Demo UI | `static/index.html` |

---

## Git workflow

- `main` is protected — all changes go through Pull Requests
- Every PR requires at least one teammate's review
- Final release tag: `v1.0-final`

---

## Team

| # | Member | GitHub | Focus |
|---|---|---|---|
| 1 | Gunash Mammadova | [@Gunas12](https://github.com/Gunas12) | Config, models, wiring, CLI, Docker, final integration |
| 2 | Punhan Murselov | [@Punhan0](https://github.com/Punhan0) | Storage (repository, PostgreSQL) |
| 3 | Ali Muradov | [@Ali-Muradov](https://github.com/Ali-Muradov) | AIService (retry), NutritionCache, concurrency pipeline |
| 4 | Esmira Mammadli | [@EsmiraMammadli](https://github.com/EsmiraMammadli) | FastAPI endpoints, static demo UI |

Per-member file/PR ownership: [`report/CONTRIBUTION_STATEMENT.md`](report/CONTRIBUTION_STATEMENT.md).
AI tool disclosure: `report/report.pdf` §10 and [`report/CONTRIBUTION_STATEMENT.md`](report/CONTRIBUTION_STATEMENT.md).

## License

Academic coursework, not a published library.
