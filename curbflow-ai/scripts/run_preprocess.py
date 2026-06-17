"""Preprocess Theme 1 police violation records and convert timestamps to IST."""

from __future__ import annotations

import argparse
from pathlib import Path

from curbflow.data.clean import preprocess_violations
from curbflow.data.schema import CLEAN_PARQUET_PATH, RAW_CSV_PATH


def main() -> None:
    """Run the preprocessing stage."""

    parser = argparse.ArgumentParser(description="Clean Theme 1 police parking violations.")
    parser.add_argument("--raw-csv", default=str(RAW_CSV_PATH), help="Input Theme 1 police CSV path.")
    parser.add_argument("--output", default=str(CLEAN_PARQUET_PATH), help="Output parquet path.")
    args = parser.parse_args()

    clean = preprocess_violations(Path(args.raw_csv), Path(args.output))
    print(f"Wrote {len(clean):,} cleaned rows to {args.output}")


if __name__ == "__main__":
    main()
