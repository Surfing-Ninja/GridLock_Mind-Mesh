"""Novel CurbFlow features including evidence-quality trust scores."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from curbflow.data.clean import normalize_boolean_value, normalize_text_value
from curbflow.scoring.pfdi import validation_confidence


EVIDENCE_TRUST_ALPHA = 100.0
VALIDATED_STATUSES = {"approved", "created1", "processing", "rejected", "duplicate"}
JUNCTION_BASINS_PATH = Path("data/processed/junction_basins.parquet")
PATROL_MYOPIA_PATH = Path("data/processed/patrol_myopia.parquet")
JUNCTION_BASIN_THRESHOLD_M = 500.0
EARTH_RADIUS_M = 6_371_000.0
NO_JUNCTION_VALUES = {"no junction", "nojunction", "none", "unknown", "null"}
EPSILON = 1e-9


@dataclass(frozen=True)
class EvidencePriors:
    """Global priors used when evidence grouping fields are missing or sparse."""

    approval_rate: float
    reject_rate: float
    type_correction_rate: float
    scita_success_rate: float
    trust_score: float


def _normalise_optional_text(value: Any) -> Any:
    """Normalize text while preserving missing values for grouping fallback."""

    normalized = normalize_text_value(value)
    if pd.isna(normalized):
        return pd.NA
    return normalized


def _is_valid_named_junction(value: Any) -> bool:
    """Return True for usable named junction values."""

    normalized = _normalise_optional_text(value)
    if pd.isna(normalized):
        return False
    return str(normalized) not in NO_JUNCTION_VALUES


def _normalise_status_series(frame: pd.DataFrame) -> pd.Series:
    """Return normalized validation statuses with unknown as the null fallback."""

    if "validation_status" not in frame.columns:
        return pd.Series(["unknown"] * len(frame), index=frame.index, dtype="object")
    return frame["validation_status"].map(
        lambda value: normalize_text_value(value, unknown_for_null=True)
    )


def _normalise_group_key(frame: pd.DataFrame, column: str) -> pd.Series:
    """Normalize an optional group key and keep missing keys unmapped."""

    if column not in frame.columns:
        return pd.Series([pd.NA] * len(frame), index=frame.index, dtype="object")
    return frame[column].map(_normalise_optional_text)


def _normalise_scita_success(frame: pd.DataFrame) -> pd.Series:
    """Normalize SCITA transmission values to nullable booleans."""

    if "data_sent_to_scita" not in frame.columns:
        return pd.Series([pd.NA] * len(frame), index=frame.index, dtype="object")
    return frame["data_sent_to_scita"].map(normalize_boolean_value)


def add_type_correction_flag(frame: pd.DataFrame) -> pd.DataFrame:
    """Flag rows where updated vehicle type exists and differs from the original type."""

    result = frame.copy()
    vehicle_type = (
        result["vehicle_type"].map(_normalise_optional_text)
        if "vehicle_type" in result.columns
        else pd.Series([pd.NA] * len(result), index=result.index, dtype="object")
    )
    updated_vehicle_type = (
        result["updated_vehicle_type"].map(_normalise_optional_text)
        if "updated_vehicle_type" in result.columns
        else pd.Series([pd.NA] * len(result), index=result.index, dtype="object")
    )
    updated_exists = updated_vehicle_type.notna()
    result["type_correction_flag"] = (
        updated_exists
        & (updated_vehicle_type.fillna("__missing__") != vehicle_type.fillna("__missing__"))
    )
    return result


def _safe_mean(values: pd.Series, default: float = 0.0) -> float:
    """Compute a float mean and return a default for empty or all-null series."""

    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return default
    return float(numeric.mean())


def _trust_formula(
    *,
    smoothed_approval_rate: float,
    smoothed_reject_rate: float,
    type_correction_rate: float,
    scita_success_rate: float,
) -> float:
    """Compute the weighted trust score for a device, user, or station."""

    score = (
        0.45 * smoothed_approval_rate
        + 0.25 * (1.0 - smoothed_reject_rate)
        + 0.15 * (1.0 - type_correction_rate)
        + 0.15 * scita_success_rate
    )
    return float(max(0.0, min(1.0, score)))


def _global_priors(frame: pd.DataFrame, status: pd.Series, scita_success: pd.Series) -> EvidencePriors:
    """Build global evidence priors for smoothing and missing identifiers."""

    validated = status.isin(VALIDATED_STATUSES)
    validated_count = int(validated.sum())
    if validated_count:
        approval_rate = float((status == "approved").sum() / validated_count)
        reject_rate = float((status == "rejected").sum() / validated_count)
    else:
        approval_rate = 0.0
        reject_rate = 0.0

    type_correction_rate = _safe_mean(frame["type_correction_flag"].astype(float), default=0.0)
    scita_rate = _safe_mean(scita_success.map({True: 1.0, False: 0.0}), default=0.0)
    trust_score = _trust_formula(
        smoothed_approval_rate=approval_rate,
        smoothed_reject_rate=reject_rate,
        type_correction_rate=type_correction_rate,
        scita_success_rate=scita_rate,
    )
    return EvidencePriors(
        approval_rate=approval_rate,
        reject_rate=reject_rate,
        type_correction_rate=type_correction_rate,
        scita_success_rate=scita_rate,
        trust_score=trust_score,
    )


def _group_evidence_stats(
    *,
    key: pd.Series,
    status: pd.Series,
    type_correction_flag: pd.Series,
    scita_success: pd.Series,
    priors: EvidencePriors,
    alpha: float,
) -> pd.DataFrame:
    """Compute smoothed evidence rates for one grouping key."""

    work = pd.DataFrame(
        {
            "key": key,
            "approved": (status == "approved").astype(float),
            "rejected": (status == "rejected").astype(float),
            "validated": status.isin(VALIDATED_STATUSES).astype(float),
            "type_correction": type_correction_flag.astype(float),
            "scita_success": scita_success.map({True: 1.0, False: 0.0}),
        },
        index=status.index,
    )
    work = work[work["key"].notna()]
    if work.empty:
        return pd.DataFrame(
            columns=[
                "smoothed_approval_rate",
                "smoothed_reject_rate",
                "type_correction_rate",
                "scita_success_rate",
                "trust",
            ]
        )

    grouped = work.groupby("key", dropna=True).agg(
        approved_count=("approved", "sum"),
        rejected_count=("rejected", "sum"),
        validated_count=("validated", "sum"),
        type_correction_rate=("type_correction", "mean"),
        scita_success_rate=("scita_success", "mean"),
    )
    denominator = grouped["validated_count"] + alpha
    grouped["smoothed_approval_rate"] = (
        grouped["approved_count"] + alpha * priors.approval_rate
    ) / denominator
    grouped["smoothed_reject_rate"] = (
        grouped["rejected_count"] + alpha * priors.reject_rate
    ) / denominator
    grouped["type_correction_rate"] = grouped["type_correction_rate"].fillna(
        priors.type_correction_rate
    )
    grouped["scita_success_rate"] = grouped["scita_success_rate"].fillna(
        priors.scita_success_rate
    )
    grouped["trust"] = grouped.apply(
        lambda row: _trust_formula(
            smoothed_approval_rate=row["smoothed_approval_rate"],
            smoothed_reject_rate=row["smoothed_reject_rate"],
            type_correction_rate=row["type_correction_rate"],
            scita_success_rate=row["scita_success_rate"],
        ),
        axis=1,
    )
    return grouped


def _map_group_column(
    key: pd.Series,
    stats: pd.DataFrame,
    column: str,
    default: float,
) -> pd.Series:
    """Map a group-level feature back to rows with a global fallback."""

    if stats.empty or column not in stats.columns:
        return pd.Series([default] * len(key), index=key.index, dtype="float64")
    return key.map(stats[column]).fillna(default).astype(float)


def add_evidence_quality_features(
    frame: pd.DataFrame,
    *,
    alpha: float = EVIDENCE_TRUST_ALPHA,
) -> pd.DataFrame:
    """Add Bayesian-smoothed evidence trust and row-level evidence quality features."""

    result = add_type_correction_flag(frame)
    status = _normalise_status_series(result)
    scita_success = _normalise_scita_success(result)
    priors = _global_priors(result, status, scita_success)

    group_specs = {
        "device": ("device_id", "device_trust"),
        "user": ("created_by_id", "user_trust"),
        "station": ("police_station", "station_evidence_quality"),
    }
    for prefix, (source_column, trust_column) in group_specs.items():
        key = _normalise_group_key(result, source_column)
        stats = _group_evidence_stats(
            key=key,
            status=status,
            type_correction_flag=result["type_correction_flag"],
            scita_success=scita_success,
            priors=priors,
            alpha=alpha,
        )
        result[trust_column] = _map_group_column(key, stats, "trust", priors.trust_score)
        result[f"{prefix}_approval_rate"] = _map_group_column(
            key,
            stats,
            "smoothed_approval_rate",
            priors.approval_rate,
        )
        result[f"{prefix}_reject_rate"] = _map_group_column(
            key,
            stats,
            "smoothed_reject_rate",
            priors.reject_rate,
        )
        result[f"{prefix}_type_correction_rate"] = _map_group_column(
            key,
            stats,
            "type_correction_rate",
            priors.type_correction_rate,
        )
        result[f"{prefix}_scita_success_rate"] = _map_group_column(
            key,
            stats,
            "scita_success_rate",
            priors.scita_success_rate,
        )

    if "zone_id" in result.columns:
        zone_key = _normalise_group_key(result, "zone_id")
        zone_stats = _group_evidence_stats(
            key=zone_key,
            status=status,
            type_correction_flag=result["type_correction_flag"],
            scita_success=scita_success,
            priors=priors,
            alpha=alpha,
        )
        result["zone_scita_success_rate"] = _map_group_column(
            zone_key,
            zone_stats,
            "scita_success_rate",
            priors.scita_success_rate,
        )

    if "validation_confidence" not in result.columns:
        result["validation_confidence"] = status.map(validation_confidence)
    else:
        result["validation_confidence"] = pd.to_numeric(
            result["validation_confidence"],
            errors="coerce",
        ).fillna(status.map(validation_confidence))

    result["evidence_quality_score"] = (
        0.50 * result["validation_confidence"]
        + 0.25 * result["device_trust"]
        + 0.15 * result["user_trust"]
        + 0.10 * result["station_evidence_quality"]
    ).clip(lower=0.0, upper=1.0)
    return result


def compute_junction_centroids(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute median lat/lon centroids for named junctions."""

    required = {"junction_name", "latitude", "longitude"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns for junction centroid computation: {sorted(missing)}")

    work = frame.copy()
    work["_junction_key"] = work["junction_name"].map(_normalise_optional_text)
    work["_valid_named_junction"] = work["_junction_key"].map(_is_valid_named_junction)
    work["latitude"] = pd.to_numeric(work["latitude"], errors="coerce")
    work["longitude"] = pd.to_numeric(work["longitude"], errors="coerce")
    work = work[
        work["_valid_named_junction"]
        & work["latitude"].notna()
        & work["longitude"].notna()
    ]
    if work.empty:
        return pd.DataFrame(
            columns=[
                "junction_name",
                "junction_centroid_latitude",
                "junction_centroid_longitude",
                "junction_record_count",
            ]
        )

    centroids = (
        work.groupby("_junction_key", dropna=True)
        .agg(
            junction_centroid_latitude=("latitude", "median"),
            junction_centroid_longitude=("longitude", "median"),
            junction_record_count=("junction_name", "size"),
        )
        .reset_index(names="junction_name")
    )
    return centroids.sort_values("junction_name").reset_index(drop=True)


def _haversine_distance_m(
    latitude: float,
    longitude: float,
    centroid_latitudes: pd.Series,
    centroid_longitudes: pd.Series,
) -> pd.Series:
    """Compute great-circle distances from one point to centroid coordinates."""

    lat1 = math.radians(latitude)
    lon1 = math.radians(longitude)
    lat2 = centroid_latitudes.astype(float).map(math.radians)
    lon2 = centroid_longitudes.astype(float).map(math.radians)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    haversine = (dlat / 2).map(math.sin) ** 2 + math.cos(lat1) * lat2.map(math.cos) * (
        (dlon / 2).map(math.sin) ** 2
    )
    return 2 * EARTH_RADIUS_M * haversine.map(math.sqrt).map(math.asin)


def add_hidden_junction_basin_features(
    frame: pd.DataFrame,
    *,
    threshold_m: float = JUNCTION_BASIN_THRESHOLD_M,
    junction_centroids: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Assign rows to explicit or hidden named-junction basins using lat/lon distance."""

    required = {"junction_name", "latitude", "longitude"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns for hidden junction basin detection: {sorted(missing)}")

    result = frame.copy()
    result["_junction_key"] = result["junction_name"].map(_normalise_optional_text)
    result["_valid_named_junction"] = result["_junction_key"].map(_is_valid_named_junction)
    result["latitude"] = pd.to_numeric(result["latitude"], errors="coerce")
    result["longitude"] = pd.to_numeric(result["longitude"], errors="coerce")

    centroids = (
        compute_junction_centroids(result)
        if junction_centroids is None
        else junction_centroids.copy()
    )
    result["hidden_junction_id"] = pd.NA
    result["hidden_junction_weight"] = 0.0
    result["nearest_named_junction_distance_m"] = pd.NA

    named_mask = result["_valid_named_junction"]
    result.loc[named_mask, "hidden_junction_id"] = result.loc[named_mask, "_junction_key"]
    result.loc[named_mask, "hidden_junction_weight"] = 1.0
    result.loc[named_mask, "nearest_named_junction_distance_m"] = 0.0

    if not centroids.empty:
        centroid_lats = centroids["junction_centroid_latitude"]
        centroid_lons = centroids["junction_centroid_longitude"]
        no_junction_mask = (
            ~named_mask
            & result["latitude"].notna()
            & result["longitude"].notna()
        )
        for index, row in result.loc[no_junction_mask].iterrows():
            distances = _haversine_distance_m(
                float(row["latitude"]),
                float(row["longitude"]),
                centroid_lats,
                centroid_lons,
            )
            nearest_position = distances.idxmin()
            nearest_distance = float(distances.loc[nearest_position])
            result.at[index, "nearest_named_junction_distance_m"] = nearest_distance
            if nearest_distance <= threshold_m:
                result.at[index, "hidden_junction_id"] = centroids.loc[
                    nearest_position,
                    "junction_name",
                ]
                result.at[index, "hidden_junction_weight"] = math.exp(
                    -nearest_distance / threshold_m
                )

    result["nearest_named_junction_distance_m"] = pd.to_numeric(
        result["nearest_named_junction_distance_m"],
        errors="coerce",
    )
    return result.drop(columns=["_junction_key", "_valid_named_junction"])


def build_junction_basin_table(
    frame: pd.DataFrame,
    *,
    zone_column: str = "zone_id",
    datetime_column: str = "created_datetime_ist",
    window: str = "3h",
) -> pd.DataFrame:
    """Aggregate hidden junction basin impact for zone-time feature tables."""

    enriched = (
        frame
        if {"hidden_junction_id", "hidden_junction_weight"}.issubset(frame.columns)
        else add_hidden_junction_basin_features(frame)
    ).copy()

    if "row_obstruction_score" not in enriched.columns:
        enriched["row_obstruction_score"] = 0.0
    enriched["_junction_basin_weighted_pfdi"] = (
        pd.to_numeric(enriched["row_obstruction_score"], errors="coerce").fillna(0.0)
        * pd.to_numeric(enriched["hidden_junction_weight"], errors="coerce").fillna(0.0)
    )
    junction_names = (
        enriched["junction_name"].map(_normalise_optional_text)
        if "junction_name" in enriched.columns
        else pd.Series([pd.NA] * len(enriched), index=enriched.index, dtype="object")
    )
    enriched["_hidden_no_junction_spillover"] = (
        enriched["hidden_junction_id"].notna()
        & ~junction_names.map(_is_valid_named_junction)
    )
    enriched["_hidden_no_junction_spillover_impact"] = enriched[
        "_junction_basin_weighted_pfdi"
    ].where(enriched["_hidden_no_junction_spillover"], 0.0)

    if zone_column not in enriched.columns:
        enriched[zone_column] = pd.NA
    if datetime_column in enriched.columns:
        created_time = pd.to_datetime(enriched[datetime_column], errors="coerce")
        enriched["time_window_start"] = created_time.dt.floor(window)
    elif "time_window_start" not in enriched.columns:
        enriched["time_window_start"] = pd.NaT

    assigned = enriched[enriched["hidden_junction_id"].notna()].copy()
    if assigned.empty:
        return pd.DataFrame(
            columns=[
                zone_column,
                "time_window_start",
                "hidden_junction_id",
                "junction_basin_raw_impact",
                "junction_basin_pfdi",
                "hidden_no_junction_spillover_count",
                "hidden_no_junction_spillover_impact",
            ]
        )

    basin_table = (
        assigned.groupby([zone_column, "time_window_start", "hidden_junction_id"], dropna=False)
        .agg(
            junction_basin_raw_impact=("hidden_junction_weight", "sum"),
            junction_basin_pfdi=("_junction_basin_weighted_pfdi", "sum"),
            hidden_no_junction_spillover_count=("_hidden_no_junction_spillover", "sum"),
            hidden_no_junction_spillover_impact=(
                "_hidden_no_junction_spillover_impact",
                "sum",
            ),
        )
        .reset_index()
    )
    basin_table["hidden_no_junction_spillover_count"] = basin_table[
        "hidden_no_junction_spillover_count"
    ].astype("int64")
    return basin_table


def write_junction_basin_table(
    frame: pd.DataFrame,
    output_path: str | Path = JUNCTION_BASINS_PATH,
) -> pd.DataFrame:
    """Build and save the junction basin zone-time table as parquet."""

    basin_table = build_junction_basin_table(frame)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    basin_table.to_parquet(destination, index=False)
    return basin_table


def normalized_zone_entropy(zone_counts: pd.Series) -> float:
    """Compute zone coverage entropy normalized by log(number of zones)."""

    counts = pd.to_numeric(zone_counts, errors="coerce").dropna()
    counts = counts[counts > 0]
    zone_count = int(len(counts))
    total = float(counts.sum())
    if zone_count <= 1 or total <= 0:
        return 0.0
    probabilities = counts / total
    entropy = float(-(probabilities * probabilities.map(math.log)).sum())
    return float(max(0.0, min(1.0, entropy / math.log(zone_count))))


def classify_patrol_myopia(score: float) -> str:
    """Classify patrol myopia into low, medium, or high risk bands."""

    if score < 0.35:
        return "Low"
    if score > 0.65:
        return "High"
    return "Medium"


def _station_window_counts(group: pd.DataFrame) -> tuple[int, int]:
    """Count morning and evening records for a station group."""

    created_time = pd.to_datetime(group["created_datetime_ist"], errors="coerce")
    minutes = created_time.dt.hour * 60 + created_time.dt.minute
    morning = int(((minutes >= 7 * 60 + 30) & (minutes < 15 * 60 + 30)).sum())
    evening = int(((minutes >= 15 * 60 + 30) & (minutes < 20 * 60 + 30)).sum())
    return morning, evening


def compute_patrol_myopia_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute station-level Patrol Myopia Index metrics."""

    required = {"police_station", "zone_id", "created_datetime_ist"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns for patrol myopia computation: {sorted(missing)}")

    work = frame.copy()
    work["police_station"] = work["police_station"].map(
        lambda value: normalize_text_value(value, unknown_for_null=True)
    )
    work["zone_id"] = work["zone_id"].map(
        lambda value: normalize_text_value(value, unknown_for_null=True)
    )
    for optional_column in ("device_id", "created_by_id"):
        if optional_column not in work.columns:
            work[optional_column] = pd.NA
        work[optional_column] = work[optional_column].map(_normalise_optional_text)

    records: list[dict[str, Any]] = []
    for station, group in work.groupby("police_station", dropna=False):
        total_records = int(len(group))
        zone_counts = group["zone_id"].value_counts(dropna=False)
        top_10_zone_records = int(zone_counts.head(10).sum())
        top_10_zone_share = top_10_zone_records / total_records if total_records else 0.0
        zone_entropy = normalized_zone_entropy(zone_counts)
        morning_records, evening_records = _station_window_counts(group)
        morning_bias = morning_records / (morning_records + evening_records + EPSILON)
        device_diversity = (
            int(group["device_id"].nunique(dropna=True)) / total_records if total_records else 0.0
        )
        user_diversity = (
            int(group["created_by_id"].nunique(dropna=True)) / total_records
            if total_records
            else 0.0
        )
        patrol_myopia = (
            0.40 * top_10_zone_share
            + 0.30 * morning_bias
            + 0.20 * (1.0 - zone_entropy)
            + 0.10 * (1.0 - device_diversity)
        )
        patrol_myopia = float(max(0.0, min(1.0, patrol_myopia)))
        records.append(
            {
                "police_station": station,
                "total_records": total_records,
                "unique_zones": int(zone_counts.size),
                "top_10_zone_records": top_10_zone_records,
                "top_10_zone_share": float(top_10_zone_share),
                "zone_coverage_entropy": float(zone_entropy),
                "morning_records_0730_1530": morning_records,
                "evening_records_1530_2030": evening_records,
                "morning_bias": float(morning_bias),
                "unique_devices": int(group["device_id"].nunique(dropna=True)),
                "device_diversity": float(device_diversity),
                "unique_created_by_users": int(group["created_by_id"].nunique(dropna=True)),
                "user_diversity": float(user_diversity),
                "patrol_myopia_index": patrol_myopia,
                "patrol_myopia_level": classify_patrol_myopia(patrol_myopia),
            }
        )

    if not records:
        return pd.DataFrame(
            columns=[
                "police_station",
                "total_records",
                "unique_zones",
                "top_10_zone_records",
                "top_10_zone_share",
                "zone_coverage_entropy",
                "morning_records_0730_1530",
                "evening_records_1530_2030",
                "morning_bias",
                "unique_devices",
                "device_diversity",
                "unique_created_by_users",
                "user_diversity",
                "patrol_myopia_index",
                "patrol_myopia_level",
            ]
        )
    return (
        pd.DataFrame(records)
        .sort_values(["patrol_myopia_index", "police_station"], ascending=[False, True])
        .reset_index(drop=True)
    )


def write_patrol_myopia_table(
    frame: pd.DataFrame,
    output_path: str | Path = PATROL_MYOPIA_PATH,
) -> pd.DataFrame:
    """Build and save the station-level Patrol Myopia Index table as parquet."""

    myopia_table = compute_patrol_myopia_table(frame)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    myopia_table.to_parquet(destination, index=False)
    return myopia_table
