"""Assemble heterogeneous zone, station, device, user, junction, and corridor graphs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from curbflow.data.clean import normalize_text_value
from curbflow.graph.adjacency import active_zone_ids, edges_to_adjacency, save_adjacency_matrices
from curbflow.graph.build_geo_graph import build_geo_graph_edges
from curbflow.graph.build_pattern_graph import build_pattern_graph_edges
from curbflow.graph.build_patrol_graph import build_patrol_graph_edges, compute_zone_centroids
from curbflow.graph.build_station_graph import (
    build_station_graph_edges,
    build_zone_station_membership_edges,
)
from curbflow.graph.build_vehicle_graph import build_vehicle_graph_edges
from curbflow.graph.graph_features import build_graph_feature_table


GRAPH_EDGES_PATH = Path("data/interim/graph_edges.parquet")
GRAPH_FEATURES_PATH = Path("data/processed/graph_features.parquet")
ADJACENCY_OUTPUT_DIR = Path("artifacts/models/adjacency_matrices")

NODE_TYPES = (
    "zone",
    "station",
    "device",
    "user",
    "repeat_vehicle",
    "junction",
    "road_corridor",
    "place_type",
)

ZONE_COORDINATE_COLUMN_SETS = (
    {"zone_centroid_lat", "zone_centroid_lon"},
    {"zone_centroid_latitude", "zone_centroid_longitude"},
    {"latitude", "longitude"},
)


def _has_zone_coordinates(frame: pd.DataFrame) -> bool:
    """Return true when a frame can provide zone centroids for graph building."""

    return any(columns.issubset(frame.columns) for columns in ZONE_COORDINATE_COLUMN_SETS)


def _attach_zone_centroids(frame: pd.DataFrame, row_frame: pd.DataFrame | None) -> pd.DataFrame:
    """Attach one centroid per zone from row-level assignments when needed."""

    if _has_zone_coordinates(frame) or row_frame is None or "zone_id" not in row_frame.columns:
        return frame
    if not _has_zone_coordinates(row_frame):
        return frame

    centroids = compute_zone_centroids(row_frame)
    if centroids.empty:
        return frame

    result = frame.copy()
    result["_zone_id_key"] = result["zone_id"].astype(str)
    centroid_lookup = centroids[["zone_id", "zone_centroid_lat", "zone_centroid_lon"]].copy()
    centroid_lookup["_zone_id_key"] = centroid_lookup["zone_id"].astype(str)
    result = result.merge(
        centroid_lookup[["_zone_id_key", "zone_centroid_lat", "zone_centroid_lon"]],
        on="_zone_id_key",
        how="left",
    )
    return result.drop(columns=["_zone_id_key"])


def _normalise_node(value: Any) -> Any:
    normalized = normalize_text_value(value)
    return pd.NA if pd.isna(normalized) else normalized


def _hetero_edge(edge_type: str, from_type: str, from_id: Any, to_type: str, to_id: Any, weight: float = 1.0) -> dict[str, Any]:
    return {
        "edge_type": edge_type,
        "from_node_type": from_type,
        "from_node_id": str(from_id),
        "to_node_type": to_type,
        "to_node_id": str(to_id),
        "weight": float(weight),
    }


def build_heterogeneous_graph_edges(
    zone_time_frame: pd.DataFrame,
    *,
    row_frame: pd.DataFrame | None = None,
    patrol_edges: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build heterogeneous graph metadata edges without exposing raw API identifiers."""

    records: list[dict[str, Any]] = []
    records.extend(build_zone_station_membership_edges(zone_time_frame).to_dict("records"))

    source = row_frame if row_frame is not None else zone_time_frame
    work = source.copy()
    if "zone_id" in work.columns:
        for column, edge_type, node_type in (
            ("device_id", "zone_recorded_by_device", "device"),
            ("created_by_id", "zone_recorded_by_user", "user"),
            ("anonymized_vehicle_id", "repeat_vehicle_seen_in_zone", "repeat_vehicle"),
            ("hidden_junction_id", "zone_in_junction_basin", "junction"),
            ("road_corridor_id", "zone_on_road_corridor", "road_corridor"),
            ("place_type_primary", "zone_has_place_type", "place_type"),
        ):
            if column not in work.columns:
                continue
            pairs = work[["zone_id", column]].dropna().drop_duplicates()
            for _, row in pairs.iterrows():
                node_id = _normalise_node(row[column])
                if pd.isna(node_id):
                    continue
                records.append(_hetero_edge(edge_type, "zone", row["zone_id"], node_type, node_id))

    if patrol_edges is not None and not patrol_edges.empty:
        for _, edge in patrol_edges.iterrows():
            records.append(
                _hetero_edge(
                    "patrol_transition_zone_to_zone",
                    "zone",
                    edge["from_zone_id"],
                    "zone",
                    edge["to_zone_id"],
                    float(edge.get("patrol_edge_weight", edge.get("weight", 0.0))),
                )
            )
    return pd.DataFrame(
        records,
        columns=[
            "edge_type",
            "from_node_type",
            "from_node_id",
            "to_node_type",
            "to_node_id",
            "weight",
        ],
    )


def _tag_zone_edges(edges: pd.DataFrame, graph_name: str) -> pd.DataFrame:
    if edges.empty:
        return pd.DataFrame(
            columns=["graph_name", "edge_type", "from_zone_id", "to_zone_id", "weight"]
        )
    result = edges.copy()
    if "weight" not in result.columns and "patrol_edge_weight" in result.columns:
        result["weight"] = result["patrol_edge_weight"]
    result["graph_name"] = graph_name
    return result


def build_all_graphs(
    zone_time_frame: pd.DataFrame,
    *,
    row_frame: pd.DataFrame | None = None,
    active_zone_min_records: int = 100,
    pattern_top_k: int = 10,
    adjacency_output_dir: str | Path = ADJACENCY_OUTPUT_DIR,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Path]]:
    """Build graph edges, graph features, and active-zone adjacency matrices."""

    zone_ids = active_zone_ids(zone_time_frame, active_zone_min_records=active_zone_min_records)
    active_frame = zone_time_frame[zone_time_frame["zone_id"].astype(str).isin(zone_ids)].copy()
    active_rows = (
        row_frame[row_frame["zone_id"].astype(str).isin(zone_ids)].copy()
        if row_frame is not None and "zone_id" in row_frame.columns
        else None
    )
    active_frame = _attach_zone_centroids(active_frame, active_rows)

    vehicle_source = active_rows if active_rows is not None else active_frame
    patrol_source = active_rows if active_rows is not None else active_frame

    geo_edges = build_geo_graph_edges(active_frame)
    station_edges = build_station_graph_edges(active_frame)
    pattern_edges = build_pattern_graph_edges(active_frame, top_k=pattern_top_k)
    vehicle_edges = build_vehicle_graph_edges(vehicle_source)
    patrol_edges = build_patrol_graph_edges(patrol_source) if {"zone_id", "created_datetime_ist"}.issubset(
        patrol_source.columns
    ) else pd.DataFrame(columns=["from_zone_id", "to_zone_id", "patrol_edge_weight"])

    matrices = {
        "A_geo": edges_to_adjacency(geo_edges, zone_ids),
        "A_station": edges_to_adjacency(station_edges, zone_ids),
        "A_pattern": edges_to_adjacency(pattern_edges, zone_ids),
        "A_vehicle": edges_to_adjacency(vehicle_edges, zone_ids),
        "A_patrol": edges_to_adjacency(
            patrol_edges.rename(columns={"patrol_edge_weight": "weight"})
            if "patrol_edge_weight" in patrol_edges.columns
            else patrol_edges,
            zone_ids,
        ),
    }
    saved_matrices = save_adjacency_matrices(matrices, adjacency_output_dir)

    graph_features = build_graph_feature_table(
        active_frame,
        geo_edges=geo_edges,
        station_edges=station_edges,
        pattern_edges=pattern_edges,
        vehicle_edges=vehicle_edges,
        patrol_edges=patrol_edges.rename(columns={"patrol_edge_weight": "weight"})
        if "patrol_edge_weight" in patrol_edges.columns
        else patrol_edges,
    )
    graph_features["is_active_graph_zone"] = True

    zone_edge_tables = [
        _tag_zone_edges(geo_edges, "geo"),
        _tag_zone_edges(station_edges, "station"),
        _tag_zone_edges(pattern_edges, "pattern"),
        _tag_zone_edges(vehicle_edges, "vehicle"),
        _tag_zone_edges(
            patrol_edges.rename(columns={"patrol_edge_weight": "weight"})
            if "patrol_edge_weight" in patrol_edges.columns
            else patrol_edges,
            "patrol",
        ),
    ]
    zone_edges = pd.concat(zone_edge_tables, ignore_index=True)
    hetero_edges = build_heterogeneous_graph_edges(active_frame, row_frame=active_rows, patrol_edges=patrol_edges)
    hetero_edges["graph_name"] = "heterogeneous"

    graph_edges = pd.concat(
        [
            zone_edges,
            hetero_edges.rename(
                columns={
                    "from_node_id": "from_zone_id",
                    "to_node_id": "to_zone_id",
                }
            ),
        ],
        ignore_index=True,
        sort=False,
    )
    graph_edges["weight"] = pd.to_numeric(graph_edges["weight"], errors="coerce").fillna(0.0)
    return graph_edges, graph_features, saved_matrices


def run_graph_build(
    zone_time_path: str | Path,
    *,
    row_path: str | Path | None = None,
    graph_edges_path: str | Path = GRAPH_EDGES_PATH,
    graph_features_path: str | Path = GRAPH_FEATURES_PATH,
    adjacency_output_dir: str | Path = ADJACENCY_OUTPUT_DIR,
    active_zone_min_records: int = 100,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Path]]:
    """Build and save all graph artifacts."""

    zone_time = pd.read_parquet(zone_time_path)
    rows = pd.read_parquet(row_path) if row_path is not None and Path(row_path).exists() else None
    graph_edges, graph_features, matrices = build_all_graphs(
        zone_time,
        row_frame=rows,
        active_zone_min_records=active_zone_min_records,
        adjacency_output_dir=adjacency_output_dir,
    )

    edges_path = Path(graph_edges_path)
    features_path = Path(graph_features_path)
    edges_path.parent.mkdir(parents=True, exist_ok=True)
    features_path.parent.mkdir(parents=True, exist_ok=True)
    graph_edges.to_parquet(edges_path, index=False)
    graph_features.to_parquet(features_path, index=False)
    return graph_edges, graph_features, matrices
