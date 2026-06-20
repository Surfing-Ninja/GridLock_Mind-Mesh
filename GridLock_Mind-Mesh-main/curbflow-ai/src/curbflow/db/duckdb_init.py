"""DuckDB schema initialization and artifact seeding utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from curbflow.data.audit import COVERAGE_AUDIT_PATH, EDA_SUMMARY_PATH
from curbflow.features.aggregate_zone_time import ZONE_TIME_FEATURES_PATH
from curbflow.features.novel_features import JUNCTION_BASINS_PATH, PATROL_MYOPIA_PATH
from curbflow.graph.build_patrol_graph import PATROL_GRAPH_EDGES_PATH, PATROL_GRAPH_FEATURES_PATH
DEEP_METRICS_PATH = Path("artifacts/metrics/deep_metrics.json")
from curbflow.ml.ranker.ensemble import PREDICTIONS_PATH
from curbflow.ml.ranker.lgbm_ranker import RANKER_METRICS_PATH
from curbflow.planner.optimizer import RECOMMENDATIONS_PATH
from curbflow.zoning.zone_geojson import ZONES_GEOJSON_PATH


APP_DB_PATH = Path("data/app/curbflow.duckdb")

EMPTY_SCHEMAS = {
    "hourly_audit": """
        hour INTEGER,
        record_count BIGINT,
        share DOUBLE
    """,
    "zone_time_features": """
        zone_id VARCHAR,
        window_start TIMESTAMP,
        window_end TIMESTAMP,
        police_station VARCHAR,
        observed_pfdi DOUBLE,
        bias_corrected_pfdi DOUBLE,
        exposure DOUBLE,
        coverage_gap DOUBLE,
        blindspot_risk DOUBLE,
        static_potential DOUBLE,
        record_count BIGINT
    """,
    "predictions": """
        zone_id VARCHAR,
        window_start TIMESTAMP,
        police_station VARCHAR,
        predicted_count DOUBLE,
        predicted_pfdi DOUBLE,
        hotspot_probability DOUBLE,
        q90_pfdi DOUBLE,
        latent_risk DOUBLE,
        exposure DOUBLE,
        coverage_gap DOUBLE,
        observed_risk_score DOUBLE,
        blindspot_risk_score DOUBLE,
        exploit_score DOUBLE,
        explore_score DOUBLE,
        deployment_priority_conservative DOUBLE,
        deployment_priority_balanced DOUBLE,
        deployment_priority_discovery DOUBLE,
        recommended_action VARCHAR,
        explanation_json VARCHAR
    """,
    "recommendations": """
        recommendation_rank INTEGER,
        zone_id VARCHAR,
        window_start TIMESTAMP,
        police_station VARCHAR,
        action VARCHAR,
        action_category VARCHAR,
        mode VARCHAR,
        expected_relief DOUBLE,
        score_per_resource_unit DOUBLE,
        officers_required INTEGER,
        tow_units_required INTEGER,
        cumulative_officers INTEGER,
        cumulative_tow_units INTEGER,
        predicted_pfdi DOUBLE,
        hotspot_probability DOUBLE,
        coverage_gap DOUBLE,
        blindspot_risk_score DOUBLE,
        exploit_score DOUBLE,
        explore_score DOUBLE,
        explanation VARCHAR,
        explanation_json VARCHAR
    """,
    "patrol_myopia": """
        police_station VARCHAR,
        total_records BIGINT,
        unique_zones BIGINT,
        top_10_zone_records BIGINT,
        top_10_zone_share DOUBLE,
        zone_coverage_entropy DOUBLE,
        morning_records_0730_1530 BIGINT,
        evening_records_1530_2030 BIGINT,
        morning_bias DOUBLE,
        unique_devices BIGINT,
        device_diversity DOUBLE,
        unique_created_by_users BIGINT,
        user_diversity DOUBLE,
        patrol_myopia_index DOUBLE,
        patrol_myopia_level VARCHAR
    """,
    "patrol_graph_edges": """
        from_zone_id VARCHAR,
        to_zone_id VARCHAR,
        device_transition_count BIGINT,
        user_transition_count BIGINT,
        device_transition_weight DOUBLE,
        user_transition_weight DOUBLE,
        device_mean_gap_hours DOUBLE,
        device_mean_distance_m DOUBLE,
        user_mean_gap_hours DOUBLE,
        user_mean_distance_m DOUBLE,
        patrol_edge_weight DOUBLE,
        patrol_transition_count BIGINT
    """,
    "patrol_graph_features": """
        zone_id VARCHAR,
        patrol_in_degree DOUBLE,
        patrol_out_degree DOUBLE,
        patrol_weighted_degree DOUBLE,
        patrol_pagerank DOUBLE,
        patrol_route_coverage DOUBLE,
        near_patrol_but_uncovered_flag BOOLEAN,
        static_potential DOUBLE,
        exposure_score DOUBLE,
        record_count BIGINT
    """,
    "junction_basins": """
        zone_id VARCHAR,
        time_window_start TIMESTAMP,
        hidden_junction_id VARCHAR,
        junction_basin_raw_impact DOUBLE,
        junction_basin_pfdi DOUBLE,
        hidden_no_junction_spillover_count BIGINT,
        hidden_no_junction_spillover_impact DOUBLE
    """,
}


def _sql_literal_path(path: str | Path) -> str:
    """Return an absolute path SQL string literal."""

    return "'" + str(Path(path).resolve()).replace("'", "''") + "'"


def _drop_relation(con: duckdb.DuckDBPyConnection, name: str) -> None:
    """Drop a relation whether it is currently a table or view."""

    for statement in (f"DROP VIEW IF EXISTS {name}", f"DROP TABLE IF EXISTS {name}"):
        try:
            con.execute(statement)
        except duckdb.CatalogException:
            continue


def _create_empty_table(con: duckdb.DuckDBPyConnection, name: str, schema: str) -> None:
    """Create an empty table with a stable API-facing schema."""

    _drop_relation(con, name)
    con.execute(f"CREATE TABLE {name} ({schema})")


def _create_parquet_view_or_empty(
    con: duckdb.DuckDBPyConnection,
    name: str,
    path: str | Path,
    fallback_schema: str,
) -> None:
    """Create a view over parquet when available, otherwise an empty table."""

    artifact = Path(path)
    _drop_relation(con, name)
    if artifact.exists():
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet({_sql_literal_path(artifact)})")
    else:
        con.execute(f"CREATE TABLE {name} ({fallback_schema})")


def _json_safe(value: Any) -> str:
    """Serialize app metadata as compact JSON."""

    return json.dumps(value, default=str, separators=(",", ":"))


def _zone_concentration_from_geojson(
    zones_geojson_path: str | Path = ZONES_GEOJSON_PATH,
    *,
    active_zone_min_records: int = 100,
) -> dict[str, Any] | None:
    """Compute audit-facing zone concentration from the generated GeoJSON."""

    path = Path(zones_geojson_path)
    if not path.exists():
        return None
    try:
        geojson = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    counts = []
    active_records = 0
    for feature in geojson.get("features", []):
        properties = feature.get("properties") or {}
        count = int(properties.get("record_count") or 0)
        counts.append(count)
        if bool(properties.get("is_active_zone")) or count >= active_zone_min_records:
            active_records += count
    if not counts:
        return None

    counts = sorted(counts, reverse=True)
    total_zones = len(counts)
    total_records = sum(counts)
    denominator = max(total_records, 1)
    active_zones = sum(1 for count in counts if count >= active_zone_min_records)
    top_1_count = max(1, int(total_zones * 0.01 + 0.999999)) if total_zones else 0
    top_1_records = sum(counts[:top_1_count]) if top_1_count else 0
    top_10_records = sum(counts[:10]) if total_zones else 0
    return {
        "available": True,
        "total_zones": total_zones,
        "active_zones": active_zones,
        "active_zone_min_records": active_zone_min_records,
        "records_covered_by_active_zones": active_records,
        "total_records": total_records,
        "top_1_percent_zone_concentration": float(top_1_records / denominator),
        "top_10_zone_concentration": float(top_10_records / denominator),
        "top_10_zone_share": float(top_10_records / denominator),
    }


def _seed_audit_summary(con: duckdb.DuckDBPyConnection, eda_summary_path: str | Path = EDA_SUMMARY_PATH) -> None:
    """Seed audit_summary and hourly_audit from the JSON EDA artifact."""

    _drop_relation(con, "audit_summary")
    con.execute(
        """
        CREATE TABLE audit_summary (
            id INTEGER,
            total_rows BIGINT,
            total_columns BIGINT,
            date_start VARCHAR,
            date_end VARCHAR,
            morning_count BIGINT,
            evening_count BIGINT,
            evening_gap_ratio DOUBLE,
            summary_json VARCHAR
        )
        """
    )
    _create_empty_table(con, "hourly_audit", EMPTY_SCHEMAS["hourly_audit"])

    path = Path(eda_summary_path)
    if not path.exists():
        con.execute("INSERT INTO audit_summary VALUES (1, 0, 0, NULL, NULL, 0, 0, NULL, '{}')")
        return

    summary = json.loads(path.read_text(encoding="utf-8"))
    zone_concentration = _zone_concentration_from_geojson()
    if zone_concentration is not None:
        summary["top_zone_concentration"] = zone_concentration
    date_range = summary.get("actual_date_range", {})
    con.execute(
        """
        INSERT INTO audit_summary
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            1,
            int(summary.get("total_rows") or 0),
            int(summary.get("total_columns") or 0),
            date_range.get("start"),
            date_range.get("end"),
            int(summary.get("morning_count_0730_1530") or 0),
            int(summary.get("evening_count_1530_2030") or 0),
            summary.get("evening_gap_ratio_morning_over_evening"),
            _json_safe(summary),
        ],
    )
    hourly = summary.get("hour_of_day_distribution", {})
    total = sum(int(count) for count in hourly.values()) or 1
    for hour_text, count in sorted(hourly.items(), key=lambda item: int(item[0])):
        count_int = int(count)
        con.execute(
            "INSERT INTO hourly_audit VALUES (?, ?, ?)",
            [int(hour_text), count_int, count_int / total],
        )


def _seed_zones_geojson(con: duckdb.DuckDBPyConnection, zones_geojson_path: str | Path = ZONES_GEOJSON_PATH) -> None:
    """Store the zone GeoJSON document and a small zone index table."""

    _drop_relation(con, "zones_geojson")
    _drop_relation(con, "zones")
    con.execute(
        """
        CREATE TABLE zones_geojson (
            layer VARCHAR,
            geojson VARCHAR,
            source_path VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE zones (
            zone_id VARCHAR,
            centroid_lat DOUBLE,
            centroid_lon DOUBLE,
            geometry_json VARCHAR
        )
        """
    )
    path = Path(zones_geojson_path)
    if not path.exists():
        con.execute(
            "INSERT INTO zones_geojson VALUES ('zones', ?, ?)",
            [_json_safe({"type": "FeatureCollection", "features": []}), str(path)],
        )
        return

    geojson_text = path.read_text(encoding="utf-8")
    con.execute("INSERT INTO zones_geojson VALUES ('zones', ?, ?)", [geojson_text, str(path)])
    try:
        geojson = json.loads(geojson_text)
    except json.JSONDecodeError:
        return
    for feature in geojson.get("features", []):
        properties = feature.get("properties") or {}
        zone_id = properties.get("zone_id") or properties.get("id")
        if zone_id is None:
            continue
        con.execute(
            "INSERT INTO zones VALUES (?, ?, ?, ?)",
            [
                str(zone_id),
                properties.get("centroid_lat"),
                properties.get("centroid_lon"),
                _json_safe(feature.get("geometry")),
            ],
        )


def _seed_model_metrics(con: duckdb.DuckDBPyConnection) -> None:
    """Seed model metric JSON artifacts into one table."""

    _drop_relation(con, "model_metrics")
    con.execute(
        """
        CREATE TABLE model_metrics (
            metric_source VARCHAR,
            metrics_json VARCHAR,
            source_path VARCHAR,
            updated_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )
    for metric_source, path in (
        ("be_sthgt", DEEP_METRICS_PATH),
        ("lightgbm_ranker", RANKER_METRICS_PATH),
    ):
        artifact = Path(path)
        if artifact.exists():
            con.execute(
                "INSERT INTO model_metrics(metric_source, metrics_json, source_path) VALUES (?, ?, ?)",
                [metric_source, artifact.read_text(encoding="utf-8"), str(artifact)],
            )


def _seed_station_summary(con: duckdb.DuckDBPyConnection) -> None:
    """Create a station summary table from predictions or zone-time features."""

    _drop_relation(con, "station_summary")
    prediction_columns = {
        row[1] for row in con.execute("PRAGMA table_info('predictions')").fetchall()
    }
    if {"police_station", "predicted_pfdi", "coverage_gap", "blindspot_risk_score"}.issubset(prediction_columns):
        con.execute(
            """
            CREATE TABLE station_summary AS
            SELECT
                police_station,
                count(*) AS row_count,
                avg(predicted_pfdi) AS avg_predicted_pfdi,
                avg(hotspot_probability) AS avg_hotspot_probability,
                avg(coverage_gap) AS avg_coverage_gap,
                avg(blindspot_risk_score) AS avg_blindspot_risk_score,
                max(deployment_priority_balanced) AS max_balanced_priority
            FROM predictions
            GROUP BY police_station
            """
        )
        return
    zone_columns = {
        row[1] for row in con.execute("PRAGMA table_info('zone_time_features')").fetchall()
    }
    if {"police_station", "observed_pfdi", "coverage_gap", "blindspot_risk"}.issubset(zone_columns):
        con.execute(
            """
            CREATE TABLE station_summary AS
            SELECT
                police_station,
                count(*) AS row_count,
                avg(observed_pfdi) AS avg_predicted_pfdi,
                NULL::DOUBLE AS avg_hotspot_probability,
                avg(coverage_gap) AS avg_coverage_gap,
                avg(blindspot_risk) AS avg_blindspot_risk_score,
                max(observed_pfdi) AS max_balanced_priority
            FROM zone_time_features
            GROUP BY police_station
            """
        )
        return
    con.execute(
        """
        CREATE TABLE station_summary (
            police_station VARCHAR,
            row_count BIGINT,
            avg_predicted_pfdi DOUBLE,
            avg_hotspot_probability DOUBLE,
            avg_coverage_gap DOUBLE,
            avg_blindspot_risk_score DOUBLE,
            max_balanced_priority DOUBLE
        )
        """
    )


def _ensure_feedback_table(con: duckdb.DuckDBPyConnection, *, rebuild: bool = False) -> None:
    """Create the feedback table used by the API learning loop."""

    if rebuild:
        _drop_relation(con, "feedback")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            feedback_id VARCHAR,
            created_at TIMESTAMP DEFAULT current_timestamp,
            zone_id VARCHAR,
            window_start TIMESTAMP,
            police_station VARCHAR,
            action_taken VARCHAR,
            officers_deployed INTEGER,
            tow_units_used INTEGER,
            vehicles_found INTEGER,
            vehicles_removed INTEGER,
            vehicles_towed INTEGER,
            road_cleared BOOLEAN,
            approx_queue_length_m DOUBLE,
            notes VARCHAR,
            payload_json VARCHAR
        )
        """
    )
    required_columns = {
        "action_taken": "VARCHAR",
        "officers_deployed": "INTEGER",
        "tow_units_used": "INTEGER",
        "vehicles_found": "INTEGER",
        "vehicles_removed": "INTEGER",
        "vehicles_towed": "INTEGER",
        "road_cleared": "BOOLEAN",
        "approx_queue_length_m": "DOUBLE",
    }
    existing_columns = {row[1] for row in con.execute("PRAGMA table_info('feedback')").fetchall()}
    for column, column_type in required_columns.items():
        if column not in existing_columns:
            con.execute(f"ALTER TABLE feedback ADD COLUMN {column} {column_type}")


def initialize_duckdb(
    db_path: str | Path = APP_DB_PATH,
    *,
    rebuild: bool = False,
) -> Path:
    """Create the CurbFlow DuckDB app database from generated artifacts."""

    destination = Path(db_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if rebuild and destination.exists():
        destination.unlink()

    con = duckdb.connect(str(destination))
    try:
        _seed_audit_summary(con)
        _create_parquet_view_or_empty(
            con,
            "coverage_audit",
            COVERAGE_AUDIT_PATH,
            """
            total_rows BIGINT,
            morning_count_0730_1530 BIGINT,
            evening_count_1530_2030 BIGINT,
            evening_gap_ratio_morning_over_evening DOUBLE,
            data_sent_to_scita_rate DOUBLE,
            top_zone_concentration_available BOOLEAN,
            top_zone_concentration_note VARCHAR
            """,
        )
        _seed_zones_geojson(con)
        _create_parquet_view_or_empty(
            con,
            "zone_time_features",
            ZONE_TIME_FEATURES_PATH,
            EMPTY_SCHEMAS["zone_time_features"],
        )
        _create_parquet_view_or_empty(
            con,
            "predictions",
            PREDICTIONS_PATH,
            EMPTY_SCHEMAS["predictions"],
        )
        _create_parquet_view_or_empty(
            con,
            "recommendations",
            RECOMMENDATIONS_PATH,
            EMPTY_SCHEMAS["recommendations"],
        )
        _seed_model_metrics(con)
        _create_parquet_view_or_empty(
            con,
            "patrol_myopia",
            PATROL_MYOPIA_PATH,
            EMPTY_SCHEMAS["patrol_myopia"],
        )
        _create_parquet_view_or_empty(
            con,
            "patrol_graph_edges",
            PATROL_GRAPH_EDGES_PATH,
            EMPTY_SCHEMAS["patrol_graph_edges"],
        )
        _create_parquet_view_or_empty(
            con,
            "patrol_graph_features",
            PATROL_GRAPH_FEATURES_PATH,
            EMPTY_SCHEMAS["patrol_graph_features"],
        )
        _create_parquet_view_or_empty(
            con,
            "junction_basins",
            JUNCTION_BASINS_PATH,
            EMPTY_SCHEMAS["junction_basins"],
        )
        _seed_station_summary(con)
        _ensure_feedback_table(con, rebuild=rebuild)
    finally:
        con.close()
    return destination
