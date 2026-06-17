# CurbFlow AI

CurbFlow AI is a full-stack, bias-aware parking enforcement intelligence system for the theme **Poor Visibility on Parking-Induced Congestion**.

The system does not treat police parking challan records as complete illegal-parking ground truth. It models them as enforcement visibility observations, then separates observed risk from low-visibility blind spots.

## Product Statement

**CurbFlow AI does not confuse no challan with no problem.** It separates parking-risk signals from enforcement-visibility bias, identifies high-impact hotspots, exposes blind spots, and recommends where limited traffic-police resources should go next.

## Operational Questions

```text
Where is illegal parking likely to damage traffic flow the most?
Where is enforcement missing the problem?
Which station zones need known-hotspot enforcement?
Which station zones need blind-spot audit patrols?
How should officers and tow units be allocated under resource limits?
```

## Constraints

- Use only the Theme 1 police parking violation CSV.
- Do not use ASTraM or any external dataset.
- Parse `created_datetime` as UTC and convert it to `Asia/Kolkata`.
- Do not use `description`, `closed_datetime`, or `action_taken_timestamp` as outcome labels.
- Treat `validation_status` nulls as unknown confidence, not rejected records.
- Treat sparse evening records as low enforcement evidence, not proof of low illegal-parking risk.
- Build repeat-vehicle features using only previous chronological history.
- Use chronological train, validation, and test splits only.
- Do not expose raw vehicle numbers, device IDs, or user IDs through API or UI.

## Architecture

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

## Intelligence Layers

```text
PFDI
  Parking-Induced Flow Disruption Index, a proxy for disruption impact.

Observed Hotspots
  Zones with strong observed PFDI and evidence quality.

Visibility Digital Twin
  Estimated enforcement exposure from devices, users, station activity,
  route coverage, validation coverage, and SCITA delivery.

Blind Spots
  High-potential, low-visibility zones treated as audit priorities.

Patrol Myopia
  Station-level concentration in repeated zones and time windows.

Hidden Junction Basins
  Junction spillover risk from nearby "No Junction" records.

Repeat Persistence
  Previous-only vehicle history, avoiding future leakage.

Corridor and Place Context
  Road and place-type signals inferred from police text fields.
```

## Model Architecture

```text
Zone-Time Tensor
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
Bias-Exposure Risk Head
      |
      v
Multi-Task Prediction Heads
      |
      v
BE-STHGT + LightGBM LambdaRank + Rule Blindspot Ensemble
```

## Monorepo Structure

```text
configs/              Pipeline, scoring, graph, model, and planner configuration
data/                 Local raw, interim, processed, and app data directories
artifacts/            Local model, metric, and report outputs
scripts/              Independently runnable pipeline entrypoints
src/curbflow/         Core Python package
apps/api/             FastAPI application
apps/web/             Next.js dashboard
tests/                Unit and integration test suite
```

## Core Modules

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

## Pipeline Commands

```bash
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

Run everything:

```bash
make full
```

## API and Dashboard Surfaces

```text
API
  /health
  /audit/summary
  /audit/hourly
  /zones/geojson
  /hotspots
  /blindspots
  /junction-basins
  /patrol/summary
  /metrics/model
  /planner/recommend
  /feedback

Dashboard
  /audit
  /hotspots
  /blindspots
  /junction-basins
  /patrol-digital-twin
  /planner
  /metrics
```

The API and dashboard expose aggregate intelligence only. Raw vehicle numbers, device IDs, and user IDs are excluded.

## Local Setup

```bash
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

- `configs/data_config.yaml`: dataset path, timezones, zones, windows, chronological split.
- `configs/scoring_config.yaml`: violation, vehicle, confidence, evidence, criticality, and PFDI weights.
- `configs/feature_config.yaml`: feature-family switches.
- `configs/graph_config.yaml`: graph relation types.
- `configs/model_config.yaml`: BE-STHGT, ranker, loss, and ensemble settings.
- `configs/planner_config.yaml`: exploit/explore planner modes and action costs.

## Git Hygiene

The repository ignores raw data, generated Parquet outputs, DuckDB files, model artifacts, report outputs, local environments, Python caches, frontend dependencies, frontend build output, and operating-system metadata.

Only source code, configuration, documentation, tests, and scaffold `.gitkeep` files should be committed.
