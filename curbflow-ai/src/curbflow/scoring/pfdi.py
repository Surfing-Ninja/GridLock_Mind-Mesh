"""Parking-Induced Flow Disruption Index computation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from curbflow.data.schema import CLEAN_PARQUET_PATH
from curbflow.scoring.location_criticality import (
    compute_location_criticality,
    named_junction_flag,
)
from curbflow.scoring.repeat_pressure import add_repeat_pressure_features
from curbflow.scoring.severity import compound_violation_severity
from curbflow.scoring.vehicle_obstruction import score_vehicle_obstruction, select_vehicle_type
from curbflow.scoring.violation_parser import parse_violation_labels


ROW_SCORES_PATH = Path("data/interim/row_scores.parquet")

VALIDATION_CONFIDENCE = {
    "approved": 1.00,
    "unknown": 0.70,
    "created1": 0.55,
    "processing": 0.55,
    "rejected": 0.25,
    "duplicate": 0.10,
}

ROW_OBSTRUCTION_WEIGHTS = {
    "violation_severity": 0.42,
    "vehicle_obstruction": 0.23,
    "location_criticality": 0.20,
    "repeat_pressure": 0.10,
    "named_junction_flag": 0.05,
}


def validation_confidence(value: Any) -> float:
    """Map validation status to confidence, treating missing values as unknown."""

    if pd.isna(value):
        return VALIDATION_CONFIDENCE["unknown"]
    key = str(value).strip().lower()
    if not key:
        return VALIDATION_CONFIDENCE["unknown"]
    return VALIDATION_CONFIDENCE.get(key, VALIDATION_CONFIDENCE["unknown"])


def compute_row_obstruction_score(
    *,
    violation_severity: float,
    vehicle_obstruction: float,
    location_criticality: float,
    repeat_pressure: float,
    named_junction: int,
    quality_multiplier: float,
) -> float:
    """Compute row-level parking obstruction score."""

    weighted_sum = (
        ROW_OBSTRUCTION_WEIGHTS["violation_severity"] * violation_severity
        + ROW_OBSTRUCTION_WEIGHTS["vehicle_obstruction"] * vehicle_obstruction
        + ROW_OBSTRUCTION_WEIGHTS["location_criticality"] * location_criticality
        + ROW_OBSTRUCTION_WEIGHTS["repeat_pressure"] * repeat_pressure
        + ROW_OBSTRUCTION_WEIGHTS["named_junction_flag"] * named_junction
    )
    return float(quality_multiplier * 100 * weighted_sum)


def _quality_multiplier(row: pd.Series) -> float:
    """Use evidence quality when available, otherwise fall back to validation confidence."""

    evidence_quality = row.get("evidence_quality_score")
    if pd.notna(evidence_quality):
        return float(evidence_quality)
    return float(row["validation_confidence"])


def score_pfdi_rows(frame: pd.DataFrame, *, compute_evidence_quality: bool = False) -> pd.DataFrame:
    """Add row-level PFDI input columns and row obstruction scores."""

    scored = add_repeat_pressure_features(frame)
    parsed_labels = scored["violation_type"].map(parse_violation_labels)
    scored["parsed_violation_labels"] = parsed_labels
    scored["violation_severity"] = parsed_labels.map(compound_violation_severity)
    scored["effective_vehicle_type"] = scored.apply(
        lambda row: select_vehicle_type(row.get("vehicle_type"), row.get("updated_vehicle_type")),
        axis=1,
    )
    scored["vehicle_obstruction"] = scored.apply(
        lambda row: score_vehicle_obstruction(
            row.get("vehicle_type"),
            row.get("updated_vehicle_type"),
        ),
        axis=1,
    )
    scored["named_junction_flag"] = scored["junction_name"].map(named_junction_flag).astype(int)
    scored["location_criticality"] = scored.apply(
        lambda row: compute_location_criticality(
            junction_name=row.get("junction_name"),
            location=row.get("location"),
            parsed_labels=row["parsed_violation_labels"],
        ),
        axis=1,
    )
    scored["validation_confidence"] = scored.get(
        "validation_status",
        pd.Series(["unknown"] * len(scored), index=scored.index),
    ).map(validation_confidence)
    if compute_evidence_quality:
        from curbflow.features.novel_features import add_evidence_quality_features

        scored = add_evidence_quality_features(scored)
    scored["pfdi_quality_multiplier"] = scored.apply(_quality_multiplier, axis=1)
    scored["row_obstruction_score"] = scored.apply(
        lambda row: compute_row_obstruction_score(
            violation_severity=row["violation_severity"],
            vehicle_obstruction=row["vehicle_obstruction"],
            location_criticality=row["location_criticality"],
            repeat_pressure=row["repeat_pressure"],
            named_junction=row["named_junction_flag"],
            quality_multiplier=row["pfdi_quality_multiplier"],
        ),
        axis=1,
    )
    return scored


def run_pfdi_scoring(
    clean_parquet_path: str | Path = CLEAN_PARQUET_PATH,
    output_path: str | Path = ROW_SCORES_PATH,
    *,
    compute_evidence_quality: bool = False,
) -> pd.DataFrame:
    """Read cleaned violations, score row-level PFDI inputs, and write parquet output."""

    clean_path = Path(clean_parquet_path)
    if not clean_path.exists():
        raise FileNotFoundError(f"Clean violations parquet not found: {clean_path}")
    frame = pd.read_parquet(clean_path)
    scored = score_pfdi_rows(frame, compute_evidence_quality=compute_evidence_quality)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    scored.to_parquet(destination, index=False)
    return scored
