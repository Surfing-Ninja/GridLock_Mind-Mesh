"""Ranking, calibration, hotspot, and PFDI evaluation metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import roc_auc_score


def _to_numpy(values) -> np.ndarray:
    """Convert tensor-like values to a NumPy array."""

    if isinstance(values, torch.Tensor):
        return values.detach().cpu().numpy()
    return np.asarray(values)


def precision_at_k(scores, labels, k: int = 5) -> float:
    """Compute binary precision@k."""

    score_values = _to_numpy(scores).reshape(-1)
    label_values = _to_numpy(labels).reshape(-1).astype(float)
    if score_values.size == 0:
        return 0.0
    top_k = min(k, score_values.size)
    indices = np.argsort(score_values)[::-1][:top_k]
    return float(label_values[indices].mean())


def ndcg_at_k(scores, relevance, k: int = 5) -> float:
    """Compute NDCG@k for graded relevance."""

    score_values = _to_numpy(scores).reshape(-1)
    relevance_values = _to_numpy(relevance).reshape(-1).astype(float)
    if score_values.size == 0:
        return 0.0
    top_k = min(k, score_values.size)
    order = np.argsort(score_values)[::-1][:top_k]
    gains = (2 ** relevance_values[order] - 1) / np.log2(np.arange(2, top_k + 2))
    ideal_order = np.argsort(relevance_values)[::-1][:top_k]
    ideal = (2 ** relevance_values[ideal_order] - 1) / np.log2(np.arange(2, top_k + 2))
    ideal_sum = ideal.sum()
    return float(gains.sum() / ideal_sum) if ideal_sum > 0 else 0.0


def station_wise_precision_at_k(scores, labels, station_ids, k: int = 5) -> float:
    """Compute mean precision@k across station groups."""

    score_values = _to_numpy(scores).reshape(-1)
    label_values = _to_numpy(labels).reshape(-1)
    station_values = _to_numpy(station_ids).reshape(-1)
    precisions = []
    for station in np.unique(station_values):
        mask = station_values == station
        if mask.any():
            precisions.append(precision_at_k(score_values[mask], label_values[mask], k=k))
    return float(np.mean(precisions)) if precisions else 0.0


def mae_pfdi(pred_pfdi, target_pfdi) -> float:
    """Mean absolute error for PFDI."""

    pred = _to_numpy(pred_pfdi).astype(float)
    target = _to_numpy(target_pfdi).astype(float)
    return float(np.mean(np.abs(pred - target))) if pred.size else 0.0


def wape_count(pred_count, target_count) -> float:
    """Weighted absolute percentage error for counts."""

    pred = _to_numpy(pred_count).astype(float)
    target = _to_numpy(target_count).astype(float)
    denominator = np.abs(target).sum()
    if denominator <= 1e-12:
        return 0.0
    return float(np.abs(pred - target).sum() / denominator)


def hotspot_auc(hotspot_prob, target_hotspot) -> float | None:
    """Compute hotspot AUC when both classes are present."""

    prob = _to_numpy(hotspot_prob).reshape(-1).astype(float)
    target = _to_numpy(target_hotspot).reshape(-1).astype(int)
    if len(np.unique(target)) < 2:
        return None
    return float(roc_auc_score(target, prob))


def ranking_metrics_frame(scores, hotspot_labels, relevance, station_ids) -> pd.DataFrame:
    """Return the requested ranking metrics in a one-row frame."""

    return pd.DataFrame(
        [
            {
                "precision_at_5": precision_at_k(scores, hotspot_labels, k=5),
                "precision_at_10": precision_at_k(scores, hotspot_labels, k=10),
                "ndcg_at_5": ndcg_at_k(scores, relevance, k=5),
                "ndcg_at_10": ndcg_at_k(scores, relevance, k=10),
                "station_wise_precision_at_5": station_wise_precision_at_k(
                    scores,
                    hotspot_labels,
                    station_ids,
                    k=5,
                ),
            }
        ]
    )
