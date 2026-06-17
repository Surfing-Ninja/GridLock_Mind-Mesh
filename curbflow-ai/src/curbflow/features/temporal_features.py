"""Temporal features for hour, day, peak windows, and seasonality."""

from __future__ import annotations

import pandas as pd


DEFAULT_WINDOW = "3h"
TARGET_TIMEZONE = "Asia/Kolkata"


def parse_ist_datetime(series: pd.Series) -> pd.Series:
    """Parse timestamps and return Asia/Kolkata-aware datetimes."""

    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    return parsed.dt.tz_convert(TARGET_TIMEZONE)


def add_zone_time_window_columns(
    frame: pd.DataFrame,
    *,
    datetime_column: str = "created_datetime_ist",
    window: str = DEFAULT_WINDOW,
) -> pd.DataFrame:
    """Add 3-hour zone-time window columns from created_datetime_ist."""

    if datetime_column not in frame.columns:
        raise ValueError(f"Missing datetime column for zone-time aggregation: {datetime_column}")
    result = frame.copy()
    created_time = parse_ist_datetime(result[datetime_column])
    result["window_start"] = created_time.dt.floor(window)
    result["window_end"] = result["window_start"] + pd.to_timedelta(window)
    result["time_window_start"] = result["window_start"]
    result["date"] = result["window_start"].dt.date
    result["hour"] = result["window_start"].dt.hour
    result["day_of_week"] = result["window_start"].dt.dayofweek
    result["is_weekend"] = result["day_of_week"].isin([5, 6])
    result["_slot_in_day"] = (result["hour"] // 3).astype("Int64")
    return result
