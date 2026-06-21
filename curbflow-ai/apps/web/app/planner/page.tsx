"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { CalendarDays, Clock, Compass, EyeOff, Flame, Info, MapPinned, Target, Truck, Video } from "lucide-react";
import Link from "next/link";
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
  getMorningBrief,
  getPlannerRecommendations,
  getZonesGeoJson,
  type GeoJsonFeatureCollection,
  type MorningBriefRow,
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

function cleanLabel(value?: string | null) {
  return String(value ?? "unknown")
    .replace(/[[\]']/g, " ")
    .replaceAll(",", " ")
    .replaceAll("_", " ")
    .replace(/\s+/g, " ")
    .trim();
}

function percent(value?: number | null) {
  return value === null || value === undefined ? "-" : `${(value * 100).toFixed(0)}%`;
}

const dayOptions = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

const slotOptions = [
  { label: "Early Morning 6-9AM", value: 2 },
  { label: "Morning 9AM-12PM", value: 3 },
  { label: "Afternoon 12-3PM", value: 4 },
];

function MorningBriefCard({ row, rank }: { row: MorningBriefRow; rank: number }) {
  const action = row.recommended_action ?? "beat_patrol";
  const Icon = action === "towing_required" ? Truck : action === "camera_patrol" ? Video : Target;
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Badge variant="warning">#{rank}</Badge>
            <div className="truncate text-sm font-semibold text-slate-950">{row.zone_label ?? row.zone_id}</div>
          </div>
          <div className="mt-1 font-mono text-xs text-slate-400">{row.zone_id}</div>
        </div>
        <Badge variant={action === "towing_required" ? "danger" : action === "camera_patrol" ? "purple" : "info"}>
          {actionLabel(action)}
        </Badge>
      </div>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div className="rounded-md bg-red-50 p-2">
          <div className="text-xs text-red-500">PFDI score</div>
          <div className="font-semibold text-red-950">{row.pfdi_score?.toFixed(1) ?? "-"}</div>
        </div>
        <div className="rounded-md bg-slate-50 p-2">
          <div className="text-xs text-slate-500">Violations</div>
          <div className="font-semibold text-slate-950">{row.total_violations?.toLocaleString() ?? "-"}</div>
        </div>
        <div className="rounded-md bg-orange-50 p-2">
          <div className="text-xs text-orange-500">Repeat vehicles</div>
          <div className="font-semibold text-orange-950">{row.repeat_offender_count ?? 0}</div>
        </div>
        <div className="rounded-md bg-blue-50 p-2">
          <div className="text-xs text-blue-500">Large vehicle</div>
          <div className="font-semibold text-blue-950">{percent(row.large_vehicle_pct)}</div>
        </div>
      </div>
      <div className="mt-3 flex items-start gap-2 rounded-md bg-slate-50 p-2 text-xs text-slate-600">
        <Icon className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
        <span>
          Dominant pattern: {cleanLabel(row.dominant_violation)}; mostly {cleanLabel(row.dominant_vehicle_type)}.
        </span>
      </div>
    </div>
  );
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

function ExplanationPanel({
  mode,
  onModeChange,
  loading,
}: {
  mode: PlannerMode;
  onModeChange: (mode: PlannerMode) => void;
  loading?: boolean;
}) {
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
              <button
                key={row.mode}
                type="button"
                disabled={loading}
                onClick={() => onModeChange(row.mode)}
                className={`rounded-lg border p-3 text-left transition ${
                  active
                    ? "border-slate-950 bg-slate-50"
                    : "border-slate-200 hover:border-slate-400 hover:bg-slate-50"
                } ${loading ? "cursor-wait opacity-70" : "cursor-pointer"}`}
              >
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 font-medium text-slate-950">
                    <Icon className="h-4 w-4 text-slate-600" />
                    {row.title}
                  </div>
                  {active ? <Badge>Active</Badge> : <Badge variant="secondary">Mode</Badge>}
                </div>
                <p className="text-sm text-slate-600">{row.text}</p>
              </button>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

function SelectedActionsPanel({ rows, onSelect }: { rows: PlannerRecommendation[]; onSelect?: (zoneId: string) => void }) {
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
          <button
            key={`${row.zone_id}-${row.action}-${index}`}
            type="button"
            onClick={() => onSelect?.(row.zone_id)}
            className="flex w-full items-center justify-between gap-3 rounded-md border border-slate-200 px-3 py-2 text-left text-sm transition hover:border-slate-300 hover:bg-slate-50"
          >
            <div>
              <div className="font-medium text-slate-950">{row.zone_id}</div>
              <div className="text-xs text-slate-500">{actionLabel(row.action)}</div>
            </div>
            <Badge variant={row.action_category === "blindspot" ? "warning" : "secondary"}>
              #{row.recommendation_rank ?? index + 1}
            </Badge>
          </button>
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
  const [briefStation, setBriefStation] = useState("");
  const [briefDay, setBriefDay] = useState("Tuesday");
  const [briefSlot, setBriefSlot] = useState(3);
  const [briefRequest, setBriefRequest] = useState<{ station: string; dow: string; slot: number } | null>(null);
  const mode = useCurbFlowStore((state) => state.plannerMode);
  const setMode = useCurbFlowStore((state) => state.setPlannerMode);
  const selectedZoneId = useCurbFlowStore((state) => state.selectedZoneId);
  const setSelectedZoneId = useCurbFlowStore((state) => state.setSelectedZoneId);
  const [rows, setRows] = useState<PlannerRecommendation[]>([]);
  const [plannerMapFitNonce, setPlannerMapFitNonce] = useState(0);

  const audit = useQuery({ queryKey: ["planner-audit-summary"], queryFn: getAuditSummary });
  const hotspots = useQuery({
    queryKey: ["planner-hotspot-options", mode],
    queryFn: () => getHotspots({ top_k: 500, mode }),
  });
  const blindspots = useQuery({
    queryKey: ["planner-blindspot-options"],
    queryFn: () => getBlindspots({ top_k: 500 }),
  });
  const morningBrief = useQuery({
    queryKey: ["morning-brief", briefRequest],
    queryFn: () =>
      getMorningBrief({
        station: briefRequest?.station ?? "",
        dow: briefRequest?.dow ?? "Tuesday",
        slot: briefRequest?.slot ?? 3,
        top_k: 5,
      }),
    enabled: Boolean(briefRequest?.station),
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

  useEffect(() => {
    if (!briefStation && stationOptions.length) {
      setBriefStation(stationOptions[0]);
    }
  }, [briefStation, stationOptions]);

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

  function runPlanner(nextMode: PlannerMode = mode) {
    if (!windowStart) return;
    setPlannerMapFitNonce((value) => value + 1);
    planner.mutate({
      window_start: windowStart,
      police_station: station || undefined,
      available_officers: officers,
      available_tow_units: towUnits,
      mode: nextMode,
      top_k: 100,
    });
  }

  function changeMode(nextMode: PlannerMode) {
    setMode(nextMode);
    if (rows.length > 0 && windowStart) {
      runPlanner(nextMode);
    }
  }

  function applyDemoPreset(preset: DemoPreset) {
    setStation(preset.policeStation);
    setWindowStart(preset.windowStart);
    setOfficers(preset.officers);
    setTowUnits(preset.towUnits);
    setMode(preset.mode);
    setSelectedZoneId(preset.zoneId);
    setRows([]);
    setPlannerMapFitNonce((value) => value + 1);
  }

  function submitPlanner() {
    runPlanner(mode);
  }

  function submitMorningBrief() {
    if (!briefStation) return;
    setBriefRequest({ station: briefStation, dow: briefDay, slot: briefSlot });
  }

  return (
    <div className="space-y-4">
      <Card className="border-orange-200 bg-gradient-to-br from-orange-50 to-white">
        <CardHeader>
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <CalendarDays className="h-4 w-4 text-orange-600" />
                Morning Deployment Brief
              </CardTitle>
              <p className="mt-1 text-sm text-slate-600">
                Historical PFDI-weighted zones for station, weekday, and 3-hour operating slot.
              </p>
            </div>
            <Link
              href="/blindspots#evening-blindspot"
              className="inline-flex h-9 items-center rounded-md border border-purple-200 bg-white px-3 text-sm font-medium text-purple-800 shadow-sm hover:bg-purple-50"
            >
              See evening blindspots
            </Link>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_220px_220px_auto]">
            <label className="space-y-1 text-sm">
              <span className="font-medium text-slate-700">Police station</span>
              <select
                value={briefStation}
                onChange={(event) => setBriefStation(event.target.value)}
                className="h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 shadow-sm"
              >
                {controlStationOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="font-medium text-slate-700">Day</span>
              <select
                value={briefDay}
                onChange={(event) => setBriefDay(event.target.value)}
                className="h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 shadow-sm"
              >
                {dayOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="font-medium text-slate-700">Slot</span>
              <select
                value={briefSlot}
                onChange={(event) => setBriefSlot(Number(event.target.value))}
                className="h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 shadow-sm"
              >
                {slotOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={submitMorningBrief}
              disabled={!briefStation || morningBrief.isFetching}
              className="mt-6 inline-flex h-10 items-center justify-center rounded-md bg-slate-950 px-4 text-sm font-medium text-white shadow-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              <Clock className="mr-2 h-4 w-4" />
              {morningBrief.isFetching ? "Loading" : "Generate"}
            </button>
          </div>
          {morningBrief.error ? (
            <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              {morningBrief.error.message}
            </div>
          ) : null}
          <div className="grid gap-3 lg:grid-cols-5">
            {(morningBrief.data ?? []).map((row, index) => (
              <MorningBriefCard key={`${row.zone_id}-${index}`} row={row} rank={index + 1} />
            ))}
          </div>
          {briefRequest && !morningBrief.isFetching && !(morningBrief.data ?? []).length ? (
            <div className="rounded-md border border-dashed border-slate-200 bg-white p-4 text-sm text-slate-500">
              No historical rows found for this station/day/slot. Try another slot or station.
            </div>
          ) : null}
        </CardContent>
      </Card>

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
        onStationChange={(value) => {
          setStation(value);
          setRows([]);
          setSelectedZoneId(undefined);
          setPlannerMapFitNonce((current) => current + 1);
        }}
        onOfficersChange={setOfficers}
        onTowUnitsChange={setTowUnits}
        onModeChange={changeMode}
        onDemoPreset={applyDemoPreset}
        onSubmit={submitPlanner}
        loading={planner.isPending}
      />

      {planner.error ? (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{planner.error.message}</div>
      ) : null}

      <ResourceSummary rows={rows} />

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <CurbFlowMap
          zones={plannerZones}
          mode={mode}
          variant="planner"
          selectedZoneId={selectedZoneId}
          onZoneClick={setSelectedZoneId}
          fitKey={`planner:${station || "all"}:${windowStart || "none"}:${mode}:${plannerMapFitNonce}`}
        />
        <SelectedActionsPanel rows={rows} onSelect={setSelectedZoneId} />
      </section>

      <ExplanationPanel mode={mode} onModeChange={changeMode} loading={planner.isPending} />
      <RecommendationTable rows={rows} />
    </div>
  );
}
