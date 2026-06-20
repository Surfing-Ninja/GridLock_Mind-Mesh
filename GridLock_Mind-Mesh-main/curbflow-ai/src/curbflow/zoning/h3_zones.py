"""Optional H3 spatial zone construction utilities."""

from __future__ import annotations

import pandas as pd


def assign_h3_zones(frame: pd.DataFrame, resolution: int = 9) -> pd.DataFrame:
    """Assign H3 zones when the optional h3 package is installed."""

    try:
        import h3
    except ImportError as exc:
        raise ImportError("H3 zoning is optional. Install `h3` to use this path.") from exc

    result = frame.copy()
    result["latitude"] = pd.to_numeric(result["latitude"], errors="coerce")
    result["longitude"] = pd.to_numeric(result["longitude"], errors="coerce")
    if result["latitude"].isna().any() or result["longitude"].isna().any():
        raise ValueError("Cannot assign H3 zones when latitude or longitude contains invalid values.")

    if hasattr(h3, "latlng_to_cell"):
        result["zone_id"] = result.apply(
            lambda row: h3.latlng_to_cell(row["latitude"], row["longitude"], resolution),
            axis=1,
        )
    else:
        result["zone_id"] = result.apply(
            lambda row: h3.geo_to_h3(row["latitude"], row["longitude"], resolution),
            axis=1,
        )
    return result
