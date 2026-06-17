"""Adjacency matrix utilities for BE-STHGT graph inputs."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


ADJACENCY_DIR = Path("artifacts/models/adjacency_matrices")


def active_zone_ids(frame: pd.DataFrame, *, active_zone_min_records: int = 100) -> list[str]:
    """Return active zone IDs from a feature or row table."""

    if "is_active_training_zone" in frame.columns:
        zones = frame.loc[frame["is_active_training_zone"].fillna(False), "zone_id"]
        if not zones.empty:
            return sorted(zones.astype(str).unique())
    if "active_zone_record_count" in frame.columns:
        zones = frame.loc[
            pd.to_numeric(frame["active_zone_record_count"], errors="coerce").fillna(0)
            >= active_zone_min_records,
            "zone_id",
        ]
        if not zones.empty:
            return sorted(zones.astype(str).unique())
    if "record_count" in frame.columns:
        counts = frame.groupby("zone_id", dropna=False)["record_count"].sum()
        zones = counts[counts >= active_zone_min_records].index.astype(str)
        if len(zones):
            return sorted(zones)
    return sorted(frame["zone_id"].dropna().astype(str).unique())


def edges_to_adjacency(
    edges: pd.DataFrame,
    zone_ids: list[str],
    *,
    weight_column: str = "weight",
) -> np.ndarray:
    """Convert aggregate edges into a dense active-zone adjacency matrix."""

    index = {zone_id: position for position, zone_id in enumerate(zone_ids)}
    matrix = np.zeros((len(zone_ids), len(zone_ids)), dtype=np.float32)
    if edges.empty:
        return matrix
    for _, edge in edges.iterrows():
        from_zone = str(edge.get("from_zone_id"))
        to_zone = str(edge.get("to_zone_id"))
        if from_zone not in index or to_zone not in index:
            continue
        weight = float(edge.get(weight_column, 0.0))
        if np.isnan(weight):
            continue
        matrix[index[from_zone], index[to_zone]] = weight
    return matrix


def save_adjacency_matrices(
    matrices: dict[str, np.ndarray],
    output_dir: str | Path = ADJACENCY_DIR,
) -> dict[str, Path]:
    """Save adjacency matrices as .npy files."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    saved: dict[str, Path] = {}
    for name, matrix in matrices.items():
        path = destination / f"{name}.npy"
        np.save(path, matrix)
        saved[name] = path
    return saved
