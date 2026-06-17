"""Violation-to-zone assignment routines."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from curbflow.scoring.pfdi import ROW_SCORES_PATH
from curbflow.zoning.grid_zones import (
    DEFAULT_GRID_SIZE_METERS,
    assign_grid_bins,
    build_grid_spec,
    build_zone_table,
)
from curbflow.zoning.zone_geojson import ZONES_GEOJSON_PATH, write_zones_geojson


ZONE_ASSIGNMENTS_PATH = Path("data/interim/zone_assignments.parquet")
BIAS_AUDIT_REPORT_PATH = Path("artifacts/reports/bias_audit_report.md")


@dataclass(frozen=True)
class ZoningSummary:
    """Summary metrics emitted by the zoning stage."""

    total_zones: int
    active_zones: int
    records_covered_by_active_zones: int
    total_records: int
    active_zone_min_records: int
    top_1_percent_zone_concentration: float
    top_10_zone_concentration: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_zones": self.total_zones,
            "active_zones": self.active_zones,
            "records_covered_by_active_zones": self.records_covered_by_active_zones,
            "total_records": self.total_records,
            "active_zone_min_records": self.active_zone_min_records,
            "top_1_percent_zone_concentration": self.top_1_percent_zone_concentration,
            "top_10_zone_concentration": self.top_10_zone_concentration,
        }


def summarize_zone_concentration(
    zones: pd.DataFrame,
    total_records: int,
    active_zone_min_records: int = 100,
) -> ZoningSummary:
    """Compute active-zone and concentration metrics."""

    sorted_counts = zones["record_count"].sort_values(ascending=False)
    total_zones = int(len(zones))
    active = zones[zones["record_count"] >= active_zone_min_records]
    top_1_count = max(1, int(total_zones * 0.01 + 0.999999)) if total_zones else 0
    top_1_records = int(sorted_counts.head(top_1_count).sum()) if top_1_count else 0
    top_10_records = int(sorted_counts.head(10).sum()) if total_zones else 0
    denominator = max(total_records, 1)
    return ZoningSummary(
        total_zones=total_zones,
        active_zones=int(len(active)),
        records_covered_by_active_zones=int(active["record_count"].sum()),
        total_records=int(total_records),
        active_zone_min_records=int(active_zone_min_records),
        top_1_percent_zone_concentration=float(top_1_records / denominator),
        top_10_zone_concentration=float(top_10_records / denominator),
    )


def append_zone_concentration_to_bias_report(
    summary: ZoningSummary,
    report_path: str | Path = BIAS_AUDIT_REPORT_PATH,
) -> None:
    """Add or replace the zoning concentration section in the bias audit report."""

    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    marker = "## Zone Concentration"
    section = (
        f"{marker}\n\n"
        f"- Total zones: {summary.total_zones:,}\n"
        f"- Active zones, >={summary.active_zone_min_records:,} records: {summary.active_zones:,}\n"
        f"- Records covered by active zones: {summary.records_covered_by_active_zones:,}\n"
        f"- Top 1% zone concentration: {summary.top_1_percent_zone_concentration:.4f}\n"
        f"- Top 10 zone concentration: {summary.top_10_zone_concentration:.4f}\n"
    )
    existing = path.read_text(encoding="utf-8") if path.exists() else "# CurbFlow AI Bias Audit Report\n"
    if marker in existing:
        existing = existing.split(marker, 1)[0].rstrip() + "\n\n"
    else:
        existing = existing.rstrip() + "\n\n"
    path.write_text(existing + section, encoding="utf-8")


def assign_grid_zones(
    frame: pd.DataFrame,
    *,
    grid_size_meters: float = DEFAULT_GRID_SIZE_METERS,
    active_zone_min_records: int = 100,
) -> tuple[pd.DataFrame, pd.DataFrame, ZoningSummary]:
    """Assign records to 300m grid zones and return assignments, zones, and summary."""

    spec = build_grid_spec(frame["latitude"], grid_size_meters)
    assignments = assign_grid_bins(frame, spec)
    zones = build_zone_table(assignments, spec, active_zone_min_records)
    summary = summarize_zone_concentration(
        zones,
        total_records=len(assignments),
        active_zone_min_records=active_zone_min_records,
    )
    return assignments, zones, summary


def run_zone_build(
    input_path: str | Path = ROW_SCORES_PATH,
    assignments_output_path: str | Path = ZONE_ASSIGNMENTS_PATH,
    zones_geojson_output_path: str | Path = ZONES_GEOJSON_PATH,
    *,
    grid_size_meters: float = DEFAULT_GRID_SIZE_METERS,
    active_zone_min_records: int = 100,
    bias_audit_report_path: str | Path = BIAS_AUDIT_REPORT_PATH,
) -> ZoningSummary:
    """Read scored rows, build 300m grid zones, and write zoning artifacts."""

    source = Path(input_path)
    if not source.exists():
        raise FileNotFoundError(f"Input parquet not found: {source}")
    frame = pd.read_parquet(source)
    assignments, zones, summary = assign_grid_zones(
        frame,
        grid_size_meters=grid_size_meters,
        active_zone_min_records=active_zone_min_records,
    )
    assignments_destination = Path(assignments_output_path)
    assignments_destination.parent.mkdir(parents=True, exist_ok=True)
    assignments.to_parquet(assignments_destination, index=False)
    write_zones_geojson(zones, zones_geojson_output_path)
    append_zone_concentration_to_bias_report(summary, bias_audit_report_path)
    return summary
