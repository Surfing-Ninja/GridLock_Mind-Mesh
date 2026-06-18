"""Run the complete CurbFlow AI pipeline from raw CSV to demo database."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from curbflow.data.audit import (
    BIAS_AUDIT_REPORT_PATH,
    COVERAGE_AUDIT_PATH,
    DATA_QUALITY_REPORT_PATH,
    EDA_SUMMARY_PATH,
    AuditOutputPaths,
    run_data_audit,
)
from curbflow.data.clean import preprocess_violations
from curbflow.data.schema import CLEAN_PARQUET_PATH, RAW_CSV_PATH
from curbflow.db.duckdb_init import APP_DB_PATH, initialize_duckdb
from curbflow.exposure.blindspot import add_blindspot_risk_features
from curbflow.exposure.coverage_gap import COVERAGE_GAP_PATH, compute_coverage_gap
from curbflow.exposure.visibility import (
    ZONE_TIME_EXPOSURE_PATH,
    build_zone_time_visibility_inputs,
    compute_enforcement_visibility,
)
from curbflow.features.aggregate_zone_time import ZONE_TIME_FEATURES_PATH, write_zone_time_features
from curbflow.features.novel_features import (
    JUNCTION_BASINS_PATH,
    PATROL_MYOPIA_PATH,
    REPEAT_VEHICLE_ZONE_TIME_PATH,
    add_evidence_quality_features,
    add_hidden_junction_basin_features,
    add_place_type_and_road_corridor_features,
    add_repeat_vehicle_features,
    write_junction_basin_table,
    write_patrol_myopia_table,
    write_repeat_vehicle_zone_time_table,
)
from curbflow.features.training_table import MODEL_TRAINING_TABLE_PATH, write_model_training_table
from curbflow.graph.build_hetero_graph import (
    ADJACENCY_OUTPUT_DIR,
    GRAPH_EDGES_PATH,
    GRAPH_FEATURES_PATH,
    run_graph_build,
)
from curbflow.graph.build_patrol_graph import (
    PATROL_GRAPH_EDGES_PATH,
    PATROL_GRAPH_FEATURES_PATH,
    run_patrol_graph_build,
)
from curbflow.ml.be_sthgt.trainer import (
    DEEP_METRICS_PATH,
    DEEP_PREDICTIONS_PATH,
    MODEL_METADATA_PATH,
    MODEL_OUTPUT_PATH,
    train_be_sthgt,
)
from curbflow.ml.ranker.ensemble import PREDICTIONS_PATH, write_ensemble_predictions
from curbflow.ml.ranker.lgbm_ranker import (
    FEATURE_IMPORTANCE_PATH,
    RANKER_METRICS_PATH,
    RANKER_MODEL_PATH,
    train_lgbm_ranker,
)
from curbflow.planner.optimizer import RECOMMENDATIONS_PATH, write_recommendations
from curbflow.scoring.pfdi import ROW_SCORES_PATH, run_pfdi_scoring
from curbflow.zoning.assign_zones import ZONE_ASSIGNMENTS_PATH, run_zone_build
from curbflow.zoning.grid_zones import DEFAULT_GRID_SIZE_METERS
from curbflow.zoning.zone_geojson import ZONES_GEOJSON_PATH
from run_train_deep import _load_training_config as load_deep_training_config
from run_train_ranker import (
    _load_ranker_config as load_ranker_config,
    _with_overrides as ranker_config_with_overrides,
)


LOGGER = logging.getLogger("curbflow.full_pipeline")
DEFAULT_RECOMMENDATION_OFFICERS = 20
DEFAULT_RECOMMENDATION_TOW_UNITS = 4
DEFAULT_RECOMMENDATION_MODE = "balanced"


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )


def _output(label: str, path: str | Path) -> None:
    """Log one output artifact path."""

    artifact = Path(path)
    LOGGER.info("output %-34s %s", f"{label}:", artifact)


def _stage(name: str) -> None:
    LOGGER.info("")
    LOGGER.info("=== %s ===", name)


def _require_raw_csv(path: str | Path) -> Path:
    """Return a raw CSV path or fail with an actionable message."""

    raw_csv = Path(path)
    if not raw_csv.exists():
        raise SystemExit(
            f"Raw Theme 1 police violation CSV not found: {raw_csv}. "
            "Place the CSV at the configured path or pass --input-csv /path/to/file.csv."
        )
    if not raw_csv.is_file():
        raise SystemExit(f"Input CSV path is not a file: {raw_csv}")
    return raw_csv


def _run_preprocess(raw_csv: Path) -> pd.DataFrame:
    _stage("1. Preprocess")
    clean = preprocess_violations(raw_csv, CLEAN_PARQUET_PATH)
    LOGGER.info("cleaned rows: %s", f"{len(clean):,}")
    _output("clean parquet", CLEAN_PARQUET_PATH)
    return clean


def _run_audit(raw_csv: Path) -> None:
    _stage("2. Data audit")
    summary = run_data_audit(
        clean_parquet_path=CLEAN_PARQUET_PATH,
        raw_csv_path=raw_csv,
        output_paths=AuditOutputPaths(
            data_quality_report=DATA_QUALITY_REPORT_PATH,
            bias_audit_report=BIAS_AUDIT_REPORT_PATH,
            eda_summary=EDA_SUMMARY_PATH,
            coverage_audit=COVERAGE_AUDIT_PATH,
        ),
    )
    LOGGER.info(
        "audit rows: %s date range: %s",
        f"{int(summary.get('total_rows', 0)):,}",
        summary.get("actual_date_range"),
    )
    _output("data quality report", DATA_QUALITY_REPORT_PATH)
    _output("bias audit report", BIAS_AUDIT_REPORT_PATH)
    _output("eda summary", EDA_SUMMARY_PATH)
    _output("coverage audit", COVERAGE_AUDIT_PATH)


def _run_pfdi() -> pd.DataFrame:
    _stage("3. PFDI scoring")
    scored = run_pfdi_scoring(
        clean_parquet_path=CLEAN_PARQUET_PATH,
        output_path=ROW_SCORES_PATH,
        compute_evidence_quality=True,
    )
    LOGGER.info("scored rows: %s", f"{len(scored):,}")
    _output("row scores", ROW_SCORES_PATH)
    return scored


def _run_zones(active_zone_min_records: int) -> None:
    _stage("4. Zone build")
    summary = run_zone_build(
        input_path=ROW_SCORES_PATH,
        assignments_output_path=ZONE_ASSIGNMENTS_PATH,
        zones_geojson_output_path=ZONES_GEOJSON_PATH,
        grid_size_meters=DEFAULT_GRID_SIZE_METERS,
        active_zone_min_records=active_zone_min_records,
        bias_audit_report_path=BIAS_AUDIT_REPORT_PATH,
    )
    LOGGER.info("zone summary: %s", summary.as_dict())
    _output("zone assignments", ZONE_ASSIGNMENTS_PATH)
    _output("zones geojson", ZONES_GEOJSON_PATH)
    _output("updated bias audit report", BIAS_AUDIT_REPORT_PATH)


def _run_novel_features() -> pd.DataFrame:
    """Run novel row and aggregate feature extraction and persist artifacts."""

    _stage("5. Novel feature extraction")
    if not ZONE_ASSIGNMENTS_PATH.exists():
        raise FileNotFoundError(f"Zone assignments missing: {ZONE_ASSIGNMENTS_PATH}")

    rows = pd.read_parquet(ZONE_ASSIGNMENTS_PATH)
    if "evidence_quality_score" not in rows.columns:
        rows = add_evidence_quality_features(rows)
    LOGGER.info("evidence quality features added")

    rows = add_hidden_junction_basin_features(rows)
    junction_basins = write_junction_basin_table(rows, JUNCTION_BASINS_PATH)
    LOGGER.info("junction basin rows: %s", f"{len(junction_basins):,}")
    _output("junction basins", JUNCTION_BASINS_PATH)

    patrol_myopia = write_patrol_myopia_table(rows, PATROL_MYOPIA_PATH)
    LOGGER.info("patrol myopia station rows: %s", f"{len(patrol_myopia):,}")
    _output("patrol myopia", PATROL_MYOPIA_PATH)

    rows = add_repeat_vehicle_features(rows)
    repeat_vehicle = write_repeat_vehicle_zone_time_table(rows, REPEAT_VEHICLE_ZONE_TIME_PATH)
    LOGGER.info("repeat vehicle zone-time rows: %s", f"{len(repeat_vehicle):,}")
    _output("repeat vehicle zone-time", REPEAT_VEHICLE_ZONE_TIME_PATH)

    rows = add_place_type_and_road_corridor_features(rows)
    LOGGER.info("place-type and road-corridor row features added")

    ZONE_ASSIGNMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows.to_parquet(ZONE_ASSIGNMENTS_PATH, index=False)
    _output("enriched zone assignments", ZONE_ASSIGNMENTS_PATH)
    return rows


def _run_exposure_and_blindspot(rows: pd.DataFrame) -> None:
    _stage("6. Exposure and blindspot features")
    visibility_inputs = build_zone_time_visibility_inputs(rows)
    exposure = compute_enforcement_visibility(visibility_inputs)
    ZONE_TIME_EXPOSURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    exposure.to_parquet(ZONE_TIME_EXPOSURE_PATH, index=False)
    LOGGER.info("visibility rows: %s", f"{len(exposure):,}")
    _output("enforcement visibility", ZONE_TIME_EXPOSURE_PATH)

    coverage_gap = compute_coverage_gap(exposure)
    blindspot = add_blindspot_risk_features(coverage_gap)
    COVERAGE_GAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    blindspot.to_parquet(COVERAGE_GAP_PATH, index=False)
    LOGGER.info("coverage/blindspot rows: %s", f"{len(blindspot):,}")
    _output("coverage gap and blindspot preview", COVERAGE_GAP_PATH)


def _run_feature_build(rows: pd.DataFrame, active_zone_min_records: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    _stage("7. Zone-time feature build")
    zone_time = write_zone_time_features(rows, ZONE_TIME_FEATURES_PATH)
    training = write_model_training_table(
        zone_time,
        MODEL_TRAINING_TABLE_PATH,
        active_zone_min_records=active_zone_min_records,
    )
    LOGGER.info("zone-time rows: %s", f"{len(zone_time):,}")
    LOGGER.info("training rows: %s", f"{len(training):,}")
    _output("zone-time features", ZONE_TIME_FEATURES_PATH)
    _output("model training table", MODEL_TRAINING_TABLE_PATH)
    return zone_time, training


def _run_graph_build(active_zone_min_records: int) -> None:
    _stage("8. Graph build")
    edges, features, matrices = run_graph_build(
        ZONE_TIME_FEATURES_PATH,
        row_path=ZONE_ASSIGNMENTS_PATH,
        graph_edges_path=GRAPH_EDGES_PATH,
        graph_features_path=GRAPH_FEATURES_PATH,
        adjacency_output_dir=ADJACENCY_OUTPUT_DIR,
        active_zone_min_records=active_zone_min_records,
    )
    LOGGER.info("graph edge rows: %s", f"{len(edges):,}")
    LOGGER.info("graph feature rows: %s", f"{len(features):,}")
    _output("graph edges", GRAPH_EDGES_PATH)
    _output("graph features", GRAPH_FEATURES_PATH)
    for name, path in sorted(matrices.items()):
        _output(f"adjacency {name}", path)

    patrol_edges, patrol_features = run_patrol_graph_build(
        ZONE_ASSIGNMENTS_PATH,
        edges_output_path=PATROL_GRAPH_EDGES_PATH,
        features_output_path=PATROL_GRAPH_FEATURES_PATH,
    )
    LOGGER.info("patrol graph edge rows: %s", f"{len(patrol_edges):,}")
    LOGGER.info("patrol graph feature rows: %s", f"{len(patrol_features):,}")
    _output("patrol graph edges", PATROL_GRAPH_EDGES_PATH)
    _output("patrol graph features", PATROL_GRAPH_FEATURES_PATH)


def _run_deep_training(enabled: bool) -> bool:
    _stage("9. BE-STHGT training")
    if not enabled:
        LOGGER.info("skipped BE-STHGT training")
        return False
    config = load_deep_training_config("configs/model_config.yaml")
    result = train_be_sthgt(
        training_table_path=MODEL_TRAINING_TABLE_PATH,
        adjacency_dir=ADJACENCY_OUTPUT_DIR,
        model_output_path=MODEL_OUTPUT_PATH,
        metadata_output_path=MODEL_METADATA_PATH,
        metrics_output_path=DEEP_METRICS_PATH,
        predictions_output_path=DEEP_PREDICTIONS_PATH,
        config=config,
    )
    LOGGER.info("best epoch: %s", result.best_epoch)
    LOGGER.info("best validation NDCG@10: %.5f", result.best_validation_ndcg_at_10)
    _output("BE-STHGT model", MODEL_OUTPUT_PATH)
    _output("BE-STHGT metadata", MODEL_METADATA_PATH)
    _output("BE-STHGT metrics", DEEP_METRICS_PATH)
    _output("BE-STHGT predictions", DEEP_PREDICTIONS_PATH)
    return True


def _run_ranker_training(enabled: bool, *, use_deep_predictions: bool, fast_demo: bool) -> bool:
    _stage("10. LightGBM ranker training")
    if not enabled:
        LOGGER.info("skipped LightGBM ranker training")
        return False
    config = load_ranker_config("configs/model_config.yaml")
    if fast_demo:
        config = ranker_config_with_overrides(config, n_estimators=100, learning_rate=None)
        LOGGER.info("fast-demo ranker override: n_estimators=100")
    result = train_lgbm_ranker(
        training_table_path=MODEL_TRAINING_TABLE_PATH,
        graph_features_path=GRAPH_FEATURES_PATH,
        deep_predictions_path=DEEP_PREDICTIONS_PATH if use_deep_predictions else None,
        model_output_path=RANKER_MODEL_PATH,
        metrics_output_path=RANKER_METRICS_PATH,
        feature_importance_output_path=FEATURE_IMPORTANCE_PATH,
        config=config,
    )
    LOGGER.info("ranker comparison rows: %s", f"{len(result.comparison_table):,}")
    _output("LightGBM ranker model", RANKER_MODEL_PATH)
    _output("LightGBM ranker metrics", RANKER_METRICS_PATH)
    _output("LightGBM feature importance", FEATURE_IMPORTANCE_PATH)
    return True


def _run_predict(*, use_deep_predictions: bool) -> pd.DataFrame:
    _stage("11. Predict")
    predictions = write_ensemble_predictions(
        MODEL_TRAINING_TABLE_PATH,
        output_path=PREDICTIONS_PATH,
        graph_features_path=GRAPH_FEATURES_PATH,
        deep_predictions_path=DEEP_PREDICTIONS_PATH if use_deep_predictions else None,
        ranker_model_path=RANKER_MODEL_PATH,
        ranker_metrics_path=RANKER_METRICS_PATH,
    )
    LOGGER.info("prediction rows: %s", f"{len(predictions):,}")
    _output("predictions", PREDICTIONS_PATH)
    return predictions


def _latest_prediction_window(predictions: pd.DataFrame) -> pd.Timestamp:
    if predictions.empty:
        raise ValueError("Prediction artifact is empty; cannot generate recommendations.")
    window_start = pd.to_datetime(predictions["window_start"], errors="coerce").dropna()
    if window_start.empty:
        raise ValueError("Prediction artifact has no valid window_start values.")
    return pd.Timestamp(window_start.max())


def _run_recommend(predictions: pd.DataFrame) -> None:
    _stage("12. Recommend")
    window_start = _latest_prediction_window(predictions)
    recommendations = write_recommendations(
        PREDICTIONS_PATH,
        output_path=RECOMMENDATIONS_PATH,
        features_path=MODEL_TRAINING_TABLE_PATH,
        police_station=None,
        window_start=window_start,
        available_officers=DEFAULT_RECOMMENDATION_OFFICERS,
        available_tow_units=DEFAULT_RECOMMENDATION_TOW_UNITS,
        mode=DEFAULT_RECOMMENDATION_MODE,
    )
    LOGGER.info(
        "recommendation rows: %s window_start=%s officers=%s tow_units=%s mode=%s",
        f"{len(recommendations):,}",
        window_start,
        DEFAULT_RECOMMENDATION_OFFICERS,
        DEFAULT_RECOMMENDATION_TOW_UNITS,
        DEFAULT_RECOMMENDATION_MODE,
    )
    _output("recommendations", RECOMMENDATIONS_PATH)


def _run_seed_db() -> None:
    _stage("13. Seed DuckDB")
    db_path = initialize_duckdb(APP_DB_PATH, rebuild=True)
    _output("DuckDB app database", db_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full CurbFlow AI pipeline.")
    parser.add_argument(
        "--input-csv",
        default=str(RAW_CSV_PATH),
        help="Theme 1 police violation CSV path. No ASTraM or external datasets are used.",
    )
    parser.add_argument(
        "--train-deep",
        action="store_true",
        help="Train BE-STHGT during this run. Off by default because full deep training is resource intensive.",
    )
    parser.add_argument("--skip-deep", action="store_true", help="Skip BE-STHGT training and deep predictions.")
    parser.add_argument("--skip-ranker", action="store_true", help="Skip LightGBM LambdaRank training.")
    parser.add_argument(
        "--fast-demo",
        action="store_true",
        help="Skip deep training and use baseline/LightGBM-only dashboard artifacts.",
    )
    parser.add_argument("--active-zone-min-records", type=int, default=100)
    return parser.parse_args()


def main() -> None:
    """Run every pipeline stage and write dashboard-ready artifacts."""

    _configure_logging()
    args = parse_args()
    if args.train_deep and args.skip_deep:
        raise SystemExit("Use either --train-deep or --skip-deep, not both.")
    raw_csv = _require_raw_csv(args.input_csv)
    deep_enabled = args.train_deep and not args.skip_deep and not args.fast_demo
    ranker_enabled = not args.skip_ranker

    LOGGER.info("input csv: %s", raw_csv)
    LOGGER.info("deep training enabled: %s", deep_enabled)
    LOGGER.info("ranker training enabled: %s", ranker_enabled)
    LOGGER.info("fast demo: %s", args.fast_demo)

    try:
        _run_preprocess(raw_csv)
        _run_audit(raw_csv)
        _run_pfdi()
        _run_zones(args.active_zone_min_records)
        rows = _run_novel_features()
        _run_exposure_and_blindspot(rows)
        _run_feature_build(rows, args.active_zone_min_records)
        _run_graph_build(args.active_zone_min_records)
        deep_available = _run_deep_training(deep_enabled)
        _run_ranker_training(
            ranker_enabled,
            use_deep_predictions=deep_available,
            fast_demo=args.fast_demo,
        )
        predictions = _run_predict(use_deep_predictions=deep_available)
        _run_recommend(predictions)
        _run_seed_db()
    except SystemExit:
        raise
    except Exception as exc:
        raise SystemExit(f"Full pipeline failed: {exc}") from exc

    LOGGER.info("")
    LOGGER.info("Full CurbFlow AI pipeline completed successfully.")


if __name__ == "__main__":
    main()
