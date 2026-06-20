"""Build graph relations from similar temporal and violation patterns."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _pfdi_column(frame: pd.DataFrame) -> str:
    for column in ("bias_corrected_pfdi", "observed_pfdi", "raw_impact"):
        if column in frame.columns:
            return column
    raise ValueError("Pattern graph requires a PFDI column.")


def build_zone_temporal_profiles(frame: pd.DataFrame) -> pd.DataFrame:
    """Create hourly/weekday PFDI profiles for each zone."""

    work = frame.copy()
    if "day_of_week" not in work.columns or "hour" not in work.columns:
        if "window_start" not in work.columns:
            raise ValueError("Pattern graph requires day/hour or window_start columns.")
        window_start = pd.to_datetime(work["window_start"], errors="coerce")
        work["day_of_week"] = window_start.dt.dayofweek
        work["hour"] = window_start.dt.hour
    pfdi = _pfdi_column(work)
    work["_slot"] = work["day_of_week"].astype("Int64").astype(str) + "_" + work["hour"].astype(
        "Int64"
    ).astype(str)
    return (
        work.pivot_table(index="zone_id", columns="_slot", values=pfdi, aggfunc="mean", fill_value=0.0)
        .sort_index()
        .astype(float)
    )


def build_pattern_graph_edges(frame: pd.DataFrame, *, top_k: int = 10) -> pd.DataFrame:
    """Connect zones with similar hourly/weekday PFDI profiles."""

    profiles = build_zone_temporal_profiles(frame)
    zones = profiles.index.astype(str).tolist()
    values = profiles.to_numpy(dtype=float)
    norms = np.linalg.norm(values, axis=1)
    records: list[dict[str, object]] = []
    for i, from_zone in enumerate(zones):
        similarities: list[tuple[str, float]] = []
        for j, to_zone in enumerate(zones):
            if i == j or norms[i] == 0 or norms[j] == 0:
                continue
            similarity = float(np.dot(values[i], values[j]) / (norms[i] * norms[j]))
            if similarity > 0:
                similarities.append((to_zone, similarity))
        for to_zone, similarity in sorted(similarities, key=lambda item: item[1], reverse=True)[:top_k]:
            records.append(
                {
                    "edge_type": "zone_temporal_pattern",
                    "from_zone_id": from_zone,
                    "to_zone_id": to_zone,
                    "weight": similarity,
                }
            )
    return pd.DataFrame(records, columns=["edge_type", "from_zone_id", "to_zone_id", "weight"])
