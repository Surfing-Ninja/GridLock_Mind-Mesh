"""Tests for evidence-quality novel features."""

from __future__ import annotations

import pandas as pd
import pytest

from curbflow.features.novel_features import (
    add_evidence_quality_features,
    add_hidden_junction_basin_features,
    add_place_type_and_road_corridor_features,
    add_place_type_features,
    add_repeat_vehicle_features,
    build_junction_basin_table,
    build_road_corridor_zone_time_features,
    compute_patrol_myopia_table,
    extract_road_name,
    normalized_zone_entropy,
    write_patrol_myopia_table,
    write_repeat_vehicle_zone_time_table,
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


def test_evidence_quality_uses_bayesian_smoothed_rates() -> None:
    scored = add_evidence_quality_features(_evidence_frame(), alpha=10.0)
    good = scored[scored["device_id"] == "device_good"].iloc[0]

    expected_approval_rate = (2 + 10 * 0.5) / (2 + 10)
    expected_reject_rate = (0 + 10 * 0.5) / (2 + 10)
    expected_trust = (
        0.45 * expected_approval_rate
        + 0.25 * (1 - expected_reject_rate)
        + 0.15 * (1 - 0.0)
        + 0.15 * 1.0
    )

    assert good["device_approval_rate"] == pytest.approx(expected_approval_rate)
    assert good["device_reject_rate"] == pytest.approx(expected_reject_rate)
    assert good["device_trust"] == pytest.approx(expected_trust)


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
    expected_focused = (
        0.40 * focused["top_10_zone_share"]
        + 0.30 * focused["morning_bias"]
        + 0.20 * (1 - focused["zone_coverage_entropy"])
        + 0.10 * (1 - focused["device_diversity"])
    )

    assert focused["patrol_myopia_index"] > balanced["patrol_myopia_index"]
    assert focused["patrol_myopia_index"] == pytest.approx(expected_focused)
    assert focused["top_10_zone_share"] == pytest.approx(19 / 20)
    assert focused["morning_bias"] == pytest.approx(1.0)
    assert focused["patrol_myopia_level"] == "High"


def test_patrol_myopia_table_can_be_saved_to_parquet(tmp_path) -> None:
    output_path = tmp_path / "patrol_myopia.parquet"

    table = write_patrol_myopia_table(_patrol_myopia_frame(), output_path)

    assert output_path.exists()
    assert len(pd.read_parquet(output_path)) == len(table)


def _repeat_vehicle_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "vehicle_number": [
                "KA01AA0001",
                "KA01AA0002",
                "KA01AA0001",
                "KA01AA0001",
                "KA01AA0002",
                "KA01AA0003",
            ],
            "created_datetime_ist": [
                "2023-11-20T08:00:00+05:30",
                "2023-11-20T08:30:00+05:30",
                "2023-11-20T10:00:00+05:30",
                "2023-11-20T13:00:00+05:30",
                "2023-11-20T16:00:00+05:30",
                "2023-11-20T17:00:00+05:30",
            ],
            "zone_id": ["zone_a", "zone_a", "zone_a", "zone_b", "zone_a", "zone_c"],
            "police_station": [
                "station_1",
                "station_1",
                "station_1",
                "station_2",
                "station_1",
                "station_3",
            ],
        }
    )


def test_repeat_vehicle_features_count_repeated_vehicles_correctly() -> None:
    scored = add_repeat_vehicle_features(_repeat_vehicle_frame())
    vehicle_1 = scored[scored["vehicle_number"] == "KA01AA0001"].iloc[0]
    vehicle_3 = scored[scored["vehicle_number"] == "KA01AA0003"].iloc[0]

    assert bool(vehicle_1["repeat_vehicle_flag"]) is True
    assert vehicle_1["vehicle_total_records"] == 3
    assert vehicle_1["vehicle_unique_zones"] == 2
    assert vehicle_1["vehicle_unique_stations"] == 2
    assert bool(vehicle_1["multi_zone_repeat_flag"]) is True
    assert bool(vehicle_1["multi_station_repeat_flag"]) is True
    assert bool(vehicle_3["repeat_vehicle_flag"]) is False
    assert pd.notna(vehicle_1["anonymized_vehicle_id"])
    assert vehicle_1["anonymized_vehicle_id"] != "KA01AA0001"


def test_repeat_vehicle_features_do_not_leak_future_rows() -> None:
    shuffled = pd.DataFrame(
        {
            "vehicle_number": ["KA01AA9999", "KA01AA9999"],
            "created_datetime_ist": [
                "2023-11-20T14:00:00+05:30",
                "2023-11-20T08:00:00+05:30",
            ],
            "zone_id": ["zone_a", "zone_a"],
            "police_station": ["station_1", "station_1"],
        }
    )

    scored = add_repeat_vehicle_features(shuffled)

    assert bool(scored.loc[1, "same_vehicle_same_zone_repeat_6h"]) is False
    assert bool(scored.loc[0, "same_vehicle_same_zone_repeat_6h"]) is True


def test_repeat_vehicle_six_hour_same_and_different_zone_logic() -> None:
    scored = add_repeat_vehicle_features(_repeat_vehicle_frame())

    assert bool(scored.loc[2, "same_vehicle_same_zone_repeat_6h"]) is True
    assert bool(scored.loc[2, "same_vehicle_different_zone_6h"]) is False
    assert bool(scored.loc[3, "same_vehicle_same_zone_repeat_6h"]) is False
    assert bool(scored.loc[3, "same_vehicle_different_zone_6h"]) is True
    assert bool(scored.loc[4, "same_vehicle_same_zone_repeat_6h"]) is False


def test_repeat_vehicle_zone_time_aggregate_excludes_vehicle_ids(tmp_path) -> None:
    output_path = tmp_path / "repeat_vehicle_zone_time.parquet"

    table = write_repeat_vehicle_zone_time_table(_repeat_vehicle_frame(), output_path)
    zone_a_repeat_window = table[
        (table["zone_id"] == "zone_a")
        & (table["time_window_start"] == pd.Timestamp("2023-11-20T09:00:00+05:30"))
    ].iloc[0]

    assert output_path.exists()
    assert "anonymized_vehicle_id" not in table.columns
    assert "vehicle_number" not in table.columns
    assert zone_a_repeat_window["repeat_vehicle_count"] == 1
    assert zone_a_repeat_window["repeat_vehicle_share"] == pytest.approx(1.0)
    assert zone_a_repeat_window["same_vehicle_same_zone_6h_count"] == 1
    assert zone_a_repeat_window["persistence_score"] == pytest.approx(1.0)
    assert 0.0 <= zone_a_repeat_window["repeat_vehicle_zone_entropy"] <= 1.0


def test_place_type_flags_and_priority_use_location_and_junction_text() -> None:
    frame = pd.DataFrame(
        {
            "location": [
                "Metro station near shopping mall",
                "City Hospital Main Road",
                "Temple Layout",
                "Unknown stretch",
            ],
            "junction_name": [
                "Terminal Junction",
                "College Signal",
                "Mandir Cross",
                "No Junction",
            ],
        }
    )

    scored = add_place_type_features(frame)

    assert bool(scored.loc[0, "transit_node"]) is True
    assert bool(scored.loc[0, "commercial_market"]) is True
    assert scored.loc[0, "place_type_primary"] == "transit"
    assert bool(scored.loc[1, "institutional"]) is True
    assert scored.loc[1, "place_type_primary"] == "institutional"
    assert bool(scored.loc[2, "religious_place"]) is True
    assert bool(scored.loc[2, "residential_layout"]) is True
    assert scored.loc[2, "place_type_primary"] == "religious"
    assert scored.loc[3, "place_type_primary"] == "unknown"


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("#42 MG Rd., Bengaluru", "mg road"),
        ("No. 12/4 Outer Ring Rd, Near Mall", "outer ring road"),
        ("100 Feet Road, Indiranagar", "feet road"),
        ("  Brigade ROAD!!!, signal", "brigade road"),
        (pd.NA, "unknown"),
    ],
)
def test_road_name_extraction_normalizes_first_location_segment(location, expected) -> None:
    assert extract_road_name(location) == expected


def _place_corridor_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "zone_id": ["zone_a", "zone_a", "zone_a", "zone_b"],
            "location": [
                "MG Rd, Commercial Market",
                "MG Road, Metro Station",
                "Outer Ring Rd, School",
                "Outer Ring Road, Airport",
            ],
            "junction_name": [
                "Mall Junction",
                "Metro Junction",
                "College Signal",
                "Airport Terminal",
            ],
            "vehicle_type": ["car", "BMTC bus", "lorry", "scooter"],
            "updated_vehicle_type": ["", "", "", ""],
            "violation_type": [
                "WRONG PARKING",
                "PARKING IN A MAIN ROAD",
                "PARKING IN A MAIN ROAD",
                "WRONG PARKING",
            ],
            "row_obstruction_score": [10.0, 20.0, 30.0, 40.0],
            "created_datetime_ist": [
                "2023-11-20T08:00:00+05:30",
                "2023-11-21T08:00:00+05:30",
                "2023-11-22T08:00:00+05:30",
                "2023-12-05T08:00:00+05:30",
            ],
        }
    )


def test_road_corridor_features_compute_corridor_stats() -> None:
    scored = add_place_type_and_road_corridor_features(_place_corridor_frame())
    mg = scored[scored["road_corridor_id"] == "mg road"].iloc[0]
    outer_ring = scored[scored["road_corridor_id"] == "outer ring road"].iloc[0]

    assert mg["corridor_record_count"] == 2
    assert mg["corridor_pfdi"] == pytest.approx(30.0)
    assert mg["corridor_large_vehicle_share"] == pytest.approx(0.5)
    assert mg["corridor_main_road_parking_share"] == pytest.approx(0.5)
    assert mg["corridor_recent_pfdi"] == pytest.approx(0.0)
    assert scored.loc[1, "corridor_rolling_7d_pfdi"] == pytest.approx(30.0)
    assert outer_ring["corridor_recent_pfdi"] == pytest.approx(40.0)


def test_road_corridor_zone_time_features_include_place_context() -> None:
    zone_time = build_road_corridor_zone_time_features(_place_corridor_frame())
    mg_morning = zone_time[
        (zone_time["zone_id"] == "zone_a")
        & (zone_time["road_corridor_id"] == "mg road")
        & (zone_time["place_type_primary"] == "commercial")
    ].iloc[0]

    assert bool(mg_morning["commercial_market"]) is True
    assert "corridor_recent_pfdi" in zone_time.columns
    assert "place_type_primary" in zone_time.columns
    assert "road_corridor_id" in zone_time.columns
