# Judge FAQ

## How do you measure congestion?

We do not claim measured congestion or exact traffic speed reduction. CurbFlow computes PFDI, a proxy for parking-induced flow disruption, from violation severity, vehicle obstruction, location criticality, repeat behavior, and evidence confidence.

The system is designed for enforcement prioritization when direct speed sensors or full traffic-flow observations are not available.

## Why make evening recommendations if evening data is sparse?

CurbFlow does not treat sparse evening data as reliable low-risk evidence. The audit shows very low evening enforcement visibility, so evening outputs are framed as blindspot audit priorities.

The recommendation is: send discovery patrols where static obstruction potential is high and enforcement visibility is low. It is not a claim that the model has validated evening violation rates.

## Why not just show a heatmap?

A heatmap shows where violations were recorded. That can be misleading because enforcement records are affected by where officers and devices already operate.

CurbFlow adds:

- exposure modeling
- coverage gap detection
- blindspot risk
- patrol myopia
- hidden junction basin spillover
- graph features
- resource-constrained planning

This turns a heatmap into an operational decision layer.

## What if validation status is missing?

Missing `validation_status` is treated as unknown confidence, not rejected evidence. Unknown records are downweighted, but they are not discarded or treated as false violations.

This matters because treating missing validation as rejection would create another bias in the dataset.

## How do you avoid leakage?

CurbFlow avoids leakage through several rules:

- chronological train, validation, and test splits only
- repeat pressure computed from previous vehicle history only
- no future rows used for current-row features
- `closed_datetime`, `action_taken_timestamp`, and `description` kept for audit only
- feature scaling fit on train split only
- next-window targets used for supervised training

## Why use a complex graph model?

Parking disruption is not only a row-level problem. It is spatial, temporal, and operational.

The graph model can represent:

- nearby zones
- station ownership
- repeated vehicle movement
- similar hourly and weekday patterns
- patrol transition routes
- corridor and junction context

BE-STHGT uses these relations while explicitly separating latent risk from enforcement exposure.

## Is this predicting illegal parking where there are no records?

No. CurbFlow distinguishes between observed hotspots and blindspot audit priorities.

Observed hotspots are based on recorded enforcement evidence. Blindspots are areas with high static potential and low visibility, so they are recommended for audit or discovery patrols rather than labeled as proven hotspots.

## Does this expose private vehicle or officer information?

No. Raw `vehicle_number`, `device_id`, and `created_by_id` are not returned by the API or UI. Repeat, device, and user intelligence is exposed only as aggregate features.

## What should the police do with this output?

Use CurbFlow as an operational prioritization layer:

- exploit known high-confidence hotspots
- explore blindspots where data is weak
- expand patrol routes near uncovered high-potential zones
- audit evidence quality where device or validation coverage is weak
- capture feedback after deployment for future action-effectiveness learning
