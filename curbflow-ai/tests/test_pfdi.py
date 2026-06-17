"""Tests for Parking-Induced Flow Disruption Index scoring."""

from __future__ import annotations

import pandas as pd
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
    return pd.DataFrame(
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


def test_evidence_quality_multiplier_rewards_high_trust_device() -> None:
    frame = pd.DataFrame(
        {
            "vehicle_number": [
                "KA01AA1001",
                "KA01AA1002",
                "KA01AA1003",
                "KA01AA2001",
                "KA01AA2002",
                "KA01AA2003",
            ],
            "created_datetime_ist": [
                "2023-11-20T08:00:00+05:30",
                "2023-11-20T08:05:00+05:30",
                "2023-11-20T08:10:00+05:30",
                "2023-11-20T08:15:00+05:30",
                "2023-11-20T08:20:00+05:30",
                "2023-11-20T08:25:00+05:30",
            ],
            "violation_type": ["WRONG PARKING"] * 6,
            "vehicle_type": ["CAR"] * 6,
            "updated_vehicle_type": [""] * 6,
            "junction_name": ["No Junction"] * 6,
            "location": ["Residential Road"] * 6,
            "validation_status": [
                "unknown",
                "approved",
                "approved",
                "unknown",
                "rejected",
                "rejected",
            ],
            "device_id": [
                "high_trust_device",
                "high_trust_device",
                "high_trust_device",
                "low_trust_device",
                "low_trust_device",
                "low_trust_device",
            ],
            "created_by_id": ["same_user"] * 6,
            "police_station": ["same_station"] * 6,
            "data_sent_to_scita": [True, True, True, False, False, False],
        }
    )

    scored = score_pfdi_rows(frame, compute_evidence_quality=True)

    assert scored.loc[0, "device_trust"] > scored.loc[3, "device_trust"]
    assert scored.loc[0, "row_obstruction_score"] > scored.loc[3, "row_obstruction_score"]


def test_unknown_device_uses_global_evidence_prior() -> None:
    frame = pd.DataFrame(
        {
            "vehicle_number": ["KA01AA3001", "KA01AA3002", "KA01AA3003"],
            "created_datetime_ist": [
                "2023-11-20T08:00:00+05:30",
                "2023-11-20T08:05:00+05:30",
                "2023-11-20T08:10:00+05:30",
            ],
            "violation_type": ["WRONG PARKING"] * 3,
            "vehicle_type": ["CAR"] * 3,
            "updated_vehicle_type": [""] * 3,
            "junction_name": ["No Junction"] * 3,
            "location": ["Residential Road"] * 3,
            "validation_status": ["unknown", "approved", "rejected"],
            "device_id": [pd.NA, "known_device", "known_device"],
            "created_by_id": ["known_user"] * 3,
            "police_station": ["known_station"] * 3,
            "data_sent_to_scita": [pd.NA, True, False],
        }
    )

    scored = score_pfdi_rows(frame, compute_evidence_quality=True)

    assert pd.notna(scored.loc[0, "device_trust"])
    assert pd.notna(scored.loc[0, "evidence_quality_score"])
    assert scored.loc[0, "pfdi_quality_multiplier"] == pytest.approx(
        scored.loc[0, "evidence_quality_score"]
    )


def test_rejected_validation_still_downweights_score_with_evidence_quality() -> None:
    frame = pd.DataFrame(
        {
            "vehicle_number": ["KA01AA4001", "KA01AA4002"],
            "created_datetime_ist": [
                "2023-11-20T08:00:00+05:30",
                "2023-11-20T08:05:00+05:30",
            ],
            "violation_type": ["WRONG PARKING", "WRONG PARKING"],
            "vehicle_type": ["CAR", "CAR"],
            "updated_vehicle_type": ["", ""],
            "junction_name": ["No Junction", "No Junction"],
            "location": ["Residential Road", "Residential Road"],
            "validation_status": ["approved", "rejected"],
            "device_id": ["same_device", "same_device"],
            "created_by_id": ["same_user", "same_user"],
            "police_station": ["same_station", "same_station"],
            "data_sent_to_scita": [True, True],
        }
    )

    scored = score_pfdi_rows(frame, compute_evidence_quality=True)

    assert scored.loc[1, "validation_confidence"] == pytest.approx(0.25)
    assert scored.loc[1, "evidence_quality_score"] < scored.loc[0, "evidence_quality_score"]
    assert scored.loc[1, "row_obstruction_score"] < scored.loc[0, "row_obstruction_score"]
