"""Build spatial zones and assign violation records to zones."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from curbflow.scoring.pfdi import ROW_SCORES_PATH
from curbflow.zoning.assign_zones import ZONE_ASSIGNMENTS_PATH, run_zone_build
from curbflow.zoning.grid_zones import DEFAULT_GRID_SIZE_METERS
from curbflow.zoning.zone_geojson import ZONES_GEOJSON_PATH


def main() -> None:
    """Run 300m grid zone assignment and GeoJSON export."""

    parser = argparse.ArgumentParser(description="Build CurbFlow 300m grid zones.")
    parser.add_argument("--input", default=str(ROW_SCORES_PATH))
    parser.add_argument("--assignments-output", default=str(ZONE_ASSIGNMENTS_PATH))
    parser.add_argument("--zones-geojson", default=str(ZONES_GEOJSON_PATH))
    parser.add_argument("--grid-size-meters", type=float, default=DEFAULT_GRID_SIZE_METERS)
    parser.add_argument("--active-zone-min-records", type=int, default=100)
    parser.add_argument("--bias-audit-report", default="artifacts/reports/bias_audit_report.md")
    args = parser.parse_args()

    summary = run_zone_build(
        input_path=Path(args.input),
        assignments_output_path=Path(args.assignments_output),
        zones_geojson_output_path=Path(args.zones_geojson),
        grid_size_meters=args.grid_size_meters,
        active_zone_min_records=args.active_zone_min_records,
        bias_audit_report_path=Path(args.bias_audit_report),
    )
    print(json.dumps(summary.as_dict(), indent=2))


if __name__ == "__main__":
    main()
