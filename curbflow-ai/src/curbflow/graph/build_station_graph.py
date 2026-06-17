"""Build zone-to-station graph relations."""

from __future__ import annotations

import pandas as pd

from curbflow.data.clean import normalize_text_value


def _dominant_station(frame: pd.DataFrame) -> pd.DataFrame:
    """Return one dominant police station per zone."""

    work = frame.copy()
    if "police_station" not in work.columns:
        work["police_station"] = "unknown"
    work["police_station"] = work["police_station"].map(
        lambda value: normalize_text_value(value, unknown_for_null=True)
    )
    counts = (
        work.groupby(["zone_id", "police_station"], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values(["zone_id", "count"], ascending=[True, False])
    )
    return counts.drop_duplicates("zone_id")[["zone_id", "police_station"]]


def build_station_graph_edges(frame: pd.DataFrame) -> pd.DataFrame:
    """Connect zones that belong to the same dominant police station."""

    zone_station = _dominant_station(frame)
    records: list[dict[str, object]] = []
    for _, group in zone_station.groupby("police_station", dropna=False):
        zones = group["zone_id"].astype(str).tolist()
        for from_zone in zones:
            for to_zone in zones:
                if from_zone == to_zone:
                    continue
                records.append(
                    {
                        "edge_type": "zone_same_station",
                        "from_zone_id": from_zone,
                        "to_zone_id": to_zone,
                        "weight": 1.0,
                        "police_station": group["police_station"].iloc[0],
                    }
                )
    return pd.DataFrame(
        records,
        columns=["edge_type", "from_zone_id", "to_zone_id", "weight", "police_station"],
    )


def build_zone_station_membership_edges(frame: pd.DataFrame) -> pd.DataFrame:
    """Build heterogeneous zone-to-station membership edges."""

    zone_station = _dominant_station(frame)
    return zone_station.assign(
        edge_type="zone_belongs_to_station",
        from_node_type="zone",
        from_node_id=zone_station["zone_id"].astype(str),
        to_node_type="station",
        to_node_id=zone_station["police_station"].astype(str),
        weight=1.0,
    )[
        [
            "edge_type",
            "from_node_type",
            "from_node_id",
            "to_node_type",
            "to_node_id",
            "weight",
        ]
    ]
