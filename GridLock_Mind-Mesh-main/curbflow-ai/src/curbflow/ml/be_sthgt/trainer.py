"""Training loop for BE-STHGT with chronological validation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader

from curbflow.features.sequence_dataset import (
    MODEL_TRAINING_TABLE_PATH,
    SequenceBuildResult,
    SequenceConfig,
    SequenceSplit,
    build_sequence_splits_from_parquet,
)
from curbflow.graph.build_hetero_graph import ADJACENCY_OUTPUT_DIR
from curbflow.ml.be_sthgt.graph_layers import DEFAULT_RELATIONS
from curbflow.ml.be_sthgt.model import BESTHGT, BESTHGTConfig
from curbflow.ml.datasets import CurbFlowSequenceDataset
from curbflow.ml.losses import BESTHGTTotalLoss, LossWeights
from curbflow.ml.metrics import (
    hotspot_auc,
    mae_pfdi,
    ndcg_at_k,
    precision_at_k,
    station_wise_precision_at_k,
    wape_count,
)


MODEL_OUTPUT_PATH = Path("artifacts/models/be_sthgt_model.pt")
MODEL_METADATA_PATH = Path("artifacts/models/model_metadata.json")
DEEP_METRICS_PATH = Path("artifacts/metrics/deep_metrics.json")
DEEP_PREDICTIONS_PATH = Path("data/processed/deep_predictions.parquet")


@dataclass(frozen=True)
class DeepTrainingConfig:
    """Runtime configuration for BE-STHGT training."""

    hidden_dim: int = 128
    graph_layers: int = 2
    temporal_layers: int = 3
    attention_heads: int = 4
    dropout: float = 0.15
    lookback_windows: int = 56
    horizon_windows: int = 1
    batch_size: int = 8
    epochs: int = 80
    learning_rate: float = 0.0007
    weight_decay: float = 0.0001
    grad_clip_norm: float = 1.0
    patience: int = 10
    min_delta: float = 1e-5
    early_stopping_metric: str = "ndcg_at_10"
    train_fraction: float = 0.70
    val_fraction: float = 0.15
    device: str | None = None
    loss_weights: LossWeights = field(default_factory=LossWeights)


@dataclass
class TrainingResult:
    """Saved artifact paths and training metrics."""

    model_path: Path
    metadata_path: Path
    metrics_path: Path
    predictions_path: Path
    best_epoch: int
    best_validation_loss: float
    best_validation_ndcg_at_10: float


def _collate_batch(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Collate tensor fields while preserving metadata lists."""

    if not samples:
        raise ValueError("Cannot collate an empty batch.")
    tensor_keys = {
        "X",
        "y_count",
        "y_pfdi",
        "y_hotspot",
        "y_q90_pfdi",
        "y_rank_relevance",
        "exposure_next",
        "zero_weight_next",
        "rank_groups",
        "police_station_ids",
    }
    batch: dict[str, Any] = {}
    for key in tensor_keys:
        batch[key] = torch.stack([sample[key] for sample in samples], dim=0)
    batch["window_start"] = [sample["window_start"] for sample in samples]
    batch["zone_ids"] = samples[0]["zone_ids"]
    return batch


def _require_finite(name: str, tensor: torch.Tensor) -> None:
    """Raise a useful error when tensors contain NaN or infinity."""

    if tensor.device.type == "mps":
        return
    if not torch.isfinite(tensor).all():
        bad_count = int((~torch.isfinite(tensor)).sum().detach().cpu().item())
        raise FloatingPointError(f"{name} contains {bad_count} non-finite values.")


def _move_targets(batch: dict[str, Any], device: torch.device) -> dict[str, torch.Tensor]:
    """Move target tensors to the training device."""

    return {
        "y_count": batch["y_count"].to(device),
        "y_pfdi": batch["y_pfdi"].to(device),
        "y_hotspot": batch["y_hotspot"].to(device),
        "y_q90_pfdi": batch["y_q90_pfdi"].to(device),
        "y_rank_relevance": batch["y_rank_relevance"].to(device),
        "zero_weight_next": batch["zero_weight_next"].to(device),
    }


def _load_adjacencies(
    adjacency_dir: str | Path = ADJACENCY_OUTPUT_DIR,
    *,
    device: torch.device,
) -> dict[str, torch.Tensor]:
    """Load the five BE-STHGT adjacency matrices from disk."""

    adjacency_path = Path(adjacency_dir)
    matrices: dict[str, torch.Tensor] = {}
    expected = {
        "geo": "A_geo.npy",
        "station": "A_station.npy",
        "pattern": "A_pattern.npy",
        "vehicle": "A_vehicle.npy",
        "patrol": "A_patrol.npy",
    }
    missing = [name for name in expected.values() if not (adjacency_path / name).exists()]
    if missing:
        raise FileNotFoundError(
            "Missing adjacency matrices in "
            f"{adjacency_path}: {', '.join(missing)}. Run `make graph` first."
        )
    for relation_name, filename in expected.items():
        values = np.load(adjacency_path / filename)
        if values.ndim != 2 or values.shape[0] != values.shape[1]:
            raise ValueError(f"{filename} must be a square adjacency matrix.")
        if not np.isfinite(values).all():
            raise ValueError(f"{filename} contains NaN or infinity.")
        matrices[relation_name] = torch.as_tensor(values, dtype=torch.float32, device=device)
    return matrices


def _validate_adjacency_shapes(adjacencies: dict[str, torch.Tensor], num_zones: int) -> None:
    """Ensure every relation matches the active-zone tensor shape."""

    for relation_name in DEFAULT_RELATIONS:
        if relation_name not in adjacencies:
            raise ValueError(f"Missing adjacency relation: {relation_name}")
        shape = tuple(adjacencies[relation_name].shape)
        if shape != (num_zones, num_zones):
            raise ValueError(
                f"Adjacency {relation_name} has shape {shape}, expected {(num_zones, num_zones)}. "
                "Rebuild graph artifacts after regenerating the training table."
            )


def _make_loader(split: SequenceSplit, *, batch_size: int, shuffle: bool = False) -> DataLoader:
    """Create a robust small-batch DataLoader for one split."""

    return DataLoader(
        CurbFlowSequenceDataset(split),
        batch_size=max(1, int(batch_size)),
        shuffle=shuffle,
        num_workers=0,
        collate_fn=_collate_batch,
    )


def _aggregate_tensor(values: list[torch.Tensor]) -> torch.Tensor:
    if not values:
        return torch.empty(0)
    return torch.cat([value.detach().cpu() for value in values], dim=0)


def _metrics_from_arrays(
    *,
    pred_pfdi: torch.Tensor,
    count_mu: torch.Tensor,
    hotspot_prob: torch.Tensor,
    rank_score: torch.Tensor,
    target_pfdi: torch.Tensor,
    target_count: torch.Tensor,
    target_hotspot: torch.Tensor,
    relevance: torch.Tensor,
    station_ids: torch.Tensor,
    total_loss: float,
    component_losses: dict[str, float],
) -> dict[str, Any]:
    """Compute scalar metrics for one split."""

    metrics: dict[str, Any] = {
        "total_loss": float(total_loss),
        "mae_pfdi": mae_pfdi(pred_pfdi, target_pfdi),
        "wape_count": wape_count(count_mu, target_count),
        "precision_at_5": precision_at_k(rank_score, target_hotspot, k=5),
        "precision_at_10": precision_at_k(rank_score, target_hotspot, k=10),
        "ndcg_at_5": ndcg_at_k(rank_score, relevance, k=5),
        "ndcg_at_10": ndcg_at_k(rank_score, relevance, k=10),
        "station_wise_precision_at_5": station_wise_precision_at_k(
            rank_score,
            target_hotspot,
            station_ids,
            k=5,
        ),
        "hotspot_auc": hotspot_auc(hotspot_prob, target_hotspot),
    }
    metrics.update({f"loss_{name}": float(value) for name, value in component_losses.items()})
    return metrics


def evaluate_model(
    model: BESTHGT,
    loader: DataLoader,
    *,
    criterion: BESTHGTTotalLoss,
    adjacencies: dict[str, torch.Tensor],
    device: torch.device,
) -> dict[str, Any]:
    """Evaluate one chronological split."""

    model.eval()
    if len(loader.dataset) == 0:
        return {
            "total_loss": float("nan"),
            "ndcg_at_10": 0.0,
            "mae_pfdi": float("nan"),
            "wape_count": float("nan"),
        }

    total_weighted_loss = 0.0
    total_samples = 0
    component_sums: dict[str, float] = {}
    collected: dict[str, list[torch.Tensor]] = {
        "pred_pfdi": [],
        "count_mu": [],
        "hotspot_prob": [],
        "rank_score": [],
        "target_pfdi": [],
        "target_count": [],
        "target_hotspot": [],
        "relevance": [],
        "station_ids": [],
    }
    with torch.no_grad():
        for batch in loader:
            X = batch["X"].to(device)
            exposure_next = batch["exposure_next"].to(device)
            _require_finite("validation X", X)
            outputs = model(X, adjacencies, exposure_next=exposure_next)
            for name, value in outputs.items():
                _require_finite(f"validation output {name}", value)
            targets = _move_targets(batch, device)
            loss_output = criterion(
                outputs,
                targets,
                rank_groups=batch["rank_groups"].to(device),
                A_geo=adjacencies["geo"],
            )
            _require_finite("validation loss", loss_output.loss)
            batch_size = int(X.shape[0])
            total_weighted_loss += float(loss_output.loss.detach().cpu().item()) * batch_size
            total_samples += batch_size
            for name, value in loss_output.components.items():
                component_sums[name] = component_sums.get(name, 0.0) + float(value.detach().cpu().item()) * batch_size

            collected["pred_pfdi"].append(outputs["pred_pfdi"])
            collected["count_mu"].append(outputs["count_mu"])
            collected["hotspot_prob"].append(outputs["hotspot_prob"])
            collected["rank_score"].append(outputs["rank_score"])
            collected["target_pfdi"].append(targets["y_pfdi"])
            collected["target_count"].append(targets["y_count"])
            collected["target_hotspot"].append(targets["y_hotspot"])
            collected["relevance"].append(targets["y_rank_relevance"])
            collected["station_ids"].append(batch["rank_groups"])

    averaged_components = {
        name: value / max(total_samples, 1) for name, value in component_sums.items()
    }
    return _metrics_from_arrays(
        pred_pfdi=_aggregate_tensor(collected["pred_pfdi"]),
        count_mu=_aggregate_tensor(collected["count_mu"]),
        hotspot_prob=_aggregate_tensor(collected["hotspot_prob"]),
        rank_score=_aggregate_tensor(collected["rank_score"]),
        target_pfdi=_aggregate_tensor(collected["target_pfdi"]),
        target_count=_aggregate_tensor(collected["target_count"]),
        target_hotspot=_aggregate_tensor(collected["target_hotspot"]),
        relevance=_aggregate_tensor(collected["relevance"]),
        station_ids=_aggregate_tensor(collected["station_ids"]),
        total_loss=total_weighted_loss / max(total_samples, 1),
        component_losses=averaged_components,
    )


def _baseline_lookup(training_table_path: str | Path) -> pd.DataFrame:
    """Read leakage-safe baseline columns keyed by current zone-window."""

    table = pd.read_parquet(training_table_path)
    required = ["zone_id", "window_start"]
    missing = [column for column in required if column not in table.columns]
    if missing:
        raise ValueError(f"Training table missing baseline key columns: {', '.join(missing)}")
    result = table[required].copy()
    result["window_start"] = pd.to_datetime(result["window_start"], errors="coerce")
    result["zone_id"] = result["zone_id"].astype(str)

    historical_candidates = [
        "same_slot_21d_avg_pfdi",
        "same_slot_7d_avg_pfdi",
        "rolling_21d_pfdi",
        "rolling_7d_pfdi",
    ]
    historical = next((column for column in historical_candidates if column in table.columns), None)
    result["baseline_historical_same_slot_pfdi"] = (
        pd.to_numeric(table[historical], errors="coerce").fillna(0.0) if historical else 0.0
    )
    result["baseline_last_week_same_slot_pfdi"] = (
        pd.to_numeric(table["lag_56_pfdi"], errors="coerce").fillna(0.0)
        if "lag_56_pfdi" in table.columns
        else 0.0
    )
    return result.drop_duplicates(["zone_id", "window_start"], keep="last").reset_index(drop=True)


def predict_split(
    model: BESTHGT,
    split_name: str,
    split: SequenceSplit,
    *,
    loader: DataLoader,
    adjacencies: dict[str, torch.Tensor],
    device: torch.device,
    baseline_table: pd.DataFrame,
) -> pd.DataFrame:
    """Generate one row per split-window-zone prediction."""

    model.eval()
    records: list[pd.DataFrame] = []
    zone_ids = list(split.zone_ids)
    with torch.no_grad():
        for batch in loader:
            X = batch["X"].to(device)
            exposure_next = batch["exposure_next"].to(device)
            outputs = model(X, adjacencies, exposure_next=exposure_next)
            batch_size, num_zones = outputs["pred_pfdi"].shape
            for batch_index in range(batch_size):
                window_start = pd.Timestamp(batch["window_start"][batch_index])
                records.append(
                    pd.DataFrame(
                        {
                            "split": split_name,
                            "window_start": window_start,
                            "zone_id": zone_ids,
                            "police_station_id": batch["rank_groups"][batch_index].cpu().numpy(),
                            "pred_latent_risk": outputs["latent_risk"][batch_index].cpu().numpy(),
                            "pred_count_mu": outputs["count_mu"][batch_index].cpu().numpy(),
                            "pred_count_theta": outputs["count_theta"][batch_index].cpu().numpy(),
                            "pred_pfdi": outputs["pred_pfdi"][batch_index].cpu().numpy(),
                            "pred_hotspot_prob": outputs["hotspot_prob"][batch_index].cpu().numpy(),
                            "pred_q90_pfdi": outputs["q90_pfdi"][batch_index].cpu().numpy(),
                            "pred_rank_score": outputs["rank_score"][batch_index].cpu().numpy(),
                            "pred_blindspot_score": outputs["blindspot_score"][batch_index].cpu().numpy(),
                            "target_count": batch["y_count"][batch_index].cpu().numpy(),
                            "target_pfdi": batch["y_pfdi"][batch_index].cpu().numpy(),
                            "target_hotspot": batch["y_hotspot"][batch_index].cpu().numpy(),
                            "target_relevance": batch["y_rank_relevance"][batch_index].cpu().numpy(),
                            "exposure_next": batch["exposure_next"][batch_index].cpu().numpy(),
                            "zero_weight_next": batch["zero_weight_next"][batch_index].cpu().numpy(),
                        }
                    )
                )
    if not records:
        return pd.DataFrame()
    predictions = pd.concat(records, ignore_index=True)
    predictions["zone_id"] = predictions["zone_id"].astype(str)
    predictions["window_start"] = pd.to_datetime(predictions["window_start"], errors="coerce")
    return predictions.merge(baseline_table, on=["zone_id", "window_start"], how="left")


def _baseline_metrics(predictions: pd.DataFrame) -> dict[str, float]:
    """Compute baseline PFDI MAE comparisons."""

    if predictions.empty:
        return {}
    return {
        "baseline_historical_same_slot_mae_pfdi": mae_pfdi(
            predictions["baseline_historical_same_slot_pfdi"].fillna(0.0),
            predictions["target_pfdi"],
        ),
        "baseline_last_week_same_slot_mae_pfdi": mae_pfdi(
            predictions["baseline_last_week_same_slot_pfdi"].fillna(0.0),
            predictions["target_pfdi"],
        ),
    }


def _score_for_early_stopping(metrics: dict[str, Any], config: DeepTrainingConfig) -> tuple[float, bool]:
    """Return comparable score and whether higher is better."""

    ndcg = metrics.get("ndcg_at_10")
    if config.early_stopping_metric == "ndcg_at_10" and ndcg is not None and np.isfinite(ndcg) and ndcg > 0:
        return float(ndcg), True
    loss = metrics.get("total_loss", float("inf"))
    return -float(loss), True


def train_be_sthgt(
    *,
    training_table_path: str | Path = MODEL_TRAINING_TABLE_PATH,
    adjacency_dir: str | Path = ADJACENCY_OUTPUT_DIR,
    model_output_path: str | Path = MODEL_OUTPUT_PATH,
    metadata_output_path: str | Path = MODEL_METADATA_PATH,
    metrics_output_path: str | Path = DEEP_METRICS_PATH,
    predictions_output_path: str | Path = DEEP_PREDICTIONS_PATH,
    config: DeepTrainingConfig = DeepTrainingConfig(),
) -> TrainingResult:
    """Train BE-STHGT, save best artifacts, and write split predictions."""

    training_table_path = Path(training_table_path)
    if not training_table_path.exists():
        raise FileNotFoundError(f"Training table not found: {training_table_path}. Run `make features` first.")

    device = torch.device(config.device or ("cuda" if torch.cuda.is_available() else "cpu"))
    print(f"Using device: {device}")
    sequence_config = SequenceConfig(
        lookback_windows=config.lookback_windows,
        horizon_windows=config.horizon_windows,
        train_fraction=config.train_fraction,
        val_fraction=config.val_fraction,
    )
    try:
        splits: SequenceBuildResult = build_sequence_splits_from_parquet(
            training_table_path,
            config=sequence_config,
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to load sequence dataset from {training_table_path}: {exc}") from exc

    if len(splits.train.X) == 0:
        raise ValueError("Training split is empty after chronological sequence construction.")

    adjacencies = _load_adjacencies(adjacency_dir, device=device)
    _validate_adjacency_shapes(adjacencies, len(splits.zone_ids))

    train_loader = _make_loader(splits.train, batch_size=config.batch_size, shuffle=False)
    val_loader = _make_loader(splits.val, batch_size=config.batch_size, shuffle=False)
    test_loader = _make_loader(splits.test, batch_size=config.batch_size, shuffle=False)

    model_config = BESTHGTConfig(
        input_dim=len(splits.feature_columns),
        num_zones=len(splits.zone_ids),
        hidden_dim=config.hidden_dim,
        graph_layers=config.graph_layers,
        temporal_layers=config.temporal_layers,
        attention_heads=config.attention_heads,
        dropout=config.dropout,
        lookback_windows=config.lookback_windows,
    )
    model = BESTHGT(model_config).to(device)
    criterion = BESTHGTTotalLoss(config.loss_weights)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )

    model_output_path = Path(model_output_path)
    metadata_output_path = Path(metadata_output_path)
    metrics_output_path = Path(metrics_output_path)
    predictions_output_path = Path(predictions_output_path)
    for path in (model_output_path, metadata_output_path, metrics_output_path, predictions_output_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    history: list[dict[str, Any]] = []
    best_score = -float("inf")
    best_epoch = 0
    best_val_loss = float("inf")
    best_val_ndcg = 0.0
    epochs_without_improvement = 0

    for epoch in range(1, config.epochs + 1):
        model.train()
        epoch_loss = 0.0
        epoch_samples = 0
        for step, batch in enumerate(train_loader, start=1):
            X = batch["X"].to(device)
            exposure_next = batch["exposure_next"].to(device)
            _require_finite("train X", X)
            optimizer.zero_grad(set_to_none=True)
            outputs = model(X, adjacencies, exposure_next=exposure_next)
            for name, value in outputs.items():
                _require_finite(f"train output {name}", value)
            targets = _move_targets(batch, device)
            loss_output = criterion(
                outputs,
                targets,
                rank_groups=batch["rank_groups"].to(device),
                A_geo=adjacencies["geo"],
            )
            _require_finite("train loss", loss_output.loss)
            loss_output.loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), config.grad_clip_norm)
            optimizer.step()

            batch_size = int(X.shape[0])
            epoch_loss += float(loss_output.loss.detach().cpu().item()) * batch_size
            epoch_samples += batch_size
            if step == 1 or step % 10 == 0:
                print(
                    f"epoch={epoch:03d} step={step:04d} "
                    f"train_loss={float(loss_output.loss.detach().cpu().item()):.5f}"
                )

        train_metrics = evaluate_model(
            model,
            train_loader,
            criterion=criterion,
            adjacencies=adjacencies,
            device=device,
        )
        val_metrics = evaluate_model(
            model,
            val_loader,
            criterion=criterion,
            adjacencies=adjacencies,
            device=device,
        )
        train_metrics["epoch_train_loss"] = epoch_loss / max(epoch_samples, 1)
        monitor_metrics = val_metrics
        if not np.isfinite(float(val_metrics.get("total_loss", float("nan")))):
            monitor_metrics = train_metrics
        score, higher_is_better = _score_for_early_stopping(monitor_metrics, config)
        improved = score > best_score + config.min_delta if higher_is_better else score < best_score - config.min_delta
        history.append({"epoch": epoch, "train": train_metrics, "val": val_metrics})
        print(
            f"epoch={epoch:03d} train_loss={train_metrics['total_loss']:.5f} "
            f"val_loss={val_metrics['total_loss']:.5f} val_ndcg@10={val_metrics.get('ndcg_at_10', 0.0):.5f}"
        )

        if improved:
            best_score = score
            best_epoch = epoch
            best_val_loss = float(val_metrics.get("total_loss", float("inf")))
            best_val_ndcg = float(val_metrics.get("ndcg_at_10", 0.0))
            epochs_without_improvement = 0
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "model_config": asdict(model_config),
                    "training_config": asdict(config),
                    "feature_columns": splits.feature_columns,
                    "zone_ids": splits.zone_ids,
                    "police_station_lookup": splits.police_station_lookup,
                    "best_epoch": best_epoch,
                },
                model_output_path,
            )
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= config.patience:
                print(f"Early stopping at epoch {epoch}; best_epoch={best_epoch}.")
                break

    if best_epoch == 0:
        raise RuntimeError("Training did not produce a valid checkpoint.")

    checkpoint = torch.load(model_output_path, map_location=device)
    model.load_state_dict(checkpoint["model_state_dict"])
    final_metrics = {
        "train": evaluate_model(model, train_loader, criterion=criterion, adjacencies=adjacencies, device=device),
        "val": evaluate_model(model, val_loader, criterion=criterion, adjacencies=adjacencies, device=device),
        "test": evaluate_model(model, test_loader, criterion=criterion, adjacencies=adjacencies, device=device),
        "history": history,
        "best_epoch": best_epoch,
        "device": str(device),
    }

    baseline_table = _baseline_lookup(training_table_path)
    prediction_frames = [
        predict_split(
            model,
            split_name,
            split,
            loader=loader,
            adjacencies=adjacencies,
            device=device,
            baseline_table=baseline_table,
        )
        for split_name, split, loader in (
            ("train", splits.train, train_loader),
            ("val", splits.val, val_loader),
            ("test", splits.test, test_loader),
        )
    ]
    predictions = pd.concat([frame for frame in prediction_frames if not frame.empty], ignore_index=True)
    predictions.to_parquet(predictions_output_path, index=False)
    for split_name in ("train", "val", "test"):
        split_predictions = predictions[predictions["split"] == split_name]
        final_metrics[split_name].update(_baseline_metrics(split_predictions))

    metadata = {
        "model": "BE-STHGT",
        "model_config": asdict(model_config),
        "training_config": asdict(config),
        "feature_columns": splits.feature_columns,
        "zone_ids": splits.zone_ids,
        "police_station_lookup": splits.police_station_lookup,
        "best_epoch": best_epoch,
        "artifact_paths": {
            "model": str(model_output_path),
            "metrics": str(metrics_output_path),
            "predictions": str(predictions_output_path),
            "adjacency_dir": str(adjacency_dir),
            "training_table": str(training_table_path),
        },
    }
    metadata_output_path.write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
    metrics_output_path.write_text(json.dumps(final_metrics, indent=2, default=str), encoding="utf-8")

    return TrainingResult(
        model_path=model_output_path,
        metadata_path=metadata_output_path,
        metrics_path=metrics_output_path,
        predictions_path=predictions_output_path,
        best_epoch=best_epoch,
        best_validation_loss=best_val_loss,
        best_validation_ndcg_at_10=best_val_ndcg,
    )
