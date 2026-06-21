"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Clock3,
  EyeOff,
  Gauge,
  Layers,
  MapPinned,
  Menu,
  Pause,
  Play,
  Radio,
  Route,
  Search,
  ShieldCheck,
  Siren,
  X,
} from "lucide-react";
import Link from "next/link";
import { type CSSProperties, useEffect, useMemo, useState } from "react";

import { CurbFlowMap } from "@/components/curbflow-map";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getAuditSummary,
  getBlindspots,
  getHotspots,
  getPredictionWindows,
  getZoneDetails,
  getZonesGeoJson,
  searchPlaces,
  type GeoJsonFeatureCollection,
  type PlaceSuggestion,
  type PredictionWindowRow,
  type RiskRow,
  type ZoneDetails,
} from "@/lib/api";
import { type PlannerMode, useCurbFlowStore } from "@/lib/store";
import { cn, formatDateTime, formatNumber } from "@/lib/utils";

type RiskLevel = "critical" | "high" | "elevated" | "clear";

const tourSteps = [
  {
    title: "Start with the city",
    text: "The map is the product surface. Heat, labels, and zone rings update from live prediction windows instead of sitting inside a static dashboard card.",
    spotlight: { left: "24rem", right: "24rem", top: "7.2rem", bottom: "9rem" },
    card: { left: "26rem", top: "8.5rem" },
  },
  {
    title: "Scrub time",
    text: "The timeline replays 3-hour IST windows. Morning makes observed hotspots prominent; evening switches attention toward evidence-poor audit zones.",
    spotlight: { left: "24rem", right: "24rem", bottom: "1rem", height: "9rem" },
    card: { left: "26rem", bottom: "11rem" },
  },
  {
    title: "Read the queue",
    text: "The queue is the operational triage list. It translates PFDI and planner scores into critical, high, elevated, or clear priorities.",
    spotlight: { left: "1rem", top: "11rem", width: "22rem", bottom: "1rem" },
    card: { left: "24.5rem", top: "14rem" },
  },
  {
    title: "Click a zone",
    text: "The zone brief explains the selected area in plain language: current situation, visibility gap, blindspot risk, and the recommended action.",
    spotlight: { right: "1rem", top: "6.5rem", width: "23rem", bottom: "1rem" },
    card: { right: "25rem", top: "9rem" },
  },
  {
    title: "Plan deployment",
    text: "When the map is crowded, collapse either panel and stay in map focus. The planner keeps exploitation and exploration under resource limits.",
    spotlight: { left: "24rem", right: "24rem", top: "1rem", height: "6rem" },
    card: { left: "29rem", top: "8rem" },
  },
] satisfies Array<{
  title: string;
  text: string;
  spotlight: CSSProperties;
  card: CSSProperties;
}>;

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

function stationMatchShare(zones: GeoJsonFeatureCollection | undefined, station: string) {
  const selected = station.trim().toLowerCase();
  if (!selected || !zones?.features.length) return 0;
  const matching = zones.features.filter(
    (feature) => String(feature.properties?.police_station ?? "").trim().toLowerCase() === selected,
  ).length;
  return matching / zones.features.length;
}

function hasPlaceCoordinates(place: PlaceSuggestion) {
  return (
    place.latitude !== null &&
    place.latitude !== undefined &&
    place.longitude !== null &&
    place.longitude !== undefined &&
    Number.isFinite(Number(place.latitude)) &&
    Number.isFinite(Number(place.longitude))
  );
}

function matchingStationForPlace(place: PlaceSuggestion, stations: string[]) {
  const text = `${place.place_name} ${place.place_address ?? ""}`.toLowerCase();
  return stations.find((station) => text.includes(station.toLowerCase())) ?? "";
}

function hourFromWindow(value?: string | null) {
  if (!value) return null;
  const direct = value.match(/T(\d{2})/);
  if (direct) return Number(direct[1]);
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.getHours();
}

function windowLabel(value?: string | null) {
  if (!value) return "No window selected";
  const start = formatDateTime(value);
  const hour = hourFromWindow(value);
  const endHour = hour === null ? null : (hour + 3) % 24;
  return endHour === null ? start : `${start} · ${String(hour).padStart(2, "0")}:00-${String(endHour).padStart(2, "0")}:00`;
}

function riskScore(row?: RiskRow | ZoneDetails | null, mode: PlannerMode = "balanced") {
  if (!row) return 0;
  const modeValue = Number(row[`deployment_priority_${mode}`]);
  const values = [
    Number(row.deployment_priority),
    modeValue,
    Number(row.observed_risk_score),
    Number(row.predicted_pfdi),
    Number(row.blindspot_risk_score),
  ];
  return values.find((value) => Number.isFinite(value)) ?? 0;
}

function riskLevel(score: number): RiskLevel {
  if (score >= 75) return "critical";
  if (score >= 50) return "high";
  if (score >= 25) return "elevated";
  return "clear";
}

function riskBadgeText(level: RiskLevel) {
  return {
    critical: "CRITICAL",
    high: "HIGH",
    elevated: "ELEVATED",
    clear: "CLEAR",
  }[level];
}

function riskClasses(level: RiskLevel) {
  return {
    critical: "bg-red-700 text-white ring-red-700",
    high: "bg-orange-600 text-white ring-orange-600",
    elevated: "bg-amber-500 text-slate-950 ring-amber-500",
    clear: "bg-emerald-600 text-white ring-emerald-600",
  }[level];
}

function actionLabel(value?: string | null) {
  if (!value) return "Beat patrol";
  return value
    .replaceAll("_", " ")
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function RiskBadge({ score }: { score: number }) {
  const level = riskLevel(score);
  return <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-bold ring-1", riskClasses(level))}>{riskBadgeText(level)}</span>;
}

function plainPercent(value?: number | null) {
  return value === null || value === undefined || Number.isNaN(value) ? "—" : `${Math.round(value * 100)}%`;
}

function bestWindowIndex(windows: PredictionWindowRow[]) {
  if (!windows.length) return 0;
  let bestIndex = 0;
  let bestScore = -Infinity;
  windows.forEach((window, index) => {
    const hour = hourFromWindow(window.window_start) ?? 0;
    const demoHourBoost = hour >= 7 && hour <= 12 ? 25 : hour >= 18 && hour <= 20 ? 15 : 0;
    const score = Number(window.max_balanced_priority ?? window.max_predicted_pfdi ?? 0) + demoHourBoost;
    if (score > bestScore) {
      bestScore = score;
      bestIndex = index;
    }
  });
  return bestIndex;
}

function windowIndexInHourRange(windows: PredictionWindowRow[], startHour: number, endHour: number) {
  const index = windows.findIndex((window) => {
    const hour = hourFromWindow(window.window_start);
    return hour !== null && hour >= startHour && hour <= endHour;
  });
  return index >= 0 ? index : null;
}

function timelineMood(hour: number | null) {
  if (hour === null) return "Select a prediction window.";
  if (hour >= 7 && hour < 15) return "Morning visibility is strongest. Observed hotspots are easiest to defend.";
  if (hour >= 15 && hour < 18) return "Shift transition window. Enforcement visibility drops, so uncertainty matters.";
  if (hour >= 18 && hour <= 20) return "Evening evidence is sparse. Treat zero-violation zones as audit candidates.";
  return "Low-volume window. Use as context, not proof of no illegal parking.";
}

function replayPhase(hour: number | null) {
  if (hour === null) return { label: "Waiting for window", tone: "bg-slate-950 text-white", help: "Choose a time window to start replay." };
  if (hour >= 7 && hour < 15) {
    return {
      label: "Morning observed hotspots",
      tone: "bg-red-700 text-white",
      help: "High-confidence challan visibility. Use this for proven enforcement priorities.",
    };
  }
  if (hour >= 15 && hour < 18) {
    return {
      label: "Visibility transition",
      tone: "bg-amber-500 text-slate-950",
      help: "Officer activity starts thinning. Treat lower counts with caution.",
    };
  }
  if (hour >= 18 && hour <= 20) {
    return {
      label: "Evening audit window",
      tone: "bg-blue-700 text-white",
      help: "Sparse evidence. Look for blindspot audits instead of assuming safe zones.",
    };
  }
  return {
    label: "Low-volume context",
    tone: "bg-slate-700 text-white",
    help: "Useful for context, not a strong proof signal.",
  };
}

function CommandQueue({
  title,
  rows,
  mode,
  selectedZoneId,
  onSelect,
}: {
  title: string;
  rows: RiskRow[];
  mode: PlannerMode;
  selectedZoneId?: string;
  onSelect: (zoneId: string) => void;
}) {
  return (
    <Card className="border-slate-200 bg-white/95">
      <CardHeader className="p-3">
        <CardTitle className="flex items-center justify-between gap-3 text-xs uppercase tracking-wide text-slate-500">
          {title}
          <span>{rows.length}</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="max-h-[34vh] space-y-2 overflow-auto p-3">
        {rows.slice(0, 8).map((row, index) => {
          const score = riskScore(row, mode);
          return (
            <button
              key={`${title}-${row.zone_id}-${row.window_start}-${index}`}
              className={cn(
                "w-full rounded-lg border border-slate-200 bg-white p-3 text-left shadow-sm transition hover:border-slate-300 hover:shadow-md",
                selectedZoneId === row.zone_id && "border-slate-950 ring-2 ring-slate-950/10",
              )}
              onClick={() => onSelect(row.zone_id)}
              type="button"
            >
              <div className="mb-2 flex items-center justify-between gap-2">
                <RiskBadge score={score} />
                <span className="font-mono text-[11px] text-slate-400">#{index + 1}</span>
              </div>
              <div className="font-semibold text-slate-950">{row.police_station ?? "Unknown station"}</div>
              <div className="mt-0.5 font-mono text-xs text-slate-500">{row.zone_id}</div>
              <div className="mt-2 flex items-center justify-between text-xs text-slate-600">
                <span>{actionLabel(row.recommended_action)}</span>
                <span className="font-semibold text-slate-950">{formatNumber(score, 0)}</span>
              </div>
            </button>
          );
        })}
      </CardContent>
    </Card>
  );
}

function ZoneBrief({
  zone,
  fallback,
  mode,
  windowStart,
}: {
  zone?: ZoneDetails;
  fallback?: RiskRow;
  mode: PlannerMode;
  windowStart?: string;
}) {
  const source = zone?.zone_id ? zone : fallback;
  const score = riskScore(source, mode);
  const projectedRelief = score >= 75 ? 40 : score >= 50 ? 30 : score >= 25 ? 18 : 8;
  const coverageGap = Number(source?.coverage_gap);
  const pfdi = Number(source?.predicted_pfdi ?? source?.observed_pfdi);
  const records = Number(source?.record_count ?? source?.predicted_count);
  const blindspot = Number(source?.blindspot_risk_score);

  if (!source) {
    return (
      <Card className="border-slate-200 bg-white/95">
        <CardHeader>
          <CardTitle>Zone brief</CardTitle>
        </CardHeader>
        <CardContent className="text-sm leading-6 text-slate-600">
          Select a zone from the map or priority queue to see the operational brief.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-slate-200 bg-white/95">
      <CardHeader className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="text-base">{source.police_station ?? "Zone brief"}</CardTitle>
            <div className="mt-1 font-mono text-xs text-slate-500">{source.zone_id}</div>
          </div>
          <RiskBadge score={score} />
        </div>
        <div className="text-xs text-slate-500">{windowLabel(source.window_start ?? windowStart)}</div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-lg bg-slate-50 p-3">
            <div className="text-xs text-slate-500">Disruption proxy</div>
            <div className="mt-1 text-lg font-semibold text-slate-950">{Number.isFinite(pfdi) ? formatNumber(pfdi, 1) : "—"}</div>
          </div>
          <div className="rounded-lg bg-slate-50 p-3">
            <div className="text-xs text-slate-500">Visibility gap</div>
            <div className="mt-1 text-lg font-semibold text-slate-950">
              {Number.isFinite(coverageGap) ? plainPercent(coverageGap) : "—"}
            </div>
          </div>
          <div className="rounded-lg bg-slate-50 p-3">
            <div className="text-xs text-slate-500">Blindspot risk</div>
            <div className="mt-1 text-lg font-semibold text-slate-950">
              {Number.isFinite(blindspot) ? formatNumber(blindspot, 1) : "—"}
            </div>
          </div>
          <div className="rounded-lg bg-slate-50 p-3">
            <div className="text-xs text-slate-500">Records/count</div>
            <div className="mt-1 text-lg font-semibold text-slate-950">{Number.isFinite(records) ? formatNumber(records, 0) : "—"}</div>
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-3">
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-950">
            <Gauge className="h-4 w-4 text-slate-500" />
            Before / after planning view
          </div>
          <div className="space-y-3 text-sm leading-6 text-slate-700">
            <p>
              <span className="font-medium text-slate-950">Current situation:</span>{" "}
              {Number.isFinite(records) ? `${formatNumber(records, 0)} records or predicted counts, ` : ""}
              {Number.isFinite(coverageGap) ? `${plainPercent(coverageGap)} coverage gap, ` : ""}
              action recommended as {actionLabel(source.recommended_action)}.
            </p>
            <p>
              <span className="font-medium text-slate-950">Targeted enforcement goal:</span> planning target of about{" "}
              {projectedRelief}% priority relief after officer verification and obstruction clearing.
            </p>
          </div>
        </div>

        <div className="grid gap-2 text-sm">
          <div className="flex items-start gap-2 rounded-lg bg-blue-50 p-3 text-blue-950">
            <ShieldCheck className="mt-0.5 h-4 w-4" />
            <span>Known signals and evidence confidence are separated from visibility gaps.</span>
          </div>
          <div className="flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-amber-950">
            <EyeOff className="mt-0.5 h-4 w-4" />
            <span>Evening zero records are treated as low evidence, not proof that the zone is safe.</span>
          </div>
        </div>

        <Link
          href={`/planner?window_start=${encodeURIComponent(windowStart ?? String(source.window_start ?? ""))}`}
          className="inline-flex h-9 w-full items-center justify-center gap-2 rounded-md bg-slate-950 px-3 text-sm font-medium text-white hover:bg-slate-800"
        >
          Open planner
          <ArrowRight className="h-4 w-4" />
        </Link>
      </CardContent>
    </Card>
  );
}

function TourOverlay({ step, setStep, onClose }: { step: number; setStep: (step: number) => void; onClose: () => void }) {
  const current = tourSteps[step];
  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      <div
        className="curbflow-tour-spotlight absolute rounded-2xl border-2 border-white bg-transparent shadow-2xl ring-4 ring-red-500/70"
        style={current.spotlight}
      />
      <div
        className="curbflow-tour-card absolute w-[min(420px,calc(100vw-2rem))] rounded-xl border border-slate-200 bg-white p-5 shadow-2xl"
        style={current.card}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <Badge variant="danger">Visual tour · Step {step + 1} of {tourSteps.length}</Badge>
            <h2 className="mt-3 text-xl font-semibold text-slate-950">{current.title}</h2>
          </div>
          <button
            aria-label="Close tour"
            className="rounded-md p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-950"
            onClick={onClose}
            type="button"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <p className="text-sm leading-7 text-slate-700">{current.text}</p>
        <div className="mt-5 flex items-center justify-between gap-3">
          <div className="flex gap-1">
            {tourSteps.map((item, index) => (
              <span
                key={item.title}
                className={cn("h-1.5 w-8 rounded-full", index === step ? "bg-slate-950" : "bg-slate-200")}
              />
            ))}
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" disabled={step === 0} onClick={() => setStep(Math.max(0, step - 1))}>
              <ChevronLeft className="mr-1 h-4 w-4" />
              Back
            </Button>
            {step === tourSteps.length - 1 ? (
              <Button onClick={onClose}>Done</Button>
            ) : (
              <Button onClick={() => setStep(Math.min(tourSteps.length - 1, step + 1))}>
                Next
                <ChevronRight className="ml-1 h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  const selectedZoneId = useCurbFlowStore((state) => state.selectedZoneId);
  const setSelectedZoneId = useCurbFlowStore((state) => state.setSelectedZoneId);
  const mode = useCurbFlowStore((state) => state.plannerMode);
  const setMode = useCurbFlowStore((state) => state.setPlannerMode);
  const [selectedStation, setSelectedStation] = useState("");
  const [stationFocusNonce, setStationFocusNonce] = useState(0);
  const [mapplsQuery, setMapplsQuery] = useState("");
  const [mapplsFocus, setMapplsFocus] = useState<{
    key: string;
    center: [number, number];
    zoom: number;
    label: string;
  } | null>(null);
  const [selectedWindowIndex, setSelectedWindowIndex] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [replaySpeedMs, setReplaySpeedMs] = useState(1400);
  const [tourOpen, setTourOpen] = useState(false);
  const [tourStep, setTourStep] = useState(0);
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);

  const audit = useQuery({ queryKey: ["audit-summary"], queryFn: getAuditSummary });
  const windows = useQuery({
    queryKey: ["prediction-windows", selectedStation],
    queryFn: () => getPredictionWindows({ station: selectedStation || undefined, limit: 144 }),
    refetchOnWindowFocus: false,
  });
  const orderedWindows = useMemo(() => [...(windows.data ?? [])].reverse(), [windows.data]);

  useEffect(() => {
    if (!orderedWindows.length) return;
    setSelectedWindowIndex((current) => {
      if (current !== null && current < orderedWindows.length) return current;
      return bestWindowIndex(orderedWindows);
    });
  }, [orderedWindows]);

  useEffect(() => {
    if (!playing || orderedWindows.length <= 1) return;
    const timer = window.setInterval(() => {
      setSelectedWindowIndex((current) => {
        const value = current ?? 0;
        return value >= orderedWindows.length - 1 ? 0 : value + 1;
      });
    }, replaySpeedMs);
    return () => window.clearInterval(timer);
  }, [orderedWindows.length, playing, replaySpeedMs]);

  const selectedWindow = selectedWindowIndex === null ? undefined : orderedWindows[selectedWindowIndex]?.window_start;
  const selectedHour = hourFromWindow(selectedWindow);
  const mapVariant = selectedHour !== null && selectedHour >= 18 && selectedHour <= 20 ? "blindspot" : "risk";

  const zones = useQuery({
    queryKey: ["command-zones", mode, selectedWindow, selectedStation],
    queryFn: () => getZonesGeoJson({ mode, window_start: selectedWindow, station: selectedStation || undefined }),
    enabled: Boolean(selectedWindow),
    refetchOnWindowFocus: false,
  });
  const hotspots = useQuery({
    queryKey: ["command-hotspots", mode, selectedWindow, selectedStation],
    queryFn: () => getHotspots({ top_k: 12, mode, window_start: selectedWindow, station: selectedStation || undefined }),
    enabled: Boolean(selectedWindow),
  });
  const blindspots = useQuery({
    queryKey: ["command-blindspots", selectedWindow, selectedStation],
    queryFn: () => getBlindspots({ top_k: 12, window_start: selectedWindow, station: selectedStation || undefined }),
    enabled: Boolean(selectedWindow),
  });
  const mapplsSuggestions = useQuery({
    queryKey: ["mappls-place-search", mapplsQuery],
    queryFn: () => searchPlaces({ q: mapplsQuery.trim(), limit: 6 }),
    enabled: mapplsQuery.trim().length >= 3,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  const combinedRows = useMemo(() => [...(hotspots.data ?? []), ...(blindspots.data ?? [])], [blindspots.data, hotspots.data]);
  const stationOptions = useMemo(
    () => stationOptionsFrom(audit.data?.raw_summary, combinedRows),
    [audit.data?.raw_summary, combinedRows],
  );
  const stationScopeReady = useMemo(() => {
    if (!selectedStation || zones.isFetching || !zones.data?.features.length) return false;
    return stationMatchShare(zones.data, selectedStation) >= 0.35;
  }, [selectedStation, zones.data, zones.isFetching]);
  const alertRow = useMemo(
    () =>
      [...combinedRows].sort((left, right) => riskScore(right, mode) - riskScore(left, mode))[0],
    [combinedRows, mode],
  );
  const zoneDetails = useQuery({
    queryKey: ["command-zone-details", selectedZoneId, selectedWindow],
    queryFn: () => getZoneDetails(selectedZoneId ?? "", { window_start: selectedWindow }),
    enabled: Boolean(selectedZoneId),
  });

  const alertScore = riskScore(alertRow, mode);
  const selectedFallback = combinedRows.find((row) => row.zone_id === selectedZoneId) ?? alertRow;
  const phase = replayPhase(selectedHour);
  const mapFocusActive = !leftOpen && !rightOpen;
  const alertInset = {
    left: leftOpen ? "376px" : "76px",
    right: rightOpen ? "408px" : "76px",
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-[#fbfbf9]">
      <CurbFlowMap
        zones={zones.data}
        mode={mode}
        variant={mapVariant}
        selectedHour={selectedHour}
        selectedZoneId={selectedZoneId}
        fitKey={stationScopeReady ? `home-station:${selectedStation}:${stationFocusNonce}:${zones.dataUpdatedAt}` : null}
        fitOnDataLoad={false}
        resetViewKey={!selectedStation ? `default-bengaluru:${stationFocusNonce}` : null}
        focusTarget={mapplsFocus}
        legendClassName={cn(
          "bottom-auto top-[7.2rem] max-w-[220px] transition-all duration-300 ease-out",
          leftOpen ? "left-[376px]" : "left-4",
          rightOpen ? "right-auto" : "",
        )}
        onZoneClick={(zoneId) => {
          setSelectedZoneId(zoneId);
          setRightOpen(true);
        }}
        className="!h-screen !min-h-screen rounded-none border-0 shadow-none"
        label={
          selectedStation
            ? `${selectedStation} focus layer`
            : mapVariant === "blindspot"
              ? "Evening audit layer"
              : "Live priority layer"
        }
      />

      <aside
        className={cn(
          "absolute bottom-4 left-4 top-4 z-30 w-[340px] overflow-auto rounded-2xl border border-slate-200 bg-[#fbfbf9]/96 p-4 shadow-2xl backdrop-blur transition-transform duration-300 ease-out",
          !leftOpen && "-translate-x-[calc(100%+2rem)]",
        )}
      >
          <div className="mb-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h1 className="text-xl font-semibold text-slate-950">CurbFlow Command Center</h1>
                <p className="mt-1 text-sm leading-6 text-slate-600">Map-first enforcement intelligence for tomorrow's deployment.</p>
              </div>
              <button
                aria-label="Hide command queue"
                className="rounded-full border border-slate-200 bg-white p-2 text-slate-600 shadow-sm transition hover:text-slate-950"
                onClick={() => setLeftOpen(false)}
                type="button"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-3 flex gap-2">
              {[
                { href: "/audit", label: "Audit" },
                { href: "/planner", label: "Planner" },
                { href: "/patrol-digital-twin", label: "Patrol twin" },
              ].map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 shadow-sm hover:border-slate-300 hover:text-slate-950"
                >
                  {item.label}
                </Link>
              ))}
            </div>
          </div>

          <div className="mb-4 grid grid-cols-3 gap-2">
            {(["conservative", "balanced", "discovery"] as PlannerMode[]).map((option) => (
              <button
                key={option}
                className={cn(
                  "rounded-lg border px-2 py-2 text-xs font-semibold capitalize shadow-sm transition hover:border-slate-300",
                  mode === option
                    ? "border-slate-950 bg-slate-950 text-white"
                    : "border-slate-200 bg-white text-slate-600",
                )}
                onClick={() => setMode(option)}
                type="button"
              >
                {option}
              </button>
            ))}
          </div>

          <label className="mb-4 block text-xs font-semibold uppercase tracking-wide text-slate-500">
            Mappls place search
            <div className="relative mt-2">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                value={mapplsQuery}
                onChange={(event) => setMapplsQuery(event.target.value)}
                placeholder="Search Bengaluru place"
                className="h-10 w-full rounded-md border border-slate-200 bg-white pl-9 pr-3 text-sm font-normal normal-case text-slate-950 shadow-sm outline-none transition focus:border-slate-400"
              />
            </div>
            {mapplsFocus ? (
              <div className="mt-2 rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-[11px] font-normal normal-case leading-5 text-blue-950">
                Map focused on {mapplsFocus.label}. CurbFlow risk layers remain visible for context.
              </div>
            ) : null}
            {mapplsSuggestions.data?.length ? (
              <div className="mt-2 max-h-44 overflow-auto rounded-md border border-slate-200 bg-white shadow-lg">
                {mapplsSuggestions.data.map((place, index) => {
                  const canFocus = hasPlaceCoordinates(place);
                  return (
                    <button
                      key={`${place.eloc ?? place.place_name}-${index}`}
                      className="block w-full border-b border-slate-100 px-3 py-2 text-left text-xs normal-case text-slate-700 transition last:border-b-0 hover:bg-slate-50"
                      onClick={() => {
                        setMapplsQuery(place.place_name);
                        setSelectedZoneId(undefined);
                        const matchedStation = matchingStationForPlace(place, stationOptions);
                        if (canFocus) {
                          setSelectedStation("");
                          setStationFocusNonce((value) => value + 1);
                          setMapplsFocus({
                            key: `${place.eloc ?? place.place_name}:${Date.now()}`,
                            center: [Number(place.longitude), Number(place.latitude)],
                            zoom: 14.8,
                            label: place.place_name,
                          });
                          return;
                        }
                        if (matchedStation) {
                          setMapplsFocus(null);
                          setSelectedStation(matchedStation);
                          setStationFocusNonce((value) => value + 1);
                        }
                      }}
                      type="button"
                    >
                      <span className="block font-semibold text-slate-950">{place.place_name}</span>
                      <span className="block truncate text-slate-500">
                        {place.place_address ?? (canFocus ? "Mappls coordinate result" : "No coordinate returned")}
                      </span>
                    </button>
                  );
                })}
              </div>
            ) : mapplsQuery.trim().length >= 3 && mapplsSuggestions.isError ? (
              <div className="mt-2 rounded-md border border-amber-100 bg-amber-50 px-3 py-2 text-[11px] font-normal normal-case leading-5 text-amber-950">
                Mappls search is unavailable. Add CURBFLOW_MAPPLS_ACCESS_TOKEN to enable live place suggestions.
              </div>
            ) : (
              <span className="mt-2 block text-[11px] font-normal normal-case leading-5 text-slate-500">
                Powered by Mappls Autosuggest. Use it for real place lookup without changing CurbFlow risk filters.
              </span>
            )}
          </label>

          <label className="mb-4 block text-xs font-semibold uppercase tracking-wide text-slate-500">
            Place / police station
            <select
              value={selectedStation}
              onChange={(event) => {
                setSelectedStation(event.target.value);
                setMapplsFocus(null);
                setSelectedZoneId(undefined);
                setStationFocusNonce((value) => value + 1);
              }}
              className="mt-2 h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm font-normal normal-case text-slate-950 shadow-sm"
            >
              <option value="">Default Bengaluru map</option>
              {stationOptions.map((station) => (
                <option key={station} value={station}>
                  {station}
                </option>
              ))}
            </select>
            <span className="mt-2 block text-[11px] font-normal normal-case leading-5 text-slate-500">
              Select a station to zoom into that operating area. Leave it on default for the full Bengaluru command view.
            </span>
          </label>

          <CommandQueue
            title="Known trouble spots"
            rows={hotspots.data ?? []}
            mode={mode}
            selectedZoneId={selectedZoneId}
            onSelect={(zoneId) => {
              setSelectedZoneId(zoneId);
              setRightOpen(true);
            }}
          />
          <div className="h-3" />
          <CommandQueue
            title="Blindspot audits"
            rows={blindspots.data ?? []}
            mode={mode}
            selectedZoneId={selectedZoneId}
            onSelect={(zoneId) => {
              setSelectedZoneId(zoneId);
              setRightOpen(true);
            }}
          />
      </aside>

      {!leftOpen ? (
        <button
          aria-label="Show command queue"
          className="absolute left-4 top-4 z-40 flex h-11 items-center gap-2 rounded-full border border-slate-200 bg-white/95 px-4 text-sm font-semibold text-slate-950 shadow-xl backdrop-blur transition hover:shadow-2xl"
          onClick={() => setLeftOpen(true)}
          type="button"
        >
          <Menu className="h-4 w-4" />
          Queue
        </button>
      ) : null}

          <div className="absolute top-4 z-20 transition-all duration-300 ease-out" style={alertInset}>
            <div className="curbflow-alert-sweep relative overflow-hidden rounded-lg border border-red-200 bg-red-700 px-4 py-3 text-white shadow-xl">
              <div className="relative z-10 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
                  <div>
                    <div className="text-sm font-bold">
                      {riskBadgeText(riskLevel(alertScore))} — {alertRow?.police_station ?? "Citywide priority"} —{" "}
                      {alertRow?.zone_id ?? "waiting for live prediction"}
                    </div>
                    <div className="mt-0.5 text-xs text-red-50">
                      {timelineMood(selectedHour)} Recommended action: {actionLabel(alertRow?.recommended_action)}.
                    </div>
                  </div>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button variant="secondary" className="bg-white text-slate-950 hover:bg-red-50" onClick={() => setTourOpen(true)}>
                    <CircleHelp className="mr-2 h-4 w-4" />
                    Visual tour
                  </Button>
                  <Button
                    variant="secondary"
                    className="bg-white text-slate-950 hover:bg-red-50"
                    onClick={() => {
                      if (mapFocusActive) {
                        setLeftOpen(true);
                        setRightOpen(true);
                        return;
                      }
                      setLeftOpen(false);
                      setRightOpen(false);
                    }}
                  >
                    <Layers className="mr-2 h-4 w-4" />
                    {mapFocusActive ? "Restore panels" : "Map focus"}
                  </Button>
                </div>
              </div>
            </div>
          </div>

          <div
            className="absolute bottom-4 z-20 rounded-xl border border-slate-200 bg-white/96 p-4 shadow-2xl backdrop-blur transition-all duration-300 ease-out"
            style={alertInset}
          >
            <div className="mb-3 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2 text-sm font-semibold text-slate-950">
                  <Clock3 className="h-4 w-4 text-slate-500" />
                  {windowLabel(selectedWindow)}
                  <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-bold", phase.tone)}>{phase.label}</span>
                </div>
                <p className="mt-1 truncate text-xs text-slate-500">{phase.help}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  onClick={() => {
                    const index = windowIndexInHourRange(orderedWindows, 9, 12);
                    if (index !== null) setSelectedWindowIndex(index);
                  }}
                  disabled={!orderedWindows.length}
                >
                  Morning
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    const index = windowIndexInHourRange(orderedWindows, 18, 20);
                    if (index !== null) setSelectedWindowIndex(index);
                  }}
                  disabled={!orderedWindows.length}
                >
                  Evening audit
                </Button>
                <Button variant="secondary" onClick={() => setPlaying((value) => !value)}>
                  {playing ? <Pause className="mr-2 h-4 w-4" /> : <Play className="mr-2 h-4 w-4" />}
                  {playing ? "Pause replay" : "Replay day"}
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => setReplaySpeedMs((value) => (value === 1400 ? 700 : 1400))}
                >
                  {replaySpeedMs === 1400 ? "1x" : "2x"}
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => setSelectedWindowIndex((current) => Math.max(0, (current ?? 0) - 1))}
                  disabled={!orderedWindows.length}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button
                  variant="secondary"
                  onClick={() =>
                    setSelectedWindowIndex((current) => Math.min(orderedWindows.length - 1, (current ?? 0) + 1))
                  }
                  disabled={!orderedWindows.length}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <input
              aria-label="Prediction window timeline"
              className="h-2 w-full cursor-pointer accent-slate-950"
              disabled={!orderedWindows.length}
              max={Math.max(0, orderedWindows.length - 1)}
              min={0}
              onChange={(event) => setSelectedWindowIndex(Number(event.target.value))}
              type="range"
              value={selectedWindowIndex ?? 0}
            />
            <div className="mt-2 flex justify-between text-[11px] font-medium uppercase tracking-wide text-slate-400">
              <span>Oldest</span>
              <span>{orderedWindows.length} windows</span>
              <span>Latest</span>
            </div>
            <div className="mt-3 grid gap-2 text-xs text-slate-600 md:grid-cols-3">
              <div className="rounded-md bg-red-50 px-3 py-2 text-red-950">
                <strong>Morning:</strong> proven hotspots stand out.
              </div>
              <div className="rounded-md bg-amber-50 px-3 py-2 text-amber-950">
                <strong>Afternoon:</strong> visibility starts dropping.
              </div>
              <div className="rounded-md bg-blue-50 px-3 py-2 text-blue-950">
                <strong>Evening:</strong> audit blindspots, do not assume safe.
              </div>
            </div>
          </div>

      <aside
        className={cn(
          "absolute bottom-4 right-4 top-4 z-30 w-[380px] overflow-auto rounded-2xl border border-slate-200 bg-[#fbfbf9]/96 p-4 shadow-2xl backdrop-blur transition-transform duration-300 ease-out",
          !rightOpen && "translate-x-[calc(100%+2rem)]",
        )}
      >
          <div className="mb-3 flex justify-end">
            <button
              aria-label="Hide zone brief"
              className="rounded-full border border-slate-200 bg-white p-2 text-slate-600 shadow-sm transition hover:text-slate-950"
              onClick={() => setRightOpen(false)}
              type="button"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
          <div className="mb-4 grid grid-cols-2 gap-2">
            <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                <Siren className="h-4 w-4 text-red-600" />
                Records
              </div>
              <div className="mt-2 text-xl font-semibold text-slate-950">{formatNumber(audit.data?.row_count, 0)}</div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                <EyeOff className="h-4 w-4 text-blue-600" />
                Evening gap
              </div>
              <div className="mt-2 text-xl font-semibold text-slate-950">{formatNumber(audit.data?.evening_gap_ratio, 1)}</div>
            </div>
          </div>

          <ZoneBrief zone={zoneDetails.data} fallback={selectedFallback} mode={mode} windowStart={selectedWindow} />

          <Card className="mt-4 border-slate-200 bg-white/95">
            <CardHeader className="p-3">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Radio className="h-4 w-4 text-emerald-600" />
                Command log
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 p-3 text-sm">
              <div className="flex gap-2">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                <span>{mode} mode is active for the current timeline window.</span>
              </div>
              <div className="flex gap-2">
                <Route className="mt-0.5 h-4 w-4 shrink-0 text-blue-600" />
                <span>{hotspots.data?.length ?? 0} known trouble spots and {blindspots.data?.length ?? 0} audit candidates loaded.</span>
              </div>
              <div className="flex gap-2">
                <MapPinned className="mt-0.5 h-4 w-4 shrink-0 text-orange-600" />
                <span>Click any zone to open its morning brief and before/after planning view.</span>
              </div>
            </CardContent>
          </Card>
      </aside>

      {!rightOpen ? (
        <button
          aria-label="Show zone brief"
          className="absolute right-4 top-4 z-40 flex h-11 items-center gap-2 rounded-full border border-slate-200 bg-white/95 px-4 text-sm font-semibold text-slate-950 shadow-xl backdrop-blur transition hover:shadow-2xl"
          onClick={() => setRightOpen(true)}
          type="button"
        >
          Brief
          <ChevronLeft className="h-4 w-4" />
        </button>
      ) : null}

      {tourOpen ? <TourOverlay step={tourStep} setStep={setTourStep} onClose={() => setTourOpen(false)} /> : null}
    </div>
  );
}
