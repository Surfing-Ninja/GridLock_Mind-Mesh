"""Generate BE-STHGT, ranker, and ensemble predictions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from curbflow.features.training_table import MODEL_TRAINING_TABLE_PATH
from curbflow.graph.build_hetero_graph import ADJACENCY_OUTPUT_DIR, GRAPH_FEATURES_PATH
from curbflow.ml.be_sthgt.inference import load_or_generate_be_sthgt_predictions
from curbflow.ml.be_sthgt.trainer import DEEP_PREDICTIONS_PATH, MODEL_OUTPUT_PATH
from curbflow.ml.ranker.ensemble import PREDICTIONS_PATH, write_ensemble_predictions
from curbflow.ml.ranker.lgbm_ranker import RANKER_METRICS_PATH, RANKER_MODEL_PATH


def main() -> None:
    """Generate final ensemble predictions."""

    parser = argparse.ArgumentParser(description="Generate CurbFlow ensemble predictions.")
    parser.add_argument("--input", default=str(MODEL_TRAINING_TABLE_PATH), help="Model feature table parquet.")
    parser.add_argument("--output", default=str(PREDICTIONS_PATH), help="Final prediction parquet path.")
    parser.add_argument("--graph-features", default=str(GRAPH_FEATURES_PATH))
    parser.add_argument("--deep-predictions", default=str(DEEP_PREDICTIONS_PATH))
    parser.add_argument("--be-model", default=str(MODEL_OUTPUT_PATH))
    parser.add_argument("--adjacency-dir", default=str(ADJACENCY_OUTPUT_DIR))
    parser.add_argument("--ranker-model", default=str(RANKER_MODEL_PATH))
    parser.add_argument("--ranker-metrics", default=str(RANKER_METRICS_PATH))
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument(
        "--device",
        choices=["cpu", "cuda", "mps"],
        default=None,
        help="Override BE-STHGT inference device.",
    )
    parser.add_argument(
        "--force-deep",
        action="store_true",
        help="Regenerate BE-STHGT deep predictions even if the parquet exists.",
    )
    parser.add_argument(
        "--skip-deep-generation",
        action="store_true",
        help="Use existing deep predictions only; do not run BE-STHGT checkpoint inference.",
    )
    parser.add_argument(
        "--no-graph-features",
        action="store_true",
        help="Do not merge graph features before ranker/ensemble scoring.",
    )
    args = parser.parse_args()

    deep_predictions_path: str | None = args.deep_predictions
    try:
        if not args.skip_deep_generation:
            deep_predictions = load_or_generate_be_sthgt_predictions(
                training_table_path=args.input,
                model_path=args.be_model,
                adjacency_dir=args.adjacency_dir,
                predictions_path=args.deep_predictions,
                batch_size=args.batch_size,
                device=args.device,
                force=args.force_deep,
            )
            if deep_predictions is None and not Path(args.deep_predictions).exists():
                deep_predictions_path = None
        elif not Path(args.deep_predictions).exists():
            deep_predictions_path = None

        predictions = write_ensemble_predictions(
            args.input,
            output_path=args.output,
            graph_features_path=None if args.no_graph_features else args.graph_features,
            deep_predictions_path=deep_predictions_path,
            ranker_model_path=args.ranker_model,
            ranker_metrics_path=args.ranker_metrics,
        )
    except Exception as exc:
        raise SystemExit(f"Prediction generation failed: {exc}") from exc

    print(f"Wrote {len(predictions):,} ensemble prediction rows to {args.output}")


if __name__ == "__main__":
    main()
