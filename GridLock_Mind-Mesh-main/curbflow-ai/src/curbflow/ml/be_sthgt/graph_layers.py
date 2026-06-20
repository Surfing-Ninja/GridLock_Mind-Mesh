"""Multi-relation graph attention and adaptive adjacency layers."""

from __future__ import annotations

import torch
from torch import nn


DEFAULT_RELATIONS = ("geo", "station", "pattern", "vehicle", "patrol")


def normalize_adjacency(adjacency: torch.Tensor, *, add_self_loops: bool = True) -> torch.Tensor:
    """Row-normalize an adjacency matrix with optional self loops."""

    if adjacency.dim() != 2 or adjacency.shape[0] != adjacency.shape[1]:
        raise ValueError("Adjacency must be a square [N, N] tensor.")
    adjacency = adjacency.float()
    if add_self_loops:
        adjacency = adjacency + torch.eye(
            adjacency.shape[0],
            device=adjacency.device,
            dtype=adjacency.dtype,
        )
    degree = adjacency.sum(dim=-1, keepdim=True).clamp_min(1e-6)
    return adjacency / degree


class AdaptiveAdjacency(nn.Module):
    """Learned adaptive adjacency from trainable node embeddings."""

    def __init__(self, num_zones: int, embedding_dim: int = 16) -> None:
        super().__init__()
        self.left_embedding = nn.Parameter(torch.randn(num_zones, embedding_dim) * 0.02)
        self.right_embedding = nn.Parameter(torch.randn(embedding_dim, num_zones) * 0.02)

    def forward(self) -> torch.Tensor:
        logits = torch.relu(self.left_embedding @ self.right_embedding)
        return torch.softmax(logits, dim=-1)


class MultiRelationGraphBlock(nn.Module):
    """Graph block over fixed relations plus learned adaptive adjacency."""

    def __init__(
        self,
        hidden_dim: int,
        num_zones: int,
        relation_names: tuple[str, ...] = DEFAULT_RELATIONS,
        dropout: float = 0.15,
        adaptive_embedding_dim: int = 16,
    ) -> None:
        super().__init__()
        self.relation_names = relation_names
        self.all_relation_names = relation_names + ("adaptive",)
        self.relation_linears = nn.ModuleDict(
            {name: nn.Linear(hidden_dim, hidden_dim, bias=False) for name in self.all_relation_names}
        )
        self.adaptive_adjacency = AdaptiveAdjacency(num_zones, adaptive_embedding_dim)
        self.relation_logits = nn.Parameter(torch.zeros(len(self.all_relation_names)))
        self.concat_projection = nn.Linear(hidden_dim * len(self.all_relation_names), hidden_dim)
        self.dropout = nn.Dropout(dropout)
        self.layer_norm = nn.LayerNorm(hidden_dim)

    def _relation_output(
        self,
        hidden: torch.Tensor,
        adjacency: torch.Tensor,
        relation_name: str,
    ) -> torch.Tensor:
        normalized = normalize_adjacency(adjacency).to(device=hidden.device, dtype=hidden.dtype)
        propagated = torch.einsum("ij,bljh->blih", normalized, hidden)
        return self.relation_linears[relation_name](propagated)

    def forward(self, hidden: torch.Tensor, adjacencies: dict[str, torch.Tensor]) -> torch.Tensor:
        """Apply multi-relation graph propagation to [B, L, N, H]."""

        relation_outputs = []
        for relation_name in self.relation_names:
            if relation_name not in adjacencies:
                raise ValueError(f"Missing adjacency relation: {relation_name}")
            relation_outputs.append(
                self._relation_output(hidden, adjacencies[relation_name], relation_name)
            )

        adaptive = self.adaptive_adjacency().to(device=hidden.device, dtype=hidden.dtype)
        relation_outputs.append(self._relation_output(hidden, adaptive, "adaptive"))

        stacked = torch.stack(relation_outputs, dim=0)
        gates = torch.softmax(self.relation_logits, dim=0).view(-1, 1, 1, 1, 1)
        gated = (stacked * gates).sum(dim=0)
        concatenated = torch.cat(relation_outputs, dim=-1)
        fused = gated + self.concat_projection(concatenated)
        return self.layer_norm(hidden + self.dropout(fused))
