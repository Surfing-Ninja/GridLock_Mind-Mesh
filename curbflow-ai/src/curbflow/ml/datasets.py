"""PyTorch and tabular dataset wrappers for CurbFlow model training."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
from torch.utils.data import Dataset

from curbflow.features.sequence_dataset import (
    MODEL_TRAINING_TABLE_PATH,
    SequenceConfig,
    SequenceSplit,
    build_sequence_splits_from_parquet,
)


class CurbFlowSequenceDataset(Dataset):
    """PyTorch dataset wrapper for one chronological CurbFlow sequence split."""

    def __init__(self, split: SequenceSplit) -> None:
        self.split = split

    def __len__(self) -> int:
        return int(self.split.X.shape[0])

    def __getitem__(self, index: int) -> dict[str, Any]:
        return {
            "X": torch.as_tensor(self.split.X[index], dtype=torch.float32),
            "y_count": torch.as_tensor(self.split.y_count[index], dtype=torch.float32),
            "y_pfdi": torch.as_tensor(self.split.y_pfdi[index], dtype=torch.float32),
            "y_hotspot": torch.as_tensor(self.split.y_hotspot[index], dtype=torch.float32),
            "y_q90_pfdi": torch.as_tensor(self.split.y_q90_pfdi[index], dtype=torch.float32),
            "y_rank_relevance": torch.as_tensor(
                self.split.y_rank_relevance[index],
                dtype=torch.long,
            ),
            "exposure_next": torch.as_tensor(self.split.exposure_next[index], dtype=torch.float32),
            "zero_weight_next": torch.as_tensor(
                self.split.zero_weight_next[index],
                dtype=torch.float32,
            ),
            "rank_groups": torch.as_tensor(self.split.rank_groups[index], dtype=torch.long),
            "window_start": self.split.window_start[index],
            "zone_ids": self.split.zone_ids,
            "police_station_ids": torch.as_tensor(self.split.police_station_ids, dtype=torch.long),
        }


def load_curbflow_sequence_datasets(
    path: str | Path = MODEL_TRAINING_TABLE_PATH,
    *,
    config: SequenceConfig = SequenceConfig(),
) -> tuple[CurbFlowSequenceDataset, CurbFlowSequenceDataset, CurbFlowSequenceDataset]:
    """Load train/val/test PyTorch datasets from the model training table."""

    splits = build_sequence_splits_from_parquet(path, config=config)
    return (
        CurbFlowSequenceDataset(splits.train),
        CurbFlowSequenceDataset(splits.val),
        CurbFlowSequenceDataset(splits.test),
    )
