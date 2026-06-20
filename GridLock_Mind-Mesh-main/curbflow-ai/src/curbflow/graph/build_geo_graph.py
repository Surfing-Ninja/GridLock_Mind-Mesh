"""Build geographic adjacency graphs between nearby zones."""

from __future__ import annotations

import math

import pandas as pd

from curbflow.graph.build_patrol_graph import _haversine_m, compute_zone_centroids


def build_geo_graph_edges(
    frame: pd.DataFrame,
    *,
    min_distance_m: float = 0.0,
    max_distance_m: float = 700.0,
    sigma_m: float = 500.0,
) -> pd.DataFrame:
    """Connect zones whose centroids are within the configured distance range."""

    centroids = compute_zone_centroids(frame)
    records: list[dict[str, object]] = []
    for left_index, left in centroids.iterrows():
        for right_index, right in centroids.iterrows():
            if left_index == right_index:
                continue
            distance_m = _haversine_m(
                float(left["zone_centroid_lat"]),
                float(left["zone_centroid_lon"]),
                float(right["zone_centroid_lat"]),
                float(right["zone_centroid_lon"]),
            )
            if min_distance_m <= distance_m <= max_distance_m:
                records.append(
                    {
                        "edge_type": "zone_near_zone",
                        "from_zone_id": str(left["zone_id"]),
                        "to_zone_id": str(right["zone_id"]),
                        "weight": math.exp(-distance_m / sigma_m),
                        "distance_m": distance_m,
                    }
                )
    return pd.DataFrame(
        records,
        columns=["edge_type", "from_zone_id", "to_zone_id", "weight", "distance_m"],
    )
