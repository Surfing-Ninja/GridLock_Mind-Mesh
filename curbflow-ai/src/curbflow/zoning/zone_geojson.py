"""GeoJSON export utilities for dashboard zone layers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


ZONES_GEOJSON_PATH = Path("data/processed/zones.geojson")


def zones_to_geojson(zones: pd.DataFrame) -> dict[str, Any]:
    """Convert a zone table with polygon rings to GeoJSON."""

    features = []
    for row in zones.itertuples(index=False):
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "zone_id": row.zone_id,
                    "record_count": int(row.record_count),
                    "is_active_zone": bool(row.is_active_zone),
                    "zone_centroid_lat": float(row.zone_centroid_lat),
                    "zone_centroid_lon": float(row.zone_centroid_lon),
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [row.polygon],
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def write_zones_geojson(
    zones: pd.DataFrame,
    output_path: str | Path = ZONES_GEOJSON_PATH,
) -> dict[str, Any]:
    """Write zone polygons to GeoJSON and return the GeoJSON object."""

    geojson = zones_to_geojson(zones)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(geojson), encoding="utf-8")
    return geojson
