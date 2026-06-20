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

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ZONE_ASSIGNMENTS_PATH = PROJECT_ROOT / "data" / "interim" / "zone_assignments.parquet"


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

    def _table_exists(self, table_name: str) -> bool:
        """Return true when a DuckDB table or view exists in the app database."""

        try:
            frame = self._fetch_df(
                """
                SELECT count(*) AS table_count
                FROM information_schema.tables
                WHERE lower(table_name) = lower(?)
                """,
                [table_name],
            )
        except duckdb.Error:
            return False
        return bool(frame.iloc[0]["table_count"]) if not frame.empty else False

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

    def get_prediction_windows(self, station: str | None = None, limit: int = 96) -> list[dict[str, Any]]:
        """Return recent prediction windows for timeline-driven map replay."""

        return _records(
            self._fetch_df(
                """
                SELECT
                    window_start,
                    count(DISTINCT zone_id) AS zone_count,
                    any_value(police_station) FILTER (WHERE police_station IS NOT NULL) AS sample_station,
                    avg(predicted_pfdi) AS avg_predicted_pfdi,
                    max(predicted_pfdi) AS max_predicted_pfdi,
                    avg(coverage_gap) AS avg_coverage_gap,
                    max(blindspot_risk_score) AS max_blindspot_risk,
                    max(deployment_priority_balanced) AS max_balanced_priority
                FROM predictions
                WHERE (? IS NULL OR police_station = ?)
                GROUP BY window_start
                ORDER BY window_start DESC
                LIMIT ?
                """,
                [station, station, max(1, int(limit))],
            )
        )

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

    def get_morning_deployment_brief(
        self,
        station: str,
        day_of_week: int,
        slot: int,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Return high-impact historical zones for a station/day/3-hour slot."""

        if self._table_exists("zone_slot_summary"):
            day_name = [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ][int(day_of_week)]
            return _records(
                self._fetch_df(
                    """
                    SELECT
                        zone_id,
                        COALESCE(NULLIF(junction_name, ''), zone_id) AS zone_label,
                        lower(police_station) AS police_station,
                        lat AS latitude,
                        lon AS longitude,
                        pfdi_score,
                        challan_count AS total_violations,
                        repeat_veh_count AS repeat_offender_count,
                        large_veh_pct / 100.0 AS large_vehicle_pct,
                        double_parking_count AS double_parking_instances,
                        dominant_vehicle_type,
                        CASE
                            WHEN double_parking_count > 0 THEN '[double_parking]'
                            ELSE NULL
                        END AS dominant_violation,
                        CASE
                            WHEN large_veh_pct > 10 OR double_parking_count > 2 THEN 'towing_required'
                            WHEN repeat_veh_count > 5 AND challan_count > 50 THEN 'camera_patrol'
                            WHEN repeat_veh_count > 3 THEN 'targeted_patrol'
                            ELSE 'beat_patrol'
                        END AS recommended_action
                    FROM zone_slot_summary
                    WHERE lower(police_station) = lower(?)
                      AND dow = ?
                      AND hour_slot = ?
                    ORDER BY pfdi_score DESC, challan_count DESC
                    LIMIT ?
                    """,
                    [station, day_name, int(slot), max(1, int(top_k))],
                )
            )
        if not ZONE_ASSIGNMENTS_PATH.exists():
            return []
        return _records(
            self._fetch_df(
                """
                WITH scoped AS (
                    SELECT
                        zone_id,
                        lower(police_station) AS police_station,
                        zone_centroid_lat,
                        zone_centroid_lon,
                        COALESCE(NULLIF(junction_name, ''), zone_id) AS junction_name,
                        lower(COALESCE(effective_vehicle_type, updated_vehicle_type, vehicle_type, 'unknown')) AS vehicle_type_norm,
                        parsed_violation_labels,
                        row_obstruction_score,
                        vehicle_number AS vehicle_key,
                        hour
                    FROM read_parquet(?)
                    WHERE zone_id IS NOT NULL
                      AND police_station IS NOT NULL
                      AND lower(police_station) = lower(?)
                      AND day_of_week = ?
                      AND CAST(floor(hour / 3) AS INTEGER) = ?
                ),
                zone_base AS (
                    SELECT
                        zone_id,
                        any_value(police_station) AS police_station,
                        any_value(zone_centroid_lat) AS latitude,
                        any_value(zone_centroid_lon) AS longitude,
                        COALESCE(
                            max(
                                CASE
                                    WHEN lower(junction_name) NOT IN ('no junction', 'unknown', 'nan')
                                    THEN junction_name
                                END
                            ),
                            zone_id
                        ) AS zone_label,
                        count(*) AS total_violations,
                        avg(row_obstruction_score) AS avg_pfdi,
                        sum(
                            CASE
                                WHEN regexp_matches(CAST(parsed_violation_labels AS VARCHAR), 'double_parking')
                                THEN 1
                                ELSE 0
                            END
                        ) AS double_parking_instances,
                        avg(
                            CASE
                                WHEN vehicle_type_norm LIKE '%bus%'
                                  OR vehicle_type_norm LIKE '%hgv%'
                                  OR vehicle_type_norm LIKE '%lorry%'
                                  OR vehicle_type_norm LIKE '%tanker%'
                                  OR vehicle_type_norm LIKE '%tempo%'
                                THEN 1
                                ELSE 0
                            END
                        ) AS large_vehicle_pct
                    FROM scoped
                    GROUP BY zone_id
                ),
                vehicle_repeat AS (
                    SELECT zone_id, count(*) AS repeat_offender_count
                    FROM (
                        SELECT zone_id, vehicle_key, count(*) AS vehicle_hits
                        FROM scoped
                        WHERE vehicle_key IS NOT NULL
                        GROUP BY zone_id, vehicle_key
                        HAVING count(*) >= 3
                    )
                    GROUP BY zone_id
                ),
                vehicle_rank AS (
                    SELECT
                        zone_id,
                        vehicle_type_norm AS dominant_vehicle_type,
                        row_number() OVER (PARTITION BY zone_id ORDER BY count(*) DESC, vehicle_type_norm) AS rn
                    FROM scoped
                    GROUP BY zone_id, vehicle_type_norm
                ),
                violation_rank AS (
                    SELECT
                        zone_id,
                        CAST(parsed_violation_labels AS VARCHAR) AS dominant_violation,
                        row_number() OVER (
                            PARTITION BY zone_id
                            ORDER BY count(*) DESC, CAST(parsed_violation_labels AS VARCHAR)
                        ) AS rn
                    FROM scoped
                    GROUP BY zone_id, CAST(parsed_violation_labels AS VARCHAR)
                ),
                max_count AS (
                    SELECT max(total_violations) AS max_zone_count
                    FROM zone_base
                )
                SELECT
                    b.zone_id,
                    b.zone_label,
                    b.police_station,
                    b.latitude,
                    b.longitude,
                    least(
                        100.0,
                        0.72 * COALESCE(b.avg_pfdi, 0)
                        + 0.28 * 100.0 * b.total_violations / NULLIF(m.max_zone_count, 0)
                    ) AS pfdi_score,
                    b.total_violations,
                    COALESCE(vr.repeat_offender_count, 0) AS repeat_offender_count,
                    b.large_vehicle_pct,
                    b.double_parking_instances,
                    v.dominant_vehicle_type,
                    pl.dominant_violation,
                    CASE
                        WHEN b.large_vehicle_pct >= 0.10 OR b.double_parking_instances > 2 THEN 'towing_required'
                        WHEN COALESCE(vr.repeat_offender_count, 0) > 5 AND b.total_violations > 50 THEN 'camera_patrol'
                        WHEN COALESCE(vr.repeat_offender_count, 0) > 3 THEN 'targeted_patrol'
                        ELSE 'beat_patrol'
                    END AS recommended_action
                FROM zone_base AS b
                CROSS JOIN max_count AS m
                LEFT JOIN vehicle_repeat AS vr USING (zone_id)
                LEFT JOIN vehicle_rank AS v ON b.zone_id = v.zone_id AND v.rn = 1
                LEFT JOIN violation_rank AS pl ON b.zone_id = pl.zone_id AND pl.rn = 1
                ORDER BY pfdi_score DESC, b.total_violations DESC
                LIMIT ?
                """,
                [
                    str(ZONE_ASSIGNMENTS_PATH),
                    station,
                    int(day_of_week),
                    int(slot),
                    max(1, int(top_k)),
                ],
            )
        )

    def get_blindspot_hourly_volume(self) -> list[dict[str, Any]]:
        """Return 24-hour record volume from row-level enforcement artifacts."""

        if self._table_exists("hourly_volume"):
            return _records(
                self._fetch_df(
                    """
                    SELECT
                        CAST(hour AS INTEGER) AS hour,
                        CAST(record_count AS BIGINT) AS record_count,
                        share
                    FROM hourly_volume
                    ORDER BY hour
                    """
                )
            )
        if ZONE_ASSIGNMENTS_PATH.exists():
            return _records(
                self._fetch_df(
                    """
                    SELECT
                        CAST(hour AS INTEGER) AS hour,
                        count(*)::BIGINT AS record_count,
                        count(*) * 1.0 / sum(count(*)) OVER () AS share
                    FROM read_parquet(?)
                    WHERE hour IS NOT NULL
                    GROUP BY hour
                    ORDER BY hour
                    """,
                    [str(ZONE_ASSIGNMENTS_PATH)],
                )
            )
        return self.get_hourly_audit()

    def get_station_shift_cutoff(self, top_k: int = 20) -> list[dict[str, Any]]:
        """Return aggregate station shift cutoff proxy using last active hour per officer-day."""

        if self._table_exists("station_shift_cutoff"):
            return _records(
                self._fetch_df(
                    """
                    SELECT
                        lower(police_station) AS police_station,
                        median_last_hour,
                        evening_active_day_share,
                        total_officers,
                        officer_days
                    FROM station_shift_cutoff
                    ORDER BY total_officers DESC, officer_days DESC
                    LIMIT ?
                    """,
                    [max(1, int(top_k))],
                )
            )
        if not ZONE_ASSIGNMENTS_PATH.exists():
            return []
        return _records(
            self._fetch_df(
                """
                WITH daily AS (
                    SELECT
                        lower(police_station) AS police_station,
                        created_by_id,
                        CAST(created_datetime_ist AS DATE) AS record_date,
                        max(CAST(hour AS INTEGER)) AS last_active_hour
                    FROM read_parquet(?)
                    WHERE police_station IS NOT NULL
                      AND created_by_id IS NOT NULL
                      AND hour IS NOT NULL
                    GROUP BY 1, 2, 3
                )
                SELECT
                    police_station,
                    median(last_active_hour) AS median_last_hour,
                    avg(CASE WHEN last_active_hour >= 15 THEN 1 ELSE 0 END) AS evening_active_day_share,
                    count(DISTINCT created_by_id) AS total_officers,
                    count(*) AS officer_days
                FROM daily
                GROUP BY police_station
                ORDER BY officer_days DESC
                LIMIT ?
                """,
                [str(ZONE_ASSIGNMENTS_PATH), max(1, int(top_k))],
            )
        )

    def get_coverage_gaps(
        self,
        station: str | None = None,
        top_k: int = 500,
    ) -> list[dict[str, Any]]:
        """Return high-frequency zones with intermittent coverage for the patrol myopia map."""

        if self._table_exists("zone_coverage_gaps"):
            return _records(
                self._fetch_df(
                    """
                    SELECT
                        zone_id,
                        lower(police_station) AS police_station,
                        lat AS latitude,
                        lon AS longitude,
                        total_violations,
                        unique_days AS active_days,
                        coverage_pct / 100.0 AS coverage_pct,
                        last_seen,
                        peak_hour,
                        junction_name,
                        gap_severity,
                        lower(gap_severity) AS gap_level,
                        NULL::DOUBLE AS patrol_myopia_score,
                        NULL::DOUBLE AS top_3_zone_share,
                        NULL::DOUBLE AS morning_only_bias,
                        NULL::DOUBLE AS zone_coverage_entropy,
                        NULL::DOUBLE AS avg_pfdi
                    FROM zone_coverage_gaps
                    WHERE ((total_violations > 100 AND coverage_pct < 20)
                        OR (total_violations > 50 AND coverage_pct < 35))
                      AND (? IS NULL OR lower(police_station) = lower(?))
                    ORDER BY
                        CASE gap_severity WHEN 'HIGH' THEN 2 ELSE 1 END DESC,
                        total_violations DESC
                    LIMIT ?
                    """,
                    [station, station, max(1, int(top_k))],
                )
            )
        if not ZONE_ASSIGNMENTS_PATH.exists():
            return []
        return _records(
            self._fetch_df(
                """
                WITH base AS (
                    SELECT
                        lower(police_station) AS police_station,
                        zone_id,
                        zone_centroid_lat AS latitude,
                        zone_centroid_lon AS longitude,
                        date,
                        hour,
                        created_datetime_ist,
                        row_obstruction_score,
                        parsed_violation_labels
                    FROM read_parquet(?)
                    WHERE zone_id IS NOT NULL
                      AND police_station IS NOT NULL
                      AND (? IS NULL OR lower(police_station) = lower(?))
                ),
                zone_counts AS (
                    SELECT
                        police_station,
                        zone_id,
                        any_value(latitude) AS latitude,
                        any_value(longitude) AS longitude,
                        count(*) AS total_violations,
                        count(DISTINCT date) AS active_days,
                        count(DISTINCT date) / 150.0 AS coverage_pct,
                        max(created_datetime_ist) AS last_seen,
                        avg(row_obstruction_score) AS avg_pfdi
                    FROM base
                    GROUP BY police_station, zone_id
                ),
                hour_rank AS (
                    SELECT
                        zone_id,
                        CAST(hour AS INTEGER) AS peak_hour,
                        row_number() OVER (PARTITION BY zone_id ORDER BY count(*) DESC, hour) AS rn
                    FROM base
                    GROUP BY zone_id, hour
                ),
                violation_rank AS (
                    SELECT
                        zone_id,
                        CAST(parsed_violation_labels AS VARCHAR) AS dominant_violation,
                        row_number() OVER (
                            PARTITION BY zone_id
                            ORDER BY count(*) DESC, CAST(parsed_violation_labels AS VARCHAR)
                        ) AS rn
                    FROM base
                    GROUP BY zone_id, CAST(parsed_violation_labels AS VARCHAR)
                ),
                station_totals AS (
                    SELECT police_station, count(*) AS station_total
                    FROM base
                    GROUP BY police_station
                ),
                station_zone_counts AS (
                    SELECT police_station, zone_id, count(*) AS zone_total
                    FROM base
                    GROUP BY police_station, zone_id
                ),
                station_ranked AS (
                    SELECT
                        police_station,
                        zone_total,
                        row_number() OVER (PARTITION BY police_station ORDER BY zone_total DESC) AS rn
                    FROM station_zone_counts
                ),
                station_entropy AS (
                    SELECT
                        z.police_station,
                        CASE
                            WHEN count(*) <= 1 THEN 0
                            ELSE -sum(
                                (zone_total * 1.0 / station_total)
                                * ln(zone_total * 1.0 / station_total)
                            ) / ln(count(*))
                        END AS zone_coverage_entropy,
                        sum(CASE WHEN rn <= 3 THEN zone_total ELSE 0 END) * 1.0
                            / max(station_total) AS top_3_zone_share
                    FROM station_ranked AS z
                    JOIN station_totals AS t USING (police_station)
                    GROUP BY z.police_station
                ),
                station_bias AS (
                    SELECT
                        police_station,
                        avg(CASE WHEN hour >= 8 AND hour < 14 THEN 1 ELSE 0 END) AS morning_only_bias
                    FROM base
                    GROUP BY police_station
                ),
                station_myopia AS (
                    SELECT
                        e.police_station,
                        e.top_3_zone_share,
                        b.morning_only_bias,
                        e.zone_coverage_entropy,
                        least(
                            100.0,
                            greatest(
                                0.0,
                                100.0 * (
                                    0.50 * e.top_3_zone_share
                                    + 0.30 * b.morning_only_bias
                                    + 0.20 * (1 - e.zone_coverage_entropy)
                                )
                            )
                        ) AS patrol_myopia_score
                    FROM station_entropy AS e
                    JOIN station_bias AS b USING (police_station)
                )
                SELECT
                    z.zone_id,
                    z.police_station,
                    z.latitude,
                    z.longitude,
                    z.total_violations,
                    z.active_days,
                    z.coverage_pct,
                    z.last_seen,
                    h.peak_hour,
                    v.dominant_violation,
                    CASE
                        WHEN z.total_violations >= 100 AND z.coverage_pct < 0.20 THEN 'high'
                        WHEN z.total_violations >= 50 AND z.coverage_pct < 0.35 THEN 'medium'
                        ELSE 'low'
                    END AS gap_level,
                    m.patrol_myopia_score,
                    m.top_3_zone_share,
                    m.morning_only_bias,
                    m.zone_coverage_entropy,
                    z.avg_pfdi
                FROM zone_counts AS z
                LEFT JOIN hour_rank AS h ON z.zone_id = h.zone_id AND h.rn = 1
                LEFT JOIN violation_rank AS v ON z.zone_id = v.zone_id AND v.rn = 1
                LEFT JOIN station_myopia AS m ON z.police_station = m.police_station
                WHERE (z.total_violations >= 100 AND z.coverage_pct < 0.20)
                   OR (z.total_violations >= 50 AND z.coverage_pct < 0.35)
                ORDER BY
                    CASE gap_level WHEN 'high' THEN 2 WHEN 'medium' THEN 1 ELSE 0 END DESC,
                    z.total_violations DESC
                LIMIT ?
                """,
                [str(ZONE_ASSIGNMENTS_PATH), station, station, max(1, int(top_k))],
            )
        )

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
