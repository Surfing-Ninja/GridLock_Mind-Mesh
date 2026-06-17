"""Novel CurbFlow features including evidence-quality trust scores."""

from __future__ import annotations

import hashlib
import math
import re
import string
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
REPEAT_VEHICLE_ZONE_TIME_PATH = Path("data/processed/repeat_vehicle_zone_time.parquet")
JUNCTION_BASIN_THRESHOLD_M = 500.0
EARTH_RADIUS_M = 6_371_000.0
NO_JUNCTION_VALUES = {"no junction", "nojunction", "none", "unknown", "null"}
EPSILON = 1e-9
REPEAT_VEHICLE_WINDOW_HOURS = 6
PLACE_TYPE_FLAGS = {
    "commercial_market": (
        "market",
        "mall",
        "plaza",
        "commercial",
        "shopping",
        "complex",
        "bazaar",
    ),
    "transit_node": ("metro", "bus", "railway", "station", "terminal"),
    "institutional": ("school", "college", "university", "hospital"),
    "airport_zone": ("airport",),
    "religious_place": ("temple", "mosque", "church", "mandir"),
    "residential_layout": ("layout", "nagar", "colony", "residential", "cross", "main"),
    "entertainment": ("theatre", "cinema", "stadium"),
}
PLACE_TYPE_PRIORITY = (
    ("transit_node", "transit"),
    ("institutional", "institutional"),
    ("commercial_market", "commercial"),
    ("airport_zone", "airport"),
    ("entertainment", "entertainment"),
    ("religious_place", "religious"),
    ("residential_layout", "residential"),
)
LARGE_VEHICLE_TERMS = (
    "hgv",
    "lorry",
    "tanker",
    "bus",
    "lgv",
    "tempo",
    "mini lorry",
    "maxi cab",
    "van",
)


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


def _normalise_vehicle_number(value: Any) -> Any:
    """Normalize vehicle numbers for grouping while preserving missing values."""

    normalized = normalize_text_value(value)
    if pd.isna(normalized):
        return pd.NA
    compact = "".join(str(normalized).upper().split())
    return compact if compact else pd.NA


def anonymize_vehicle_number(value: Any) -> Any:
    """Create a stable anonymous vehicle identifier for internal feature joins."""

    normalized = _normalise_vehicle_number(value)
    if pd.isna(normalized):
        return pd.NA
    return hashlib.sha256(str(normalized).encode("utf-8")).hexdigest()


def _normalise_repeat_dimension(frame: pd.DataFrame, column: str) -> pd.Series:
    """Normalize optional repeat-vehicle dimensions with unknown as a grouping bucket."""

    if column not in frame.columns:
        return pd.Series(["unknown"] * len(frame), index=frame.index, dtype="object")
    return frame[column].map(lambda value: normalize_text_value(value, unknown_for_null=True))


def add_repeat_vehicle_features(
    frame: pd.DataFrame,
    *,
    vehicle_column: str = "vehicle_number",
    zone_column: str = "zone_id",
    station_column: str = "police_station",
    datetime_column: str = "created_datetime_ist",
    window_hours: int = REPEAT_VEHICLE_WINDOW_HOURS,
) -> pd.DataFrame:
    """Add anonymized repeat-vehicle intelligence without future leakage."""

    required = {vehicle_column, datetime_column}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns for repeat vehicle features: {sorted(missing)}")

    result = frame.copy()
    result["anonymized_vehicle_id"] = result[vehicle_column].map(anonymize_vehicle_number)
    result["_repeat_vehicle_valid"] = result["anonymized_vehicle_id"].notna()
    result["_repeat_zone_key"] = _normalise_repeat_dimension(result, zone_column)
    result["_repeat_station_key"] = _normalise_repeat_dimension(result, station_column)
    result["_repeat_created_time"] = pd.to_datetime(
        result[datetime_column],
        errors="coerce",
        utc=True,
    )
    result["_repeat_local_day"] = pd.to_datetime(
        result[datetime_column],
        errors="coerce",
    ).dt.date

    valid = result[result["_repeat_vehicle_valid"]]
    vehicle_total_records = valid.groupby("anonymized_vehicle_id").size()
    vehicle_unique_zones = valid.groupby("anonymized_vehicle_id")["_repeat_zone_key"].nunique()
    vehicle_unique_stations = valid.groupby("anonymized_vehicle_id")[
        "_repeat_station_key"
    ].nunique()
    vehicle_unique_days = valid.groupby("anonymized_vehicle_id")["_repeat_local_day"].nunique()

    result["vehicle_total_records"] = (
        result["anonymized_vehicle_id"].map(vehicle_total_records).fillna(0).astype("int64")
    )
    result["vehicle_unique_zones"] = (
        result["anonymized_vehicle_id"].map(vehicle_unique_zones).fillna(0).astype("int64")
    )
    result["vehicle_unique_stations"] = (
        result["anonymized_vehicle_id"].map(vehicle_unique_stations).fillna(0).astype("int64")
    )
    result["vehicle_unique_days"] = (
        result["anonymized_vehicle_id"].map(vehicle_unique_days).fillna(0).astype("int64")
    )
    result["repeat_vehicle_flag"] = result["vehicle_total_records"] > 1
    result["multi_zone_repeat_flag"] = (
        result["repeat_vehicle_flag"] & (result["vehicle_unique_zones"] > 1)
    )
    result["multi_station_repeat_flag"] = (
        result["repeat_vehicle_flag"] & (result["vehicle_unique_stations"] > 1)
    )
    result["same_vehicle_same_zone_repeat_6h"] = False
    result["same_vehicle_different_zone_6h"] = False

    sorted_rows = result.sort_values(
        by=["_repeat_created_time"],
        na_position="last",
        kind="mergesort",
    )
    time_window = pd.Timedelta(hours=window_hours)
    for _, group in sorted_rows[sorted_rows["_repeat_vehicle_valid"]].groupby(
        "anonymized_vehicle_id",
        sort=False,
    ):
        last_seen_by_zone: dict[str, pd.Timestamp] = {}
        for row_index, row in group.iterrows():
            current_time = row["_repeat_created_time"]
            current_zone = str(row["_repeat_zone_key"])
            if pd.isna(current_time):
                continue

            same_zone_time = last_seen_by_zone.get(current_zone)
            if same_zone_time is not None and current_time - same_zone_time <= time_window:
                result.at[row_index, "same_vehicle_same_zone_repeat_6h"] = True

            different_zone_recent = any(
                zone != current_zone and current_time - previous_time <= time_window
                for zone, previous_time in last_seen_by_zone.items()
            )
            result.at[row_index, "same_vehicle_different_zone_6h"] = different_zone_recent
            last_seen_by_zone[current_zone] = current_time

    return result.drop(
        columns=[
            "_repeat_vehicle_valid",
            "_repeat_zone_key",
            "_repeat_station_key",
            "_repeat_created_time",
            "_repeat_local_day",
        ]
    )


def _repeat_vehicle_zone_entropy(group: pd.DataFrame) -> float:
    """Compute entropy of repeated vehicle observations across anonymized vehicles."""

    repeated = group[group["repeat_vehicle_flag"] & group["anonymized_vehicle_id"].notna()]
    if repeated.empty:
        return 0.0
    return normalized_zone_entropy(repeated["anonymized_vehicle_id"].value_counts())


def build_repeat_vehicle_zone_time_table(
    frame: pd.DataFrame,
    *,
    zone_column: str = "zone_id",
    datetime_column: str = "created_datetime_ist",
    window: str = "3h",
) -> pd.DataFrame:
    """Aggregate repeat-vehicle persistence features to zone-time rows."""

    enriched = (
        frame
        if {
            "anonymized_vehicle_id",
            "repeat_vehicle_flag",
            "same_vehicle_same_zone_repeat_6h",
            "same_vehicle_different_zone_6h",
        }.issubset(frame.columns)
        else add_repeat_vehicle_features(frame, zone_column=zone_column, datetime_column=datetime_column)
    ).copy()

    if zone_column not in enriched.columns:
        enriched[zone_column] = "unknown"
    enriched[zone_column] = enriched[zone_column].map(
        lambda value: normalize_text_value(value, unknown_for_null=True)
    )
    created_time = pd.to_datetime(enriched[datetime_column], errors="coerce")
    enriched["time_window_start"] = created_time.dt.floor(window)

    grouped = enriched.groupby([zone_column, "time_window_start"], dropna=False)
    table = grouped.agg(
        total_records=("anonymized_vehicle_id", "size"),
        unique_vehicle_count=("anonymized_vehicle_id", "nunique"),
        repeat_vehicle_count=("repeat_vehicle_flag", "sum"),
        same_vehicle_same_zone_6h_count=("same_vehicle_same_zone_repeat_6h", "sum"),
        same_vehicle_different_zone_6h_count=("same_vehicle_different_zone_6h", "sum"),
    ).reset_index()
    table["repeat_vehicle_count"] = table["repeat_vehicle_count"].astype("int64")
    table["same_vehicle_same_zone_6h_count"] = table[
        "same_vehicle_same_zone_6h_count"
    ].astype("int64")
    table["same_vehicle_different_zone_6h_count"] = table[
        "same_vehicle_different_zone_6h_count"
    ].astype("int64")
    table["repeat_vehicle_share"] = table["repeat_vehicle_count"] / table[
        "total_records"
    ].clip(lower=1)
    table["persistence_score"] = table["same_vehicle_same_zone_6h_count"] / table[
        "unique_vehicle_count"
    ].clip(lower=1)

    entropy_records = []
    for keys, group in grouped:
        zone_value, window_start = keys
        entropy_records.append(
            {
                zone_column: zone_value,
                "time_window_start": window_start,
                "repeat_vehicle_zone_entropy": _repeat_vehicle_zone_entropy(group),
            }
        )
    entropy = pd.DataFrame(entropy_records)
    table = table.merge(
        entropy,
        on=[zone_column, "time_window_start"],
        how="left",
    )
    table["repeat_vehicle_zone_entropy"] = table["repeat_vehicle_zone_entropy"].fillna(0.0)
    return table.sort_values([zone_column, "time_window_start"]).reset_index(drop=True)


def write_repeat_vehicle_zone_time_table(
    frame: pd.DataFrame,
    output_path: str | Path = REPEAT_VEHICLE_ZONE_TIME_PATH,
) -> pd.DataFrame:
    """Build and save repeat-vehicle zone-time features without exposing vehicle IDs."""

    repeat_table = build_repeat_vehicle_zone_time_table(frame)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    repeat_table.to_parquet(destination, index=False)
    return repeat_table


def _combined_place_text(row: pd.Series) -> str:
    """Combine location and junction text for place-type extraction."""

    values = [row.get("location"), row.get("junction_name")]
    parts = [str(value) for value in values if not pd.isna(value)]
    return re.sub(r"\s+", " ", " ".join(parts).lower()).strip()


def _contains_place_term(text: str, term: str) -> bool:
    """Match place terms on word boundaries where possible."""

    pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
    return bool(re.search(pattern, text))


def infer_place_type_primary(flags: dict[str, bool]) -> str:
    """Infer the primary place type using the product priority order."""

    for flag_name, label in PLACE_TYPE_PRIORITY:
        if flags.get(flag_name, False):
            return label
    return "unknown"


def add_place_type_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add text-derived place-type context flags and primary type."""

    result = frame.copy()
    texts = result.apply(_combined_place_text, axis=1)
    for flag_name, terms in PLACE_TYPE_FLAGS.items():
        result[flag_name] = texts.map(
            lambda text, term_values=terms: any(
                _contains_place_term(text, term) for term in term_values
            )
        )
    result["place_type_primary"] = result.apply(
        lambda row: infer_place_type_primary(
            {flag_name: bool(row[flag_name]) for flag_name in PLACE_TYPE_FLAGS}
        ),
        axis=1,
    )
    return result


def normalize_road_name(value: Any) -> str:
    """Normalize a road corridor name extracted from location text."""

    if pd.isna(value):
        return "unknown"
    text = str(value).split(",", maxsplit=1)[0].lower()
    text = re.sub(r"^\s*(?:#|no\.?\s*)?\d+[a-z]?(?:[/\-]\d+[a-z]?)?\s+", "", text)
    text = text.translate(str.maketrans(string.punctuation, " " * len(string.punctuation)))
    text = re.sub(r"(?<![a-z])rd(?![a-z])", "road", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or "unknown"


def extract_road_name(location: Any) -> str:
    """Extract the first comma-delimited location segment as a normalized road name."""

    return normalize_road_name(location)


def _vehicle_is_large(row: pd.Series) -> bool:
    """Return True for large vehicle categories using available vehicle type fields."""

    vehicle_text = " ".join(
        str(value)
        for value in (row.get("effective_vehicle_type"), row.get("updated_vehicle_type"), row.get("vehicle_type"))
        if not pd.isna(value)
    ).lower()
    vehicle_text = re.sub(r"\s+", " ", vehicle_text)
    return any(_contains_place_term(vehicle_text, term) for term in LARGE_VEHICLE_TERMS)


def _main_road_parking_signal(row: pd.Series) -> bool:
    """Return True when the row indicates main-road parking."""

    labels = row.get("parsed_violation_labels")
    if isinstance(labels, list) and "parking_in_main_road" in labels:
        return True
    violation_text = str(row.get("violation_type", "")).lower()
    location_text = str(row.get("location", "")).lower()
    return "main road" in violation_text or "parking in a main road" in violation_text or bool(
        re.search(r"\b(main road|ring road|highway)\b", location_text)
    )


def _rolling_corridor_pfdi(
    frame: pd.DataFrame,
    *,
    corridor_column: str,
    datetime_column: str,
    pfdi_column: str,
) -> pd.Series:
    """Compute per-row chronological 7-day PFDI sums by corridor."""

    work = frame[[corridor_column, datetime_column, pfdi_column]].copy()
    work["_original_index"] = frame.index
    work[datetime_column] = pd.to_datetime(work[datetime_column], errors="coerce", utc=True)
    work[pfdi_column] = pd.to_numeric(work[pfdi_column], errors="coerce").fillna(0.0)
    output = pd.Series(0.0, index=frame.index, dtype="float64")
    for _, group in work.dropna(subset=[datetime_column]).sort_values(datetime_column).groupby(
        corridor_column,
        sort=False,
    ):
        group = group.sort_values(datetime_column)
        rolling_values = group.set_index(datetime_column)[pfdi_column].rolling("7D").sum()
        output.loc[group["_original_index"]] = rolling_values.to_numpy()
    return output


def add_road_corridor_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add road-corridor identifiers and aggregate corridor risk features."""

    result = frame.copy()
    if "location" not in result.columns:
        result["location"] = pd.NA
    if "created_datetime_ist" not in result.columns:
        result["created_datetime_ist"] = pd.NaT
    if "row_obstruction_score" not in result.columns:
        result["row_obstruction_score"] = 0.0

    result["road_corridor_id"] = result["location"].map(extract_road_name)
    result["_corridor_pfdi_value"] = pd.to_numeric(
        result["row_obstruction_score"],
        errors="coerce",
    ).fillna(0.0)
    result["_corridor_large_vehicle"] = result.apply(_vehicle_is_large, axis=1)
    result["_corridor_main_road_parking"] = result.apply(_main_road_parking_signal, axis=1)
    result["_corridor_created_time"] = pd.to_datetime(
        result["created_datetime_ist"],
        errors="coerce",
        utc=True,
    )

    corridor_stats = result.groupby("road_corridor_id", dropna=False).agg(
        corridor_record_count=("road_corridor_id", "size"),
        corridor_pfdi=("_corridor_pfdi_value", "sum"),
        corridor_large_vehicle_share=("_corridor_large_vehicle", "mean"),
        corridor_main_road_parking_share=("_corridor_main_road_parking", "mean"),
    )
    result["corridor_record_count"] = result["road_corridor_id"].map(
        corridor_stats["corridor_record_count"]
    )
    result["corridor_pfdi"] = result["road_corridor_id"].map(corridor_stats["corridor_pfdi"])
    result["corridor_large_vehicle_share"] = result["road_corridor_id"].map(
        corridor_stats["corridor_large_vehicle_share"]
    )
    result["corridor_main_road_parking_share"] = result["road_corridor_id"].map(
        corridor_stats["corridor_main_road_parking_share"]
    )

    max_time = result["_corridor_created_time"].max()
    if pd.isna(max_time):
        recent_stats = pd.Series(dtype="float64")
    else:
        recent_cutoff = max_time - pd.Timedelta(days=7)
        recent_stats = result[result["_corridor_created_time"] >= recent_cutoff].groupby(
            "road_corridor_id",
            dropna=False,
        )["_corridor_pfdi_value"].sum()
    result["corridor_recent_pfdi"] = (
        result["road_corridor_id"].map(recent_stats).fillna(0.0).astype(float)
    )
    result["corridor_rolling_7d_pfdi"] = _rolling_corridor_pfdi(
        result,
        corridor_column="road_corridor_id",
        datetime_column="created_datetime_ist",
        pfdi_column="_corridor_pfdi_value",
    )
    return result.drop(
        columns=[
            "_corridor_pfdi_value",
            "_corridor_large_vehicle",
            "_corridor_main_road_parking",
            "_corridor_created_time",
        ]
    )


def add_place_type_and_road_corridor_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add place-type context and road-corridor risk features to row-level data."""

    return add_road_corridor_features(add_place_type_features(frame))


def build_road_corridor_zone_time_features(
    frame: pd.DataFrame,
    *,
    zone_column: str = "zone_id",
    datetime_column: str = "created_datetime_ist",
    window: str = "3h",
) -> pd.DataFrame:
    """Aggregate place and road-corridor fields for zone-time feature tables."""

    enriched = (
        frame
        if {"road_corridor_id", "place_type_primary", "corridor_recent_pfdi"}.issubset(
            frame.columns
        )
        else add_place_type_and_road_corridor_features(frame)
    ).copy()
    if zone_column not in enriched.columns:
        enriched[zone_column] = "unknown"
    enriched[zone_column] = enriched[zone_column].map(
        lambda value: normalize_text_value(value, unknown_for_null=True)
    )
    created_time = pd.to_datetime(enriched[datetime_column], errors="coerce")
    enriched["time_window_start"] = created_time.dt.floor(window)

    group_columns = [zone_column, "time_window_start", "road_corridor_id", "place_type_primary"]
    aggregations: dict[str, tuple[str, str]] = {
        "corridor_recent_pfdi": ("corridor_recent_pfdi", "max"),
        "corridor_record_count": ("corridor_record_count", "max"),
        "corridor_pfdi": ("corridor_pfdi", "max"),
    }
    for flag_name in PLACE_TYPE_FLAGS:
        aggregations[flag_name] = (flag_name, "max")
    zone_time = enriched.groupby(group_columns, dropna=False).agg(**aggregations).reset_index()
    for flag_name in PLACE_TYPE_FLAGS:
        zone_time[flag_name] = zone_time[flag_name].astype(bool)
    return zone_time.sort_values(group_columns).reset_index(drop=True)
