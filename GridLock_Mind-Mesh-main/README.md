# CurbFlow AI

CurbFlow AI is a full-stack, bias-aware parking enforcement intelligence system for the theme **Poor Visibility on Parking-Induced Congestion**.

The core principle is simple: **no challan does not mean no problem**. Police violation records show where enforcement was visible, not every place where illegal parking occurred. CurbFlow AI separates observed parking-risk signals from enforcement visibility bias, identifies high-impact hotspots, exposes blind spots, and recommends where limited traffic-police resources should go next.

The canonical project scaffold lives in [curbflow-ai](./curbflow-ai). New implementation work should happen inside that monorepo structure.

## Product Scope

CurbFlow AI is designed to:

- compute a Parking-Induced Flow Disruption Index, PFDI;
- detect observed illegal-parking hotspots;
- detect enforcement visibility gaps;
- detect blind spots, especially evening peak-risk windows;
- build operational intelligence features from the Theme 1 police violation CSV;
- train a BE-STHGT deep model and LightGBM ranker ensemble;
- recommend station-wise enforcement plans through an exploit/explore planner;
- serve aggregate outputs through FastAPI and a Next.js dashboard.

## Problem Framing

Most parking dashboards answer only one question:

```text
Where did violations happen?
```

CurbFlow AI is designed for operational traffic enforcement, where the more useful questions are:

```text
Where is illegal parking likely to damage traffic flow the most?
Where is enforcement missing the problem?
Where should limited officers and tow vehicles go first?
```

The dataset is an enforcement record, not complete illegal-parking ground truth. Sparse evening enforcement records are therefore treated as low evidence and high uncertainty rather than proof that evening illegal parking is low.

## Non-Negotiable Data Constraints

- Use only the Theme 1 police parking violation CSV.
- Do not use ASTraM or any external dataset.
- Parse `created_datetime` as UTC and convert it to `Asia/Kolkata`.
- Do not use `description`, `closed_datetime`, or `action_taken_timestamp` as outcome labels.
- Treat `validation_status` nulls as unknown confidence, not rejected records.
- Treat sparse evening records as low enforcement evidence, not proof of low illegal-parking risk.
- Build repeat-vehicle features using only previous chronological history.
- Use chronological train, validation, and test splits only.
- Do not expose raw vehicle numbers, device IDs, or user IDs through API or UI.

## Repository Layout

```text
curbflow-ai/
  configs/              Pipeline, scoring, graph, model, and planner configuration
  data/                 Local raw, interim, processed, and DuckDB data directories
  artifacts/            Local model, metric, and report outputs
  scripts/              Independently runnable pipeline entrypoints
  src/curbflow/         Core Python package
  apps/api/             FastAPI application
  apps/web/             Next.js dashboard
  tests/                Unit and integration test suite
```

Raw data, generated Parquet files, DuckDB files, model artifacts, frontend dependencies, cache files, and local environment files are intentionally ignored by git.

## System Architecture

```text
                         Theme 1 Police Violation CSV
                                      |
                                      v
                         Data Audit and Validation
                                      |
                                      v
                         Preprocess and IST Time Windows
                                      |
                                      v
              +---------------- PFDI Row Scoring ----------------+
              |                                                   |
              v                                                   v
       300m Zone Assignment                         Evidence and Exposure Features
              |                                                   |
              v                                                   v
       Zone-Time Aggregation <---------- Novel Operational Features
              |
              v
      Multi-Relation Graph Construction
              |
              v
  +--------------------------+        +----------------------------+
  | BE-STHGT Deep Model      |        | LightGBM LambdaRank Model  |
  +--------------------------+        +----------------------------+
              |                                    |
              +----------------+-------------------+
                               v
                         Ensemble Risk Score
                               |
                               v
                  Exploit/Explore Enforcement Planner
                               |
                               v
                 DuckDB + FastAPI + Next.js Dashboard
```

## Core Backend Architecture

```text
src/curbflow/
  data/        Schema checks, loading, cleaning, timestamp conversion, audit
  scoring/     Violation parsing, severity, obstruction, repeat pressure, PFDI
  zoning/      Grid and optional H3 zones, zone assignment, GeoJSON export
  exposure/    Visibility digital twin, coverage gaps, blindspot scoring
  features/    Zone-time, static, temporal, lag, novel, sequence, training features
  graph/       Geo, station, pattern, vehicle, patrol, heterogeneous graphs
  ml/          BE-STHGT, ranking models, losses, metrics, inference, ensemble
  planner/     Action rules, priority scoring, optimization, explanations
  feedback/    Future outcome feedback schema and learning loop hooks
  db/          DuckDB initialization, queries, and repository abstractions
```

## Intelligence Layers

```text
Observed Hotspots
  Zones with high observed PFDI and strong evidence quality.

Enforcement Visibility Digital Twin
  Estimated where police enforcement was visible based on devices, users,
  station activity, route coverage, validation coverage, and SCITA delivery.

Blind Spots
  Zones with high static potential and low enforcement visibility, especially
  during sparse evening peak-risk windows.

Patrol Myopia
  Station-level concentration of enforcement in repeated zones and time windows.

Hidden Junction Basins
  Spillover risk from records tagged "No Junction" that are physically near
  named junction areas.

Repeat-Vehicle Persistence
  Chronology-safe pressure from previous vehicle history only.

Road Corridor Risk and Place-Type Context
  Corridor and land-use signals inferred from police location text without
  external datasets.
```

## Model Architecture

```text
Zone-Time Feature Tensor
          |
          v
Feature Projection
          |
          v
Multi-Relation Graph Blocks
          |
          v
Adaptive Learned Adjacency
          |
          v
Temporal Transformer Encoder
          |
          v
Bias-Exposure Latent Risk Head
          |
          v
Multi-Task Outputs
  - latent risk
  - observed count parameters
  - predicted PFDI
  - hotspot probability
  - q90 PFDI
  - blindspot score
  - station rank score
          |
          v
LightGBM LambdaRank + Rule Blindspot Ensemble
```

The ensemble uses BE-STHGT for graph-temporal and bias-exposure behavior, LightGBM LambdaRank for robust tabular prioritization, and a rule blindspot prior for explicit low-visibility audit needs.

## Data Pipeline

```text
make audit
make preprocess
make pfdi
make zones
make features
make graph
make train-deep
make train-ranker
make predict
make recommend
make db
```

The complete pipeline is exposed as:

```bash
cd curbflow-ai
make full
```

## API and Dashboard Surfaces

```text
FastAPI
  GET  /health
  GET  /audit/summary
  GET  /audit/hourly
  GET  /zones/geojson
  GET  /hotspots
  GET  /blindspots
  GET  /zones/{zone_id}
  GET  /junction-basins
  GET  /patrol/summary
  GET  /metrics/model
  POST /planner/recommend
  POST /feedback

Next.js Dashboard
  /audit
  /hotspots
  /blindspots
  /junction-basins
  /patrol-digital-twin
  /planner
  /metrics
```

The API must return aggregate intelligence only. Raw vehicle numbers, device IDs, and user IDs are not API or UI fields.

## Artifact Contract

```text
data/interim/
  violations_clean.parquet
  row_scores.parquet
  zone_assignments.parquet
  graph_edges.parquet

data/processed/
  zones.geojson
  zone_static_features.parquet
  zone_time_features.parquet
  model_training_table.parquet
  predictions.parquet
  recommendations.parquet
  coverage_audit.parquet

data/app/
  curbflow.duckdb

artifacts/models/
  be_sthgt_model.pt
  ranker_lgbm.txt
  model_metadata.json

artifacts/metrics/
  metrics.json
  station_metrics.json
  model_card.md

artifacts/reports/
  data_quality_report.md
  bias_audit_report.md
  eda_summary.json
```

These files are generated locally and intentionally excluded from git.

## Local Development

```bash
cd curbflow-ai
python -m venv .venv
source .venv/bin/activate
make setup
```

Run the API:

```bash
make api
```

Run the web app:

```bash
make web
```

Run tests:

```bash
make test
```

## Configuration

The project is configured through YAML files under [curbflow-ai/configs](./curbflow-ai/configs):

- `data_config.yaml` controls dataset path, timezones, zoning, windows, and chronological split.
- `scoring_config.yaml` controls violation, vehicle, confidence, evidence, criticality, and PFDI weights.
- `feature_config.yaml` controls feature families and operational intelligence switches.
- `graph_config.yaml` controls graph relation types.
- `model_config.yaml` controls BE-STHGT, ranker, loss, and ensemble settings.
- `planner_config.yaml` controls exploit/explore modes and enforcement action costs.

## Git Hygiene

The repository is configured to ignore:

- raw CSV datasets;
- Parquet, DuckDB, SQLite, and generated data outputs;
- model checkpoints and serialized model artifacts;
- report and metric artifacts;
- `.env` files;
- Python cache files;
- frontend `node_modules` and `.next` builds;
- macOS and editor metadata.

Only source code, configuration, documentation, tests, and scaffold `.gitkeep` files should be committed.
