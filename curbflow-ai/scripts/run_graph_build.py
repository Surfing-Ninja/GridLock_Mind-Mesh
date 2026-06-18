"""Build geo, station, pattern, vehicle, patrol, and heterogeneous graphs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from curbflow.features.aggregate_zone_time import ZONE_TIME_FEATURES_PATH
from curbflow.graph.build_hetero_graph import (
    ADJACENCY_OUTPUT_DIR,
    GRAPH_EDGES_PATH,
    GRAPH_FEATURES_PATH,
    run_graph_build,
)
from curbflow.zoning.assign_zones import ZONE_ASSIGNMENTS_PATH


def main() -> None:
    """Build all graph artifacts for active zones."""

    parser = argparse.ArgumentParser(description="Build CurbFlow graph artifacts.")
    parser.add_argument("--zone-time-input", default=str(ZONE_TIME_FEATURES_PATH))
    parser.add_argument("--row-input", default=str(ZONE_ASSIGNMENTS_PATH))
    parser.add_argument("--graph-edges-output", default=str(GRAPH_EDGES_PATH))
    parser.add_argument("--graph-features-output", default=str(GRAPH_FEATURES_PATH))
    parser.add_argument("--adjacency-output-dir", default=str(ADJACENCY_OUTPUT_DIR))
    parser.add_argument("--active-zone-min-records", type=int, default=100)
    args = parser.parse_args()

    zone_time_path = Path(args.zone_time_input)
    if not zone_time_path.exists():
        raise FileNotFoundError(f"Zone-time feature table not found: {zone_time_path}")
    row_path = Path(args.row_input)
    row_input = row_path if row_path.exists() else None

    edges, features, matrices = run_graph_build(
        zone_time_path,
        row_path=row_input,
        graph_edges_path=args.graph_edges_output,
        graph_features_path=args.graph_features_output,
        adjacency_output_dir=args.adjacency_output_dir,
        active_zone_min_records=args.active_zone_min_records,
    )
    print(f"Wrote {len(edges):,} graph edges to {args.graph_edges_output}")
    print(f"Wrote {len(features):,} graph feature rows to {args.graph_features_output}")
    print(f"Wrote {len(matrices):,} adjacency matrices to {args.adjacency_output_dir}")


if __name__ == "__main__":
    main()
