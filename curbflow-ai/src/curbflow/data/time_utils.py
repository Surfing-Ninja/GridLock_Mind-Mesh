"""UTC parsing and Asia/Kolkata timestamp conversion helpers."""

from __future__ import annotations

import pandas as pd

from curbflow.data.schema import CREATED_DATETIME_COLUMN, TARGET_TIMEZONE


def parse_created_datetime_utc(values: pd.Series) -> pd.Series:
    """Parse raw created timestamps as UTC, coercing invalid values to NaT."""

    return pd.to_datetime(values, utc=True, errors="coerce")


def convert_utc_to_ist(values: pd.Series) -> pd.Series:
    """Convert a UTC timestamp series to Asia/Kolkata."""

    parsed = parse_created_datetime_utc(values)
    return parsed.dt.tz_convert(TARGET_TIMEZONE)


def add_created_datetime_parts(
    frame: pd.DataFrame,
    source_column: str = CREATED_DATETIME_COLUMN,
    target_column: str = "created_datetime_ist",
) -> pd.DataFrame:
    """Add IST timestamp and calendar fields used by downstream features."""

    result = frame.copy()
    created_ist = convert_utc_to_ist(result[source_column])
    result[target_column] = created_ist
    result["date"] = created_ist.dt.date
    result["hour"] = created_ist.dt.hour.astype("Int64")
    result["minute"] = created_ist.dt.minute.astype("Int64")
    result["day_of_week"] = created_ist.dt.dayofweek.astype("Int64")
    weekend = created_ist.dt.dayofweek.isin([5, 6]).astype("boolean")
    result["is_weekend"] = weekend.mask(created_ist.isna(), pd.NA)
    return result
