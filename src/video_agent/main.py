"""
Video-Agent main application.

Provides the FastAPI application with health check endpoint.
"""

from fastapi import FastAPI

app = FastAPI(title="Video-Agent", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok"}