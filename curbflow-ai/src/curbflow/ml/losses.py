"""BE-STHGT multitask losses for observed counts, PFDI, hotspots, and ranking."""

from __future__ import annotations

from dataclasses import dataclass, field

import torch
from torch import nn
from torch.nn import functional as F


class NegativeBinomialObservedCountLoss(nn.Module):
    """Negative binomial loss parameterized by mean and dispersion."""

    def forward(
        self,
        count_mu: torch.Tensor,
        count_theta: torch.Tensor,
        target_count: torch.Tensor,
    ) -> torch.Tensor:
        mu = count_mu.clamp_min(1e-6)
        theta = count_theta.clamp_min(1e-6)
        target = target_count.float().clamp_min(0.0)
        log_prob = (
            torch.lgamma(target + theta)
            - torch.lgamma(theta)
            - torch.lgamma(target + 1.0)
            + theta * (torch.log(theta) - torch.log(theta + mu))
            + target * (torch.log(mu) - torch.log(theta + mu))
        )
        return -log_prob.mean()


class SmoothL1PFDILoss(nn.Module):
    """Smooth L1 loss for predicted PFDI."""

    def forward(self, pred_pfdi: torch.Tensor, target_pfdi: torch.Tensor) -> torch.Tensor:
        return F.smooth_l1_loss(pred_pfdi, target_pfdi.float())


class FocalHotspotLoss(nn.Module):
    """Binary focal loss for hotspot probabilities."""

    def __init__(self, gamma: float = 2.0, eps: float = 1e-6) -> None:
        super().__init__()
        self.gamma = gamma
        self.eps = eps

    def forward(self, hotspot_prob: torch.Tensor, target_hotspot: torch.Tensor) -> torch.Tensor:
        target = target_hotspot.float()
        prob = hotspot_prob.clamp(self.eps, 1.0 - self.eps)
        p_t = torch.where(target.eq(1.0), prob, 1.0 - prob)
        return (-(1.0 - p_t).pow(self.gamma) * torch.log(p_t)).mean()


class PairwiseStationRankLoss(nn.Module):
    """Pairwise logistic ranking loss within station-window groups."""

    def forward(
        self,
        rank_score: torch.Tensor,
        relevance: torch.Tensor,
        rank_groups: torch.Tensor,
    ) -> torch.Tensor:
        scores = rank_score.reshape(-1)
        labels = relevance.reshape(-1).float()
        groups = rank_groups.reshape(-1)
        pair_losses = []
        for group in groups.unique():
            mask = groups.eq(group)
            group_scores = scores[mask]
            group_labels = labels[mask]
            if group_scores.numel() < 2 or group_labels.max() == group_labels.min():
                continue
            pos_idx, neg_idx = torch.where(group_labels[:, None] > group_labels[None, :])
            if pos_idx.numel() == 0:
                continue
            diff = group_scores[pos_idx] - group_scores[neg_idx]
            pair_losses.append(F.softplus(-diff))
        if not pair_losses:
            return scores.sum() * 0.0
        return torch.cat(pair_losses).mean()


class PinballQ90Loss(nn.Module):
    """Pinball loss for q=0.90 PFDI prediction."""

    def __init__(self, quantile: float = 0.90) -> None:
        super().__init__()
        self.quantile = quantile

    def forward(self, q90_pfdi: torch.Tensor, target_pfdi: torch.Tensor) -> torch.Tensor:
        error = target_pfdi.float() - q90_pfdi
        return torch.maximum(
            self.quantile * error,
            (self.quantile - 1.0) * error,
        ).mean()


class ExposureConsistencyLoss(nn.Module):
    """Weakly penalize zero counts under low exposure via zero-window weights."""

    def forward(
        self,
        count_mu: torch.Tensor,
        target_count: torch.Tensor,
        zero_weight_next: torch.Tensor,
    ) -> torch.Tensor:
        zero_mask = target_count.float().le(0.0)
        if not zero_mask.any():
            return count_mu.sum() * 0.0
        weights = zero_weight_next.float().clamp(0.0, 1.0)
        penalty = count_mu.clamp_min(0.0).pow(2) * weights
        return penalty[zero_mask].mean()


class SpatialSmoothnessLoss(nn.Module):
    """Graph smoothness penalty over geographic adjacency."""

    def forward(self, latent_risk: torch.Tensor, A_geo: torch.Tensor) -> torch.Tensor:
        adjacency = A_geo.to(device=latent_risk.device, dtype=latent_risk.dtype)
        if adjacency.dim() != 2:
            raise ValueError("A_geo must be [N, N].")
        diff = latent_risk.unsqueeze(-1) - latent_risk.unsqueeze(-2)
        weighted = adjacency.unsqueeze(0) * diff.pow(2)
        denominator = adjacency.sum().clamp_min(1.0) * latent_risk.shape[0]
        return weighted.sum() / denominator


@dataclass(frozen=True)
class LossWeights:
    """Default BE-STHGT multitask loss weights."""

    count: float = 0.22
    pfdi: float = 0.20
    hotspot: float = 0.16
    rank: float = 0.16
    q90: float = 0.10
    exposure_consistency: float = 0.08
    spatial_smoothness: float = 0.08


@dataclass
class TotalLossOutput:
    """Total loss plus component logging dictionary."""

    loss: torch.Tensor
    components: dict[str, torch.Tensor] = field(default_factory=dict)


class BESTHGTTotalLoss(nn.Module):
    """Weighted total loss for BE-STHGT outputs."""

    def __init__(self, weights: LossWeights = LossWeights()) -> None:
        super().__init__()
        self.weights = weights
        self.count_loss = NegativeBinomialObservedCountLoss()
        self.pfdi_loss = SmoothL1PFDILoss()
        self.hotspot_loss = FocalHotspotLoss()
        self.rank_loss = PairwiseStationRankLoss()
        self.q90_loss = PinballQ90Loss()
        self.exposure_loss = ExposureConsistencyLoss()
        self.spatial_loss = SpatialSmoothnessLoss()

    def forward(
        self,
        outputs: dict[str, torch.Tensor],
        targets: dict[str, torch.Tensor],
        *,
        rank_groups: torch.Tensor,
        A_geo: torch.Tensor,
    ) -> TotalLossOutput:
        components = {
            "count": self.count_loss(
                outputs["count_mu"],
                outputs["count_theta"],
                targets["y_count"],
            ),
            "pfdi": self.pfdi_loss(outputs["pred_pfdi"], targets["y_pfdi"]),
            "hotspot": self.hotspot_loss(outputs["hotspot_prob"], targets["y_hotspot"]),
            "rank": self.rank_loss(
                outputs["rank_score"],
                targets["y_rank_relevance"],
                rank_groups,
            ),
            "q90": self.q90_loss(outputs["q90_pfdi"], targets["y_q90_pfdi"]),
            "exposure_consistency": self.exposure_loss(
                outputs["count_mu"],
                targets["y_count"],
                targets["zero_weight_next"],
            ),
            "spatial_smoothness": self.spatial_loss(outputs["latent_risk"], A_geo),
        }
        total = (
            self.weights.count * components["count"]
            + self.weights.pfdi * components["pfdi"]
            + self.weights.hotspot * components["hotspot"]
            + self.weights.rank * components["rank"]
            + self.weights.q90 * components["q90"]
            + self.weights.exposure_consistency * components["exposure_consistency"]
            + self.weights.spatial_smoothness * components["spatial_smoothness"]
        )
        return TotalLossOutput(loss=total, components=components)
