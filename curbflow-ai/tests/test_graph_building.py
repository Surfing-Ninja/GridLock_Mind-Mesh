"""Tests for graph construction, zoning, and adjacency outputs."""

from __future__ import annotations

import pandas as pd

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
