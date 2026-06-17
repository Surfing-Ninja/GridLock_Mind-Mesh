"""Chronology-safe lag and rolling-window feature builders."""

from __future__ import annotations

import pandas as pd


PFDi_COLUMN = "bias_corrected_pfdi"


def _pfdi_series(frame: pd.DataFrame) -> pd.Series:
    """Return the preferred PFDI series for lag features."""

    for column in (PFDi_COLUMN, "observed_pfdi", "raw_impact"):
        if column in frame.columns:
            return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    return pd.Series([0.0] * len(frame), index=frame.index, dtype="float64")


def _same_slot_average(
    frame: pd.DataFrame,
    *,
    value_column: str,
    periods: int,
) -> pd.Series:
    """Compute same 3-hour slot historical average by zone."""

    slot = frame["hour"].fillna(-1).astype(int)
    work = frame.assign(_slot=slot, _value=pd.to_numeric(frame[value_column], errors="coerce").fillna(0.0))
    return (
        work.groupby(["zone_id", "_slot"], dropna=False)["_value"]
        .transform(lambda values: values.shift(1).rolling(periods, min_periods=1).mean())
    )


def add_lag_rolling_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add chronology-safe lag and rolling PFDI features per zone."""

    result = frame.copy().sort_values(["zone_id", "window_start"]).reset_index(drop=True)
    result["_lag_pfdi"] = _pfdi_series(result)
    grouped = result.groupby("zone_id", dropna=False)["_lag_pfdi"]

    for lag in (1, 2, 8, 56):
        result[f"lag_{lag}_pfdi"] = grouped.shift(lag)

    result["rolling_1d_pfdi"] = grouped.transform(
        lambda values: values.shift(1).rolling(8, min_periods=1).sum()
    )
    result["rolling_7d_pfdi"] = grouped.transform(
        lambda values: values.shift(1).rolling(56, min_periods=1).sum()
    )
    result["rolling_21d_pfdi"] = grouped.transform(
        lambda values: values.shift(1).rolling(168, min_periods=1).sum()
    )
    result["same_slot_7d_avg_pfdi"] = _same_slot_average(result, value_column="_lag_pfdi", periods=7)
    result["same_slot_21d_avg_pfdi"] = _same_slot_average(
        result,
        value_column="_lag_pfdi",
        periods=21,
    )
    result["growth_7d_vs_21d"] = (
        (result["same_slot_7d_avg_pfdi"] - result["same_slot_21d_avg_pfdi"])
        / result["same_slot_21d_avg_pfdi"].abs().clip(lower=1e-6)
    )
    return result.drop(columns=["_lag_pfdi"])
