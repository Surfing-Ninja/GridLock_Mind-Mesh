"""Tests for enforcement visibility and coverage gap scoring."""

from __future__ import annotations

import pandas as pd
import pytest

from curbflow.exposure.blindspot import (
    add_blindspot_risk_features,
    compute_evening_severity_prior,
    compute_peak_priority,
    write_blindspot_zone_time_features,
)
from curbflow.exposure.coverage_gap import compute_coverage_gap
from curbflow.exposure.visibility import (
    build_zone_time_visibility_inputs,
    compute_enforcement_visibility,
    robust_percentile_scale,
)


def _visibility_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "zone_id": ["zone_a", "zone_b", "zone_c", "zone_d"],
            "time_window_start": pd.to_datetime(
                [
                    "2023-11-20T06:00:00+05:30",
                    "2023-11-20T06:00:00+05:30",
                    "2023-11-20T06:00:00+05:30",
                    "2023-11-20T06:00:00+05:30",
                ]
            ),
            "police_station": ["station_1", "station_1", "station_1", "station_1"],
            "unique_device_count": [0, 1, 4, 12],
            "unique_created_by_user_count": [0, 1, 3, 8],
            "station_hour_activity": [0, 2, 8, 20],
            "patrol_route_coverage": [0.0, 0.2, 0.6, 1.0],
            "scita_success_rate": [0.0, 0.3, 0.7, 1.0],
            "validation_coverage": [0.0, 0.4, 0.8, 1.0],
            "observed_pfdi": [0.0, 10.0, 20.0, 100.0],
        }
    )


def test_robust_percentile_scale_clips_to_unit_interval() -> None:
    scaled = robust_percentile_scale(pd.Series([-10, 0, 5, 1000]))

    assert scaled.between(0, 1).all()
    assert scaled.iloc[0] == pytest.approx(0.0)
    assert scaled.iloc[-1] == pytest.approx(1.0)


def test_exposure_and_coverage_gap_are_between_zero_and_one() -> None:
    scored = compute_enforcement_visibility(_visibility_frame())

    assert scored["exposure"].between(0, 1).all()
    assert scored["coverage_gap"].between(0, 1).all()
    assert (scored["coverage_gap"] - (1 - scored["exposure"])).abs().max() < 1e-12


def test_low_exposure_bias_correction_does_not_explode_beyond_clamp() -> None:
    frame = pd.DataFrame(
        {
            "zone_id": ["low", "mid", "high"],
            "time_window_start": pd.to_datetime(
                [
                    "2023-11-20T06:00:00+05:30",
                    "2023-11-20T06:00:00+05:30",
                    "2023-11-20T06:00:00+05:30",
                ]
            ),
            "police_station": ["station_1", "station_1", "station_1"],
            "exposure": [0.001, 0.5, 1.0],
            "observed_pfdi": [100.0, 100.0, 100.0],
        }
    )

    scored = compute_coverage_gap(frame)

    assert scored.loc[0, "exposure_bias_correction_factor"] <= 1.50
    assert scored.loc[0, "bias_corrected_pfdi"] <= 150.0
    assert scored.loc[2, "exposure_bias_correction_factor"] >= 0.70


def test_zero_window_weight_uses_exposure_over_p75() -> None:
    scored = compute_coverage_gap(_visibility_frame())

    assert scored["zero_window_weight"].between(0, 1).all()
    assert scored.sort_values("exposure").iloc[0]["zero_window_weight"] <= scored.sort_values(
        "exposure"
    ).iloc[-1]["zero_window_weight"]


def test_zone_time_visibility_inputs_aggregate_raw_records() -> None:
    raw = pd.DataFrame(
        {
            "zone_id": ["zone_a", "zone_a", "zone_b"],
            "created_datetime_ist": [
                "2023-11-20T08:00:00+05:30",
                "2023-11-20T08:30:00+05:30",
                "2023-11-20T09:00:00+05:30",
            ],
            "police_station": ["station_1", "station_1", "station_2"],
            "device_id": ["device_1", "device_2", "device_3"],
            "created_by_id": ["user_1", "user_1", "user_2"],
            "data_sent_to_scita": [True, False, True],
            "validation_status": ["approved", "unknown", "rejected"],
            "row_obstruction_score": [10.0, 20.0, 30.0],
            "patrol_route_coverage": [0.2, 0.4, 0.6],
        }
    )

    zone_time = build_zone_time_visibility_inputs(raw)
    zone_a = zone_time[zone_time["zone_id"] == "zone_a"].iloc[0]

    assert zone_a["unique_device_count"] == 2
    assert zone_a["unique_created_by_user_count"] == 1
    assert zone_a["observed_pfdi"] == pytest.approx(30.0)
    assert zone_a["scita_success_rate"] == pytest.approx(0.5)
    assert zone_a["validation_coverage"] == pytest.approx(0.5)


def _blindspot_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "zone_id": ["zone_a", "zone_b", "zone_c"],
            "time_window_start": pd.to_datetime(
                [
                    "2023-11-20T08:00:00+05:30",
                    "2023-11-20T17:00:00+05:30",
                    "2023-11-20T17:00:00+05:30",
                ]
            ),
            "p90_historical_pfdi": [20.0, 90.0, 10.0],
            "recurrence": [0.2, 0.9, 0.1],
            "location_criticality": [0.2, 0.8, 0.1],
            "large_vehicle_share": [0.1, 0.7, 0.0],
            "persistence_score": [0.0, 0.8, 0.0],
            "junction_basin_pfdi": [0.0, 50.0, 0.0],
            "corridor_recent_pfdi": [0.0, 80.0, 0.0],
            "near_patrol_but_uncovered_flag": [False, True, False],
            "exposure": [0.8, 0.05, 0.9],
            "coverage_gap": [0.2, 0.95, 0.1],
            "observed_record_count": [20, 0, 10],
            "hidden_no_junction_spillover_count": [0, 2, 0],
        }
    )


def test_blindspot_risk_is_clamped_and_has_explanations() -> None:
    scored = add_blindspot_risk_features(_blindspot_frame())
    high_risk = scored[scored["zone_id"] == "zone_b"].iloc[0]

    assert scored["static_potential"].between(0, 1).all()
    assert scored["blindspot_risk"].between(0, 100).all()
    assert bool(high_risk["high_static_potential"]) is True
    assert bool(high_risk["low_enforcement_visibility"]) is True
    assert bool(high_risk["evening_peak_audit"]) is True
    assert bool(high_risk["near_patrol_but_uncovered"]) is True
    assert bool(high_risk["hidden_junction_spillover"]) is True


def test_peak_priority_and_evening_severity_prior_are_operational_multipliers() -> None:
    frame = _blindspot_frame()
    peak_priority = compute_peak_priority(frame)
    evening_prior = compute_evening_severity_prior(frame)

    assert peak_priority.iloc[0] == pytest.approx(1.20)
    assert peak_priority.iloc[1] == pytest.approx(1.40)
    assert evening_prior.iloc[1] > 1.20
    assert evening_prior.iloc[1] <= 1.40
    assert evening_prior.iloc[2] == pytest.approx(1.0)


def test_blindspot_uncertainty_decreases_with_observations() -> None:
    scored = add_blindspot_risk_features(_blindspot_frame())

    zero_observation = scored[scored["zone_id"] == "zone_b"].iloc[0]
    many_observations = scored[scored["zone_id"] == "zone_a"].iloc[0]

    assert zero_observation["uncertainty"] > many_observations["uncertainty"]


def test_blindspot_features_save_into_zone_time_features(tmp_path) -> None:
    output_path = tmp_path / "zone_time_features.parquet"

    features = write_blindspot_zone_time_features(_blindspot_frame(), output_path)

    assert output_path.exists()
    persisted = pd.read_parquet(output_path)
    assert len(persisted) == len(features)
    assert "blindspot_risk" in persisted.columns
