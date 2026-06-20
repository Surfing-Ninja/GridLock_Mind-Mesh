"""Precompute zone-level summary tables for fast API responses.

Run after the standard pipeline has produced ``data/interim/zone_assignments.parquet``:

    python scripts/precompute_zone_summaries.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from curbflow.db.duckdb_init import APP_DB_PATH

ZONE_ASSIGNMENTS_PATH = PROJECT_ROOT / "data" / "interim" / "zone_assignments.parquet"
DEFAULT_OUTPUT_TABLES = [
    "zone_slot_summary",
    "zone_coverage_gaps",
    "hourly_volume",
    "station_shift_cutoff",
]

LARGE_VEHICLE_TERMS = (
    "hgv",
    "private bus",
    "bmtc",
    "ksrtc",
    "bus",
    "lgv",
    "tempo",
    "lorry",
    "goods vehicle",
    "maxi-cab",
    "tanker",
)


def _mode_or_empty(series: pd.Series) -> str:
    """Return the most frequent non-empty string value."""

    cleaned = series.dropna().astype(str)
    cleaned = cleaned[cleaned.str.strip().ne("")]
    if cleaned.empty:
        return ""
    return str(cleaned.mode().iloc[0])


def _mode_or_unknown(series: pd.Series) -> str:
    """Return the most frequent non-empty value or UNKNOWN."""

    value = _mode_or_empty(series)
    return value if value else "UNKNOWN"


def _contains_double_parking(value: object) -> bool:
    """Return true when a parsed violation label contains double parking."""

    return "double_parking" in str(value).lower() or "double parking" in str(value).lower()


def _load_zone_rows(input_path: Path) -> pd.DataFrame:
    """Load row-level zone assignments and normalize fields needed by summaries."""

    if not input_path.exists():
        raise FileNotFoundError(
            f"Zone assignment artifact not found: {input_path}. "
            "Run `make preprocess`, `make pfdi`, and `make zones` or `make full` first."
        )
    rows = pd.read_parquet(input_path)
    required = {
        "zone_id",
        "police_station",
        "created_datetime_ist",
        "hour",
        "date",
        "vehicle_number",
        "vehicle_type",
        "junction_name",
        "zone_centroid_lat",
        "zone_centroid_lon",
    }
    missing = sorted(required - set(rows.columns))
    if missing:
        raise ValueError(f"Zone assignment artifact is missing required columns: {missing}")

    rows = rows.copy()
    rows["created_datetime_ist"] = pd.to_datetime(rows["created_datetime_ist"], errors="coerce")
    rows["hour"] = pd.to_numeric(rows["hour"], errors="coerce").fillna(0).astype(int)
    rows["hour_slot"] = (rows["hour"] // 3).clip(0, 7).astype(int)
    rows["dow"] = rows["created_datetime_ist"].dt.day_name()
    rows["date"] = pd.to_datetime(rows["date"], errors="coerce").dt.date
    rows["police_station"] = rows["police_station"].fillna("unknown").astype(str).str.strip().str.lower()
    rows["vehicle_type_norm"] = rows["vehicle_type"].fillna("").astype(str).str.lower()
    rows["is_large_veh"] = rows["vehicle_type_norm"].apply(
        lambda value: any(term in value for term in LARGE_VEHICLE_TERMS)
    )
    if "row_obstruction_score" not in rows.columns:
        rows["row_obstruction_score"] = 0.0
    rows["row_obstruction_score"] = pd.to_numeric(rows["row_obstruction_score"], errors="coerce").fillna(0.0)
    if "parsed_violation_labels" not in rows.columns:
        rows["parsed_violation_labels"] = ""
    rows["double_parking_flag"] = rows["parsed_violation_labels"].apply(_contains_double_parking)
    repeat_vehicle_counts = rows["vehicle_number"].value_counts(dropna=True)
    repeat_vehicles = set(repeat_vehicle_counts[repeat_vehicle_counts >= 3].index)
    rows["is_repeat_vehicle"] = rows["vehicle_number"].isin(repeat_vehicles)
    return rows


def build_summary_tables(rows: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Build all requested summary tables from row-level zone assignments."""

    zone_group = ["zone_id", "police_station", "dow", "hour_slot"]
    summary = (
        rows.groupby(zone_group, dropna=False)
        .agg(
            challan_count=("zone_id", "size"),
            total_obstruction=("row_obstruction_score", "sum"),
            large_veh_count=("is_large_veh", "sum"),
            repeat_veh_count=("is_repeat_vehicle", "sum"),
            double_parking_count=("double_parking_flag", "sum"),
            lat=("zone_centroid_lat", "first"),
            lon=("zone_centroid_lon", "first"),
            junction_name=("junction_name", _mode_or_empty),
            dominant_vehicle_type=("vehicle_type", _mode_or_unknown),
        )
        .reset_index()
    )
    p99 = float(summary["total_obstruction"].quantile(0.99)) if not summary.empty else 0.0
    denominator = np.log1p(p99) if p99 > 0 else 1.0
    summary["pfdi_score"] = (
        100.0 * np.log1p(summary["total_obstruction"].clip(lower=0)) / denominator
    ).clip(0, 100).round(1)
    summary["large_veh_pct"] = (
        summary["large_veh_count"] / summary["challan_count"].clip(lower=1) * 100.0
    ).round(1)

    coverage = (
        rows.groupby(["zone_id", "police_station"], dropna=False)
        .agg(
            total_violations=("zone_id", "size"),
            unique_days=("date", "nunique"),
            last_seen=("date", "max"),
            peak_hour=("hour", lambda series: int(series.mode().iloc[0]) if not series.mode().empty else 0),
            lat=("zone_centroid_lat", "first"),
            lon=("zone_centroid_lon", "first"),
            junction_name=("junction_name", _mode_or_empty),
        )
        .reset_index()
    )
    coverage["coverage_pct"] = (coverage["unique_days"] / 150.0 * 100.0).round(1)
    coverage["gap_severity"] = np.where(
        (coverage["total_violations"] > 100) & (coverage["coverage_pct"] < 20),
        "HIGH",
        "MEDIUM",
    )

    hourly = rows.groupby("hour").size().reset_index(name="record_count")
    hourly["challan_count"] = hourly["record_count"]
    total = float(hourly["record_count"].sum())
    hourly["share"] = np.where(total > 0, hourly["record_count"] / total, 0.0)

    officer_hours = (
        rows.dropna(subset=["created_by_id"])
        .groupby(["police_station", "created_by_id", "date"], dropna=False)["hour"]
        .max()
        .reset_index(name="last_active_hour")
    )
    station_cutoff = (
        officer_hours.groupby("police_station", dropna=False)
        .agg(
            median_last_hour=("last_active_hour", "median"),
            evening_active_day_share=("last_active_hour", lambda series: float((series >= 15).mean())),
            total_officers=("created_by_id", "nunique"),
            officer_days=("created_by_id", "size"),
        )
        .reset_index()
    )

    return {
        "zone_slot_summary": summary,
        "zone_coverage_gaps": coverage,
        "hourly_volume": hourly,
        "station_shift_cutoff": station_cutoff,
    }


def write_tables(tables: dict[str, pd.DataFrame], db_path: Path) -> None:
    """Write summary tables to DuckDB, replacing only these derived tables."""

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        for table_name in DEFAULT_OUTPUT_TABLES:
            frame = tables[table_name]
            con.register("summary_frame", frame)
            con.execute(f"DROP TABLE IF EXISTS {table_name}")
            con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM summary_frame")
            con.unregister("summary_frame")


def main() -> None:
    """CLI entrypoint."""

    parser = argparse.ArgumentParser(description="Precompute CurbFlow zone summary tables.")
    parser.add_argument("--input", default=str(ZONE_ASSIGNMENTS_PATH), help="Input zone assignments parquet.")
    parser.add_argument("--db-path", default=str(APP_DB_PATH), help="Output DuckDB database path.")
    args = parser.parse_args()

    rows = _load_zone_rows(Path(args.input))
    tables = build_summary_tables(rows)
    write_tables(tables, Path(args.db_path))
    print(
        "Done. Tables written: "
        + ", ".join(f"{name} ({len(frame):,} rows)" for name, frame in tables.items())
    )


if __name__ == "__main__":
    main()
