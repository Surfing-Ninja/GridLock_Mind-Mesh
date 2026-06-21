"""API request and response schemas for privacy-safe aggregate outputs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


PlannerMode = Literal["conservative", "balanced", "discovery"]


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    app_version: str
    model_loaded: bool
    ranker_model_available: bool = False
    deep_model_available: bool = False
    database_available: bool


class DebugFileStatus(BaseModel):
    """Artifact availability status for development diagnostics."""

    path: str
    exists: bool
    size_bytes: int | None = None


class DebugFilesResponse(BaseModel):
    """Development-only artifact availability response."""

    environment: str
    files: dict[str, DebugFileStatus]


class DateRange(BaseModel):
    """Dataset date range."""

    start: str | None = None
    end: str | None = None


class AuditSummaryResponse(BaseModel):
    """Bias-aware audit summary response."""

    row_count: int = 0
    date_range: DateRange = Field(default_factory=DateRange)
    null_outcome_columns: dict[str, bool] = Field(default_factory=dict)
    morning_count: int = 0
    evening_count: int = 0
    evening_gap_ratio: float | None = None
    active_zones: int | None = None
    top_zone_concentration: dict[str, Any] = Field(default_factory=dict)
    key_warning_message: str
    raw_summary: dict[str, Any] = Field(default_factory=dict)


class HourlyAuditRow(BaseModel):
    """Hour-of-day audit row."""

    hour: int
    record_count: int
    share: float | None = None


class RiskRow(BaseModel):
    """Generic hotspot/blindspot row."""

    model_config = ConfigDict(extra="allow")

    zone_id: str
    window_start: str | None = None
    police_station: str | None = None
    predicted_count: float | None = None
    predicted_pfdi: float | None = None
    hotspot_probability: float | None = None
    q90_pfdi: float | None = None
    exposure: float | None = None
    coverage_gap: float | None = None
    observed_risk_score: float | None = None
    blindspot_risk_score: float | None = None
    exploit_score: float | None = None
    explore_score: float | None = None
    deployment_priority: float | None = None
    deployment_priority_discovery: float | None = None
    recommended_action: str | None = None
    explanation_json: str | None = None


class PredictionWindowRow(BaseModel):
    """Timeline window available for map replay."""

    window_start: str
    zone_count: int | None = None
    sample_station: str | None = None
    avg_predicted_pfdi: float | None = None
    max_predicted_pfdi: float | None = None
    avg_coverage_gap: float | None = None
    max_blindspot_risk: float | None = None
    max_balanced_priority: float | None = None


class PlaceSuggestion(BaseModel):
    """Mappls place autosuggest result used for map focusing."""

    place_name: str
    place_address: str | None = None
    eloc: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    source: str = "mappls_autosuggest"


class MorningBriefRow(BaseModel):
    """Historical morning deployment brief row."""

    model_config = ConfigDict(extra="allow")

    zone_id: str
    zone_label: str | None = None
    police_station: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    pfdi_score: float | None = None
    total_violations: int | None = None
    repeat_offender_count: int | None = None
    large_vehicle_pct: float | None = None
    double_parking_instances: int | None = None
    dominant_vehicle_type: str | None = None
    dominant_violation: str | None = None
    recommended_action: str | None = None


class BlindspotHourlyVolumeRow(BaseModel):
    """Hour-of-day enforcement volume row for blindspot diagnosis."""

    hour: int
    record_count: int
    share: float | None = None


class StationShiftCutoffRow(BaseModel):
    """Station-level shift cutoff proxy row."""

    police_station: str
    median_last_hour: float | None = None
    evening_active_day_share: float | None = None
    total_officers: int | None = None
    officer_days: int | None = None


class CoverageGapRow(BaseModel):
    """Coverage-gap map row for station patrol myopia views."""

    model_config = ConfigDict(extra="allow")

    zone_id: str
    police_station: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    total_violations: int | None = None
    active_days: int | None = None
    coverage_pct: float | None = None
    last_seen: str | None = None
    peak_hour: int | None = None
    dominant_violation: str | None = None
    gap_level: str | None = None
    patrol_myopia_score: float | None = None
    top_3_zone_share: float | None = None
    morning_only_bias: float | None = None
    zone_coverage_entropy: float | None = None
    avg_pfdi: float | None = None


class PatrolStationSummary(BaseModel):
    """Station-level aggregate patrol digital twin summary."""

    model_config = ConfigDict(extra="allow")

    police_station: str | None = None
    total_records: int | None = None
    top_10_zone_share: float | None = None
    evening_coverage: float | None = None
    zone_coverage_entropy: float | None = None
    morning_bias: float | None = None
    device_diversity: float | None = None
    user_diversity: float | None = None
    patrol_myopia_index: float | None = None
    patrol_myopia_level: str | None = None
    patrol_feature_zones: int | None = None
    patrol_connected_zones: int | None = None
    nearby_uncovered_zones: int | None = None
    avg_patrol_route_coverage: float | None = None
    max_patrol_pagerank: float | None = None
    avg_exposure: float | None = None
    avg_coverage_gap: float | None = None


class PatrolRouteRow(BaseModel):
    """Aggregate patrol transition edge row."""

    model_config = ConfigDict(extra="allow")

    from_zone_id: str | None = None
    to_zone_id: str | None = None
    police_station: str | None = None
    patrol_transition_count: int | None = None
    device_transition_count: int | None = None
    user_transition_count: int | None = None
    patrol_edge_weight: float | None = None
    mean_gap_hours: float | None = None
    mean_distance_m: float | None = None
    from_patrol_route_coverage: float | None = None
    to_patrol_route_coverage: float | None = None
    from_patrol_weighted_degree: float | None = None
    to_patrol_weighted_degree: float | None = None
    from_near_patrol_but_uncovered: bool | None = None
    to_near_patrol_but_uncovered: bool | None = None
    avg_coverage_gap: float | None = None
    avg_static_potential: float | None = None
    route_category: str | None = None


class ZoneDetailsResponse(BaseModel):
    """Zone detail response."""

    model_config = ConfigDict(extra="allow")

    zone_id: str | None = None
    window_start: str | None = None
    police_station: str | None = None


class PlannerRecommendationRequest(BaseModel):
    """Resource-constrained planner request."""

    window_start: str
    police_station: str | None = None
    available_officers: int = Field(ge=0)
    available_tow_units: int = Field(ge=0)
    mode: PlannerMode = "balanced"
    top_k: int = Field(default=50, ge=1, le=500)


class PlannerRecommendation(BaseModel):
    """Planner recommendation response row."""

    model_config = ConfigDict(extra="allow")

    recommendation_rank: int | None = None
    zone_id: str
    window_start: str | None = None
    police_station: str | None = None
    action: str
    action_category: str | None = None
    mode: PlannerMode | str | None = None
    expected_relief: float | None = None
    score_per_resource_unit: float | None = None
    officers_required: int | None = None
    tow_units_required: int | None = None
    explanation: str | None = None
    explanation_json: str | None = None


class FeedbackRequest(BaseModel):
    """Feedback capture request."""

    zone_id: str
    window_start: str
    police_station: str | None = None
    action_taken: str
    officers_deployed: int = Field(ge=0)
    tow_units_used: int = Field(ge=0)
    vehicles_found: int = Field(ge=0)
    vehicles_removed: int = Field(ge=0)
    vehicles_towed: int = Field(ge=0)
    road_cleared: bool
    approx_queue_length_m: float | None = Field(default=None, ge=0)
    notes: str | None = None


class FeedbackResponse(BaseModel):
    """Feedback write response."""

    feedback_id: str
    saved: bool


class ModelMetricsResponse(BaseModel):
    """Model metrics payload keyed by model source."""

    metrics: dict[str, Any] = Field(default_factory=dict)
