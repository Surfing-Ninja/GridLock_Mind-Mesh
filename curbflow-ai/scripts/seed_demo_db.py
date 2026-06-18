"""Seed the DuckDB demo database from processed CurbFlow artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from curbflow.db.duckdb_init import APP_DB_PATH, initialize_duckdb


def main() -> None:
    """Seed the DuckDB app database from processed artifacts."""

    parser = argparse.ArgumentParser(description="Seed the CurbFlow DuckDB app database.")
    parser.add_argument("--db-path", default=str(APP_DB_PATH), help="Output DuckDB database path.")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete and recreate the database, including feedback.",
    )
    args = parser.parse_args()

    db_path = initialize_duckdb(args.db_path, rebuild=args.rebuild)
    print(f"Seeded DuckDB database at {db_path}")


if __name__ == "__main__":
    main()
