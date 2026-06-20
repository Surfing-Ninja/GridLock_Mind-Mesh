"""Theme 1 police violation schema definitions and column contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


RAW_CSV_PATH = Path("data/raw/police_parking_violations_nov2023_apr2024.csv")
CLEAN_PARQUET_PATH = Path("data/interim/violations_clean.parquet")

CREATED_DATETIME_COLUMN = "created_datetime"
SOURCE_TIMEZONE = "UTC"
TARGET_TIMEZONE = "Asia/Kolkata"

REQUIRED_COLUMNS = (
    "latitude",
    "longitude",
    CREATED_DATETIME_COLUMN,
)

TEXT_COLUMNS = (
    "police_station",
    "junction_name",
    "location",
    "vehicle_type",
    "updated_vehicle_type",
    "validation_status",
)

AUDIT_ONLY_NULLABLE_COLUMNS = (
    "closed_datetime",
    "action_taken_timestamp",
    "description",
)

BOOLEAN_LIKE_COLUMNS = (
    "data_sent_to_scita",
)

DERIVED_TIME_COLUMNS = (
    "created_datetime_ist",
    "date",
    "hour",
    "minute",
    "day_of_week",
    "is_weekend",
)


@dataclass(frozen=True)
class PreprocessPaths:
    """Input and output paths for the preprocessing stage."""

    raw_csv: Path = RAW_CSV_PATH
    clean_parquet: Path = CLEAN_PARQUET_PATH


def validate_required_columns(columns: list[str] | tuple[str, ...]) -> None:
    """Raise a clear error when the raw Theme 1 CSV lacks required columns."""

    missing = sorted(set(REQUIRED_COLUMNS) - set(columns))
    if missing:
        raise ValueError(f"Missing required Theme 1 columns: {missing}")
