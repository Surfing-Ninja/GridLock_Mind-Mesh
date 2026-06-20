"""Tests for BE-STHGT losses and metrics."""

from __future__ import annotations

import torch

from curbflow.ml.losses import (
    BESTHGTTotalLoss,
    ExposureConsistencyLoss,
    FocalHotspotLoss,
    NegativeBinomialObservedCountLoss,
    PairwiseStationRankLoss,
    PinballQ90Loss,
    SmoothL1PFDILoss,
    SpatialSmoothnessLoss,
)
from curbflow.ml.metrics import (
    hotspot_auc,
    mae_pfdi,
    ndcg_at_k,
    precision_at_k,
    station_wise_precision_at_k,
    wape_count,
)


def test_negative_binomial_observed_count_loss_is_finite() -> None:
    loss = NegativeBinomialObservedCountLoss()
    value = loss(
        torch.tensor([[2.0, 3.0]]),
        torch.tensor([[1.5, 2.0]]),
        torch.tensor([[1.0, 4.0]]),
    )

    assert torch.isfinite(value)
    assert value > 0


def test_pfdi_hotspot_and_pinball_losses_are_finite() -> None:
    pfdi = SmoothL1PFDILoss()(torch.tensor([[10.0, 20.0]]), torch.tensor([[12.0, 18.0]]))
    hotspot = FocalHotspotLoss()(torch.tensor([[0.8, 0.2]]), torch.tensor([[1.0, 0.0]]))
    q90 = PinballQ90Loss()(torch.tensor([[15.0, 25.0]]), torch.tensor([[20.0, 10.0]]))

    assert torch.isfinite(pfdi)
    assert torch.isfinite(hotspot)
    assert torch.isfinite(q90)
    assert q90 > 0


def test_pairwise_station_rank_loss_prefers_ordered_scores() -> None:
    rank_loss = PairwiseStationRankLoss()
    good = rank_loss(
        torch.tensor([[3.0, 2.0, 1.0]]),
        torch.tensor([[3, 2, 0]]),
        torch.tensor([[1, 1, 1]]),
    )
    bad = rank_loss(
        torch.tensor([[1.0, 2.0, 3.0]]),
        torch.tensor([[3, 2, 0]]),
        torch.tensor([[1, 1, 1]]),
    )

    assert good < bad


def test_exposure_consistency_uses_zero_weight_for_zero_counts() -> None:
    loss = ExposureConsistencyLoss()
    low_weight = loss(
        torch.tensor([[10.0, 10.0]]),
        torch.tensor([[0.0, 0.0]]),
        torch.tensor([[0.1, 0.1]]),
    )
    high_weight = loss(
        torch.tensor([[10.0, 10.0]]),
        torch.tensor([[0.0, 0.0]]),
        torch.tensor([[1.0, 1.0]]),
    )

    assert low_weight < high_weight


def test_spatial_smoothness_penalizes_neighbor_risk_difference() -> None:
    loss = SpatialSmoothnessLoss()
    adjacency = torch.tensor([[0.0, 1.0], [1.0, 0.0]])
    smooth = loss(torch.tensor([[1.0, 1.0]]), adjacency)
    rough = loss(torch.tensor([[1.0, 5.0]]), adjacency)

    assert smooth == 0
    assert rough > smooth


def test_total_loss_combines_components() -> None:
    outputs = {
        "count_mu": torch.tensor([[2.0, 3.0]]),
        "count_theta": torch.tensor([[1.0, 1.0]]),
        "pred_pfdi": torch.tensor([[20.0, 30.0]]),
        "hotspot_prob": torch.tensor([[0.7, 0.2]]),
        "rank_score": torch.tensor([[2.0, 1.0]]),
        "q90_pfdi": torch.tensor([[25.0, 35.0]]),
        "latent_risk": torch.tensor([[2.0, 4.0]]),
    }
    targets = {
        "y_count": torch.tensor([[2.0, 4.0]]),
        "y_pfdi": torch.tensor([[22.0, 28.0]]),
        "y_hotspot": torch.tensor([[1.0, 0.0]]),
        "y_rank_relevance": torch.tensor([[2, 0]]),
        "y_q90_pfdi": torch.tensor([[24.0, 36.0]]),
        "zero_weight_next": torch.tensor([[1.0, 1.0]]),
    }
    total = BESTHGTTotalLoss()(
        outputs,
        targets,
        rank_groups=torch.tensor([[1, 1]]),
        A_geo=torch.tensor([[0.0, 1.0], [1.0, 0.0]]),
    )

    assert torch.isfinite(total.loss)
    assert set(total.components) == {
        "count",
        "pfdi",
        "hotspot",
        "rank",
        "q90",
        "exposure_consistency",
        "spatial_smoothness",
    }


def test_metrics_compute_expected_ranges() -> None:
    scores = torch.tensor([0.9, 0.8, 0.1, 0.2])
    hotspot = torch.tensor([1, 0, 0, 1])
    relevance = torch.tensor([3, 1, 0, 2])
    stations = torch.tensor([1, 1, 2, 2])

    assert precision_at_k(scores, hotspot, k=2) == 0.5
    assert 0.0 <= ndcg_at_k(scores, relevance, k=3) <= 1.0
    assert 0.0 <= station_wise_precision_at_k(scores, hotspot, stations, k=1) <= 1.0
    assert mae_pfdi(torch.tensor([1.0, 3.0]), torch.tensor([2.0, 1.0])) == 1.5
    assert wape_count(torch.tensor([2.0, 4.0]), torch.tensor([1.0, 5.0])) > 0
    assert hotspot_auc(scores, hotspot) is not None
    assert hotspot_auc(scores, torch.tensor([1, 1, 1, 1])) is None
