"""Model training table assembly with chronological split metadata."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


MODEL_TRAINING_TABLE_PATH = Path("data/processed/model_training_table.parquet")


def _station_relevance(values: pd.Series) -> pd.Series:
    """Map next PFDI to 0-3 relevance labels using station-wise quantiles."""

    numeric = pd.to_numeric(values, errors="coerce")
    valid = numeric.dropna()
    if valid.empty:
        return pd.Series([pd.NA] * len(values), index=values.index, dtype="Int64")
    q50 = valid.quantile(0.50)
    q75 = valid.quantile(0.75)
    q90 = valid.quantile(0.90)

    def label(value: float) -> int | pd.NA:
        if pd.isna(value):
            return pd.NA
        if value <= q50:
            return 0
        if value <= q75:
            return 1
        if value <= q90:
            return 2
        return 3

    return numeric.map(label).astype("Int64")


def add_supervised_targets(frame: pd.DataFrame) -> pd.DataFrame:
    """Add next-window supervised targets per zone."""

    result = frame.copy().sort_values(["zone_id", "window_start"]).reset_index(drop=True)
    grouped = result.groupby("zone_id", dropna=False)
    result["next_window_start"] = grouped["window_start"].shift(-1)
    result["next_count"] = grouped["record_count"].shift(-1)
    result["next_pfdi"] = grouped["observed_pfdi"].shift(-1)
    result["next_bias_corrected_pfdi"] = grouped["bias_corrected_pfdi"].shift(-1)

    hotspot_threshold = result.groupby(["police_station", "next_window_start"], dropna=False)[
        "next_pfdi"
    ].transform(lambda values: values.quantile(0.90))
    result["next_hotspot"] = (
        result["next_pfdi"].notna() & result["next_pfdi"].ge(hotspot_threshold)
    ).astype(bool)
    result["next_relevance"] = result.groupby("police_station", dropna=False)["next_pfdi"].transform(
        _station_relevance
    )
    return result


def filter_active_supervised_rows(
    frame: pd.DataFrame,
    *,
    active_zone_min_records: int = 100,
) -> pd.DataFrame:
    """Restrict supervised rows to active zones while keeping complete feature artifacts separate."""

    result = frame.copy()
    zone_records = result.groupby("zone_id", dropna=False)["record_count"].transform("sum")
    result["active_zone_record_count"] = zone_records
    result["is_active_training_zone"] = zone_records >= active_zone_min_records
    return result[
        result["is_active_training_zone"]
        & result["next_count"].notna()
        & result["next_pfdi"].notna()
        & result["next_bias_corrected_pfdi"].notna()
    ].reset_index(drop=True)


def build_model_training_table(
    zone_time_features: pd.DataFrame,
    *,
    active_zone_min_records: int = 100,
) -> pd.DataFrame:
    """Build the supervised model training table from zone-time features."""

    targeted = add_supervised_targets(zone_time_features)
    return filter_active_supervised_rows(
        targeted,
        active_zone_min_records=active_zone_min_records,
    )


def write_model_training_table(
    zone_time_features: pd.DataFrame,
    output_path: str | Path = MODEL_TRAINING_TABLE_PATH,
    *,
    active_zone_min_records: int = 100,
) -> pd.DataFrame:
    """Build and save the active-zone supervised training table."""

    table = build_model_training_table(
        zone_time_features,
        active_zone_min_records=active_zone_min_records,
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(destination, index=False)
    return table
