from __future__ import annotations

import argparse
import json

from .analytics import (
    assign_zones,
    build_recommendations,
    build_station_metrics,
    build_zone_time_features,
    load_and_clean,
    run_pipeline,
    score_rows,
    seed_duckdb,
)
from .modeling import train_and_score
from .settings import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="CurbFlow AI data and model pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("audit", help="Load CSV, convert timestamps to IST, and write data-quality artifacts")
    sub.add_parser("features", help="Build PFDI, zones, novel features, coverage gaps, and graph edges")
    sub.add_parser("train", help="Train BE-STHGT/LightGBM ensemble or recorded fallbacks")
    sub.add_parser("planner", help="Build station-wise deployment recommendation artifacts")
    sub.add_parser("seed-db", help="Seed the DuckDB application database from processed artifacts")
    sub.add_parser("run-all", help="Run the complete independent-stage pipeline")
    args = parser.parse_args()

    if args.command == "audit":
        _, audit = load_and_clean(settings)
        print(json.dumps(audit, indent=2))
    elif args.command == "features":
        df, _ = load_and_clean(settings)
        scored = score_rows(df, settings)
        zoned = assign_zones(scored, settings)
        zone_time, zone_static, graph_edges = build_zone_time_features(zoned, settings)
        station_metrics = build_station_metrics(zone_time, settings)
        print(json.dumps({"zone_time_rows": len(zone_time), "zones": len(zone_static), "graph_edges": len(graph_edges), "stations": len(station_metrics)}, indent=2))
    elif args.command == "train":
        zone_time = settings.processed_dir / "zone_time_features.parquet"
        if not zone_time.exists():
            raise SystemExit("Missing zone_time_features.parquet. Run `python -m curbflow.cli features` first.")
        import pandas as pd

        predictions, metrics = train_and_score(pd.read_parquet(zone_time), settings.model_dir, settings.metrics_dir)
        predictions.to_parquet(settings.processed_dir / "predictions.parquet", index=False)
        print(json.dumps(metrics, indent=2))
    elif args.command == "planner":
        predictions_path = settings.processed_dir / "predictions.parquet"
        if not predictions_path.exists():
            raise SystemExit("Missing predictions.parquet. Run `python -m curbflow.cli train` first.")
        import pandas as pd

        recs = build_recommendations(pd.read_parquet(predictions_path), settings)
        print(json.dumps({"recommendations": len(recs)}, indent=2))
    elif args.command == "seed-db":
        seed_duckdb(settings)
        print(json.dumps({"duckdb": str(settings.duckdb_path)}, indent=2))
    elif args.command == "run-all":
        print(json.dumps(run_pipeline(settings), indent=2))


if __name__ == "__main__":
    main()
