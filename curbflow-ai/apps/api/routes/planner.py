"""Station-wise exploit/explore enforcement planner routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError

from apps.api.dependencies import (
    get_repository,
    sanitize_private_fields,
    validate_station,
    validate_window_start,
)
from apps.api.schemas import MorningBriefRow, PlannerRecommendation, PlannerRecommendationRequest
from curbflow.db.repository import CurbFlowRepository


router = APIRouter(prefix="/planner", tags=["planner"])

DAY_OF_WEEK = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}


def _parse_day_of_week(value: str | int) -> int:
    """Parse weekday names or integer day indexes where Monday is 0."""

    if isinstance(value, int):
        parsed = value
    else:
        text = str(value).strip().lower()
        if text.isdigit():
            parsed = int(text)
        elif text in DAY_OF_WEEK:
            parsed = DAY_OF_WEEK[text]
        else:
            raise HTTPException(
                status_code=400,
                detail="dow must be a weekday name such as Tuesday or an integer 0-6 where Monday is 0.",
            )
    if parsed < 0 or parsed > 6:
        raise HTTPException(
            status_code=400,
            detail="dow must be in the range 0-6 where Monday is 0.",
        )
    return parsed


@router.get(
    "/morning-brief",
    response_model=list[MorningBriefRow],
    summary="Get station morning deployment brief",
    description=(
        "Return the top historical high-impact zones for a police station, weekday, and "
        "3-hour slot. The brief uses aggregate PFDI, violation frequency, repeat pressure, "
        "vehicle mix, and action rules without exposing raw vehicle or officer identifiers."
    ),
)
def morning_brief(
    station: str = Depends(validate_station),
    dow: str = Query(default="Tuesday", description="Weekday name or 0-6 integer where Monday is 0."),
    slot: int = Query(default=3, ge=0, le=7, description="3-hour slot index, for example 3 for 09:00-12:00."),
    top_k: int = Query(default=5, ge=1, le=25),
    repository: CurbFlowRepository = Depends(get_repository),
) -> list[MorningBriefRow]:
    """Return a deployment-ready station/day/slot morning brief."""

    if station is None:
        raise HTTPException(status_code=400, detail="station is required for the morning brief.")
    rows = repository.get_morning_deployment_brief(
        station=station,
        day_of_week=_parse_day_of_week(dow),
        slot=slot,
        top_k=top_k,
    )
    return [MorningBriefRow(**row) for row in sanitize_private_fields(rows)]


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
