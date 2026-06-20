"""Enforcement visibility digital twin feature computation."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd
import numpy as np

from curbflow.data.clean import normalize_boolean_value, normalize_text_value


ZONE_TIME_EXPOSURE_PATH = Path("data/processed/enforcement_visibility.parquet")

EXPOSURE_WEIGHTS = {
    "unique_device_count": 0.25,
    "unique_created_by_user_count": 0.20,
    "station_hour_activity": 0.15,
    "patrol_route_coverage": 0.15,
    "scita_success_rate": 0.15,
    "validation_coverage": 0.10,
}


def robust_percentile_scale(series: pd.Series) -> pd.Series:
    """Scale values with p5/p95 clipping, handling constant series defensibly."""

    values = pd.to_numeric(series, errors="coerce")
    valid = values.dropna()
    if valid.empty:
        return pd.Series([0.0] * len(series), index=series.index, dtype="float64")

    p5 = float(valid.quantile(0.05))
    p95 = float(valid.quantile(0.95))
    if abs(p95 - p5) < 1e-12:
        return values.fillna(0.0).map(lambda value: 1.0 if value > 0 else 0.0).astype(float)

    return ((values - p5) / (p95 - p5)).clip(lower=0.0, upper=1.0).fillna(0.0)


def _normalise_key_series(frame: pd.DataFrame, column: str, default: str = "unknown") -> pd.Series:
    """Normalize an optional text grouping column."""

    if column not in frame.columns:
        return pd.Series([default] * len(frame), index=frame.index, dtype="object")
    return frame[column].map(lambda value: normalize_text_value(value, unknown_for_null=True))


def _normalise_scita(series: pd.Series) -> pd.Series:
    """Return nullable SCITA booleans as float success values."""

    return series.map(normalize_boolean_value).map({True: 1.0, False: 0.0})


def _validation_known(series: pd.Series) -> pd.Series:
    """Return 1 for known validation statuses and 0 for unknown or missing statuses."""

    statuses = series.map(lambda value: normalize_text_value(value, unknown_for_null=True))
    return statuses.ne("unknown").astype(float)


def build_zone_time_visibility_inputs(
    frame: pd.DataFrame,
    *,
    zone_column: str = "zone_id",
    datetime_column: str = "created_datetime_ist",
    window: str = "3h",
) -> pd.DataFrame:
    """Aggregate raw records into zone-time inputs used by exposure scoring."""

    required = {zone_column, datetime_column}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns for visibility aggregation: {sorted(missing)}")

    work = frame.copy()
    work[zone_column] = _normalise_key_series(work, zone_column)
    work["police_station"] = _normalise_key_series(work, "police_station")
    created_time = pd.to_datetime(work[datetime_column], errors="coerce")
    work["time_window_start"] = created_time.dt.floor(window)
    work["station_hour"] = (
        work["police_station"].astype(str) + "|" + created_time.dt.hour.fillna(-1).astype(int).astype(str)
    )
    if "device_id" not in work.columns:
        work["device_id"] = pd.NA
    if "created_by_id" not in work.columns:
        work["created_by_id"] = pd.NA
    if "data_sent_to_scita" not in work.columns:
        work["data_sent_to_scita"] = pd.NA
    if "validation_status" not in work.columns:
        work["validation_status"] = "unknown"
    work["_scita_success"] = _normalise_scita(work["data_sent_to_scita"])
    work["_validation_known"] = _validation_known(work["validation_status"])
    if "patrol_route_coverage" not in work.columns:
        work["patrol_route_coverage"] = 0.0
    if "row_obstruction_score" in work.columns:
        work["_observed_pfdi"] = pd.to_numeric(work["row_obstruction_score"], errors="coerce").fillna(0.0)
    elif "observed_pfdi" in work.columns:
        work["_observed_pfdi"] = pd.to_numeric(work["observed_pfdi"], errors="coerce").fillna(0.0)
    else:
        work["_observed_pfdi"] = 0.0

    grouped = work.groupby([zone_column, "time_window_start", "police_station"], dropna=False)
    zone_time = grouped.agg(
        unique_device_count=("device_id", "nunique"),
        unique_created_by_user_count=("created_by_id", "nunique"),
        station_hour_activity=("station_hour", "count"),
        patrol_route_coverage=("patrol_route_coverage", "mean"),
        scita_success_rate=("_scita_success", "mean"),
        validation_coverage=("_validation_known", "mean"),
        observed_pfdi=("_observed_pfdi", "sum"),
        observed_record_count=(zone_column, "size"),
    ).reset_index()
    zone_time["scita_success_rate"] = zone_time["scita_success_rate"].fillna(0.0)
    zone_time["validation_coverage"] = zone_time["validation_coverage"].fillna(0.0)
    return zone_time


def _ensure_columns(frame: pd.DataFrame, columns: Iterable[str], default: float = 0.0) -> pd.DataFrame:
    """Ensure numeric exposure input columns exist."""

    result = frame.copy()
    for column in columns:
        if column not in result.columns:
            result[column] = default
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(default)
    return result


def compute_enforcement_visibility(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute zone-time enforcement exposure from visibility input columns."""

    result = _ensure_columns(frame, EXPOSURE_WEIGHTS.keys())
    transforms = {
        "unique_device_count": np.log1p(result["unique_device_count"]),
        "unique_created_by_user_count": np.log1p(result["unique_created_by_user_count"]),
        "station_hour_activity": result["station_hour_activity"],
        "patrol_route_coverage": result["patrol_route_coverage"],
        "scita_success_rate": result["scita_success_rate"],
        "validation_coverage": result["validation_coverage"],
    }
    for column, values in transforms.items():
        result[f"{column}_norm"] = robust_percentile_scale(values)

    result["exposure"] = sum(
        weight * result[f"{column}_norm"] for column, weight in EXPOSURE_WEIGHTS.items()
    ).clip(lower=0.0, upper=1.0)
    result["coverage_gap"] = (1.0 - result["exposure"]).clip(lower=0.0, upper=1.0)
    return result


def run_visibility_scoring(
    input_frame_or_path: pd.DataFrame | str | Path,
    output_path: str | Path = ZONE_TIME_EXPOSURE_PATH,
) -> pd.DataFrame:
    """Compute and save zone-time enforcement visibility scores."""

    frame = (
        pd.read_parquet(input_frame_or_path)
        if not isinstance(input_frame_or_path, pd.DataFrame)
        else input_frame_or_path
    )
    scored = compute_enforcement_visibility(frame)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    scored.to_parquet(destination, index=False)
    return scored
