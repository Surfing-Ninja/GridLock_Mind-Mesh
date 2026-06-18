"""Prediction heads for latent risk, observed counts, PFDI, hotspots, and ranking."""

from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F


class BEPredictionHeads(nn.Module):
    """Multitask prediction heads for bias-exposure traffic risk modeling."""

    def __init__(self, hidden_dim: int, dropout: float = 0.15) -> None:
        super().__init__()
        self.shared = nn.Sequential(
            nn.LayerNorm(hidden_dim),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
        )
        self.latent_risk_head = nn.Linear(hidden_dim, 1)
        self.count_dispersion_head = nn.Linear(hidden_dim, 1)
        self.pfdi_head = nn.Linear(hidden_dim, 1)
        self.hotspot_head = nn.Linear(hidden_dim, 1)
        self.q90_head = nn.Linear(hidden_dim, 1)
        self.rank_head = nn.Linear(hidden_dim, 1)
        self.blindspot_head = nn.Linear(hidden_dim, 1)

    def forward(self, hidden: torch.Tensor, exposure_next: torch.Tensor | None = None) -> dict[str, torch.Tensor]:
        """Return all BE-STHGT prediction heads for [B, N, H] hidden states."""

        features = self.shared(hidden)
        latent_risk = F.softplus(self.latent_risk_head(features)).squeeze(-1) + 1e-6
        if exposure_next is None:
            exposure = torch.ones_like(latent_risk)
        else:
            exposure = exposure_next.to(device=latent_risk.device, dtype=latent_risk.dtype)
        exposure = exposure.clamp(0.05, 1.0)

        return {
            "latent_risk": latent_risk,
            "count_mu": latent_risk * exposure,
            "count_theta": F.softplus(self.count_dispersion_head(features)).squeeze(-1) + 1e-6,
            "pred_pfdi": 100.0 * torch.sigmoid(self.pfdi_head(features)).squeeze(-1),
            "hotspot_prob": torch.sigmoid(self.hotspot_head(features)).squeeze(-1),
            "q90_pfdi": 100.0 * torch.sigmoid(self.q90_head(features)).squeeze(-1),
            "rank_score": self.rank_head(features).squeeze(-1),
            "blindspot_score": 100.0 * torch.sigmoid(self.blindspot_head(features)).squeeze(-1),
        }
