"""Zone GeoJSON and zone detail routes."""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.dependencies import (
    APISettings,
    get_repository,
    get_settings,
    sanitize_private_fields,
    validate_station,
    validate_window_start,
)
from apps.api.schemas import PlaceSuggestion, PlannerMode, PredictionWindowRow, ZoneDetailsResponse
from curbflow.db.repository import CurbFlowRepository


router = APIRouter(prefix="/zones", tags=["zones"])
_GEOJSON_CACHE: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}
BENGALURU_LAT_LON = "12.9716,77.5946"


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
    "/windows",
    response_model=list[PredictionWindowRow],
    summary="List replayable prediction windows",
    description=(
        "Return recent 3-hour prediction windows for the map timeline. Each row is an aggregate "
        "window summary and contains no vehicle, device, or user identifiers."
    ),
)
def prediction_windows(
    station: str | None = Depends(validate_station),
    limit: int = Query(default=96, ge=1, le=500),
    repository: CurbFlowRepository = Depends(get_repository),
) -> list[PredictionWindowRow]:
    """Return recent prediction windows for map replay controls."""

    rows = repository.get_prediction_windows(station=station, limit=limit)
    return [PredictionWindowRow(**row) for row in sanitize_private_fields(rows)]


def _float_from(payload: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    """Return the first numeric coordinate from a Mappls payload."""

    for key in keys:
        value = payload.get(key)
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed == parsed:
            return parsed
    return None


def _mappls_suggestion(payload: dict[str, Any]) -> PlaceSuggestion | None:
    """Normalize one Mappls autosuggest location."""

    place_name = str(payload.get("placeName") or payload.get("name") or "").strip()
    place_address = str(payload.get("placeAddress") or payload.get("address") or "").strip() or None
    if not place_name and not place_address:
        return None
    latitude = _float_from(payload, ("latitude", "lat", "entryLatitude", "placeLatitude"))
    longitude = _float_from(payload, ("longitude", "lng", "lon", "entryLongitude", "placeLongitude"))
    return PlaceSuggestion(
        place_name=place_name or place_address or "Mappls place",
        place_address=place_address,
        eloc=(str(payload.get("eLoc") or payload.get("eloc") or payload.get("ELoc") or "").strip() or None),
        latitude=latitude,
        longitude=longitude,
    )


@router.get(
    "/place-search",
    response_model=list[PlaceSuggestion],
    summary="Search places with Mappls Autosuggest",
    description=(
        "Proxy Mappls/MapMyIndia Autosuggest for the command-center place search. "
        "The access token stays server-side, and the response is normalized to names and optional coordinates."
    ),
)
def mappls_place_search(
    q: str = Query(min_length=3, max_length=80, description="Place query, for example 'banaswadi' or 'ashok nagar'."),
    limit: int = Query(default=6, ge=1, le=10),
    settings: APISettings = Depends(get_settings),
) -> list[PlaceSuggestion]:
    """Return Mappls Autosuggest results biased around Bengaluru."""

    token = (settings.mappls_access_token or "").strip()
    if not token:
        raise HTTPException(
            status_code=503,
            detail="Mappls Autosuggest is not configured. Set CURBFLOW_MAPPLS_ACCESS_TOKEN or MAPPLS_ACCESS_TOKEN.",
        )
    params = {
        "query": q.strip(),
        "access_token": token,
        "location": BENGALURU_LAT_LON,
        "region": "ind",
    }
    url = f"{settings.mappls_autosuggest_url}?{urlencode(params)}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "CurbFlowAI/0.1"})
    try:
        with urlopen(request, timeout=settings.mappls_request_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Mappls Autosuggest request failed with status {exc.code}.") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail="Mappls Autosuggest request failed. Try again later.") from exc

    raw_results = payload.get("suggestedLocations") or payload.get("results") or []
    if not isinstance(raw_results, list):
        return []
    suggestions: list[PlaceSuggestion] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        suggestion = _mappls_suggestion(item)
        if suggestion:
            suggestions.append(suggestion)
        if len(suggestions) >= limit:
            break
    return suggestions


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
