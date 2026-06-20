"""Human-readable recommendation explanation builders."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd


def _parse_reasons(value: Any) -> list[str]:
    """Normalize stored rule reasons."""

    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    if pd.isna(value):
        return []
    return [str(value)]


def build_recommendation_explanation(row: pd.Series) -> str:
    """Build a concise explanation string for one selected recommendation."""

    action = str(row.get("action", "action"))
    zone_id = str(row.get("zone_id", "unknown"))
    reasons = _parse_reasons(row.get("rule_reasons", []))
    reason_text = "; ".join(reasons) if reasons else "highest expected relief under current constraints"
    relief = float(row.get("expected_relief", 0.0))
    officers = int(row.get("officers_required", 0))
    tow_units = int(row.get("tow_units_required", 0))
    return (
        f"{action} for zone {zone_id}: {reason_text}. "
        f"Expected relief {relief:.1f}; requires {officers} officer(s)"
        f"{f' and {tow_units} tow unit(s)' if tow_units else ''}."
    )


def build_recommendation_json(row: pd.Series) -> str:
    """Build machine-readable recommendation explanation JSON."""

    payload = {
        "action": str(row.get("action", "")),
        "category": str(row.get("action_category", "")),
        "reasons": _parse_reasons(row.get("rule_reasons", [])),
        "expected_relief": round(float(row.get("expected_relief", 0.0)), 3),
        "score_per_resource_unit": round(float(row.get("score_per_resource_unit", 0.0)), 3),
        "resources": {
            "officers": int(row.get("officers_required", 0)),
            "tow_units": int(row.get("tow_units_required", 0)),
        },
    }
    return json.dumps(payload, separators=(",", ":"))
