"""Train optional benchmark rankers for CurbFlow model comparison.

This script is intended for a stronger Colab/GPU/CPU runtime after the
CurbFlow feature pipeline has produced data/processed/model_training_table.parquet.
It writes artifacts/metrics/model_benchmark_metrics.json, which the API can seed
and the Evidence Audit page can display.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from curbflow.features.training_table import MODEL_TRAINING_TABLE_PATH
from curbflow.graph.build_hetero_graph import GRAPH_FEATURES_PATH
from curbflow.ml.be_sthgt.trainer import DEEP_PREDICTIONS_PATH
from curbflow.ml.ranker.lgbm_ranker import (
    TARGET_COLUMN,
    RankerConfig,
    _baseline_scores,
    _evaluate_rank_scores,
    _group_sizes,
    _has_rank_signal,
    _prepare_feature_matrix,
    _sort_for_ranker,
    chronological_rank_split,
    infer_ranker_feature_columns,
    load_ranker_frame,
)

try:
    import lightgbm as lgb
except ImportError:  # pragma: no cover
    lgb = None

try:
    from catboost import CatBoostRanker, Pool
except ImportError:  # pragma: no cover
    CatBoostRanker = None
    Pool = None

try:
    from xgboost import XGBRanker
except ImportError:  # pragma: no cover
    XGBRanker = None


BENCHMARK_METRICS_PATH = Path("artifacts/metrics/model_benchmark_metrics.json")


def _evaluate_all_splits(
    *,
    model_name: str,
    splits: dict[str, pd.DataFrame],
    scores: dict[str, np.ndarray],
) -> list[dict[str, Any]]:
    """Evaluate a model on train/val/test splits with shared ranking metrics."""

    return [
        _evaluate_rank_scores(split_frame, scores.get(split_name, np.array([], dtype=float)), model_name=model_name, split=split_name)
        for split_name, split_frame in splits.items()
    ]


def _baseline_rows(splits: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    """Evaluate leakage-safe operational baselines."""

    rows: list[dict[str, Any]] = []
    for split_name, split_frame in splits.items():
        for baseline_name, scores in _baseline_scores(split_frame).items():
            rows.append(_evaluate_rank_scores(split_frame, scores, model_name=baseline_name, split=split_name))
    return rows


def _train_lightgbm(
    *,
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    X_val: pd.DataFrame,
    y_val: np.ndarray,
    train_group: list[int],
    val_group: list[int],
    config: RankerConfig,
    iterations: int,
) -> Any:
    """Train a LightGBM LambdaRank benchmark."""

    if lgb is None:
        raise ImportError("lightgbm is not installed.")
    model = lgb.LGBMRanker(
        objective=config.objective,
        metric=config.metric,
        learning_rate=config.learning_rate,
        num_leaves=config.num_leaves,
        n_estimators=iterations,
        feature_fraction=config.feature_fraction,
        bagging_fraction=config.bagging_fraction,
        bagging_freq=config.bagging_freq,
        min_data_in_leaf=config.min_data_in_leaf,
        random_state=config.random_state,
        verbose=-1,
    )
    fit_kwargs: dict[str, Any] = {
        "X": X_train,
        "y": y_train,
        "group": train_group,
        "eval_at": list(config.ndcg_eval_at),
        "callbacks": [lgb.log_evaluation(period=100)],
    }
    if len(X_val) and val_group:
        fit_kwargs["eval_set"] = [(X_val, y_val)]
        fit_kwargs["eval_group"] = [val_group]
        fit_kwargs["callbacks"].append(lgb.early_stopping(config.early_stopping_rounds, verbose=False))
    model.fit(**fit_kwargs)
    return model


def _train_catboost(
    *,
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    X_val: pd.DataFrame,
    y_val: np.ndarray,
    train: pd.DataFrame,
    val: pd.DataFrame,
    iterations: int,
    learning_rate: float,
) -> Any:
    """Train a CatBoost YetiRank benchmark."""

    if CatBoostRanker is None or Pool is None:
        raise ImportError("catboost is not installed.")
    train_pool = Pool(X_train, label=y_train, group_id=train["_rank_group"].astype(str).to_numpy())
    val_pool = Pool(X_val, label=y_val, group_id=val["_rank_group"].astype(str).to_numpy()) if len(X_val) else None
    model = CatBoostRanker(
        loss_function="YetiRank",
        eval_metric="NDCG:top=10",
        iterations=iterations,
        learning_rate=learning_rate,
        depth=8,
        random_seed=42,
        verbose=100,
    )
    if val_pool is not None:
        model.fit(train_pool, eval_set=val_pool, use_best_model=True)
    else:
        model.fit(train_pool)
    return model


def _train_xgboost(
    *,
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    X_val: pd.DataFrame,
    y_val: np.ndarray,
    train_group: list[int],
    val_group: list[int],
    iterations: int,
    learning_rate: float,
) -> Any:
    """Train an XGBoost NDCG ranker benchmark."""

    if XGBRanker is None:
        raise ImportError("xgboost is not installed.")
    model = XGBRanker(
        objective="rank:ndcg",
        eval_metric="ndcg@10",
        n_estimators=iterations,
        learning_rate=learning_rate,
        max_depth=6,
        subsample=0.85,
        colsample_bytree=0.85,
        random_state=42,
        tree_method="hist",
    )
    fit_kwargs: dict[str, Any] = {
        "X": X_train,
        "y": y_train,
        "group": train_group,
        "verbose": True,
    }
    if len(X_val) and val_group:
        fit_kwargs["eval_set"] = [(X_val, y_val)]
        fit_kwargs["eval_group"] = [val_group]
    model.fit(**fit_kwargs)
    return model


def main() -> None:
    """Train benchmark rankers and save a single metrics JSON artifact."""

    parser = argparse.ArgumentParser(description="Train CurbFlow benchmark ranking models.")
    parser.add_argument("--training-table", default=str(MODEL_TRAINING_TABLE_PATH))
    parser.add_argument("--graph-features", default=str(GRAPH_FEATURES_PATH))
    parser.add_argument("--deep-predictions", default=str(DEEP_PREDICTIONS_PATH))
    parser.add_argument("--output", default=str(BENCHMARK_METRICS_PATH))
    parser.add_argument("--models", default="lightgbm,catboost,xgboost", help="Comma-separated: lightgbm,catboost,xgboost")
    parser.add_argument("--iterations", type=int, default=800)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--strict", action="store_true", help="Fail if any requested model cannot train.")
    args = parser.parse_args()

    frame = load_ranker_frame(
        args.training_table,
        graph_features_path=args.graph_features,
        deep_predictions_path=args.deep_predictions,
    )
    train, val, test = chronological_rank_split(frame)
    train = _sort_for_ranker(train)
    val = _sort_for_ranker(val)
    test = _sort_for_ranker(test)
    if not _has_rank_signal(train):
        raise SystemExit("Training split has no ranking signal. Run the full feature pipeline first.")

    feature_columns = infer_ranker_feature_columns(frame)
    X_train, X_val, X_test = _prepare_feature_matrix(train, val, test, feature_columns)
    y_train = train[TARGET_COLUMN].astype(int).to_numpy()
    y_val = val[TARGET_COLUMN].astype(int).to_numpy()
    y_test = test[TARGET_COLUMN].astype(int).to_numpy()
    train_group = _group_sizes(train)
    val_group = _group_sizes(val)

    splits = {"train": train, "val": val, "test": test}
    comparison_rows = _baseline_rows(splits)
    failures: dict[str, str] = {}
    requested_models = {model.strip().lower() for model in args.models.split(",") if model.strip()}
    config = RankerConfig(learning_rate=args.learning_rate, n_estimators=args.iterations)

    trainers = {
        "lightgbm": (
            "lightgbm_lambdarank",
            lambda: _train_lightgbm(
                X_train=X_train,
                y_train=y_train,
                X_val=X_val,
                y_val=y_val,
                train_group=train_group,
                val_group=val_group,
                config=config,
                iterations=args.iterations,
            ),
        ),
        "catboost": (
            "catboost_yetirank",
            lambda: _train_catboost(
                X_train=X_train,
                y_train=y_train,
                X_val=X_val,
                y_val=y_val,
                train=train,
                val=val,
                iterations=args.iterations,
                learning_rate=args.learning_rate,
            ),
        ),
        "xgboost": (
            "xgboost_ndcg_ranker",
            lambda: _train_xgboost(
                X_train=X_train,
                y_train=y_train,
                X_val=X_val,
                y_val=y_val,
                train_group=train_group,
                val_group=val_group,
                iterations=args.iterations,
                learning_rate=args.learning_rate,
            ),
        ),
    }

    for key, (model_name, trainer) in trainers.items():
        if key not in requested_models:
            continue
        try:
            model = trainer()
            scores = {
                "train": np.asarray(model.predict(X_train), dtype=float),
                "val": np.asarray(model.predict(X_val), dtype=float) if len(X_val) else np.array([], dtype=float),
                "test": np.asarray(model.predict(X_test), dtype=float) if len(X_test) else np.array([], dtype=float),
            }
            comparison_rows.extend(_evaluate_all_splits(model_name=model_name, splits=splits, scores=scores))
        except Exception as exc:  # pragma: no cover - depends on optional packages/runtime.
            failures[key] = str(exc)
            if args.strict:
                raise
            print(f"Skipped {key}: {exc}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": "curbflow_model_benchmark",
        "config": {
            **asdict(config),
            "models": sorted(requested_models),
            "strict": bool(args.strict),
        },
        "feature_count": len(feature_columns),
        "feature_columns": feature_columns,
        "row_counts": {name: int(len(split)) for name, split in splits.items()},
        "group_counts": {name: int(split["_rank_group"].nunique()) for name, split in splits.items()},
        "comparison_table": comparison_rows,
        "failures": failures,
    }
    output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(pd.DataFrame(comparison_rows).to_string(index=False))
    print(f"Wrote benchmark metrics to {output}")
    if failures:
        print("Failures:")
        for model_name, message in failures.items():
            print(f"- {model_name}: {message}")


if __name__ == "__main__":
    main()
