"""Violation label parsing and normalization for multi-label rows."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable
from typing import Any

import pandas as pd


CANONICAL_LABELS = (
    "double_parking",
    "parking_in_main_road",
    "parking_near_road_crossing",
    "parking_near_traffic_light_zebra",
    "parking_opposite_another_vehicle",
    "parking_near_bus_stop_school_hospital",
    "parking_other_than_bus_stop",
    "no_parking",
    "wrong_parking",
    "parking_on_footpath",
    "defective_number_plate",
    "minor_other",
)


LABEL_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("double_parking", (r"\bdouble\s+parking\b",)),
    (
        "parking_in_main_road",
        (
            r"\bparking\s+(?:in|on)\s+a?\s*main\s+road\b",
            r"\bmain\s+road\b",
        ),
    ),
    (
        "parking_near_road_crossing",
        (
            r"\broad\s+crossing\b",
            r"\bnear\s+crossing\b",
        ),
    ),
    (
        "parking_near_traffic_light_zebra",
        (
            r"\btraffic\s+light\b",
            r"\bzebra\s+crossing\b",
            r"\bnear\s+signal\b",
            r"\bsignal\b",
        ),
    ),
    (
        "parking_opposite_another_vehicle",
        (
            r"\bopposite\s+another\s+parked\s+vehicle\b",
            r"\bopposite\s+another\s+vehicle\b",
            r"\bopposite\s+parked\s+vehicle\b",
        ),
    ),
    (
        "parking_near_bus_stop_school_hospital",
        (
            r"\bbus\s+stop\b",
            r"\bschool\b",
            r"\bhospital\b",
        ),
    ),
    ("parking_other_than_bus_stop", (r"\bparking\s+other\s+than\s+bus\s+stop\b",)),
    ("no_parking", (r"\bno\s+parking\b",)),
    ("wrong_parking", (r"\bwrong\s+parking\b",)),
    ("parking_on_footpath", (r"\bfoot\s*path\b", r"\bfootpath\b")),
    ("defective_number_plate", (r"\bdefective\s+number\s+plate\b", r"\bnumber\s+plate\b")),
)


def _split_raw_text(value: str) -> list[str]:
    """Split comma-separated violation text while preserving raw single labels."""

    stripped = value.strip()
    if not stripped:
        return []

    try:
        parsed = ast.literal_eval(stripped)
    except (ValueError, SyntaxError):
        parsed = None

    if isinstance(parsed, list):
        return [str(item) for item in parsed if str(item).strip()]
    if isinstance(parsed, tuple):
        return [str(item) for item in parsed if str(item).strip()]

    parts = [part.strip() for part in re.split(r"[,;|]+", stripped) if part.strip()]
    return parts or [stripped]


def extract_raw_violation_labels(value: Any) -> list[str]:
    """Extract raw violation labels from list-like, comma-separated, or raw text values."""

    if value is None:
        return []
    if isinstance(value, str):
        return _split_raw_text(value)
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        return [str(item) for item in value if not pd.isna(item) and str(item).strip()]
    if pd.isna(value):
        return []
    return [str(value)]


def canonicalize_violation_label(raw_label: Any) -> str:
    """Map a raw violation label to a canonical CurbFlow violation label."""

    text = re.sub(r"[_\-]+", " ", str(raw_label).strip().lower())
    text = re.sub(r"\s+", " ", text)
    if not text:
        return "minor_other"

    for label, patterns in LABEL_PATTERNS:
        if any(re.search(pattern, text) for pattern in patterns):
            return label
    return "minor_other"


def parse_violation_labels(value: Any) -> list[str]:
    """Parse and canonicalize a violation field, returning unique labels in source order."""

    labels: list[str] = []
    seen: set[str] = set()
    for raw_label in extract_raw_violation_labels(value):
        canonical = canonicalize_violation_label(raw_label)
        if canonical not in seen:
            labels.append(canonical)
            seen.add(canonical)
    return labels
