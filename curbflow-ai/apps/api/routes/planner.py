"""Station-wise exploit/explore enforcement planner routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from apps.api.dependencies import (
    get_repository,
    sanitize_private_fields,
    validate_station,
    validate_window_start,
)
from apps.api.schemas import PlannerRecommendation, PlannerRecommendationRequest
from curbflow.db.repository import CurbFlowRepository


router = APIRouter(prefix="/planner", tags=["planner"])


@router.post(
    "/recommend",
    response_model=list[PlannerRecommendation],
    summary="Generate resource-constrained enforcement recommendations",
    description=(
        "Return a station-wise enforcement plan for the requested time window, officer budget, "
        "tow-unit budget, and exploit/explore mode. Recommendations include aggregate "
        "explanations and never expose raw vehicle, device, or user identifiers."
    ),
)
async def recommend(
    http_request: Request,
    repository: CurbFlowRepository = Depends(get_repository),
) -> list[PlannerRecommendation]:
    """Return resource-constrained station-wise enforcement recommendations."""

    try:
        payload: dict[str, Any] = await http_request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON.") from exc
    try:
        request = PlannerRecommendationRequest(**payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    window_start = validate_window_start(request.window_start, required=True)
    station = validate_station(request.police_station)
    if request.available_officers == 0:
        return []
    try:
        rows = repository.get_planner_recommendations(
            {
                "window_start": window_start,
                "police_station": station,
                "available_officers": request.available_officers,
                "available_tow_units": request.available_tow_units,
                "mode": request.mode,
                "top_k": request.top_k,
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [PlannerRecommendation(**row) for row in sanitize_private_fields(rows)]
