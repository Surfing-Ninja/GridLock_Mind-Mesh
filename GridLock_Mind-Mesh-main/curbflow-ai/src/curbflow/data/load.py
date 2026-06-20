"""CSV loading utilities for the Theme 1 police violation dataset only."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from curbflow.data.schema import RAW_CSV_PATH, validate_required_columns


def load_raw_violations(csv_path: str | Path = RAW_CSV_PATH) -> pd.DataFrame:
    """Load the Theme 1 police parking violation CSV."""

    path = Path(csv_path)
    if "astram" in path.name.lower():
        raise ValueError("ASTraM data is not allowed for CurbFlow Theme 1.")
    if not path.exists():
        raise FileNotFoundError(f"Raw CSV not found: {path}")

    frame = pd.read_csv(
        path,
        na_values=["NULL", "null", "NaN", "nan", ""],
        keep_default_na=True,
        low_memory=False,
    )
    validate_required_columns(tuple(frame.columns))
    return frame
