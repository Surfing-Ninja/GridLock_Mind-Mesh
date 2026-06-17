"""Tests for Parking-Induced Flow Disruption Index scoring."""

from __future__ import annotations

import pytest

from curbflow.scoring.location_criticality import compute_location_criticality
from curbflow.scoring.pfdi import score_pfdi_rows
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


def _pfdi_frame(vehicle_type="CAR", violation_type="WRONG PARKING", validation_status="approved"):
    return __import__("pandas").DataFrame(
        {
            "vehicle_number": ["KA01AA0001"],
            "created_datetime_ist": ["2023-11-20T08:00:00+05:30"],
            "violation_type": [violation_type],
            "vehicle_type": [vehicle_type],
            "updated_vehicle_type": [""],
            "junction_name": ["No Junction"],
            "location": ["Residential Road"],
            "validation_status": [validation_status],
        }
    )


def test_row_score_increases_for_double_parking_vs_wrong_parking() -> None:
    wrong = score_pfdi_rows(_pfdi_frame(violation_type="WRONG PARKING"))
    double = score_pfdi_rows(_pfdi_frame(violation_type="DOUBLE PARKING"))

    assert double.loc[0, "row_obstruction_score"] > wrong.loc[0, "row_obstruction_score"]


def test_bus_obstruction_greater_than_car_greater_than_scooter() -> None:
    bus = score_pfdi_rows(_pfdi_frame(vehicle_type="BMTC BUS"))
    car = score_pfdi_rows(_pfdi_frame(vehicle_type="CAR"))
    scooter = score_pfdi_rows(_pfdi_frame(vehicle_type="SCOOTER"))

    assert bus.loc[0, "vehicle_obstruction"] > car.loc[0, "vehicle_obstruction"]
    assert car.loc[0, "vehicle_obstruction"] > scooter.loc[0, "vehicle_obstruction"]
    assert bus.loc[0, "row_obstruction_score"] > car.loc[0, "row_obstruction_score"]
    assert car.loc[0, "row_obstruction_score"] > scooter.loc[0, "row_obstruction_score"]


def test_rejected_validation_downweights_score() -> None:
    approved = score_pfdi_rows(_pfdi_frame(validation_status="approved"))
    rejected = score_pfdi_rows(_pfdi_frame(validation_status="rejected"))

    assert rejected.loc[0, "validation_confidence"] == pytest.approx(0.25)
    assert rejected.loc[0, "row_obstruction_score"] < approved.loc[0, "row_obstruction_score"]


def test_unknown_validation_is_not_treated_as_rejected() -> None:
    unknown = score_pfdi_rows(_pfdi_frame(validation_status="unknown"))
    rejected = score_pfdi_rows(_pfdi_frame(validation_status="rejected"))

    assert unknown.loc[0, "validation_confidence"] == pytest.approx(0.70)
    assert unknown.loc[0, "validation_confidence"] > rejected.loc[0, "validation_confidence"]
    assert unknown.loc[0, "row_obstruction_score"] > rejected.loc[0, "row_obstruction_score"]
