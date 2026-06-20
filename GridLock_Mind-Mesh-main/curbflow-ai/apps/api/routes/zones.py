"""Zone GeoJSON and zone detail routes."""

from __future__ import annotations

import copy
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query

from apps.api.dependencies import (
    APISettings,
    get_repository,
    get_settings,
    sanitize_private_fields,
    validate_station,
    validate_window_start,
)
from apps.api.schemas import PlannerMode, ZoneDetailsResponse
from curbflow.db.repository import CurbFlowRepository


router = APIRouter(prefix="/zones", tags=["zones"])
_GEOJSON_CACHE: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}


def _repository_cache_marker(repository: CurbFlowRepository) -> tuple[Any, ...]:
    """Return a cache marker that changes when the backing database file changes."""

    db_path = getattr(repository, "db_path", None)
    if db_path is None:
        return ("repository", id(repository))
    path = Path(db_path)
    try:
        return ("duckdb", str(path.resolve()), path.stat().st_mtime_ns)
    except FileNotFoundError:
        return ("duckdb", str(path.resolve()), None)


def _get_cached_geojson(
    *,
    repository: CurbFlowRepository,
    settings: APISettings,
    layer: str,
    window_start: str | None,
    station: str | None,
    mode: PlannerMode,
) -> dict[str, Any]:
    """Return cached GeoJSON for repeated dashboard map requests."""

    ttl = max(0, int(settings.geojson_cache_ttl_seconds))
    if ttl == 0:
        return repository.get_zones_geojson(
            layer=layer,
            window_start=window_start,
            station=station,
            mode=mode,
        )
    key = (_repository_cache_marker(repository), layer, window_start, station, mode)
    now = time.monotonic()
    cached = _GEOJSON_CACHE.get(key)
    if cached and now - cached[0] <= ttl:
        return copy.deepcopy(cached[1])
    geojson = repository.get_zones_geojson(
        layer=layer,
        window_start=window_start,
        station=station,
        mode=mode,
    )
    _GEOJSON_CACHE[key] = (now, copy.deepcopy(geojson))
    return geojson


@router.get(
    "/geojson",
    response_model=dict[str, Any],
    summary="Get zone GeoJSON",
    description=(
        "Return zone polygons enriched with aggregate prediction and patrol properties. "
        "Responses are cached briefly because map GeoJSON can be expensive to build."
    ),
)
def zones_geojson(
    layer: str = Query(default="zones"),
    window_start: str | None = Query(default=None),
    station: str | None = Depends(validate_station),
    mode: PlannerMode = "balanced",
    repository: CurbFlowRepository = Depends(get_repository),
    settings: APISettings = Depends(get_settings),
) -> dict[str, Any]:
    """Return zones as GeoJSON, enriched with prediction properties when available."""

    validated_window = validate_window_start(window_start)
    geojson = _get_cached_geojson(
        repository=repository,
        settings=settings,
        layer=layer,
        window_start=validated_window,
        station=station,
        mode=mode,
    )
    return sanitize_private_fields(geojson)


@router.get(
    "/{zone_id}",
    response_model=ZoneDetailsResponse,
    summary="Get zone details",
    description=(
        "Return one zone's aggregate prediction and engineered feature details for an optional "
        "window. Raw vehicle, device, and user identifiers are removed from the response."
    ),
)
def zone_details(
    zone_id: str,
    window_start: str | None = Query(default=None),
    repository: CurbFlowRepository = Depends(get_repository),
) -> ZoneDetailsResponse:
    """Return one zone's prediction and feature details."""

    validated_window = validate_window_start(window_start)
    details = sanitize_private_fields(repository.get_zone_details(zone_id, validated_window))
    if not details:
        return ZoneDetailsResponse(zone_id=zone_id, window_start=validated_window)
    return ZoneDetailsResponse(**details)
