"""Temporal transformer layers for zone-time sequences."""

from __future__ import annotations

import torch
from torch import nn


class ZoneTemporalTransformer(nn.Module):
    """Transformer encoder over lookback windows for each zone independently."""

    def __init__(
        self,
        hidden_dim: int = 128,
        n_layers: int = 3,
        n_heads: int = 4,
        dropout: float = 0.15,
        max_len: int = 512,
    ) -> None:
        super().__init__()
        self.position_embedding = nn.Parameter(torch.randn(max_len, hidden_dim) * 0.02)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=n_heads,
            dim_feedforward=hidden_dim * 4,
            dropout=dropout,
            activation="gelu",
            batch_first=True,
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)
        self.layer_norm = nn.LayerNorm(hidden_dim)

    def forward(self, hidden: torch.Tensor) -> torch.Tensor:
        """Encode [B, L, N, H] and return the latest state [B, N, H]."""

        batch_size, lookback, num_zones, hidden_dim = hidden.shape
        if lookback > self.position_embedding.shape[0]:
            raise ValueError("Lookback exceeds max positional embedding length.")
        temporal = hidden.permute(0, 2, 1, 3).reshape(batch_size * num_zones, lookback, hidden_dim)
        temporal = temporal + self.position_embedding[:lookback].unsqueeze(0)
        encoded = self.encoder(temporal)
        latest = encoded[:, -1, :].reshape(batch_size, num_zones, hidden_dim)
        return self.layer_norm(latest)
