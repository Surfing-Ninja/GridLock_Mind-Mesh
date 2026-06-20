"""DuckDB-backed feedback aggregation for future action-effectiveness learning."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from curbflow.db.duckdb_init import APP_DB_PATH


def _payload_to_dict(payload: Any) -> dict[str, Any]:
    """Normalize mapping, dataclass, or Pydantic-like feedback payloads."""

    if payload is None:
        return {}
    if isinstance(payload, dict):
        return dict(payload)
    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    if hasattr(payload, "dict"):
        return payload.dict()
    return dict(payload)


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a DataFrame to JSON-friendly records."""

    output: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        clean_row = {}
        for key, value in row.items():
            if isinstance(value, pd.Timestamp):
                clean_row[key] = value.isoformat()
            elif pd.isna(value):
                clean_row[key] = None
            elif hasattr(value, "item"):
                clean_row[key] = value.item()
            else:
                clean_row[key] = value
        output.append(clean_row)
    return output


def _connect(db_path: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    """Open the CurbFlow application DuckDB database."""

    path = Path(db_path or APP_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))


def ensure_feedback_learning_tables(db_path: str | Path | None = None) -> None:
    """Create learning-loop tables if they are missing."""

    with _connect(db_path) as con:
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
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_records (
                feedback_id VARCHAR PRIMARY KEY,
                zone_id VARCHAR,
                window_start TIMESTAMP,
                police_station VARCHAR,
                recommended_action VARCHAR,
                action_taken VARCHAR,
                predicted_risk DOUBLE,
                officers_deployed INTEGER,
                tow_units_used INTEGER,
                vehicles_found INTEGER,
                vehicles_removed INTEGER,
                vehicles_towed INTEGER,
                road_cleared BOOLEAN,
                approx_queue_length_m DOUBLE,
                notes VARCHAR,
                created_at TIMESTAMP DEFAULT current_timestamp,
                payload_json VARCHAR
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS action_effectiveness (
                action_taken VARCHAR,
                police_station VARCHAR,
                samples INTEGER,
                avg_predicted_risk DOUBLE,
                avg_vehicles_found DOUBLE,
                avg_vehicles_removed DOUBLE,
                avg_vehicles_towed DOUBLE,
                clearance_rate DOUBLE,
                avg_queue_length_m DOUBLE,
                outcome_feedback DOUBLE,
                future_action_effectiveness DOUBLE,
                updated_at TIMESTAMP DEFAULT current_timestamp,
                PRIMARY KEY (action_taken, police_station)
            )
            """
        )


def record_feedback(
    feedback: Any,
    *,
    predicted_risk: float | None = None,
    recommended_action: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Record a deployment feedback payload for future learning-loop aggregation."""

    payload = _payload_to_dict(feedback)
    feedback_id = str(payload.get("feedback_id") or uuid.uuid4())
    ensure_feedback_learning_tables(db_path)
    with _connect(db_path) as con:
        con.execute(
            """
            INSERT OR REPLACE INTO feedback_records (
                feedback_id,
                zone_id,
                window_start,
                police_station,
                recommended_action,
                action_taken,
                predicted_risk,
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
            VALUES (?, ?, CAST(? AS TIMESTAMP), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                feedback_id,
                payload.get("zone_id"),
                payload.get("window_start"),
                payload.get("police_station", payload.get("station")),
                recommended_action or payload.get("recommended_action"),
                payload.get("action_taken", payload.get("action")),
                predicted_risk if predicted_risk is not None else payload.get("predicted_risk"),
                int(payload.get("officers_deployed") or 0),
                int(payload.get("tow_units_used") or 0),
                int(payload.get("vehicles_found") or 0),
                int(payload.get("vehicles_removed") or 0),
                int(payload.get("vehicles_towed") or 0),
                bool(payload.get("road_cleared")),
                payload.get("approx_queue_length_m"),
                payload.get("notes"),
                json.dumps(payload, default=str),
            ],
        )
    return {"feedback_id": feedback_id, "saved": True}


def aggregate_action_effectiveness(
    *,
    min_samples: int = 1,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Aggregate deployment feedback into station-action effectiveness scores."""

    ensure_feedback_learning_tables(db_path)
    with _connect(db_path) as con:
        con.execute(
            """
            INSERT OR REPLACE INTO action_effectiveness (
                action_taken,
                police_station,
                samples,
                avg_predicted_risk,
                avg_vehicles_found,
                avg_vehicles_removed,
                avg_vehicles_towed,
                clearance_rate,
                avg_queue_length_m,
                outcome_feedback,
                future_action_effectiveness,
                updated_at
            )
            WITH feedback_source AS (
                SELECT
                    action_taken,
                    COALESCE(police_station, 'unknown') AS police_station,
                    predicted_risk,
                    vehicles_found,
                    vehicles_removed,
                    vehicles_towed,
                    road_cleared,
                    approx_queue_length_m
                FROM feedback_records
                UNION ALL
                SELECT
                    action_taken,
                    COALESCE(police_station, 'unknown') AS police_station,
                    NULL AS predicted_risk,
                    vehicles_found,
                    vehicles_removed,
                    vehicles_towed,
                    road_cleared,
                    approx_queue_length_m
                FROM feedback
            ),
            scored AS (
                SELECT
                    action_taken,
                    police_station,
                    count(*) AS samples,
                    avg(predicted_risk) AS avg_predicted_risk,
                    avg(vehicles_found) AS avg_vehicles_found,
                    avg(vehicles_removed) AS avg_vehicles_removed,
                    avg(vehicles_towed) AS avg_vehicles_towed,
                    avg(CASE WHEN road_cleared THEN 1 ELSE 0 END) AS clearance_rate,
                    avg(approx_queue_length_m) AS avg_queue_length_m,
                    avg(
                        COALESCE(vehicles_removed, 0)
                        + 1.5 * COALESCE(vehicles_towed, 0)
                        + CASE WHEN road_cleared THEN 3 ELSE 0 END
                    ) AS outcome_feedback
                FROM feedback_source
                WHERE action_taken IS NOT NULL
                GROUP BY action_taken, police_station
                HAVING count(*) >= ?
            )
            SELECT
                action_taken,
                police_station,
                samples,
                avg_predicted_risk,
                avg_vehicles_found,
                avg_vehicles_removed,
                avg_vehicles_towed,
                clearance_rate,
                avg_queue_length_m,
                outcome_feedback,
                CASE
                    WHEN avg_predicted_risk IS NULL OR avg_predicted_risk <= 0 THEN NULL
                    ELSE outcome_feedback / avg_predicted_risk
                END AS future_action_effectiveness,
                current_timestamp AS updated_at
            FROM scored
            """,
            [max(1, int(min_samples))],
        )
        frame = con.execute(
            """
            SELECT *
            FROM action_effectiveness
            WHERE samples >= ?
            ORDER BY future_action_effectiveness DESC NULLS LAST, samples DESC
            """,
            [max(1, int(min_samples))],
        ).fetchdf()
    return _records(frame)


def get_effectiveness_overrides(
    *,
    station: str | None = None,
    min_samples: int = 1,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return stored action-effectiveness aggregates for optional future planner use."""

    ensure_feedback_learning_tables(db_path)
    with _connect(db_path) as con:
        frame = con.execute(
            """
            SELECT *
            FROM action_effectiveness
            WHERE samples >= ?
              AND (? IS NULL OR lower(police_station) = lower(?))
            ORDER BY future_action_effectiveness DESC NULLS LAST, samples DESC
            """,
            [max(1, int(min_samples)), station, station],
        ).fetchdf()
    return _records(frame)
