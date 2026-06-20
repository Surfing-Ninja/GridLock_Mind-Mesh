"""Health and readiness routes for the CurbFlow AI API."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from apps.api.dependencies import get_repository, get_settings
from apps.api.schemas import DebugFilesResponse, DebugFileStatus, HealthResponse
from curbflow.db.repository import CurbFlowRepository


router = APIRouter(tags=["health"])

DEBUG_ARTIFACTS = {
    "duckdb": "data/app/curbflow.duckdb",
    "zones_geojson": "data/processed/zones.geojson",
    "zone_time_features": "data/processed/zone_time_features.parquet",
    "model_training_table": "data/processed/model_training_table.parquet",
    "predictions": "data/processed/predictions.parquet",
    "recommendations": "data/processed/recommendations.parquet",
    "patrol_myopia": "data/processed/patrol_myopia.parquet",
    "junction_basins": "data/processed/junction_basins.parquet",
    "data_quality_report": "artifacts/reports/data_quality_report.md",
    "bias_audit_report": "artifacts/reports/bias_audit_report.md",
    "deep_model": "artifacts/models/be_sthgt_model.pt",
    "ranker_model": "artifacts/models/ranker_lgbm.txt",
    "deep_metrics": "artifacts/metrics/deep_metrics.json",
    "ranker_metrics": "artifacts/metrics/ranker_metrics.json",
    "model_card": "artifacts/metrics/model_card.md",
}


def _database_available(repository: CurbFlowRepository) -> bool:
    """Check whether the DuckDB app database can serve at least one API query."""

    try:
        repository.get_audit_summary()
    except Exception:
        return False
    return True


def _debug_file_status(path: str) -> DebugFileStatus:
    """Return lightweight file metadata for a development artifact."""

    artifact = Path(path)
    return DebugFileStatus(
        path=str(artifact),
        exists=artifact.exists(),
        size_bytes=artifact.stat().st_size if artifact.exists() else None,
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="API health and readiness",
    description=(
        "Return service readiness, database availability, and whether a configured model "
        "artifact is present. This endpoint does not expose any dataset records."
    ),
)
def health(repository: CurbFlowRepository = Depends(get_repository)) -> HealthResponse:
    """Return API and database readiness."""

    settings = get_settings()
    return HealthResponse(
        status="ok",
        app_version=settings.app_version,
        model_loaded=settings.model_loaded,
        ranker_model_available=Path("artifacts/models/ranker_lgbm.txt").exists(),
        deep_model_available=Path("artifacts/models/be_sthgt_model.pt").exists(),
        database_available=_database_available(repository),
    )


@router.get(
    "/debug/files",
    response_model=DebugFilesResponse,
    summary="Development artifact availability",
    description=(
        "Development-only diagnostic endpoint that reports whether expected pipeline "
        "artifacts exist on disk. It is unavailable outside development/local mode."
    ),
)
def debug_files() -> DebugFilesResponse:
    """Return development-only artifact availability."""

    settings = get_settings()
    if not settings.is_development:
        raise HTTPException(
            status_code=404,
            detail="debug files endpoint is only available when CURBFLOW_ENVIRONMENT=development.",
        )
    return DebugFilesResponse(
        environment=settings.environment,
        files={name: _debug_file_status(path) for name, path in DEBUG_ARTIFACTS.items()},
    )
