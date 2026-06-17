"""Sequence tensor construction for BE-STHGT training and inference."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler


MODEL_TRAINING_TABLE_PATH = Path("data/processed/model_training_table.parquet")
SCALER_PATH = Path("artifacts/models/scaler.pkl")

TARGET_COLUMNS = {
    "next_count",
    "next_pfdi",
    "next_bias_corrected_pfdi",
    "next_hotspot",
    "next_relevance",
}
META_COLUMNS = {
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
}


@dataclass(frozen=True)
class SequenceConfig:
    """Configuration for chronological BE-STHGT sequence construction."""

    lookback_windows: int = 56
    horizon_windows: int = 1
    train_fraction: float = 0.70
    val_fraction: float = 0.15
    scaler_path: Path = SCALER_PATH


@dataclass
class SequenceSplit:
    """Tensor split plus metadata arrays."""

    X: np.ndarray
    y_count: np.ndarray
    y_pfdi: np.ndarray
    y_hotspot: np.ndarray
    y_q90_pfdi: np.ndarray
    y_rank_relevance: np.ndarray
    exposure_next: np.ndarray
    zero_weight_next: np.ndarray
    window_start: np.ndarray
    zone_ids: list[str]
    police_station_ids: np.ndarray
    rank_groups: np.ndarray


@dataclass
class SequenceBuildResult:
    """All chronological sequence splits and shared metadata."""

    train: SequenceSplit
    val: SequenceSplit
    test: SequenceSplit
    feature_columns: list[str]
    zone_ids: list[str]
    police_station_lookup: dict[str, int]
    scaler: StandardScaler


def infer_feature_columns(frame: pd.DataFrame) -> list[str]:
    """Infer numeric model feature columns while excluding targets and IDs."""

    excluded = TARGET_COLUMNS | META_COLUMNS | {"is_active_training_zone"}
    candidates = []
    for column in frame.columns:
        if column in excluded:
            continue
        if pd.api.types.is_bool_dtype(frame[column]) or pd.api.types.is_numeric_dtype(frame[column]):
            candidates.append(column)
    return sorted(candidates)


def _prepare_training_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Filter active rows and normalize key columns."""

    result = frame.copy()
    if "is_active_training_zone" in result.columns:
        result = result[result["is_active_training_zone"].fillna(False)].copy()
    if result.empty:
        raise ValueError("No active rows available for sequence dataset construction.")
    if "window_start" not in result.columns:
        raise ValueError("Sequence dataset requires window_start.")
    result["window_start"] = pd.to_datetime(result["window_start"], errors="coerce")
    result = result[result["window_start"].notna() & result["zone_id"].notna()].copy()
    result["zone_id"] = result["zone_id"].astype(str)
    if "police_station" not in result.columns:
        result["police_station"] = "unknown"
    result["police_station"] = result["police_station"].fillna("unknown").astype(str)
    return result.sort_values(["window_start", "zone_id"]).reset_index(drop=True)


def _chronological_split_counts(total_samples: int, train_fraction: float, val_fraction: float) -> tuple[int, int]:
    """Return train and validation counts for chronological sample splits."""

    if total_samples <= 0:
        return 0, 0
    train_count = int(total_samples * train_fraction)
    val_count = int(total_samples * val_fraction)
    if total_samples >= 3:
        train_count = max(1, train_count)
        val_count = max(1, val_count)
        if train_count + val_count >= total_samples:
            val_count = max(1, total_samples - train_count - 1)
    return train_count, val_count


def _fit_transform_features(
    panel: np.ndarray,
    train_sample_count: int,
    *,
    scaler_path: Path,
) -> tuple[np.ndarray, StandardScaler]:
    """Fit a StandardScaler on train samples only and transform the full panel."""

    scaler = StandardScaler()
    if train_sample_count <= 0:
        raise ValueError("At least one train sample is required to fit the scaler.")
    train_values = panel[:train_sample_count].reshape(-1, panel.shape[-1])
    scaler.fit(train_values)
    scaled = scaler.transform(panel.reshape(-1, panel.shape[-1])).reshape(panel.shape)
    scaler_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(scaler, scaler_path)
    return scaled.astype(np.float32), scaler


def _pivot_tensor(
    frame: pd.DataFrame,
    *,
    value_columns: list[str],
    windows: list[pd.Timestamp],
    zone_ids: list[str],
    fill_value: float = 0.0,
) -> np.ndarray:
    """Pivot value columns into [time, zone, feature] arrays."""

    arrays = []
    index = pd.MultiIndex.from_product([windows, zone_ids], names=["window_start", "zone_id"])
    for column in value_columns:
        values = (
            frame.set_index(["window_start", "zone_id"])[column]
            .reindex(index)
            .fillna(fill_value)
            .astype(float)
            .to_numpy()
            .reshape(len(windows), len(zone_ids))
        )
        arrays.append(values)
    return np.stack(arrays, axis=-1)


def _target_panel(frame: pd.DataFrame, column: str, windows: list[pd.Timestamp], zone_ids: list[str]) -> np.ndarray:
    return _pivot_tensor(
        frame,
        value_columns=[column],
        windows=windows,
        zone_ids=zone_ids,
        fill_value=0.0,
    )[:, :, 0]


def _build_split(
    *,
    X: np.ndarray,
    targets: dict[str, np.ndarray],
    sample_windows: np.ndarray,
    sample_indices: np.ndarray,
    zone_ids: list[str],
    police_station_ids: np.ndarray,
) -> SequenceSplit:
    """Slice arrays into one chronological split."""

    rank_groups = np.tile(police_station_ids, (len(sample_indices), 1))
    return SequenceSplit(
        X=X[sample_indices],
        y_count=targets["next_count"][sample_indices],
        y_pfdi=targets["next_pfdi"][sample_indices],
        y_hotspot=targets["next_hotspot"][sample_indices],
        y_q90_pfdi=targets["next_pfdi"][sample_indices],
        y_rank_relevance=targets["next_relevance"][sample_indices],
        exposure_next=targets["exposure_next"][sample_indices],
        zero_weight_next=targets["zero_weight_next"][sample_indices],
        window_start=sample_windows[sample_indices],
        zone_ids=zone_ids,
        police_station_ids=police_station_ids,
        rank_groups=rank_groups,
    )


def build_sequence_splits(
    frame: pd.DataFrame,
    *,
    config: SequenceConfig = SequenceConfig(),
    feature_columns: list[str] | None = None,
) -> SequenceBuildResult:
    """Build chronological train/val/test BE-STHGT sequence tensors."""

    table = _prepare_training_frame(frame)
    feature_columns = feature_columns or infer_feature_columns(table)
    if not feature_columns:
        raise ValueError("No numeric feature columns available for sequence construction.")

    zone_ids = sorted(table["zone_id"].unique())
    windows = sorted(table["window_start"].dropna().unique())
    if len(windows) < config.lookback_windows:
        raise ValueError("Not enough windows to build the requested lookback sequence.")

    feature_panel = _pivot_tensor(table, value_columns=feature_columns, windows=windows, zone_ids=zone_ids)
    target_columns = ["next_count", "next_pfdi", "next_hotspot", "next_relevance"]
    target_panels = {
        column: _target_panel(table, column, windows, zone_ids).astype(np.float32)
        for column in target_columns
    }
    target_panels["exposure_next"] = _target_panel(table, "exposure", windows, zone_ids).astype(np.float32)
    target_panels["zero_weight_next"] = _target_panel(
        table,
        "zero_window_weight",
        windows,
        zone_ids,
    ).astype(np.float32)

    end_indices = np.arange(config.lookback_windows - 1, len(windows), dtype=int)
    X = np.stack(
        [
            feature_panel[end_index - config.lookback_windows + 1 : end_index + 1]
            for end_index in end_indices
        ],
        axis=0,
    )
    sample_windows = np.array([pd.Timestamp(windows[end_index]) for end_index in end_indices], dtype=object)
    targets = {name: panel[end_indices] for name, panel in target_panels.items()}

    train_count, val_count = _chronological_split_counts(
        len(end_indices),
        config.train_fraction,
        config.val_fraction,
    )
    X_scaled, scaler = _fit_transform_features(X, train_count, scaler_path=config.scaler_path)

    station_by_zone = (
        table.sort_values("window_start")
        .groupby("zone_id")["police_station"]
        .agg(lambda values: values.mode().iloc[0] if not values.mode().empty else "unknown")
    )
    station_labels = sorted(station_by_zone.fillna("unknown").astype(str).unique())
    station_lookup = {station: idx for idx, station in enumerate(station_labels)}
    police_station_ids = np.array(
        [station_lookup[str(station_by_zone.get(zone_id, "unknown"))] for zone_id in zone_ids],
        dtype=np.int64,
    )

    train_indices = np.arange(0, train_count, dtype=int)
    val_indices = np.arange(train_count, train_count + val_count, dtype=int)
    test_indices = np.arange(train_count + val_count, len(end_indices), dtype=int)

    return SequenceBuildResult(
        train=_build_split(
            X=X_scaled,
            targets=targets,
            sample_windows=sample_windows,
            sample_indices=train_indices,
            zone_ids=zone_ids,
            police_station_ids=police_station_ids,
        ),
        val=_build_split(
            X=X_scaled,
            targets=targets,
            sample_windows=sample_windows,
            sample_indices=val_indices,
            zone_ids=zone_ids,
            police_station_ids=police_station_ids,
        ),
        test=_build_split(
            X=X_scaled,
            targets=targets,
            sample_windows=sample_windows,
            sample_indices=test_indices,
            zone_ids=zone_ids,
            police_station_ids=police_station_ids,
        ),
        feature_columns=feature_columns,
        zone_ids=zone_ids,
        police_station_lookup=station_lookup,
        scaler=scaler,
    )


def build_sequence_splits_from_parquet(
    path: str | Path = MODEL_TRAINING_TABLE_PATH,
    *,
    config: SequenceConfig = SequenceConfig(),
) -> SequenceBuildResult:
    """Read the model training table and build chronological sequence splits."""

    return build_sequence_splits(pd.read_parquet(path), config=config)
