"""Fixed-grid spatial zone construction utilities."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


DEFAULT_GRID_SIZE_METERS = 300.0
METERS_PER_LATITUDE_DEGREE = 111_320.0


@dataclass(frozen=True)
class GridSpec:
    """Grid resolution and degree step sizes."""

    grid_size_meters: float
    lat_step: float
    lon_step: float
    mean_latitude: float


def build_grid_spec(
    latitudes: pd.Series,
    grid_size_meters: float = DEFAULT_GRID_SIZE_METERS,
) -> GridSpec:
    """Build approximate 300m grid steps from mean latitude."""

    numeric_latitudes = pd.to_numeric(latitudes, errors="coerce").dropna()
    if numeric_latitudes.empty:
        raise ValueError("Cannot build grid spec without valid latitude values.")
    mean_latitude = float(numeric_latitudes.mean())
    lat_step = grid_size_meters / METERS_PER_LATITUDE_DEGREE
    lon_scale = max(math.cos(math.radians(mean_latitude)), 0.1)
    lon_step = grid_size_meters / (METERS_PER_LATITUDE_DEGREE * lon_scale)
    return GridSpec(
        grid_size_meters=grid_size_meters,
        lat_step=lat_step,
        lon_step=lon_step,
        mean_latitude=mean_latitude,
    )


def assign_grid_bins(frame: pd.DataFrame, spec: GridSpec) -> pd.DataFrame:
    """Assign latitude/longitude records to approximate fixed grid bins."""

    result = frame.copy()
    result["latitude"] = pd.to_numeric(result["latitude"], errors="coerce")
    result["longitude"] = pd.to_numeric(result["longitude"], errors="coerce")
    if result["latitude"].isna().any() or result["longitude"].isna().any():
        raise ValueError("Cannot assign zones when latitude or longitude contains invalid values.")

    result["zone_lat_bin"] = np.floor(result["latitude"] / spec.lat_step).astype("int64")
    result["zone_lon_bin"] = np.floor(result["longitude"] / spec.lon_step).astype("int64")
    result["zone_id"] = result["zone_lat_bin"].astype(str) + "_" + result["zone_lon_bin"].astype(str)
    result["zone_centroid_lat"] = (result["zone_lat_bin"] + 0.5) * spec.lat_step
    result["zone_centroid_lon"] = (result["zone_lon_bin"] + 0.5) * spec.lon_step
    return result


def polygon_for_grid_cell(lat_bin: int, lon_bin: int, spec: GridSpec) -> list[list[float]]:
    """Return a rectangular polygon ring for a grid cell as lon/lat coordinates."""

    min_lat = lat_bin * spec.lat_step
    max_lat = (lat_bin + 1) * spec.lat_step
    min_lon = lon_bin * spec.lon_step
    max_lon = (lon_bin + 1) * spec.lon_step
    return [
        [min_lon, min_lat],
        [max_lon, min_lat],
        [max_lon, max_lat],
        [min_lon, max_lat],
        [min_lon, min_lat],
    ]


def build_zone_table(
    assignments: pd.DataFrame,
    spec: GridSpec,
    active_zone_min_records: int = 100,
) -> pd.DataFrame:
    """Build one row per zone with centroid, polygon, counts, and active flag."""

    zones = (
        assignments.groupby(["zone_id", "zone_lat_bin", "zone_lon_bin"], as_index=False)
        .agg(
            record_count=("zone_id", "size"),
            zone_centroid_lat=("zone_centroid_lat", "first"),
            zone_centroid_lon=("zone_centroid_lon", "first"),
        )
        .sort_values("record_count", ascending=False)
        .reset_index(drop=True)
    )
    zones["is_active_zone"] = zones["record_count"] >= active_zone_min_records
    zones["polygon"] = zones.apply(
        lambda row: polygon_for_grid_cell(
            int(row["zone_lat_bin"]),
            int(row["zone_lon_bin"]),
            spec,
        ),
        axis=1,
    )
    return zones
