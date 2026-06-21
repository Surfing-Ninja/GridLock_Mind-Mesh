# CurbFlow AI

CurbFlow AI is a full-stack hackathon prototype for the theme **Poor Visibility on Parking-Induced Congestion**. It is a bias-aware parking enforcement intelligence system that helps traffic police distinguish observed illegal-parking hotspots from places where enforcement visibility is weak.

The core product idea is simple:

```text
CurbFlow AI does not confuse no challan with no problem.
```

It uses police parking violation records to compute a Parking-Induced Flow Disruption Index (PFDI), identify high-impact enforcement zones, expose blind spots, and recommend station-wise enforcement plans under limited officer and towing resources.

The GitHub-facing overview, Mermaid diagrams, and fresh-clone setup are maintained in the repository root [README.md](../README.md). This file stays focused on the `curbflow-ai/` monorepo commands and implementation contract.

## Theme

```text
Theme 1: Poor Visibility on Parking-Induced Congestion
```

The project addresses a practical gap in traffic operations: parking violations are often recorded only where enforcement is already present. A zone with no challans may be clear, or it may simply be under-observed. CurbFlow AI treats this as a visibility and bias problem, not only as a heatmap problem.

## Dataset Used

CurbFlow AI uses only the Theme 1 police parking violation CSV.

```text
Configured raw path:
data/raw/police_parking_violations_nov2023_apr2024.csv

Approximate row count:
298,450 rows

Actual observed date range:
November 2023 to April 2024
```

Dataset constraints:

- `created_datetime` is parsed as UTC and converted to `Asia/Kolkata`.
- `closed_datetime`, `action_taken_timestamp`, and `description` are audit-only fields and are not used as labels.
- `validation_status` null values are treated as `unknown` confidence, not as rejected records.
- Evening enforcement records are sparse, so evening zero-violation windows are treated as evidence-poor windows.
- ASTraM and external datasets are not used for Theme 1.

## What Makes CurbFlow Different

Most dashboards would show a parking-violation heatmap. CurbFlow AI builds an operational intelligence layer around the heatmap:

- **PFDI scoring:** estimates parking-induced flow disruption using violation severity, vehicle obstruction, location criticality, validation confidence, evidence quality, and repeat pressure.
- **Enforcement visibility digital twin:** estimates where enforcement has actually been visible using device/user activity, station-hour activity, patrol coverage, validation coverage, and SCITA transmission.
- **Coverage gaps:** separates low-observed-risk zones from low-visibility zones.
- **Blindspot risk:** highlights high-potential, low-visibility zones, especially during evening audit windows.
- **Patrol myopia:** detects stations whose records are concentrated in a small set of zones or morning-heavy patrol patterns.
- **Hidden junction basins:** assigns "No Junction" records near named junctions to nearby junction basins.
- **Repeat-vehicle persistence:** uses previous-only vehicle history to identify recurring obstruction pressure without future leakage.
- **Road corridor and place context:** extracts operational context from police text fields.
- **Graph modeling:** builds geo, station, pattern, repeat-vehicle, and patrol-transition graph relations.
- **Resource planner:** recommends exploit/explore enforcement actions under officer and tow-unit constraints.

## Explanation Snippets

These are the short explanations used across the dashboard and demo narrative:

1. **PFDI:** “Parking-Induced Flow Disruption Index is a proxy score built from violation severity, vehicle obstruction, location criticality, repeat behavior, and evidence confidence. It does not claim measured speed reduction.”
2. **Enforcement visibility:** “Police violation data is affected by when and where enforcement is visible. CurbFlow estimates this visibility using device activity, user activity, station-hour activity, SCITA success, validation coverage, and patrol route patterns.”
3. **Blindspot:** “A blindspot is a zone with high static obstruction potential but low enforcement visibility. CurbFlow does not mark it as a proven hotspot; it marks it as an audit priority.”
4. **Evening gap:** “The dataset shows very low evening enforcement records. A normal ML model would treat that as low risk. CurbFlow treats it as low evidence and recommends discovery patrols.”
5. **Patrol myopia:** “Patrol Myopia Index measures whether a station’s enforcement is concentrated in a few repeated zones and time windows, potentially missing nearby risk zones.”
6. **Hidden junction basin:** “Many records are tagged No Junction even when they are spatially close to named junctions. CurbFlow assigns these to junction basins to detect spillover around traffic-critical points.”
7. **Planner:** “The planner balances exploitation of proven hotspots with exploration of under-covered blindspots under officer and towing constraints.”

## Architecture

```text
Theme 1 Police Violation CSV
        |
        v
+---------------------+
| Data Load and Clean |
| UTC -> Asia/Kolkata |
+---------------------+
        |
        v
+----------------------+
| Data and Bias Audit  |
| nulls, hours, gaps   |
+----------------------+
        |
        v
+---------------------------+
| Row-Level PFDI Scoring    |
| severity, obstruction,    |
| criticality, repeat,      |
| evidence quality          |
+---------------------------+
        |
        v
+---------------------------+       +----------------------------+
| 300m Zone Assignment      | ----> | Zone GeoJSON               |
| active-zone detection     |       | dashboard map layer        |
+---------------------------+       +----------------------------+
        |
        v
+---------------------------------------------------------------+
| Novel Feature Layer                                           |
| visibility twin, coverage gap, blindspot, patrol myopia,      |
| hidden junction basins, repeat persistence, corridor context  |
+---------------------------------------------------------------+
        |
        v
+------------------------------+
| Zone x 3-Hour IST Features   |
| lags, rolling windows,       |
| next-window targets          |
+------------------------------+
        |
        v
+------------------------------------------------+
| Multi-Relation Graph Build                     |
| geo, station, pattern, vehicle, patrol, hetero |
+------------------------------------------------+
        |
        v
+--------------------------+      +---------------------------+
| BE-STHGT Deep Model      |      | LightGBM LambdaRank       |
| bias-exposure graph      |      | engineered feature ranker |
| transformer              |      |                           |
+--------------------------+      +---------------------------+
        |                                      |
        +-------------------+------------------+
                            v
+------------------------------------------------+
| Ensemble Risk                                  |
| 0.65 BE-STHGT + 0.25 LightGBM + 0.10 rules    |
+------------------------------------------------+
                            |
                            v
+------------------------------------------------+
| Exploit/Explore Enforcement Planner           |
| conservative, balanced, discovery modes       |
+------------------------------------------------+
                            |
                            v
+-------------------+      +--------------------+
| DuckDB App Store  | ---> | FastAPI Backend    |
+-------------------+      +--------------------+
                                      |
                                      v
                            +--------------------+
                            | Next.js Dashboard  |
                            +--------------------+
```

## Repository Layout

```text
configs/              Data, scoring, feature, graph, model, and planner configs
data/                 Local raw, interim, processed, and app data directories
artifacts/            Local model, metric, and report outputs
scripts/              Independently runnable pipeline entrypoints
src/curbflow/         Core Python package
apps/api/             FastAPI backend
apps/web/             Next.js frontend
tests/                Unit and integration tests
```

## How To Run The Pipeline

Install Python dependencies:

```bash
make setup
```

`make setup` installs from the single root-level dependency file at `../requirements.txt`.

Place the Theme 1 CSV at:

```text
data/raw/police_parking_violations_nov2023_apr2024.csv
```

Run the full production-style pipeline:

```bash
python scripts/run_full_pipeline.py
```

Run the lightweight demo pipeline:

```bash
python scripts/run_full_pipeline.py --fast-demo --skip-deep
```

Run individual stages:

```bash
make preprocess
make audit
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

Run tests:

```bash
make test
```

Fresh clone final check:

```bash
make setup
make full
make db
make api
cd apps/web && npm install && npm run dev
```

Run the lightweight CI check:

```bash
make ci
```

`make ci` executes:

```bash
python -m pytest -q
python scripts/run_full_pipeline.py --fast-demo --skip-deep
```

## How To Run The Backend

Seed the DuckDB app database from generated artifacts:

```bash
make db
```

Start the FastAPI server:

```bash
make api
```

Default local API host and port are configured by:

```text
CURBFLOW_API_HOST
CURBFLOW_API_PORT
```

Key endpoints:

```text
GET  /health
GET  /audit/summary
GET  /audit/hourly
GET  /zones/geojson
GET  /hotspots
GET  /blindspots
GET  /zones/{zone_id}
GET  /patrol/summary
GET  /patrol/routes
POST /planner/recommend
GET  /metrics/model
POST /feedback
```

The API does not expose raw `vehicle_number`, `device_id`, or `created_by_id`.

## How To Run The Frontend

Install frontend dependencies:

```bash
cd apps/web
npm install
```

Start the Next.js app:

```bash
make web
```

Default local frontend:

```text
http://localhost:3000
```

Dashboard pages:

```text
/
/audit
/hotspots
/blindspots
/junction-basins
/patrol-digital-twin
/planner
/metrics
```

## Model Stack

The intended model stack is:

```text
BE-STHGT + LightGBM LambdaRank + Rule Blindspot Ensemble
```

BE-STHGT stands for **Bias-Exposure Spatio-Temporal Heterogeneous Graph Transformer**. Its key modeling idea is:

```text
observed_mu = latent_risk * exposure
```

This makes enforcement exposure explicit. Low observed counts in low-exposure windows are not treated as strong evidence of low illegal-parking risk.

The fast-demo mode skips BE-STHGT training and produces dashboard artifacts using the LightGBM/rule path. Full deep training can be run with:

```bash
make train-deep
```

## Planner Modes

```text
conservative: prioritize proven observed hotspots
balanced:     combine observed hotspots with blindspot audits
discovery:    allocate more resources to uncovered high-potential zones
```

Planner actions include beat patrol, towing support, mobile camera patrol, repeat-offender checks, temporary cones, evening audit patrol, patrol expansion, and evidence-quality audit.

## Feedback Loop

The historical dataset has no usable outcome columns. CurbFlow adds a feedback table for future learning through:

```text
POST /feedback
```

Feedback captures officers deployed, tow units used, vehicles found, vehicles removed, vehicles towed, road-cleared status, approximate queue length, and notes.

Feedback is stored for future learning and is not used in current model training.

Future action-effectiveness learning can be framed as:

```text
future_action_effectiveness = outcome feedback / predicted risk
```

## Guardrails

CurbFlow AI is intentionally conservative about what it claims.

- We do not claim exact traffic speed reduction.
- We do not claim measured congestion.
- PFDI is a proxy for parking-induced flow disruption, not measured speed loss.
- No challan does not mean no illegal parking.
- Evening outputs are blindspot audit priorities, not validated evening predictions.
- `validation_status` NaN is unknown confidence, not rejected evidence.
- Repeat pressure uses past vehicle history only and does not use future rows.
- Train, validation, and test splits are chronological.
- ASTraM is not used in Theme 1.
- Streamlit is not used; the app stack is FastAPI and Next.js.
- Raw vehicle numbers, device IDs, and user IDs must not be exposed in API or UI responses.
- `closed_datetime`, `action_taken_timestamp`, and `description` are not outcome labels.
- Low exposure increases uncertainty and audit priority; it does not automatically fabricate hotspots.
- The system supports operational prioritization, not legal adjudication.

## Generated Artifacts

Typical generated outputs:

```text
data/interim/violations_clean.parquet
data/interim/row_scores.parquet
data/interim/zone_assignments.parquet
data/processed/zones.geojson
data/processed/zone_time_features.parquet
data/processed/model_training_table.parquet
data/processed/predictions.parquet
data/processed/recommendations.parquet
data/app/curbflow.duckdb
artifacts/metrics/ranker_metrics.json
artifacts/metrics/model_card.md
artifacts/reports/data_quality_report.md
artifacts/reports/bias_audit_report.md
```

Raw data, Parquet outputs, DuckDB files, generated reports, and model binaries are ignored by git by default. The model card is intentionally allowed as a tracked documentation artifact.
