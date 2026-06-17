"""Static zone, station, corridor, junction, and place-type features."""

from __future__ import annotations

from typing import Any

import pandas as pd

from curbflow.data.clean import normalize_text_value
from curbflow.features.novel_features import (
    PLACE_TYPE_FLAGS,
    add_evidence_quality_features,
    add_hidden_junction_basin_features,
    add_place_type_and_road_corridor_features,
    add_repeat_vehicle_features,
)
from curbflow.scoring.vehicle_obstruction import score_vehicle_obstruction
from curbflow.scoring.violation_parser import parse_violation_labels


TWO_WHEELER_TERMS = ("scooter", "motorcycle", "motor cycle", "moped")


def mode_or_unknown(series: pd.Series) -> str:
    """Return the dominant normalized station label."""

    normalized = series.map(lambda value: normalize_text_value(value, unknown_for_null=True))
    modes = normalized.value_counts(dropna=False)
    return str(modes.index[0]) if not modes.empty else "unknown"


def _labels(value: Any) -> list[str]:
    """Return parsed violation labels from list or raw text."""

    if isinstance(value, list):
        return value
    return parse_violation_labels(value)


def _label_contains(value: Any, label: str) -> bool:
    return label in _labels(value)


def _text_contains(value: Any, terms: tuple[str, ...]) -> bool:
    if pd.isna(value):
        return False
    text = str(value).lower()
    return any(term in text for term in terms)


def ensure_row_feature_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Ensure row-level features needed for zone-time aggregation exist."""

    result = frame.copy()
    if "parsed_violation_labels" not in result.columns:
        result["parsed_violation_labels"] = result.get(
            "violation_type",
            pd.Series([""] * len(result), index=result.index),
        ).map(parse_violation_labels)
    if "vehicle_obstruction" not in result.columns:
        result["vehicle_obstruction"] = result.apply(
            lambda row: score_vehicle_obstruction(
                row.get("vehicle_type"),
                row.get("updated_vehicle_type"),
            ),
            axis=1,
        )
    if "row_obstruction_score" not in result.columns:
        result["row_obstruction_score"] = result.get(
            "observed_pfdi",
            pd.Series([0.0] * len(result), index=result.index),
        )
    if "evidence_quality_score" not in result.columns:
        result = add_evidence_quality_features(result)
    if "hidden_junction_id" not in result.columns and {"junction_name", "latitude", "longitude"}.issubset(
        result.columns
    ):
        result = add_hidden_junction_basin_features(result)
    if "anonymized_vehicle_id" not in result.columns and {"vehicle_number", "created_datetime_ist"}.issubset(
        result.columns
    ):
        result = add_repeat_vehicle_features(result)
    if "road_corridor_id" not in result.columns:
        result = add_place_type_and_road_corridor_features(result)

    result["is_large_vehicle"] = pd.to_numeric(
        result["vehicle_obstruction"],
        errors="coerce",
    ).fillna(0.0).ge(0.85)
    vehicle_text = (
        result.get("effective_vehicle_type", result.get("vehicle_type", ""))
        .fillna("")
        .astype(str)
        .str.lower()
    )
    result["is_two_wheeler"] = vehicle_text.map(lambda text: _text_contains(text, TWO_WHEELER_TERMS))
    result["main_road_parking_flag"] = result["parsed_violation_labels"].map(
        lambda labels: _label_contains(labels, "parking_in_main_road")
    ) | result.get("location", pd.Series([""] * len(result), index=result.index)).map(
        lambda value: _text_contains(value, ("main road", "ring road", "highway"))
    )
    result["double_parking_flag"] = result["parsed_violation_labels"].map(
        lambda labels: _label_contains(labels, "double_parking")
    )
    if "type_correction_flag" in result.columns:
        result["type_correction_flag"] = result["type_correction_flag"].fillna(False).astype(bool)
    else:
        result["type_correction_flag"] = False

    for flag_name in PLACE_TYPE_FLAGS:
        if flag_name not in result.columns:
            result[flag_name] = False
        result[flag_name] = result[flag_name].fillna(False).astype(bool)
    return result


def share(series: pd.Series) -> float:
    """Return boolean share as a float."""

    if series.empty:
        return 0.0
    return float(series.fillna(False).astype(bool).mean())
