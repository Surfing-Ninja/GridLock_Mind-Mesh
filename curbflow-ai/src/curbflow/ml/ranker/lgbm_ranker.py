"""LightGBM LambdaRank training and inference wrapper."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from curbflow.features.training_table import MODEL_TRAINING_TABLE_PATH
from curbflow.graph.build_hetero_graph import GRAPH_FEATURES_PATH
from curbflow.graph.graph_features import merge_graph_features
from curbflow.ml.be_sthgt.trainer import DEEP_PREDICTIONS_PATH
from curbflow.ml.metrics import (
    ndcg_at_k,
    precision_at_k,
    station_wise_precision_at_k,
)

try:
    import lightgbm as lgb
except ImportError:  # pragma: no cover - exercised only in missing dependency environments.
    lgb = None


RANKER_MODEL_PATH = Path("artifacts/models/ranker_lgbm.txt")
RANKER_METRICS_PATH = Path("artifacts/metrics/ranker_metrics.json")
FEATURE_IMPORTANCE_PATH = Path("artifacts/metrics/feature_importance.csv")

TARGET_COLUMN = "next_relevance"
HOTSPOT_COLUMN = "next_hotspot"
GROUP_COLUMNS = ("police_station", "window_start")

EXCLUDED_FEATURE_COLUMNS = {
    "zone_id",
    "window_start",
    "window_end",
    "time_window_start",
    "next_window_start",
    "date",
    "police_station",
    "road_corridor_id",
    "place_type_primary",
    "patrol_myopia_level",
    "is_active_training_zone",
    "active_zone_record_count",
    "next_count",
    "next_pfdi",
    "next_bias_corrected_pfdi",
    "next_hotspot",
    "next_relevance",
    "target_count",
    "target_pfdi",
    "target_hotspot",
    "target_relevance",
    "split",
}


@dataclass(frozen=True)
class RankerConfig:
    """LightGBM LambdaRank training configuration."""

    train_fraction: float = 0.70
    val_fraction: float = 0.15
    objective: str = "lambdarank"
    metric: str = "ndcg"
    ndcg_eval_at: tuple[int, ...] = (5, 10, 20)
    learning_rate: float = 0.05
    num_leaves: int = 63
    n_estimators: int = 800
    feature_fraction: float = 0.85
    bagging_fraction: float = 0.85
    bagging_freq: int = 3
    min_data_in_leaf: int = 20
    early_stopping_rounds: int = 50
    random_state: int = 42


@dataclass
class RankerArtifacts:
    """Paths and summary tables written by ranker training."""

    model_path: Path
    metrics_path: Path
    feature_importance_path: Path
    comparison_table: list[dict[str, Any]] = field(default_factory=list)


def _normalise_keys(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize merge and ranking keys."""

    result = frame.copy()
    if "zone_id" not in result.columns:
        raise ValueError("Ranker input requires zone_id.")
    if "window_start" not in result.columns:
        raise ValueError("Ranker input requires window_start.")
    if "police_station" not in result.columns:
        result["police_station"] = "unknown"
    result["zone_id"] = result["zone_id"].astype(str)
    result["police_station"] = result["police_station"].fillna("unknown").astype(str)
    result["window_start"] = pd.to_datetime(result["window_start"], errors="coerce")
    result = result[result["window_start"].notna()].copy()
    return result


def _merge_optional_graph_features(frame: pd.DataFrame, graph_features_path: str | Path | None) -> pd.DataFrame:
    """Merge graph features when the artifact exists."""

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


def _merge_optional_deep_predictions(frame: pd.DataFrame, deep_predictions_path: str | Path | None) -> pd.DataFrame:
    """Merge BE-STHGT prediction columns when available."""

    if deep_predictions_path is None:
        return frame
    path = Path(deep_predictions_path)
    if not path.exists():
        return frame
    predictions = pd.read_parquet(path)
    required = {"zone_id", "window_start"}
    if not required.issubset(predictions.columns):
        raise ValueError(f"Deep predictions at {path} must include zone_id and window_start.")
    predictions = _normalise_keys(predictions)
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
    return frame.merge(prediction_features, on=["zone_id", "window_start"], how="left")


def load_ranker_frame(
    training_table_path: str | Path = MODEL_TRAINING_TABLE_PATH,
    *,
    graph_features_path: str | Path | None = GRAPH_FEATURES_PATH,
    deep_predictions_path: str | Path | None = DEEP_PREDICTIONS_PATH,
) -> pd.DataFrame:
    """Load the training table plus optional graph and deep prediction features."""

    path = Path(training_table_path)
    if not path.exists():
        raise FileNotFoundError(f"Model training table not found: {path}. Run `make features` first.")
    frame = _normalise_keys(pd.read_parquet(path))
    if TARGET_COLUMN not in frame.columns:
        raise ValueError(f"Ranker input requires {TARGET_COLUMN}.")
    frame = _merge_optional_graph_features(frame, graph_features_path)
    frame = _merge_optional_deep_predictions(frame, deep_predictions_path)
    frame[TARGET_COLUMN] = pd.to_numeric(frame[TARGET_COLUMN], errors="coerce")
    frame = frame[frame[TARGET_COLUMN].notna()].copy()
    frame[TARGET_COLUMN] = frame[TARGET_COLUMN].clip(lower=0).astype(int)
    if HOTSPOT_COLUMN in frame.columns:
        frame[HOTSPOT_COLUMN] = frame[HOTSPOT_COLUMN].fillna(False).astype(bool)
    else:
        frame[HOTSPOT_COLUMN] = frame[TARGET_COLUMN].ge(2)
    if frame.empty:
        raise ValueError("Ranker input is empty after filtering rows with valid next_relevance.")
    return frame


def infer_ranker_feature_columns(frame: pd.DataFrame) -> list[str]:
    """Infer numeric engineered features for LambdaRank."""

    feature_columns = []
    for column in frame.columns:
        if column in EXCLUDED_FEATURE_COLUMNS:
            continue
        if column.startswith("target_") or column.startswith("next_"):
            continue
        if pd.api.types.is_bool_dtype(frame[column]) or pd.api.types.is_numeric_dtype(frame[column]):
            feature_columns.append(column)
    return sorted(feature_columns)


def chronological_rank_split(
    frame: pd.DataFrame,
    *,
    train_fraction: float = 0.70,
    val_fraction: float = 0.15,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split full station-window groups by chronological window order."""

    windows = np.array(sorted(frame["window_start"].dropna().unique()))
    if windows.size == 0:
        raise ValueError("Cannot split ranker frame without window_start values.")
    train_count = int(windows.size * train_fraction)
    val_count = int(windows.size * val_fraction)
    if windows.size >= 3:
        train_count = max(1, train_count)
        val_count = max(1, val_count)
        if train_count + val_count >= windows.size:
            val_count = max(1, windows.size - train_count - 1)
    else:
        train_count = max(1, windows.size - 1)
        val_count = max(0, windows.size - train_count)

    train_windows = set(windows[:train_count])
    val_windows = set(windows[train_count : train_count + val_count])
    test_windows = set(windows[train_count + val_count :])
    return (
        frame[frame["window_start"].isin(train_windows)].copy(),
        frame[frame["window_start"].isin(val_windows)].copy(),
        frame[frame["window_start"].isin(test_windows)].copy(),
    )


def _rank_group_key(frame: pd.DataFrame) -> pd.Series:
    """Create police_station x window_start group labels."""

    return (
        frame["police_station"].fillna("unknown").astype(str)
        + "||"
        + frame["window_start"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    )


def _sort_for_ranker(frame: pd.DataFrame) -> pd.DataFrame:
    """Sort so each LightGBM group is contiguous."""

    result = frame.copy()
    result["_rank_group"] = _rank_group_key(result)
    return result.sort_values(["window_start", "police_station", "_rank_group", "zone_id"]).reset_index(drop=True)


def _group_sizes(frame: pd.DataFrame) -> list[int]:
    """Return contiguous LightGBM group sizes."""

    if frame.empty:
        return []
    return frame.groupby("_rank_group", sort=False).size().astype(int).tolist()


def _has_rank_signal(frame: pd.DataFrame) -> bool:
    """Check that at least one group has relevance variation."""

    if frame.empty:
        return False
    relevance_counts = frame.groupby("_rank_group", sort=False)[TARGET_COLUMN].nunique()
    group_sizes = frame.groupby("_rank_group", sort=False).size()
    return bool(((group_sizes >= 2) & (relevance_counts >= 2)).any())


def _prepare_feature_matrix(
    train: pd.DataFrame,
    val: pd.DataFrame,
    test: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Convert feature columns to numeric and impute from train medians only."""

    if not feature_columns:
        raise ValueError("No numeric engineered features are available for LambdaRank.")

    def numeric_matrix(frame: pd.DataFrame) -> pd.DataFrame:
        matrix = frame[feature_columns].copy()
        for column in feature_columns:
            if pd.api.types.is_bool_dtype(matrix[column]):
                matrix[column] = matrix[column].astype(int)
            else:
                matrix[column] = pd.to_numeric(matrix[column], errors="coerce")
        return matrix

    X_train = numeric_matrix(train)
    medians = X_train.median(numeric_only=True).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    def clean(matrix: pd.DataFrame) -> pd.DataFrame:
        result = matrix.replace([np.inf, -np.inf], np.nan).fillna(medians).fillna(0.0)
        return result.astype(np.float32)

    return clean(X_train), clean(numeric_matrix(val)), clean(numeric_matrix(test))


def _evaluate_rank_scores(frame: pd.DataFrame, scores: np.ndarray, *, model_name: str, split: str) -> dict[str, Any]:
    """Evaluate ranking scores with hotspot and relevance metrics."""

    if frame.empty:
        return {
            "model": model_name,
            "split": split,
            "precision_at_5": 0.0,
            "precision_at_10": 0.0,
            "ndcg_at_5": 0.0,
            "ndcg_at_10": 0.0,
            "station_wise_precision_at_5": 0.0,
            "row_count": 0,
            "group_count": 0,
        }
    hotspot_labels = frame[HOTSPOT_COLUMN].astype(int).to_numpy()
    relevance = frame[TARGET_COLUMN].astype(int).to_numpy()
    station_ids = pd.factorize(frame["police_station"].fillna("unknown").astype(str))[0]
    return {
        "model": model_name,
        "split": split,
        "precision_at_5": precision_at_k(scores, hotspot_labels, k=5),
        "precision_at_10": precision_at_k(scores, hotspot_labels, k=10),
        "ndcg_at_5": ndcg_at_k(scores, relevance, k=5),
        "ndcg_at_10": ndcg_at_k(scores, relevance, k=10),
        "station_wise_precision_at_5": station_wise_precision_at_k(
            scores,
            hotspot_labels,
            station_ids,
            k=5,
        ),
        "row_count": int(len(frame)),
        "group_count": int(frame["_rank_group"].nunique()) if "_rank_group" in frame.columns else 0,
    }


def _baseline_scores(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    """Return leakage-safe baseline ranking scores."""

    if frame.empty:
        return {
            "count_only_baseline": np.array([], dtype=float),
            "historical_pfdi_baseline": np.array([], dtype=float),
            "rule_blindspot_baseline": np.array([], dtype=float),
        }

    count_column = next(
        (column for column in ("record_count", "lag_1_count", "raw_impact") if column in frame.columns),
        None,
    )
    historical_column = next(
        (
            column
            for column in (
                "same_slot_21d_avg_pfdi",
                "same_slot_7d_avg_pfdi",
                "lag_56_pfdi",
                "rolling_7d_pfdi",
                "observed_pfdi",
            )
            if column in frame.columns
        ),
        None,
    )
    if "blindspot_risk" in frame.columns:
        blindspot = pd.to_numeric(frame["blindspot_risk"], errors="coerce").fillna(0.0).to_numpy()
    elif {"coverage_gap", "static_potential"}.issubset(frame.columns):
        blindspot = (
            pd.to_numeric(frame["coverage_gap"], errors="coerce").fillna(0.0)
            * pd.to_numeric(frame["static_potential"], errors="coerce").fillna(0.0)
        ).to_numpy()
    else:
        blindspot = np.zeros(len(frame), dtype=float)

    return {
        "count_only_baseline": (
            pd.to_numeric(frame[count_column], errors="coerce").fillna(0.0).to_numpy()
            if count_column
            else np.zeros(len(frame), dtype=float)
        ),
        "historical_pfdi_baseline": (
            pd.to_numeric(frame[historical_column], errors="coerce").fillna(0.0).to_numpy()
            if historical_column
            else np.zeros(len(frame), dtype=float)
        ),
        "rule_blindspot_baseline": blindspot,
    }


def _comparison_table(
    *,
    model_scores: dict[str, np.ndarray],
    splits: dict[str, pd.DataFrame],
) -> list[dict[str, Any]]:
    """Build metrics rows for LightGBM and simple baselines."""

    rows: list[dict[str, Any]] = []
    for split_name, split_frame in splits.items():
        if split_name in model_scores:
            rows.append(
                _evaluate_rank_scores(
                    split_frame,
                    model_scores[split_name],
                    model_name="lightgbm_lambdarank",
                    split=split_name,
                )
            )
        for baseline_name, scores in _baseline_scores(split_frame).items():
            rows.append(
                _evaluate_rank_scores(
                    split_frame,
                    scores,
                    model_name=baseline_name,
                    split=split_name,
                )
            )
    return rows


def _save_feature_importance(model: Any, feature_columns: list[str], output_path: str | Path) -> pd.DataFrame:
    """Save LightGBM split and gain importance."""

    booster = model.booster_
    importance = pd.DataFrame(
        {
            "feature": feature_columns,
            "importance_split": booster.feature_importance(importance_type="split"),
            "importance_gain": booster.feature_importance(importance_type="gain"),
        }
    ).sort_values(["importance_gain", "importance_split"], ascending=False)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    importance.to_csv(destination, index=False)
    return importance


def train_lgbm_ranker(
    *,
    training_table_path: str | Path = MODEL_TRAINING_TABLE_PATH,
    graph_features_path: str | Path | None = GRAPH_FEATURES_PATH,
    deep_predictions_path: str | Path | None = DEEP_PREDICTIONS_PATH,
    model_output_path: str | Path = RANKER_MODEL_PATH,
    metrics_output_path: str | Path = RANKER_METRICS_PATH,
    feature_importance_output_path: str | Path = FEATURE_IMPORTANCE_PATH,
    config: RankerConfig = RankerConfig(),
) -> RankerArtifacts:
    """Train LightGBM LambdaRank and save model, metrics, and feature importance."""

    if lgb is None:
        raise ImportError("lightgbm is not installed. Install requirements.txt before training the ranker.")

    frame = load_ranker_frame(
        training_table_path,
        graph_features_path=graph_features_path,
        deep_predictions_path=deep_predictions_path,
    )
    train, val, test = chronological_rank_split(
        frame,
        train_fraction=config.train_fraction,
        val_fraction=config.val_fraction,
    )
    train = _sort_for_ranker(train)
    val = _sort_for_ranker(val)
    test = _sort_for_ranker(test)
    if not _has_rank_signal(train):
        raise ValueError(
            "Training split has no station-window group with at least two relevance levels. "
            "LambdaRank needs pairwise ranking signal."
        )

    feature_columns = infer_ranker_feature_columns(frame)
    X_train, X_val, X_test = _prepare_feature_matrix(train, val, test, feature_columns)
    y_train = train[TARGET_COLUMN].astype(int).to_numpy()
    y_val = val[TARGET_COLUMN].astype(int).to_numpy()
    y_test = test[TARGET_COLUMN].astype(int).to_numpy()
    train_group = _group_sizes(train)
    val_group = _group_sizes(val)
    test_group = _group_sizes(test)

    model = lgb.LGBMRanker(
        objective=config.objective,
        metric=config.metric,
        learning_rate=config.learning_rate,
        num_leaves=config.num_leaves,
        n_estimators=config.n_estimators,
        feature_fraction=config.feature_fraction,
        bagging_fraction=config.bagging_fraction,
        bagging_freq=config.bagging_freq,
        min_data_in_leaf=config.min_data_in_leaf,
        random_state=config.random_state,
        verbose=-1,
    )
    callbacks = [lgb.log_evaluation(period=50)]
    eval_set = None
    eval_group = None
    if not val.empty and val_group:
        eval_set = [(X_val, y_val)]
        eval_group = [val_group]
        callbacks.append(lgb.early_stopping(config.early_stopping_rounds, verbose=False))

    fit_kwargs: dict[str, Any] = {
        "X": X_train,
        "y": y_train,
        "group": train_group,
        "eval_at": list(config.ndcg_eval_at),
        "callbacks": callbacks,
    }
    if eval_set is not None and eval_group is not None:
        fit_kwargs["eval_set"] = eval_set
        fit_kwargs["eval_group"] = eval_group
    model.fit(**fit_kwargs)

    model_output_path = Path(model_output_path)
    metrics_output_path = Path(metrics_output_path)
    feature_importance_output_path = Path(feature_importance_output_path)
    model_output_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_output_path.parent.mkdir(parents=True, exist_ok=True)
    model.booster_.save_model(str(model_output_path))
    importance = _save_feature_importance(model, feature_columns, feature_importance_output_path)

    model_scores = {
        "train": model.predict(X_train),
        "val": model.predict(X_val) if not val.empty else np.array([], dtype=float),
        "test": model.predict(X_test) if not test.empty else np.array([], dtype=float),
    }
    splits = {"train": train, "val": val, "test": test}
    comparison = _comparison_table(model_scores=model_scores, splits=splits)
    metrics = {
        "model": "lightgbm_lambdarank",
        "config": asdict(config),
        "feature_columns": feature_columns,
        "feature_count": len(feature_columns),
        "row_counts": {name: int(len(split)) for name, split in splits.items()},
        "group_counts": {
            "train": len(train_group),
            "val": len(val_group),
            "test": len(test_group),
        },
        "best_iteration": int(getattr(model, "best_iteration_", 0) or config.n_estimators),
        "comparison_table": comparison,
        "top_features": importance.head(25).to_dict("records"),
    }
    metrics_output_path.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
    return RankerArtifacts(
        model_path=model_output_path,
        metrics_path=metrics_output_path,
        feature_importance_path=feature_importance_output_path,
        comparison_table=comparison,
    )
