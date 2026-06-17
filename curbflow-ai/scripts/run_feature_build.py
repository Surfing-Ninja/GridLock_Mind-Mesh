"""Build static, temporal, exposure, blindspot, and novel CurbFlow features."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from curbflow.features.aggregate_zone_time import (
    ZONE_TIME_FEATURES_PATH,
    write_zone_time_features,
)
from curbflow.features.training_table import MODEL_TRAINING_TABLE_PATH, write_model_training_table
from curbflow.scoring.pfdi import ROW_SCORES_PATH


def main() -> None:
    """Build zone-time features and active-zone supervised training table."""

    parser = argparse.ArgumentParser(description="Build CurbFlow zone-time feature artifacts.")
    parser.add_argument("--input", default=str(ROW_SCORES_PATH), help="Row-level scored parquet.")
    parser.add_argument(
        "--zone-time-output",
        default=str(ZONE_TIME_FEATURES_PATH),
        help="Full zone-time feature artifact path.",
    )
    parser.add_argument(
        "--training-output",
        default=str(MODEL_TRAINING_TABLE_PATH),
        help="Active-zone supervised training table path.",
    )
    parser.add_argument("--active-zone-min-records", type=int, default=100)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Row-level scored parquet not found: {input_path}")

    rows = pd.read_parquet(input_path)
    zone_time = write_zone_time_features(rows, args.zone_time_output)
    training = write_model_training_table(
        zone_time,
        args.training_output,
        active_zone_min_records=args.active_zone_min_records,
    )
    print(f"Wrote {len(zone_time):,} zone-time rows to {args.zone_time_output}")
    print(f"Wrote {len(training):,} supervised rows to {args.training_output}")


if __name__ == "__main__":
    main()
