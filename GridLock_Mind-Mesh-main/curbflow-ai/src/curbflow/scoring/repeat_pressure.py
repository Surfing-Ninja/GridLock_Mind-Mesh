"""Chronology-safe repeat pressure features using previous vehicle history only."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


CREATED_TIME_COLUMN = "created_datetime_ist"
VEHICLE_COLUMN = "vehicle_number"


def _normalise_vehicle(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().str.upper()


def _safe_time_sort_values(frame: pd.DataFrame, created_column: str) -> pd.Series:
    return pd.to_datetime(frame[created_column], errors="coerce", utc=True)


def compute_repeat_pressure_from_previous_count(previous_count: int | float) -> float:
    """Compute repeat pressure from prior same-vehicle appearances."""

    if pd.isna(previous_count) or previous_count <= 0:
        return 0.0
    return float(min(math.log1p(previous_count) / math.log(11), 1.0))


def add_repeat_pressure_features(
    frame: pd.DataFrame,
    *,
    vehicle_column: str = VEHICLE_COLUMN,
    created_column: str = CREATED_TIME_COLUMN,
) -> pd.DataFrame:
    """Add no-future-leakage repeat pressure features.

    Rows are sorted by `created_datetime_ist` only for feature construction. The returned
    frame preserves the original input order.
    """

    if vehicle_column not in frame.columns:
        raise ValueError(f"Missing vehicle column: {vehicle_column}")
    if created_column not in frame.columns:
        raise ValueError(f"Missing created datetime column: {created_column}")

    result = frame.copy()
    result["_repeat_original_order"] = np.arange(len(result))
    result["_repeat_vehicle_key"] = _normalise_vehicle(result[vehicle_column])
    result["_repeat_sort_time"] = _safe_time_sort_values(result, created_column)
    result["_repeat_missing_vehicle"] = result["_repeat_vehicle_key"].eq("")

    sorted_frame = result.sort_values(
        by=["_repeat_sort_time", "_repeat_original_order"],
        na_position="last",
    ).copy()
    sorted_frame["previous_vehicle_count"] = (
        sorted_frame.groupby("_repeat_vehicle_key", sort=False).cumcount().astype("int64")
    )
    sorted_frame.loc[sorted_frame["_repeat_missing_vehicle"], "previous_vehicle_count"] = 0
    sorted_frame["repeat_pressure"] = sorted_frame["previous_vehicle_count"].map(
        compute_repeat_pressure_from_previous_count
    )

    sorted_frame["previous_same_zone_count"] = pd.NA
    if "zone_id" in sorted_frame.columns:
        zone_key = [sorted_frame["_repeat_vehicle_key"], sorted_frame["zone_id"].fillna("")]
        sorted_frame["previous_same_zone_count"] = (
            sorted_frame.groupby(zone_key, sort=False).cumcount().astype("Int64")
        )
        sorted_frame.loc[sorted_frame["_repeat_missing_vehicle"], "previous_same_zone_count"] = 0

    sorted_frame["previous_station_count"] = pd.NA
    if "police_station" in sorted_frame.columns:
        station_key = [
            sorted_frame["_repeat_vehicle_key"],
            sorted_frame["police_station"].fillna("").astype(str).str.strip().str.lower(),
        ]
        sorted_frame["previous_station_count"] = (
            sorted_frame.groupby(station_key, sort=False).cumcount().astype("Int64")
        )
        sorted_frame.loc[sorted_frame["_repeat_missing_vehicle"], "previous_station_count"] = 0

    sorted_frame["previous_day_count"] = pd.NA
    day_values = sorted_frame["_repeat_sort_time"].dt.date
    day_key = [sorted_frame["_repeat_vehicle_key"], day_values]
    sorted_frame["previous_day_count"] = sorted_frame.groupby(day_key, sort=False).cumcount().astype(
        "Int64"
    )
    sorted_frame.loc[
        sorted_frame["_repeat_missing_vehicle"] | sorted_frame["_repeat_sort_time"].isna(),
        "previous_day_count",
    ] = 0

    output = sorted_frame.sort_values("_repeat_original_order").drop(
        columns=[
            "_repeat_original_order",
            "_repeat_vehicle_key",
            "_repeat_sort_time",
            "_repeat_missing_vehicle",
        ]
    )
    return output
