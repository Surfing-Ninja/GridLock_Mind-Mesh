from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import duckdb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .settings import settings


app = FastAPI(title="CurbFlow AI API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PlannerRequest(BaseModel):
    police_station: str | None = None
    window_start: datetime | None = None
    available_officers: int = Field(20, ge=1, le=500)
    available_tow_units: int = Field(4, ge=0, le=100)
    mode: Literal["conservative", "balanced", "discovery"] = "balanced"


class FeedbackPayload(BaseModel):
    zone_id: str
    window_start: datetime
    police_station: str
    action_taken: str
    officers_deployed: int = Field(ge=0)
    tow_units_used: int = Field(ge=0)
    vehicles_found: int = Field(ge=0)
    vehicles_removed: int = Field(ge=0)
    vehicles_towed: int = Field(ge=0)
    road_cleared: bool
    approx_queue_length_m: float | None = Field(default=None, ge=0)
    notes: str | None = None


def _connect() -> duckdb.DuckDBPyConnection:
    if not settings.duckdb_path.exists():
        raise HTTPException(status_code=503, detail="DuckDB artifact missing. Run `python -m curbflow.cli run-all` first.")
    return duckdb.connect(str(settings.duckdb_path), read_only=True)


def _rows(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with _connect() as conn:
        return conn.execute(sql, params or []).fetchdf().to_dict(orient="records")


def _one(sql: str, params: list[Any] | None = None) -> dict[str, Any]:
    rows = _rows(sql, params)
    return rows[0] if rows else {}


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "duckdb_exists": settings.duckdb_path.exists(), "service": "curbflow-ai"}


@app.get("/audit/summary")
def audit_summary() -> dict[str, Any]:
    report = settings.reports_dir / "eda_summary.json"
    if report.exists():
        return json.loads(report.read_text(encoding="utf-8"))
    return _one(
        """
        SELECT
          COUNT(*) AS zone_time_rows,
          MIN(window_start) AS first_window,
          MAX(window_start) AS last_window,
          AVG(exposure) AS average_exposure,
          AVG(coverage_gap) AS average_coverage_gap
        FROM zone_time_features
        """
    )


@app.get("/audit/hourly")
def audit_hourly() -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT hour, SUM(event_count) AS records, AVG(exposure) AS exposure, AVG(blindspot_risk) AS blindspot_risk
        FROM zone_time_features
        GROUP BY hour
        ORDER BY hour
        """
    )


@app.get("/zones/geojson")
def zones_geojson() -> dict[str, Any]:
    path = settings.processed_dir / "zones.geojson"
    if not path.exists():
        raise HTTPException(status_code=503, detail="zones.geojson missing. Run the pipeline first.")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/hotspots")
def hotspots(limit: int = 50) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT zone_id, police_station, zone_center_lat, zone_center_lon, observed_pfdi, final_risk_score,
               hotspot_probability, road_corridor, place_type
        FROM predictions
        QUALIFY ROW_NUMBER() OVER (PARTITION BY zone_id ORDER BY window_start DESC) = 1
        ORDER BY observed_pfdi DESC, final_risk_score DESC
        LIMIT ?
        """,
        [limit],
    )


@app.get("/blindspots")
def blindspots(limit: int = 50) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT zone_id, police_station, zone_center_lat, zone_center_lon, blindspot_risk, coverage_gap,
               static_potential, exposure, road_corridor, place_type
        FROM predictions
        QUALIFY ROW_NUMBER() OVER (PARTITION BY zone_id ORDER BY window_start DESC) = 1
        ORDER BY blindspot_risk DESC, coverage_gap DESC
        LIMIT ?
        """,
        [limit],
    )


@app.get("/zones/{zone_id}")
def zone_detail(zone_id: str) -> dict[str, Any]:
    summary = _one(
        """
        SELECT zone_id, police_station, zone_center_lat, zone_center_lon, AVG(observed_pfdi) AS observed_pfdi,
               AVG(final_risk_score) AS final_risk_score, AVG(blindspot_risk) AS blindspot_risk,
               AVG(exposure) AS exposure, AVG(coverage_gap) AS coverage_gap,
               ANY_VALUE(road_corridor) AS road_corridor, ANY_VALUE(place_type) AS place_type
        FROM predictions
        WHERE zone_id = ?
        GROUP BY zone_id, police_station, zone_center_lat, zone_center_lon
        """,
        [zone_id],
    )
    if not summary:
        raise HTTPException(status_code=404, detail="Zone not found")
    summary["timeline"] = _rows(
        """
        SELECT window_start, event_count, observed_pfdi, exposure, blindspot_risk, final_risk_score
        FROM predictions
        WHERE zone_id = ?
        ORDER BY window_start
        """,
        [zone_id],
    )
    return summary


@app.get("/junction-basins")
def junction_basins(limit: int = 50) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT junction_name, police_station, AVG(junction_basin_risk) AS junction_basin_pfdi,
               SUM(event_count) AS records, AVG(named_junction_share) AS named_junction_share,
               AVG(observed_pfdi) AS observed_pfdi
        FROM predictions
        GROUP BY junction_name, police_station
        ORDER BY junction_basin_pfdi DESC
        LIMIT ?
        """,
        [limit],
    )


@app.get("/patrol/summary")
def patrol_summary() -> dict[str, Any]:
    stations = _rows("SELECT * FROM station_metrics ORDER BY patrol_myopia_index DESC")
    top = _rows(
        """
        SELECT police_station, AVG(exposure) AS exposure, AVG(coverage_gap) AS coverage_gap,
               AVG(blindspot_risk) AS blindspot_risk
        FROM predictions
        GROUP BY police_station
        ORDER BY blindspot_risk DESC
        LIMIT 20
        """
    )
    return {"stations": stations, "coverage": top}


@app.get("/metrics/model")
def model_metrics() -> dict[str, Any]:
    path = settings.metrics_dir / "metrics.json"
    if not path.exists():
        raise HTTPException(status_code=503, detail="metrics.json missing. Run the pipeline first.")
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/planner/recommend")
def planner_recommend(request: PlannerRequest) -> dict[str, Any]:
    weights = {
        "conservative": (0.85, 0.15),
        "balanced": (0.70, 0.30),
        "discovery": (0.55, 0.45),
    }[request.mode]
    where = "WHERE police_station = ?" if request.police_station else ""
    params: list[Any] = [request.police_station] if request.police_station else []
    rows = _rows(
        f"""
        SELECT *, ({weights[0]} * final_risk_score + {weights[1]} * blindspot_risk) AS risk_score
        FROM predictions
        {where}
        QUALIFY ROW_NUMBER() OVER (PARTITION BY zone_id ORDER BY window_start DESC) = 1
        ORDER BY risk_score DESC
        LIMIT ?
        """,
        params + [max(request.available_officers * 2, 10)],
    )
    recommendations = []
    officers_left = request.available_officers
    tow_left = request.available_tow_units
    known = 0
    blind = 0
    for row in rows:
        if officers_left <= 0:
            break
        action = "towing_support" if row.get("large_vehicle_share", 0) > 0.25 and tow_left > 0 else ("evening_audit_patrol" if row["blindspot_risk"] > row["observed_pfdi"] else "beat_patrol")
        tow_units = 1 if action == "towing_support" and tow_left > 0 else 0
        officers = min(2 if action in {"towing_support", "evening_audit_patrol"} else 1, officers_left)
        officers_left -= officers
        tow_left -= tow_units
        if row["blindspot_risk"] > row["observed_pfdi"]:
            blind += officers
        else:
            known += officers
        recommendations.append(
            {
                "rank": len(recommendations) + 1,
                "zone_id": row["zone_id"],
                "police_station": row["police_station"],
                "risk_score": round(float(row["risk_score"]), 2),
                "blindspot_score": round(float(row["blindspot_risk"]), 2),
                "observed_pfdi": round(float(row["observed_pfdi"]), 2),
                "recommended_action": action,
                "officers": officers,
                "tow_units": tow_units,
                "road_corridor": row.get("road_corridor"),
                "reason": _planner_reasons(row),
                "lat": row["zone_center_lat"],
                "lon": row["zone_center_lon"],
            }
        )
    expected = sum(item["risk_score"] for item in recommendations) / max(sum(row["risk_score"] for row in rows[: len(recommendations)]), 1)
    return {
        "summary": {
            "mode": request.mode,
            "known_hotspot_allocations": known,
            "blindspot_audit_allocations": blind,
            "expected_risk_coverage": round(float(expected), 3),
            "officers_used": request.available_officers - officers_left,
            "tow_units_used": request.available_tow_units - tow_left,
        },
        "recommendations": recommendations,
    }


def _planner_reasons(row: dict[str, Any]) -> list[str]:
    reasons = []
    if row.get("final_risk_score", 0) >= 70:
        reasons.append("High predicted PFDI")
    if row.get("blindspot_risk", 0) >= 45:
        reasons.append("High blindspot audit priority")
    if row.get("coverage_gap", 0) >= 0.50:
        reasons.append("Low enforcement visibility")
    if row.get("large_vehicle_share", 0) >= 0.25:
        reasons.append("High large-vehicle obstruction share")
    return reasons or ["Balanced exploit/explore priority"]


@app.post("/feedback")
def feedback(payload: FeedbackPayload) -> dict[str, Any]:
    settings.app_dir.mkdir(parents=True, exist_ok=True)
    record = payload.model_dump(mode="json")
    record["received_at"] = datetime.utcnow().isoformat() + "Z"
    with settings.feedback_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    return {"status": "accepted", "message": "Feedback captured for future outcome learning."}
