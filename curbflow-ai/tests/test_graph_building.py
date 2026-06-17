"""Tests for graph construction, zoning, and adjacency outputs."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from curbflow.graph.build_hetero_graph import build_all_graphs
from curbflow.graph.build_patrol_graph import (
    build_patrol_graph_edges,
    build_patrol_graph_features,
    run_patrol_graph_build,
)
from curbflow.graph.graph_features import merge_graph_features
from curbflow.zoning.assign_zones import assign_grid_zones
from curbflow.zoning.zone_geojson import zones_to_geojson


def _sample_points() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "latitude": [12.9716, 12.9717, 12.9900],
            "longitude": [77.5946, 77.5947, 77.6200],
            "row_obstruction_score": [10.0, 20.0, 30.0],
        }
    )


def test_every_row_gets_zone_id() -> None:
    assignments, zones, summary = assign_grid_zones(_sample_points(), active_zone_min_records=2)

    assert assignments["zone_id"].notna().all()
    assert assignments["zone_id"].astype(str).str.len().gt(0).all()
    assert len(assignments) == 3
    assert summary.total_zones == len(zones)


def test_zones_have_valid_rectangular_polygons() -> None:
    _, zones, _ = assign_grid_zones(_sample_points(), active_zone_min_records=1)
    geojson = zones_to_geojson(zones)

    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == len(zones)
    for feature in geojson["features"]:
        polygon = feature["geometry"]["coordinates"][0]
        assert feature["geometry"]["type"] == "Polygon"
        assert len(polygon) == 5
        assert polygon[0] == polygon[-1]
        assert all(len(point) == 2 for point in polygon)


def test_active_zone_filtering_and_concentration_metrics() -> None:
    assignments, zones, summary = assign_grid_zones(_sample_points(), active_zone_min_records=2)

    active_zones = zones[zones["is_active_zone"]]
    assert summary.active_zones == 1
    assert summary.records_covered_by_active_zones == 2
    assert int(active_zones.iloc[0]["record_count"]) == 2
    assert summary.top_10_zone_concentration == 1.0
    assert summary.top_1_percent_zone_concentration == 2 / 3


def _patrol_rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "zone_id": [
                "zone_a",
                "zone_b",
                "zone_c",
                "zone_far",
                "zone_d",
                "zone_a",
                "zone_b",
            ],
            "created_datetime_ist": [
                "2023-11-20T08:00:00+05:30",
                "2023-11-20T09:00:00+05:30",
                "2023-11-20T10:00:00+05:30",
                "2023-11-20T12:00:00+05:30",
                "2023-11-20T08:30:00+05:30",
                "2023-11-21T08:00:00+05:30",
                "2023-11-21T12:30:00+05:30",
            ],
            "device_id": ["device_1", "device_1", "device_1", "device_1", "device_2", "device_3", "device_3"],
            "created_by_id": ["user_1", "user_1", "user_1", "user_1", "user_2", "user_3", "user_3"],
            "zone_centroid_lat": [12.9716, 12.9730, 12.9740, 13.2000, 12.9720, 12.9716, 12.9730],
            "zone_centroid_lon": [77.5946, 77.5960, 77.5970, 77.9000, 77.5950, 77.5946, 77.5960],
            "static_potential": [10.0, 10.0, 10.0, 10.0, 100.0, 10.0, 10.0],
            "exposure_score": [0.9, 0.8, 0.7, 0.9, 0.1, 0.9, 0.8],
        }
    )


def test_patrol_transition_graph_combines_device_and_user_edges() -> None:
    edges = build_patrol_graph_edges(_patrol_rows())
    edge = edges[(edges["from_zone_id"] == "zone_a") & (edges["to_zone_id"] == "zone_b")].iloc[0]

    expected_weight = math.exp(-0.5)
    assert edge["device_transition_count"] == 1
    assert edge["user_transition_count"] == 1
    assert edge["patrol_edge_weight"] == pytest.approx(expected_weight)
    assert "device_id" not in edges.columns
    assert "created_by_id" not in edges.columns


def test_patrol_transition_graph_filters_gap_and_distance() -> None:
    edges = build_patrol_graph_edges(_patrol_rows())
    pairs = set(zip(edges["from_zone_id"], edges["to_zone_id"], strict=False))

    assert ("zone_c", "zone_far") not in pairs
    assert not (
        (edges["from_zone_id"] == "zone_a") & (edges["to_zone_id"] == "zone_b")
    ).sum() > 1


def test_patrol_graph_features_include_degrees_pagerank_and_uncovered_flag() -> None:
    rows = _patrol_rows()
    edges = build_patrol_graph_edges(rows)
    features = build_patrol_graph_features(rows, edges)
    zone_a = features[features["zone_id"] == "zone_a"].iloc[0]
    zone_d = features[features["zone_id"] == "zone_d"].iloc[0]

    assert zone_a["patrol_out_degree"] > 0
    assert zone_a["patrol_pagerank"] > 0
    assert 0.0 <= zone_a["patrol_route_coverage"] <= 1.0
    assert bool(zone_d["near_patrol_but_uncovered_flag"]) is True


def test_patrol_graph_build_writes_aggregate_artifacts(tmp_path) -> None:
    edges_path = tmp_path / "patrol_graph_edges.parquet"
    features_path = tmp_path / "patrol_graph_features.parquet"

    edges, features = run_patrol_graph_build(
        _patrol_rows(),
        edges_output_path=edges_path,
        features_output_path=features_path,
    )

    assert edges_path.exists()
    assert features_path.exists()
    assert len(pd.read_parquet(edges_path)) == len(edges)
    assert len(pd.read_parquet(features_path)) == len(features)
    assert "device_id" not in pd.read_parquet(edges_path).columns
    assert "created_by_id" not in pd.read_parquet(edges_path).columns


def _graph_zone_time() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "zone_id": ["zone_a", "zone_a", "zone_b", "zone_b", "zone_c", "zone_c"],
            "window_start": pd.to_datetime(
                [
                    "2023-11-20T06:00:00+05:30",
                    "2023-11-20T09:00:00+05:30",
                    "2023-11-20T06:00:00+05:30",
                    "2023-11-20T09:00:00+05:30",
                    "2023-11-20T06:00:00+05:30",
                    "2023-11-20T09:00:00+05:30",
                ]
            ),
            "day_of_week": [0, 0, 0, 0, 0, 0],
            "hour": [6, 9, 6, 9, 6, 9],
            "police_station": ["station_1", "station_1", "station_1", "station_1", "station_2", "station_2"],
            "zone_centroid_lat": [12.9716, 12.9716, 12.9730, 12.9730, 12.9750, 12.9750],
            "zone_centroid_lon": [77.5946, 77.5946, 77.5960, 77.5960, 77.5980, 77.5980],
            "record_count": [120, 120, 140, 140, 150, 150],
            "observed_pfdi": [10.0, 20.0, 12.0, 24.0, 2.0, 3.0],
            "bias_corrected_pfdi": [11.0, 22.0, 13.0, 26.0, 2.0, 3.0],
            "place_type_primary": ["commercial", "commercial", "transit", "transit", "unknown", "unknown"],
            "road_corridor_id": ["mg road", "mg road", "mg road", "mg road", "other road", "other road"],
        }
    )


def _graph_rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "zone_id": ["zone_a", "zone_b", "zone_a", "zone_c", "zone_b", "zone_c"],
            "created_datetime_ist": [
                "2023-11-20T08:00:00+05:30",
                "2023-11-20T09:00:00+05:30",
                "2023-11-20T10:00:00+05:30",
                "2023-11-20T11:00:00+05:30",
                "2023-11-20T12:00:00+05:30",
                "2023-11-20T13:00:00+05:30",
            ],
            "vehicle_number": ["KA01AA0001", "KA01AA0001", "KA01AA0002", "KA01AA0002", "KA01AA0001", "KA01AA0003"],
            "device_id": ["device_1", "device_1", "device_2", "device_2", "device_1", "device_3"],
            "created_by_id": ["user_1", "user_1", "user_2", "user_2", "user_1", "user_3"],
            "zone_centroid_lat": [12.9716, 12.9730, 12.9716, 12.9750, 12.9730, 12.9750],
            "zone_centroid_lon": [77.5946, 77.5960, 77.5946, 77.5980, 77.5960, 77.5980],
            "hidden_junction_id": ["junction_a", "junction_a", "junction_a", "junction_b", "junction_a", "junction_b"],
            "road_corridor_id": ["mg road", "mg road", "mg road", "other road", "mg road", "other road"],
            "place_type_primary": ["commercial", "transit", "commercial", "unknown", "transit", "unknown"],
        }
    )


def test_graph_adjacency_matrices_are_square_and_saved(tmp_path) -> None:
    edges, features, matrices = build_all_graphs(
        _graph_zone_time(),
        row_frame=_graph_rows(),
        active_zone_min_records=100,
        adjacency_output_dir=tmp_path,
    )

    assert len(features) == 3
    for name in ("A_geo", "A_station", "A_pattern", "A_vehicle", "A_patrol"):
        matrix = np.load(matrices[name])
        assert matrix.shape == (3, 3)

    assert not edges["weight"].isna().any()
    assert np.isfinite(edges["weight"].to_numpy(dtype=float)).all()


def test_graph_features_merge_into_training_table(tmp_path) -> None:
    _, graph_features, _ = build_all_graphs(
        _graph_zone_time(),
        row_frame=_graph_rows(),
        active_zone_min_records=100,
        adjacency_output_dir=tmp_path,
    )
    training_like = _graph_zone_time()[["zone_id", "window_start", "bias_corrected_pfdi"]].copy()
    merged = merge_graph_features(training_like, graph_features)

    expected_columns = {
        "geo_neighbor_mean_pfdi",
        "station_neighbor_mean_pfdi",
        "pattern_neighbor_mean_pfdi",
        "vehicle_graph_degree",
        "patrol_pagerank",
        "community_id",
    }
    assert expected_columns.issubset(merged.columns)
    assert len(merged) == len(training_like)
