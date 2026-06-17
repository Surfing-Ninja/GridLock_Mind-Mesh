"""Coverage gap scoring from enforcement exposure estimates."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from curbflow.exposure.visibility import compute_enforcement_visibility


COVERAGE_GAP_PATH = Path("data/processed/coverage_gap.parquet")


def _observed_pfdi_column(frame: pd.DataFrame, preferred: str = "observed_pfdi") -> str:
    """Find the observed PFDI column used for bias correction."""

    for column in (preferred, "zone_time_pfdi", "pfdi", "row_obstruction_score"):
        if column in frame.columns:
            return column
    raise ValueError("Coverage gap correction requires an observed PFDI column.")


def _station_time_median_exposure(frame: pd.DataFrame) -> pd.Series:
    """Compute median exposure by station-time when possible, otherwise globally."""

    if {"police_station", "time_window_start"}.issubset(frame.columns):
        medians = frame.groupby(["police_station", "time_window_start"], dropna=False)[
            "exposure"
        ].transform("median")
    elif "police_station" in frame.columns:
        medians = frame.groupby("police_station", dropna=False)["exposure"].transform("median")
    else:
        medians = pd.Series([frame["exposure"].median()] * len(frame), index=frame.index)
    global_median = float(frame["exposure"].median()) if frame["exposure"].notna().any() else 0.0
    return medians.fillna(global_median).astype(float)


def compute_coverage_gap(
    frame: pd.DataFrame,
    *,
    observed_pfdi_column: str = "observed_pfdi",
    eps: float = 1e-6,
) -> pd.DataFrame:
    """Add coverage-gap and conservative bias-corrected PFDI scores."""

    result = frame.copy()
    if "exposure" not in result.columns:
        result = compute_enforcement_visibility(result)
    else:
        result["exposure"] = pd.to_numeric(result["exposure"], errors="coerce").fillna(0.0).clip(0, 1)
        result["coverage_gap"] = (1.0 - result["exposure"]).clip(0, 1)

    pfdi_column = _observed_pfdi_column(result, observed_pfdi_column)
    result["observed_pfdi"] = pd.to_numeric(result[pfdi_column], errors="coerce").fillna(0.0)
    result["median_exposure_station_time"] = _station_time_median_exposure(result)
    correction_factor = (
        result["median_exposure_station_time"] / (result["exposure"] + eps)
    ).pow(0.25)
    result["exposure_bias_correction_factor"] = correction_factor.clip(lower=0.70, upper=1.50)
    result["bias_corrected_pfdi"] = (
        result["observed_pfdi"] * result["exposure_bias_correction_factor"]
    )

    p75_exposure = (
        float(result["exposure"].quantile(0.75)) if result["exposure"].notna().any() else 0.0
    )
    denominator = max(p75_exposure, eps)
    result["zero_window_weight"] = (result["exposure"] / denominator).clip(lower=0.0, upper=1.0)
    return result


def run_coverage_gap_scoring(
    input_frame_or_path: pd.DataFrame | str | Path,
    output_path: str | Path = COVERAGE_GAP_PATH,
) -> pd.DataFrame:
    """Compute and save coverage-gap scores."""

    frame = (
        pd.read_parquet(input_frame_or_path)
        if not isinstance(input_frame_or_path, pd.DataFrame)
        else input_frame_or_path
    )
    scored = compute_coverage_gap(frame)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    scored.to_parquet(destination, index=False)
    return scored
