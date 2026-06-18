"""Patrol digital twin routes for aggregate operational intelligence."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from apps.api.dependencies import get_repository, sanitize_private_fields, validate_station
from apps.api.schemas import PatrolRouteRow, PatrolStationSummary
from curbflow.db.repository import CurbFlowRepository


router = APIRouter(prefix="/patrol", tags=["patrol"])


@router.get(
    "/summary",
    response_model=list[PatrolStationSummary],
    summary="Get patrol digital twin station summary",
    description=(
        "Return station-level patrol myopia, coverage entropy, evening coverage, and nearby "
        "uncovered-zone summaries. Raw device and user identifiers are never returned."
    ),
)
def patrol_summary(
    station: str | None = Depends(validate_station),
    top_k: int = Query(default=25, ge=1, le=500),
    repository: CurbFlowRepository = Depends(get_repository),
) -> list[PatrolStationSummary]:
    """Return station-level aggregate patrol myopia and route coverage metrics."""

    rows = repository.get_patrol_summary(station=station, top_k=top_k)
    return [PatrolStationSummary(**row) for row in sanitize_private_fields(rows)]


@router.get(
    "/routes",
    response_model=list[PatrolRouteRow],
    summary="Get aggregate patrol route patterns",
    description=(
        "Return aggregate zone-to-zone transition patterns reconstructed from patrol behavior. "
        "Only aggregate route statistics are exposed."
    ),
)
def patrol_routes(
    station: str | None = Depends(validate_station),
    top_k: int = Query(default=50, ge=1, le=500),
    repository: CurbFlowRepository = Depends(get_repository),
) -> list[PatrolRouteRow]:
    """Return aggregate patrol transition route patterns without raw actor identifiers."""

    rows = repository.get_patrol_routes(station=station, top_k=top_k)
    return [PatrolRouteRow(**row) for row in sanitize_private_fields(rows)]
