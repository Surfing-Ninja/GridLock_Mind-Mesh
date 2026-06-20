"""Tests for parsing multi-label violation fields."""

from __future__ import annotations

import pytest

from curbflow.scoring.severity import compound_violation_severity, score_violation_severity
from curbflow.scoring.violation_parser import parse_violation_labels


def test_json_like_list_strings_are_parsed() -> None:
    labels = parse_violation_labels('["WRONG PARKING","PARKING IN A MAIN ROAD"]')

    assert labels == ["wrong_parking", "parking_in_main_road"]


def test_comma_separated_strings_are_parsed() -> None:
    labels = parse_violation_labels("NO PARKING, PARKING NEAR ROAD CROSSING")

    assert labels == ["no_parking", "parking_near_road_crossing"]


def test_single_strings_are_parsed() -> None:
    labels = parse_violation_labels("Parking on Footpath")

    assert labels == ["parking_on_footpath"]


def test_unknown_strings_map_to_minor_other() -> None:
    labels = parse_violation_labels("some local parking note")

    assert labels == ["minor_other"]


def test_wrong_parking_severity_uses_config_weight() -> None:
    score = score_violation_severity("wrong parking")

    assert score == pytest.approx(0.65)


def test_compounding_formula_for_multi_label_violations() -> None:
    score = compound_violation_severity(["wrong_parking", "parking_in_main_road"])

    assert score == pytest.approx(0.9825)
