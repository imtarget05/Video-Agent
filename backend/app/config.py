"""Centralized, fail-closed runtime settings for the API service."""
from dataclasses import dataclass
import os
from typing import Any, Dict, List


class SettingsError(RuntimeError):
    """Raised when a deployment cannot safely start."""


@dataclass(frozen=True)
class Settings:
    environment: str
    api_key: str
    cors_origins: List[str]
    cors_allow_credentials: bool

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


def _csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def load_settings() -> Settings:
    """Read environment settings and reject unsafe production configuration."""
    environment = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).lower()
    api_key = os.getenv("API_KEY", "").strip()
    raw_origins = os.getenv("CORS_ORIGINS", "")
    cors_origins = _csv(raw_origins)
    if not cors_origins and not environment == "production":
        cors_origins = ["*"]

    raw_credentials = os.getenv("CORS_ALLOW_CREDENTIALS")
    cors_allow_credentials = raw_credentials.lower() in {"1", "true", "yes"} if raw_credentials else "*" not in cors_origins

    if environment == "production":
        if not api_key:
            raise SettingsError("API_KEY is required in production")
        if not cors_origins:
            raise SettingsError("CORS_ORIGINS is required in production")
        if "*" in cors_origins:
            raise SettingsError("CORS_ORIGINS cannot contain a wildcard in production")

    if "*" in cors_origins:
        if environment == "production" or cors_allow_credentials:
            raise SettingsError("CORS wildcard cannot be combined with credentials")
        cors_allow_credentials = False

    return Settings(
        environment=environment,
        api_key=api_key,
        cors_origins=cors_origins,
        cors_allow_credentials=cors_allow_credentials,
    )


def cors_options(settings: Settings) -> Dict[str, Any]:
    """Return the exact FastAPI CORS options for validated settings."""
    return {
        "allow_origins": settings.cors_origins,
        "allow_credentials": settings.cors_allow_credentials,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }
