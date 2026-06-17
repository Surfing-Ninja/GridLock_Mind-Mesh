"""Data cleaning routines for parking violation records."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from curbflow.data.load import load_raw_violations
from curbflow.data.schema import (
    AUDIT_ONLY_NULLABLE_COLUMNS,
    BOOLEAN_LIKE_COLUMNS,
    CLEAN_PARQUET_PATH,
    CREATED_DATETIME_COLUMN,
    RAW_CSV_PATH,
    TEXT_COLUMNS,
)
from curbflow.data.time_utils import add_created_datetime_parts


TRUE_VALUES = {"true", "t", "yes", "y", "1"}
FALSE_VALUES = {"false", "f", "no", "n", "0"}


def normalize_text_value(value: Any, *, unknown_for_null: bool = False) -> Any:
    """Normalize whitespace and casing for text fields."""

    if pd.isna(value):
        return "unknown" if unknown_for_null else pd.NA
    text = re.sub(r"\s+", " ", str(value).strip())
    if not text:
        return "unknown" if unknown_for_null else pd.NA
    return text.lower()


def normalize_boolean_value(value: Any) -> Any:
    """Normalize common boolean-like values while preserving unknowns."""

    if pd.isna(value):
        return pd.NA
    text = str(value).strip().lower()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    return pd.NA


def normalize_text_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize configured text columns without dropping audit-only null fields."""

    result = frame.copy()
    for column in TEXT_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA
        result[column] = result[column].map(
            lambda value, col=column: normalize_text_value(
                value,
                unknown_for_null=col == "validation_status",
            )
        )
    result["validation_status"] = result["validation_status"].fillna("unknown")
    return result


def normalize_boolean_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize boolean-like columns such as data_sent_to_scita."""

    result = frame.copy()
    for column in BOOLEAN_LIKE_COLUMNS:
        if column in result.columns:
            result[column] = result[column].map(normalize_boolean_value).astype("boolean")
    return result


def validate_lat_lon(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert latitude and longitude to numeric values."""

    result = frame.copy()
    result["latitude"] = pd.to_numeric(result["latitude"], errors="coerce")
    result["longitude"] = pd.to_numeric(result["longitude"], errors="coerce")
    return result


def ensure_audit_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Ensure fully nullable outcome-like columns remain available for audits."""

    result = frame.copy()
    for column in AUDIT_ONLY_NULLABLE_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA
    return result


def clean_violations(frame: pd.DataFrame) -> pd.DataFrame:
    """Clean raw violations while preserving audit-only null outcome columns."""

    result = ensure_audit_columns(frame)
    result = add_created_datetime_parts(result, CREATED_DATETIME_COLUMN)
    result = normalize_text_columns(result)
    result = normalize_boolean_columns(result)
    result = validate_lat_lon(result)
    return result


def preprocess_violations(
    raw_csv_path: str | Path = RAW_CSV_PATH,
    output_path: str | Path = CLEAN_PARQUET_PATH,
) -> pd.DataFrame:
    """Load, clean, and write the interim violations parquet artifact."""

    raw = load_raw_violations(raw_csv_path)
    clean = clean_violations(raw)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    clean.to_parquet(destination, index=False)
    return clean
