"""Tests for Parking-Induced Flow Disruption Index scoring."""

from __future__ import annotations

import pytest

from curbflow.scoring.location_criticality import compute_location_criticality
from curbflow.scoring.vehicle_obstruction import score_vehicle_obstruction


@pytest.mark.parametrize(
    ("vehicle_type", "updated_vehicle_type", "expected"),
    [
        ("CAR", "", 0.75),
        ("CAR", "HGV", 1.00),
        ("Tempo", None, 0.90),
        ("Maxi Cab", None, 0.85),
        ("Goods Auto", None, 0.65),
        ("Passenger Auto", None, 0.58),
        ("Motorcycle", None, 0.35),
        ("Moped", None, 0.25),
        ("Unmapped Vehicle", None, 0.60),
    ],
)
def test_vehicle_obstruction_weights(vehicle_type, updated_vehicle_type, expected) -> None:
    assert score_vehicle_obstruction(vehicle_type, updated_vehicle_type) == pytest.approx(expected)


def test_location_criticality_named_junction_only() -> None:
    score = compute_location_criticality(
        junction_name="Town Hall Junction",
        location="",
        parsed_labels=[],
    )

    assert score == pytest.approx(0.35)


def test_location_criticality_no_junction_is_zero_for_junction_flag() -> None:
    score = compute_location_criticality(
        junction_name="No Junction",
        location="",
        parsed_labels=[],
    )

    assert score == pytest.approx(0.0)


def test_location_criticality_combines_text_and_parsed_label_flags() -> None:
    score = compute_location_criticality(
        junction_name="Silk Board",
        location="Outer Ring Road near signal and college bus stop",
        parsed_labels=["double_parking"],
    )

    assert score == pytest.approx(1.0)


def test_location_criticality_uses_violation_labels_for_flags() -> None:
    score = compute_location_criticality(
        junction_name="No Junction",
        location="Residential layout",
        violation_type='["PARKING IN A MAIN ROAD","PARKING NEAR ROAD CROSSING"]',
    )

    assert score == pytest.approx(0.45)
