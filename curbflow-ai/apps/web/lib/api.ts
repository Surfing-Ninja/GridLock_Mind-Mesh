import type { PlannerMode } from "./store";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export type DateRange = {
  start?: string | null;
  end?: string | null;
};

export type AuditSummary = {
  row_count: number;
  date_range: DateRange;
  null_outcome_columns: Record<string, boolean>;
  morning_count: number;
  evening_count: number;
  evening_gap_ratio?: number | null;
  active_zones?: number | null;
  top_zone_concentration: Record<string, unknown>;
  key_warning_message: string;
  raw_summary?: Record<string, unknown>;
};

export type HourlyAuditRow = {
  hour: number;
  record_count: number;
  share?: number | null;
};

export type GeoJsonFeatureCollection = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    properties: Record<string, unknown>;
    geometry: Record<string, unknown> | null;
  }>;
};

export type RiskRow = {
  zone_id: string;
  window_start?: string | null;
  police_station?: string | null;
  predicted_count?: number | null;
  predicted_pfdi?: number | null;
  hotspot_probability?: number | null;
  q90_pfdi?: number | null;
  exposure?: number | null;
  coverage_gap?: number | null;
  observed_risk_score?: number | null;
  blindspot_risk_score?: number | null;
  exploit_score?: number | null;
  explore_score?: number | null;
  deployment_priority?: number | null;
  deployment_priority_discovery?: number | null;
  recommended_action?: string | null;
  explanation_json?: string | null;
  [key: string]: unknown;
};

export type PredictionWindowRow = {
  window_start: string;
  zone_count?: number | null;
  sample_station?: string | null;
  avg_predicted_pfdi?: number | null;
  max_predicted_pfdi?: number | null;
  avg_coverage_gap?: number | null;
  max_blindspot_risk?: number | null;
  max_balanced_priority?: number | null;
};

export type PatrolStationSummary = {
  police_station?: string | null;
  total_records?: number | null;
  top_10_zone_share?: number | null;
  evening_coverage?: number | null;
  zone_coverage_entropy?: number | null;
  morning_bias?: number | null;
  device_diversity?: number | null;
  user_diversity?: number | null;
  patrol_myopia_index?: number | null;
  patrol_myopia_level?: string | null;
  patrol_feature_zones?: number | null;
  patrol_connected_zones?: number | null;
  nearby_uncovered_zones?: number | null;
  avg_patrol_route_coverage?: number | null;
  max_patrol_pagerank?: number | null;
  avg_exposure?: number | null;
  avg_coverage_gap?: number | null;
  [key: string]: unknown;
};

export type PatrolRouteRow = {
  from_zone_id?: string | null;
  to_zone_id?: string | null;
  police_station?: string | null;
  patrol_transition_count?: number | null;
  device_transition_count?: number | null;
  user_transition_count?: number | null;
  patrol_edge_weight?: number | null;
  mean_gap_hours?: number | null;
  mean_distance_m?: number | null;
  from_patrol_route_coverage?: number | null;
  to_patrol_route_coverage?: number | null;
  from_patrol_weighted_degree?: number | null;
  to_patrol_weighted_degree?: number | null;
  from_near_patrol_but_uncovered?: boolean | null;
  to_near_patrol_but_uncovered?: boolean | null;
  avg_coverage_gap?: number | null;
  avg_static_potential?: number | null;
  route_category?: string | null;
  [key: string]: unknown;
};

export type MorningBriefRow = {
  zone_id: string;
  zone_label?: string | null;
  police_station?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  pfdi_score?: number | null;
  total_violations?: number | null;
  repeat_offender_count?: number | null;
  large_vehicle_pct?: number | null;
  double_parking_instances?: number | null;
  dominant_vehicle_type?: string | null;
  dominant_violation?: string | null;
  recommended_action?: string | null;
  [key: string]: unknown;
};

export type StationShiftCutoffRow = {
  police_station: string;
  median_last_hour?: number | null;
  evening_active_day_share?: number | null;
  total_officers?: number | null;
  officer_days?: number | null;
};

export type CoverageGapRow = {
  zone_id: string;
  police_station?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  total_violations?: number | null;
  active_days?: number | null;
  coverage_pct?: number | null;
  last_seen?: string | null;
  peak_hour?: number | null;
  dominant_violation?: string | null;
  gap_level?: string | null;
  patrol_myopia_score?: number | null;
  top_3_zone_share?: number | null;
  morning_only_bias?: number | null;
  zone_coverage_entropy?: number | null;
  avg_pfdi?: number | null;
  [key: string]: unknown;
};

export type ZoneDetails = RiskRow & {
  observed_pfdi?: number | null;
  bias_corrected_pfdi?: number | null;
  static_potential?: number | null;
  record_count?: number | null;
};

export type PlannerRequest = {
  window_start: string;
  police_station?: string;
  available_officers: number;
  available_tow_units: number;
  mode: PlannerMode;
  top_k?: number;
};

export type PlannerRecommendation = {
  recommendation_rank?: number | null;
  zone_id: string;
  window_start?: string | null;
  police_station?: string | null;
  action: string;
  action_category?: string | null;
  mode?: string | null;
  expected_relief?: number | null;
  score_per_resource_unit?: number | null;
  officers_required?: number | null;
  tow_units_required?: number | null;
  predicted_pfdi?: number | null;
  hotspot_probability?: number | null;
  coverage_gap?: number | null;
  blindspot_risk_score?: number | null;
  exploit_score?: number | null;
  explore_score?: number | null;
  explanation?: string | null;
  explanation_json?: string | null;
  [key: string]: unknown;
};

export type ModelMetricsResponse = {
  metrics: Record<string, unknown>;
};

export type FeedbackRequest = {
  zone_id: string;
  window_start: string;
  police_station?: string;
  action_taken: string;
  officers_deployed: number;
  tow_units_used: number;
  vehicles_found: number;
  vehicles_removed: number;
  vehicles_towed: number;
  road_cleared: boolean;
  approx_queue_length_m?: number | null;
  notes?: string;
};

function qs(params: Record<string, string | number | null | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getAuditSummary() {
  return request<AuditSummary>("/audit/summary");
}

export function getHourlyAudit() {
  return request<HourlyAuditRow[]>("/audit/hourly");
}

export function getZonesGeoJson(params: {
  layer?: string;
  window_start?: string;
  station?: string;
  mode?: PlannerMode;
} = {}) {
  return request<GeoJsonFeatureCollection>(`/zones/geojson${qs(params)}`);
}

export function getPredictionWindows(params: { station?: string; limit?: number } = {}) {
  return request<PredictionWindowRow[]>(`/zones/windows${qs(params)}`);
}

export function getHotspots(params: {
  window_start?: string;
  station?: string;
  top_k?: number;
  mode?: PlannerMode;
} = {}) {
  return request<RiskRow[]>(`/hotspots${qs(params)}`);
}

export function getBlindspots(params: {
  window_start?: string;
  station?: string;
  top_k?: number;
} = {}) {
  return request<RiskRow[]>(`/blindspots${qs(params)}`);
}

export function getPatrolSummary(params: {
  station?: string;
  top_k?: number;
} = {}) {
  return request<PatrolStationSummary[]>(`/patrol/summary${qs(params)}`);
}

export function getPatrolRoutes(params: {
  station?: string;
  top_k?: number;
} = {}) {
  return request<PatrolRouteRow[]>(`/patrol/routes${qs(params)}`);
}

export function getMorningBrief(params: {
  station: string;
  dow?: string | number;
  slot?: number;
  top_k?: number;
}) {
  return request<MorningBriefRow[]>(`/api/planner/morning-brief${qs(params)}`);
}

export function getBlindspotHourlyVolume() {
  return request<HourlyAuditRow[]>("/api/blindspots/hourly-volume");
}

export function getStationShiftCutoff(params: { top_k?: number } = {}) {
  return request<StationShiftCutoffRow[]>(`/api/blindspots/station-shift-cutoff${qs(params)}`);
}

export function getCoverageGaps(params: { station?: string; top_k?: number } = {}) {
  return request<CoverageGapRow[]>(`/api/hotspots/coverage-gaps${qs(params)}`);
}

export function getZoneDetails(zoneId: string, params: { window_start?: string } = {}) {
  return request<ZoneDetails>(`/zones/${encodeURIComponent(zoneId)}${qs(params)}`);
}

export function getPlannerRecommendations(payload: PlannerRequest) {
  return request<PlannerRecommendation[]>("/planner/recommend", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getModelMetrics() {
  return request<ModelMetricsResponse>("/metrics/model");
}

export function submitFeedback(payload: FeedbackRequest) {
  return request<{ feedback_id: string; saved: boolean }>("/feedback", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
