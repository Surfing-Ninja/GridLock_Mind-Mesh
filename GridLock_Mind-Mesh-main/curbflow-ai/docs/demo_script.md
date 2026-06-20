# CurbFlow AI Demo Script

## 5-Minute Walkthrough

### 0:00-0:30 Opening

“Most parking AI detects violations. CurbFlow solves the next problem: deciding where enforcement should go when data itself is biased by patrol visibility.”

CurbFlow AI is a bias-aware parking enforcement intelligence system. It does not simply show where challans were issued. It separates observed parking-risk signals from enforcement visibility gaps, then recommends where limited traffic-police resources should go next.

### 0:30-1:05 Data Audit

Open the **Audit** page.

Show:

- **298,450 records** from the Theme 1 police violation CSV.
- Actual date range: **November 2023 to April 2024**, not January to May.
- Fully null outcome columns: `description`, `closed_datetime`, and `action_taken_timestamp`.
- Morning-heavy enforcement pattern and sparse evening records.

Say:

“This dataset is an enforcement visibility dataset, not a complete record of every illegal parking event. The audit tells us where the data is strong and where it is evidence-poor.”

### 1:05-1:40 Observed Hotspots

Open the **Hotspots** page.

Show the red/orange map layer and select a known hotspot zone.

Say:

“These are observed hotspots. The PFDI score combines violation severity, vehicle obstruction, location criticality, repeat behavior, and evidence confidence. It is a proxy for parking-induced flow disruption, not a measured traffic speed loss.”

Point to:

- Predicted PFDI.
- Hotspot probability.
- Recommended action.
- Explanation JSON or reason text if visible.

### 1:40-2:10 Hidden Junction Basin

Open the **Junction Basins** page.

Show how records tagged as `No Junction` can still contribute to nearby named junction basins.

Say:

“Many records are tagged No Junction even when they are spatially close to named junctions. CurbFlow assigns these to junction basins to detect spillover around traffic-critical points.”

Emphasize that this uses only the police CSV latitude, longitude, and junction text fields.

### 2:10-2:45 Blindspots

Open the **Blindspots** page.

Show the purple blindspot audit map, especially evening audit candidates.

Say:

“No challan does not mean no problem.”

Then explain:

“A blindspot is a zone with high static obstruction potential but low enforcement visibility. CurbFlow does not mark it as a proven hotspot; it marks it as an audit priority.”

Point out:

- Coverage gap.
- Blindspot risk.
- Evening audit priority.
- Low evidence interpretation.

### 2:45-3:20 Patrol Digital Twin

Open the **Patrol Digital Twin** page.

Show:

- Patrol Myopia Index.
- Top 10 zone share.
- Evening coverage.
- Route coverage gaps.
- Nearby uncovered zones.

Say:

“Patrol Myopia Index measures whether a station’s enforcement is concentrated in a few repeated zones and time windows, potentially missing nearby risk zones.”

Then show route patterns:

“The patrol transition graph reconstructs aggregate route behavior from device and user transitions, but it never exposes raw device IDs or user IDs.”

### 3:20-4:10 Planner

Open the **Planner** page.

Use:

- Officers: **20**
- Tow units: **4**
- Mode: **balanced**

Click submit.

Show:

- Officers used.
- Tow units used.
- Known hotspot allocations.
- Blindspot audit allocations.
- Recommendation table.
- Map layer colored by action type.

Say:

“The planner balances exploitation of proven hotspots with exploration of under-covered blindspots under officer and towing constraints.”

Explain balanced mode:

“Balanced mode is designed to combine known hotspots with blindspot audits, so the system does not overfit only to places where enforcement was already visible.”

### 4:10-4:40 Model Metrics

Open the **Metrics** page.

Show:

- Historical baseline.
- LightGBM ranker.
- BE-STHGT deep model.
- BE-STHGT + LightGBM ensemble.

Say:

“The model stack combines engineered features, graph structure, and ranking. BE-STHGT explicitly models observed intensity as latent risk multiplied by enforcement exposure, while the LightGBM ranker provides a strong tabular ranking baseline.”

Emphasize:

“Evening blindspot outputs are audit recommendations, not validated evening predictions.”

### 4:40-5:00 Closing

“CurbFlow turns police violation records into a bias-aware enforcement intelligence layer — identifying what is visible, what is hidden, and where action should go next.”

End on the planner recommendations page or the main dashboard.

## Backup Answers For Judges

### How do you measure congestion?

We do not claim measured congestion or exact speed reduction. PFDI is a proxy for parking-induced flow disruption built from violation severity, vehicle obstruction, location criticality, repeat behavior, and evidence confidence. It helps prioritize enforcement action when direct speed or traffic-flow sensors are not available.

### Why evening predictions if evening data is sparse?

We do not treat sparse evening data as strong prediction ground truth. The audit shows evening enforcement records are evidence-poor, so CurbFlow handles evening outputs as blindspot audit priorities. The system recommends discovery patrols where static obstruction potential is high but enforcement visibility is low.

### Why not just heatmap?

A heatmap only shows where violations were recorded. That can over-reward places where patrols already go and hide places with low enforcement visibility. CurbFlow separates observed hotspots from coverage gaps, blindspots, patrol myopia, junction spillover, and resource-feasible enforcement plans.

### What if validation status is missing?

Missing `validation_status` is treated as unknown confidence, not rejected evidence. Unknown records are downweighted through evidence confidence, but they are not discarded as false violations. This avoids converting missing validation into a biased negative label.

### How do you avoid leakage?

The pipeline uses chronological splits only. Repeat pressure uses only previous vehicle history before the current row, never future rows. The null outcome columns are kept for audit but not used as labels. Targets are next-window targets, and feature scaling is fit only on the training split.

### Why complex graph model?

Parking disruption is spatial, temporal, and operational. Nearby zones, station boundaries, repeated vehicle movement, similar hourly patterns, junction basins, and patrol transitions all carry signal. BE-STHGT is designed to model those multiple relations while explicitly separating latent risk from enforcement exposure.
