"""Data quality, hourly evidence, and enforcement-bias audit routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.api.dependencies import get_repository, sanitize_private_fields
from apps.api.schemas import AuditSummaryResponse, DateRange, HourlyAuditRow
from curbflow.db.repository import CurbFlowRepository


router = APIRouter(prefix="/audit", tags=["audit"])


def _active_zones(summary: dict) -> int | None:
    top_zone = summary.get("top_zone_concentration", {}) or {}
    for key in ("active_zones", "active_zone_count", "total_active_zones"):
        if key in top_zone and top_zone[key] is not None:
            return int(top_zone[key])
    return None


@router.get(
    "/summary",
    response_model=AuditSummaryResponse,
    summary="Get audit summary",
    description=(
        "Return the core data quality and enforcement-visibility audit summary, including "
        "date range, null outcome columns, morning/evening evidence imbalance, active zones, "
        "and the key interpretation warning."
    ),
)
def audit_summary(repository: CurbFlowRepository = Depends(get_repository)) -> AuditSummaryResponse:
    """Return the bias-aware data audit summary."""

    summary = sanitize_private_fields(repository.get_audit_summary())
    warnings = summary.get("interpretation_warnings") or [
        "This dataset is an enforcement visibility dataset, not a complete record of all illegal parking."
    ]
    return AuditSummaryResponse(
        row_count=int(summary.get("total_rows") or summary.get("row_count") or 0),
        date_range=DateRange(**(summary.get("actual_date_range") or {})),
        null_outcome_columns=summary.get("fully_null_columns") or {},
        morning_count=int(summary.get("morning_count_0730_1530") or 0),
        evening_count=int(summary.get("evening_count_1530_2030") or 0),
        evening_gap_ratio=summary.get("evening_gap_ratio_morning_over_evening"),
        active_zones=_active_zones(summary),
        top_zone_concentration=summary.get("top_zone_concentration") or {},
        key_warning_message=str(warnings[0]),
        raw_summary=summary,
    )


@router.get(
    "/hourly",
    response_model=list[HourlyAuditRow],
    summary="Get hourly evidence distribution",
    description="Return hour-of-day record counts used to show morning-heavy enforcement visibility.",
)
def hourly_audit(repository: CurbFlowRepository = Depends(get_repository)) -> list[HourlyAuditRow]:
    """Return hour-of-day evidence distribution."""

    rows = sanitize_private_fields(repository.get_hourly_audit())
    return [HourlyAuditRow(**row) for row in rows]
