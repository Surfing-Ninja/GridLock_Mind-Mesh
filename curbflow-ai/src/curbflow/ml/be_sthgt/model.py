"""Bias-Exposure Spatio-Temporal Heterogeneous Graph Transformer model."""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn

from curbflow.ml.be_sthgt.graph_layers import DEFAULT_RELATIONS, MultiRelationGraphBlock
from curbflow.ml.be_sthgt.heads import BEPredictionHeads
from curbflow.ml.be_sthgt.temporal_layers import ZoneTemporalTransformer


@dataclass(frozen=True)
class BESTHGTConfig:
    """Configuration for Bias-Exposure Spatio-Temporal Heterogeneous Graph Transformer."""

    input_dim: int
    num_zones: int
    hidden_dim: int = 128
    graph_layers: int = 2
    temporal_layers: int = 3
    attention_heads: int = 4
    dropout: float = 0.15
    lookback_windows: int = 56
    static_feature_dim: int | None = None
    relation_names: tuple[str, ...] = DEFAULT_RELATIONS


class BESTHGT(nn.Module):
    """Bias-Exposure Spatio-Temporal Heterogeneous Graph Transformer."""

    def __init__(self, config: BESTHGTConfig) -> None:
        super().__init__()
        self.config = config
        self.relation_names = config.relation_names
        self.feature_projection = nn.Linear(config.input_dim, config.hidden_dim)
        self.input_norm = nn.LayerNorm(config.hidden_dim)
        self.graph_blocks = nn.ModuleList(
            [
                MultiRelationGraphBlock(
                    hidden_dim=config.hidden_dim,
                    num_zones=config.num_zones,
                    relation_names=config.relation_names,
                    dropout=config.dropout,
                )
                for _ in range(config.graph_layers)
            ]
        )
        self.temporal_encoder = ZoneTemporalTransformer(
            hidden_dim=config.hidden_dim,
            n_layers=config.temporal_layers,
            n_heads=config.attention_heads,
            dropout=config.dropout,
            max_len=max(config.lookback_windows, 512),
        )
        self.static_projection = (
            nn.Linear(config.static_feature_dim, config.hidden_dim)
            if config.static_feature_dim is not None and config.static_feature_dim > 0
            else None
        )
        self.heads = BEPredictionHeads(config.hidden_dim, dropout=config.dropout)

    def _prepare_adjacencies(
        self,
        adjacencies: dict[str, torch.Tensor] | list[torch.Tensor] | tuple[torch.Tensor, ...],
        *,
        device: torch.device,
    ) -> dict[str, torch.Tensor]:
        """Normalize accepted adjacency input forms into a relation dict."""

        if isinstance(adjacencies, dict):
            relation_adjacencies = {name: adjacencies[name] for name in self.relation_names}
        else:
            if len(adjacencies) != len(self.relation_names):
                raise ValueError(
                    f"Expected {len(self.relation_names)} adjacency matrices, got {len(adjacencies)}."
                )
            relation_adjacencies = dict(zip(self.relation_names, adjacencies, strict=True))
        return {name: adjacency.to(device=device) for name, adjacency in relation_adjacencies.items()}

    def _add_static_features(
        self,
        hidden: torch.Tensor,
        static_zone_features: torch.Tensor | None,
    ) -> torch.Tensor:
        """Add optional static zone feature projection to [B, N, H] hidden states."""

        if static_zone_features is None or self.static_projection is None:
            return hidden
        static = static_zone_features.to(device=hidden.device, dtype=hidden.dtype)
        if static.dim() == 2:
            static = static.unsqueeze(0).expand(hidden.shape[0], -1, -1)
        projected = self.static_projection(static)
        return hidden + projected

    def forward(
        self,
        X: torch.Tensor,
        adjacencies: dict[str, torch.Tensor] | list[torch.Tensor] | tuple[torch.Tensor, ...],
        *,
        exposure_next: torch.Tensor | None = None,
        static_zone_features: torch.Tensor | None = None,
    ) -> dict[str, torch.Tensor]:
        """Run BE-STHGT.

        Args:
            X: Tensor shaped [B, L, N, F].
            adjacencies: Five active-zone adjacency matrices for geo, station, pattern,
                vehicle, and patrol relations.
            exposure_next: Next-window exposure tensor [B, N]. The observed count intensity
                is explicitly modeled as latent risk multiplied by this exposure.
            static_zone_features: Optional static zone features shaped [N, S] or [B, N, S].
        """

        if X.dim() != 4:
            raise ValueError("X must be shaped [B, L, N, F].")
        if X.shape[2] != self.config.num_zones:
            raise ValueError(f"Expected {self.config.num_zones} zones, got {X.shape[2]}.")

        relation_adjacencies = self._prepare_adjacencies(adjacencies, device=X.device)
        hidden = self.input_norm(self.feature_projection(X))
        for graph_block in self.graph_blocks:
            hidden = graph_block(hidden, relation_adjacencies)
        zone_hidden = self.temporal_encoder(hidden)
        zone_hidden = self._add_static_features(zone_hidden, static_zone_features)
        return self.heads(zone_hidden, exposure_next=exposure_next)
