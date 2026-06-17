from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


FEATURE_COLUMNS = [
    "observed_pfdi",
    "event_count",
    "exposure",
    "coverage_gap",
    "static_potential",
    "blindspot_risk",
    "location_criticality",
    "repeat_persistence",
    "large_vehicle_share",
    "corridor_risk",
    "junction_basin_risk",
    "hour",
    "is_evening_peak",
]


def _chronological_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ordered = df.sort_values("window_start")
    n = len(ordered)
    train_end = max(1, int(n * 0.70))
    valid_end = max(train_end + 1, int(n * 0.85))
    return ordered.iloc[:train_end], ordered.iloc[train_end:valid_end], ordered.iloc[valid_end:]


def _normalise(values: np.ndarray) -> np.ndarray:
    lo = np.nanmin(values) if len(values) else 0.0
    hi = np.nanmax(values) if len(values) else 1.0
    if hi - lo < 1e-9:
        return np.zeros_like(values, dtype=float)
    return (values - lo) / (hi - lo)


def _rank_metrics(df: pd.DataFrame, score_col: str, label_col: str = "target_pfdi") -> dict[str, float]:
    metrics: dict[str, float] = {}
    if df.empty:
        return {"precision_at_5": 0.0, "precision_at_10": 0.0, "ndcg_at_5": 0.0, "ndcg_at_10": 0.0}
    threshold = float(df[label_col].quantile(0.80))
    ranked = df.sort_values(score_col, ascending=False)
    for k in (5, 10):
        top = ranked.head(k)
        rel = (top[label_col] >= threshold).astype(float).to_numpy()
        metrics[f"precision_at_{k}"] = float(rel.mean()) if len(rel) else 0.0
        discounts = 1.0 / np.log2(np.arange(2, len(rel) + 2))
        dcg = float((rel * discounts).sum())
        ideal_rel = np.sort((df[label_col] >= threshold).astype(float).to_numpy())[::-1][:k]
        ideal_dcg = float((ideal_rel * discounts[: len(ideal_rel)]).sum())
        metrics[f"ndcg_at_{k}"] = dcg / ideal_dcg if ideal_dcg > 0 else 0.0
    return metrics


def train_besthgt(zone_time: pd.DataFrame, model_dir: Path) -> tuple[pd.Series, dict[str, Any]]:
    features = zone_time[FEATURE_COLUMNS].fillna(0.0).astype("float32")
    label = zone_time["target_pfdi"].fillna(zone_time["observed_pfdi"]).astype("float32")
    rule_score = (
        0.40 * zone_time["observed_pfdi"].fillna(0)
        + 0.25 * zone_time["blindspot_risk"].fillna(0)
        + 0.20 * zone_time["static_potential"].fillna(0)
        + 0.15 * zone_time["coverage_gap"].fillna(0) * 100
    )
    try:
        import torch
        import torch.nn as nn

        class BiasExposureSTHGT(nn.Module):
            def __init__(self, input_dim: int, hidden_dim: int = 128) -> None:
                super().__init__()
                self.projection = nn.Linear(input_dim, hidden_dim)
                encoder_layer = nn.TransformerEncoderLayer(
                    d_model=hidden_dim,
                    nhead=4,
                    dim_feedforward=hidden_dim * 2,
                    dropout=0.15,
                    batch_first=True,
                )
                self.temporal_encoder = nn.TransformerEncoder(encoder_layer, num_layers=3)
                self.risk_head = nn.Sequential(
                    nn.LayerNorm(hidden_dim),
                    nn.Linear(hidden_dim, hidden_dim // 2),
                    nn.GELU(),
                    nn.Linear(hidden_dim // 2, 1),
                    nn.Sigmoid(),
                )

            def forward(self, x: torch.Tensor) -> torch.Tensor:
                h = self.projection(x).unsqueeze(1)
                h = self.temporal_encoder(h).squeeze(1)
                return self.risk_head(h).squeeze(-1) * 100.0

        train, valid, test = _chronological_split(zone_time)
        train_idx = train.index
        valid_idx = valid.index
        x = torch.tensor(features.to_numpy(), dtype=torch.float32)
        y = torch.tensor(label.to_numpy(), dtype=torch.float32)
        model = BiasExposureSTHGT(features.shape[1])
        optimiser = torch.optim.AdamW(model.parameters(), lr=0.002, weight_decay=1e-4)
        loss_fn = nn.SmoothL1Loss()
        for _ in range(8):
            model.train()
            optimiser.zero_grad()
            pred = model(x[features.index.get_indexer(train_idx)])
            loss = loss_fn(pred, y[features.index.get_indexer(train_idx)])
            loss.backward()
            optimiser.step()
        model.eval()
        with torch.no_grad():
            scores = model(x).detach().cpu().numpy()
            valid_pred = model(x[features.index.get_indexer(valid_idx)]).detach().cpu().numpy()
        torch.save(model.state_dict(), model_dir / "be_sthgt_model.pt")
        valid_mae = float(np.mean(np.abs(valid_pred - label.loc[valid_idx].to_numpy()))) if len(valid_idx) else 0.0
        meta = {
            "model": "BE-STHGT",
            "architecture": "feature projection + temporal transformer + bias-exposure risk head",
            "chronological_split": {"train": len(train), "validation": len(valid), "test": len(test)},
            "validation_mae_pfdi": valid_mae,
            "fallback_used": False,
        }
        return pd.Series(scores, index=zone_time.index, name="be_sthgt_score"), meta
    except Exception as exc:
        scores = _normalise(rule_score.to_numpy()) * 100
        meta = {
            "model": "BE-STHGT",
            "architecture": "configured; rule fallback emitted because PyTorch training was unavailable",
            "fallback_used": True,
            "fallback_reason": str(exc),
        }
        return pd.Series(scores, index=zone_time.index, name="be_sthgt_score"), meta


def train_lambdarank(zone_time: pd.DataFrame, model_dir: Path) -> tuple[pd.Series, dict[str, Any]]:
    features = zone_time[FEATURE_COLUMNS].fillna(0.0).astype("float32")
    label = zone_time["target_pfdi"].fillna(zone_time["observed_pfdi"])
    fallback = _normalise(
        (
            0.45 * zone_time["observed_pfdi"].fillna(0)
            + 0.30 * zone_time["blindspot_risk"].fillna(0)
            + 0.25 * zone_time["recurrence"].fillna(0) * 100
        ).to_numpy()
    ) * 100
    try:
        import lightgbm as lgb

        train, _, _ = _chronological_split(zone_time)
        train_x = features.loc[train.index]
        train_y = pd.qcut(label.loc[train.index].rank(method="first"), q=5, labels=False, duplicates="drop")
        group = train.groupby(["police_station", "window_start"], dropna=False).size().to_list()
        ranker = lgb.LGBMRanker(
            objective="lambdarank",
            metric="ndcg",
            n_estimators=80,
            learning_rate=0.05,
            num_leaves=31,
            random_state=42,
        )
        ranker.fit(train_x, train_y, group=group)
        scores = _normalise(ranker.predict(features)) * 100
        ranker.booster_.save_model(str(model_dir / "ranker_lgbm.txt"))
        return pd.Series(scores, index=zone_time.index, name="lambdarank_score"), {
            "model": "LightGBM LambdaRank",
            "fallback_used": False,
        }
    except Exception as exc:
        return pd.Series(fallback, index=zone_time.index, name="lambdarank_score"), {
            "model": "LightGBM LambdaRank",
            "fallback_used": True,
            "fallback_reason": str(exc),
        }


def train_and_score(zone_time: pd.DataFrame, model_dir: Path, metrics_dir: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    model_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    scored = zone_time.copy()
    scored["target_pfdi"] = scored.groupby("zone_id")["observed_pfdi"].shift(-1).fillna(scored["observed_pfdi"])
    be_scores, be_meta = train_besthgt(scored, model_dir)
    lgb_scores, lgb_meta = train_lambdarank(scored, model_dir)
    scored["be_sthgt_score"] = be_scores
    scored["lambdarank_score"] = lgb_scores
    scored["rule_blindspot_score"] = _normalise(scored["blindspot_risk"].fillna(0).to_numpy()) * 100
    scored["final_risk_score"] = (
        0.65 * scored["be_sthgt_score"]
        + 0.25 * scored["lambdarank_score"]
        + 0.10 * scored["rule_blindspot_score"]
    ).clip(0, 100)
    scored["hotspot_probability"] = (scored["observed_pfdi"] / 100).clip(0, 1)
    scored["q90_pfdi"] = scored.groupby("zone_id")["observed_pfdi"].transform(lambda s: s.rolling(8, min_periods=1).quantile(0.90))
    _, valid, test = _chronological_split(scored)
    metrics = {
        "baseline": _rank_metrics(test.assign(baseline_score=test["observed_pfdi"]), "baseline_score"),
        "be_sthgt": _rank_metrics(test, "be_sthgt_score"),
        "lightgbm_lambdarank": _rank_metrics(test, "lambdarank_score"),
        "ensemble": _rank_metrics(test, "final_risk_score"),
        "model_metadata": {"be_sthgt": be_meta, "lightgbm": lgb_meta, "validation_rows": len(valid), "test_rows": len(test)},
    }
    (metrics_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (model_dir / "model_metadata.json").write_text(json.dumps(metrics["model_metadata"], indent=2), encoding="utf-8")
    (metrics_dir / "model_card.md").write_text(
        "# CurbFlow AI Model Card\n\n"
        "CurbFlow uses the Theme 1 police violation CSV only. It treats violation rows as enforcement-visibility observations, not complete illegal-parking ground truth.\n\n"
        "The chronological split prevents future leakage. Evening low-count periods are interpreted as low evidence and elevated audit uncertainty, not proof of low parking risk.\n\n"
        "The ensemble score combines BE-STHGT, LightGBM LambdaRank, and a rule blindspot prior. If optional ML libraries are unavailable, the pipeline records a fallback reason in model metadata.\n",
        encoding="utf-8",
    )
    return scored, metrics
