"""Generate station-wise exploit/explore enforcement recommendations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from curbflow.features.training_table import MODEL_TRAINING_TABLE_PATH
from curbflow.ml.ranker.ensemble import PREDICTIONS_PATH
from curbflow.planner.optimizer import RECOMMENDATIONS_PATH, write_recommendations


def main() -> None:
    """Generate station-wise resource-constrained recommendations."""

    parser = argparse.ArgumentParser(description="Generate CurbFlow enforcement recommendations.")
    parser.add_argument("--input", default=str(PREDICTIONS_PATH), help="Prediction parquet path.")
    parser.add_argument("--features", default=str(MODEL_TRAINING_TABLE_PATH), help="Optional feature parquet path.")
    parser.add_argument("--output", default=str(RECOMMENDATIONS_PATH), help="Recommendation parquet path.")
    parser.add_argument("--police-station", default=None, help="Optional station filter.")
    parser.add_argument("--window-start", required=True, help="Recommendation window start timestamp.")
    parser.add_argument("--available-officers", type=int, required=True)
    parser.add_argument("--available-tow-units", type=int, required=True)
    parser.add_argument(
        "--mode",
        choices=["conservative", "balanced", "discovery"],
        default="balanced",
    )
    parser.add_argument(
        "--no-feature-merge",
        action="store_true",
        help="Use predictions only and skip engineered-feature merge.",
    )
    args = parser.parse_args()

    try:
        recommendations = write_recommendations(
            args.input,
            output_path=args.output,
            features_path=None if args.no_feature_merge else args.features,
            police_station=args.police_station,
            window_start=args.window_start,
            available_officers=args.available_officers,
            available_tow_units=args.available_tow_units,
            mode=args.mode,
        )
    except Exception as exc:
        raise SystemExit(f"Recommendation generation failed: {exc}") from exc

    print(f"Wrote {len(recommendations):,} recommendations to {args.output}")


if __name__ == "__main__":
    main()
