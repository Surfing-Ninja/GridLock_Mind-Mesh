"""Novel CurbFlow features including evidence-quality trust scores."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from curbflow.data.clean import normalize_boolean_value, normalize_text_value
from curbflow.scoring.pfdi import validation_confidence


EVIDENCE_TRUST_ALPHA = 100.0
VALIDATED_STATUSES = {"approved", "created1", "processing", "rejected", "duplicate"}


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
