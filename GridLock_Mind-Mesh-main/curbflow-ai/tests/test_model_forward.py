"""Tests for BE-STHGT model forward pass shape contracts."""

from __future__ import annotations

import torch

from curbflow.ml.be_sthgt.model import BESTHGT, BESTHGTConfig


def _adjacency(num_zones: int) -> torch.Tensor:
    adjacency = torch.eye(num_zones)
    for index in range(num_zones - 1):
        adjacency[index, index + 1] = 1.0
        adjacency[index + 1, index] = 1.0
    return adjacency


def test_be_sthgt_forward_shapes_and_exposure_link() -> None:
    torch.manual_seed(7)
    batch_size = 2
    lookback = 5
    num_zones = 4
    num_features = 6
    static_dim = 3
    config = BESTHGTConfig(
        input_dim=num_features,
        num_zones=num_zones,
        hidden_dim=32,
        graph_layers=2,
        temporal_layers=1,
        attention_heads=4,
        dropout=0.0,
        lookback_windows=lookback,
        static_feature_dim=static_dim,
    )
    model = BESTHGT(config)
    X = torch.randn(batch_size, lookback, num_zones, num_features)
    exposure_next = torch.tensor(
        [
            [1.0, 0.5, 0.1, 0.0],
            [0.8, 0.3, 0.2, 0.05],
        ],
        dtype=torch.float32,
    )
    adjacencies = {
        "geo": _adjacency(num_zones),
        "station": torch.eye(num_zones),
        "pattern": _adjacency(num_zones),
        "vehicle": torch.eye(num_zones),
        "patrol": _adjacency(num_zones),
    }
    static_zone_features = torch.randn(num_zones, static_dim)

    outputs = model(
        X,
        adjacencies,
        exposure_next=exposure_next,
        static_zone_features=static_zone_features,
    )

    expected_shape = (batch_size, num_zones)
    assert outputs["latent_risk"].shape == expected_shape
    assert outputs["count_mu"].shape == expected_shape
    assert outputs["count_theta"].shape == expected_shape
    assert outputs["pred_pfdi"].shape == expected_shape
    assert outputs["hotspot_prob"].shape == expected_shape
    assert outputs["q90_pfdi"].shape == expected_shape
    assert outputs["rank_score"].shape == expected_shape
    assert torch.all(outputs["count_theta"] > 0)
    assert torch.all((outputs["pred_pfdi"] >= 0) & (outputs["pred_pfdi"] <= 100))
    assert torch.all((outputs["hotspot_prob"] >= 0) & (outputs["hotspot_prob"] <= 1))
    assert torch.allclose(
        outputs["count_mu"],
        outputs["latent_risk"] * exposure_next.clamp(0.05, 1.0),
        atol=1e-6,
    )
