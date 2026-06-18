"""Compute row-level Parking-Induced Flow Disruption Index inputs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from curbflow.data.schema import CLEAN_PARQUET_PATH
from curbflow.scoring.pfdi import ROW_SCORES_PATH, run_pfdi_scoring


def main() -> None:
    """Run row-level PFDI scoring."""

    parser = argparse.ArgumentParser(description="Compute row-level CurbFlow PFDI scores.")
    parser.add_argument("--clean-parquet", default=str(CLEAN_PARQUET_PATH))
    parser.add_argument("--output", default=str(ROW_SCORES_PATH))
    parser.add_argument(
        "--with-evidence-quality",
        action="store_true",
        help="Compute evidence-quality trust features before final PFDI scoring.",
    )
    args = parser.parse_args()

    scored = run_pfdi_scoring(
        clean_parquet_path=Path(args.clean_parquet),
        output_path=Path(args.output),
        compute_evidence_quality=args.with_evidence_quality,
    )
    print(f"Wrote {len(scored):,} scored rows to {args.output}")


if __name__ == "__main__":
    main()
