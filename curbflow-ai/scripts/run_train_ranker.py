"""Train the LightGBM LambdaRank model for station-wise prioritization."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from curbflow.features.training_table import MODEL_TRAINING_TABLE_PATH
from curbflow.graph.build_hetero_graph import GRAPH_FEATURES_PATH
from curbflow.ml.be_sthgt.trainer import DEEP_PREDICTIONS_PATH
from curbflow.ml.ranker.lgbm_ranker import (
    FEATURE_IMPORTANCE_PATH,
    RANKER_METRICS_PATH,
    RANKER_MODEL_PATH,
    RankerConfig,
    train_lgbm_ranker,
)


MODEL_CONFIG_PATH = Path("configs/model_config.yaml")


def _load_ranker_config(config_path: str | Path) -> RankerConfig:
    """Load ranker and chronological split settings from YAML."""

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Model config not found: {path}")
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    split_config = config.get("split", {})
    ranker_config = config.get("ranker", {})
    return RankerConfig(
        train_fraction=float(split_config.get("train_fraction", 0.70)),
        val_fraction=float(split_config.get("validation_fraction", 0.15)),
        objective=str(ranker_config.get("objective", "lambdarank")),
        metric=str(ranker_config.get("metric", "ndcg")),
        ndcg_eval_at=tuple(ranker_config.get("ndcg_eval_at", [5, 10, 20])),
        learning_rate=float(ranker_config.get("learning_rate", 0.05)),
        num_leaves=int(ranker_config.get("num_leaves", 63)),
        n_estimators=int(ranker_config.get("n_estimators", 800)),
        feature_fraction=float(ranker_config.get("feature_fraction", 0.85)),
        bagging_fraction=float(ranker_config.get("bagging_fraction", 0.85)),
        bagging_freq=int(ranker_config.get("bagging_freq", 3)),
        min_data_in_leaf=int(ranker_config.get("min_data_in_leaf", 20)),
        early_stopping_rounds=int(ranker_config.get("early_stopping_rounds", 50)),
        random_state=int(ranker_config.get("random_state", 42)),
    )


def _with_overrides(
    config: RankerConfig,
    *,
    n_estimators: int | None,
    learning_rate: float | None,
) -> RankerConfig:
    values = config.__dict__.copy()
    if n_estimators is not None:
        values["n_estimators"] = n_estimators
    if learning_rate is not None:
        values["learning_rate"] = learning_rate
    return RankerConfig(**values)


def main() -> None:
    """Train the station-wise LambdaRank model."""

    parser = argparse.ArgumentParser(description="Train CurbFlow LightGBM LambdaRank.")
    parser.add_argument("--config", default=str(MODEL_CONFIG_PATH), help="Model YAML config path.")
    parser.add_argument("--training-table", default=str(MODEL_TRAINING_TABLE_PATH))
    parser.add_argument("--graph-features", default=str(GRAPH_FEATURES_PATH))
    parser.add_argument("--deep-predictions", default=str(DEEP_PREDICTIONS_PATH))
    parser.add_argument("--model-output", default=str(RANKER_MODEL_PATH))
    parser.add_argument("--metrics-output", default=str(RANKER_METRICS_PATH))
    parser.add_argument("--feature-importance-output", default=str(FEATURE_IMPORTANCE_PATH))
    parser.add_argument("--n-estimators", type=int, default=None, help="Override estimator count.")
    parser.add_argument("--learning-rate", type=float, default=None, help="Override learning rate.")
    parser.add_argument(
        "--no-graph-features",
        action="store_true",
        help="Train without optional graph feature join.",
    )
    parser.add_argument(
        "--no-deep-predictions",
        action="store_true",
        help="Train without optional BE-STHGT prediction join.",
    )
    args = parser.parse_args()

    try:
        config = _load_ranker_config(args.config)
        config = _with_overrides(
            config,
            n_estimators=args.n_estimators,
            learning_rate=args.learning_rate,
        )
        result = train_lgbm_ranker(
            training_table_path=args.training_table,
            graph_features_path=None if args.no_graph_features else args.graph_features,
            deep_predictions_path=None if args.no_deep_predictions else args.deep_predictions,
            model_output_path=args.model_output,
            metrics_output_path=args.metrics_output,
            feature_importance_output_path=args.feature_importance_output,
            config=config,
        )
    except Exception as exc:
        raise SystemExit(f"LightGBM ranker training failed: {exc}") from exc

    comparison = pd.DataFrame(result.comparison_table)
    print("Comparison table:")
    if comparison.empty:
        print("(no comparison rows)")
    else:
        print(comparison.to_string(index=False))
    print(f"Wrote model to {result.model_path}")
    print(f"Wrote metrics to {result.metrics_path}")
    print(f"Wrote feature importance to {result.feature_importance_path}")


if __name__ == "__main__":
    main()
