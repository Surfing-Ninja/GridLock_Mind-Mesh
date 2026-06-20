# Model Card: BE-STHGT + LightGBM Ensemble

## Model Name

```text
BE-STHGT + LightGBM Ensemble
```

BE-STHGT is the **Bias-Exposure Spatio-Temporal Heterogeneous Graph Transformer**. It is ensembled with a LightGBM LambdaRank model and a rule-based blindspot score.

## Intended Use

The model is intended to support parking enforcement planning for Theme 1: Poor Visibility on Parking-Induced Congestion.

Primary uses:

- Rank zone-time windows for parking-induced flow disruption risk.
- Separate observed hotspot priority from enforcement visibility gaps.
- Identify blindspot audit candidates, especially in evidence-poor evening windows.
- Support station-wise resource allocation across officers and tow units.
- Provide aggregate operational intelligence for dashboards and planning.

## Not Intended Use

The model must not be used for:

- Claiming exact traffic speed reduction.
- Claiming measured congestion or measured travel-time loss.
- Legal adjudication of individual violations.
- Individual vehicle, device, or user monitoring.
- Automated punitive action without human review.
- Inferring that a no-challan zone has no illegal parking.
- Treating evening blindspot outputs as validated evening predictions.

## Inputs

The model uses only the Theme 1 police parking violation CSV and derived features.

Core row-level inputs:

- `created_datetime`, parsed as UTC and converted to `Asia/Kolkata`.
- `police_station`.
- `junction_name`.
- `location`.
- `latitude`, `longitude`.
- `violation_type`.
- `vehicle_type`, `updated_vehicle_type`.
- `validation_status`.
- `data_sent_to_scita`.
- `device_id` and `created_by_id` for aggregate evidence quality only.
- `vehicle_number` for anonymized repeat-pressure features only.

Derived inputs:

- PFDI row obstruction features.
- 300m grid zone assignments.
- Zone x 3-hour IST window aggregates.
- Evidence-quality trust scores.
- Enforcement exposure and coverage-gap features.
- Blindspot-risk features.
- Hidden junction basin features.
- Patrol myopia features.
- Repeat-vehicle persistence features.
- Road-corridor and place-type features.
- Geo, station, temporal-pattern, repeat-vehicle, and patrol-transition graph features.
- Lag and rolling PFDI features.

Fields not used as outcome labels:

- `closed_datetime`.
- `action_taken_timestamp`.
- `description`.

## Outputs

The ensemble writes `data/processed/predictions.parquet` with zone-window outputs including:

- `predicted_count`.
- `predicted_pfdi`.
- `hotspot_probability`.
- `q90_pfdi`.
- `latent_risk`.
- `exposure`.
- `coverage_gap`.
- `observed_risk_score`.
- `blindspot_risk_score`.
- `exploit_score`.
- `explore_score`.
- `deployment_priority_conservative`.
- `deployment_priority_balanced`.
- `deployment_priority_discovery`.
- `recommended_action`.
- `explanation_json`.

Planner outputs are written to `data/processed/recommendations.parquet`.

## Training Split

Training uses chronological splitting only:

```text
train: first 70 percent of windows
val:   next 15 percent of windows
test:  final 15 percent of windows
```

No random split is used.

The current fast-demo run produced:

```text
train rows: 36,647
val rows:   6,593
test rows:  6,436
```

Rank groups are formed by:

```text
police_station x window_start
```

## Model Components

### BE-STHGT

BE-STHGT models spatio-temporal zone risk with multiple graph relations:

- Geographic adjacency.
- Same-station adjacency.
- Temporal-pattern similarity.
- Repeat-vehicle graph.
- Patrol-transition graph.
- Learned adaptive adjacency.

The key bias-exposure relationship is:

```text
observed_mu = latent_risk * exposure
```

This explicitly prevents low observed counts in low-exposure windows from being treated as strong proof of low risk.

### LightGBM LambdaRank

The ranker uses engineered zone-time, exposure, blindspot, graph, patrol, repeat-persistence, corridor, and place-type features. It optimizes ranking quality within station-window groups.

### Rule Blindspot Score

The rule component preserves operational blindspot signals where model training evidence is sparse, especially evening low-exposure windows.

### Ensemble

Configured ensemble weights:

```text
BE-STHGT rank score:     0.65
LightGBM rank score:    0.25
Rule blindspot score:   0.10
```

In fast-demo mode, BE-STHGT training is skipped and the available dashboard artifacts are generated using the LightGBM/rule path.

## Metrics

Current available metrics are from the fast-demo LightGBM LambdaRank component.

Validation split:

```text
Precision@5:                  0.600
Precision@10:                 0.700
NDCG@5:                       0.635
NDCG@10:                      0.649
Station-wise Precision@5:     0.657
Rows:                         6,593
Groups:                       2,836
```

Test split:

```text
Precision@5:                  0.600
Precision@10:                 0.800
NDCG@5:                       0.723
NDCG@10:                      0.739
Station-wise Precision@5:     0.723
Rows:                         6,436
Groups:                       2,715
```

Baseline comparisons are stored in:

```text
artifacts/metrics/ranker_metrics.json
```

BE-STHGT metrics are generated when deep training is run and saved to:

```text
artifacts/metrics/deep_metrics.json
```

## Baseline Comparison

CurbFlow compares the ensemble against simple operational baselines so model value is not judged against an empty reference point.

Baseline methods:

- **Count-only baseline**: ranks zones by observed historical violation counts.
- **Historical PFDI baseline**: ranks zones by lagged and same-slot historical PFDI.
- **Rule-based blindspot baseline**: ranks audit candidates by static potential, coverage gap, and evening prior.
- **LightGBM LambdaRank**: ranks station-window candidates using engineered tabular features.
- **BE-STHGT deep model**: learns latent risk with exposure-aware observed intensity.
- **BE-STHGT + LightGBM ensemble**: combines deep rank score, LightGBM rank score, and rule blindspot score.

The fast-demo path always generates dashboard-ready baseline and LightGBM/rule artifacts. Deep-model comparison is included when `make train-deep` or the full pipeline with deep training has produced:

```text
artifacts/models/be_sthgt_model.pt
artifacts/metrics/deep_metrics.json
```

Primary comparison metrics:

- Precision@5 and Precision@10 for top deployment candidates.
- NDCG@5 and NDCG@10 for ranked station-window quality.
- Station-wise Precision@5 to avoid only optimizing city-wide aggregate performance.
- MAE PFDI and WAPE count for calibrated risk/count outputs.

Interpretation:

- A heatmap-style count baseline is useful for visible hotspots but cannot distinguish no-problem zones from no-visibility zones.
- The rule blindspot baseline protects sparse evening audit behavior from being erased by observed-count training labels.
- The ensemble is intended to combine visible disruption evidence with blindspot discovery, not to claim measured traffic-speed improvement.

## Known Limitations

- The source dataset is an enforcement visibility dataset, not a complete record of all illegal parking.
- PFDI is a proxy for parking-induced flow disruption, not measured traffic speed loss.
- The dataset does not provide measured queue length, speed, travel time, or actual congestion outcomes.
- `closed_datetime`, `action_taken_timestamp`, and `description` are fully null or unsuitable for outcome labels.
- Evening records are very sparse; evening outputs should be interpreted as audit priorities.
- Device and user fields support aggregate evidence-quality features only; raw IDs are not exposed.
- Location text can be noisy, abbreviated, or incomplete.
- Road-corridor and place-type extraction is text-derived and may be imperfect.
- Repeat-vehicle intelligence depends on anonymized vehicle consistency in the CSV.
- Fast-demo metrics do not represent a fully trained BE-STHGT model.

## Bias Handling

CurbFlow AI separates observed enforcement records from latent risk by modeling enforcement visibility.

Bias-handling mechanisms:

- Enforcement exposure score from devices, users, station activity, patrol coverage, SCITA success, and validation coverage.
- Coverage gap score as `1 - exposure`.
- Bias-corrected PFDI with conservative clipping to avoid inflating low-exposure windows too aggressively.
- Evidence-quality scores with Bayesian smoothing for devices, users, and stations.
- Patrol myopia index for station-level concentration and morning-heavy enforcement behavior.
- Blindspot risk that uses low visibility as uncertainty and audit priority, not automatic hotspot proof.
- Chronological split to avoid future leakage.
- Repeat pressure computed from previous vehicle history only.

## Evening Gap Handling

Evening enforcement data is sparse. The model therefore treats evening zero-violation windows as evidence-poor audit windows, not safe zones.

Evening handling includes:

- Evening peak priority multiplier.
- Evening severity prior for low-exposure windows.
- Coverage-gap and uncertainty terms.
- Blindspot explanations such as `evening_peak_audit` and `low_enforcement_visibility`.

Evening blindspot outputs are operational audit recommendations, not validated evening predictions.

## Privacy and Exposure Controls

The API and frontend must not expose:

- Raw vehicle numbers.
- Raw device IDs.
- Raw created-by user IDs.

Allowed outputs are aggregate zone, station, corridor, graph, and planner features.

## Guardrails

- We do not claim exact traffic speed reduction.
- We do not claim measured congestion.
- PFDI is a proxy for parking-induced flow disruption.
- No challan does not mean no illegal parking.
- Evening outputs are blindspot audit priorities.
- `validation_status` NaN is unknown confidence.
- Repeat pressure uses past history only.
- Train/test split is chronological.
- ASTraM is not used in Theme 1.
