"""Repository abstraction for privacy-safe aggregate dashboard data."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from curbflow.db.duckdb_init import APP_DB_PATH, initialize_duckdb
from curbflow.db import queries
from curbflow.planner.optimizer import merge_planner_features, plan_enforcement


def _payload_to_dict(payload: Any) -> dict[str, Any]:
    """Normalize dict, dataclass, or Pydantic-like payloads."""

    if payload is None:
        return {}
    if isinstance(payload, dict):
        return dict(payload)
    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    if hasattr(payload, "dict"):
        return payload.dict()
    return dict(payload)


def _jsonable(value: Any) -> Any:
    """Convert DuckDB/Pandas scalar values to API-safe values."""

    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "isoformat") and value.__class__.__name__ in {"Timestamp", "datetime", "date"}:
        return value.isoformat()
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a DataFrame into JSON-safe record dictionaries."""

    return [
        {column: _jsonable(value) for column, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


class CurbFlowRepository:
    """DuckDB-backed repository for aggregate, privacy-safe CurbFlow API data."""

    def __init__(self, db_path: str | Path = APP_DB_PATH, *, auto_init: bool = True) -> None:
        self.db_path = Path(db_path)
        if auto_init and not self.db_path.exists():
            initialize_duckdb(self.db_path)

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path))

    def _fetch_df(self, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> pd.DataFrame:
        with self._connect() as con:
            return con.execute(sql, params or []).fetchdf()

    def get_audit_summary(self) -> dict[str, Any]:
        """Return the data and bias audit summary."""

        frame = self._fetch_df(queries.AUDIT_SUMMARY)
        if frame.empty:
            return {}
        row = frame.iloc[0].to_dict()
        summary_json = row.get("summary_json")
        if summary_json:
            try:
                return json.loads(summary_json)
            except json.JSONDecodeError:
                pass
        return {key: _jsonable(value) for key, value in row.items()}

    def get_hourly_audit(self) -> list[dict[str, Any]]:
        """Return hour-of-day audit distribution."""

        return _records(self._fetch_df(queries.HOURLY_AUDIT))

    def get_zones_geojson(
        self,
        layer: str = "zones",
        window_start: str | None = None,
        station: str | None = None,
        mode: str = "balanced",
    ) -> dict[str, Any]:
        """Return zone GeoJSON enriched with prediction properties."""

        with self._connect() as con:
            row = con.execute(
                "SELECT geojson FROM zones_geojson WHERE layer = ? LIMIT 1",
                [layer],
            ).fetchone()
            geojson = (
                json.loads(row[0])
                if row and row[0]
                else {"type": "FeatureCollection", "features": []}
            )
            priority = queries.priority_column(mode)
            prediction_rows = con.execute(
                f"""
                SELECT
                    zone_id,
                    window_start,
                    police_station,
                    predicted_count,
                    predicted_pfdi,
                    hotspot_probability,
                    coverage_gap,
                    blindspot_risk_score,
                    exploit_score,
                    explore_score,
                    {priority} AS deployment_priority,
                    recommended_action
                FROM predictions
                WHERE (? IS NULL OR window_start = CAST(? AS TIMESTAMP))
                  AND (? IS NULL OR police_station = ?)
                """,
                [window_start, window_start, station, station],
            ).fetchdf()
            try:
                patrol_rows = con.execute(
                    """
                    SELECT
                        features.zone_id,
                        any_value(zone_time_features.police_station) AS police_station,
                        features.patrol_in_degree,
                        features.patrol_out_degree,
                        features.patrol_weighted_degree,
                        features.patrol_pagerank,
                        features.patrol_route_coverage,
                        features.near_patrol_but_uncovered_flag,
                        features.static_potential AS patrol_static_potential,
                        features.exposure_score AS patrol_exposure_score
                    FROM patrol_graph_features AS features
                    LEFT JOIN zone_time_features
                        ON features.zone_id = zone_time_features.zone_id
                    GROUP BY
                        features.zone_id,
                        features.patrol_in_degree,
                        features.patrol_out_degree,
                        features.patrol_weighted_degree,
                        features.patrol_pagerank,
                        features.patrol_route_coverage,
                        features.near_patrol_but_uncovered_flag,
                        features.static_potential,
                        features.exposure_score
                    """
                ).fetchdf()
            except duckdb.Error:
                patrol_rows = pd.DataFrame()

        prediction_lookup = {
            str(row["zone_id"]): {key: _jsonable(value) for key, value in row.items()}
            for row in prediction_rows.to_dict(orient="records")
        }
        patrol_lookup = {
            str(row["zone_id"]): {key: _jsonable(value) for key, value in row.items()}
            for row in patrol_rows.to_dict(orient="records")
        }
        enriched_features = []
        for feature in geojson.get("features", []):
            properties = feature.setdefault("properties", {})
            zone_id = str(properties.get("zone_id") or properties.get("id") or "")
            prediction = prediction_lookup.get(zone_id)
            patrol = patrol_lookup.get(zone_id)
            if station and prediction is None and (patrol is None or patrol.get("police_station") != station):
                continue
            if prediction:
                properties.update(prediction)
            if patrol:
                properties.update(patrol)
            enriched_features.append(feature)
        return {"type": "FeatureCollection", "features": enriched_features}

    def get_hotspots(
        self,
        window_start: str | None = None,
        station: str | None = None,
        top_k: int = 25,
        mode: str = "balanced",
    ) -> list[dict[str, Any]]:
        """Return top observed-risk hotspot rows."""

        limit = max(1, int(top_k))
        return _records(
            self._fetch_df(
                queries.hotspots_query(mode),
                [window_start, window_start, station, station, limit],
            )
        )

    def get_blindspots(
        self,
        window_start: str | None = None,
        station: str | None = None,
        top_k: int = 25,
    ) -> list[dict[str, Any]]:
        """Return top low-visibility blindspot rows."""

        limit = max(1, int(top_k))
        return _records(
            self._fetch_df(
                queries.blindspots_query(),
                [window_start, window_start, station, station, limit],
            )
        )

    def get_patrol_summary(
        self,
        station: str | None = None,
        top_k: int = 25,
    ) -> list[dict[str, Any]]:
        """Return station-level aggregate patrol digital twin metrics."""

        try:
            return _records(
                self._fetch_df(
                    queries.PATROL_SUMMARY,
                    [station, station, max(1, int(top_k))],
                )
            )
        except duckdb.Error:
            return []

    def get_patrol_routes(
        self,
        station: str | None = None,
        top_k: int = 50,
    ) -> list[dict[str, Any]]:
        """Return aggregate patrol transition patterns without raw actor identifiers."""

        try:
            return _records(
                self._fetch_df(
                    queries.PATROL_ROUTES,
                    [station, station, max(1, int(top_k))],
                )
            )
        except duckdb.Error:
            return []

    def get_zone_details(self, zone_id: str, window_start: str | None = None) -> dict[str, Any]:
        """Return prediction and feature details for a single zone-window."""

        frame = self._fetch_df(
            queries.ZONE_DETAILS,
            [zone_id, window_start, window_start, zone_id, window_start, window_start],
        )
        return _records(frame)[0] if not frame.empty else {}

    def get_planner_recommendations(self, input: Any) -> list[dict[str, Any]]:
        """Return saved recommendations or compute scoped fallback recommendations."""

        payload = _payload_to_dict(input)
        window_start = payload.get("window_start")
        station = payload.get("police_station", payload.get("station"))
        mode = str(payload.get("mode", "balanced")).lower()
        top_k = int(payload.get("top_k", payload.get("limit", 50)))
        saved = self._fetch_df(
            queries.recommendations_query(),
            [window_start, window_start, station, station, mode, mode, max(1, top_k)],
        )
        if not saved.empty:
            return _records(saved)

        available_officers = int(payload.get("available_officers", 8))
        available_tow_units = int(payload.get("available_tow_units", 2))
        predictions = self._fetch_df(
            queries.scoped_prediction_features_query(),
            [window_start, window_start, station, station],
        )
        if predictions.empty:
            return []
        features = self._fetch_df(
            queries.scoped_zone_time_features_query(),
            [window_start, window_start, station, station],
        )
        planner_input = merge_planner_features(predictions, features)
        recommendations = plan_enforcement(
            planner_input,
            police_station=station,
            window_start=window_start,
            available_officers=available_officers,
            available_tow_units=available_tow_units,
            mode=mode,
        ).head(max(1, top_k))
        return _records(recommendations)

    def get_model_metrics(self) -> dict[str, Any]:
        """Return model metrics keyed by metric source."""

        frame = self._fetch_df(queries.MODEL_METRICS)
        metrics: dict[str, Any] = {}
        for row in frame.to_dict(orient="records"):
            source = str(row.get("metric_source"))
            payload = row.get("metrics_json") or "{}"
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                parsed = {"raw": payload}
            parsed["_source_path"] = row.get("source_path")
            parsed["_updated_at"] = _jsonable(row.get("updated_at"))
            metrics[source] = parsed
        return metrics

    def save_feedback(self, feedback: Any) -> dict[str, Any]:
        """Persist deployment feedback for future learning-loop use."""

        payload = _payload_to_dict(feedback)
        feedback_id = str(payload.get("feedback_id") or uuid.uuid4())
        zone_id = payload.get("zone_id")
        window_start = payload.get("window_start")
        police_station = payload.get("police_station", payload.get("station"))
        action_taken = payload.get("action_taken", payload.get("action"))
        officers_deployed = int(payload.get("officers_deployed") or 0)
        tow_units_used = int(payload.get("tow_units_used") or 0)
        vehicles_found = int(payload.get("vehicles_found") or 0)
        vehicles_removed = int(payload.get("vehicles_removed") or 0)
        vehicles_towed = int(payload.get("vehicles_towed") or 0)
        road_cleared = bool(payload.get("road_cleared"))
        approx_queue_length_m = payload.get("approx_queue_length_m")
        notes = payload.get("notes")
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO feedback (
                    feedback_id,
                    zone_id,
                    window_start,
                    police_station,
                    action_taken,
                    officers_deployed,
                    tow_units_used,
                    vehicles_found,
                    vehicles_removed,
                    vehicles_towed,
                    road_cleared,
                    approx_queue_length_m,
                    notes,
                    payload_json
                )
                VALUES (?, ?, CAST(? AS TIMESTAMP), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    feedback_id,
                    zone_id,
                    window_start,
                    police_station,
                    action_taken,
                    officers_deployed,
                    tow_units_used,
                    vehicles_found,
                    vehicles_removed,
                    vehicles_towed,
                    road_cleared,
                    approx_queue_length_m,
                    notes,
                    json.dumps(payload, default=str),
                ],
            )
        return {"feedback_id": feedback_id, "saved": True}
