"""Parameterized DuckDB queries for the API repository layer."""

from __future__ import annotations


AUDIT_SUMMARY = "SELECT * FROM audit_summary LIMIT 1"

HOURLY_AUDIT = "SELECT * FROM hourly_audit ORDER BY hour"

MODEL_METRICS = """
SELECT metric_source, metrics_json, source_path, updated_at
FROM model_metrics
ORDER BY metric_source
"""

PATROL_SUMMARY = """
WITH zone_station AS (
    SELECT
        zone_id,
        any_value(police_station) AS police_station
    FROM zone_time_features
    WHERE zone_id IS NOT NULL
    GROUP BY zone_id
),
zone_evening AS (
    SELECT
        police_station,
        sum(coalesce(record_count, 0)) AS zone_time_records,
        sum(
            CASE
                WHEN date_part('hour', window_start) >= 15
                 AND date_part('hour', window_start) <= 20
                THEN coalesce(record_count, 0)
                ELSE 0
            END
        ) AS evening_zone_records,
        avg(exposure) AS avg_exposure,
        avg(coverage_gap) AS avg_coverage_gap
    FROM zone_time_features
    WHERE police_station IS NOT NULL
    GROUP BY police_station
),
station_graph AS (
    SELECT
        zone_station.police_station,
        count(DISTINCT features.zone_id) AS patrol_feature_zones,
        sum(CASE WHEN coalesce(features.patrol_weighted_degree, 0) > 0 THEN 1 ELSE 0 END) AS patrol_connected_zones,
        sum(CASE WHEN coalesce(features.near_patrol_but_uncovered_flag, false) THEN 1 ELSE 0 END) AS nearby_uncovered_zones,
        avg(features.patrol_route_coverage) AS avg_patrol_route_coverage,
        max(features.patrol_pagerank) AS max_patrol_pagerank
    FROM patrol_graph_features AS features
    LEFT JOIN zone_station ON features.zone_id = zone_station.zone_id
    GROUP BY zone_station.police_station
)
SELECT
    coalesce(myopia.police_station, zone_evening.police_station, station_graph.police_station) AS police_station,
    coalesce(myopia.total_records, zone_evening.zone_time_records, 0) AS total_records,
    myopia.top_10_zone_share,
    coalesce(
        CASE
            WHEN coalesce(myopia.morning_records_0730_1530, 0) + coalesce(myopia.evening_records_1530_2030, 0) > 0
            THEN myopia.evening_records_1530_2030::DOUBLE
                 / (myopia.morning_records_0730_1530 + myopia.evening_records_1530_2030)
            ELSE NULL
        END,
        CASE
            WHEN coalesce(zone_evening.zone_time_records, 0) > 0
            THEN zone_evening.evening_zone_records::DOUBLE / zone_evening.zone_time_records
            ELSE NULL
        END
    ) AS evening_coverage,
    myopia.zone_coverage_entropy,
    myopia.morning_bias,
    myopia.device_diversity,
    myopia.user_diversity,
    myopia.patrol_myopia_index,
    myopia.patrol_myopia_level,
    coalesce(station_graph.patrol_feature_zones, 0) AS patrol_feature_zones,
    coalesce(station_graph.patrol_connected_zones, 0) AS patrol_connected_zones,
    coalesce(station_graph.nearby_uncovered_zones, 0) AS nearby_uncovered_zones,
    station_graph.avg_patrol_route_coverage,
    station_graph.max_patrol_pagerank,
    zone_evening.avg_exposure,
    zone_evening.avg_coverage_gap
FROM patrol_myopia AS myopia
FULL OUTER JOIN zone_evening ON myopia.police_station = zone_evening.police_station
FULL OUTER JOIN station_graph
    ON coalesce(myopia.police_station, zone_evening.police_station) = station_graph.police_station
WHERE (? IS NULL OR coalesce(myopia.police_station, zone_evening.police_station, station_graph.police_station) = ?)
ORDER BY patrol_myopia_index DESC NULLS LAST, total_records DESC NULLS LAST
LIMIT ?
"""

PATROL_ROUTES = """
WITH zone_station AS (
    SELECT
        zone_id,
        any_value(police_station) AS police_station,
        avg(coverage_gap) AS avg_coverage_gap,
        avg(static_potential) AS avg_static_potential
    FROM zone_time_features
    WHERE zone_id IS NOT NULL
    GROUP BY zone_id
),
edge_enriched AS (
    SELECT
        edges.from_zone_id,
        edges.to_zone_id,
        coalesce(from_station.police_station, to_station.police_station) AS police_station,
        coalesce(edges.patrol_transition_count, 0) AS patrol_transition_count,
        coalesce(edges.device_transition_count, 0) AS device_transition_count,
        coalesce(edges.user_transition_count, 0) AS user_transition_count,
        coalesce(edges.patrol_edge_weight, 0) AS patrol_edge_weight,
        CASE
            WHEN edges.device_mean_gap_hours IS NOT NULL AND edges.user_mean_gap_hours IS NOT NULL
            THEN (edges.device_mean_gap_hours + edges.user_mean_gap_hours) / 2
            ELSE coalesce(edges.device_mean_gap_hours, edges.user_mean_gap_hours)
        END AS mean_gap_hours,
        CASE
            WHEN edges.device_mean_distance_m IS NOT NULL AND edges.user_mean_distance_m IS NOT NULL
            THEN (edges.device_mean_distance_m + edges.user_mean_distance_m) / 2
            ELSE coalesce(edges.device_mean_distance_m, edges.user_mean_distance_m)
        END AS mean_distance_m,
        coalesce(from_features.patrol_route_coverage, 0) AS from_patrol_route_coverage,
        coalesce(to_features.patrol_route_coverage, 0) AS to_patrol_route_coverage,
        coalesce(from_features.patrol_weighted_degree, 0) AS from_patrol_weighted_degree,
        coalesce(to_features.patrol_weighted_degree, 0) AS to_patrol_weighted_degree,
        coalesce(from_features.near_patrol_but_uncovered_flag, false) AS from_near_patrol_but_uncovered,
        coalesce(to_features.near_patrol_but_uncovered_flag, false) AS to_near_patrol_but_uncovered,
        coalesce(from_station.avg_coverage_gap, to_station.avg_coverage_gap) AS avg_coverage_gap,
        coalesce(from_station.avg_static_potential, to_station.avg_static_potential) AS avg_static_potential
    FROM patrol_graph_edges AS edges
    LEFT JOIN patrol_graph_features AS from_features
        ON edges.from_zone_id = from_features.zone_id
    LEFT JOIN patrol_graph_features AS to_features
        ON edges.to_zone_id = to_features.zone_id
    LEFT JOIN zone_station AS from_station
        ON edges.from_zone_id = from_station.zone_id
    LEFT JOIN zone_station AS to_station
        ON edges.to_zone_id = to_station.zone_id
)
SELECT
    from_zone_id,
    to_zone_id,
    police_station,
    patrol_transition_count,
    device_transition_count,
    user_transition_count,
    patrol_edge_weight,
    mean_gap_hours,
    mean_distance_m,
    from_patrol_route_coverage,
    to_patrol_route_coverage,
    from_patrol_weighted_degree,
    to_patrol_weighted_degree,
    from_near_patrol_but_uncovered,
    to_near_patrol_but_uncovered,
    avg_coverage_gap,
    avg_static_potential,
    CASE
        WHEN from_near_patrol_but_uncovered OR to_near_patrol_but_uncovered
        THEN 'nearby_uncovered_zone'
        WHEN from_patrol_route_coverage >= 0.65 AND to_patrol_route_coverage >= 0.65
        THEN 'high_coverage_patrol_loop'
        ELSE 'frequent_transition'
    END AS route_category
FROM edge_enriched
WHERE (? IS NULL OR police_station = ?)
ORDER BY patrol_edge_weight DESC NULLS LAST, patrol_transition_count DESC NULLS LAST
LIMIT ?
"""

ZONE_DETAILS = """
WITH prediction_row AS (
    SELECT *
    FROM predictions
    WHERE zone_id = ?
      AND (? IS NULL OR window_start = CAST(? AS TIMESTAMP))
    ORDER BY window_start DESC
    LIMIT 1
),
feature_row AS (
    SELECT *
    FROM zone_time_features
    WHERE zone_id = ?
      AND (? IS NULL OR window_start = CAST(? AS TIMESTAMP))
    ORDER BY window_start DESC
    LIMIT 1
)
SELECT
    coalesce(prediction_row.zone_id, feature_row.zone_id) AS zone_id,
    coalesce(prediction_row.window_start, feature_row.window_start) AS window_start,
    coalesce(prediction_row.police_station, feature_row.police_station) AS police_station,
    prediction_row.predicted_count,
    prediction_row.predicted_pfdi,
    prediction_row.hotspot_probability,
    prediction_row.q90_pfdi,
    prediction_row.latent_risk,
    coalesce(prediction_row.exposure, feature_row.exposure) AS exposure,
    coalesce(prediction_row.coverage_gap, feature_row.coverage_gap) AS coverage_gap,
    prediction_row.observed_risk_score,
    coalesce(prediction_row.blindspot_risk_score, feature_row.blindspot_risk) AS blindspot_risk_score,
    prediction_row.exploit_score,
    prediction_row.explore_score,
    prediction_row.recommended_action,
    prediction_row.explanation_json,
    feature_row.observed_pfdi,
    feature_row.bias_corrected_pfdi,
    feature_row.static_potential,
    feature_row.record_count
FROM prediction_row
FULL OUTER JOIN feature_row
    ON prediction_row.zone_id = feature_row.zone_id
"""


def priority_column(mode: str = "balanced") -> str:
    """Return a safe deployment-priority column for mode."""

    normalized = str(mode or "balanced").strip().lower()
    if normalized not in {"conservative", "balanced", "discovery"}:
        normalized = "balanced"
    return f"deployment_priority_{normalized}"


def hotspots_query(mode: str = "balanced") -> str:
    """Return the parameterized hotspot query for a priority mode."""

    priority = priority_column(mode)
    return f"""
    SELECT
        zone_id,
        window_start,
        police_station,
        predicted_count,
        predicted_pfdi,
        hotspot_probability,
        q90_pfdi,
        coverage_gap,
        observed_risk_score,
        blindspot_risk_score,
        exploit_score,
        explore_score,
        {priority} AS deployment_priority,
        recommended_action,
        explanation_json
    FROM predictions
    WHERE (? IS NULL OR window_start = CAST(? AS TIMESTAMP))
      AND (? IS NULL OR police_station = ?)
    ORDER BY {priority} DESC, predicted_pfdi DESC, hotspot_probability DESC
    LIMIT ?
    """


def blindspots_query() -> str:
    """Return the parameterized blindspot query."""

    return """
    SELECT
        zone_id,
        window_start,
        police_station,
        predicted_pfdi,
        hotspot_probability,
        exposure,
        coverage_gap,
        blindspot_risk_score,
        explore_score,
        deployment_priority_discovery,
        recommended_action,
        explanation_json
    FROM predictions
    WHERE (? IS NULL OR window_start = CAST(? AS TIMESTAMP))
      AND (? IS NULL OR police_station = ?)
    ORDER BY blindspot_risk_score DESC, coverage_gap DESC, explore_score DESC
    LIMIT ?
    """


def recommendations_query() -> str:
    """Return the parameterized saved-recommendations query."""

    return """
    SELECT *
    FROM recommendations
    WHERE (? IS NULL OR window_start = CAST(? AS TIMESTAMP))
      AND (? IS NULL OR police_station = ?)
      AND (? IS NULL OR mode = ?)
    ORDER BY recommendation_rank ASC, expected_relief DESC
    LIMIT ?
    """


def scoped_prediction_features_query() -> str:
    """Return one-window prediction rows for on-demand planning fallback."""

    return """
    SELECT *
    FROM predictions
    WHERE (? IS NULL OR window_start = CAST(? AS TIMESTAMP))
      AND (? IS NULL OR police_station = ?)
    """


def scoped_zone_time_features_query() -> str:
    """Return one-window zone-time rows for on-demand planning fallback."""

    return """
    SELECT *
    FROM zone_time_features
    WHERE (? IS NULL OR window_start = CAST(? AS TIMESTAMP))
      AND (? IS NULL OR police_station = ?)
    """
