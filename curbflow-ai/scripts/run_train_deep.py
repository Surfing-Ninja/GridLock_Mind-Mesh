"""Train the BE-STHGT deep model with chronological splits."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from curbflow.features.sequence_dataset import MODEL_TRAINING_TABLE_PATH
from curbflow.graph.build_hetero_graph import ADJACENCY_OUTPUT_DIR
from curbflow.ml.be_sthgt.trainer import (
    DEEP_METRICS_PATH,
    DEEP_PREDICTIONS_PATH,
    MODEL_METADATA_PATH,
    MODEL_OUTPUT_PATH,
    DeepTrainingConfig,
    train_be_sthgt,
)
from curbflow.ml.losses import LossWeights


MODEL_CONFIG_PATH = Path("configs/model_config.yaml")


def _load_training_config(config_path: str | Path) -> DeepTrainingConfig:
    """Load BE-STHGT training settings from YAML."""

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Model config not found: {path}")
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    split_config = config.get("split", {})
    model_config = config.get("be_sthgt", {})
    loss_config = config.get("loss_weights", {})
    return DeepTrainingConfig(
        hidden_dim=int(model_config.get("hidden_dim", 128)),
        graph_layers=int(model_config.get("graph_layers", 2)),
        temporal_layers=int(model_config.get("temporal_layers", 3)),
        attention_heads=int(model_config.get("attention_heads", 4)),
        dropout=float(model_config.get("dropout", 0.15)),
        lookback_windows=int(model_config.get("lookback_windows", 56)),
        horizon_windows=int(model_config.get("horizon_windows", 1)),
        batch_size=int(model_config.get("batch_size", 8)),
        epochs=int(model_config.get("epochs", 80)),
        learning_rate=float(model_config.get("learning_rate", 0.0007)),
        train_fraction=float(split_config.get("train_fraction", 0.70)),
        val_fraction=float(split_config.get("validation_fraction", 0.15)),
        loss_weights=LossWeights(
            count=float(loss_config.get("count", 0.22)),
            pfdi=float(loss_config.get("pfdi", 0.20)),
            hotspot=float(loss_config.get("hotspot", 0.16)),
            rank=float(loss_config.get("ranking", loss_config.get("rank", 0.16))),
            q90=float(loss_config.get("q90", 0.10)),
            exposure_consistency=float(loss_config.get("exposure_consistency", 0.08)),
            spatial_smoothness=float(loss_config.get("spatial_smoothness", 0.08)),
        ),
    )


def _with_overrides(
    config: DeepTrainingConfig,
    *,
    epochs: int | None,
    batch_size: int | None,
    device: str | None,
    patience: int | None,
) -> DeepTrainingConfig:
    """Apply CLI overrides without mutating the config dataclass."""

    values = config.__dict__.copy()
    if epochs is not None:
        values["epochs"] = epochs
    if batch_size is not None:
        values["batch_size"] = batch_size
    if device is not None:
        values["device"] = device
    if patience is not None:
        values["patience"] = patience
    return DeepTrainingConfig(**values)


def main() -> None:
    """Train BE-STHGT and write model, metadata, metrics, and predictions."""

    parser = argparse.ArgumentParser(description="Train the CurbFlow BE-STHGT deep model.")
    parser.add_argument("--config", default=str(MODEL_CONFIG_PATH), help="Model YAML config path.")
    parser.add_argument(
        "--training-table",
        default=str(MODEL_TRAINING_TABLE_PATH),
        help="Input model training table parquet.",
    )
    parser.add_argument(
        "--adjacency-dir",
        default=str(ADJACENCY_OUTPUT_DIR),
        help="Directory containing A_geo/A_station/A_pattern/A_vehicle/A_patrol matrices.",
    )
    parser.add_argument("--model-output", default=str(MODEL_OUTPUT_PATH))
    parser.add_argument("--metadata-output", default=str(MODEL_METADATA_PATH))
    parser.add_argument("--metrics-output", default=str(DEEP_METRICS_PATH))
    parser.add_argument("--predictions-output", default=str(DEEP_PREDICTIONS_PATH))
    parser.add_argument("--epochs", type=int, default=None, help="Override YAML epoch count.")
    parser.add_argument("--batch-size", type=int, default=None, help="Override YAML batch size.")
    parser.add_argument(
        "--device",
        choices=["cpu", "cuda", "mps"],
        default=None,
        help="Override auto device selection.",
    )
    parser.add_argument("--patience", type=int, default=None, help="Early stopping patience.")
    args = parser.parse_args()

    try:
        config = _load_training_config(args.config)
        config = _with_overrides(
            config,
            epochs=args.epochs,
            batch_size=args.batch_size,
            device=args.device,
            patience=args.patience,
        )
        result = train_be_sthgt(
            training_table_path=args.training_table,
            adjacency_dir=args.adjacency_dir,
            model_output_path=args.model_output,
            metadata_output_path=args.metadata_output,
            metrics_output_path=args.metrics_output,
            predictions_output_path=args.predictions_output,
            config=config,
        )
    except Exception as exc:
        raise SystemExit(f"BE-STHGT training failed: {exc}") from exc

    print(f"Best epoch: {result.best_epoch}")
    print(f"Best validation loss: {result.best_validation_loss:.5f}")
    print(f"Best validation NDCG@10: {result.best_validation_ndcg_at_10:.5f}")
    print(f"Wrote model to {result.model_path}")
    print(f"Wrote metadata to {result.metadata_path}")
    print(f"Wrote metrics to {result.metrics_path}")
    print(f"Wrote predictions to {result.predictions_path}")


if __name__ == "__main__":
    main()
