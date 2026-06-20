"""Build repeat-vehicle graph relations without future leakage."""

from __future__ import annotations

import pandas as pd

from curbflow.features.novel_features import add_repeat_vehicle_features


def _repeat_vehicle_sets(frame: pd.DataFrame) -> dict[str, set[str]]:
    """Return repeated anonymized vehicles observed per zone."""

    work = frame.copy()
    if "anonymized_vehicle_id" not in work.columns or "repeat_vehicle_flag" not in work.columns:
        if {"vehicle_number", "created_datetime_ist"}.issubset(work.columns):
            work = add_repeat_vehicle_features(work)
        else:
            return {}
    work = work[work["repeat_vehicle_flag"].fillna(False) & work["anonymized_vehicle_id"].notna()]
    return {
        str(zone): set(group["anonymized_vehicle_id"].astype(str))
        for zone, group in work.groupby("zone_id", dropna=False)
    }


def build_vehicle_graph_edges(frame: pd.DataFrame) -> pd.DataFrame:
    """Connect zones that share repeated anonymized vehicles."""

    vehicle_sets = _repeat_vehicle_sets(frame)
    zones = sorted(vehicle_sets)
    records: list[dict[str, object]] = []
    for from_zone in zones:
        for to_zone in zones:
            if from_zone == to_zone:
                continue
            shared = vehicle_sets[from_zone] & vehicle_sets[to_zone]
            union = vehicle_sets[from_zone] | vehicle_sets[to_zone]
            if not shared or not union:
                continue
            records.append(
                {
                    "edge_type": "repeat_vehicle_zone_overlap",
                    "from_zone_id": from_zone,
                    "to_zone_id": to_zone,
                    "weight": len(shared) / len(union),
                    "shared_repeat_vehicle_count": len(shared),
                    "union_repeat_vehicle_count": len(union),
                }
            )
    return pd.DataFrame(
        records,
        columns=[
            "edge_type",
            "from_zone_id",
            "to_zone_id",
            "weight",
            "shared_repeat_vehicle_count",
            "union_repeat_vehicle_count",
        ],
    )
