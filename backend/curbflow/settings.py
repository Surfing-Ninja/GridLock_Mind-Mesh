from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV_PATH = PROJECT_ROOT / "jan to may police violation_anonymized791b166.csv"


@dataclass(frozen=True)
class CurbFlowSettings:
    project_root: Path = PROJECT_ROOT
    csv_path: Path = Path(os.getenv("CURBFLOW_CSV_PATH", DEFAULT_CSV_PATH))
    interim_dir: Path = PROJECT_ROOT / "data" / "interim"
    processed_dir: Path = PROJECT_ROOT / "data" / "processed"
    app_dir: Path = PROJECT_ROOT / "data" / "app"
    model_dir: Path = PROJECT_ROOT / "artifacts" / "models"
    metrics_dir: Path = PROJECT_ROOT / "artifacts" / "metrics"
    reports_dir: Path = PROJECT_ROOT / "artifacts" / "reports"
    duckdb_path: Path = PROJECT_ROOT / "data" / "app" / "curbflow.duckdb"
    feedback_path: Path = PROJECT_ROOT / "data" / "app" / "feedback.jsonl"
    zone_size_m: float = 300.0
    timezone: str = "Asia/Kolkata"

    def ensure_dirs(self) -> None:
        for path in (
            self.interim_dir,
            self.processed_dir,
            self.app_dir,
            self.model_dir,
            self.metrics_dir,
            self.reports_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


settings = CurbFlowSettings()
