"""Exploit/explore priority score computation for station-wise planning."""

from __future__ import annotations

import pandas as pd

from curbflow.planner.action_rules import BLINDSPOT_ACTIONS, numeric_value


MODE_WEIGHTS = {
    "conservative": {"exploit": 0.85, "explore": 0.15},
    "balanced": {"exploit": 0.70, "explore": 0.30},
    "discovery": {"exploit": 0.55, "explore": 0.45},
}


def validate_mode(mode: str) -> str:
    """Validate and normalize planner mode."""

    normalized = str(mode).strip().lower()
    if normalized not in MODE_WEIGHTS:
        raise ValueError(f"Unknown planner mode '{mode}'. Expected one of {sorted(MODE_WEIGHTS)}.")
    return normalized


def mode_explore_fraction(mode: str) -> float:
    """Return the target blindspot/explore allocation fraction for a mode."""

    return MODE_WEIGHTS[validate_mode(mode)]["explore"]


def row_priority_score(row: pd.Series, mode: str = "balanced") -> float:
    """Compute deployment priority for one row using mode-specific score columns when present."""

    mode = validate_mode(mode)
    priority_column = f"deployment_priority_{mode}"
    if priority_column in row.index and not pd.isna(row[priority_column]):
        return float(row[priority_column])

    exploit = numeric_value(row, "exploit_score", "observed_risk_score", "predicted_pfdi")
    explore = numeric_value(row, "explore_score", "blindspot_risk_score", "blindspot_risk")
    weights = MODE_WEIGHTS[mode]
    return float(weights["exploit"] * exploit + weights["explore"] * explore)


def action_priority_score(row: pd.Series, candidate: pd.Series, mode: str = "balanced") -> float:
    """Compute expected relief for one candidate action."""

    base_priority = row_priority_score(row, mode=mode)
    action_multiplier = float(candidate.get("action_multiplier", 1.0))
    if candidate.get("action") in BLINDSPOT_ACTIONS:
        explore_score = numeric_value(row, "explore_score", "blindspot_risk_score", "blindspot_risk")
        base_priority = max(base_priority, explore_score)
    return max(base_priority * action_multiplier, 0.0)


def add_candidate_priority_scores(
    candidates: pd.DataFrame,
    rows: pd.DataFrame,
    *,
    mode: str = "balanced",
) -> pd.DataFrame:
    """Add expected relief and relief-per-resource scores to candidate rows."""

    if candidates.empty:
        return candidates.copy()
    mode = validate_mode(mode)
    row_lookup = {
        (str(row["zone_id"]), pd.Timestamp(row["window_start"])): row
        for _, row in rows.iterrows()
    }
    result = candidates.copy()
    expected_relief = []
    source_exploit = []
    source_explore = []
    for _, candidate in result.iterrows():
        key = (str(candidate["zone_id"]), pd.Timestamp(candidate["window_start"]))
        row = row_lookup[key]
        expected_relief.append(action_priority_score(row, candidate, mode=mode))
        source_exploit.append(numeric_value(row, "exploit_score", "observed_risk_score", "predicted_pfdi"))
        source_explore.append(numeric_value(row, "explore_score", "blindspot_risk_score", "blindspot_risk"))
    result["expected_relief"] = pd.Series(expected_relief, index=result.index).clip(lower=0.0, upper=150.0)
    result["source_exploit_score"] = source_exploit
    result["source_explore_score"] = source_explore
    resource_units = (
        pd.to_numeric(result["officers_required"], errors="coerce").fillna(0.0)
        + 1.5 * pd.to_numeric(result["tow_units_required"], errors="coerce").fillna(0.0)
    ).clip(lower=1.0)
    result["score_per_resource_unit"] = result["expected_relief"] / resource_units
    return result.sort_values(
        ["score_per_resource_unit", "expected_relief"],
        ascending=False,
    ).reset_index(drop=True)
