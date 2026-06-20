"""Tests for UTC parsing, cleaning defaults, and safe invalid timestamp handling."""

from __future__ import annotations

import pandas as pd

from curbflow.data.audit import AuditOutputPaths, build_audit_summary, run_data_audit
from curbflow.data.clean import clean_violations
from curbflow.data.time_utils import convert_utc_to_ist


def _minimum_raw_frame(**overrides: object) -> pd.DataFrame:
    data = {
        "latitude": ["12.9716"],
        "longitude": ["77.5946"],
        "created_datetime": ["2023-11-20 00:28:46+00"],
        "police_station": ["  Upparpet  "],
        "junction_name": [" No Junction "],
        "location": [" MG Road  Bengaluru "],
        "vehicle_type": [" CAR "],
        "updated_vehicle_type": [pd.NA],
        "validation_status": [pd.NA],
        "data_sent_to_scita": ["true"],
        "closed_datetime": [pd.NA],
        "action_taken_timestamp": [pd.NA],
        "description": [pd.NA],
    }
    data.update(overrides)
    target_len = max(len(value) for value in data.values() if isinstance(value, list))
    data = {
        key: value * target_len if isinstance(value, list) and len(value) == 1 and target_len > 1 else value
        for key, value in data.items()
    }
    return pd.DataFrame(data)


def test_created_datetime_utc_converts_to_ist() -> None:
    converted = convert_utc_to_ist(pd.Series(["2023-11-20 00:28:46+00"]))

    assert str(converted.iloc[0]) == "2023-11-20 05:58:46+05:30"


def test_validation_status_nan_becomes_unknown() -> None:
    clean = clean_violations(_minimum_raw_frame(validation_status=[pd.NA]))

    assert clean.loc[0, "validation_status"] == "unknown"


def test_invalid_timestamps_are_handled_safely() -> None:
    clean = clean_violations(_minimum_raw_frame(created_datetime=["not-a-date"]))

    assert pd.isna(clean.loc[0, "created_datetime_ist"])
    assert pd.isna(clean.loc[0, "hour"])
    assert pd.isna(clean.loc[0, "minute"])
    assert pd.isna(clean.loc[0, "day_of_week"])
    assert pd.isna(clean.loc[0, "is_weekend"])


def test_audit_calculates_operational_windows_and_breakdowns() -> None:
    clean = clean_violations(
        _minimum_raw_frame(
            latitude=["12.1", "12.2", "12.3"],
            longitude=["77.1", "77.2", "77.3"],
            created_datetime=[
                "2023-11-20 02:00:00+00",
                "2023-11-20 10:00:00+00",
                "2023-11-20 14:59:00+00",
            ],
            police_station=["A", "A", "B"],
            junction_name=["J1", "J2", "J2"],
            vehicle_type=["CAR", "CAR", "SCOOTER"],
            validation_status=[pd.NA, "approved", "rejected"],
            data_sent_to_scita=["true", "false", "true"],
            device_id=["d1", "d1", "d2"],
            created_by_id=["u1", "u2", "u2"],
            closed_datetime=[pd.NA, pd.NA, pd.NA],
            action_taken_timestamp=[pd.NA, pd.NA, pd.NA],
            description=[pd.NA, pd.NA, pd.NA],
        )
    )

    summary = build_audit_summary(clean)

    assert summary["total_rows"] == 3
    assert summary["morning_count_0730_1530"] == 1
    assert summary["evening_count_1530_2030"] == 2
    assert summary["evening_gap_ratio_morning_over_evening"] == 0.5
    assert summary["fully_null_columns"]["description"] is True
    assert summary["validation_status_breakdown"]["including_unknown"]["unknown"] == 1
    assert "unknown" not in summary["validation_status_breakdown"]["non_unknown_only"]
    assert summary["data_sent_to_scita_rate"] == 2 / 3
    assert summary["device_user_counts"]["device_id_unique"] == 2
    assert summary["top_zone_concentration"]["available"] is False
    assert summary["patrol_myopia"]["available"] is False


def test_audit_summary_includes_patrol_myopia_when_zones_exist() -> None:
    clean = clean_violations(
        _minimum_raw_frame(
            latitude=["12.1", "12.2", "12.3", "12.4"],
            longitude=["77.1", "77.2", "77.3", "77.4"],
            created_datetime=[
                "2023-11-20 02:00:00+00",
                "2023-11-20 03:00:00+00",
                "2023-11-20 12:00:00+00",
                "2023-11-20 13:00:00+00",
            ],
            police_station=["A", "A", "B", "B"],
            junction_name=["J1", "No Junction", "J2", "No Junction"],
            zone_id=["z1", "z1", "z2", "z3"],
            device_id=["d1", "d1", "d2", "d3"],
            created_by_id=["u1", "u1", "u2", "u3"],
        )
    )

    summary = build_audit_summary(clean)

    assert summary["patrol_myopia"]["available"] is True
    assert summary["patrol_myopia"]["station_count"] == 2
    assert summary["patrol_myopia"]["max_patrol_myopia_index"] > 0


def test_run_data_audit_writes_expected_artifacts(tmp_path) -> None:
    clean = clean_violations(_minimum_raw_frame())
    clean_path = tmp_path / "violations_clean.parquet"
    clean.to_parquet(clean_path, index=False)

    outputs = AuditOutputPaths(
        data_quality_report=tmp_path / "data_quality_report.md",
        bias_audit_report=tmp_path / "bias_audit_report.md",
        eda_summary=tmp_path / "eda_summary.json",
        coverage_audit=tmp_path / "coverage_audit.parquet",
    )
    run_data_audit(clean_parquet_path=clean_path, output_paths=outputs)

    data_quality_text = outputs.data_quality_report.read_text()
    bias_text = outputs.bias_audit_report.read_text()
    coverage = pd.read_parquet(outputs.coverage_audit)

    assert "This dataset is an enforcement visibility dataset" in data_quality_text
    assert "No challan should not be interpreted as no illegal parking." in bias_text
    assert "Evening windows are evidence-poor" in bias_text
    assert outputs.eda_summary.exists()
    assert bool(coverage.loc[0, "top_zone_concentration_available"]) is False
