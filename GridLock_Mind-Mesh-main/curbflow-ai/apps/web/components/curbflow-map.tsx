"use client";

import maplibregl from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import { Legend } from "@/components/legend";
import type { GeoJsonFeatureCollection } from "@/lib/api";
import type { PlannerMode } from "@/lib/store";
import { cn } from "@/lib/utils";

const SOURCE_ID = "curbflow-zones";
const POINT_SOURCE_ID = "curbflow-zone-centroids";
const LABEL_SOURCE_ID = "curbflow-zone-labels";
const HEAT_LAYER_ID = "curbflow-zones-heat";
const FILL_LAYER_ID = "curbflow-zones-fill";
const GLOW_LAYER_ID = "curbflow-zones-glow";
const POINT_LAYER_ID = "curbflow-zones-points";
const LINE_LAYER_ID = "curbflow-zones-line";
const HOVER_LAYER_ID = "curbflow-zones-hover";
const LABEL_LAYER_ID = "curbflow-zone-labels";
const SHADOW_GLOW_ID = "curbflow-shadow-glow";
const SHADOW_POINT_ID = "curbflow-shadow-point";
const TOOLTIP_WIDTH = 280;
const TOOLTIP_HEIGHT = 370;
const TOOLTIP_OFFSET = 16;
const TOOLTIP_EDGE_PADDING = 12;

type CurbFlowMapProps = {
  zones?: GeoJsonFeatureCollection;
  mode?: PlannerMode;
  variant?: "risk" | "blindspot" | "patrol" | "planner" | "coverageGap";
  onZoneClick?: (zoneId: string) => void;
  timeHour?: number | null;
  showShadow?: boolean;
  className?: string;
};

type MapTooltip = {
  x: number;
  y: number;
  zoneId: string;
  station: string;
  risk: number | null;
  pfdi: number | null;
  coverageGap: number | null;
  blindspotRisk: number | null;
  action: string;
  records: number | null;
  activeDays: number | null;
  coveragePct: number | null;
  peakHour: number | null;
  dominantViolation: string | null;
  gapLevel: string | null;
};

function emptyFeatureCollection(): GeoJsonFeatureCollection {
  return { type: "FeatureCollection", features: [] };
}

function priorityPropertyForMode(mode: PlannerMode) {
  return `deployment_priority_${mode}`;
}

function toNumberExpression(property: string, fallback = 0): unknown[] {
  return ["to-number", ["coalesce", ["get", property], fallback]];
}

function riskValueExpression(mode: PlannerMode): unknown[] {
  return [
    "to-number",
    [
      "coalesce",
      ["get", "deployment_priority"],
      ["get", priorityPropertyForMode(mode)],
      ["get", "predicted_pfdi"],
      0,
    ],
  ];
}

function riskFillColor(mode: PlannerMode): unknown[] {
  const risk = riskValueExpression(mode);
  return [
    "case",
    [">=", risk, 75],
    "rgb(185, 28, 28)",
    [">=", risk, 50],
    "rgb(234, 88, 12)",
    [">=", risk, 25],
    "rgb(217, 119, 6)",
    "rgb(37, 99, 235)",
  ];
}

function blindspotFillColor(): unknown[] {
  const blindspotRisk = [
    "to-number",
    ["coalesce", ["get", "blindspot_risk_score"], ["get", "blindspot_risk"], 0],
  ];
  const coverageGap = toNumberExpression("coverage_gap");
  return [
    "case",
    [">=", blindspotRisk, 45],
    "rgb(162, 28, 175)",
    [">=", blindspotRisk, 25],
    "rgb(147, 51, 234)",
    [">=", coverageGap, 0.65],
    "rgb(37, 99, 235)",
    "rgb(148, 163, 184)",
  ];
}

function coverageGapFillColor(): unknown[] {
  const coveragePct = toNumberExpression("coverage_pct", 1);
  const totalViolations = toNumberExpression("total_violations");
  return [
    "case",
    ["all", ["<", coveragePct, 0.2], [">=", totalViolations, 100]],
    "rgb(185, 28, 28)",
    ["all", ["<", coveragePct, 0.35], [">=", totalViolations, 80]],
    "rgb(234, 88, 12)",
    ["<", coveragePct, 0.35],
    "rgb(217, 119, 6)",
    "rgb(37, 99, 235)",
  ];
}

function patrolFillColor(): unknown[] {
  const weightedDegree = toNumberExpression("patrol_weighted_degree");
  const routeCoverage = toNumberExpression("patrol_route_coverage");
  return [
    "case",
    ["==", ["get", "near_patrol_but_uncovered_flag"], true],
    "rgb(220, 38, 38)",
    [">", weightedDegree, 0],
    "rgb(37, 99, 235)",
    [">=", routeCoverage, 0.5],
    "rgb(37, 99, 235)",
    [">", routeCoverage, 0],
    "rgb(14, 165, 233)",
    "rgb(148, 163, 184)",
  ];
}

function plannerFillColor(): unknown[] {
  return [
    "case",
    ["!=", ["get", "planner_selected"], true],
    "rgb(148, 163, 184)",
    ["==", ["get", "planner_action"], "towing_support"],
    "rgb(185, 28, 28)",
    ["==", ["get", "planner_action"], "evening_audit_patrol"],
    "rgb(217, 119, 6)",
    ["==", ["get", "planner_action"], "patrol_expansion"],
    "rgb(13, 148, 136)",
    ["==", ["get", "planner_action"], "evidence_quality_audit"],
    "rgb(100, 116, 139)",
    ["==", ["get", "planner_action"], "temporary_cones"],
    "rgb(202, 138, 4)",
    ["==", ["get", "planner_action"], "repeat_offender_check"],
    "rgb(234, 88, 12)",
    ["==", ["get", "planner_action"], "mobile_camera_patrol"],
    "rgb(124, 58, 237)",
    "rgb(37, 99, 235)",
  ];
}

function fillColorForVariant(variant: NonNullable<CurbFlowMapProps["variant"]>, mode: PlannerMode) {
  if (variant === "blindspot") return blindspotFillColor();
  if (variant === "coverageGap") return coverageGapFillColor();
  if (variant === "patrol") return patrolFillColor();
  if (variant === "planner") return plannerFillColor();
  return riskFillColor(mode);
}

function lineColorForVariant(variant: NonNullable<CurbFlowMapProps["variant"]>) {
  if (variant === "blindspot") return "rgb(88, 28, 135)";
  if (variant === "coverageGap") return "rgb(124, 45, 18)";
  if (variant === "patrol") return "rgb(30, 64, 175)";
  if (variant === "planner") return "rgb(15, 23, 42)";
  return "rgb(124, 45, 18)";
}

function fillOpacityForVariant(variant: NonNullable<CurbFlowMapProps["variant"]>, mode: PlannerMode): unknown[] {
  if (variant === "blindspot") {
    const blindspotRisk = [
      "to-number",
      ["coalesce", ["get", "blindspot_risk_score"], ["get", "blindspot_risk"], 0],
    ];
    const coverageGap = toNumberExpression("coverage_gap");
    return [
      "case",
      [">=", blindspotRisk, 45],
      0.2,
      [">=", blindspotRisk, 25],
      0.13,
      [">=", coverageGap, 0.65],
      0.06,
      0.012,
    ];
  }
  if (variant === "patrol") {
    const weightedDegree = toNumberExpression("patrol_weighted_degree");
    const routeCoverage = toNumberExpression("patrol_route_coverage");
    return [
      "case",
      ["==", ["get", "near_patrol_but_uncovered_flag"], true],
      0.2,
      [">", weightedDegree, 0],
      0.08,
      [">=", routeCoverage, 0.5],
      0.08,
      [">", routeCoverage, 0],
      0.05,
      0.012,
    ];
  }
  if (variant === "coverageGap") {
    const coveragePct = toNumberExpression("coverage_pct", 1);
    const totalViolations = toNumberExpression("total_violations");
    return [
      "case",
      ["all", ["<", coveragePct, 0.2], [">=", totalViolations, 100]],
      0.2,
      ["<", coveragePct, 0.35],
      0.12,
      0.04,
    ];
  }
  if (variant === "planner") {
    return ["case", ["==", ["get", "planner_selected"], true], 0.42, 0.015];
  }
  const risk = riskValueExpression(mode);
  return ["interpolate", ["linear"], risk, 0, 0.01, 25, 0.025, 50, 0.08, 75, 0.16, 100, 0.22];
}

function glowOpacityForVariant(variant: NonNullable<CurbFlowMapProps["variant"]>, mode: PlannerMode): unknown[] {
  if (variant === "blindspot") {
    const blindspotRisk = [
      "to-number",
      ["coalesce", ["get", "blindspot_risk_score"], ["get", "blindspot_risk"], 0],
    ];
    return ["interpolate", ["linear"], blindspotRisk, 0, 0, 20, 0.08, 45, 0.24, 70, 0.38, 100, 0.48];
  }
  if (variant === "patrol") {
    const weightedDegree = toNumberExpression("patrol_weighted_degree");
    return ["interpolate", ["linear"], weightedDegree, 0, 0, 1, 0.12, 20, 0.28, 80, 0.42];
  }
  if (variant === "coverageGap") {
    const gap = ["-", 1, toNumberExpression("coverage_pct", 1)] as unknown[];
    return ["interpolate", ["linear"], gap, 0, 0.04, 0.4, 0.16, 0.7, 0.32, 1, 0.42];
  }
  if (variant === "planner") {
    return ["case", ["==", ["get", "planner_selected"], true], 0.28, 0];
  }
  const risk = riskValueExpression(mode);
  return ["interpolate", ["linear"], risk, 0, 0, 30, 0.03, 55, 0.12, 80, 0.24, 100, 0.34];
}

function pointOpacityForVariant(variant: NonNullable<CurbFlowMapProps["variant"]>, mode: PlannerMode): unknown[] {
  if (variant === "planner") return ["case", ["==", ["get", "planner_selected"], true], 0.88, 0];
  if (variant === "blindspot") {
    const blindspotRisk = [
      "to-number",
      ["coalesce", ["get", "blindspot_risk_score"], ["get", "blindspot_risk"], 0],
    ];
    return ["interpolate", ["linear"], blindspotRisk, 0, 0, 20, 0.14, 45, 0.58, 100, 0.85];
  }
  if (variant === "patrol") {
    return ["case", ["==", ["get", "near_patrol_but_uncovered_flag"], true], 0.86, 0.04];
  }
  if (variant === "coverageGap") {
    const gap = ["-", 1, toNumberExpression("coverage_pct", 1)] as unknown[];
    return ["interpolate", ["linear"], gap, 0, 0.18, 0.45, 0.58, 0.8, 0.88, 1, 0.95];
  }
  const risk = riskValueExpression(mode);
  return ["interpolate", ["linear"], risk, 0, 0, 40, 0, 60, 0.4, 80, 0.82, 100, 0.95];
}

function signalRadiusExpression(mode: PlannerMode): unknown[] {
  const risk = riskValueExpression(mode);
  return ["interpolate", ["linear"], risk, 0, 1.5, 30, 4, 55, 8, 80, 14, 100, 20];
}

function lineOpacityForVariant(variant: NonNullable<CurbFlowMapProps["variant"]>, mode: PlannerMode): unknown[] {
  void mode;
  if (variant === "planner") return ["case", ["==", ["get", "planner_selected"], true], 0.42, 0.02];
  if (variant === "blindspot") return ["interpolate", ["linear"], ["zoom"], 9, 0, 12, 0.04, 15, 0.16];
  if (variant === "coverageGap") return ["interpolate", ["linear"], ["zoom"], 9, 0.02, 12, 0.08, 15, 0.2];
  if (variant === "patrol") return ["interpolate", ["linear"], ["zoom"], 9, 0, 12, 0.035, 15, 0.14];
  return ["interpolate", ["linear"], ["zoom"], 9, 0, 12, 0.035, 15, 0.14];
}

function heatWeightForVariant(variant: NonNullable<CurbFlowMapProps["variant"]>, mode: PlannerMode): unknown[] {
  if (variant === "blindspot") {
    const blindspotRisk = [
      "to-number",
      ["coalesce", ["get", "blindspot_risk_score"], ["get", "blindspot_risk"], 0],
    ];
    return ["interpolate", ["linear"], blindspotRisk, 0, 0.16, 20, 0.34, 45, 0.72, 75, 0.96, 100, 1];
  }
  if (variant === "patrol") {
    const weightedDegree = toNumberExpression("patrol_weighted_degree");
    return [
      "case",
      ["==", ["get", "near_patrol_but_uncovered_flag"], true],
      0.95,
      [">", weightedDegree, 0],
      0.52,
      0.18,
    ];
  }
  if (variant === "coverageGap") {
    const gap = ["-", 1, toNumberExpression("coverage_pct", 1)] as unknown[];
    return ["interpolate", ["linear"], gap, 0, 0.12, 0.35, 0.45, 0.65, 0.78, 0.9, 1];
  }
  if (variant === "planner") {
    return ["case", ["==", ["get", "planner_selected"], true], 1, 0.02];
  }
  const risk = riskValueExpression(mode);
  return ["interpolate", ["linear"], risk, 0, 0.2, 20, 0.36, 45, 0.58, 70, 0.84, 100, 1];
}

function heatColorForVariant(variant: NonNullable<CurbFlowMapProps["variant"]>): unknown[] {
  if (variant === "blindspot") {
    return [
      "interpolate",
      ["linear"],
      ["heatmap-density"],
      0,
      "rgba(37, 99, 235, 0)",
      0.16,
      "rgba(37, 99, 235, 0.34)",
      0.38,
      "rgba(147, 51, 234, 0.50)",
      0.68,
      "rgba(162, 28, 175, 0.70)",
      1,
      "rgba(112, 26, 117, 0.90)",
    ];
  }
  if (variant === "patrol") {
    return [
      "interpolate",
      ["linear"],
      ["heatmap-density"],
      0,
      "rgba(14, 165, 233, 0)",
      0.2,
      "rgba(14, 165, 233, 0.32)",
      0.5,
      "rgba(37, 99, 235, 0.54)",
      0.78,
      "rgba(13, 148, 136, 0.62)",
      1,
      "rgba(220, 38, 38, 0.78)",
    ];
  }
  if (variant === "coverageGap") {
    return [
      "interpolate",
      ["linear"],
      ["heatmap-density"],
      0,
      "rgba(37, 99, 235, 0)",
      0.18,
      "rgba(37, 99, 235, 0.34)",
      0.42,
      "rgba(217, 119, 6, 0.50)",
      0.72,
      "rgba(234, 88, 12, 0.72)",
      1,
      "rgba(185, 28, 28, 0.90)",
    ];
  }
  if (variant === "planner") {
    return [
      "interpolate",
      ["linear"],
      ["heatmap-density"],
      0,
      "rgba(16, 185, 129, 0)",
      0.3,
      "rgba(16, 185, 129, 0.38)",
      0.6,
      "rgba(37, 99, 235, 0.58)",
      1,
      "rgba(234, 88, 12, 0.82)",
    ];
  }
  return [
    "interpolate",
    ["linear"],
    ["heatmap-density"],
    0,
    "rgba(37, 99, 235, 0)",
    0.12,
    "rgba(37, 99, 235, 0.34)",
    0.3,
    "rgba(14, 165, 233, 0.42)",
    0.52,
    "rgba(250, 204, 21, 0.54)",
    0.76,
    "rgba(249, 115, 22, 0.74)",
    1,
    "rgba(185, 28, 28, 0.92)",
  ];
}

function heatOpacityForVariant(variant: NonNullable<CurbFlowMapProps["variant"]>): unknown[] {
  if (variant === "planner") return ["interpolate", ["linear"], ["zoom"], 8, 0.62, 12, 0.58, 15, 0.46, 18, 0.32];
  return ["interpolate", ["linear"], ["zoom"], 8, 0.86, 12, 0.82, 15, 0.68, 17, 0.48, 19, 0.32];
}

function boostLabelReadability(map: maplibregl.Map) {
  for (const layer of map.getStyle().layers ?? []) {
    if (layer.type !== "symbol" || !layer.layout?.["text-field"]) continue;
    try {
      map.setPaintProperty(layer.id, "text-halo-color", "rgba(255, 255, 255, 0.96)");
      map.setPaintProperty(layer.id, "text-halo-width", 1.25);
      map.setPaintProperty(layer.id, "text-halo-blur", 0.2);
    } catch {
      // Some third-party basemap symbol layers have locked paint schemas.
    }
  }
}

function firstLabelLayerId(map: maplibregl.Map) {
  return map
    .getStyle()
    .layers?.find((layer) => layer.type === "symbol" && Boolean(layer.layout?.["text-field"]))?.id;
}

function applyZonePaint(
  map: maplibregl.Map,
  variant: NonNullable<CurbFlowMapProps["variant"]>,
  mode: PlannerMode,
) {
  if (!map.getLayer(FILL_LAYER_ID) || !map.getLayer(LINE_LAYER_ID)) return;
  if (map.getLayer(HEAT_LAYER_ID)) {
    map.setPaintProperty(HEAT_LAYER_ID, "heatmap-weight", heatWeightForVariant(variant, mode) as never);
    map.setPaintProperty(HEAT_LAYER_ID, "heatmap-color", heatColorForVariant(variant) as never);
    map.setPaintProperty(HEAT_LAYER_ID, "heatmap-opacity", heatOpacityForVariant(variant) as never);
  }
  map.setPaintProperty(FILL_LAYER_ID, "fill-color", fillColorForVariant(variant, mode) as never);
  map.setPaintProperty(FILL_LAYER_ID, "fill-opacity", fillOpacityForVariant(variant, mode) as never);
  map.setPaintProperty(LINE_LAYER_ID, "line-color", lineColorForVariant(variant));
  map.setPaintProperty(LINE_LAYER_ID, "line-opacity", lineOpacityForVariant(variant, mode) as never);
  map.setPaintProperty(LINE_LAYER_ID, "line-width", [
    "interpolate",
    ["linear"],
    ["zoom"],
    9,
    0.45,
    12,
    0.85,
    15,
    1.25,
  ] as never);
  if (map.getLayer(GLOW_LAYER_ID) && map.getLayer(POINT_LAYER_ID)) {
    map.setPaintProperty(GLOW_LAYER_ID, "circle-color", fillColorForVariant(variant, mode) as never);
    map.setPaintProperty(GLOW_LAYER_ID, "circle-opacity", glowOpacityForVariant(variant, mode) as never);
    map.setPaintProperty(GLOW_LAYER_ID, "circle-radius", signalRadiusExpression(mode) as never);
    map.setPaintProperty(POINT_LAYER_ID, "circle-color", fillColorForVariant(variant, mode) as never);
    map.setPaintProperty(POINT_LAYER_ID, "circle-opacity", pointOpacityForVariant(variant, mode) as never);
  }
}

function collectBounds(data?: GeoJsonFeatureCollection) {
  if (!data?.features.length) return null;
  const bounds = new maplibregl.LngLatBounds();
  let coordinateCount = 0;

  function visit(value: unknown) {
    if (!Array.isArray(value)) return;
    if (
      value.length >= 2 &&
      typeof value[0] === "number" &&
      typeof value[1] === "number" &&
      Number.isFinite(value[0]) &&
      Number.isFinite(value[1])
    ) {
      bounds.extend([value[0], value[1]]);
      coordinateCount += 1;
      return;
    }
    value.forEach(visit);
  }

  for (const feature of data.features) {
    visit(feature.geometry?.coordinates);
  }
  return coordinateCount > 0 ? bounds : null;
}

function numericProperty(properties: Record<string, unknown>, names: string[]) {
  for (const name of names) {
    const value = Number(properties[name]);
    if (Number.isFinite(value)) return value;
  }
  return null;
}

function geometryCentroid(geometry?: Record<string, unknown> | null): [number, number] | null {
  const coordinates = geometry?.coordinates;
  const points: Array<[number, number]> = [];

  function visit(value: unknown) {
    if (!Array.isArray(value)) return;
    if (
      value.length >= 2 &&
      typeof value[0] === "number" &&
      typeof value[1] === "number" &&
      Number.isFinite(value[0]) &&
      Number.isFinite(value[1])
    ) {
      points.push([value[0], value[1]]);
      return;
    }
    value.forEach(visit);
  }

  visit(coordinates);
  if (!points.length) return null;
  const total = points.reduce(
    (acc, point) => {
      acc.lng += point[0];
      acc.lat += point[1];
      return acc;
    },
    { lng: 0, lat: 0 },
  );
  return [total.lng / points.length, total.lat / points.length];
}

function centroidFeatureCollection(data?: GeoJsonFeatureCollection): GeoJSON.FeatureCollection {
  const features =
    data?.features.flatMap((feature) => {
      const properties = feature.properties ?? {};
      const lon = numericProperty(properties, ["zone_centroid_lon", "lon", "longitude"]);
      const lat = numericProperty(properties, ["zone_centroid_lat", "lat", "latitude"]);
      const centroid = lon !== null && lat !== null ? ([lon, lat] as [number, number]) : geometryCentroid(feature.geometry);
      if (!centroid) return [];
      return [
        {
          type: "Feature" as const,
          properties,
          geometry: {
            type: "Point" as const,
            coordinates: centroid,
          },
        },
      ];
    }) ?? [];
  return { type: "FeatureCollection", features };
}

function asNumber(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function titleCase(value: string) {
  return value
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

function humanize(value: string) {
  return titleCase(value.replaceAll("_", " "));
}

function formatTooltipNumber(value: number | null, digits = 1) {
  return value === null ? "-" : value.toFixed(digits);
}

function formatTooltipPercent(value: number | null) {
  return value === null ? "-" : `${(value * 100).toFixed(0)}%`;
}

function formatTooltipText(value: string | null) {
  return value ? humanize(value.replace(/[[\]']/g, " ").replaceAll(",", " ")) : "-";
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function featureScore(properties: Record<string, unknown>, variant: NonNullable<CurbFlowMapProps["variant"]>, mode: PlannerMode) {
  if (variant === "blindspot") {
    return (
      asNumber(properties.blindspot_risk_score) ??
      asNumber(properties.blindspot_risk) ??
      (asNumber(properties.coverage_gap) ?? 0) * 100
    );
  }
  if (variant === "patrol") {
    const nearUncovered = properties.near_patrol_but_uncovered_flag === true ? 80 : 0;
    const routeCoverage = (asNumber(properties.patrol_route_coverage) ?? 0) * 100;
    const degree = Math.min(asNumber(properties.patrol_weighted_degree) ?? 0, 100);
    return Math.max(nearUncovered, routeCoverage, degree);
  }
  if (variant === "coverageGap") {
    const coveragePct = asNumber(properties.coverage_pct);
    const totalViolations = Math.min(asNumber(properties.total_violations) ?? 0, 250) / 250;
    return Math.max(0, Math.min(100, (1 - (coveragePct ?? 1)) * 80 + totalViolations * 20));
  }
  if (variant === "planner") {
    if (properties.planner_selected !== true) return 0;
    return (
      asNumber(properties.deployment_priority) ??
      asNumber(properties[`deployment_priority_${mode}`]) ??
      asNumber(properties.predicted_pfdi) ??
      0
    );
  }
  return (
    asNumber(properties.deployment_priority) ??
    asNumber(properties[`deployment_priority_${mode}`]) ??
    asNumber(properties.predicted_pfdi) ??
    0
  );
}

function stationLabelFeatureCollection(
  data: GeoJsonFeatureCollection | undefined,
  variant: NonNullable<CurbFlowMapProps["variant"]>,
  mode: PlannerMode,
): GeoJSON.FeatureCollection {
  const groups = new Map<
    string,
    { label: string; coordinates: [number, number]; score: number; records: number }
  >();

  for (const feature of data?.features ?? []) {
    const properties = feature.properties ?? {};
    const station = String(properties.police_station ?? "").trim();
    if (!station) continue;
    const lon = numericProperty(properties, ["zone_centroid_lon", "lon", "longitude"]);
    const lat = numericProperty(properties, ["zone_centroid_lat", "lat", "latitude"]);
    const coordinates = lon !== null && lat !== null ? ([lon, lat] as [number, number]) : geometryCentroid(feature.geometry);
    if (!coordinates) continue;

    const score = featureScore(properties, variant, mode);
    const records = asNumber(properties.record_count) ?? 0;
    const current = groups.get(station);
    if (!current || score > current.score || (score === current.score && records > current.records)) {
      groups.set(station, {
        label: titleCase(station),
        coordinates,
        score,
        records,
      });
    }
  }

  const features = [...groups.values()]
    .sort((left, right) => right.score - left.score)
    .slice(0, 28)
    .map((label) => ({
      type: "Feature" as const,
      properties: {
        label: label.label,
        score: label.score,
        records: label.records,
      },
      geometry: {
        type: "Point" as const,
        coordinates: label.coordinates,
      },
    }));
  return { type: "FeatureCollection", features };
}

function tooltipFromFeature(feature: maplibregl.MapGeoJSONFeature, point: maplibregl.PointLike, map: maplibregl.Map): MapTooltip | null {
  const properties = feature.properties ?? {};
  const zoneId = properties.zone_id;
  if (zoneId === undefined || zoneId === null) return null;
  const canvas = map.getCanvas();
  const x = "x" in point ? point.x : point[0];
  const y = "y" in point ? point.y : point[1];
  const maxLeft = Math.max(TOOLTIP_EDGE_PADDING, canvas.clientWidth - TOOLTIP_WIDTH - TOOLTIP_EDGE_PADDING);
  const maxTop = Math.max(TOOLTIP_EDGE_PADDING, canvas.clientHeight - TOOLTIP_HEIGHT - TOOLTIP_EDGE_PADDING);
  const shouldFlipLeft = x + TOOLTIP_WIDTH + TOOLTIP_OFFSET + TOOLTIP_EDGE_PADDING > canvas.clientWidth;
  const shouldFlipUp = y + TOOLTIP_HEIGHT + TOOLTIP_OFFSET + TOOLTIP_EDGE_PADDING > canvas.clientHeight;
  const left = clamp(
    shouldFlipLeft ? x - TOOLTIP_WIDTH - TOOLTIP_OFFSET : x + TOOLTIP_OFFSET,
    TOOLTIP_EDGE_PADDING,
    maxLeft,
  );
  const top = clamp(
    shouldFlipUp ? y - TOOLTIP_HEIGHT - TOOLTIP_OFFSET : y + TOOLTIP_OFFSET,
    TOOLTIP_EDGE_PADDING,
    maxTop,
  );

  return {
    x: left,
    y: top,
    zoneId: String(zoneId),
    station: titleCase(String(properties.police_station ?? "Unknown station")),
    risk:
      asNumber(properties.deployment_priority) ??
      asNumber(properties.deployment_priority_balanced) ??
      asNumber(properties.predicted_pfdi),
    pfdi: asNumber(properties.predicted_pfdi),
    coverageGap: asNumber(properties.coverage_gap),
    blindspotRisk: asNumber(properties.blindspot_risk_score),
    action: humanize(String(properties.recommended_action ?? "No action assigned")),
    records: asNumber(properties.record_count) ?? asNumber(properties.total_violations),
    activeDays: asNumber(properties.active_days),
    coveragePct: asNumber(properties.coverage_pct),
    peakHour: asNumber(properties.peak_hour),
    dominantViolation: typeof properties.dominant_violation === "string" ? String(properties.dominant_violation) : null,
    gapLevel: typeof properties.gap_level === "string" ? String(properties.gap_level) : null,
  };
}

export function CurbFlowMap({ zones, mode = "balanced", variant = "risk", onZoneClick, timeHour, showShadow = false, className }: CurbFlowMapProps) {
  const mapRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<maplibregl.Map | null>(null);
  const onZoneClickRef = useRef(onZoneClick);
  const hoveredZoneIdRef = useRef<string | number | null>(null);
  const hasFitBoundsRef = useRef(false);
  const [mapReady, setMapReady] = useState(false);
  const [tooltip, setTooltip] = useState<MapTooltip | null>(null);
  const featureCount = zones?.features.length ?? 0;

  useEffect(() => {
    onZoneClickRef.current = onZoneClick;
  }, [onZoneClick]);

  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;
    const map = new maplibregl.Map({
      container: mapRef.current,
      style: "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",
      center: [77.5946, 12.9716],
      zoom: 11,
      attributionControl: false,
    });
    mapInstanceRef.current = map;

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 110, unit: "metric" }), "bottom-right");

    const handleLoad = () => {
      const beforeLabels = firstLabelLayerId(map);
      boostLabelReadability(map);
      if (!map.getSource(SOURCE_ID)) {
        map.addSource(SOURCE_ID, {
          type: "geojson",
          data: emptyFeatureCollection() as unknown as GeoJSON.FeatureCollection,
          promoteId: "zone_id",
        });
      }
      if (!map.getSource(POINT_SOURCE_ID)) {
        map.addSource(POINT_SOURCE_ID, {
          type: "geojson",
          data: centroidFeatureCollection(),
          promoteId: "zone_id",
        });
      }
      if (!map.getSource(LABEL_SOURCE_ID)) {
        map.addSource(LABEL_SOURCE_ID, {
          type: "geojson",
          data: stationLabelFeatureCollection(undefined, variant, mode),
        });
      }
      if (!map.getLayer(HEAT_LAYER_ID)) {
        map.addLayer(
          {
            id: HEAT_LAYER_ID,
            type: "heatmap",
            source: POINT_SOURCE_ID,
            maxzoom: 20,
            paint: {
              "heatmap-color": heatColorForVariant(variant) as never,
              "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 8, 0.86, 11, 1.16, 14, 1.62, 17, 2.05] as never,
              "heatmap-opacity": heatOpacityForVariant(variant) as never,
              "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 8, 10, 11, 24, 13, 44, 15, 70, 17, 98] as never,
              "heatmap-weight": heatWeightForVariant(variant, mode) as never,
            },
          },
          beforeLabels,
        );
      }
      if (!map.getLayer(FILL_LAYER_ID)) {
        map.addLayer(
          {
            id: FILL_LAYER_ID,
            type: "fill",
            source: SOURCE_ID,
            paint: {
              "fill-antialias": true,
              "fill-color": fillColorForVariant(variant, mode) as never,
              "fill-opacity": fillOpacityForVariant(variant, mode) as never,
            },
          },
          beforeLabels,
        );
      }
      if (!map.getLayer(GLOW_LAYER_ID)) {
        map.addLayer(
          {
            id: GLOW_LAYER_ID,
            type: "circle",
            source: POINT_SOURCE_ID,
            paint: {
              "circle-blur": 0.85,
              "circle-color": fillColorForVariant(variant, mode) as never,
              "circle-opacity": glowOpacityForVariant(variant, mode) as never,
              "circle-radius": signalRadiusExpression(mode) as never,
            },
          },
          beforeLabels,
        );
      }
      // Coverage shadow layers — violet/amber overlay for blindspot zones (visibility toggled by showShadow)
      if (!map.getLayer(SHADOW_GLOW_ID)) {
        map.addLayer(
          {
            id: SHADOW_GLOW_ID,
            type: "circle",
            source: POINT_SOURCE_ID,
            layout: { visibility: "none" },
            paint: {
              "circle-color": "#6d28d9",
              "circle-blur": 0.9,
              "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 22, 12, 36, 15, 56] as never,
              "circle-opacity": [
                "interpolate", ["linear"],
                ["coalesce", ["get", "blindspot_risk_score"], 0],
                0, 0, 0.2, 0.06, 0.5, 0.22, 1, 0.48,
              ] as never,
            },
          },
          beforeLabels,
        );
      }
      if (!map.getLayer(SHADOW_POINT_ID)) {
        map.addLayer(
          {
            id: SHADOW_POINT_ID,
            type: "circle",
            source: POINT_SOURCE_ID,
            layout: { visibility: "none" },
            paint: {
              "circle-color": [
                "case",
                [">=", ["coalesce", ["get", "coverage_gap"], 0], 0.5], "#f59e0b",
                "#7c3aed",
              ] as never,
              "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 4, 12, 7, 15, 11] as never,
              "circle-opacity": [
                "interpolate", ["linear"],
                ["coalesce", ["get", "blindspot_risk_score"], 0],
                0, 0, 0.2, 0.12, 0.5, 0.55, 1, 0.9,
              ] as never,
              "circle-stroke-color": "rgba(255,255,255,0.6)",
              "circle-stroke-width": 0.8,
            },
          },
          beforeLabels,
        );
      }
      if (!map.getLayer(POINT_LAYER_ID)) {
        map.addLayer(
          {
            id: POINT_LAYER_ID,
            type: "circle",
            source: POINT_SOURCE_ID,
            paint: {
              "circle-color": fillColorForVariant(variant, mode) as never,
              "circle-opacity": pointOpacityForVariant(variant, mode) as never,
              "circle-radius": [
                "interpolate",
                ["linear"],
                ["zoom"],
                9,
                1.1,
                12,
                2.2,
                15,
                4,
              ] as never,
              "circle-stroke-color": "rgba(255, 255, 255, 0.90)",
              "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 9, 0, 12, 0.65, 15, 1.2] as never,
            },
          },
          beforeLabels,
        );
      }
      if (!map.getLayer(LINE_LAYER_ID)) {
        map.addLayer(
          {
            id: LINE_LAYER_ID,
            type: "line",
            source: SOURCE_ID,
            paint: {
              "line-color": lineColorForVariant(variant),
              "line-opacity": lineOpacityForVariant(variant, mode) as never,
              "line-width": 0.75 as never,
            },
          },
          beforeLabels,
        );
      }
      if (!map.getLayer(HOVER_LAYER_ID)) {
        map.addLayer(
          {
            id: HOVER_LAYER_ID,
            type: "line",
            source: SOURCE_ID,
            paint: {
              "line-color": "rgba(255, 255, 255, 0.96)",
              "line-opacity": ["case", ["boolean", ["feature-state", "hover"], false], 0.98, 0] as never,
              "line-width": ["interpolate", ["linear"], ["zoom"], 9, 1, 12, 2.3, 15, 3.4] as never,
            },
          },
          beforeLabels,
        );
      }
      if (!map.getLayer(LABEL_LAYER_ID)) {
        map.addLayer({
          id: LABEL_LAYER_ID,
          type: "symbol",
          source: LABEL_SOURCE_ID,
          minzoom: 8,
          maxzoom: 16,
          layout: {
            "symbol-placement": "point",
            "text-allow-overlap": false,
            "text-field": ["get", "label"],
            "text-size": ["interpolate", ["linear"], ["zoom"], 8, 10.5, 12, 13, 15, 14] as never,
            "text-variable-anchor": ["top", "bottom", "left", "right"],
            "text-radial-offset": 0.75,
          },
          paint: {
            "text-color": "rgba(30, 41, 59, 0.88)",
            "text-halo-blur": 0.2,
            "text-halo-color": "rgba(255, 255, 255, 0.96)",
            "text-halo-width": 1.5,
            "text-opacity": ["interpolate", ["linear"], ["zoom"], 8, 0.98, 12, 0.82, 14, 0.45, 16, 0.18] as never,
          },
        });
      }
      applyZonePaint(map, variant, mode);
      for (const layerId of [FILL_LAYER_ID, POINT_LAYER_ID]) {
        map.on("click", layerId, handleClick);
        map.on("mousemove", layerId, handleMouseMove);
        map.on("mouseenter", layerId, handleMouseEnter);
        map.on("mouseleave", layerId, handleMouseLeave);
      }
      setMapReady(true);
    };

    const handleClick = (event: maplibregl.MapLayerMouseEvent) => {
      const feature = event.features?.[0];
      const zoneId = feature?.properties?.zone_id;
      if (zoneId !== undefined && zoneId !== null) {
        onZoneClickRef.current?.(String(zoneId));
      }
    };
    const handleMouseMove = (event: maplibregl.MapLayerMouseEvent) => {
      const feature = event.features?.[0];
      if (!feature) return;
      const zoneId = feature.id;
      if (zoneId === undefined || zoneId === null) return;
      if (zoneId !== hoveredZoneIdRef.current && hoveredZoneIdRef.current !== null) {
        map.setFeatureState({ source: SOURCE_ID, id: hoveredZoneIdRef.current }, { hover: false });
      }
      if (zoneId !== hoveredZoneIdRef.current) {
        hoveredZoneIdRef.current = zoneId;
        map.setFeatureState({ source: SOURCE_ID, id: zoneId }, { hover: true });
      }
      const tooltip = tooltipFromFeature(feature, event.point, map);
      setTooltip(tooltip);
    };
    const handleMouseEnter = () => {
      map.getCanvas().style.cursor = "pointer";
    };
    const handleMouseLeave = () => {
      if (hoveredZoneIdRef.current !== null) {
        map.setFeatureState({ source: SOURCE_ID, id: hoveredZoneIdRef.current }, { hover: false });
        hoveredZoneIdRef.current = null;
      }
      setTooltip(null);
      map.getCanvas().style.cursor = "";
    };

    map.on("load", handleLoad);
    return () => {
      map.off("load", handleLoad);
      for (const layerId of [FILL_LAYER_ID, POINT_LAYER_ID]) {
        map.off("click", layerId, handleClick);
        map.off("mousemove", layerId, handleMouseMove);
        map.off("mouseenter", layerId, handleMouseEnter);
        map.off("mouseleave", layerId, handleMouseLeave);
      }
      map.remove();
      mapInstanceRef.current = null;
      setMapReady(false);
    };
  }, []);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapReady) return;
    applyZonePaint(map, variant, mode);
  }, [mapReady, mode, variant]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapReady) return;
    const source = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    const pointSource = map.getSource(POINT_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    const labelSource = map.getSource(LABEL_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    if (!source || !pointSource || !labelSource) return;
    const data = zones ?? emptyFeatureCollection();
    source.setData(data as unknown as GeoJSON.FeatureCollection);
    pointSource.setData(centroidFeatureCollection(zones));
    labelSource.setData(stationLabelFeatureCollection(zones, variant, mode));

    const bounds = collectBounds(zones);
    if (bounds && !hasFitBoundsRef.current) {
      map.fitBounds(bounds, { padding: 32, maxZoom: 13.5, duration: 700 });
      hasFitBoundsRef.current = true;
    }
  }, [mapReady, mode, variant, zones]);

  // Toggle coverage shadow layers (violet/amber blindspot overlay)
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapReady) return;
    const vis = showShadow ? "visible" : "none";
    if (map.getLayer(SHADOW_GLOW_ID)) map.setLayoutProperty(SHADOW_GLOW_ID, "visibility", vis);
    if (map.getLayer(SHADOW_POINT_ID)) map.setLayoutProperty(SHADOW_POINT_ID, "visibility", vis);
  }, [mapReady, showShadow]);

  // Timeline hour animation: boost zones whose peak_hour matches, dim others
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapReady) return;
    if (!map.getLayer(POINT_LAYER_ID) || !map.getLayer(GLOW_LAYER_ID)) return;

    if (timeHour === null || timeHour === undefined) {
      // Restore defaults
      map.setPaintProperty(POINT_LAYER_ID, "circle-radius", ["interpolate", ["linear"], ["zoom"], 9, 1.1, 12, 2.2, 15, 4] as never);
      map.setPaintProperty(POINT_LAYER_ID, "circle-opacity", pointOpacityForVariant(variant, mode) as never);
      map.setPaintProperty(GLOW_LAYER_ID, "circle-radius", signalRadiusExpression(mode) as never);
      map.setPaintProperty(GLOW_LAYER_ID, "circle-opacity", glowOpacityForVariant(variant, mode) as never);
      return;
    }

    const isMatch = ["==", ["to-number", ["coalesce", ["get", "peak_hour"], -1]], timeHour];

    // MapLibre forbids >1 zoom-based interpolate in a single expression tree,
    // so the highlight/dim branches use fixed values instead.
    map.setPaintProperty(POINT_LAYER_ID, "circle-radius", ["case", isMatch, 9, 1.5] as never);
    map.setPaintProperty(POINT_LAYER_ID, "circle-opacity", ["case", isMatch, 0.92, 0.07] as never);
    map.setPaintProperty(GLOW_LAYER_ID, "circle-radius", ["case", isMatch, 22, 3] as never);
    map.setPaintProperty(GLOW_LAYER_ID, "circle-opacity", ["case", isMatch, 0.38, 0.02] as never);
  }, [mapReady, timeHour, variant, mode]);

  return (
    <div className={className ?? "relative h-[360px] overflow-hidden rounded-lg border border-[#e8e8e4] bg-[#f8f8f5] shadow-sm sm:h-[440px]"}>
      <div ref={mapRef} className="absolute inset-0" />
      <div className="pointer-events-none absolute left-3 top-3 rounded-md border border-[#e8e8e4] bg-white/95 px-2.5 py-1.5 text-[11px] font-medium text-[#6b6b6b] shadow-md backdrop-blur">
        {featureCount > 0 ? `${featureCount.toLocaleString()} zones loaded` : "Loading zones..."}
      </div>
      {tooltip ? (
        <div
          className="pointer-events-none absolute z-10 w-[280px] rounded-lg border border-slate-200 bg-white/95 p-3 text-xs text-slate-600 shadow-xl backdrop-blur"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          <div className="mb-2 flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-slate-950">{tooltip.station}</div>
              <div className="font-mono text-[11px] text-slate-400">{tooltip.zoneId}</div>
            </div>
            <div className="rounded-full bg-slate-950 px-2 py-0.5 text-[11px] font-semibold text-white">
              {formatTooltipNumber(tooltip.risk, 0)}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-md bg-slate-50 p-2">
              <div className="text-slate-400">PFDI</div>
              <div className="font-semibold text-slate-900">{formatTooltipNumber(tooltip.pfdi, 1)}</div>
            </div>
            <div className="rounded-md bg-slate-50 p-2">
              <div className="text-slate-400">Coverage gap</div>
              <div className="font-semibold text-slate-900">{formatTooltipPercent(tooltip.coverageGap)}</div>
            </div>
            <div className="rounded-md bg-purple-50 p-2">
              <div className="text-purple-500">Blindspot</div>
              <div className="font-semibold text-purple-950">{formatTooltipNumber(tooltip.blindspotRisk, 1)}</div>
            </div>
            <div className="rounded-md bg-orange-50 p-2">
              <div className="text-orange-500">Records</div>
              <div className="font-semibold text-orange-950">{formatTooltipNumber(tooltip.records, 0)}</div>
            </div>
          </div>
          <div className="mt-2 rounded-md border border-slate-100 bg-white p-2">
            <div className="text-slate-400">Recommended action</div>
            <div className="font-medium text-slate-900">{tooltip.action}</div>
          </div>
          {tooltip.coveragePct !== null || tooltip.activeDays !== null || tooltip.peakHour !== null ? (
            <div className="mt-2 grid grid-cols-2 gap-2">
              <div className="rounded-md bg-blue-50 p-2">
                <div className="text-blue-500">Active days</div>
                <div className="font-semibold text-blue-950">{formatTooltipNumber(tooltip.activeDays, 0)}</div>
              </div>
              <div className="rounded-md bg-blue-50 p-2">
                <div className="text-blue-500">Coverage</div>
                <div className="font-semibold text-blue-950">{formatTooltipPercent(tooltip.coveragePct)}</div>
              </div>
              <div className="rounded-md bg-slate-50 p-2">
                <div className="text-slate-400">Peak hour</div>
                <div className="font-semibold text-slate-900">
                  {tooltip.peakHour === null ? "-" : `${formatTooltipNumber(tooltip.peakHour, 0)}:00`}
                </div>
              </div>
              <div className="rounded-md bg-slate-50 p-2">
                <div className="text-slate-400">Gap level</div>
                <div className="font-semibold text-slate-900">{formatTooltipText(tooltip.gapLevel)}</div>
              </div>
              <div className="col-span-2 rounded-md bg-slate-50 p-2">
                <div className="text-slate-400">Dominant violation</div>
                <div className="font-semibold text-slate-900">{formatTooltipText(tooltip.dominantViolation)}</div>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
      <Legend variant={variant} />
    </div>
  );
}
