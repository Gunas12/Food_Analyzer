# ---- Build stage ----
FROM python:3.12-slim AS builder
WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements-ai.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements-ai.txt -r requirements.txt

# ---- Runtime stage ----
FROM python:3.12-slim
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY ai/ ai/
COPY data/ data/
COPY src/ src/
COPY static/ static/

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
