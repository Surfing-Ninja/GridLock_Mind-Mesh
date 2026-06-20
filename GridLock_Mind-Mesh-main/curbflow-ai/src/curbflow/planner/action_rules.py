"""Recommended enforcement action rules for patrol, towing, audits, and evidence review."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


ACTIONS = (
    "beat_patrol",
    "towing_support",
    "mobile_camera_patrol",
    "repeat_offender_check",
    "temporary_cones",
    "evening_audit_patrol",
    "patrol_expansion",
    "evidence_quality_audit",
)

ACTION_COSTS = {
    "beat_patrol": {"officers": 1, "tow_units": 0},
    "towing_support": {"officers": 2, "tow_units": 1},
    "mobile_camera_patrol": {"officers": 1, "tow_units": 0},
    "repeat_offender_check": {"officers": 1, "tow_units": 0},
    "temporary_cones": {"officers": 2, "tow_units": 0},
    "evening_audit_patrol": {"officers": 2, "tow_units": 0},
    "patrol_expansion": {"officers": 2, "tow_units": 0},
    "evidence_quality_audit": {"officers": 1, "tow_units": 0},
}

ACTION_RELIEF_MULTIPLIERS = {
    "beat_patrol": 1.00,
    "towing_support": 1.18,
    "mobile_camera_patrol": 0.88,
    "repeat_offender_check": 0.82,
    "temporary_cones": 0.78,
    "evening_audit_patrol": 1.08,
    "patrol_expansion": 0.92,
    "evidence_quality_audit": 0.66,
}

BLINDSPOT_ACTIONS = {"evening_audit_patrol", "patrol_expansion", "evidence_quality_audit"}


@dataclass(frozen=True)
class ActionCandidate:
    """One feasible zone-action candidate before resource optimization."""

    zone_id: str
    window_start: pd.Timestamp
    police_station: str
    action: str
    officers_required: int
    tow_units_required: int
    action_category: str
    rule_reasons: tuple[str, ...]
    action_multiplier: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a DataFrame-friendly dictionary."""

        return {
            "zone_id": self.zone_id,
            "window_start": self.window_start,
            "police_station": self.police_station,
            "action": self.action,
            "officers_required": self.officers_required,
            "tow_units_required": self.tow_units_required,
            "action_category": self.action_category,
            "rule_reasons": list(self.rule_reasons),
            "action_multiplier": self.action_multiplier,
        }


def numeric_value(row: pd.Series, *columns: str, default: float = 0.0) -> float:
    """Return the first numeric value from a row."""

    for column in columns:
        if column in row.index and not pd.isna(row[column]):
            try:
                return float(row[column])
            except (TypeError, ValueError):
                continue
    return default


def bool_value(row: pd.Series, *columns: str) -> bool:
    """Return the first boolean-like value from a row."""

    for column in columns:
        if column not in row.index or pd.isna(row[column]):
            continue
        value = row[column]
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y"}
        return bool(value)
    return False


def is_evening_window(row: pd.Series) -> bool:
    """Return true for the 15:30-20:30 IST audit window."""

    timestamp = pd.to_datetime(row.get("window_start"), errors="coerce")
    if pd.isna(timestamp):
        return False
    minute = int(timestamp.hour) * 60 + int(timestamp.minute)
    return 15 * 60 + 30 <= minute < 20 * 60 + 30


def _cost(action: str) -> dict[str, int]:
    if action not in ACTION_COSTS:
        raise ValueError(f"Unknown action: {action}")
    return ACTION_COSTS[action]


def _candidate(
    row: pd.Series,
    action: str,
    *,
    reasons: tuple[str, ...],
    category: str | None = None,
) -> ActionCandidate:
    costs = _cost(action)
    return ActionCandidate(
        zone_id=str(row.get("zone_id", "unknown")),
        window_start=pd.Timestamp(row.get("window_start")),
        police_station=str(row.get("police_station", "unknown")),
        action=action,
        officers_required=int(costs["officers"]),
        tow_units_required=int(costs["tow_units"]),
        action_category=category or ("blindspot" if action in BLINDSPOT_ACTIONS else "known_hotspot"),
        rule_reasons=reasons,
        action_multiplier=ACTION_RELIEF_MULTIPLIERS[action],
    )


def towing_support_rule(row: pd.Series) -> tuple[bool, tuple[str, ...]]:
    """Trigger towing support for large, double-parked, or main-road obstruction risk."""

    reasons: list[str] = []
    if numeric_value(row, "large_vehicle_share") >= 0.30:
        reasons.append("large vehicle share is high")
    if numeric_value(row, "double_parking_share") >= 0.20:
        reasons.append("double parking share is high")
    if numeric_value(row, "main_road_parking_share") >= 0.30:
        reasons.append("main-road parking share is high")
    if numeric_value(row, "q90_pfdi", "predicted_pfdi") >= 75 and numeric_value(row, "predicted_count") >= 3:
        reasons.append("high severe-disruption forecast")
    return bool(reasons), tuple(reasons)


def evening_audit_rule(row: pd.Series) -> tuple[bool, tuple[str, ...]]:
    """Trigger evening audit patrol for high-potential low-visibility evening windows."""

    coverage_gap = numeric_value(row, "coverage_gap")
    static_potential = numeric_value(row, "static_potential")
    if coverage_gap >= 0.60 and static_potential >= 0.60 and is_evening_window(row):
        return True, ("evening window has high static potential and low visibility",)
    return False, ()


def patrol_expansion_rule(row: pd.Series) -> tuple[bool, tuple[str, ...]]:
    """Trigger patrol expansion for zones near existing patrol routes but under-covered."""

    if bool_value(row, "near_patrol_but_uncovered_flag", "near_patrol_but_uncovered"):
        return True, ("near patrol route but under-covered",)
    return False, ()


def repeat_offender_rule(row: pd.Series) -> tuple[bool, tuple[str, ...]]:
    """Trigger repeat offender checks for repeat pressure or persistence."""

    if max(numeric_value(row, "repeat_pressure_mean", "repeat_pressure"), numeric_value(row, "persistence_score")) >= 0.35:
        return True, ("repeat pressure or same-zone persistence is high",)
    return False, ()


def temporary_cones_rule(row: pd.Series) -> tuple[bool, tuple[str, ...]]:
    """Trigger temporary cones for recurring critical-corridor obstruction."""

    recurring = max(
        numeric_value(row, "recurrence", "repeat_vehicle_share"),
        numeric_value(row, "rolling_7d_pfdi", "corridor_recent_pfdi") / 100.0,
    )
    critical_obstruction = (
        numeric_value(row, "main_road_parking_share") >= 0.25
        or numeric_value(row, "location_criticality_mean", "location_criticality") >= 0.65
        or numeric_value(row, "junction_basin_pfdi") >= 50
        or bool_value(row, "place_type_transit_node", "place_type_institutional")
    )
    if recurring >= 0.25 and critical_obstruction:
        return True, ("recurring critical-location obstruction",)
    return False, ()


def evidence_quality_rule(row: pd.Series) -> tuple[bool, tuple[str, ...]]:
    """Trigger evidence-quality audit for low trust or low SCITA success."""

    reasons: list[str] = []
    if numeric_value(row, "device_reject_rate", "user_reject_rate") >= 0.25:
        reasons.append("device or user rejection rate is high")
    if "scita_success_rate" in row.index and numeric_value(row, "scita_success_rate", default=1.0) <= 0.40:
        reasons.append("SCITA success rate is low")
    if "evidence_quality_score_mean" in row.index and numeric_value(row, "evidence_quality_score_mean", default=1.0) <= 0.45:
        reasons.append("evidence quality score is low")
    return bool(reasons), tuple(reasons)


def action_candidates_for_row(row: pd.Series) -> list[ActionCandidate]:
    """Generate action candidates for one zone-window row."""

    candidates: list[ActionCandidate] = []
    observed = numeric_value(row, "observed_risk_score", "exploit_score", "predicted_pfdi")
    hotspot_probability = numeric_value(row, "hotspot_probability")
    coverage_gap = numeric_value(row, "coverage_gap")

    if observed >= 35 or hotspot_probability >= 0.35:
        candidates.append(
            _candidate(
                row,
                "beat_patrol",
                reasons=("observed hotspot priority is actionable",),
                category="known_hotspot",
            )
        )
    if coverage_gap >= 0.45 or hotspot_probability >= 0.50:
        candidates.append(
            _candidate(
                row,
                "mobile_camera_patrol",
                reasons=("mobile observation can improve visibility",),
                category="blindspot" if coverage_gap >= 0.60 else "known_hotspot",
            )
        )

    for action, rule in (
        ("towing_support", towing_support_rule),
        ("evening_audit_patrol", evening_audit_rule),
        ("patrol_expansion", patrol_expansion_rule),
        ("repeat_offender_check", repeat_offender_rule),
        ("temporary_cones", temporary_cones_rule),
        ("evidence_quality_audit", evidence_quality_rule),
    ):
        triggered, reasons = rule(row)
        if triggered:
            candidates.append(_candidate(row, action, reasons=reasons))

    if not candidates:
        candidates.append(
            _candidate(
                row,
                "beat_patrol",
                reasons=("baseline patrol coverage",),
                category="known_hotspot",
            )
        )
    return candidates


def build_action_candidates(frame: pd.DataFrame) -> pd.DataFrame:
    """Build all candidate zone-action pairs for planner optimization."""

    records: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        records.extend(candidate.to_dict() for candidate in action_candidates_for_row(row))
    return pd.DataFrame.from_records(records)
