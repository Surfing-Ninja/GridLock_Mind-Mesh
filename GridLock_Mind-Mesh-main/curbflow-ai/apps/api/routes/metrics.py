"""Model, ranking, and system metric routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.api.dependencies import get_repository, sanitize_private_fields
from apps.api.schemas import ModelMetricsResponse
from curbflow.db.repository import CurbFlowRepository


router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get(
    "/model",
    response_model=ModelMetricsResponse,
    summary="Get model metrics",
    description=(
        "Return baseline, ranker, deep-model, and ensemble metrics when available. "
        "Metric payloads are privacy-sanitized before response."
    ),
)
def model_metrics(repository: CurbFlowRepository = Depends(get_repository)) -> ModelMetricsResponse:
    """Return model training and ranking metrics."""

    return ModelMetricsResponse(metrics=sanitize_private_fields(repository.get_model_metrics()))
