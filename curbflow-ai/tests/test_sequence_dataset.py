"""Tests for feature table construction and BE-STHGT sequence inputs."""

from __future__ import annotations

import pandas as pd

from curbflow.features.aggregate_zone_time import build_zone_time_features
from curbflow.features.training_table import build_model_training_table


def _row_feature_fixture() -> pd.DataFrame:
    rows = []
    for zone_index, zone_id in enumerate(["zone_a", "zone_b"]):
        for window_index, hour in enumerate([8, 11, 14]):
            rows.append(
                {
                    "zone_id": zone_id,
                    "created_datetime_ist": f"2023-11-20T{hour:02d}:10:00+05:30",
                    "latitude": 12.9716 + zone_index * 0.001,
                    "longitude": 77.5946 + zone_index * 0.001,
                    "zone_centroid_lat": 12.9716 + zone_index * 0.001,
                    "zone_centroid_lon": 77.5946 + zone_index * 0.001,
                    "police_station": "station_1",
                    "junction_name": "Town Hall" if zone_index == 0 else "No Junction",
                    "location": "MG Road Metro Market",
                    "vehicle_number": f"KA01AA00{zone_index}",
                    "vehicle_type": "BMTC Bus" if zone_index == 0 else "Scooter",
                    "updated_vehicle_type": "",
                    "violation_type": "DOUBLE PARKING"
                    if window_index == 2
                    else "PARKING IN A MAIN ROAD",
                    "parsed_violation_labels": ["double_parking"]
                    if window_index == 2
                    else ["parking_in_main_road"],
                    "violation_severity": 0.98 if window_index == 2 else 0.95,
                    "vehicle_obstruction": 1.0 if zone_index == 0 else 0.35,
                    "location_criticality": 0.8,
                    "repeat_pressure": 0.2 * window_index,
                    "validation_status": "approved",
                    "data_sent_to_scita": True,
                    "device_id": "device_1",
                    "created_by_id": "user_1",
                    "row_obstruction_score": 40.0 + 10 * window_index + 5 * zone_index,
                    "evidence_quality_score": 0.9,
                    "device_trust": 0.8,
                    "user_trust": 0.85,
                    "station_evidence_quality": 0.82,
                    "type_correction_flag": False,
                }
            )
    return pd.DataFrame(rows)


def test_zone_time_features_and_training_table_are_built() -> None:
    zone_time = build_zone_time_features(_row_feature_fixture())
    training = build_model_training_table(zone_time, active_zone_min_records=2)

    required_zone_columns = {
        "zone_id",
        "window_start",
        "window_end",
        "observed_pfdi",
        "bias_corrected_pfdi",
        "exposure",
        "coverage_gap",
        "zero_window_weight",
        "evidence_quality_score_mean",
        "junction_basin_pfdi",
        "patrol_route_coverage",
        "persistence_score",
        "corridor_recent_pfdi",
        "commercial_market",
        "transit_node",
        "static_potential",
        "evening_severity_prior",
        "uncertainty",
        "blindspot_risk",
        "lag_1_pfdi",
        "rolling_7d_pfdi",
    }
    required_training_columns = {
        "next_count",
        "next_pfdi",
        "next_bias_corrected_pfdi",
        "next_hotspot",
        "next_relevance",
        "is_active_training_zone",
    }

    assert required_zone_columns.issubset(zone_time.columns)
    assert required_training_columns.issubset(training.columns)
    assert len(zone_time) == 6
    assert len(training) == 4
    assert training["is_active_training_zone"].all()
