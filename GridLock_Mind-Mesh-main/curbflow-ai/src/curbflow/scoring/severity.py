"""Violation severity weighting for row-level PFDI scoring."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import yaml

from curbflow.scoring.violation_parser import parse_violation_labels


DEFAULT_SCORING_CONFIG_PATH = Path("configs/scoring_config.yaml")

CONFIG_WEIGHT_ALIASES = {
    "parking_near_traffic_light_zebra": "parking_near_traffic_light_or_zebra_crossing",
    "parking_opposite_another_vehicle": "parking_opposite_another_parked_vehicle",
}

DEFAULT_VIOLATION_WEIGHTS = {
    "double_parking": 1.00,
    "parking_in_main_road": 0.95,
    "parking_near_road_crossing": 0.90,
    "parking_near_traffic_light_zebra": 0.88,
    "parking_opposite_another_vehicle": 0.86,
    "parking_near_bus_stop_school_hospital": 0.85,
    "parking_other_than_bus_stop": 0.75,
    "no_parking": 0.70,
    "wrong_parking": 0.65,
    "parking_on_footpath": 0.55,
    "defective_number_plate": 0.15,
    "minor_other": 0.10,
}


def load_violation_weights(config_path: str | Path = DEFAULT_SCORING_CONFIG_PATH) -> dict[str, float]:
    """Load canonical violation weights from the scoring config."""

    path = Path(config_path)
    if not path.exists():
        return DEFAULT_VIOLATION_WEIGHTS.copy()

    config = yaml.safe_load(path.read_text()) or {}
    raw_weights = config.get("violation_weights", {})
    weights: dict[str, float] = {}
    for label, default_weight in DEFAULT_VIOLATION_WEIGHTS.items():
        config_key = CONFIG_WEIGHT_ALIASES.get(label, label)
        weights[label] = float(raw_weights.get(config_key, raw_weights.get(label, default_weight)))
    return weights


def compound_violation_severity(
    labels: list[str],
    weights: dict[str, float] | None = None,
) -> float:
    """Compute compounded multi-label violation severity."""

    if not labels:
        return 0.0
    active_weights = weights or load_violation_weights()
    product = math.prod(1 - active_weights.get(label, active_weights["minor_other"]) for label in labels)
    return 1 - product


def score_violation_severity(
    violation_value: Any,
    weights: dict[str, float] | None = None,
) -> float:
    """Parse a raw violation value and return compounded severity."""

    return compound_violation_severity(parse_violation_labels(violation_value), weights)
