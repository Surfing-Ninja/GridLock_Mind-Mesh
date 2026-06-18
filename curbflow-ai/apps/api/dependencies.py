"""FastAPI dependency providers for settings, repositories, and services."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import sys
from typing import Any

import pandas as pd
from fastapi import HTTPException, Query
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SRC_PATH = Path(__file__).resolve().parents[2] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from curbflow.db.duckdb_init import APP_DB_PATH
from curbflow.db.repository import CurbFlowRepository


PRIVATE_KEYS = {"vehicle_number", "device_id", "created_by_id"}
DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]
DEFAULT_MODEL_ARTIFACT_PATHS = [
    Path("artifacts/models/be_sthgt_model.pt"),
    Path("artifacts/models/ranker_lgbm.txt"),
]


class APISettings(BaseSettings):
    """Runtime settings for the CurbFlow FastAPI app."""

    app_name: str = "CurbFlow AI API"
    app_version: str = "0.1.0"
    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("CURBFLOW_ENVIRONMENT", "CURBFLOW_ENV"),
    )
    db_path: Path = Field(
        default=APP_DB_PATH,
        validation_alias=AliasChoices("CURBFLOW_DB_PATH", "CURBFLOW_DUCKDB_PATH"),
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: list(DEFAULT_CORS_ORIGINS),
        validation_alias=AliasChoices("CURBFLOW_CORS_ORIGINS", "CURBFLOW_ALLOWED_ORIGINS"),
    )
    geojson_cache_ttl_seconds: int = 120
    model_artifact_paths: list[Path] = Field(
        default_factory=lambda: list(DEFAULT_MODEL_ARTIFACT_PATHS),
    )

    model_config = SettingsConfigDict(env_prefix="CURBFLOW_", env_file=".env", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> Any:
        """Accept JSON arrays or comma-separated strings from .env."""

        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return value
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return value

    @field_validator("model_artifact_paths", mode="before")
    @classmethod
    def parse_model_artifact_paths(cls, value: Any) -> Any:
        """Accept JSON arrays or comma-separated model artifact paths."""

        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return value
            return [Path(item.strip()) for item in stripped.split(",") if item.strip()]
        return value

    @property
    def is_development(self) -> bool:
        """Return true when development-only diagnostics should be available."""

        return self.environment.strip().lower() in {"development", "dev", "local"}

    @property
    def model_loaded(self) -> bool:
        """Return true when at least one configured model artifact is available."""

        return any(Path(path).exists() for path in self.model_artifact_paths)


@lru_cache(maxsize=1)
def get_settings() -> APISettings:
    """Return cached API settings."""

    return APISettings()


def get_repository(settings: APISettings = None) -> CurbFlowRepository:
    """Return the DuckDB-backed repository dependency."""

    settings = settings or get_settings()
    return CurbFlowRepository(settings.db_path)


def validate_window_start(window_start: str | None, *, required: bool = False) -> str | None:
    """Validate a query/body window_start value and return an ISO timestamp string."""

    if window_start is None or str(window_start).strip() == "":
        if required:
            raise HTTPException(
                status_code=400,
                detail="window_start is required. Provide an ISO timestamp such as 2024-04-01T09:00:00.",
            )
        return None
    timestamp = pd.to_datetime(window_start, errors="coerce")
    if pd.isna(timestamp):
        raise HTTPException(
            status_code=400,
            detail=f"window_start must be a valid timestamp; received {window_start!r}.",
        )
    normalized = pd.Timestamp(timestamp)
    if normalized.tzinfo is None:
        normalized = normalized.tz_localize("Asia/Kolkata")
    return normalized.isoformat()


def validate_station(station: str | None = Query(default=None)) -> str | None:
    """Validate optional station filters."""

    if station is None:
        return None
    normalized = station.strip()
    if not normalized or normalized.lower() in {"null", "none", "undefined"}:
        raise HTTPException(
            status_code=400,
            detail="station must be a valid non-empty police station name.",
        )
    return normalized


def sanitize_private_fields(payload: Any) -> Any:
    """Drop private/raw identifier fields from nested API payloads."""

    if isinstance(payload, list):
        return [sanitize_private_fields(item) for item in payload]
    if isinstance(payload, dict):
        sanitized = {}
        for key, value in payload.items():
            lowered = str(key).lower()
            if lowered in PRIVATE_KEYS:
                continue
            sanitized[key] = sanitize_private_fields(value)
        return sanitized
    return payload
