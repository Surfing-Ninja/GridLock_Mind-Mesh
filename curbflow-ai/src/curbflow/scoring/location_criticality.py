"""Location criticality scoring from junction, corridor, and place text."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from curbflow.scoring.violation_parser import parse_violation_labels


LOCATION_CRITICALITY_WEIGHTS = {
    "named_junction_flag": 0.35,
    "main_road_flag": 0.25,
    "crossing_or_signal_flag": 0.20,
    "bus_stop_school_hospital_flag": 0.15,
    "double_parking_flag": 0.05,
}


def _is_missing(value: Any) -> bool:
    if value is None or pd.isna(value):
        return True
    return not str(value).strip()


def _normalise_text(*values: Any) -> str:
    parts = [str(value) for value in values if not _is_missing(value)]
    text = " ".join(parts).lower()
    text = re.sub(r"[_\-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def named_junction_flag(junction_name: Any) -> int:
    """Return 1 when junction_name is present and not 'No Junction'."""

    if _is_missing(junction_name):
        return 0
    text = _normalise_text(junction_name)
    return int(text not in {"no junction", "nojunction", "none", "unknown", "null"})


def main_road_flag(location_text: Any, labels: list[str]) -> int:
    """Return 1 for main-road signals from parsed labels or text."""

    text = _normalise_text(location_text)
    has_label = "parking_in_main_road" in labels
    has_text = bool(re.search(r"\b(road|main\s+road|ring\s+road|highway)\b", text))
    return int(has_label or has_text)


def crossing_or_signal_flag(location_text: Any, labels: list[str]) -> int:
    """Return 1 for crossing, signal, or zebra signals from parsed labels or text."""

    text = _normalise_text(location_text)
    has_label = bool(
        {"parking_near_road_crossing", "parking_near_traffic_light_zebra"} & set(labels)
    )
    has_text = bool(re.search(r"\b(crossing|signal|zebra)\b", text))
    return int(has_label or has_text)


def bus_stop_school_hospital_flag(location_text: Any, labels: list[str]) -> int:
    """Return 1 for bus stop, school, hospital, or college signals."""

    text = _normalise_text(location_text)
    has_label = "parking_near_bus_stop_school_hospital" in labels
    has_text = bool(re.search(r"\b(bus\s+stop|school|hospital|college)\b", text))
    return int(has_label or has_text)


def double_parking_flag(labels: list[str]) -> int:
    """Return 1 when parsed violation labels include double parking."""

    return int("double_parking" in labels)


def compute_location_criticality(
    *,
    junction_name: Any = None,
    location: Any = None,
    violation_type: Any = None,
    parsed_labels: list[str] | None = None,
) -> float:
    """Compute the weighted location criticality score clamped to [0, 1]."""

    labels = parsed_labels if parsed_labels is not None else parse_violation_labels(violation_type)
    score = (
        LOCATION_CRITICALITY_WEIGHTS["named_junction_flag"] * named_junction_flag(junction_name)
        + LOCATION_CRITICALITY_WEIGHTS["main_road_flag"] * main_road_flag(location, labels)
        + LOCATION_CRITICALITY_WEIGHTS["crossing_or_signal_flag"]
        * crossing_or_signal_flag(location, labels)
        + LOCATION_CRITICALITY_WEIGHTS["bus_stop_school_hospital_flag"]
        * bus_stop_school_hospital_flag(location, labels)
        + LOCATION_CRITICALITY_WEIGHTS["double_parking_flag"] * double_parking_flag(labels)
    )
    return max(0.0, min(1.0, float(score)))


def compute_location_criticality_from_row(row: pd.Series) -> float:
    """Compute location criticality from a pandas row."""

    return compute_location_criticality(
        junction_name=row.get("junction_name"),
        location=row.get("location"),
        violation_type=row.get("violation_type"),
    )
