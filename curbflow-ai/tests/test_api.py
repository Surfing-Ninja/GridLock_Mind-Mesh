"""Tests for FastAPI routes and privacy-safe responses."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.api.dependencies import get_repository
from apps.api.main import app
from apps.api.routes import zones as zones_routes


class FakeRepository:
    """Small fake repository for route tests."""

    def __init__(self) -> None:
        self.feedback_payload = None
        self.geojson_calls = 0

    def get_audit_summary(self):
        return {
            "total_rows": 298450,
            "actual_date_range": {
                "start": "2023-11-01T00:00:00+05:30",
                "end": "2024-04-30T23:59:59+05:30",
            },
            "fully_null_columns": {
                "description": True,
                "closed_datetime": True,
                "action_taken_timestamp": True,
            },
            "morning_count_0730_1530": 250000,
            "evening_count_1530_2030": 1200,
            "evening_gap_ratio_morning_over_evening": 208.33,
            "top_zone_concentration": {
                "available": True,
                "active_zones": 42,
                "top_10_zone_share": 0.36,
            },
            "interpretation_warnings": [
                "This dataset is an enforcement visibility dataset, not a complete record of all illegal parking."
            ],
        }

    def get_hourly_audit(self):
        return [{"hour": 7, "record_count": 10, "share": 0.1}]

    def get_zones_geojson(self, layer="zones", window_start=None, station=None, mode="balanced"):
        self.geojson_calls += 1
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "zone_id": "z1",
                        "police_station": station or "station_a",
                        "device_id": "private-device",
                    },
                    "geometry": None,
                }
            ],
        }

    def get_hotspots(self, window_start=None, station=None, top_k=25, mode="balanced"):
        return [
            {
                "zone_id": "z1",
                "window_start": window_start,
                "police_station": station or "station_a",
                "predicted_pfdi": 88.0,
                "hotspot_probability": 0.91,
                "deployment_priority": 90.0,
                "device_id": "private-device",
                "vehicle_number": "private-vehicle",
            }
        ][:top_k]

    def get_blindspots(self, window_start=None, station=None, top_k=25):
        return [
            {
                "zone_id": "z2",
                "window_start": window_start,
                "police_station": station or "station_a",
                "coverage_gap": 0.9,
                "blindspot_risk_score": 92.0,
                "created_by_id": "private-user",
            }
        ][:top_k]

    def get_patrol_summary(self, station=None, top_k=25):
        return [
            {
                "police_station": station or "station_a",
                "total_records": 1200,
                "top_10_zone_share": 0.62,
                "evening_coverage": 0.08,
                "zone_coverage_entropy": 0.41,
                "morning_bias": 0.92,
                "patrol_myopia_index": 0.71,
                "patrol_myopia_level": "High",
                "patrol_connected_zones": 18,
                "nearby_uncovered_zones": 4,
                "device_id": "private-device",
            }
        ][:top_k]

    def get_patrol_routes(self, station=None, top_k=50):
        return [
            {
                "from_zone_id": "z1",
                "to_zone_id": "z2",
                "police_station": station or "station_a",
                "patrol_transition_count": 12,
                "device_transition_count": 8,
                "user_transition_count": 4,
                "patrol_edge_weight": 6.4,
                "mean_gap_hours": 0.7,
                "mean_distance_m": 620.0,
                "from_patrol_route_coverage": 0.8,
                "to_patrol_route_coverage": 0.74,
                "from_near_patrol_but_uncovered": False,
                "to_near_patrol_but_uncovered": True,
                "route_category": "nearby_uncovered_zone",
                "created_by_id": "private-user",
            }
        ][:top_k]

    def get_zone_details(self, zone_id, window_start=None):
        return {
            "zone_id": zone_id,
            "window_start": window_start,
            "police_station": "station_a",
            "predicted_pfdi": 72.0,
            "device_id": "private-device",
        }

    def get_planner_recommendations(self, input):
        return [
            {
                "recommendation_rank": 1,
                "zone_id": "z1",
                "window_start": input["window_start"],
                "police_station": input.get("police_station") or "station_a",
                "action": "beat_patrol",
                "action_category": "known_hotspot",
                "mode": input["mode"],
                "expected_relief": 81.0,
                "score_per_resource_unit": 81.0,
                "officers_required": 1,
                "tow_units_required": 0,
                "explanation": "High observed hotspot priority.",
                "explanation_json": '{"reasons":["high predicted observed disruption"]}',
            }
        ]

    def get_model_metrics(self):
        return {"be_sthgt": {"ndcg_at_10": 0.7}, "lightgbm_ranker": {"ndcg_at_10": 0.8}}

    def save_feedback(self, feedback):
        self.feedback_payload = feedback
        return {"feedback_id": "feedback-1", "saved": True}


@pytest.fixture()
def client():
    fake = FakeRepository()
    zones_routes._GEOJSON_CACHE.clear()
    app.dependency_overrides[get_repository] = lambda: fake
    with TestClient(app) as test_client:
        test_client.fake_repository = fake
        yield test_client
    app.dependency_overrides.clear()


def test_health(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "app_version" in payload
    assert "model_loaded" in payload
    assert "database_available" in payload


def test_debug_files_available_in_development(client) -> None:
    response = client.get("/debug/files")
    assert response.status_code == 200
    payload = response.json()
    assert payload["environment"] in {"development", "dev", "local"}
    assert "duckdb" in payload["files"]


def test_openapi_has_endpoint_descriptions(client) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    openapi = response.json()
    checked_paths = [
        ("/health", "get"),
        ("/audit/summary", "get"),
        ("/audit/hourly", "get"),
        ("/zones/geojson", "get"),
        ("/zones/{zone_id}", "get"),
        ("/hotspots", "get"),
        ("/blindspots", "get"),
        ("/patrol/summary", "get"),
        ("/patrol/routes", "get"),
        ("/planner/recommend", "post"),
        ("/metrics/model", "get"),
        ("/feedback", "post"),
    ]
    for path, method in checked_paths:
        operation = openapi["paths"][path][method]
        assert operation.get("summary")
        assert operation.get("description")


def test_audit_summary_shape(client) -> None:
    response = client.get("/audit/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["row_count"] == 298450
    assert payload["null_outcome_columns"]["description"] is True
    assert payload["morning_count"] == 250000
    assert payload["evening_count"] == 1200
    assert payload["active_zones"] == 42
    assert "enforcement visibility dataset" in payload["key_warning_message"]


def test_audit_hourly(client) -> None:
    response = client.get("/audit/hourly")
    assert response.status_code == 200
    assert response.json()[0]["hour"] == 7


def test_zones_geojson_sanitizes_private_fields(client) -> None:
    response = client.get("/zones/geojson?window_start=2024-01-01T00:00:00&station=station_a")
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert "device_id" not in payload["features"][0]["properties"]


def test_zones_geojson_uses_cache(client) -> None:
    first = client.get("/zones/geojson?window_start=2024-01-01T00:00:00&station=station_a")
    second = client.get("/zones/geojson?window_start=2024-01-01T00:00:00&station=station_a")
    assert first.status_code == 200
    assert second.status_code == 200
    assert client.fake_repository.geojson_calls == 1


def test_hotspots_and_blindspots_sanitize_private_fields(client) -> None:
    hotspot = client.get("/hotspots?window_start=2024-01-01T00:00:00&station=station_a").json()[0]
    blindspot = client.get("/blindspots?window_start=2024-01-01T00:00:00&station=station_a").json()[0]
    assert hotspot["zone_id"] == "z1"
    assert "device_id" not in hotspot
    assert "vehicle_number" not in hotspot
    assert blindspot["zone_id"] == "z2"
    assert "created_by_id" not in blindspot


def test_patrol_routes_return_aggregate_operational_intelligence(client) -> None:
    summary = client.get("/patrol/summary?station=station_a")
    routes = client.get("/patrol/routes?station=station_a")
    assert summary.status_code == 200
    assert routes.status_code == 200
    summary_payload = summary.json()[0]
    route_payload = routes.json()[0]
    assert summary_payload["patrol_myopia_index"] == 0.71
    assert route_payload["route_category"] == "nearby_uncovered_zone"
    assert "device_id" not in summary_payload
    assert "created_by_id" not in route_payload


def test_zone_details(client) -> None:
    response = client.get("/zones/z1?window_start=2024-01-01T00:00:00")
    assert response.status_code == 200
    payload = response.json()
    assert payload["zone_id"] == "z1"
    assert "device_id" not in payload


def test_planner_recommend_requires_valid_request_and_returns_explanation(client) -> None:
    response = client.post(
        "/planner/recommend",
        json={
            "window_start": "2024-01-01T00:00:00",
            "police_station": "station_a",
            "available_officers": 2,
            "available_tow_units": 0,
            "mode": "balanced",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["action"] == "beat_patrol"
    assert payload[0]["explanation_json"]


def test_planner_missing_window_start_is_validation_error(client) -> None:
    response = client.post(
        "/planner/recommend",
        json={
            "available_officers": 2,
            "available_tow_units": 0,
            "mode": "balanced",
        },
    )
    assert response.status_code == 422


def test_invalid_station_returns_400(client) -> None:
    response = client.get("/hotspots?station=undefined")
    assert response.status_code == 400


def test_model_metrics_and_feedback(client) -> None:
    metrics = client.get("/metrics/model")
    assert metrics.status_code == 200
    assert "be_sthgt" in metrics.json()["metrics"]

    feedback = client.post(
        "/feedback",
        json={
            "zone_id": "z1",
            "window_start": "2024-01-01T00:00:00",
            "police_station": "station_a",
            "action_taken": "beat_patrol",
            "officers_deployed": 2,
            "tow_units_used": 0,
            "vehicles_found": 5,
            "vehicles_removed": 3,
            "vehicles_towed": 1,
            "road_cleared": True,
            "approx_queue_length_m": 80,
            "notes": "No queueing seen.",
        },
    )
    assert feedback.status_code == 200
    assert feedback.json()["saved"] is True
    assert client.fake_repository.feedback_payload["action_taken"] == "beat_patrol"
    assert client.fake_repository.feedback_payload["vehicles_found"] == 5
