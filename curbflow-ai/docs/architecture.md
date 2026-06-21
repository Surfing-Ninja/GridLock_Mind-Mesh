# CurbFlow AI Architecture

## System Goal

CurbFlow AI turns a police parking violation CSV into a bias-aware enforcement intelligence layer. The system separates observed violation risk from enforcement visibility bias, then recommends enforcement actions under station-level resource constraints.

The project uses only the Theme 1 police violation CSV. ASTraM and external datasets are not used.

## End-to-End Flow

```text
Theme 1 Police Violation CSV
        |
        v
Data Loading and Cleaning
- parse created_datetime as UTC
- convert to Asia/Kolkata
- normalize text and boolean-like columns
- preserve null outcome columns for audit only
        |
        v
Data and Bias Audit
- row and column counts
- actual date range
- fully null outcome fields
- morning/evening evidence gap
- station and validation summaries
        |
        v
Row-Level PFDI Scoring
- violation severity
- vehicle obstruction
- location criticality
- evidence confidence
- repeat pressure without future leakage
        |
        v
300m Zone Assignment
- grid zone_id
- active-zone detection
- zone GeoJSON
- top-zone concentration
        |
        v
Novel Feature Layer
- enforcement visibility digital twin
- patrol myopia
- hidden junction basins
- repeat vehicle persistence
- road corridor and place-type context
- patrol transition graph
        |
        v
Zone x 3-Hour IST Feature Table
- observed PFDI
- exposure and coverage gap
- blindspot risk
- lags and rolling windows
- next-window supervised targets
        |
        v
Graph Build
- geographic graph
- station graph
- temporal pattern graph
- repeat vehicle graph
- patrol transition graph
        |
        v
Modeling
- BE-STHGT deep model when explicitly trained
- LightGBM LambdaRank
- rule blindspot score
- ensemble risk
        |
        v
Planner
- conservative, balanced, discovery modes
- officer and tow-unit constraints
- exploit/explore recommendations
        |
        v
DuckDB + FastAPI + Next.js Dashboard
```

## Backend

The backend is a FastAPI app in `apps/api`.

Main responsibilities:

- Serve audit summaries, hourly distributions, zones, hotspots, blindspots, patrol summaries, planner recommendations, model metrics, and feedback capture.
- Read from `data/app/curbflow.duckdb`.
- Avoid loading the raw CSV into API memory.
- Strip raw PII-like fields from responses: `vehicle_number`, `device_id`, and `created_by_id`.
- Expose development-only artifact diagnostics through `/debug/files`.

Run:

```bash
make db
make api
```

The API runs on port `8000`.

## Frontend

The frontend is a Next.js App Router app in `apps/web`.

Main pages:

- `/`
- `/audit`
- `/hotspots`
- `/blindspots`
- `/junction-basins`
- `/patrol-digital-twin`
- `/planner`
- `/metrics`

The API routing is configurable with:

```bash
NEXT_PUBLIC_API_BASE_URL=/api
CURBFLOW_API_INTERNAL_URL=<FastAPI backend URL>
```

The app also supports the older `NEXT_PUBLIC_API_BASE` variable for compatibility.

Run:

```bash
cd apps/web
npm install
npm run dev
```

The frontend runs on port `3000`.

## Storage

Pipeline artifacts are written to disk:

- `data/interim/violations_clean.parquet`
- `data/interim/row_scores.parquet`
- `data/interim/zone_assignments.parquet`
- `data/processed/zones.geojson`
- `data/processed/zone_time_features.parquet`
- `data/processed/model_training_table.parquet`
- `data/processed/predictions.parquet`
- `data/processed/recommendations.parquet`
- `data/app/curbflow.duckdb`

Generated data, raw CSVs, Parquet outputs, DuckDB files, and model binaries are ignored by git.

## Model Architecture

The intended model stack is:

```text
BE-STHGT + LightGBM LambdaRank + rule blindspot score
```

BE-STHGT stands for Bias-Exposure Spatio-Temporal Heterogeneous Graph Transformer.

Its key modeling idea is:

```text
observed_mu = latent_risk * exposure
```

This ensures low observed counts under low exposure are not treated as strong evidence of safety.

For local demo reliability, `make full` generates dashboard-ready LightGBM/rule artifacts by default. Full BE-STHGT training remains available through:

```bash
make train-deep
```

or:

```bash
python scripts/run_full_pipeline.py --train-deep
```

## Guardrails

- PFDI is a proxy for parking-induced flow disruption, not measured speed loss.
- No challan does not mean no illegal parking.
- Evening blindspot outputs are audit priorities, not validated evening predictions.
- `validation_status` missing values are unknown confidence, not rejected evidence.
- Repeat pressure uses past vehicle history only.
- Model train, validation, and test splits are chronological.
- Raw vehicle, device, and user identifiers are not exposed in API or UI responses.
