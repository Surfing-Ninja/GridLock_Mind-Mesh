"""Tests for feature table construction and BE-STHGT sequence inputs."""

from __future__ import annotations

import numpy as np
import pandas as pd

from curbflow.features.aggregate_zone_time import build_zone_time_features
from curbflow.features.sequence_dataset import SequenceConfig, build_sequence_splits
from curbflow.features.training_table import build_model_training_table
from curbflow.ml.datasets import CurbFlowSequenceDataset


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


def _training_sequence_fixture() -> pd.DataFrame:
    rows = []
    windows = pd.date_range("2023-11-20 00:00:00+05:30", periods=8, freq="3h")
    for zone_index, zone_id in enumerate(["zone_a", "zone_b"]):
        for time_index, window_start in enumerate(windows):
            observed = float(time_index + zone_index)
            if time_index >= 6:
                observed = 10_000.0 + zone_index
            rows.append(
                {
                    "zone_id": zone_id,
                    "window_start": window_start,
                    "window_end": window_start + pd.Timedelta(hours=3),
                    "police_station": "station_1" if zone_id == "zone_a" else "station_2",
                    "observed_pfdi": observed,
                    "bias_corrected_pfdi": observed + 1,
                    "record_count": 120,
                    "exposure": 0.5 + 0.01 * time_index,
                    "zero_window_weight": 0.6,
                    "next_count": time_index + 1,
                    "next_pfdi": observed + 10,
                    "next_bias_corrected_pfdi": observed + 11,
                    "next_hotspot": time_index % 2 == 0,
                    "next_relevance": min(time_index % 4, 3),
                    "is_active_training_zone": True,
                }
            )
    return pd.DataFrame(rows)


def test_sequence_dataset_shapes_are_correct(tmp_path) -> None:
    config = SequenceConfig(lookback_windows=3, scaler_path=tmp_path / "scaler.pkl")
    result = build_sequence_splits(
        _training_sequence_fixture(),
        config=config,
        feature_columns=["observed_pfdi", "exposure"],
    )

    total_samples = result.train.X.shape[0] + result.val.X.shape[0] + result.test.X.shape[0]
    assert total_samples == 6
    assert result.train.X.shape[1:] == (3, 2, 2)
    assert result.train.y_count.shape[1:] == (2,)
    assert result.train.y_pfdi.shape == result.train.y_q90_pfdi.shape
    assert result.zone_ids == ["zone_a", "zone_b"]
    assert (tmp_path / "scaler.pkl").exists()


def test_sequence_chronological_split_order_is_correct(tmp_path) -> None:
    config = SequenceConfig(lookback_windows=3, scaler_path=tmp_path / "scaler.pkl")
    result = build_sequence_splits(
        _training_sequence_fixture(),
        config=config,
        feature_columns=["observed_pfdi"],
    )

    assert result.train.window_start.max() < result.val.window_start.min()
    assert result.val.window_start.max() < result.test.window_start.min()


def test_sequence_construction_does_not_use_future_windows(tmp_path) -> None:
    config = SequenceConfig(lookback_windows=3, scaler_path=tmp_path / "scaler.pkl")
    result = build_sequence_splits(
        _training_sequence_fixture(),
        config=config,
        feature_columns=["observed_pfdi"],
    )

    first_test_window = result.test.window_start[0]
    assert all(window <= first_test_window for window in result.test.window_start)
    train_sample_end = result.train.window_start[-1]
    assert train_sample_end < first_test_window
    assert result.train.X.shape[1] == 3


def test_sequence_scaler_is_fit_only_on_train(tmp_path) -> None:
    config = SequenceConfig(lookback_windows=3, scaler_path=tmp_path / "scaler.pkl")
    result = build_sequence_splits(
        _training_sequence_fixture(),
        config=config,
        feature_columns=["observed_pfdi"],
    )

    assert result.scaler.mean_[0] < 100.0
    all_window_mean = _training_sequence_fixture()["observed_pfdi"].mean()
    assert all_window_mean > 2_000.0


def test_pytorch_sequence_dataset_returns_expected_keys(tmp_path) -> None:
    config = SequenceConfig(lookback_windows=3, scaler_path=tmp_path / "scaler.pkl")
    result = build_sequence_splits(
        _training_sequence_fixture(),
        config=config,
        feature_columns=["observed_pfdi", "exposure"],
    )
    dataset = CurbFlowSequenceDataset(result.train)
    sample = dataset[0]

    assert sample["X"].shape == (3, 2, 2)
    assert sample["y_count"].shape == (2,)
    assert sample["rank_groups"].shape == (2,)
    assert np.array_equal(sample["police_station_ids"].numpy(), result.train.police_station_ids)
