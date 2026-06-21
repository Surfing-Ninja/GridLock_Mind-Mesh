# CurbFlow AI — Product Requirements Document (PRD)

> **Project theme:** Poor Visibility on Parking-Induced Congestion
> **Product name:** CurbFlow AI
> **Subtitle:** Bias-Aware Parking Enforcement Intelligence
> **Stack:** Python + FastAPI, Next.js + TypeScript, PyTorch, LightGBM, DuckDB, Parquet, MapLibre, deck.gl
> **Dataset:** Theme 1 police parking violation CSV only
> **Core pitch:** CurbFlow AI does not confuse **“no challan”** with **“no problem.”** It separates parking-risk signals from enforcement-visibility bias, identifies observed hotspots, exposes blind spots, and recommends where limited traffic-police resources should go next.

---

## 1. Executive Summary

CurbFlow AI is a full-stack traffic-enforcement intelligence system that uses police parking violation records to identify high-impact illegal-parking hotspots, quantify their estimated traffic-flow disruption, detect enforcement visibility gaps, and recommend optimized deployment plans for patrol officers, towing units, mobile camera checks, and blind-spot audits.

The system is designed for the hackathon theme:

> **Poor Visibility on Parking-Induced Congestion**
> On-street illegal parking and spillover parking near commercial areas, metro stations, and events choke carriageways and intersections. Enforcement is patrol-based and reactive, there is no heatmap of parking violations versus congestion impact, and enforcement zones are hard to prioritize.

CurbFlow AI solves this by creating a **bias-aware decision layer** on top of police violation data.

Unlike generic AI submissions that simply show a heatmap, CurbFlow AI explicitly models that the dataset is an **enforcement visibility dataset**, not a complete ground-truth record of all illegal parking. The product therefore distinguishes between:

1. **Observed hotspots** — zones with strong evidence of parking-induced disruption.
2. **Blind spots** — zones that may look safe only because enforcement visibility is low.
3. **Patrol myopia zones** — areas where enforcement is over-concentrated in repeated zones or time windows.
4. **Junction basins** — traffic-critical junction areas affected by nearby “No Junction” spillover records.
5. **Repeat obstruction zones** — zones with repeated anonymized vehicle behavior and persistence signals.
6. **Actionable enforcement plans** — station-wise deployment recommendations under resource constraints.

---

## 2. Problem Statement

### 2.1 Operational Challenge

On-street illegal parking and spillover parking near markets, metro stations, schools, hospitals, commercial roads, and junctions reduce effective carriageway width and choke traffic movement.

Current enforcement is largely:

- Patrol-based.
- Reactive.
- Dependent on officer experience.
- Concentrated around known/familiar locations.
- Weak in visibility during certain periods, especially evening peak-risk windows.
- Not linked to a data-driven congestion-impact prioritization framework.

### 2.2 Why This Is Hard Today

Existing systems usually answer:

```text
Where did violations happen?
```

But traffic police need to answer:

```text
Where is illegal parking likely to damage traffic flow the most?
Where is enforcement missing the problem?
Where should limited officers and tow vehicles go first?
```

The uploaded dataset also reveals a major challenge:

```text
Violation records are not uniformly collected across time.
Evening windows are severely under-represented.
```

Therefore, a naive ML model would incorrectly learn:

```text
Low evening challans = low evening parking risk
```

CurbFlow AI fixes this by treating low-coverage periods as **low evidence**, not automatically as low risk.

---

## 3. Product Vision

### 3.1 Vision Statement

CurbFlow AI turns police parking violation records into a bias-aware traffic-enforcement intelligence layer that helps authorities identify what is visible, what is hidden, and where action should go next.

### 3.2 Product Promise

CurbFlow AI will:

- Quantify parking-induced flow disruption using a defensible proxy score.
- Detect high-confidence observed hotspots.
- Detect under-observed blind spots.
- Reveal enforcement concentration and patrol myopia.
- Recommend station-wise enforcement plans.
- Add a feedback loop missing from the historical dataset.

### 3.3 Winning Differentiator

Most teams may build:

```text
AI parking violation heatmap
```

CurbFlow AI builds:

```text
Bias-aware enforcement intelligence + patrol digital twin + graph-based deployment planner
```

The main judge-facing line:

> **“CurbFlow does not confuse no challan with no problem.”**

---

## 4. Goals and Non-Goals

### 4.1 Goals

CurbFlow AI must:

1. Use only the Theme 1 police violation CSV dataset.
2. Clean and audit the dataset.
3. Detect data quality issues, null outcome columns, and enforcement-time bias.
4. Compute a Parking-Induced Flow Disruption Index, PFDI.
5. Build 300m spatial zones or optional H3 zones.
6. Aggregate records into 3-hour IST zone-time windows.
7. Estimate enforcement exposure and coverage gaps.
8. Detect observed hotspots.
9. Detect blind spots.
10. Compute novel operational features:
    - Enforcement Visibility Digital Twin
    - Patrol Myopia Index
    - Hidden Junction Basin Detection
    - Repeat-Vehicle Persistence Score
    - Device/User Evidence Trust Score
    - Patrol Transition Graph
    - Road Corridor Risk
    - Place-Type Context
11. Train a complex ML model:
    - BE-STHGT: Bias-Exposure Spatio-Temporal Heterogeneous Graph Transformer.
12. Train a LightGBM LambdaRank model.
13. Ensemble deep model + ranker + rule-based blindspot score.
14. Recommend enforcement deployment under resource constraints.
15. Expose results through FastAPI.
16. Visualize results in a Next.js dashboard.
17. Include a feedback loop for future learning.

### 4.2 Non-Goals

CurbFlow AI must **not** claim:

- Exact vehicle speed reduction.
- Exact travel-time delay.
- Measured congestion ground truth.
- Verified traffic-flow causality.
- Validated evening congestion prediction when evening labels are sparse.
- Real-time prediction unless live data integration is later added.

CurbFlow AI must not use:

- ASTraM event data for Theme 1.
- Random train/test split.
- Future rows for repeat-vehicle features.
- Validation status as a live-time prediction feature.
- Raw vehicle numbers, device IDs, or created_by IDs in frontend/API responses.

---

## 5. Users and Personas

### 5.1 Traffic Police Command Officer

Needs to know:

- Which zones should receive enforcement first?
- Which police stations have major hotspots?
- Where should tow vehicles be sent?
- Which time windows are under-covered?

Uses:

- Planner page.
- Hotspot map.
- Blindspot map.
- Station summary.

### 5.2 Station-Level Enforcement Planner

Needs to know:

- Top 5–10 enforcement zones for their station.
- Which zones need patrols versus towing support?
- Which areas are over-patrolled?
- Which evening areas require audit patrol?

Uses:

- Station filter.
- Patrol Myopia Index.
- Planner recommendations.

### 5.3 Field Officer

Needs to know:

- Where to go.
- Why that zone is high priority.
- What action to take.
- How to submit post-action feedback.

Uses:

- Recommendation table.
- Zone details drawer.
- Feedback form.

### 5.4 Hackathon Judge

Needs to see:

- Clear problem fit.
- Data-driven insight.
- Novelty beyond generic AI heatmap.
- Technical depth.
- Honest handling of limitations.
- Working frontend and backend.

Uses:

- Full demo flow.

---

## 6. Dataset Understanding

### 6.1 Dataset Type

The dataset is a police parking violation event log.

Each row represents a recorded violation event, not necessarily every illegal parking event that happened in the city.

### 6.2 Core Columns Expected

The CSV may include columns such as:

```text
latitude
longitude
created_datetime
modified_datetime
vehicle_number
vehicle_type
updated_vehicle_type
violation_type
offence_code
police_station
junction_name
location
validation_status
validation_timestamp
device_id
created_by_id
data_sent_to_scita
data_sent_to_scita_timestamp
description
closed_datetime
action_taken_timestamp
```

### 6.3 Critical Data Findings

The implementation must explicitly audit and display these truths:

1. The dataset has approximately 298,450 rows.
2. The actual date range is approximately Nov 2023 to Apr 2024.
3. The filename may say Jan-May, but internal references should clarify actual date range.
4. `description`, `closed_datetime`, and `action_taken_timestamp` are fully null.
5. There is no direct outcome data:
   - no towing confirmation,
   - no road cleared status,
   - no obstruction duration,
   - no measured congestion relief.
6. Evening enforcement records are extremely sparse compared with morning/midday records.
7. Therefore, the dataset is an enforcement visibility record, not complete illegal-parking ground truth.

### 6.4 Data Interpretation Principle

The system must follow this rule:

```text
No challan ≠ no illegal parking.
No challan may mean no enforcement visibility.
```

---

## 7. Core Metrics and Scores

## 7.1 Parking-Induced Flow Disruption Index (PFDI)

PFDI is a proxy for estimated parking-induced traffic-flow disruption.

It is not measured speed loss.

PFDI uses:

- Violation severity.
- Vehicle obstruction footprint.
- Location criticality.
- Repeat pressure.
- Evidence confidence.

### 7.1.1 Violation Severity

Each row may contain multiple violation labels.

Use compounding:

```text
ViolationSeverity_i = 1 - Π(1 - weight_c)
```

Example:

```text
Wrong parking = 0.65
Parking in main road = 0.95

Combined severity =
1 - (1 - 0.65)(1 - 0.95)
= 0.9825
```

Recommended weights:

| Violation Type | Weight |
|---|---:|
| Double parking | 1.00 |
| Parking in main road | 0.95 |
| Parking near road crossing | 0.90 |
| Parking near traffic light / zebra crossing | 0.88 |
| Parking opposite another parked vehicle | 0.86 |
| Parking near bus stop / school / hospital | 0.85 |
| Parking other than bus stop | 0.75 |
| No parking | 0.70 |
| Wrong parking | 0.65 |
| Parking on footpath | 0.55 |
| Defective number plate | 0.15 |
| Minor other | 0.10 |

### 7.1.2 Vehicle Obstruction

Use `updated_vehicle_type` when available, otherwise `vehicle_type`.

| Vehicle Type | Weight |
|---|---:|
| HGV / lorry / tanker / private bus / BMTC/KSRTC bus | 1.00 |
| LGV / tempo / mini lorry | 0.90 |
| Maxi-cab / van | 0.85 |
| Car / jeep | 0.75 |
| Goods auto | 0.65 |
| Passenger auto | 0.58 |
| Scooter / motorcycle | 0.35 |
| Moped | 0.25 |
| Unknown / other | 0.60 |

### 7.1.3 Location Criticality

```text
LocationCriticality =
0.35 × NamedJunctionFlag
+ 0.25 × MainRoadFlag
+ 0.20 × CrossingOrSignalFlag
+ 0.15 × BusStopSchoolHospitalFlag
+ 0.05 × DoubleParkingFlag
```

Clamp to `[0, 1]`.

### 7.1.4 Evidence Quality

Use validation confidence, device trust, user trust, and station evidence quality.

```text
EvidenceQualityScore =
0.50 × ValidationConfidence
+ 0.25 × DeviceTrust
+ 0.15 × UserTrust
+ 0.10 × StationEvidenceQuality
```

Validation confidence:

| Validation Status | Confidence |
|---|---:|
| approved | 1.00 |
| unknown / NaN | 0.70 |
| created1 | 0.55 |
| processing | 0.55 |
| rejected | 0.25 |
| duplicate | 0.10 |

### 7.1.5 Repeat Pressure

Use only past history.

```text
RepeatPressure =
min(log(1 + previous_violations_of_same_vehicle) / log(11), 1)
```

### 7.1.6 Row Obstruction Score

```text
RowObstruction =
EvidenceQualityScore
× 100
× (
  0.42 × ViolationSeverity
+ 0.23 × VehicleObstruction
+ 0.20 × LocationCriticality
+ 0.10 × RepeatPressure
+ 0.05 × NamedJunctionFlag
)
```

### 7.1.7 Zone-Time PFDI

For zone `z` and time window `t`:

```text
RawImpact_z,t = Σ RowObstruction_i
```

Normalize:

```text
ObservedPFDI_z,t =
100 × log(1 + RawImpact_z,t) / log(1 + P99(RawImpact))
```

Clamp to 100.

---

## 8. Novel Features

These features are the key edge over generic submissions.

---

## 8.1 Enforcement Visibility Digital Twin

### Purpose

Estimate where enforcement was actually visible.

### Formula

For zone `z`, time `t`:

```text
Exposure_z,t =
0.25 × norm(log(1 + unique_devices_z,t))
+ 0.20 × norm(log(1 + unique_users_z,t))
+ 0.15 × norm(station_hour_activity_s,t)
+ 0.15 × norm(patrol_route_coverage_z,t)
+ 0.15 × norm(scita_success_rate_z,t)
+ 0.10 × norm(validation_coverage_z,t)
```

```text
CoverageGap_z,t = 1 - Exposure_z,t
```

### Product Output

Map layer:

```text
Blue = enforcement visibility
Purple = blind spot
Red = observed hotspot
```

### Judge Hook

> “CurbFlow models enforcement visibility before modeling parking risk.”

---

## 8.2 Patrol Myopia Index

### Purpose

Detect whether a police station’s enforcement is concentrated in a few repeated zones and time windows.

### Formula

```text
PatrolMyopia_s =
0.40 × Top10ZoneShare_s
+ 0.30 × MorningBias_s
+ 0.20 × (1 - ZoneCoverageEntropy_s)
+ 0.10 × (1 - DeviceDiversity_s)
```

### Output

Station cards:

```text
Station: Upparpet
Patrol Myopia: High
Top 10 zone concentration: 96%
Recommendation: add discovery patrols
```

### Judge Hook

> “We identify not only parking hotspots, but also enforcement blind spots caused by repetitive patrol behavior.”

---

## 8.3 Hidden Junction Basin Detection

### Purpose

Many records are tagged `No Junction`, but may be physically near named junctions.

### Method

1. Compute named junction centroids.
2. Assign nearby `No Junction` records to closest named junction if within 500m.
3. Weight by distance:

```text
hidden_junction_weight = exp(-distance_m / 500)
```

### Output

Junction basin risk:

```text
JunctionBasinPFDI =
NamedJunctionPFDI + nearby No-Junction spillover impact
```

### Judge Hook

> “CurbFlow detects the full spillover basin around junctions, not just the named junction point.”

---

## 8.4 Repeat-Vehicle Persistence Score

### Purpose

Distinguish one-time violations from recurring obstruction behavior.

### Metrics

```text
repeat_vehicle_share
same_vehicle_same_zone_6h_count
same_vehicle_different_zone_6h_count
persistence_score
repeat_vehicle_zone_entropy
```

### Formula

```text
PersistenceScore_z,t =
same_vehicle_same_zone_repeat_count_6h / max(unique_vehicle_count_z,t, 1)
```

### Judge Hook

> “We separate transient violations from persistent obstruction patterns.”

---

## 8.5 Device/User Evidence Trust Score

### Purpose

Not every violation record has equal evidence reliability.

### Bayesian Smoothing

For device `d`:

```text
SmoothedApprovalRate_d =
(approved_d + α × global_approval_rate) / (validated_d + α)
```

```text
SmoothedRejectRate_d =
(rejected_d + α × global_reject_rate) / (validated_d + α)
```

Use:

```text
α = 100
```

```text
DeviceTrust =
0.45 × SmoothedApprovalRate
+ 0.25 × (1 - SmoothedRejectRate)
+ 0.15 × (1 - TypeCorrectionRate)
+ 0.15 × ScitaSuccessRate
```

### Judge Hook

> “CurbFlow is evidence-quality aware; it does not blindly trust every record equally.”

---

## 8.6 Patrol Transition Graph

### Purpose

Reconstruct approximate patrol movement from sequential device/user records.

### Method

For each device or user:

```text
Sort records by time within same day.
For consecutive zone records A → B:
if Δt <= 3 hours:
    edge_weight += exp(-Δt / 2h)
```

### Output

```text
patrol_in_degree
patrol_out_degree
patrol_pagerank
patrol_route_coverage
near_patrol_but_uncovered_flag
```

### Judge Hook

> “We reconstruct patrol behavior from violation logs and recommend coverage expansion.”

---

## 8.7 Road Corridor Risk

### Purpose

Move from isolated points to traffic-corridor intelligence.

### Method

Extract normalized road name from `location`.

Aggregate:

```text
CorridorPFDI_r,t = Σ PFDI_z,t for zones on road r
```

### Output

Top risky corridors:

```text
Outer Ring Road
Mysore Road
Bellary Road
Hosur Road
Subedar Chatram Road
```

### Judge Hook

> “CurbFlow supports corridor-level traffic management, not just point heatmaps.”

---

## 8.8 Place-Type Context

### Purpose

Infer land-use context from `location` and `junction_name`.

### Place Types

```text
commercial_market
transit_node
institutional
airport_zone
religious_place
residential_layout
entertainment
unknown
```

### Judge Hook

> “We infer functional context directly from police text fields, without external data.”

---

## 9. Blind-Spot Risk

### 9.1 Static Potential

```text
StaticPotential =
0.30 × P90HistoricalPFDI
+ 0.15 × Recurrence
+ 0.15 × LocationCriticality
+ 0.12 × LargeVehicleShare
+ 0.10 × RepeatPersistence
+ 0.08 × JunctionBasinRisk
+ 0.05 × CorridorRisk
+ 0.05 × PatrolExpansionOpportunity
```

### 9.2 Peak Priority

```text
normal = 1.00
school/office peak = 1.20
evening peak = 1.40
```

### 9.3 Evening Severity Prior

Use as an operational prior, not a learned ground truth.

```text
normal window = 1.00
evening low-exposure window = 1.20 to 1.40
```

### 9.4 Uncertainty

```text
Uncertainty =
min(1, sqrt(1 / (1 + observations_in_same_zone_time_bucket)))
```

### 9.5 Final Blind-Spot Risk

```text
BlindSpotRisk =
StaticPotential
× CoverageGap
× PeakPriority
× EveningSeverityPrior
× Uncertainty
```

---

## 10. Machine Learning Architecture

## 10.1 Main Model

### Model Name

```text
BE-STHGT
Bias-Exposure Spatio-Temporal Heterogeneous Graph Transformer
```

### Core Concept

```text
Observed violations = latent illegal-parking risk × enforcement exposure
```

This prevents the model from learning:

```text
low evening records = low evening risk
```

Instead it learns:

```text
low evening records + low exposure = uncertain blind spot
```

---

## 10.2 Input Shape

```text
X ∈ R[B, L, N, F]
```

Where:

```text
B = batch size
L = lookback windows
N = active zones
F = features
```

Recommended:

```text
lookback_windows = 56
window_size = 3 hours
lookback_duration = 7 days
prediction_horizon = next 3 hours
```

---

## 10.3 Graph Types

### Zone-Level Graphs

```text
A_geo
A_station
A_pattern
A_vehicle
A_patrol
A_learned
```

### Heterogeneous Node Types

```text
zone
station
device
user
repeat_vehicle
junction
road_corridor
place_type
```

### Edge Types

```text
zone_near_zone
zone_belongs_to_station
zone_recorded_by_device
zone_recorded_by_user
repeat_vehicle_seen_in_zone
zone_in_junction_basin
zone_on_road_corridor
zone_has_place_type
patrol_transition_zone_to_zone
```

---

## 10.4 Model Architecture

```text
Zone-time sequence
        ↓
Feature projection
        ↓
Multi-relation graph block
        ↓
Learned adaptive adjacency
        ↓
Temporal transformer encoder
        ↓
Bias-exposure latent risk head
        ↓
Multi-task prediction heads
        ↓
Station-wise rank score
```

### Feature Projection

```text
Linear(F → hidden_dim)
hidden_dim = 128
```

### Multi-Relation Graph Block

For each graph relation `r`:

```text
H_r = A_r @ X @ W_r
```

Then:

```text
H = relation_attention(concat(H_r))
H = LayerNorm(H + residual)
```

### Adaptive Graph

```text
A_learned = softmax(ReLU(E1 @ E2.T))
```

### Temporal Transformer

```text
TransformerEncoder
layers = 3
heads = 4
hidden_dim = 128
dropout = 0.15
```

---

## 10.5 Model Outputs

For each active zone and next time window:

```text
latent_risk
observed_count_mu
observed_count_theta
predicted_pfdi
hotspot_probability
q90_pfdi
blindspot_score
station_rank_score
```

Observed count is modeled as:

```text
observed_mu = latent_risk × clamp(exposure, 0.05, 1.0)
```

---

## 10.6 Loss Function

```text
TotalLoss =
0.22 × NegativeBinomialObservedCountLoss
+ 0.20 × SmoothL1PFDILoss
+ 0.16 × FocalHotspotLoss
+ 0.16 × PairwiseStationRankLoss
+ 0.10 × PinballQ90Loss
+ 0.08 × ExposureConsistencyLoss
+ 0.08 × SpatialSmoothnessLoss
```

### Why These Losses

| Loss | Purpose |
|---|---|
| Negative Binomial | Handles overdispersed count data |
| SmoothL1 | Predicts PFDI robustly |
| Focal Loss | Handles rare severe hotspots |
| Pairwise Ranking | Optimizes top-K enforcement ranking |
| Pinball Q90 | Estimates worst-case risk |
| Exposure Consistency | Avoids treating low-exposure zeros as safe |
| Spatial Smoothness | Stabilizes neighboring zone predictions |

---

## 10.7 LightGBM LambdaRank Ensemble

The deep model is ensembled with a tabular ranker.

```text
FinalRisk =
0.65 × BE_STHGT_score
+ 0.25 × LightGBM_LambdaRank_score
+ 0.10 × RuleBlindspot_score
```

### Why Ensemble

The dataset is sparse and tabular. LightGBM helps capture strong engineered features, while BE-STHGT captures graph-temporal structure and bias-exposure behavior.

---

## 11. Planner

## 11.1 Planner Modes

| Mode | Exploit Weight | Explore Weight | Use Case |
|---|---:|---:|---|
| Conservative | 0.85 | 0.15 | Known hotspot enforcement |
| Balanced | 0.70 | 0.30 | Standard deployment |
| Discovery | 0.55 | 0.45 | Blind-spot auditing |

### Exploit Risk

```text
ExploitRisk =
0.45 × PredictedPFDI
+ 0.25 × HotspotProbability
+ 0.15 × Recurrence
+ 0.10 × LocationCriticality
+ 0.05 × RepeatPressure
```

### Explore Risk

```text
ExploreRisk =
0.45 × BlindSpotRisk
+ 0.25 × StaticPotential
+ 0.20 × CoverageGap
+ 0.10 × OperationalPeakPriority
```

### Deployment Priority

```text
DeploymentPriority =
exploit_weight × ExploitRisk
+ explore_weight × ExploreRisk
```

---

## 11.2 Recommended Actions

| Action | Trigger |
|---|---|
| Beat patrol | Medium-high risk, routine enforcement |
| Towing support | Large vehicle, double parking, main road obstruction |
| Mobile camera patrol | High repeat pressure, high volume |
| Repeat-offender check | High persistence or repeat-vehicle share |
| Temporary cones | Recurring junction/crossing/bus-stop obstruction |
| Evening audit patrol | High blindspot risk in evening low-exposure windows |
| Patrol expansion | Near existing patrol route but under-covered |
| Evidence-quality audit | High rejection rate, low SCITA success, high correction rate |

---

## 12. API Requirements

Backend uses FastAPI.

### 12.1 Routes

```text
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
```

### 12.2 PII/Privacy Guardrail

API must not return:

```text
vehicle_number
device_id
created_by_id
```

Only aggregate intelligence is allowed.

### 12.3 Example Planner Request

```json
{
  "police_station": "Upparpet",
  "window_start": "2024-04-05T15:00:00+05:30",
  "available_officers": 20,
  "available_tow_units": 4,
  "mode": "balanced"
}
```

### 12.4 Example Planner Response

```json
{
  "summary": {
    "mode": "balanced",
    "known_hotspot_allocations": 14,
    "blindspot_audit_allocations": 6,
    "expected_risk_coverage": 0.73
  },
  "recommendations": [
    {
      "rank": 1,
      "zone_id": "zone_102_88",
      "risk_score": 94.2,
      "blindspot_score": 12.1,
      "recommended_action": "towing_support",
      "officers": 2,
      "tow_units": 1,
      "reason": [
        "High predicted PFDI",
        "High main-road obstruction",
        "High large-vehicle share"
      ]
    }
  ]
}
```

---

## 13. Frontend Requirements

Frontend uses:

```text
Next.js
TypeScript
TailwindCSS
shadcn/ui
TanStack Query
MapLibre GL
deck.gl
Recharts
Zustand
```

### 13.1 Pages

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

---

## 13.2 Page Requirements

### `/audit`

Must show:

- Total records.
- Actual date range.
- Null outcome columns.
- Morning count.
- Evening count.
- Evening gap ratio.
- SCITA success rate.
- Station-level Patrol Myopia Index.
- Hour-of-day bar chart.
- Warning that low evening data means low evidence, not low risk.

### `/hotspots`

Must show:

- Observed PFDI map.
- Red/orange/yellow risk scale.
- Top hotspot table.
- Zone details drawer.

### `/blindspots`

Must show:

- Purple blindspot map.
- Coverage gap.
- Static potential.
- Evening audit priority.
- Explanation that blindspots are audit priorities, not proven hotspots.

### `/junction-basins`

Must show:

- Named junction risk.
- Hidden No-Junction spillover.
- Junction basin PFDI.
- Table of top junction basins.

### `/patrol-digital-twin`

Must show:

- Patrol Myopia Index.
- Patrol route coverage.
- Under-covered nearby zones.
- Station cards.

### `/planner`

Must show:

- Police station selector.
- Time window selector.
- Officer/tow resource inputs.
- Conservative/balanced/discovery mode.
- Recommendation table.
- Resource usage summary.
- Map of recommended zones.

### `/metrics`

Must show:

- Baseline metrics.
- LightGBM metrics.
- BE-STHGT metrics.
- Ensemble metrics.
- Model card caveats.

---

## 14. Data Pipeline

### 14.1 Pipeline Stages

```text
Raw CSV
  ↓
Preprocess and timestamp conversion
  ↓
Data quality and bias audit
  ↓
Violation parsing
  ↓
PFDI row scoring
  ↓
300m zone assignment
  ↓
Novel feature extraction
  ↓
Zone-time aggregation
  ↓
Exposure and blindspot scoring
  ↓
Graph construction
  ↓
Deep model training
  ↓
LightGBM ranker training
  ↓
Ensemble prediction
  ↓
Planner recommendation generation
  ↓
DuckDB seeding
  ↓
FastAPI + Next.js dashboard
```

### 14.2 Output Artifacts

```text
data/interim/violations_clean.parquet
data/interim/row_scores.parquet
data/interim/zone_assignments.parquet
data/interim/graph_edges.parquet

data/processed/zones.geojson
data/processed/zone_static_features.parquet
data/processed/zone_time_features.parquet
data/processed/model_training_table.parquet
data/processed/predictions.parquet
data/processed/recommendations.parquet
data/processed/coverage_audit.parquet

data/app/curbflow.duckdb

artifacts/models/be_sthgt_model.pt
artifacts/models/ranker_lgbm.txt
artifacts/models/scaler.pkl
artifacts/models/model_metadata.json

artifacts/metrics/metrics.json
artifacts/metrics/station_metrics.json
artifacts/metrics/model_card.md

artifacts/reports/data_quality_report.md
artifacts/reports/bias_audit_report.md
artifacts/reports/eda_summary.json
```

---

## 15. Evaluation

### 15.1 Model Metrics

Primary metrics:

```text
Precision@5
Precision@10
NDCG@5
NDCG@10
Station-wise Precision@5
```

Secondary metrics:

```text
MAE PFDI
WAPE count
Hotspot AUC
Calibration error
```

### 15.2 Why Ranking Metrics Matter

Traffic police do not need a perfect prediction for every road.

They need:

```text
Which top 5–10 zones should we cover next?
```

Therefore, top-K ranking metrics are more important than RMSE alone.

### 15.3 Baselines

Compare against:

1. Historical same-slot average.
2. Last-week same-slot value.
3. Count-only heatmap baseline.
4. Rule-based PFDI baseline.
5. LightGBM ranker.
6. BE-STHGT.
7. BE-STHGT + LightGBM ensemble.

---

## 16. Feedback Loop

The historical dataset has no outcome fields.

CurbFlow AI adds a feedback form so future deployments can record:

```text
zone_id
window_start
police_station
action_taken
officers_deployed
tow_units_used
vehicles_found
vehicles_removed
vehicles_towed
road_cleared
approx_queue_length_m
notes
```

This enables future learning:

```text
action_effectiveness = observed outcome / predicted risk
```

The feedback loop is not required for initial model training, but it is essential for product completeness.

---

## 17. Non-Functional Requirements

### 17.1 Performance

- API should load dashboard data from DuckDB/Parquet, not raw CSV.
- GeoJSON responses should be cacheable.
- Frontend should load main dashboard in under a few seconds for demo.
- Model training may be offline.

### 17.2 Reliability

- Pipeline stages should be independently runnable.
- Missing optional columns should not crash the system.
- All major outputs should be validated before seeding DB.

### 17.3 Privacy

Do not expose:

```text
vehicle_number
device_id
created_by_id
```

Only aggregate repeat/device/user intelligence should be visible.

### 17.4 Explainability

Every recommendation should include explanation bullets.

Example:

```text
Recommended action: towing_support
Reasons:
- High predicted PFDI
- High main-road parking share
- High large-vehicle obstruction
- Strong historical recurrence
```

---

## 18. Technical Stack

### Backend

```text
Python
FastAPI
Pydantic
DuckDB
Pandas
PyArrow
LightGBM
CatBoost optional
PyTorch
NetworkX
Shapely
```

### Frontend

```text
Next.js
TypeScript
TailwindCSS
shadcn/ui
TanStack Query
MapLibre GL
deck.gl
Recharts
Zustand
Lucide Icons
```

### Storage

```text
CSV raw input
Parquet intermediate outputs
DuckDB app database
Model artifacts in artifacts/models
```

---

## 19. Milestones

### Milestone 1 — Data Foundation

- Repo scaffold.
- Configs.
- CSV loading.
- Timestamp conversion.
- Data audit.
- Bias audit.

### Milestone 2 — PFDI and Zones

- Violation parser.
- Vehicle obstruction.
- Location criticality.
- Evidence quality.
- Repeat pressure.
- Row obstruction score.
- 300m zones.
- Zones GeoJSON.

### Milestone 3 — Novel Features

- Enforcement visibility.
- Coverage gap.
- Blindspot risk.
- Patrol Myopia Index.
- Hidden junction basin.
- Repeat-vehicle persistence.
- Device/user trust.
- Patrol transition graph.
- Road corridor risk.
- Place-type context.

### Milestone 4 — ML

- Zone-time table.
- Sequence dataset.
- BE-STHGT model.
- Deep training.
- LightGBM LambdaRank.
- Ensemble predictions.
- Metrics.

### Milestone 5 — Planner

- Exploit/explore score.
- Action rules.
- Resource optimizer.
- Recommendation explanations.

### Milestone 6 — Backend

- DuckDB seeding.
- FastAPI routes.
- API tests.
- Privacy filtering.

### Milestone 7 — Frontend

- Audit page.
- Hotspot map.
- Blindspot map.
- Junction basin page.
- Patrol digital twin.
- Planner.
- Metrics page.

### Milestone 8 — Demo Polish

- Demo presets.
- README.
- Model card.
- Demo script.
- Judge FAQ.
- Final screenshots.

---

## 20. Risks and Mitigations

### Risk 1: Evening Data Collapse

**Problem:** Evening labels are sparse.

**Mitigation:** Treat evening outputs as blindspot audit priorities, not validated predictions.

### Risk 2: No Congestion Ground Truth

**Problem:** Dataset has no speed or travel-time labels.

**Mitigation:** Use PFDI as a proxy and clearly state it is not measured congestion.

### Risk 3: No Outcome Columns

**Problem:** No action result, towing result, or road cleared data.

**Mitigation:** Add feedback capture module for future learning.

### Risk 4: Sparse Zone-Time Grid

**Problem:** Many zone-time windows have zero records.

**Mitigation:** Train on active zones and use exposure-weighted zero labels.

### Risk 5: PII Exposure

**Problem:** Vehicle/device/user identifiers exist.

**Mitigation:** Use only aggregate repeat/device/user features in API and UI.

### Risk 6: Complex Model Overhead

**Problem:** BE-STHGT may be heavy for hackathon time.

**Mitigation:** Keep LightGBM ranker and rule-based blindspot engine as reliable fallback.

---

## 21. Demo Flow

### Step 1 — Open with Problem

> “Most parking AI systems detect violations. CurbFlow solves the next problem: where enforcement should go when the data itself is biased by patrol visibility.”

### Step 2 — Data Audit

Show:

- 298k records.
- Actual date range.
- Fully null outcome columns.
- Morning-heavy enforcement.
- Sparse evening visibility.

Say:

> “This is not just parking data. It is enforcement visibility data.”

### Step 3 — Observed Hotspots

Show red hotspot map.

Click a zone.

Show:

- PFDI.
- Violation mix.
- Vehicle mix.
- Evidence confidence.
- Recommended action.

### Step 4 — Hidden Junction Basin

Show how `No Junction` spillover records are assigned to nearby named junctions.

Say:

> “We detect the basin around a junction, not just the junction label.”

### Step 5 — Blind Spots

Show purple evening blindspot map.

Say:

> “A normal model would mark these areas safe. CurbFlow marks them as low-evidence audit priorities.”

### Step 6 — Patrol Digital Twin

Show Patrol Myopia Index and station coverage gaps.

Say:

> “We identify where enforcement is repeating the same loops and missing nearby zones.”

### Step 7 — Planner

Input:

```text
20 officers
4 tow units
Balanced mode
```

Show:

- Known hotspot deployments.
- Blindspot audit deployments.
- Towing support zones.
- Repeat-offender check zones.

### Step 8 — Metrics

Show model comparison:

```text
Baseline vs LightGBM vs BE-STHGT vs Ensemble
```

### Step 9 — Closing

> “CurbFlow turns police violation records into a bias-aware enforcement intelligence layer — identifying what is visible, what is hidden, and where action should go next.”

---

## 22. Judge FAQ

### Q1. Are you measuring real congestion?

No. The dataset does not contain speed, flow, or travel-time labels. We compute PFDI, a proxy for parking-induced flow disruption based on violation severity, vehicle obstruction, location criticality, repeat behavior, and evidence quality.

### Q2. Why not just use a heatmap?

A heatmap confuses enforcement visibility with actual risk. CurbFlow estimates where enforcement was visible and where it was not, then separates observed hotspots from blind spots.

### Q3. How do you handle sparse evening data?

We do not treat evening zeros as safe. We treat them as low-evidence windows and recommend audit patrols when static potential and coverage gap are high.

### Q4. Why use a graph model?

Illegal parking is spatial, temporal, and operational. Zones are connected by geography, police station, repeat vehicles, patrol transitions, junction basins, and road corridors. A graph model captures these relationships better than a flat model.

### Q5. How do you avoid leakage?

Repeat pressure uses only previous vehicle history. Train/validation/test splits are chronological. Scalers are fit only on training data.

### Q6. Why include LightGBM if you have a deep model?

The data has strong tabular features and sparse labels. LightGBM improves ranking accuracy, while BE-STHGT captures graph-temporal and exposure-bias structure. The ensemble is more robust.

### Q7. What would improve the system in production?

Add live patrol data, traffic speed/volume data, towing outcomes, road-cleared feedback, camera detections, and actual congestion measurements.

---

## 23. Setup Commands

### Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Data

Place CSV here:

```text
data/raw/police_parking_violations_nov2023_apr2024.csv
```

### Pipeline

```bash
make full
make db
```

### API

```bash
make api
```

or:

```bash
uvicorn apps.api.main:app --reload --port 8000
```

### Frontend

```bash
cd apps/web
npm install
npm run dev
```

---

## 24. Guardrails

CurbFlow AI must always follow these guardrails:

```text
Do not claim exact traffic speed reduction.
Do not claim measured congestion.
PFDI is a proxy, not ground-truth traffic delay.
No challan does not mean no illegal parking.
Evening outputs are audit priorities, not validated evening predictions.
validation_status NaN is unknown confidence, not rejection.
Repeat pressure uses past history only.
Train/test split is chronological.
Raw vehicle/device/user IDs are never exposed to frontend.
ASTraM data is not used in Theme 1.
```

---

## 25. Final Architecture Diagram

```text
Police Violation CSV
        ↓
Data Quality + Bias Audit
        ↓
PFDI Scoring Engine
        ↓
300m Zone Assignment
        ↓
Novel Feature Layer
    ├─ Enforcement Visibility
    ├─ Patrol Myopia
    ├─ Hidden Junction Basins
    ├─ Repeat-Vehicle Persistence
    ├─ Evidence Trust
    ├─ Patrol Transition Graph
    ├─ Road Corridor Risk
    └─ Place-Type Context
        ↓
Zone-Time Feature Table
        ↓
Multi-Relation + Heterogeneous Graph Builder
        ↓
BE-STHGT Deep Model
        ↓
LightGBM LambdaRank Ensemble
        ↓
Observed Hotspots + Blind Spots
        ↓
Resource-Constrained Planner
        ↓
FastAPI Backend
        ↓
Next.js Dashboard
        ↓
Officer Feedback Loop
```

---

## 26. Final Success Criteria

The project is successful if the demo can show:

1. A truthful data audit.
2. Observed hotspot map.
3. Blindspot map.
4. Hidden junction basin detection.
5. Patrol Myopia Index.
6. Repeat-vehicle persistence insight.
7. Evidence-quality-aware PFDI.
8. Resource-constrained planner.
9. BE-STHGT + LightGBM model metrics.
10. Clear explanation that the system handles enforcement bias instead of ignoring it.

Final pitch:

> **CurbFlow AI turns parking violation logs into a bias-aware traffic-police decision system. It identifies where illegal parking is visible, where it is hidden, and where enforcement should go next.**
