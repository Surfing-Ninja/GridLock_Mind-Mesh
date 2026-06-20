"""Resource allocation optimizer for officers and tow units."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from curbflow.features.training_table import MODEL_TRAINING_TABLE_PATH
from curbflow.ml.ranker.ensemble import PREDICTIONS_PATH
from curbflow.planner.action_rules import build_action_candidates
from curbflow.planner.explanations import (
    build_recommendation_explanation,
    build_recommendation_json,
)
from curbflow.planner.priority_score import (
    add_candidate_priority_scores,
    mode_explore_fraction,
    validate_mode,
)


RECOMMENDATIONS_PATH = Path("data/processed/recommendations.parquet")

RECOMMENDATION_COLUMNS = [
    "recommendation_rank",
    "zone_id",
    "window_start",
    "police_station",
    "action",
    "action_category",
    "mode",
    "expected_relief",
    "score_per_resource_unit",
    "officers_required",
    "tow_units_required",
    "cumulative_officers",
    "cumulative_tow_units",
    "predicted_pfdi",
    "hotspot_probability",
    "coverage_gap",
    "blindspot_risk_score",
    "exploit_score",
    "explore_score",
    "explanation",
    "explanation_json",
]


def _normalise_input(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize planner keys and common numeric columns."""

    result = frame.copy()
    if "zone_id" not in result.columns:
        raise ValueError("Planner input requires zone_id.")
    if "window_start" not in result.columns:
        raise ValueError("Planner input requires window_start.")
    if "police_station" not in result.columns:
        result["police_station"] = "unknown"
    result["zone_id"] = result["zone_id"].astype(str)
    result["police_station"] = result["police_station"].fillna("unknown").astype(str)
    result["window_start"] = pd.to_datetime(result["window_start"], errors="coerce")
    result = result[result["window_start"].notna()].copy()
    for column in (
        "predicted_pfdi",
        "hotspot_probability",
        "coverage_gap",
        "blindspot_risk_score",
        "exploit_score",
        "explore_score",
    ):
        if column not in result.columns:
            result[column] = 0.0
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0.0)
    return result


def merge_planner_features(
    predictions: pd.DataFrame,
    feature_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Merge engineered feature columns into prediction rows for action rules."""

    result = _normalise_input(predictions)
    if feature_frame is None or feature_frame.empty:
        return result
    features = _normalise_input(feature_frame)
    duplicate_columns = [
        column
        for column in features.columns
        if column in result.columns and column not in {"zone_id", "window_start"}
    ]
    features = features.drop(columns=duplicate_columns, errors="ignore")
    features = features.drop_duplicates(["zone_id", "window_start"], keep="last")
    return result.merge(features, on=["zone_id", "window_start"], how="left")


def load_planner_input(
    predictions_path: str | Path = PREDICTIONS_PATH,
    *,
    features_path: str | Path | None = MODEL_TRAINING_TABLE_PATH,
) -> pd.DataFrame:
    """Load final predictions and optional engineered features for planning."""

    prediction_file = Path(predictions_path)
    if not prediction_file.exists():
        raise FileNotFoundError(f"Predictions not found: {prediction_file}. Run `make predict` first.")
    predictions = pd.read_parquet(prediction_file)
    feature_frame = None
    if features_path is not None and Path(features_path).exists():
        feature_frame = pd.read_parquet(features_path)
    return merge_planner_features(predictions, feature_frame)


def _filter_planner_scope(
    frame: pd.DataFrame,
    *,
    police_station: str | None = None,
    window_start: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Filter rows to the requested station and window."""

    result = _normalise_input(frame)
    if police_station:
        result = result[result["police_station"].astype(str).eq(str(police_station))]
    if window_start is None:
        if result.empty:
            return result
        selected_window = result["window_start"].max()
    else:
        selected_window = pd.Timestamp(window_start)
    result = result[result["window_start"].eq(selected_window)].copy()
    return result.reset_index(drop=True)


def _feasible(
    candidate: pd.Series,
    *,
    used_zones: set[str],
    used_officers: int,
    used_tow_units: int,
    available_officers: int,
    available_tow_units: int,
) -> bool:
    """Return whether a candidate can be added under constraints."""

    zone_id = str(candidate["zone_id"])
    if zone_id in used_zones:
        return False
    if used_officers + int(candidate["officers_required"]) > available_officers:
        return False
    if used_tow_units + int(candidate["tow_units_required"]) > available_tow_units:
        return False
    return True


def _select_candidate(
    selected: list[dict],
    candidate: pd.Series,
    *,
    used_zones: set[str],
    resources: dict[str, int],
) -> None:
    """Append a candidate and update mutable resource trackers."""

    resources["officers"] += int(candidate["officers_required"])
    resources["tow_units"] += int(candidate["tow_units_required"])
    used_zones.add(str(candidate["zone_id"]))
    record = candidate.to_dict()
    record["cumulative_officers"] = resources["officers"]
    record["cumulative_tow_units"] = resources["tow_units"]
    selected.append(record)


def _target_blindspot_count(
    candidates: pd.DataFrame,
    *,
    mode: str,
    available_officers: int,
) -> int:
    """Compute mode-specific target count for blindspot audit actions."""

    if candidates.empty or available_officers <= 0:
        return 0
    unique_zone_capacity = min(available_officers, candidates["zone_id"].nunique())
    available_blindspot_zones = candidates.loc[
        candidates["action_category"].eq("blindspot"),
        "zone_id",
    ].nunique()
    target = int(round(unique_zone_capacity * mode_explore_fraction(mode)))
    return min(max(target, 0), int(available_blindspot_zones))


def greedy_optimize_candidates(
    candidates: pd.DataFrame,
    *,
    available_officers: int,
    available_tow_units: int,
    mode: str = "balanced",
) -> pd.DataFrame:
    """Greedily select zone-action pairs under officer and tow constraints."""

    mode = validate_mode(mode)
    if available_officers < 0 or available_tow_units < 0:
        raise ValueError("Available officers and tow units must be non-negative.")
    if candidates.empty or available_officers == 0:
        return pd.DataFrame(columns=RECOMMENDATION_COLUMNS)

    sorted_candidates = candidates.sort_values(
        ["score_per_resource_unit", "expected_relief"],
        ascending=False,
    ).reset_index(drop=True)
    selected: list[dict] = []
    used_zones: set[str] = set()
    resources = {"officers": 0, "tow_units": 0}

    target_blindspots = _target_blindspot_count(
        sorted_candidates,
        mode=mode,
        available_officers=available_officers,
    )
    if target_blindspots > 0:
        for _, candidate in sorted_candidates[sorted_candidates["action_category"].eq("blindspot")].iterrows():
            if len([row for row in selected if row["action_category"] == "blindspot"]) >= target_blindspots:
                break
            if _feasible(
                candidate,
                used_zones=used_zones,
                used_officers=resources["officers"],
                used_tow_units=resources["tow_units"],
                available_officers=available_officers,
                available_tow_units=available_tow_units,
            ):
                _select_candidate(selected, candidate, used_zones=used_zones, resources=resources)

    for _, candidate in sorted_candidates.iterrows():
        if _feasible(
            candidate,
            used_zones=used_zones,
            used_officers=resources["officers"],
            used_tow_units=resources["tow_units"],
            available_officers=available_officers,
            available_tow_units=available_tow_units,
        ):
            _select_candidate(selected, candidate, used_zones=used_zones, resources=resources)

    recommendations = pd.DataFrame.from_records(selected)
    if recommendations.empty:
        return pd.DataFrame(columns=RECOMMENDATION_COLUMNS)
    recommendations["mode"] = mode
    recommendations["recommendation_rank"] = np.arange(1, len(recommendations) + 1)
    recommendations["explanation"] = recommendations.apply(build_recommendation_explanation, axis=1)
    recommendations["explanation_json"] = recommendations.apply(build_recommendation_json, axis=1)
    for column in RECOMMENDATION_COLUMNS:
        if column not in recommendations.columns:
            recommendations[column] = pd.NA
    return recommendations[RECOMMENDATION_COLUMNS]


def plan_enforcement(
    frame: pd.DataFrame,
    *,
    police_station: str | None = None,
    window_start: str | pd.Timestamp | None = None,
    available_officers: int = 8,
    available_tow_units: int = 2,
    mode: str = "balanced",
) -> pd.DataFrame:
    """Create resource-constrained enforcement recommendations for one window."""

    scoped = _filter_planner_scope(
        frame,
        police_station=police_station,
        window_start=window_start,
    )
    if scoped.empty:
        return pd.DataFrame(columns=RECOMMENDATION_COLUMNS)
    candidates = build_action_candidates(scoped)
    candidates = add_candidate_priority_scores(candidates, scoped, mode=mode)
    return greedy_optimize_candidates(
        candidates,
        available_officers=available_officers,
        available_tow_units=available_tow_units,
        mode=mode,
    )


def write_recommendations(
    input_frame_or_path: pd.DataFrame | str | Path = PREDICTIONS_PATH,
    output_path: str | Path = RECOMMENDATIONS_PATH,
    *,
    features_path: str | Path | None = MODEL_TRAINING_TABLE_PATH,
    police_station: str | None = None,
    window_start: str | pd.Timestamp | None = None,
    available_officers: int = 8,
    available_tow_units: int = 2,
    mode: str = "balanced",
) -> pd.DataFrame:
    """Run the planner and save recommendations to parquet."""

    if isinstance(input_frame_or_path, pd.DataFrame):
        frame = input_frame_or_path
    else:
        frame = load_planner_input(input_frame_or_path, features_path=features_path)
    recommendations = plan_enforcement(
        frame,
        police_station=police_station,
        window_start=window_start,
        available_officers=available_officers,
        available_tow_units=available_tow_units,
        mode=mode,
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    recommendations.to_parquet(destination, index=False)
    return recommendations
