"""Vehicle obstruction footprint scoring from vehicle type fields."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


UNKNOWN_VEHICLE_OBSTRUCTION_WEIGHT = 0.60

VEHICLE_OBSTRUCTION_PATTERNS: tuple[tuple[float, tuple[str, ...]], ...] = (
    (
        1.00,
        (
            r"\bhgv\b",
            r"\blorry\b",
            r"\btanker\b",
            r"\bprivate\s+bus\b",
            r"\bbmtc\b",
            r"\bksrtc\b",
        ),
    ),
    (0.90, (r"\blgv\b", r"\btempo\b", r"\bmini\s+lorry\b")),
    (0.85, (r"\bmaxi[-\s]?cab\b", r"\bvan\b")),
    (0.75, (r"\bcar\b", r"\bjeep\b")),
    (0.65, (r"\bgoods\s+auto\b",)),
    (0.58, (r"\bpassenger\s+auto\b", r"(?<!goods\s)\bauto\b")),
    (0.35, (r"\bscooter\b", r"\bmotor\s*cycle\b", r"\bmotorcycle\b")),
    (0.25, (r"\bmoped\b",)),
)


def _is_missing(value: Any) -> bool:
    if value is None or pd.isna(value):
        return True
    return not str(value).strip()


def select_vehicle_type(vehicle_type: Any, updated_vehicle_type: Any = None) -> str:
    """Use updated vehicle type when present, otherwise fall back to vehicle_type."""

    if not _is_missing(updated_vehicle_type):
        return str(updated_vehicle_type).strip()
    if not _is_missing(vehicle_type):
        return str(vehicle_type).strip()
    return ""


def score_vehicle_type(vehicle_type: Any) -> float:
    """Map a vehicle type string to its obstruction footprint weight."""

    if _is_missing(vehicle_type):
        return UNKNOWN_VEHICLE_OBSTRUCTION_WEIGHT

    text = re.sub(r"[_\-]+", " ", str(vehicle_type).strip().lower())
    text = re.sub(r"\s+", " ", text)
    for weight, patterns in VEHICLE_OBSTRUCTION_PATTERNS:
        if any(re.search(pattern, text) for pattern in patterns):
            return weight
    return UNKNOWN_VEHICLE_OBSTRUCTION_WEIGHT


def score_vehicle_obstruction(vehicle_type: Any, updated_vehicle_type: Any = None) -> float:
    """Score obstruction using updated_vehicle_type when available."""

    return score_vehicle_type(select_vehicle_type(vehicle_type, updated_vehicle_type))


def score_vehicle_obstruction_from_row(row: pd.Series) -> float:
    """Score obstruction from a pandas row with vehicle type fields."""

    return score_vehicle_obstruction(
        row.get("vehicle_type"),
        row.get("updated_vehicle_type"),
    )
