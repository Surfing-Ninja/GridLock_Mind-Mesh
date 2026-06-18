"""Ensemble scoring for BE-STHGT, ranker, and rule blindspot scores."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from curbflow.exposure.visibility import robust_percentile_scale
from curbflow.features.training_table import MODEL_TRAINING_TABLE_PATH
from curbflow.graph.build_hetero_graph import GRAPH_FEATURES_PATH
from curbflow.graph.graph_features import merge_graph_features
from curbflow.ml.be_sthgt.trainer import DEEP_PREDICTIONS_PATH
from curbflow.ml.ranker.lgbm_ranker import RANKER_METRICS_PATH, RANKER_MODEL_PATH, lgb


PREDICTIONS_PATH = Path("data/processed/predictions.parquet")

ENSEMBLE_WEIGHTS = {
    "be_sthgt": 0.65,
    "lightgbm": 0.25,
    "rule_blindspot": 0.10,
}
DEPLOYMENT_MODE_WEIGHTS = {
    "conservative": (0.85, 0.15),
    "balanced": (0.70, 0.30),
    "discovery": (0.55, 0.45),
}

REQUIRED_OUTPUT_COLUMNS = [
    "zone_id",
    "window_start",
    "police_station",
    "predicted_count",
    "predicted_pfdi",
    "hotspot_probability",
    "q90_pfdi",
    "latent_risk",
    "exposure",
    "coverage_gap",
    "observed_risk_score",
    "blindspot_risk_score",
    "exploit_score",
    "explore_score",
    "deployment_priority_conservative",
    "deployment_priority_balanced",
    "deployment_priority_discovery",
    "recommended_action",
    "explanation_json",
]


def _normalise_keys(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize prediction merge keys."""

    result = frame.copy()
    if "zone_id" not in result.columns:
        raise ValueError("Prediction input requires zone_id.")
    if "window_start" not in result.columns:
        raise ValueError("Prediction input requires window_start.")
    if "police_station" not in result.columns:
        result["police_station"] = "unknown"
    result["zone_id"] = result["zone_id"].astype(str)
    result["police_station"] = result["police_station"].fillna("unknown").astype(str)
    result["window_start"] = pd.to_datetime(result["window_start"], errors="coerce")
    result = result[result["window_start"].notna()].copy()
    return result


def _numeric(frame: pd.DataFrame, candidates: tuple[str, ...], default: float = 0.0) -> pd.Series:
    """Return first available numeric column."""

    result = pd.Series([np.nan] * len(frame), index=frame.index, dtype="float64")
    for column in candidates:
        if column in frame.columns:
            values = pd.to_numeric(frame[column], errors="coerce")
            result = result.where(result.notna(), values)
    return result.fillna(default)


def _score_0_100(values: pd.Series | np.ndarray | float, *, probability_hint: bool = False) -> pd.Series:
    """Scale a raw feature defensibly to a 0-100 score."""

    if isinstance(values, pd.Series):
        series = pd.to_numeric(values, errors="coerce").fillna(0.0)
    else:
        series = pd.Series(values, dtype="float64")
    if series.empty:
        return series.astype(float)
    max_value = float(series.max()) if series.notna().any() else 0.0
    min_value = float(series.min()) if series.notna().any() else 0.0
    if probability_hint or (min_value >= 0.0 and max_value <= 1.5):
        return (100.0 * series.clip(lower=0.0, upper=1.0)).astype(float)
    return series.clip(lower=0.0, upper=100.0).astype(float)


def _robust_norm_0_100(values: pd.Series | np.ndarray) -> pd.Series:
    """Robust percentile normalize to a 0-100 score."""

    if not isinstance(values, pd.Series):
        values = pd.Series(values, dtype="float64")
    return 100.0 * robust_percentile_scale(values)


def _merge_graph_features(frame: pd.DataFrame, graph_features_path: str | Path | None) -> pd.DataFrame:
    """Merge optional graph features into the prediction frame."""

    if graph_features_path is None:
        return frame
    path = Path(graph_features_path)
    if not path.exists():
        return frame
    graph_features = pd.read_parquet(path)
    if "zone_id" not in graph_features.columns:
        raise ValueError(f"Graph features at {path} must include zone_id.")
    graph_features = graph_features.copy()
    graph_features["zone_id"] = graph_features["zone_id"].astype(str)
    return merge_graph_features(frame, graph_features.drop_duplicates("zone_id"))


def _merge_deep_predictions(frame: pd.DataFrame, deep_predictions_path: str | Path | None) -> pd.DataFrame:
    """Merge BE-STHGT prediction columns when available."""

    if deep_predictions_path is None:
        return frame
    path = Path(deep_predictions_path)
    if not path.exists():
        return frame
    predictions = _normalise_keys(pd.read_parquet(path))
    pred_columns = [
        column
        for column in predictions.columns
        if column.startswith("pred_") and pd.api.types.is_numeric_dtype(predictions[column])
    ]
    if not pred_columns:
        return frame
    prediction_features = (
        predictions[["zone_id", "window_start", *pred_columns]]
        .groupby(["zone_id", "window_start"], as_index=False)
        .mean(numeric_only=True)
    )
    result = frame.drop(columns=[column for column in pred_columns if column in frame.columns], errors="ignore")
    return result.merge(prediction_features, on=["zone_id", "window_start"], how="left")


def load_prediction_frame(
    input_path: str | Path = MODEL_TRAINING_TABLE_PATH,
    *,
    graph_features_path: str | Path | None = GRAPH_FEATURES_PATH,
    deep_predictions_path: str | Path | None = DEEP_PREDICTIONS_PATH,
) -> pd.DataFrame:
    """Load model features plus optional graph and BE-STHGT prediction artifacts."""

    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Prediction input not found: {path}. Run `make features` first.")
    frame = _normalise_keys(pd.read_parquet(path))
    frame = _merge_graph_features(frame, graph_features_path)
    frame = _merge_deep_predictions(frame, deep_predictions_path)
    if frame.empty:
        raise ValueError("Prediction input is empty after key normalization.")
    return frame


def _ranker_feature_columns(metrics_path: str | Path) -> list[str]:
    """Read ranker feature columns from the saved metrics JSON."""

    path = Path(metrics_path)
    if not path.exists():
        return []
    metrics = json.loads(path.read_text(encoding="utf-8"))
    feature_columns = metrics.get("feature_columns", [])
    return [str(column) for column in feature_columns]


def predict_lightgbm_rank_scores(
    frame: pd.DataFrame,
    *,
    model_path: str | Path = RANKER_MODEL_PATH,
    metrics_path: str | Path = RANKER_METRICS_PATH,
) -> pd.Series:
    """Score rows with the saved LambdaRank model when available."""

    if lgb is None:
        return pd.Series([np.nan] * len(frame), index=frame.index, dtype="float64")
    model_file = Path(model_path)
    feature_columns = _ranker_feature_columns(metrics_path)
    if not model_file.exists() or not feature_columns:
        return pd.Series([np.nan] * len(frame), index=frame.index, dtype="float64")

    matrix = pd.DataFrame(index=frame.index)
    for column in feature_columns:
        if column in frame.columns:
            if pd.api.types.is_bool_dtype(frame[column]):
                matrix[column] = frame[column].fillna(False).astype(int)
            else:
                matrix[column] = pd.to_numeric(frame[column], errors="coerce")
        else:
            matrix[column] = 0.0
    matrix = matrix.replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(np.float32)
    booster = lgb.Booster(model_file=str(model_file))
    scores = booster.predict(matrix)
    return pd.Series(scores, index=frame.index, dtype="float64")


def _evening_peak_priority(frame: pd.DataFrame) -> pd.Series:
    """Derive a 0-100 evening priority score from available window fields."""

    if "evening_peak_priority" in frame.columns:
        return _score_0_100(pd.to_numeric(frame["evening_peak_priority"], errors="coerce").fillna(0.0))
    if "peak_priority" in frame.columns:
        peak = pd.to_numeric(frame["peak_priority"], errors="coerce").fillna(1.0)
        return (((peak - 1.0) / 0.40).clip(lower=0.0, upper=1.0) * 100.0).astype(float)
    window_start = pd.to_datetime(frame["window_start"], errors="coerce")
    minute = window_start.dt.hour * 60 + window_start.dt.minute
    evening = minute.between(15 * 60 + 30, 20 * 60 + 29, inclusive="both")
    return evening.astype(float) * 100.0


def _observed_risk(frame: pd.DataFrame) -> pd.Series:
    """Compute observed/exploit-facing risk score."""

    predicted_pfdi = _score_0_100(_numeric(frame, ("pred_pfdi", "predicted_pfdi", "bias_corrected_pfdi", "observed_pfdi")))
    hotspot_probability = _score_0_100(
        _numeric(frame, ("pred_hotspot_prob", "hotspot_probability"), default=0.0),
        probability_hint=True,
    )
    recurrence = _robust_norm_0_100(
        _numeric(frame, ("recurrence", "repeat_vehicle_share", "repeat_vehicle_count", "persistence_score"))
    )
    location_criticality = _score_0_100(
        _numeric(frame, ("location_criticality_mean", "location_criticality", "location_criticality_score")),
        probability_hint=True,
    )
    repeat_pressure = _score_0_100(
        _numeric(frame, ("repeat_pressure_mean", "repeat_pressure")),
        probability_hint=True,
    )
    return (
        0.45 * predicted_pfdi
        + 0.25 * hotspot_probability
        + 0.15 * recurrence
        + 0.10 * location_criticality
        + 0.05 * repeat_pressure
    ).clip(lower=0.0, upper=100.0)


def _explore_risk(frame: pd.DataFrame, blindspot_risk_score: pd.Series) -> pd.Series:
    """Compute exploration/blindspot-facing risk score."""

    static_potential = _score_0_100(_numeric(frame, ("static_potential",), default=0.0), probability_hint=True)
    coverage_gap = _score_0_100(_numeric(frame, ("coverage_gap",), default=0.0), probability_hint=True)
    evening_priority = _evening_peak_priority(frame)
    return (
        0.45 * blindspot_risk_score
        + 0.25 * static_potential
        + 0.20 * coverage_gap
        + 0.10 * evening_priority
    ).clip(lower=0.0, upper=100.0)


def _recommended_action(row: pd.Series) -> str:
    """Map scores to an operational action label."""

    if row["explore_score"] >= 70 and row["coverage_gap"] >= 0.60:
        return "blindspot_audit"
    if row["hotspot_probability"] >= 0.65 and row["predicted_pfdi"] >= 65:
        return "targeted_enforcement"
    if row["q90_pfdi"] >= 75 and row["predicted_count"] >= 3:
        return "tow_support_standby"
    if row["coverage_gap"] >= 0.70:
        return "visibility_sweep"
    return "routine_patrol"


def _explanation(row: pd.Series) -> str:
    """Build compact JSON reasons for API and planner display."""

    reasons: list[str] = []
    if row["observed_risk_score"] >= 70:
        reasons.append("high predicted observed disruption")
    if row["blindspot_risk_score"] >= 60:
        reasons.append("high blindspot risk")
    if row["coverage_gap"] >= 0.60:
        reasons.append("low enforcement visibility")
    if row["hotspot_probability"] >= 0.65:
        reasons.append("high hotspot probability")
    if row["deployment_priority_discovery"] > row["deployment_priority_conservative"] + 5:
        reasons.append("discovery mode lifts priority")
    if not reasons:
        reasons.append("moderate routine patrol priority")
    payload = {
        "reasons": reasons,
        "scores": {
            "observed": round(float(row["observed_risk_score"]), 3),
            "blindspot": round(float(row["blindspot_risk_score"]), 3),
            "exploit": round(float(row["exploit_score"]), 3),
            "explore": round(float(row["explore_score"]), 3),
        },
    }
    return json.dumps(payload, separators=(",", ":"))


def build_ensemble_predictions(
    frame: pd.DataFrame,
    *,
    ranker_model_path: str | Path = RANKER_MODEL_PATH,
    ranker_metrics_path: str | Path = RANKER_METRICS_PATH,
) -> pd.DataFrame:
    """Build final CurbFlow prediction and deployment-priority scores."""

    result = _normalise_keys(frame)
    result["predicted_count"] = _numeric(result, ("pred_count_mu", "predicted_count", "record_count"))
    result["predicted_pfdi"] = _score_0_100(
        _numeric(result, ("pred_pfdi", "predicted_pfdi", "bias_corrected_pfdi", "observed_pfdi"))
    )
    result["hotspot_probability"] = (
        _numeric(result, ("pred_hotspot_prob", "hotspot_probability"), default=np.nan)
        .where(lambda values: values.notna(), result["predicted_pfdi"] / 100.0)
        .clip(lower=0.0, upper=1.0)
    )
    result["q90_pfdi"] = _score_0_100(
        _numeric(result, ("pred_q90_pfdi", "q90_pfdi", "rolling_7d_pfdi", "observed_pfdi"))
    )
    result["latent_risk"] = _numeric(
        result,
        ("pred_latent_risk", "latent_risk", "static_potential", "predicted_count"),
    )
    result["exposure"] = _numeric(result, ("exposure", "exposure_next"), default=0.0).clip(0.0, 1.0)
    if "coverage_gap" not in result.columns:
        result["coverage_gap"] = 1.0 - result["exposure"]
    else:
        result["coverage_gap"] = pd.to_numeric(result["coverage_gap"], errors="coerce").fillna(
            1.0 - result["exposure"]
        )
    result["coverage_gap"] = result["coverage_gap"].clip(0.0, 1.0)

    result["observed_risk_score"] = _observed_risk(result)
    result["blindspot_risk_score"] = _score_0_100(
        _numeric(result, ("blindspot_risk", "pred_blindspot_score", "blindspot_risk_score")),
    )
    result["explore_score"] = _explore_risk(result, result["blindspot_risk_score"])

    be_rank_score = _numeric(result, ("pred_rank_score", "be_rank_score"), default=np.nan)
    be_rank_score = be_rank_score.where(be_rank_score.notna(), result["observed_risk_score"])
    lgbm_rank_score = predict_lightgbm_rank_scores(
        result,
        model_path=ranker_model_path,
        metrics_path=ranker_metrics_path,
    )
    lgbm_rank_score = lgbm_rank_score.where(lgbm_rank_score.notna(), result["observed_risk_score"])
    rule_blindspot_score = result["blindspot_risk_score"]

    normalized_be = _robust_norm_0_100(be_rank_score)
    normalized_lgbm = _robust_norm_0_100(lgbm_rank_score)
    normalized_rule = _robust_norm_0_100(rule_blindspot_score)
    result["exploit_score"] = (
        ENSEMBLE_WEIGHTS["be_sthgt"] * normalized_be
        + ENSEMBLE_WEIGHTS["lightgbm"] * normalized_lgbm
        + ENSEMBLE_WEIGHTS["rule_blindspot"] * normalized_rule
    ).clip(lower=0.0, upper=100.0)

    for mode, (exploit_weight, explore_weight) in DEPLOYMENT_MODE_WEIGHTS.items():
        result[f"deployment_priority_{mode}"] = (
            exploit_weight * result["exploit_score"] + explore_weight * result["explore_score"]
        ).clip(lower=0.0, upper=100.0)

    result["recommended_action"] = result.apply(_recommended_action, axis=1)
    result["explanation_json"] = result.apply(_explanation, axis=1)

    for column in REQUIRED_OUTPUT_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA
    return result[REQUIRED_OUTPUT_COLUMNS].sort_values(
        ["window_start", "police_station", "deployment_priority_balanced"],
        ascending=[True, True, False],
    ).reset_index(drop=True)


def write_ensemble_predictions(
    input_frame_or_path: pd.DataFrame | str | Path = MODEL_TRAINING_TABLE_PATH,
    output_path: str | Path = PREDICTIONS_PATH,
    *,
    graph_features_path: str | Path | None = GRAPH_FEATURES_PATH,
    deep_predictions_path: str | Path | None = DEEP_PREDICTIONS_PATH,
    ranker_model_path: str | Path = RANKER_MODEL_PATH,
    ranker_metrics_path: str | Path = RANKER_METRICS_PATH,
) -> pd.DataFrame:
    """Create and save the final CurbFlow ensemble prediction artifact."""

    frame = (
        input_frame_or_path
        if isinstance(input_frame_or_path, pd.DataFrame)
        else load_prediction_frame(
            input_frame_or_path,
            graph_features_path=graph_features_path,
            deep_predictions_path=deep_predictions_path,
        )
    )
    predictions = build_ensemble_predictions(
        frame,
        ranker_model_path=ranker_model_path,
        ranker_metrics_path=ranker_metrics_path,
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_parquet(destination, index=False)
    return predictions
