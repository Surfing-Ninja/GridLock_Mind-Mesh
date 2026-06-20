"""Graph-derived features such as pagerank, degree, and patrol coverage."""

from __future__ import annotations

import networkx as nx
import pandas as pd


def _zone_pfdi(frame: pd.DataFrame) -> pd.Series:
    """Return mean PFDI per zone from available feature columns."""

    for column in ("bias_corrected_pfdi", "observed_pfdi", "raw_impact"):
        if column in frame.columns:
            return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    return pd.Series([0.0] * len(frame), index=frame.index, dtype="float64")


def neighbor_mean_pfdi(
    frame: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    feature_name: str,
) -> pd.DataFrame:
    """Compute weighted neighbor mean PFDI for each zone."""

    zone_pfdi = frame.assign(_pfdi=_zone_pfdi(frame)).groupby("zone_id")["_pfdi"].mean()
    records = []
    for zone_id in frame["zone_id"].dropna().astype(str).unique():
        outgoing = edges[edges["from_zone_id"].astype(str).eq(zone_id)] if not edges.empty else edges
        numerator = 0.0
        denominator = 0.0
        for _, edge in outgoing.iterrows():
            neighbor = str(edge["to_zone_id"])
            if neighbor not in zone_pfdi.index:
                continue
            weight = float(edge.get("weight", edge.get("patrol_edge_weight", 0.0)))
            numerator += weight * float(zone_pfdi.loc[neighbor])
            denominator += weight
        records.append({"zone_id": zone_id, feature_name: numerator / denominator if denominator else 0.0})
    return pd.DataFrame(records)


def _patrol_graph(edges: pd.DataFrame, zones: list[str]) -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_nodes_from(zones)
    for _, edge in edges.iterrows():
        weight = float(edge.get("weight", edge.get("patrol_edge_weight", 0.0)))
        if weight > 0:
            graph.add_edge(str(edge["from_zone_id"]), str(edge["to_zone_id"]), weight=weight)
    return graph


def build_graph_feature_table(
    frame: pd.DataFrame,
    *,
    geo_edges: pd.DataFrame,
    station_edges: pd.DataFrame,
    pattern_edges: pd.DataFrame,
    vehicle_edges: pd.DataFrame,
    patrol_edges: pd.DataFrame,
) -> pd.DataFrame:
    """Build graph-derived zone features for ML tables."""

    zones = sorted(frame["zone_id"].dropna().astype(str).unique())
    features = pd.DataFrame({"zone_id": zones})
    for edge_table, feature_name in (
        (geo_edges, "geo_neighbor_mean_pfdi"),
        (station_edges, "station_neighbor_mean_pfdi"),
        (pattern_edges, "pattern_neighbor_mean_pfdi"),
    ):
        features = features.merge(
            neighbor_mean_pfdi(frame, edge_table, feature_name=feature_name),
            on="zone_id",
            how="left",
        )

    vehicle_degree = (
        vehicle_edges.groupby("from_zone_id")["weight"].sum().rename("vehicle_graph_degree")
        if not vehicle_edges.empty
        else pd.Series(dtype="float64", name="vehicle_graph_degree")
    )
    features["vehicle_graph_degree"] = features["zone_id"].map(vehicle_degree).fillna(0.0)

    patrol_graph = _patrol_graph(patrol_edges, zones)
    pagerank = nx.pagerank(patrol_graph, weight="weight") if patrol_graph.number_of_nodes() else {}
    features["patrol_pagerank"] = features["zone_id"].map(pagerank).fillna(0.0)

    undirected = patrol_graph.to_undirected()
    communities = list(nx.connected_components(undirected)) if undirected.number_of_nodes() else []
    community_lookup = {
        zone: community_id
        for community_id, community in enumerate(communities)
        for zone in community
    }
    features["community_id"] = features["zone_id"].map(community_lookup).fillna(-1).astype(int)
    return features.fillna(0.0)


def merge_graph_features(training_table: pd.DataFrame, graph_features: pd.DataFrame) -> pd.DataFrame:
    """Merge graph features into a zone-time or model training table."""

    return training_table.merge(graph_features, on="zone_id", how="left").fillna(
        {
            "geo_neighbor_mean_pfdi": 0.0,
            "station_neighbor_mean_pfdi": 0.0,
            "pattern_neighbor_mean_pfdi": 0.0,
            "vehicle_graph_degree": 0.0,
            "patrol_pagerank": 0.0,
            "community_id": -1,
        }
    )
