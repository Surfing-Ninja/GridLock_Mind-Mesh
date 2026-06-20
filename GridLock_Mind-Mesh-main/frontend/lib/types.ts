export type AuditSummary = {
  total_records?: number;
  actual_date_range?: { start_ist?: string; end_ist?: string; note?: string };
  null_outcome_columns?: Record<string, number>;
  morning_count?: number;
  evening_count?: number;
  evening_gap_ratio?: number;
  scita_success_rate?: number;
  warning?: string;
};

export type HourlyAudit = {
  hour: number;
  records: number;
  exposure: number;
  blindspot_risk: number;
};

export type ZonePoint = {
  zone_id: string;
  police_station: string;
  zone_center_lat: number;
  zone_center_lon: number;
  lat?: number;
  lon?: number;
  observed_pfdi?: number;
  final_risk_score?: number;
  hotspot_probability?: number;
  blindspot_risk?: number;
  coverage_gap?: number;
  static_potential?: number;
  exposure?: number;
  road_corridor?: string;
  place_type?: string;
};

export type PlannerResponse = {
  summary: {
    mode: string;
    known_hotspot_allocations: number;
    blindspot_audit_allocations: number;
    expected_risk_coverage: number;
    officers_used: number;
    tow_units_used: number;
  };
  recommendations: Array<{
    rank: number;
    zone_id: string;
    police_station: string;
    risk_score: number;
    blindspot_score: number;
    observed_pfdi: number;
    recommended_action: string;
    officers: number;
    tow_units: number;
    road_corridor: string;
    reason: string[];
    lat: number;
    lon: number;
  }>;
};
