"""Zone-time aggregation over three-hour IST windows."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from curbflow.exposure.blindspot import add_blindspot_risk_features
from curbflow.exposure.coverage_gap import compute_coverage_gap
from curbflow.exposure.visibility import compute_enforcement_visibility
from curbflow.features.lag_features import add_lag_rolling_features
from curbflow.features.novel_features import (
    PLACE_TYPE_FLAGS,
    build_junction_basin_table,
    build_repeat_vehicle_zone_time_table,
    build_road_corridor_zone_time_features,
    compute_patrol_myopia_table,
)
from curbflow.features.static_features import ensure_row_feature_columns, mode_or_unknown
from curbflow.features.temporal_features import add_zone_time_window_columns
from curbflow.graph.build_patrol_graph import build_patrol_graph_edges, build_patrol_graph_features


ZONE_TIME_FEATURES_PATH = Path("data/processed/zone_time_features.parquet")


def _mean_column(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([default] * len(frame), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce").fillna(default)


def _merge_optional(
    left: pd.DataFrame,
    right: pd.DataFrame,
    on: list[str],
) -> pd.DataFrame:
    """Left-merge an optional feature table when it has rows."""

    if right.empty:
        return left
    return left.merge(right, on=on, how="left")


def _base_zone_time_aggregation(row_frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate row-level scored records to zone_id x 3-hour window."""

    work = row_frame.copy()
    work["raw_impact"] = _mean_column(work, "row_obstruction_score")
    work["observed_pfdi_value"] = _mean_column(work, "row_obstruction_score")
    work["severe_violation_flag"] = _mean_column(work, "violation_severity").ge(0.85)
    work["location_criticality"] = _mean_column(work, "location_criticality")
    work["repeat_pressure"] = _mean_column(work, "repeat_pressure")
    work["evidence_quality_score"] = _mean_column(work, "evidence_quality_score")
    work["device_trust"] = _mean_column(work, "device_trust")
    work["user_trust"] = _mean_column(work, "user_trust")
    work["station_evidence_quality"] = _mean_column(work, "station_evidence_quality")
    work["scita_success"] = work.get(
        "data_sent_to_scita",
        pd.Series([pd.NA] * len(work), index=work.index),
    ).map({True: 1.0, False: 0.0}).fillna(0.0)
    validation = work.get("validation_status", pd.Series(["unknown"] * len(work), index=work.index))
    work["validation_known"] = validation.fillna("unknown").astype(str).str.lower().ne("unknown")

    group_cols = ["zone_id", "window_start"]
    aggregated = (
        work.groupby(group_cols, dropna=False)
        .agg(
            window_end=("window_end", "first"),
            date=("date", "first"),
            hour=("hour", "first"),
            day_of_week=("day_of_week", "first"),
            is_weekend=("is_weekend", "first"),
            police_station=("police_station", mode_or_unknown),
            record_count=("zone_id", "size"),
            raw_impact=("raw_impact", "sum"),
            observed_pfdi=("observed_pfdi_value", "sum"),
            severe_violation_count=("severe_violation_flag", "sum"),
            large_vehicle_share=("is_large_vehicle", "mean"),
            two_wheeler_share=("is_two_wheeler", "mean"),
            main_road_parking_share=("main_road_parking_flag", "mean"),
            double_parking_share=("double_parking_flag", "mean"),
            location_criticality_mean=("location_criticality", "mean"),
            repeat_pressure_mean=("repeat_pressure", "mean"),
            unique_device_count=("device_id", "nunique"),
            unique_created_by_user_count=("created_by_id", "nunique"),
            station_hour_activity=("zone_id", "size"),
            scita_success_rate=("scita_success", "mean"),
            validation_coverage=("validation_known", "mean"),
            evidence_quality_score_mean=("evidence_quality_score", "mean"),
            device_trust_mean=("device_trust", "mean"),
            user_trust_mean=("user_trust", "mean"),
            station_evidence_quality=("station_evidence_quality", "mean"),
            type_correction_rate=("type_correction_flag", "mean"),
        )
        .reset_index()
    )
    aggregated["time_window_start"] = aggregated["window_start"]
    return aggregated


def _join_novel_zone_time_features(zone_time: pd.DataFrame, row_frame: pd.DataFrame) -> pd.DataFrame:
    """Merge optional novel feature aggregates into zone-time rows."""

    result = zone_time.copy()
    key = ["zone_id", "time_window_start"]

    junction = build_junction_basin_table(row_frame)
    if not junction.empty:
        junction = (
            junction.groupby(key, dropna=False)
            .agg(
                junction_basin_pfdi=("junction_basin_pfdi", "sum"),
                hidden_no_junction_spillover_count=("hidden_no_junction_spillover_count", "sum"),
                hidden_no_junction_spillover_impact=("hidden_no_junction_spillover_impact", "sum"),
            )
            .reset_index()
        )
        result = _merge_optional(result, junction, key)

    repeat = build_repeat_vehicle_zone_time_table(row_frame)
    result = _merge_optional(
        result,
        repeat[
            [
                "zone_id",
                "time_window_start",
                "persistence_score",
                "repeat_vehicle_share",
                "repeat_vehicle_count",
                "same_vehicle_same_zone_6h_count",
                "same_vehicle_different_zone_6h_count",
            ]
        ]
        if not repeat.empty
        else repeat,
        key,
    )

    corridor = build_road_corridor_zone_time_features(row_frame)
    if not corridor.empty:
        corridor_agg = (
            corridor.groupby(key, dropna=False)
            .agg(
                corridor_recent_pfdi=("corridor_recent_pfdi", "max"),
                corridor_pfdi=("corridor_pfdi", "max"),
                **{flag: (flag, "max") for flag in PLACE_TYPE_FLAGS},
            )
            .reset_index()
        )
        dominant_place = (
            corridor.sort_values("corridor_recent_pfdi", ascending=False)
            .drop_duplicates(key)[key + ["place_type_primary", "road_corridor_id"]]
        )
        corridor_agg = corridor_agg.merge(dominant_place, on=key, how="left")
        result = _merge_optional(result, corridor_agg, key)

    patrol_edges = build_patrol_graph_edges(row_frame)
    patrol_features = build_patrol_graph_features(row_frame, patrol_edges)
    if not patrol_features.empty:
        result = result.merge(
            patrol_features[
                [
                    "zone_id",
                    "patrol_in_degree",
                    "patrol_out_degree",
                    "patrol_weighted_degree",
                    "patrol_pagerank",
                    "patrol_route_coverage",
                    "near_patrol_but_uncovered_flag",
                ]
            ],
            on="zone_id",
            how="left",
        )

    myopia = compute_patrol_myopia_table(row_frame)
    if not myopia.empty:
        result = result.merge(
            myopia[["police_station", "patrol_myopia_index"]].rename(
                columns={"patrol_myopia_index": "patrol_myopia_station"}
            ),
            on="police_station",
            how="left",
        )
    return result


def build_zone_time_features(row_frame: pd.DataFrame, *, window: str = "3h") -> pd.DataFrame:
    """Build the complete map/blindspot zone-time feature table."""

    rows = ensure_row_feature_columns(row_frame)
    rows = add_zone_time_window_columns(rows, window=window)
    rows = rows[rows["zone_id"].notna() & rows["window_start"].notna()].copy()
    zone_time = _base_zone_time_aggregation(rows)
    zone_time = _join_novel_zone_time_features(zone_time, rows)

    fill_zero_columns = [
        "junction_basin_pfdi",
        "hidden_no_junction_spillover_count",
        "hidden_no_junction_spillover_impact",
        "persistence_score",
        "repeat_vehicle_share",
        "repeat_vehicle_count",
        "same_vehicle_same_zone_6h_count",
        "same_vehicle_different_zone_6h_count",
        "corridor_recent_pfdi",
        "corridor_pfdi",
        "patrol_in_degree",
        "patrol_out_degree",
        "patrol_weighted_degree",
        "patrol_pagerank",
        "patrol_route_coverage",
        "patrol_myopia_station",
    ]
    for column in fill_zero_columns:
        if column not in zone_time.columns:
            zone_time[column] = 0.0
        zone_time[column] = pd.to_numeric(zone_time[column], errors="coerce").fillna(0.0)
    for flag in PLACE_TYPE_FLAGS:
        if flag not in zone_time.columns:
            zone_time[flag] = False
        zone_time[flag] = zone_time[flag].fillna(False).astype(bool)
    if "near_patrol_but_uncovered_flag" not in zone_time.columns:
        zone_time["near_patrol_but_uncovered_flag"] = False
    zone_time["near_patrol_but_uncovered_flag"] = zone_time[
        "near_patrol_but_uncovered_flag"
    ].fillna(False).astype(bool)
    if "place_type_primary" not in zone_time.columns:
        zone_time["place_type_primary"] = "unknown"
    if "road_corridor_id" not in zone_time.columns:
        zone_time["road_corridor_id"] = "unknown"

    zone_time = compute_enforcement_visibility(zone_time)
    zone_time = compute_coverage_gap(zone_time)
    zone_time = add_blindspot_risk_features(zone_time)
    zone_time = add_lag_rolling_features(zone_time)
    return zone_time.sort_values(["zone_id", "window_start"]).reset_index(drop=True)


def write_zone_time_features(
    row_frame: pd.DataFrame,
    output_path: str | Path = ZONE_TIME_FEATURES_PATH,
) -> pd.DataFrame:
    """Build and save the full zone-time feature table."""

    features = build_zone_time_features(row_frame)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(destination, index=False)
    return features
