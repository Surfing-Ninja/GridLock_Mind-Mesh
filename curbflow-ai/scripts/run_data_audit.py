"""Run dataset schema, null-outcome, timestamp, and enforcement-bias audits."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from curbflow.data.audit import AuditOutputPaths, run_data_audit
from curbflow.data.schema import CLEAN_PARQUET_PATH, RAW_CSV_PATH


def main() -> None:
    """Run the data audit stage and write report artifacts."""

    parser = argparse.ArgumentParser(description="Build CurbFlow data and bias audit reports.")
    parser.add_argument("--clean-parquet", default=str(CLEAN_PARQUET_PATH))
    parser.add_argument("--raw-csv", default=str(RAW_CSV_PATH))
    parser.add_argument("--data-quality-report", default="artifacts/reports/data_quality_report.md")
    parser.add_argument("--bias-audit-report", default="artifacts/reports/bias_audit_report.md")
    parser.add_argument("--eda-summary", default="artifacts/reports/eda_summary.json")
    parser.add_argument("--coverage-audit", default="data/processed/coverage_audit.parquet")
    args = parser.parse_args()

    summary = run_data_audit(
        clean_parquet_path=Path(args.clean_parquet),
        raw_csv_path=Path(args.raw_csv),
        output_paths=AuditOutputPaths(
            data_quality_report=Path(args.data_quality_report),
            bias_audit_report=Path(args.bias_audit_report),
            eda_summary=Path(args.eda_summary),
            coverage_audit=Path(args.coverage_audit),
        ),
    )
    print(
        json.dumps(
            {
                "total_rows": summary["total_rows"],
                "total_columns": summary["total_columns"],
                "date_range": summary["actual_date_range"],
                "data_quality_report": args.data_quality_report,
                "bias_audit_report": args.bias_audit_report,
                "eda_summary": args.eda_summary,
                "coverage_audit": args.coverage_audit,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
