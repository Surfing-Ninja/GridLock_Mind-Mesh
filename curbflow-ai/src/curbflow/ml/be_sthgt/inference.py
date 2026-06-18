"""BE-STHGT inference utilities for prediction artifact generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import torch

from curbflow.features.sequence_dataset import (
    MODEL_TRAINING_TABLE_PATH,
    SequenceBuildResult,
    SequenceConfig,
    build_sequence_splits,
)
from curbflow.graph.build_hetero_graph import ADJACENCY_OUTPUT_DIR
from curbflow.ml.be_sthgt.model import BESTHGT, BESTHGTConfig
from curbflow.ml.be_sthgt.trainer import (
    DEEP_PREDICTIONS_PATH,
    MODEL_OUTPUT_PATH,
    _baseline_lookup,
    _load_adjacencies,
    _make_loader,
    _validate_adjacency_shapes,
    predict_split,
)


def _torch_load_checkpoint(path: Path, device: torch.device) -> dict[str, Any]:
    """Load a checkpoint across PyTorch versions."""

    try:
        return torch.load(path, map_location=device, weights_only=False)
    except TypeError:
        return torch.load(path, map_location=device)


def generate_be_sthgt_predictions(
    *,
    training_table_path: str | Path = MODEL_TRAINING_TABLE_PATH,
    model_path: str | Path = MODEL_OUTPUT_PATH,
    adjacency_dir: str | Path = ADJACENCY_OUTPUT_DIR,
    output_path: str | Path = DEEP_PREDICTIONS_PATH,
    batch_size: int = 8,
    device: str | None = None,
) -> pd.DataFrame:
    """Run a saved BE-STHGT checkpoint and write deep prediction features."""

    table_path = Path(training_table_path)
    checkpoint_path = Path(model_path)
    if not table_path.exists():
        raise FileNotFoundError(f"Training table not found: {table_path}. Run `make features` first.")
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"BE-STHGT checkpoint not found: {checkpoint_path}. Run `make train-deep` first.")

    torch_device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    checkpoint = _torch_load_checkpoint(checkpoint_path, torch_device)
    model_config = BESTHGTConfig(**checkpoint["model_config"])
    feature_columns = [str(column) for column in checkpoint.get("feature_columns", [])]
    if not feature_columns:
        raise ValueError(f"Checkpoint at {checkpoint_path} does not include feature_columns.")

    table = pd.read_parquet(table_path)
    for column in feature_columns:
        if column not in table.columns:
            table[column] = 0.0
    sequence_config = SequenceConfig(
        lookback_windows=model_config.lookback_windows,
        train_fraction=float(checkpoint.get("training_config", {}).get("train_fraction", 0.70)),
        val_fraction=float(checkpoint.get("training_config", {}).get("val_fraction", 0.15)),
    )
    splits: SequenceBuildResult = build_sequence_splits(
        table,
        config=sequence_config,
        feature_columns=feature_columns,
    )
    adjacencies = _load_adjacencies(adjacency_dir, device=torch_device)
    _validate_adjacency_shapes(adjacencies, len(splits.zone_ids))

    model = BESTHGT(model_config).to(torch_device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    baseline_table = _baseline_lookup(table_path)
    prediction_frames = []
    for split_name, split in (("train", splits.train), ("val", splits.val), ("test", splits.test)):
        loader = _make_loader(split, batch_size=batch_size, shuffle=False)
        prediction_frames.append(
            predict_split(
                model,
                split_name,
                split,
                loader=loader,
                adjacencies=adjacencies,
                device=torch_device,
                baseline_table=baseline_table,
            )
        )
    predictions = pd.concat(
        [frame for frame in prediction_frames if not frame.empty],
        ignore_index=True,
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_parquet(destination, index=False)
    return predictions


def load_or_generate_be_sthgt_predictions(
    *,
    training_table_path: str | Path = MODEL_TRAINING_TABLE_PATH,
    model_path: str | Path = MODEL_OUTPUT_PATH,
    adjacency_dir: str | Path = ADJACENCY_OUTPUT_DIR,
    predictions_path: str | Path = DEEP_PREDICTIONS_PATH,
    batch_size: int = 8,
    device: str | None = None,
    force: bool = False,
) -> pd.DataFrame | None:
    """Load existing deep predictions or generate them when a checkpoint exists."""

    prediction_file = Path(predictions_path)
    if prediction_file.exists() and not force:
        return pd.read_parquet(prediction_file)
    if not Path(model_path).exists():
        return None
    return generate_be_sthgt_predictions(
        training_table_path=training_table_path,
        model_path=model_path,
        adjacency_dir=adjacency_dir,
        output_path=predictions_path,
        batch_size=batch_size,
        device=device,
    )
