"""Tests ensuring repeat pressure uses only previous vehicle history."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from curbflow.scoring.repeat_pressure import add_repeat_pressure_features


def test_first_occurrence_has_zero_repeat_pressure() -> None:
    frame = pd.DataFrame(
        {
            "vehicle_number": ["KA01AA0001"],
            "created_datetime_ist": ["2023-11-20T08:00:00+05:30"],
        }
    )

    scored = add_repeat_pressure_features(frame)

    assert scored.loc[0, "previous_vehicle_count"] == 0
    assert scored.loc[0, "repeat_pressure"] == 0


def test_second_occurrence_has_positive_repeat_pressure() -> None:
    frame = pd.DataFrame(
        {
            "vehicle_number": ["KA01AA0001", "KA01AA0001"],
            "created_datetime_ist": [
                "2023-11-20T08:00:00+05:30",
                "2023-11-20T09:00:00+05:30",
            ],
        }
    )

    scored = add_repeat_pressure_features(frame)

    assert scored.loc[1, "previous_vehicle_count"] == 1
    assert scored.loc[1, "repeat_pressure"] == pytest.approx(math.log(2) / math.log(11))


def test_future_rows_do_not_affect_earlier_rows() -> None:
    frame = pd.DataFrame(
        {
            "vehicle_number": ["KA01AA0001", "KA01AA0001", "KA01AA0001"],
            "created_datetime_ist": [
                "2023-11-20T08:00:00+05:30",
                "2023-11-20T09:00:00+05:30",
                "2023-11-20T10:00:00+05:30",
            ],
        }
    )

    scored = add_repeat_pressure_features(frame)

    assert scored.loc[0, "previous_vehicle_count"] == 0
    assert scored.loc[0, "repeat_pressure"] == 0
    assert scored.loc[2, "previous_vehicle_count"] == 2


def test_sorting_works_when_input_is_shuffled() -> None:
    frame = pd.DataFrame(
        {
            "vehicle_number": ["KA01AA0001", "KA01AA0001", "KA01AA0001"],
            "created_datetime_ist": [
                "2023-11-20T10:00:00+05:30",
                "2023-11-20T08:00:00+05:30",
                "2023-11-20T09:00:00+05:30",
            ],
        }
    )

    scored = add_repeat_pressure_features(frame)

    assert scored.loc[1, "previous_vehicle_count"] == 0
    assert scored.loc[2, "previous_vehicle_count"] == 1
    assert scored.loc[0, "previous_vehicle_count"] == 2


def test_optional_zone_station_and_day_previous_counts() -> None:
    frame = pd.DataFrame(
        {
            "vehicle_number": ["KA01AA0001", "KA01AA0001", "KA01AA0001"],
            "created_datetime_ist": [
                "2023-11-20T08:00:00+05:30",
                "2023-11-20T09:00:00+05:30",
                "2023-11-21T09:00:00+05:30",
            ],
            "zone_id": ["z1", "z1", "z2"],
            "police_station": ["station-a", "station-a", "station-a"],
        }
    )

    scored = add_repeat_pressure_features(frame)

    assert scored.loc[1, "previous_same_zone_count"] == 1
    assert scored.loc[2, "previous_same_zone_count"] == 0
    assert scored.loc[2, "previous_station_count"] == 2
    assert scored.loc[2, "previous_day_count"] == 0
