"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Compass, EyeOff, Flame, Info, MapPinned } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { CurbFlowMap } from "@/components/curbflow-map";
import { PlannerControls } from "@/components/planner-controls";
import { RecommendationTable } from "@/components/recommendation-table";
import { ResourceSummary } from "@/components/resource-summary";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getAuditSummary,
  getBlindspots,
  getHotspots,
  getPlannerRecommendations,
  getZonesGeoJson,
  type GeoJsonFeatureCollection,
  type PlannerRecommendation,
  type RiskRow,
} from "@/lib/api";
import { demoPresets, type DemoPreset } from "@/lib/demoPresets";
import type { PlannerMode } from "@/lib/store";
import { useCurbFlowStore } from "@/lib/store";

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function uniqueSorted(values: Array<string | null | undefined>) {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value)))).sort((left, right) =>
    left.localeCompare(right),
  );
}

function stationOptionsFrom(summary: unknown, rows: RiskRow[]) {
  const counts = asRecord(asRecord(summary).police_station_counts);
  return uniqueSorted([...Object.keys(counts), ...rows.map((row) => row.police_station)]);
}

function windowOptionsFrom(rows: RiskRow[], station?: string) {
  const scopedRows = station ? rows.filter((row) => row.police_station === station) : rows;
  return uniqueSorted(scopedRows.map((row) => row.window_start)).sort().reverse();
}

function actionLabel(action?: string | null) {
  return String(action ?? "recommended action").replaceAll("_", " ");
}

function enrichZonesForPlanner(
  zones: GeoJsonFeatureCollection | undefined,
  recommendations: PlannerRecommendation[],
): GeoJsonFeatureCollection | undefined {
  if (!zones) return undefined;
  const recommendationByZone = new Map(recommendations.map((row) => [String(row.zone_id), row]));
  return {
    ...zones,
    features: zones.features.map((feature) => {
      const zoneId = String(feature.properties?.zone_id ?? feature.properties?.id ?? "");
      const recommendation = recommendationByZone.get(zoneId);
      return {
        ...feature,
        properties: {
          ...feature.properties,
          planner_selected: Boolean(recommendation),
          planner_action: recommendation?.action,
          planner_rank: recommendation?.recommendation_rank,
          planner_action_category: recommendation?.action_category,
          planner_expected_relief: recommendation?.expected_relief,
          planner_blindspot_score: recommendation?.blindspot_risk_score,
        },
      };
    }),
  };
}

function ExplanationPanel({ mode }: { mode: PlannerMode }) {
  const rows = [
    {
      mode: "conservative" as PlannerMode,
      icon: Flame,
      title: "Conservative",
      text: "Conservative mode = prioritize proven hotspots.",
    },
    {
      mode: "balanced" as PlannerMode,
      icon: Compass,
      title: "Balanced",
      text: "Balanced mode = combine proven hotspots and blindspot audits.",
    },
    {
      mode: "discovery" as PlannerMode,
      icon: EyeOff,
      title: "Discovery",
      text: "Discovery mode = prioritize uncovered high-potential zones.",
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Info className="h-4 w-4" />
          Mode Explanation
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm font-medium text-emerald-950">
          The planner balances exploitation of proven hotspots with exploration of under-covered blindspots under officer and towing
          constraints.
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          {rows.map((row) => {
            const Icon = row.icon;
            const active = row.mode === mode;
            return (
              <div key={row.mode} className={`rounded-lg border p-3 ${active ? "border-slate-950 bg-slate-50" : "border-slate-200"}`}>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 font-medium text-slate-950">
                    <Icon className="h-4 w-4 text-slate-600" />
                    {row.title}
                  </div>
                  {active ? <Badge>Active</Badge> : <Badge variant="secondary">Mode</Badge>}
                </div>
                <p className="text-sm text-slate-600">{row.text}</p>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

function SelectedActionsPanel({ rows }: { rows: PlannerRecommendation[] }) {
  const actions = rows.slice(0, 8);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MapPinned className="h-4 w-4" />
          Selected Recommendation Zones
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {actions.map((row, index) => (
          <div key={`${row.zone_id}-${row.action}-${index}`} className="flex items-center justify-between gap-3 rounded-md border border-slate-200 px-3 py-2 text-sm">
            <div>
              <div className="font-medium text-slate-950">{row.zone_id}</div>
              <div className="text-xs text-slate-500">{actionLabel(row.action)}</div>
            </div>
            <Badge variant={row.action_category === "blindspot" ? "warning" : "secondary"}>
              #{row.recommendation_rank ?? index + 1}
            </Badge>
          </div>
        ))}
        {!actions.length ? (
          <div className="rounded-md border border-dashed border-slate-200 p-4 text-sm text-slate-500">
            Submitted recommendations will be highlighted on the map by action type.
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

export default function PlannerPage() {
  const [windowStart, setWindowStart] = useState("");
  const [station, setStation] = useState("");
  const [officers, setOfficers] = useState(8);
  const [towUnits, setTowUnits] = useState(2);
  const mode = useCurbFlowStore((state) => state.plannerMode);
  const setMode = useCurbFlowStore((state) => state.setPlannerMode);
  const setSelectedZoneId = useCurbFlowStore((state) => state.setSelectedZoneId);
  const [rows, setRows] = useState<PlannerRecommendation[]>([]);

  const audit = useQuery({ queryKey: ["planner-audit-summary"], queryFn: getAuditSummary });
  const hotspots = useQuery({
    queryKey: ["planner-hotspot-options", mode],
    queryFn: () => getHotspots({ top_k: 500, mode }),
  });
  const blindspots = useQuery({
    queryKey: ["planner-blindspot-options"],
    queryFn: () => getBlindspots({ top_k: 500 }),
  });
  const optionRows = useMemo(() => [...(hotspots.data ?? []), ...(blindspots.data ?? [])], [hotspots.data, blindspots.data]);
  const stationOptions = useMemo(
    () => stationOptionsFrom(audit.data?.raw_summary, optionRows),
    [audit.data?.raw_summary, optionRows],
  );
  const windowOptions = useMemo(() => windowOptionsFrom(optionRows, station), [optionRows, station]);
  const controlStationOptions = useMemo(
    () => uniqueSorted([...stationOptions, station]),
    [stationOptions, station],
  );
  const controlWindowOptions = useMemo(
    () => uniqueSorted([...windowOptions, windowStart]).sort().reverse(),
    [windowOptions, windowStart],
  );

  useEffect(() => {
    if (!windowStart && windowOptions.length) {
      setWindowStart(windowOptions[0]);
    }
  }, [windowOptions, windowStart]);

  const zones = useQuery({
    queryKey: ["zones", "planner", mode, windowStart, station],
    queryFn: () =>
      getZonesGeoJson({
        mode,
        window_start: windowStart || undefined,
        station: station || undefined,
      }),
  });
  const plannerZones = useMemo(() => enrichZonesForPlanner(zones.data, rows), [zones.data, rows]);

  const planner = useMutation({
    mutationFn: getPlannerRecommendations,
    onSuccess: setRows,
  });

  function applyDemoPreset(preset: DemoPreset) {
    setStation(preset.policeStation);
    setWindowStart(preset.windowStart);
    setOfficers(preset.officers);
    setTowUnits(preset.towUnits);
    setMode(preset.mode);
    setSelectedZoneId(preset.zoneId);
    setRows([]);
  }

  function submitPlanner() {
    if (!windowStart) return;
    planner.mutate({
      window_start: windowStart,
      police_station: station || undefined,
      available_officers: officers,
      available_tow_units: towUnits,
      mode,
      top_k: 100,
    });
  }

  return (
    <div className="space-y-4">
      <PlannerControls
        windowStart={windowStart}
        station={station}
        officers={officers}
        towUnits={towUnits}
        mode={mode}
        demoPresets={demoPresets}
        stationOptions={controlStationOptions}
        windowOptions={controlWindowOptions}
        onWindowStartChange={setWindowStart}
        onStationChange={setStation}
        onOfficersChange={setOfficers}
        onTowUnitsChange={setTowUnits}
        onModeChange={(nextMode: PlannerMode) => setMode(nextMode)}
        onDemoPreset={applyDemoPreset}
        onSubmit={submitPlanner}
        loading={planner.isPending}
      />

      {planner.error ? (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{planner.error.message}</div>
      ) : null}

      <ResourceSummary rows={rows} />

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <CurbFlowMap zones={plannerZones} mode={mode} variant="planner" />
        <SelectedActionsPanel rows={rows} />
      </section>

      <ExplanationPanel mode={mode} />
      <RecommendationTable rows={rows} />
    </div>
  );
}
