"""Observed illegal-parking hotspot routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from apps.api.dependencies import (
    get_repository,
    sanitize_private_fields,
    validate_station,
    validate_window_start,
)
from apps.api.schemas import PlannerMode, RiskRow
from curbflow.db.repository import CurbFlowRepository


router = APIRouter(tags=["hotspots"])


@router.get(
    "/hotspots",
    response_model=list[RiskRow],
    summary="List observed hotspot priorities",
    description=(
        "Return observed illegal-parking hotspots ranked by the selected deployment mode. "
        "Only aggregate zone-level features are returned."
    ),
)
def hotspots(
    window_start: str | None = Query(default=None),
    station: str | None = Depends(validate_station),
    top_k: int = Query(default=25, ge=1, le=500),
    mode: PlannerMode = "balanced",
    repository: CurbFlowRepository = Depends(get_repository),
) -> list[RiskRow]:
    """Return observed illegal-parking hotspots."""

    validated_window = validate_window_start(window_start)
    rows = repository.get_hotspots(
        window_start=validated_window,
        station=station,
        top_k=top_k,
        mode=mode,
    )
    return [RiskRow(**row) for row in sanitize_private_fields(rows)]
