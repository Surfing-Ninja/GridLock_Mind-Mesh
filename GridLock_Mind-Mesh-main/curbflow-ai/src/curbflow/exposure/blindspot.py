"""Blindspot risk scoring for low-visibility high-potential zones."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from curbflow.exposure.visibility import robust_percentile_scale


ZONE_TIME_FEATURES_PATH = Path("data/processed/zone_time_features.parquet")

STATIC_POTENTIAL_WEIGHTS = {
    "p90_historical_pfdi": 0.30,
    "recurrence": 0.15,
    "location_criticality": 0.15,
    "large_vehicle_share": 0.12,
    "repeat_persistence": 0.10,
    "junction_basin_risk": 0.08,
    "corridor_risk": 0.05,
    "patrol_expansion_opportunity": 0.05,
}

EVENING_START_MINUTE = 15 * 60 + 30
EVENING_END_MINUTE = 20 * 60 + 30
SCHOOL_OFFICE_PEAKS = (
    (7 * 60 + 30, 10 * 60 + 30),
    (12 * 60 + 30, 15 * 60 + 30),
)


def _numeric_column(frame: pd.DataFrame, candidates: tuple[str, ...], default: float = 0.0) -> pd.Series:
    """Return the first available numeric column from a list of candidates."""

    for column in candidates:
        if column in frame.columns:
            return pd.to_numeric(frame[column], errors="coerce").fillna(default)
    return pd.Series([default] * len(frame), index=frame.index, dtype="float64")


def _boolean_column(frame: pd.DataFrame, candidates: tuple[str, ...]) -> pd.Series:
    """Return the first available boolean-like column as floats."""

    for column in candidates:
        if column in frame.columns:
            return frame[column].fillna(False).astype(bool).astype(float)
    return pd.Series([0.0] * len(frame), index=frame.index, dtype="float64")


def _p90_historical_pfdi(frame: pd.DataFrame) -> pd.Series:
    """Infer historical P90 PFDI per zone when a precomputed column is unavailable."""

    direct = _numeric_column(
        frame,
        ("p90_historical_pfdi", "historical_pfdi_p90", "zone_p90_pfdi"),
        default=float("nan"),
    )
    if direct.notna().any():
        return direct.fillna(0.0)

    pfdi = _numeric_column(
        frame,
        ("bias_corrected_pfdi", "observed_pfdi", "zone_time_pfdi", "pfdi", "row_obstruction_score"),
    )
    if "zone_id" not in frame.columns:
        return pfdi
    return pfdi.groupby(frame["zone_id"]).transform(lambda values: values.quantile(0.90)).fillna(0.0)


def _component_inputs(frame: pd.DataFrame) -> dict[str, pd.Series]:
    """Collect raw static-potential component inputs."""

    return {
        "p90_historical_pfdi": _p90_historical_pfdi(frame),
        "recurrence": _numeric_column(
            frame,
            ("recurrence", "recurrence_score", "repeat_vehicle_share", "repeat_vehicle_count"),
        ),
        "location_criticality": _numeric_column(
            frame,
            ("location_criticality", "mean_location_criticality", "location_criticality_score"),
        ),
        "large_vehicle_share": _numeric_column(
            frame,
            ("large_vehicle_share", "corridor_large_vehicle_share", "vehicle_large_share"),
        ),
        "repeat_persistence": _numeric_column(
            frame,
            ("repeat_persistence", "persistence_score", "same_vehicle_same_zone_6h_count"),
        ),
        "junction_basin_risk": _numeric_column(
            frame,
            (
                "junction_basin_risk",
                "junction_basin_pfdi",
                "hidden_no_junction_spillover_impact",
                "hidden_no_junction_spillover_count",
            ),
        ),
        "corridor_risk": _numeric_column(
            frame,
            ("corridor_risk", "corridor_recent_pfdi", "corridor_pfdi"),
        ),
        "patrol_expansion_opportunity": _numeric_column(
            frame,
            ("patrol_expansion_opportunity",),
        )
        .where(
            lambda series: series.ne(0),
            _boolean_column(frame, ("near_patrol_but_uncovered_flag",)),
        ),
    }


def compute_static_potential(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute normalized StaticPotential and retain component columns."""

    result = frame.copy()
    components = _component_inputs(result)
    static_potential = pd.Series([0.0] * len(result), index=result.index, dtype="float64")
    for component_name, raw_values in components.items():
        normalized = robust_percentile_scale(raw_values)
        component_column = f"{component_name}_component"
        result[component_column] = normalized
        static_potential += STATIC_POTENTIAL_WEIGHTS[component_name] * normalized
    result["static_potential"] = static_potential.clip(lower=0.0, upper=1.0)
    return result


def _minute_of_day_from_row(row: pd.Series) -> int | None:
    """Infer minute of day from time-window or hour columns."""

    if "time_window_start" in row.index and not pd.isna(row["time_window_start"]):
        timestamp = pd.to_datetime(row["time_window_start"], errors="coerce")
        if not pd.isna(timestamp):
            return int(timestamp.hour * 60 + timestamp.minute)
    if "hour" in row.index and not pd.isna(row["hour"]):
        minute = int(row["minute"]) if "minute" in row.index and not pd.isna(row["minute"]) else 0
        return int(row["hour"]) * 60 + minute
    return None


def _is_evening_window(row: pd.Series) -> bool:
    minute = _minute_of_day_from_row(row)
    return minute is not None and EVENING_START_MINUTE <= minute < EVENING_END_MINUTE


def _is_school_office_peak(row: pd.Series) -> bool:
    minute = _minute_of_day_from_row(row)
    if minute is None:
        return False
    return any(start <= minute < end for start, end in SCHOOL_OFFICE_PEAKS)


def compute_peak_priority(frame: pd.DataFrame) -> pd.Series:
    """Compute operational peak priority multipliers."""

    return frame.apply(
        lambda row: 1.40 if _is_evening_window(row) else 1.20 if _is_school_office_peak(row) else 1.00,
        axis=1,
    ).astype(float)


def compute_evening_severity_prior(frame: pd.DataFrame) -> pd.Series:
    """Compute conservative evening low-exposure audit prior."""

    exposure = _numeric_column(frame, ("exposure",), default=0.0).clip(lower=0.0, upper=1.0)
    median_exposure = float(exposure.median()) if exposure.notna().any() else 0.0
    p5_exposure = float(exposure.quantile(0.05)) if exposure.notna().any() else 0.0
    denominator = max(median_exposure - p5_exposure, 1e-9)
    low_exposure_strength = ((median_exposure - exposure) / denominator).clip(lower=0.0, upper=1.0)
    evening = frame.apply(_is_evening_window, axis=1)
    prior = pd.Series([1.0] * len(frame), index=frame.index, dtype="float64")
    prior.loc[evening & exposure.lt(median_exposure)] = (
        1.20 + 0.20 * low_exposure_strength.loc[evening & exposure.lt(median_exposure)]
    )
    return prior.clip(lower=1.0, upper=1.40)


def compute_uncertainty(frame: pd.DataFrame) -> pd.Series:
    """Compute uncertainty from observations in the same zone-time bucket."""

    observations = _numeric_column(
        frame,
        ("observations_in_same_zone_time_bucket", "observed_record_count", "total_records", "record_count"),
        default=0.0,
    ).clip(lower=0.0)
    return (1.0 / (1.0 + observations)).pow(0.5).clip(lower=0.0, upper=1.0)


def add_blindspot_risk_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add static potential, blind-spot risk, and explanation fields to zone-time rows."""

    result = compute_static_potential(frame)
    if "coverage_gap" not in result.columns:
        exposure = _numeric_column(result, ("exposure",), default=0.0).clip(lower=0.0, upper=1.0)
        result["coverage_gap"] = (1.0 - exposure).clip(lower=0.0, upper=1.0)
    else:
        result["coverage_gap"] = pd.to_numeric(result["coverage_gap"], errors="coerce").fillna(1.0).clip(0, 1)
    if "exposure" not in result.columns:
        result["exposure"] = (1.0 - result["coverage_gap"]).clip(lower=0.0, upper=1.0)
    else:
        result["exposure"] = pd.to_numeric(result["exposure"], errors="coerce").fillna(0.0).clip(0, 1)

    result["peak_priority"] = compute_peak_priority(result)
    result["evening_severity_prior"] = compute_evening_severity_prior(result)
    result["uncertainty"] = compute_uncertainty(result)
    blindspot_raw = (
        result["static_potential"]
        * result["coverage_gap"]
        * result["peak_priority"]
        * result["evening_severity_prior"]
        * result["uncertainty"]
    )
    result["blindspot_risk"] = (100.0 * blindspot_raw).clip(lower=0.0, upper=100.0)

    static_threshold = result["static_potential"].quantile(0.75)
    exposure_threshold = result["exposure"].quantile(0.25)
    result["high_static_potential"] = result["static_potential"] >= static_threshold
    result["low_enforcement_visibility"] = result["exposure"] <= exposure_threshold
    result["evening_peak_audit"] = result.apply(_is_evening_window, axis=1)
    result["near_patrol_but_uncovered"] = _boolean_column(
        result,
        ("near_patrol_but_uncovered_flag",),
    ).astype(bool)
    hidden_spillover = _numeric_column(
        result,
        ("hidden_no_junction_spillover_count", "hidden_no_junction_spillover_impact", "junction_basin_pfdi"),
    )
    result["hidden_junction_spillover"] = hidden_spillover.gt(0)
    return result


def write_blindspot_zone_time_features(
    frame: pd.DataFrame,
    output_path: str | Path = ZONE_TIME_FEATURES_PATH,
) -> pd.DataFrame:
    """Compute blind-spot features and save them into the zone-time feature artifact."""

    features = add_blindspot_risk_features(frame)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(destination, index=False)
    return features
