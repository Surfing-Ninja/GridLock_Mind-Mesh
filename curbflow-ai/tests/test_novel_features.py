"""Tests for evidence-quality novel features."""

from __future__ import annotations

import pandas as pd
import pytest

from curbflow.features.novel_features import (
    add_evidence_quality_features,
    add_hidden_junction_basin_features,
    build_junction_basin_table,
    compute_patrol_myopia_table,
    normalized_zone_entropy,
    write_patrol_myopia_table,
    write_junction_basin_table,
)


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


def _junction_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "junction_name": [
                "Silk Board",
                "Silk Board",
                "No Junction",
                "No Junction",
            ],
            "latitude": [12.9172, 12.9174, 12.9173, 12.9300],
            "longitude": [77.6234, 77.6236, 77.6235, 77.6500],
            "zone_id": ["zone_a", "zone_a", "zone_a", "zone_b"],
            "created_datetime_ist": [
                "2023-11-20T08:00:00+05:30",
                "2023-11-20T08:05:00+05:30",
                "2023-11-20T08:10:00+05:30",
                "2023-11-20T08:15:00+05:30",
            ],
            "row_obstruction_score": [10.0, 20.0, 30.0, 40.0],
        }
    )


def test_named_junction_rows_map_to_themselves() -> None:
    scored = add_hidden_junction_basin_features(_junction_frame())

    assert scored.loc[0, "hidden_junction_id"] == "silk board"
    assert scored.loc[0, "hidden_junction_weight"] == pytest.approx(1.0)
    assert scored.loc[0, "nearest_named_junction_distance_m"] == pytest.approx(0.0)


def test_no_junction_rows_within_500m_get_assigned() -> None:
    scored = add_hidden_junction_basin_features(_junction_frame())

    assert scored.loc[2, "hidden_junction_id"] == "silk board"
    assert scored.loc[2, "nearest_named_junction_distance_m"] <= 500.0
    assert 0.0 < scored.loc[2, "hidden_junction_weight"] < 1.0


def test_no_junction_rows_beyond_threshold_remain_null() -> None:
    scored = add_hidden_junction_basin_features(_junction_frame())

    assert pd.isna(scored.loc[3, "hidden_junction_id"])
    assert scored.loc[3, "nearest_named_junction_distance_m"] > 500.0
    assert scored.loc[3, "hidden_junction_weight"] == pytest.approx(0.0)


def test_junction_basin_table_computes_zone_time_spillover_fields() -> None:
    scored = add_hidden_junction_basin_features(_junction_frame())
    basin_table = build_junction_basin_table(scored)
    silk_board_zone = basin_table[
        (basin_table["zone_id"] == "zone_a")
        & (basin_table["hidden_junction_id"] == "silk board")
    ].iloc[0]

    assert silk_board_zone["junction_basin_raw_impact"] > 2.0
    assert silk_board_zone["junction_basin_pfdi"] > 30.0
    assert silk_board_zone["hidden_no_junction_spillover_count"] == 1
    assert silk_board_zone["hidden_no_junction_spillover_impact"] > 0.0


def test_junction_basin_table_can_be_saved_to_parquet(tmp_path) -> None:
    output_path = tmp_path / "junction_basins.parquet"

    basin_table = write_junction_basin_table(_junction_frame(), output_path)

    assert output_path.exists()
    assert len(pd.read_parquet(output_path)) == len(basin_table)


def test_normalized_zone_entropy_reflects_concentration() -> None:
    concentrated = normalized_zone_entropy(pd.Series([10, 0, 0]))
    balanced = normalized_zone_entropy(pd.Series([10, 10, 10]))

    assert concentrated == pytest.approx(0.0)
    assert balanced == pytest.approx(1.0)


def _patrol_myopia_frame() -> pd.DataFrame:
    focused_records = []
    for index in range(20):
        focused_records.append(
            {
                "police_station": "Focused Station",
                "zone_id": "zone_hot" if index < 10 else f"zone_{index}",
                "created_datetime_ist": f"2023-11-20T{8 + index % 4:02d}:00:00+05:30",
                "device_id": "device_one",
                "created_by_id": "user_one",
            }
        )
    balanced_records = []
    for index in range(20):
        hour = 8 if index < 10 else 17
        balanced_records.append(
            {
                "police_station": "Balanced Station",
                "zone_id": f"zone_{index}",
                "created_datetime_ist": f"2023-11-20T{hour:02d}:00:00+05:30",
                "device_id": f"device_{index}",
                "created_by_id": f"user_{index}",
            }
        )
    return pd.DataFrame(focused_records + balanced_records)


def test_patrol_myopia_score_rises_for_concentrated_morning_patrols() -> None:
    table = compute_patrol_myopia_table(_patrol_myopia_frame())
    focused = table[table["police_station"] == "focused station"].iloc[0]
    balanced = table[table["police_station"] == "balanced station"].iloc[0]

    assert focused["patrol_myopia_index"] > balanced["patrol_myopia_index"]
    assert focused["top_10_zone_share"] == pytest.approx(19 / 20)
    assert focused["morning_bias"] == pytest.approx(1.0)
    assert focused["patrol_myopia_level"] == "High"


def test_patrol_myopia_table_can_be_saved_to_parquet(tmp_path) -> None:
    output_path = tmp_path / "patrol_myopia.parquet"

    table = write_patrol_myopia_table(_patrol_myopia_frame(), output_path)

    assert output_path.exists()
    assert len(pd.read_parquet(output_path)) == len(table)
