"""Tests for evidence-quality novel features."""

from __future__ import annotations

import pandas as pd
import pytest

from curbflow.features.novel_features import add_evidence_quality_features


def _evidence_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "device_id": ["device_good", "device_good", "device_bad", "device_bad"],
            "created_by_id": ["user_good", "user_good", "user_bad", "user_bad"],
            "police_station": ["station_a", "station_a", "station_b", "station_b"],
            "zone_id": ["zone_1", "zone_1", "zone_2", "zone_2"],
            "validation_status": ["approved", "approved", "rejected", "rejected"],
            "data_sent_to_scita": [True, True, False, False],
            "vehicle_type": ["car", "car", "car", "car"],
            "updated_vehicle_type": ["", "", "bus", "bus"],
        }
    )


def test_device_user_and_station_trust_reward_better_evidence() -> None:
    scored = add_evidence_quality_features(_evidence_frame())

    good = scored[scored["device_id"] == "device_good"].iloc[0]
    bad = scored[scored["device_id"] == "device_bad"].iloc[0]

    assert good["device_trust"] > bad["device_trust"]
    assert good["user_trust"] > bad["user_trust"]
    assert good["station_evidence_quality"] > bad["station_evidence_quality"]


def test_missing_device_and_user_ids_use_global_priors_without_nulls() -> None:
    frame = _evidence_frame()
    frame.loc[0, "device_id"] = pd.NA
    frame.loc[1, "created_by_id"] = pd.NA

    scored = add_evidence_quality_features(frame)

    assert scored["device_trust"].notna().all()
    assert scored["user_trust"].notna().all()
    assert scored["station_evidence_quality"].notna().all()
    assert scored["evidence_quality_score"].between(0, 1).all()


def test_type_correction_flag_only_when_updated_type_differs() -> None:
    frame = pd.DataFrame(
        {
            "device_id": ["d1", "d1", "d1"],
            "created_by_id": ["u1", "u1", "u1"],
            "police_station": ["s1", "s1", "s1"],
            "validation_status": ["approved", "approved", "approved"],
            "data_sent_to_scita": [True, True, True],
            "vehicle_type": ["car", "car", "car"],
            "updated_vehicle_type": ["car", "bus", ""],
        }
    )

    scored = add_evidence_quality_features(frame)

    assert scored["type_correction_flag"].tolist() == [False, True, False]


def test_evidence_quality_score_uses_required_formula() -> None:
    scored = add_evidence_quality_features(_evidence_frame())
    row = scored.iloc[0]

    expected = (
        0.50 * row["validation_confidence"]
        + 0.25 * row["device_trust"]
        + 0.15 * row["user_trust"]
        + 0.10 * row["station_evidence_quality"]
    )

    assert row["evidence_quality_score"] == pytest.approx(expected)


def test_zone_scita_success_rate_is_added_when_zone_exists() -> None:
    scored = add_evidence_quality_features(_evidence_frame())

    zone_1 = scored[scored["zone_id"] == "zone_1"].iloc[0]
    zone_2 = scored[scored["zone_id"] == "zone_2"].iloc[0]

    assert "zone_scita_success_rate" in scored.columns
    assert zone_1["zone_scita_success_rate"] == pytest.approx(1.0)
    assert zone_2["zone_scita_success_rate"] == pytest.approx(0.0)
