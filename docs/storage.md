# Storage

## Database

PostgreSQL 16 (Docker: `postgres:16-alpine`), accessed asynchronously via the
`asyncpg` driver. The connection is configured through `DATABASE_URL`
(`postgresql+asyncpg://...`) in `src/config.py`.

## Table: `analysis_records`

(SQLAlchemy `AnalysisRecordModel` in `src/storage/repository.py`.)

| Column | Type | Description |
|---|---|---|
| `id` | `Integer PRIMARY KEY, autoincrement` | auto-incrementing id |
| `created_at` | `DateTime(timezone=True)`, default `now(timezone.utc)` | set on insert |
| `image_path` | `String`, not null | path to the uploaded image on disk (`uploads/<uuid>.png`) |
| `meal_recognized` | `Boolean`, not null, default `True` | whether the VLM recognized the meal |
| `ingredients` | `JSON`, not null | list of `IngredientLine` dicts (name, grams, confidence, kcal, protein, carbs, fat) |
| `totals` | `JSON`, not null | `MealTotals` dict (kcal, protein_g, carbs_g, fat_g) |

There is no separate `status` column — "unrecognized meal" is represented by
`meal_recognized=False` with empty `ingredients` and zeroed `totals`, not by a
distinct status string.

The table is created by `Repository.init_models()` on application startup
(idempotent, via `Base.metadata.create_all`) — no separate migration tool is used.

## `Repository` interface (`src/storage/repository.py`)

```python
async def init_models(self) -> None: ...      # creates the table (idempotent)
async def save(self, record: AnalysisRecord) -> AnalysisRecord: ...   # fills id/created_at
async def get(self, record_id: int) -> AnalysisRecord | None: ...
async def list_recent(self, limit: int = 20) -> list[AnalysisRecord]: ...
```

`list_recent()` is implemented and tested (`tests/test_repository.py`) but is
**not yet exposed over HTTP** — there is no `GET /analyses` list endpoint in
`src/api.py`, only `GET /analyses/{id}` for a single record. If a history view
is wanted for the demo, wiring `list_recent()` into a new `GET /analyses`
route is a small, low-risk addition worth doing before the deadline if there's
time, or naming explicitly as a known gap in the report's Limitations section
if not.

## Image blobs

Uploaded images are stored on the filesystem, not in the database (`uploads/`
directory, listed in `.gitignore`). The on-disk filename is generated
server-side as a UUID rather than trusted from the client, to prevent
path-traversal attacks (see `src/api.py::_safe_upload_path`).

## Running tests without a live database

`tests/test_repository.py` does not require a real PostgreSQL instance — it
exercises the same `Repository` interface against
`sqlite+aiosqlite:///:memory:`, so tests stay fully offline in CI and locally.

## Nutrition cache vs. storage

`NutritionCache` (`src/services/nutrition_cache.py`) is a separate,
process-local, in-memory TTL cache — not to be confused with the
`analysis_records` history table in PostgreSQL. The cache resets on server
restart; the table persists.
