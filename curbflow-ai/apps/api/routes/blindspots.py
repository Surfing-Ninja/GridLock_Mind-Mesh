"""Blindspot and enforcement visibility gap routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from apps.api.dependencies import (
    get_repository,
    sanitize_private_fields,
    validate_station,
    validate_window_start,
)
from apps.api.schemas import RiskRow
from curbflow.db.repository import CurbFlowRepository


router = APIRouter(tags=["blindspots"])


@router.get(
    "/blindspots",
    response_model=list[RiskRow],
    summary="List blindspot audit priorities",
    description=(
        "Return zones with high static potential and low enforcement visibility. These are "
        "audit priorities, not claims of validated unobserved violations."
    ),
)
def blindspots(
    window_start: str | None = Query(default=None),
    station: str | None = Depends(validate_station),
    top_k: int = Query(default=25, ge=1, le=500),
    repository: CurbFlowRepository = Depends(get_repository),
) -> list[RiskRow]:
    """Return high-potential low-visibility blindspots."""

    validated_window = validate_window_start(window_start)
    rows = repository.get_blindspots(
        window_start=validated_window,
        station=station,
        top_k=top_k,
    )
    return [RiskRow(**row) for row in sanitize_private_fields(rows)]
