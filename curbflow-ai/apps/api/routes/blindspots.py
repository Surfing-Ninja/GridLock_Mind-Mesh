"""Blindspot and enforcement visibility gap routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from apps.api.dependencies import (
    get_repository,
    sanitize_private_fields,
    validate_station,
    validate_window_start,
)
from apps.api.schemas import BlindspotHourlyVolumeRow, RiskRow, StationShiftCutoffRow
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


@router.get(
    "/blindspots/hourly-volume",
    response_model=list[BlindspotHourlyVolumeRow],
    summary="Get 24-hour enforcement volume curve",
    description=(
        "Return aggregate hourly record volume used to show the evening evidence gap. "
        "This is enforcement visibility volume, not a complete measure of illegal parking."
    ),
)
def hourly_volume(
    repository: CurbFlowRepository = Depends(get_repository),
) -> list[BlindspotHourlyVolumeRow]:
    """Return hour-of-day enforcement volume for blindspot diagnosis."""

    rows = repository.get_blindspot_hourly_volume()
    return [BlindspotHourlyVolumeRow(**row) for row in sanitize_private_fields(rows)]


@router.get(
    "/blindspots/station-shift-cutoff",
    response_model=list[StationShiftCutoffRow],
    summary="Get station shift cutoff proxy",
    description=(
        "Return each station's median last active enforcement hour per officer-day. "
        "This helps explain why evening zero-violation windows are treated as low-evidence audit windows."
    ),
)
def station_shift_cutoff(
    top_k: int = Query(default=20, ge=1, le=100),
    repository: CurbFlowRepository = Depends(get_repository),
) -> list[StationShiftCutoffRow]:
    """Return aggregate station shift cutoff diagnostics."""

    rows = repository.get_station_shift_cutoff(top_k=top_k)
    return [StationShiftCutoffRow(**row) for row in sanitize_private_fields(rows)]
