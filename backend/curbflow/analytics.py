from __future__ import annotations

import ast
import json
import math
import re
from pathlib import Path
from typing import Any

import duckdb
import networkx as nx
import numpy as np
import pandas as pd

from .modeling import train_and_score
from .settings import CurbFlowSettings, settings


NULL_OUTCOME_COLUMNS = ["description", "closed_datetime", "action_taken_timestamp"]
PII_COLUMNS = ["vehicle_number", "updated_vehicle_number", "device_id", "created_by_id"]
EVENING_HOURS = {17, 18, 19, 20, 21}

VIOLATION_WEIGHTS = {
    "DOUBLE PARKING": 1.00,
    "PARKING IN A MAIN ROAD": 0.95,
    "PARKING IN MAIN ROAD": 0.95,
    "PARKING NEAR ROAD CROSSING": 0.90,
    "PARKING NEAR TRAFFIC LIGHT": 0.88,
    "PARKING NEAR ZEBRA CROSSING": 0.88,
    "PARKING OPPOSITE ANOTHER PARKED VEHICLE": 0.86,
    "PARKING NEAR BUS STOP": 0.85,
    "PARKING NEAR SCHOOL": 0.85,
    "PARKING NEAR HOSPITAL": 0.85,
    "PARKING OTHER THAN BUS STOP": 0.75,
    "NO PARKING": 0.70,
    "WRONG PARKING": 0.65,
    "PARKING ON FOOTPATH": 0.55,
    "DEFECTIVE NUMBER PLATE": 0.15,
}

VEHICLE_WEIGHTS = {
    "HGV": 1.00,
    "LORRY": 1.00,
    "TANKER": 1.00,
    "PRIVATE BUS": 1.00,
    "BMTC": 1.00,
    "KSRTC": 1.00,
    "LGV": 0.90,
    "TEMPO": 0.90,
    "MINI LORRY": 0.90,
    "MAXI": 0.85,
    "VAN": 0.85,
    "CAR": 0.75,
    "JEEP": 0.75,
    "GOODS AUTO": 0.65,
    "AUTO": 0.58,
    "SCOOTER": 0.35,
    "MOTOR": 0.35,
    "BIKE": 0.35,
    "MOPED": 0.25,
}

VALIDATION_CONFIDENCE = {
    "approved": 1.00,
    "nan": 0.70,
    "null": 0.70,
    "": 0.70,
    "created1": 0.55,
    "processing": 0.55,
    "rejected": 0.25,
    "duplicate": 0.10,
}

PLACE_TYPES = {
    "commercial_market": ["market", "mall", "bazaar", "shop", "commercial", "complex"],
    "transit_node": ["metro", "bus", "station", "stand", "railway"],
    "institutional": ["school", "college", "hospital", "university", "clinic"],
    "airport_zone": ["airport"],
    "religious_place": ["temple", "mosque", "church", "masjid"],
    "residential_layout": ["layout", "residency", "apartment", "colony"],
    "entertainment": ["cinema", "theatre", "club", "hotel", "restaurant"],
}


def _safe_norm(series: pd.Series) -> pd.Series:
    values = series.fillna(0).astype(float)
    lo = values.min()
    hi = values.max()
    if hi - lo < 1e-9:
        return pd.Series(np.zeros(len(values)), index=series.index)
    return (values - lo) / (hi - lo)


def _parse_list(value: Any) -> list[str]:
    if pd.isna(value) or str(value).upper() == "NULL":
        return []
    try:
        parsed = ast.literal_eval(str(value))
        if isinstance(parsed, list):
            return [str(item).strip().upper() for item in parsed]
    except (ValueError, SyntaxError):
        pass
    return [part.strip().upper() for part in re.split(r"[,;/|]+", str(value)) if part.strip()]


def _contains_any(text: str, needles: list[str]) -> bool:
    lowered = text.lower()
    return any(needle in lowered for needle in needles)


def _vehicle_weight(value: Any) -> float:
    text = str(value or "").upper()
    for key, weight in VEHICLE_WEIGHTS.items():
        if key in text:
            return weight
    return 0.60


def _place_type(text: str) -> str:
    lowered = text.lower()
    for place, tokens in PLACE_TYPES.items():
        if any(token in lowered for token in tokens):
            return place
    return "unknown"


def _road_corridor(text: str) -> str:
    cleaned = re.sub(r"\([^)]*\)", " ", str(text))
    parts = [p.strip() for p in cleaned.split(",") if p.strip()]
    for part in parts:
        if re.search(r"\b(road|rd|street|st|main|cross|ring|highway|flyover|circle)\b", part, re.I):
            return re.sub(r"\s+", " ", part).title()[:80]
    return (parts[0].title() if parts else "Unknown Corridor")[:80]


def _zone_polygon(center_lat: float, center_lon: float, lat_step: float, lon_step: float) -> list[list[float]]:
    half_lat = lat_step / 2
    half_lon = lon_step / 2
    return [
        [center_lon - half_lon, center_lat - half_lat],
        [center_lon + half_lon, center_lat - half_lat],
        [center_lon + half_lon, center_lat + half_lat],
        [center_lon - half_lon, center_lat + half_lat],
        [center_lon - half_lon, center_lat - half_lat],
    ]


def _audit_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    created = df["created_at_ist"]
    hour_counts = df.groupby(created.dt.hour).size().reindex(range(24), fill_value=0)
    morning_count = int(hour_counts.loc[7:11].sum())
    evening_count = int(hour_counts.loc[17:21].sum())
    return {
        "total_records": int(len(df)),
        "actual_date_range": {
            "start_ist": created.min().isoformat() if len(df) else None,
            "end_ist": created.max().isoformat() if len(df) else None,
            "note": "Filename may say Jan-May; records are audited from created_datetime after UTC to Asia/Kolkata conversion.",
        },
        "null_outcome_columns": {col: float(df[col].isna().mean()) if col in df else 1.0 for col in NULL_OUTCOME_COLUMNS},
        "morning_count": morning_count,
        "evening_count": evening_count,
        "evening_gap_ratio": float(1 - (evening_count / max(morning_count, 1))),
        "scita_success_rate": float(df.get("data_sent_to_scita", pd.Series(dtype=object)).astype(str).str.lower().isin(["true", "1", "yes"]).mean()),
        "warning": "Low evening challans mean low enforcement evidence, not proof of low illegal-parking risk.",
    }


def load_and_clean(config: CurbFlowSettings = settings) -> tuple[pd.DataFrame, dict[str, Any]]:
    config.ensure_dirs()
    if "astram" in config.csv_path.name.lower():
        raise ValueError("CurbFlow Theme 1 must use only the police violation CSV, not ASTraM data.")
    df = pd.read_csv(config.csv_path, na_values=["NULL", "null", "", "NaN"], low_memory=False)
    required = {"latitude", "longitude", "created_datetime", "violation_type", "police_station", "location"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"CSV is missing required Theme 1 columns: {missing}")
    df["created_at_utc"] = pd.to_datetime(df["created_datetime"], utc=True, errors="coerce")
    df = df[df["created_at_utc"].notna()].copy()
    df["created_at_ist"] = df["created_at_utc"].dt.tz_convert(config.timezone)
    df["window_start"] = df["created_at_ist"].dt.floor("3h")
    df["hour"] = df["created_at_ist"].dt.hour
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df = df[df["latitude"].between(12.0, 14.0) & df["longitude"].between(76.0, 78.5)].copy()
    for col in ["validation_status", "updated_vehicle_type", "vehicle_type", "junction_name", "police_station", "location"]:
        if col not in df:
            df[col] = np.nan
    audit = _audit_dataframe(df)
    clean_path = config.interim_dir / "violations_clean.parquet"
    df.to_parquet(clean_path, index=False)
    (config.reports_dir / "eda_summary.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    (config.reports_dir / "data_quality_report.md").write_text(
        "# Data Quality Report\n\n"
        f"- Records loaded: {audit['total_records']:,}\n"
        f"- Actual IST date range: {audit['actual_date_range']['start_ist']} to {audit['actual_date_range']['end_ist']}\n"
        f"- Null outcome columns: {audit['null_outcome_columns']}\n"
        f"- Evening records: {audit['evening_count']:,}; morning records: {audit['morning_count']:,}\n\n"
        "The dataset is an enforcement visibility log. `description`, `closed_datetime`, and `action_taken_timestamp` are not used as outcome labels.\n",
        encoding="utf-8",
    )
    return df, audit


def score_rows(df: pd.DataFrame, config: CurbFlowSettings = settings) -> pd.DataFrame:
    scored = df.copy()
    scored["violation_labels"] = scored["violation_type"].map(_parse_list)
    scored["violation_severity"] = scored["violation_labels"].map(
        lambda labels: 1 - math.prod([1 - VIOLATION_WEIGHTS.get(label, 0.10) for label in labels]) if labels else 0.10
    )
    vehicle_type = scored["updated_vehicle_type"].fillna(scored["vehicle_type"])
    scored["vehicle_obstruction"] = vehicle_type.map(_vehicle_weight)
    combined_text = (scored["location"].fillna("") + " " + scored["junction_name"].fillna("") + " " + scored["violation_type"].fillna("")).astype(str)
    scored["named_junction_flag"] = scored["junction_name"].fillna("").astype(str).str.lower().ne("no junction") & scored["junction_name"].notna()
    scored["main_road_flag"] = combined_text.str.contains("main road|main rd|ring road|highway", case=False, regex=True)
    scored["crossing_signal_flag"] = combined_text.str.contains("crossing|traffic light|signal|zebra", case=False, regex=True)
    scored["bus_school_hospital_flag"] = combined_text.str.contains("bus stop|school|hospital|college", case=False, regex=True)
    scored["double_parking_flag"] = combined_text.str.contains("double parking", case=False, regex=False)
    scored["location_criticality"] = (
        0.35 * scored["named_junction_flag"].astype(float)
        + 0.25 * scored["main_road_flag"].astype(float)
        + 0.20 * scored["crossing_signal_flag"].astype(float)
        + 0.15 * scored["bus_school_hospital_flag"].astype(float)
        + 0.05 * scored["double_parking_flag"].astype(float)
    ).clip(0, 1)
    validation_key = scored["validation_status"].fillna("unknown").astype(str).str.strip().str.lower()
    scored["validation_confidence"] = validation_key.map(VALIDATION_CONFIDENCE).fillna(0.70)
    global_approved = validation_key.eq("approved").mean()
    global_rejected = validation_key.eq("rejected").mean()
    alpha = 100.0
    for entity, col in {"device": "device_id", "user": "created_by_id"}.items():
        if col in scored:
            stats = scored.groupby(col, dropna=False).agg(
                approved=("validation_status", lambda s: s.fillna("").astype(str).str.lower().eq("approved").sum()),
                rejected=("validation_status", lambda s: s.fillna("").astype(str).str.lower().eq("rejected").sum()),
                total=("validation_status", "size"),
                scita=("data_sent_to_scita", lambda s: s.astype(str).str.lower().isin(["true", "1", "yes"]).mean()),
            )
            stats[f"{entity}_trust"] = (
                0.45 * ((stats["approved"] + alpha * global_approved) / (stats["total"] + alpha))
                + 0.25 * (1 - ((stats["rejected"] + alpha * global_rejected) / (stats["total"] + alpha)))
                + 0.15
                + 0.15 * stats["scita"].fillna(0)
            ).clip(0, 1)
            scored = scored.join(stats[[f"{entity}_trust"]], on=col)
        else:
            scored[f"{entity}_trust"] = 0.70
    station_quality = scored.groupby("police_station")["validation_confidence"].mean().rename("station_evidence_quality")
    scored = scored.join(station_quality, on="police_station")
    scored["evidence_quality_score"] = (
        0.50 * scored["validation_confidence"]
        + 0.25 * scored["device_trust"].fillna(0.70)
        + 0.15 * scored["user_trust"].fillna(0.70)
        + 0.10 * scored["station_evidence_quality"].fillna(0.70)
    ).clip(0, 1)
    scored = scored.sort_values("created_at_ist")
    scored["previous_vehicle_violations"] = scored.groupby("vehicle_number", dropna=False).cumcount()
    scored["repeat_pressure"] = np.minimum(np.log1p(scored["previous_vehicle_violations"]) / np.log(11), 1.0)
    scored["row_obstruction"] = scored["evidence_quality_score"] * 100 * (
        0.42 * scored["violation_severity"]
        + 0.23 * scored["vehicle_obstruction"]
        + 0.20 * scored["location_criticality"]
        + 0.10 * scored["repeat_pressure"]
        + 0.05 * scored["named_junction_flag"].astype(float)
    )
    scored["place_type"] = combined_text.map(_place_type)
    scored["road_corridor"] = scored["location"].fillna("").map(_road_corridor)
    scored.to_parquet(config.interim_dir / "row_scores.parquet", index=False)
    return scored


def assign_zones(scored: pd.DataFrame, config: CurbFlowSettings = settings) -> pd.DataFrame:
    zoned = scored.copy()
    median_lat = float(zoned["latitude"].median())
    lat_step = config.zone_size_m / 111_320.0
    lon_step = config.zone_size_m / (111_320.0 * max(math.cos(math.radians(median_lat)), 0.1))
    zoned["zone_lat_bin"] = np.floor(zoned["latitude"] / lat_step).astype(int)
    zoned["zone_lon_bin"] = np.floor(zoned["longitude"] / lon_step).astype(int)
    zoned["zone_id"] = "zone_" + zoned["zone_lat_bin"].astype(str) + "_" + zoned["zone_lon_bin"].astype(str)
    zoned["zone_center_lat"] = (zoned["zone_lat_bin"] + 0.5) * lat_step
    zoned["zone_center_lon"] = (zoned["zone_lon_bin"] + 0.5) * lon_step
    zoned.to_parquet(config.interim_dir / "zone_assignments.parquet", index=False)
    return zoned


def build_zone_time_features(zoned: pd.DataFrame, config: CurbFlowSettings = settings) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    grouped = zoned.groupby(["zone_id", "window_start"], dropna=False)
    zone_time = grouped.agg(
        event_count=("id", "size"),
        raw_impact=("row_obstruction", "sum"),
        unique_devices=("device_id", "nunique"),
        unique_users=("created_by_id", "nunique"),
        unique_vehicles=("vehicle_number", "nunique"),
        police_station=("police_station", lambda s: s.mode().iat[0] if not s.mode().empty else "Unknown"),
        zone_center_lat=("zone_center_lat", "first"),
        zone_center_lon=("zone_center_lon", "first"),
        location_criticality=("location_criticality", "mean"),
        repeat_pressure=("repeat_pressure", "mean"),
        repeat_persistence=("previous_vehicle_violations", lambda s: float((s > 0).sum()) / max(len(s), 1)),
        large_vehicle_share=("vehicle_obstruction", lambda s: float((s >= 0.85).mean())),
        scita_success_rate=("data_sent_to_scita", lambda s: s.astype(str).str.lower().isin(["true", "1", "yes"]).mean()),
        validation_coverage=("validation_status", lambda s: s.notna().mean()),
        place_type=("place_type", lambda s: s.mode().iat[0] if not s.mode().empty else "unknown"),
        road_corridor=("road_corridor", lambda s: s.mode().iat[0] if not s.mode().empty else "Unknown Corridor"),
        junction_name=("junction_name", lambda s: s.mode().iat[0] if not s.mode().empty else "No Junction"),
        named_junction_share=("named_junction_flag", "mean"),
        main_road_share=("main_road_flag", "mean"),
    ).reset_index()
    p99 = max(float(zone_time["raw_impact"].quantile(0.99)), 1.0)
    zone_time["observed_pfdi"] = (100 * np.log1p(zone_time["raw_impact"]) / np.log1p(p99)).clip(0, 100)
    zone_time["hour"] = zone_time["window_start"].dt.hour
    zone_time["is_evening_peak"] = zone_time["hour"].isin(EVENING_HOURS).astype(int)
    station_hour = zone_time.groupby(["police_station", "hour"])["event_count"].transform("sum")
    zone_time["station_hour_activity"] = station_hour
    zone_time["patrol_route_coverage"] = 0.0
    graph_edges = build_patrol_transition_graph(zoned, zone_time)
    if not graph_edges.empty:
        coverage = graph_edges.groupby(["source_zone", "window_start"])["edge_weight"].sum().rename("patrol_route_coverage")
        zone_time = zone_time.drop(columns=["patrol_route_coverage"]).join(coverage, on=["zone_id", "window_start"])
        zone_time["patrol_route_coverage"] = zone_time["patrol_route_coverage"].fillna(0.0)
    zone_time["exposure"] = (
        0.25 * _safe_norm(np.log1p(zone_time["unique_devices"]))
        + 0.20 * _safe_norm(np.log1p(zone_time["unique_users"]))
        + 0.15 * _safe_norm(zone_time["station_hour_activity"])
        + 0.15 * _safe_norm(zone_time["patrol_route_coverage"])
        + 0.15 * zone_time["scita_success_rate"].fillna(0)
        + 0.10 * zone_time["validation_coverage"].fillna(0)
    ).clip(0, 1)
    zone_time["coverage_gap"] = 1 - zone_time["exposure"]
    zone_recurrence = zone_time.groupby("zone_id")["event_count"].transform(lambda s: (s > 0).rolling(16, min_periods=1).mean())
    zone_time["recurrence"] = zone_recurrence.fillna(0)
    corridor_risk = zone_time.groupby("road_corridor")["observed_pfdi"].transform("mean")
    zone_time["corridor_risk"] = _safe_norm(corridor_risk) * 100
    zone_time["junction_basin_risk"] = compute_junction_basin_risk(zoned, zone_time)
    zone_time["static_potential"] = (
        0.30 * zone_time.groupby("zone_id")["observed_pfdi"].transform(lambda s: s.quantile(0.90))
        + 0.15 * zone_time["recurrence"] * 100
        + 0.15 * zone_time["location_criticality"] * 100
        + 0.12 * zone_time["large_vehicle_share"] * 100
        + 0.10 * zone_time["repeat_persistence"] * 100
        + 0.08 * zone_time["junction_basin_risk"]
        + 0.05 * zone_time["corridor_risk"]
        + 0.05 * _safe_norm(zone_time["patrol_route_coverage"]) * 100
    ).clip(0, 100)
    peak_priority = np.select(
        [zone_time["is_evening_peak"].eq(1), zone_time["hour"].isin([8, 9, 10, 15, 16])],
        [1.40, 1.20],
        default=1.00,
    )
    evening_prior = np.where((zone_time["is_evening_peak"].eq(1)) & (zone_time["exposure"].lt(0.25)), 1.30, 1.00)
    uncertainty = np.sqrt(1 / (1 + zone_time.groupby(["zone_id", "hour"])["event_count"].transform("sum"))).clip(0, 1)
    zone_time["blindspot_risk"] = (zone_time["static_potential"] * zone_time["coverage_gap"] * peak_priority * evening_prior * uncertainty).clip(0, 100)
    zone_static = zone_time.groupby("zone_id").agg(
        zone_center_lat=("zone_center_lat", "first"),
        zone_center_lon=("zone_center_lon", "first"),
        police_station=("police_station", lambda s: s.mode().iat[0] if not s.mode().empty else "Unknown"),
        observed_pfdi=("observed_pfdi", "mean"),
        blindspot_risk=("blindspot_risk", "mean"),
        exposure=("exposure", "mean"),
        coverage_gap=("coverage_gap", "mean"),
        static_potential=("static_potential", "mean"),
        location_criticality=("location_criticality", "mean"),
        repeat_persistence=("repeat_persistence", "mean"),
        road_corridor=("road_corridor", lambda s: s.mode().iat[0] if not s.mode().empty else "Unknown Corridor"),
        place_type=("place_type", lambda s: s.mode().iat[0] if not s.mode().empty else "unknown"),
    ).reset_index()
    write_zones_geojson(zone_static, config)
    zone_time.to_parquet(config.processed_dir / "zone_time_features.parquet", index=False)
    zone_static.to_parquet(config.processed_dir / "zone_static_features.parquet", index=False)
    graph_edges.to_parquet(config.interim_dir / "graph_edges.parquet", index=False)
    coverage = zone_time[["zone_id", "window_start", "exposure", "coverage_gap", "blindspot_risk", "static_potential"]]
    coverage.to_parquet(config.processed_dir / "coverage_audit.parquet", index=False)
    return zone_time, zone_static, graph_edges


def build_patrol_transition_graph(zoned: pd.DataFrame, zone_time: pd.DataFrame) -> pd.DataFrame:
    columns = ["source_zone", "target_zone", "window_start", "edge_weight", "transition_count"]
    records: list[dict[str, Any]] = []
    key = "device_id" if "device_id" in zoned else "created_by_id"
    for _, group in zoned.sort_values("created_at_ist").groupby([key, zoned["created_at_ist"].dt.date], dropna=True):
        previous = None
        for row in group[["zone_id", "created_at_ist", "window_start"]].itertuples(index=False):
            if previous is not None and previous.zone_id != row.zone_id:
                delta_hours = (row.created_at_ist - previous.created_at_ist).total_seconds() / 3600
                if 0 < delta_hours <= 3:
                    records.append(
                        {
                            "source_zone": previous.zone_id,
                            "target_zone": row.zone_id,
                            "window_start": row.window_start,
                            "edge_weight": math.exp(-delta_hours / 2),
                            "transition_count": 1,
                        }
                    )
            previous = row
    edges = pd.DataFrame(records, columns=columns)
    if edges.empty:
        return edges
    edges = edges.groupby(["source_zone", "target_zone", "window_start"], as_index=False).agg(edge_weight=("edge_weight", "sum"), transition_count=("transition_count", "sum"))
    graph = nx.from_pandas_edgelist(edges, "source_zone", "target_zone", ["edge_weight"], create_using=nx.DiGraph)
    pagerank = nx.pagerank(graph, weight="edge_weight") if graph.number_of_nodes() else {}
    edges["source_pagerank"] = edges["source_zone"].map(pagerank).fillna(0)
    return edges


def compute_junction_basin_risk(zoned: pd.DataFrame, zone_time: pd.DataFrame) -> pd.Series:
    named = zoned[zoned["named_junction_flag"]].groupby("junction_name").agg(latitude=("latitude", "mean"), longitude=("longitude", "mean"), impact=("row_obstruction", "sum"))
    if named.empty:
        return pd.Series(np.zeros(len(zone_time)), index=zone_time.index)
    named_coords = named[["latitude", "longitude"]].to_numpy()
    values = []
    for row in zone_time[["zone_center_lat", "zone_center_lon", "observed_pfdi", "named_junction_share"]].itertuples(index=False):
        distances = np.sqrt(((named_coords[:, 0] - row.zone_center_lat) * 111_320) ** 2 + ((named_coords[:, 1] - row.zone_center_lon) * 111_320) ** 2)
        nearest = float(distances.min()) if len(distances) else 999_999
        spillover = math.exp(-nearest / 500) if nearest <= 500 else 0.0
        values.append(min(100.0, row.observed_pfdi * (0.5 + row.named_junction_share) + spillover * 50))
    return pd.Series(values, index=zone_time.index)


def write_zones_geojson(zone_static: pd.DataFrame, config: CurbFlowSettings = settings) -> None:
    lat_step = config.zone_size_m / 111_320.0
    median_lat = float(zone_static["zone_center_lat"].median()) if len(zone_static) else 12.97
    lon_step = config.zone_size_m / (111_320.0 * max(math.cos(math.radians(median_lat)), 0.1))
    features = []
    for row in zone_static.itertuples(index=False):
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "zone_id": row.zone_id,
                    "police_station": row.police_station,
                    "observed_pfdi": round(float(row.observed_pfdi), 3),
                    "blindspot_risk": round(float(row.blindspot_risk), 3),
                    "exposure": round(float(row.exposure), 3),
                    "coverage_gap": round(float(row.coverage_gap), 3),
                    "road_corridor": row.road_corridor,
                    "place_type": row.place_type,
                },
                "geometry": {"type": "Polygon", "coordinates": [_zone_polygon(row.zone_center_lat, row.zone_center_lon, lat_step, lon_step)]},
            }
        )
    geojson = {"type": "FeatureCollection", "features": features}
    (config.processed_dir / "zones.geojson").write_text(json.dumps(geojson), encoding="utf-8")


def build_station_metrics(zone_time: pd.DataFrame, config: CurbFlowSettings = settings) -> pd.DataFrame:
    station_groups = zone_time.groupby("police_station", dropna=False)
    rows = []
    for station, group in station_groups:
        total = max(float(group["event_count"].sum()), 1.0)
        top10_share = float(group.groupby("zone_id")["event_count"].sum().sort_values(ascending=False).head(10).sum() / total)
        morning = float(group[group["hour"].between(7, 11)]["event_count"].sum() / total)
        evening = float(group[group["hour"].isin(EVENING_HOURS)]["event_count"].sum() / total)
        morning_bias = max(0.0, morning - evening)
        zone_counts = group.groupby("zone_id")["event_count"].sum()
        p = zone_counts / max(zone_counts.sum(), 1)
        entropy = float(-(p * np.log(p + 1e-9)).sum() / max(np.log(len(p) + 1e-9), 1e-9))
        device_diversity = float(_safe_norm(group["unique_devices"]).mean())
        myopia = 0.40 * top10_share + 0.30 * morning_bias + 0.20 * (1 - entropy) + 0.10 * (1 - device_diversity)
        rows.append(
            {
                "police_station": station or "Unknown",
                "patrol_myopia_index": round(float(myopia), 4),
                "top10_zone_share": round(top10_share, 4),
                "morning_bias": round(morning_bias, 4),
                "zone_coverage_entropy": round(entropy, 4),
                "device_diversity": round(device_diversity, 4),
                "average_exposure": round(float(group["exposure"].mean()), 4),
                "average_blindspot_risk": round(float(group["blindspot_risk"].mean()), 4),
            }
        )
    metrics = pd.DataFrame(rows).sort_values("patrol_myopia_index", ascending=False)
    metrics.to_parquet(config.processed_dir / "station_metrics.parquet", index=False)
    (config.metrics_dir / "station_metrics.json").write_text(metrics.to_json(orient="records", indent=2), encoding="utf-8")
    return metrics


def build_recommendations(predictions: pd.DataFrame, config: CurbFlowSettings = settings) -> pd.DataFrame:
    latest = predictions.sort_values("window_start").groupby("zone_id", as_index=False).tail(1).copy()
    latest["exploit_risk"] = (
        0.45 * latest["final_risk_score"]
        + 0.25 * latest["hotspot_probability"] * 100
        + 0.15 * latest["recurrence"] * 100
        + 0.10 * latest["location_criticality"] * 100
        + 0.05 * latest["repeat_pressure"].fillna(0) * 100
    )
    latest["explore_risk"] = (
        0.45 * latest["blindspot_risk"]
        + 0.25 * latest["static_potential"]
        + 0.20 * latest["coverage_gap"] * 100
        + 0.10 * np.where(latest["is_evening_peak"].eq(1), 100, 60)
    )
    latest["deployment_priority_balanced"] = 0.70 * latest["exploit_risk"] + 0.30 * latest["explore_risk"]
    latest["recommended_action"] = np.select(
        [
            (latest["large_vehicle_share"] > 0.30) & (latest["main_road_share"] > 0.20),
            latest["blindspot_risk"] > latest["observed_pfdi"],
            latest["repeat_persistence"] > 0.35,
            latest["location_criticality"] > 0.50,
        ],
        ["towing_support", "evening_audit_patrol", "repeat_offender_check", "temporary_cones"],
        default="beat_patrol",
    )
    latest["reason"] = latest.apply(_recommendation_reasons, axis=1)
    recommendations = latest.sort_values("deployment_priority_balanced", ascending=False).reset_index(drop=True)
    recommendations["rank"] = recommendations.index + 1
    keep = [
        "rank",
        "zone_id",
        "police_station",
        "window_start",
        "zone_center_lat",
        "zone_center_lon",
        "final_risk_score",
        "blindspot_risk",
        "observed_pfdi",
        "coverage_gap",
        "deployment_priority_balanced",
        "recommended_action",
        "reason",
        "road_corridor",
        "place_type",
    ]
    recommendations = recommendations[keep]
    recommendations.to_parquet(config.processed_dir / "recommendations.parquet", index=False)
    return recommendations


def _recommendation_reasons(row: pd.Series) -> list[str]:
    reasons = []
    if row["final_risk_score"] >= 70:
        reasons.append("High predicted PFDI")
    if row["blindspot_risk"] >= 50:
        reasons.append("High blindspot audit priority")
    if row["coverage_gap"] >= 0.50:
        reasons.append("Low enforcement visibility")
    if row["main_road_share"] >= 0.20:
        reasons.append("Main-road obstruction signal")
    if row["large_vehicle_share"] >= 0.25:
        reasons.append("High large-vehicle obstruction share")
    if row["repeat_persistence"] >= 0.30:
        reasons.append("Repeat-vehicle persistence")
    return reasons or ["Balanced risk and exploration priority"]


def seed_duckdb(config: CurbFlowSettings = settings) -> None:
    conn = duckdb.connect(str(config.duckdb_path))
    tables = {
        "zone_time_features": config.processed_dir / "zone_time_features.parquet",
        "zone_static_features": config.processed_dir / "zone_static_features.parquet",
        "predictions": config.processed_dir / "predictions.parquet",
        "recommendations": config.processed_dir / "recommendations.parquet",
        "coverage_audit": config.processed_dir / "coverage_audit.parquet",
        "station_metrics": config.processed_dir / "station_metrics.parquet",
    }
    for table, path in tables.items():
        if path.exists():
            conn.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM read_parquet(?)", [str(path)])
    conn.close()


def run_pipeline(config: CurbFlowSettings = settings) -> dict[str, Any]:
    df, audit = load_and_clean(config)
    scored = score_rows(df, config)
    zoned = assign_zones(scored, config)
    zone_time, zone_static, _ = build_zone_time_features(zoned, config)
    station_metrics = build_station_metrics(zone_time, config)
    predictions, model_metrics = train_and_score(zone_time, config.model_dir, config.metrics_dir)
    predictions.to_parquet(config.processed_dir / "predictions.parquet", index=False)
    recommendations = build_recommendations(predictions, config)
    seed_duckdb(config)
    (config.reports_dir / "bias_audit_report.md").write_text(
        "# Bias Audit Report\n\n"
        f"- Evening gap ratio: {audit['evening_gap_ratio']:.3f}\n"
        "- CurbFlow treats evening low records as a visibility gap and audit priority, not absence of illegal parking.\n"
        f"- Stations scored for patrol myopia: {len(station_metrics)}\n"
        f"- Recommended zones generated: {len(recommendations)}\n",
        encoding="utf-8",
    )
    return {
        "audit": audit,
        "zone_time_rows": int(len(zone_time)),
        "zones": int(len(zone_static)),
        "recommendations": int(len(recommendations)),
        "metrics": model_metrics,
        "duckdb": str(config.duckdb_path),
    }
