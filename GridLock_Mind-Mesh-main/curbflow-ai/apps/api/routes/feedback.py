"""Deployment feedback capture routes for future outcome learning."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from apps.api.dependencies import (
    get_repository,
    sanitize_private_fields,
    validate_station,
    validate_window_start,
)
from apps.api.schemas import FeedbackRequest, FeedbackResponse
from curbflow.db.repository import CurbFlowRepository


router = APIRouter(tags=["feedback"])


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    summary="Store enforcement feedback",
    description=(
        "Persist post-deployment feedback for future learning. The current model does not train "
        "on this feedback yet; it is stored as the missing outcome layer for future evaluation."
    ),
)
async def save_feedback(
    http_request: Request,
    repository: CurbFlowRepository = Depends(get_repository),
) -> FeedbackResponse:
    """Persist deployment feedback without exposing raw identifiers."""

    try:
        payload: dict[str, Any] = await http_request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON.") from exc
    try:
        request = FeedbackRequest(**payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    payload = request.model_dump() if hasattr(request, "model_dump") else request.dict()
    payload["window_start"] = validate_window_start(request.window_start, required=True)
    payload["police_station"] = validate_station(request.police_station)
    response = repository.save_feedback(sanitize_private_fields(payload))
    return FeedbackResponse(**response)
