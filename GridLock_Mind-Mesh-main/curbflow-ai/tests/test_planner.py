"""Tests for exploit/explore planner scoring and resource allocation."""

from __future__ import annotations

import pandas as pd

from curbflow.planner.optimizer import plan_enforcement


def _planner_frame() -> pd.DataFrame:
    window = pd.Timestamp("2024-01-01 15:30:00")
    return pd.DataFrame(
        [
            {
                "zone_id": "known_1",
                "window_start": window,
                "police_station": "station_a",
                "predicted_pfdi": 92,
                "hotspot_probability": 0.92,
                "coverage_gap": 0.15,
                "blindspot_risk_score": 12,
                "static_potential": 0.20,
                "exploit_score": 95,
                "explore_score": 10,
                "large_vehicle_share": 0.10,
                "double_parking_share": 0.05,
                "main_road_parking_share": 0.12,
            },
            {
                "zone_id": "known_2",
                "window_start": window,
                "police_station": "station_a",
                "predicted_pfdi": 86,
                "hotspot_probability": 0.82,
                "coverage_gap": 0.20,
                "blindspot_risk_score": 15,
                "static_potential": 0.25,
                "exploit_score": 88,
                "explore_score": 12,
                "large_vehicle_share": 0.12,
                "double_parking_share": 0.08,
                "main_road_parking_share": 0.14,
            },
            {
                "zone_id": "tow_1",
                "window_start": window,
                "police_station": "station_a",
                "predicted_pfdi": 84,
                "hotspot_probability": 0.76,
                "coverage_gap": 0.30,
                "blindspot_risk_score": 18,
                "static_potential": 0.35,
                "exploit_score": 84,
                "explore_score": 20,
                "large_vehicle_share": 0.45,
                "double_parking_share": 0.25,
                "main_road_parking_share": 0.40,
            },
            {
                "zone_id": "blind_1",
                "window_start": window,
                "police_station": "station_a",
                "predicted_pfdi": 25,
                "hotspot_probability": 0.20,
                "coverage_gap": 0.88,
                "blindspot_risk_score": 93,
                "static_potential": 0.92,
                "exploit_score": 20,
                "explore_score": 96,
                "near_patrol_but_uncovered_flag": True,
            },
            {
                "zone_id": "blind_2",
                "window_start": window,
                "police_station": "station_a",
                "predicted_pfdi": 22,
                "hotspot_probability": 0.18,
                "coverage_gap": 0.86,
                "blindspot_risk_score": 90,
                "static_potential": 0.90,
                "exploit_score": 18,
                "explore_score": 92,
                "near_patrol_but_uncovered_flag": True,
            },
            {
                "zone_id": "blind_3",
                "window_start": window,
                "police_station": "station_a",
                "predicted_pfdi": 20,
                "hotspot_probability": 0.16,
                "coverage_gap": 0.84,
                "blindspot_risk_score": 88,
                "static_potential": 0.88,
                "exploit_score": 16,
                "explore_score": 90,
                "near_patrol_but_uncovered_flag": True,
            },
        ]
    )


def test_planner_respects_officer_limit() -> None:
    recommendations = plan_enforcement(
        _planner_frame(),
        window_start="2024-01-01 15:30:00",
        available_officers=3,
        available_tow_units=1,
        mode="balanced",
    )

    assert recommendations["officers_required"].sum() <= 3


def test_planner_respects_tow_limit() -> None:
    recommendations = plan_enforcement(
        _planner_frame(),
        window_start="2024-01-01 15:30:00",
        available_officers=8,
        available_tow_units=0,
        mode="balanced",
    )

    assert recommendations["tow_units_required"].sum() == 0


def test_planner_assigns_no_duplicate_primary_action_per_zone() -> None:
    recommendations = plan_enforcement(
        _planner_frame(),
        window_start="2024-01-01 15:30:00",
        available_officers=8,
        available_tow_units=1,
        mode="balanced",
    )

    assert recommendations["zone_id"].is_unique


def test_discovery_mode_selects_more_blindspots_than_conservative_mode() -> None:
    conservative = plan_enforcement(
        _planner_frame(),
        window_start="2024-01-01 15:30:00",
        available_officers=6,
        available_tow_units=1,
        mode="conservative",
    )
    discovery = plan_enforcement(
        _planner_frame(),
        window_start="2024-01-01 15:30:00",
        available_officers=6,
        available_tow_units=1,
        mode="discovery",
    )

    conservative_blindspots = conservative["action_category"].eq("blindspot").sum()
    discovery_blindspots = discovery["action_category"].eq("blindspot").sum()
    assert discovery_blindspots > conservative_blindspots
