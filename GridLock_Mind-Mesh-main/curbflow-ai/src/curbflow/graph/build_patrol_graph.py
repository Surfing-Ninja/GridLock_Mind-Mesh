"""Build patrol transition graphs from sequential device or user observations."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import networkx as nx
import pandas as pd

from curbflow.data.clean import normalize_text_value


PATROL_GRAPH_EDGES_PATH = Path("data/interim/patrol_graph_edges.parquet")
PATROL_GRAPH_FEATURES_PATH = Path("data/processed/patrol_graph_features.parquet")
EARTH_RADIUS_M = 6_371_000.0


def _normalise_key(value: Any) -> Any:
    """Normalize optional graph keys while preserving missing values."""

    normalized = normalize_text_value(value)
    if pd.isna(normalized):
        return pd.NA
    return normalized


def _haversine_m(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Compute great-circle distance in meters."""

    phi_a = math.radians(lat_a)
    phi_b = math.radians(lat_b)
    delta_phi = math.radians(lat_b - lat_a)
    delta_lambda = math.radians(lon_b - lon_a)
    haversine = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(haversine))


def _created_time_ist(series: pd.Series) -> pd.Series:
    """Parse created timestamps and normalize to Asia/Kolkata."""

    return pd.to_datetime(series, errors="coerce", utc=True).dt.tz_convert("Asia/Kolkata")


def compute_zone_centroids(frame: pd.DataFrame) -> pd.DataFrame:
    """Build one centroid row per zone from available zone or raw coordinates."""

    if "zone_id" not in frame.columns:
        raise ValueError("Missing required column for patrol graph: zone_id")

    work = frame.copy()
    work["zone_id"] = work["zone_id"].map(lambda value: normalize_text_value(value, unknown_for_null=True))
    if {"zone_centroid_lat", "zone_centroid_lon"}.issubset(work.columns):
        lat_col = "zone_centroid_lat"
        lon_col = "zone_centroid_lon"
    elif {"zone_centroid_latitude", "zone_centroid_longitude"}.issubset(work.columns):
        lat_col = "zone_centroid_latitude"
        lon_col = "zone_centroid_longitude"
    elif {"latitude", "longitude"}.issubset(work.columns):
        lat_col = "latitude"
        lon_col = "longitude"
    else:
        raise ValueError(
            "Patrol graph requires zone centroid columns or latitude/longitude columns."
        )

    work[lat_col] = pd.to_numeric(work[lat_col], errors="coerce")
    work[lon_col] = pd.to_numeric(work[lon_col], errors="coerce")
    centroids = (
        work.dropna(subset=[lat_col, lon_col])
        .groupby("zone_id", dropna=False)
        .agg(zone_centroid_lat=(lat_col, "median"), zone_centroid_lon=(lon_col, "median"))
        .reset_index()
    )
    return centroids


def _zone_centroid_lookup(centroids: pd.DataFrame) -> dict[str, tuple[float, float]]:
    """Return a zone centroid lookup dictionary."""

    return {
        str(row["zone_id"]): (float(row["zone_centroid_lat"]), float(row["zone_centroid_lon"]))
        for _, row in centroids.dropna(subset=["zone_centroid_lat", "zone_centroid_lon"]).iterrows()
    }


def _build_actor_transition_edges(
    frame: pd.DataFrame,
    *,
    actor_column: str,
    edge_source: str,
    max_gap_hours: float,
    max_distance_km: float,
    centroids: pd.DataFrame,
) -> pd.DataFrame:
    """Build aggregate directed transition edges for one actor type."""

    if actor_column not in frame.columns:
        return pd.DataFrame(
            columns=[
                "from_zone_id",
                "to_zone_id",
                f"{edge_source}_transition_count",
                f"{edge_source}_transition_weight",
            ]
        )

    work = frame.copy()
    work[actor_column] = work[actor_column].map(_normalise_key)
    work["zone_id"] = work["zone_id"].map(lambda value: normalize_text_value(value, unknown_for_null=True))
    work["_created_time_ist"] = _created_time_ist(work["created_datetime_ist"])
    work["_created_date_ist"] = work["_created_time_ist"].dt.date
    work = work.dropna(subset=[actor_column, "_created_time_ist", "_created_date_ist"])

    centroid_lookup = _zone_centroid_lookup(centroids)
    max_gap = pd.Timedelta(hours=max_gap_hours)
    max_distance_m = max_distance_km * 1000
    records: list[dict[str, Any]] = []

    for _, group in work.sort_values("_created_time_ist").groupby(
        [actor_column, "_created_date_ist"],
        sort=False,
    ):
        ordered = group.sort_values("_created_time_ist")
        previous = None
        for _, current in ordered.iterrows():
            if previous is None:
                previous = current
                continue

            from_zone = str(previous["zone_id"])
            to_zone = str(current["zone_id"])
            time_gap = current["_created_time_ist"] - previous["_created_time_ist"]
            previous = current
            if from_zone == to_zone or time_gap <= pd.Timedelta(0) or time_gap > max_gap:
                continue
            if from_zone not in centroid_lookup or to_zone not in centroid_lookup:
                continue

            from_lat, from_lon = centroid_lookup[from_zone]
            to_lat, to_lon = centroid_lookup[to_zone]
            distance_m = _haversine_m(from_lat, from_lon, to_lat, to_lon)
            if distance_m > max_distance_m:
                continue

            gap_hours = time_gap.total_seconds() / 3600
            records.append(
                {
                    "from_zone_id": from_zone,
                    "to_zone_id": to_zone,
                    "transition_count": 1,
                    "transition_weight": math.exp(-gap_hours / 2),
                    "mean_gap_hours": gap_hours,
                    "mean_distance_m": distance_m,
                }
            )

    if not records:
        return pd.DataFrame(
            columns=[
                "from_zone_id",
                "to_zone_id",
                f"{edge_source}_transition_count",
                f"{edge_source}_transition_weight",
                f"{edge_source}_mean_gap_hours",
                f"{edge_source}_mean_distance_m",
            ]
        )

    edges = (
        pd.DataFrame(records)
        .groupby(["from_zone_id", "to_zone_id"], as_index=False)
        .agg(
            transition_count=("transition_count", "sum"),
            transition_weight=("transition_weight", "sum"),
            mean_gap_hours=("mean_gap_hours", "mean"),
            mean_distance_m=("mean_distance_m", "mean"),
        )
        .rename(
            columns={
                "transition_count": f"{edge_source}_transition_count",
                "transition_weight": f"{edge_source}_transition_weight",
                "mean_gap_hours": f"{edge_source}_mean_gap_hours",
                "mean_distance_m": f"{edge_source}_mean_distance_m",
            }
        )
    )
    return edges


def build_patrol_graph_edges(
    frame: pd.DataFrame,
    *,
    max_gap_hours: float = 3.0,
    max_distance_km: float = 10.0,
) -> pd.DataFrame:
    """Build combined device/user patrol transition graph edges."""

    required = {"zone_id", "created_datetime_ist"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns for patrol graph: {sorted(missing)}")

    centroids = compute_zone_centroids(frame)
    device_edges = _build_actor_transition_edges(
        frame,
        actor_column="device_id",
        edge_source="device",
        max_gap_hours=max_gap_hours,
        max_distance_km=max_distance_km,
        centroids=centroids,
    )
    user_edges = _build_actor_transition_edges(
        frame,
        actor_column="created_by_id",
        edge_source="user",
        max_gap_hours=max_gap_hours,
        max_distance_km=max_distance_km,
        centroids=centroids,
    )
    edges = pd.merge(device_edges, user_edges, on=["from_zone_id", "to_zone_id"], how="outer")
    if edges.empty:
        return pd.DataFrame(
            columns=[
                "from_zone_id",
                "to_zone_id",
                "device_transition_count",
                "user_transition_count",
                "device_transition_weight",
                "user_transition_weight",
                "patrol_edge_weight",
                "patrol_transition_count",
            ]
        )

    fill_columns = [
        "device_transition_count",
        "user_transition_count",
        "device_transition_weight",
        "user_transition_weight",
    ]
    for column in fill_columns:
        if column not in edges.columns:
            edges[column] = 0.0
        edges[column] = pd.to_numeric(edges[column], errors="coerce").fillna(0.0)

    edges["patrol_edge_weight"] = (
        0.6 * edges["device_transition_weight"] + 0.4 * edges["user_transition_weight"]
    )
    edges["patrol_transition_count"] = (
        edges["device_transition_count"] + edges["user_transition_count"]
    ).astype("int64")
    return edges.sort_values(["from_zone_id", "to_zone_id"]).reset_index(drop=True)


def _zone_static_potential(frame: pd.DataFrame) -> pd.Series:
    """Infer static potential per zone from available risk columns."""

    if "static_potential" in frame.columns:
        return pd.to_numeric(frame["static_potential"], errors="coerce")
    if "row_obstruction_score" in frame.columns:
        return pd.to_numeric(frame["row_obstruction_score"], errors="coerce")
    if "pfdi" in frame.columns:
        return pd.to_numeric(frame["pfdi"], errors="coerce")
    return pd.Series([0.0] * len(frame), index=frame.index)


def _zone_exposure(frame: pd.DataFrame) -> pd.Series:
    """Infer exposure per zone from available enforcement visibility columns."""

    for column in ("exposure_score", "enforcement_visibility", "visibility_score", "coverage_score"):
        if column in frame.columns:
            return pd.to_numeric(frame[column], errors="coerce")
    return pd.Series([1.0] * len(frame), index=frame.index)


def _build_patrol_network(edges: pd.DataFrame, zones: pd.Series) -> nx.DiGraph:
    """Create a directed graph from aggregate patrol transition edges."""

    graph = nx.DiGraph()
    graph.add_nodes_from(zones.dropna().astype(str).unique())
    for _, edge in edges.iterrows():
        weight = float(edge.get("patrol_edge_weight", 0.0))
        if weight <= 0:
            continue
        graph.add_edge(str(edge["from_zone_id"]), str(edge["to_zone_id"]), weight=weight)
    return graph


def build_patrol_graph_features(
    frame: pd.DataFrame,
    edges: pd.DataFrame | None = None,
    *,
    max_distance_km: float = 10.0,
) -> pd.DataFrame:
    """Compute aggregate zone features from the combined patrol graph."""

    if "zone_id" not in frame.columns:
        raise ValueError("Missing columns for patrol graph features: ['zone_id']")

    work = frame.copy()
    work["zone_id"] = work["zone_id"].map(lambda value: normalize_text_value(value, unknown_for_null=True))
    edges = build_patrol_graph_edges(work, max_distance_km=max_distance_km) if edges is None else edges
    centroids = compute_zone_centroids(work)
    graph = _build_patrol_network(edges, work["zone_id"])
    pagerank = nx.pagerank(graph, weight="weight") if graph.number_of_nodes() else {}

    static_potential = _zone_static_potential(work)
    exposure = _zone_exposure(work)
    zone_stats = (
        work.assign(_static_potential=static_potential, _exposure=exposure)
        .groupby("zone_id", dropna=False)
        .agg(
            static_potential=("_static_potential", "sum"),
            exposure_score=("_exposure", "mean"),
            record_count=("zone_id", "size"),
        )
        .reset_index()
    )
    feature_rows = []
    max_neighbor_count = 1
    neighbor_counts: dict[str, int] = {}
    for zone in zone_stats["zone_id"].astype(str):
        predecessors = set(graph.predecessors(zone)) if zone in graph else set()
        successors = set(graph.successors(zone)) if zone in graph else set()
        neighbor_counts[zone] = len(predecessors | successors)
        max_neighbor_count = max(max_neighbor_count, neighbor_counts[zone])

    in_degree = dict(graph.in_degree(weight="weight"))
    out_degree = dict(graph.out_degree(weight="weight"))
    weighted_degree = {
        zone: float(in_degree.get(zone, 0.0) + out_degree.get(zone, 0.0))
        for zone in zone_stats["zone_id"].astype(str)
    }

    static_threshold = zone_stats["static_potential"].quantile(0.75)
    exposure_threshold = zone_stats["exposure_score"].quantile(0.25)
    centroid_lookup = _zone_centroid_lookup(centroids)
    patrol_connected_zones = {zone for zone, degree in weighted_degree.items() if degree > 0}
    max_distance_m = max_distance_km * 1000

    for _, row in zone_stats.iterrows():
        zone = str(row["zone_id"])
        near_connected = False
        if zone in centroid_lookup:
            zone_lat, zone_lon = centroid_lookup[zone]
            for connected_zone in patrol_connected_zones - {zone}:
                if connected_zone not in centroid_lookup:
                    continue
                connected_lat, connected_lon = centroid_lookup[connected_zone]
                if _haversine_m(zone_lat, zone_lon, connected_lat, connected_lon) <= max_distance_m:
                    near_connected = True
                    break
        high_static = row["static_potential"] >= static_threshold
        low_exposure = row["exposure_score"] <= exposure_threshold
        feature_rows.append(
            {
                "zone_id": zone,
                "patrol_in_degree": float(in_degree.get(zone, 0.0)),
                "patrol_out_degree": float(out_degree.get(zone, 0.0)),
                "patrol_weighted_degree": float(weighted_degree.get(zone, 0.0)),
                "patrol_pagerank": float(pagerank.get(zone, 0.0)),
                "patrol_route_coverage": neighbor_counts[zone] / max_neighbor_count,
                "near_patrol_but_uncovered_flag": bool(
                    high_static and low_exposure and near_connected and weighted_degree.get(zone, 0) == 0
                ),
                "static_potential": float(row["static_potential"]),
                "exposure_score": float(row["exposure_score"]),
                "record_count": int(row["record_count"]),
            }
        )

    return pd.DataFrame(feature_rows).sort_values("zone_id").reset_index(drop=True)


def run_patrol_graph_build(
    frame_or_path: pd.DataFrame | str | Path,
    *,
    edges_output_path: str | Path = PATROL_GRAPH_EDGES_PATH,
    features_output_path: str | Path = PATROL_GRAPH_FEATURES_PATH,
    max_gap_hours: float = 3.0,
    max_distance_km: float = 10.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build patrol graph edge and zone feature artifacts."""

    frame = pd.read_parquet(frame_or_path) if not isinstance(frame_or_path, pd.DataFrame) else frame_or_path
    edges = build_patrol_graph_edges(
        frame,
        max_gap_hours=max_gap_hours,
        max_distance_km=max_distance_km,
    )
    features = build_patrol_graph_features(frame, edges, max_distance_km=max_distance_km)

    edges_path = Path(edges_output_path)
    features_path = Path(features_output_path)
    edges_path.parent.mkdir(parents=True, exist_ok=True)
    features_path.parent.mkdir(parents=True, exist_ok=True)
    edges.to_parquet(edges_path, index=False)
    features.to_parquet(features_path, index=False)
    return edges, features
