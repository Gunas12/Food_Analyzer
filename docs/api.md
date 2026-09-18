# HTTP API

Base URL: `http://localhost:8000` (configurable via `HTTP_PORT`).

## `GET /health`

Health check. No auth required.

```bash
curl http://localhost:8000/health
```

```json
{"status": "ok"}
```

## `POST /analyze`

Uploads a meal photo, analyzes it, persists the result to PostgreSQL, and
returns it.

- **Body:** `multipart/form-data`, field name `file`
- **Accepted types:** `image/jpeg`, `image/png`
- **Size limit:** `MAX_IMAGE_SIZE_MB` (default 5 MB)

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
     "kcal": 430.8, "protein_g": 8.328, "carbs_g": 95.76, "fat_g": 1.56}
  ],
  "totals": {"kcal": 2290.8, "protein_g": 42.828, "carbs_g": 95.76, "fat_g": 34.26}
}
```

An unrecognized meal returns `"meal_recognized": false` with an empty
`ingredients` list and zeroed `totals` — there is no separate `status` field.

**Error responses:**

| Status | Reason |
|---|---|
| `400` | Invalid image format / size limit exceeded / validation error |
| `503` | VLM provider (Gemini/Anthropic/OpenAI) or USDA is unavailable |

## `GET /analyses/{id}`

Fetches a past analysis by id.

```bash
curl http://localhost:8000/analyses/1
```

- **200 OK** → `AnalysisRecord` JSON
- **404 Not Found** → `{"detail": "Analysis not found."}`

## `GET /`

Serves the static demo UI (`static/index.html`) — drag-and-drop image upload
with a results table.
