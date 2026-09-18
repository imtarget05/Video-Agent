# Video-Agent — inference/API service image.
# Build context is the REPO ROOT (needs backend/ + remotion/ + dashboard/):
#   docker build -t video-agent:latest .
# Run:
#   docker run --env-file .env -p 8000:8000 video-agent:latest
# Secrets are NOT baked in — pass via --env-file or -e flags.
# Health:  curl http://localhost:8000/health/live
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    STORAGE_BACKEND=local \
    MOCK_VIDEO=true \
    MOCK_TTS=true

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 appuser

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY remotion/ ./remotion/
COPY dashboard/ ./dashboard/

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/health/live" || exit 1

CMD ["sh", "-c", "uvicorn backend.app.api.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
