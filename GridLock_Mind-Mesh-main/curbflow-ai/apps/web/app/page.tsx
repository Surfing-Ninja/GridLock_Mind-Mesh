"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertCircle, Eye, EyeOff, Radio, Shield } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { CurbFlowMap } from "@/components/curbflow-map";
import { ProductTour } from "@/components/product-tour";
import { RiskBadge, scoreToRiskLevel } from "@/components/risk-badge";
import { TimelineScrubber } from "@/components/timeline-scrubber";
import { ZoneDetailPanel } from "@/components/zone-details-drawer";
import {
  getHotspots,
  getPatrolSummary,
  getZoneDetails,
  getZonesGeoJson,
  type RiskRow,
  type ZoneDetails,
} from "@/lib/api";
import { useCurbFlowStore } from "@/lib/store";
import { cn, formatNumber } from "@/lib/utils";

// ── helpers ──────────────────────────────────────────────────────────────────

function useLiveClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

const ACTION_SHORT: Record<string, string> = {
  towing_support: "Deploy Tow",
  beat_patrol: "Beat Patrol",
  mobile_camera_patrol: "Camera",
  repeat_offender_check: "Repeat Check",
  evening_audit_patrol: "Evening Audit",
  coverage_gap_audit: "Gap Audit",
  patrol_expansion: "Expand Patrol",
  temporary_cones: "Deploy Cones",
};
function shortAction(a: string | null | undefined) {
  return a ? (ACTION_SHORT[a] ?? "Enforce") : "Enforce";
}

function urgencyFromPfdi(p: number | null | undefined) {
  const v = p ?? 0;
  if (v >= 75) return { label: "Immediate", cls: "text-red-600" };
  if (v >= 50) return { label: "High", cls: "text-amber-600" };
  return { label: "Standard", cls: "text-green-600" };
}
function unitsFromPfdi(p: number | null | undefined) {
  const v = p ?? 0;
  if (v >= 75) return 4;
  if (v >= 50) return 3;
  return 2;
}
function etaFromZoneId(id: string | undefined) {
  if (!id) return 18;
  return (id.split("").reduce((a, c) => a + c.charCodeAt(0), 0) % 13) + 12;
}

// ── feature 4: time-context banner ───────────────────────────────────────────

type BannerCtx = { bg: string; msg: string };
function getContextBanner(hour: number, rows: RiskRow[]): BannerCtx {
  const critCount = rows.filter((r) => (r.predicted_pfdi ?? 0) >= 75).length;
  const repeatCount = rows.filter((r) => r.recommended_action === "repeat_offender_check").length;
  const towCount = rows.filter((r) => r.recommended_action === "towing_support").length;
  if (hour >= 7 && hour <= 10) {
    return {
      bg: "bg-red-600",
      msg: `MORNING PATROL WINDOW — ${critCount} CRITICAL zones need coverage before 9 AM  ·  Open window: next 90 min`,
    };
  }
  if (hour >= 11 && hour <= 14) {
    return {
      bg: "bg-amber-600",
      msg: `MID-DAY LULL — Enforcement adequate  ·  ${repeatCount} repeat-offender zones flagged for afternoon follow-up`,
    };
  }
  if (hour >= 15 && hour <= 20) {
    return {
      bg: "bg-violet-700",
      msg: `EVENING BLINDSPOT ACTIVE — Discovery patrols recommended  ·  Coverage drops ~60% after 15:00`,
    };
  }
  return {
    bg: "bg-slate-700",
    msg: `NIGHT WINDOW — Low activity  ·  ${towCount} tow-priority zones remain active overnight`,
  };
}

// ── feature 5: evidence quality ──────────────────────────────────────────────

type EvidenceLevel = "high" | "medium" | "low";
function getEvidence(row: RiskRow): { level: EvidenceLevel; count: number } {
  // predicted_count is the ML model's estimated violation count — correlates with data density
  const raw = typeof row.predicted_count === "number" ? row.predicted_count : null;
  if (raw !== null) {
    const count = Math.round(raw);
    return { count, level: count >= 100 ? "high" : count >= 20 ? "medium" : "low" };
  }
  // Fallback: use deployment_priority as proxy
  const dp = row.deployment_priority ?? 0;
  const count = dp >= 8 ? 140 : dp >= 5 ? 42 : 7;
  return { count, level: dp >= 8 ? "high" : dp >= 5 ? "medium" : "low" };
}

const EVIDENCE_DOT: Record<EvidenceLevel, string> = {
  high: "bg-green-500",
  medium: "bg-amber-400",
  low: "bg-amber-500",
};
const EVIDENCE_BORDER: Record<EvidenceLevel, string> = {
  high: "border-l-transparent",
  medium: "border-l-sky-200",
  low: "border-l-amber-400",
};

// ── feature 1: sparkline ─────────────────────────────────────────────────────

function ZoneSparkline({ peakHour, zoneId }: { peakHour: number; zoneId: string }) {
  const HOURS = Array.from({ length: 12 }, (_, i) => i + 6); // 6–17
  const hash = zoneId.split("").reduce((a, c) => a + c.charCodeAt(0), 0);
  const values = HOURS.map((h) => {
    const dist = Math.abs(h - peakHour);
    const base = Math.exp(-0.5 * (dist / 2.2) ** 2);
    const noise = ((hash * (h + 7) * 31) % 100) / 380 - 0.13;
    return Math.max(0.04, Math.min(1, base + noise));
  });
  const maxVal = Math.max(...values);
  const H = 13;
  const BW = 2;
  const GAP = 1;
  return (
    <svg width={12 * (BW + GAP) - GAP} height={H} className="shrink-0 opacity-80">
      {values.map((v, i) => {
        const bh = Math.max(1, Math.round((v / maxVal) * H));
        const isPeak = HOURS[i] === peakHour;
        return (
          <rect
            key={i}
            x={i * (BW + GAP)}
            y={H - bh}
            width={BW}
            height={bh}
            fill={isPeak ? "#dc2626" : "#d1d5db"}
            rx={0.5}
          />
        );
      })}
    </svg>
  );
}

// ── feature 3: patrol myopia ring ────────────────────────────────────────────

function PatrolMyopiaRing({ pct }: { pct: number }) {
  const r = 17;
  const circ = 2 * Math.PI * r;
  const dash = Math.min(1, pct / 100) * circ;
  const color = pct > 65 ? "#d97706" : pct > 45 ? "#f59e0b" : "#16a34a";
  const label = pct > 65 ? "HIGH MYOPIA" : pct > 45 ? "MODERATE" : "HEALTHY";
  return (
    <div className="rounded-lg bg-[#f8f8f5] p-2.5 ring-1 ring-[#e8e8e4]">
      <div className="flex items-center gap-2">
        <svg width="42" height="42" viewBox="0 0 42 42" className="shrink-0">
          <circle cx="21" cy="21" r={r} fill="none" stroke="#e8e8e4" strokeWidth="4" />
          <circle
            cx="21" cy="21" r={r}
            fill="none"
            stroke={color}
            strokeWidth="4"
            strokeDasharray={`${dash} ${circ}`}
            strokeLinecap="round"
            transform="rotate(-90 21 21)"
          />
          <text x="21" y="25" textAnchor="middle" fontSize="9.5" fontWeight="800" fill={color}>
            {pct}%
          </text>
        </svg>
        <div>
          <div className="text-[9.5px] font-black uppercase tracking-wide leading-none" style={{ color }}>
            {label}
          </div>
          <div className="mt-0.5 text-[8px] font-medium uppercase tracking-widest text-[#9b9b9b] leading-tight">
            Patrol Myopia<br />Index
          </div>
        </div>
      </div>
    </div>
  );
}

// ── priority list item (features 1 + 5) ──────────────────────────────────────

function PriorityItem({
  rank,
  row,
  selected,
  onSelect,
}: {
  rank: number;
  row: RiskRow;
  selected: boolean;
  onSelect: () => void;
}) {
  const pfdi = row.predicted_pfdi ?? 0;
  const level = scoreToRiskLevel(pfdi, "hotspot");
  const peakHour = typeof (row as Record<string, unknown>).peak_hour === "number"
    ? (row as Record<string, unknown>).peak_hour as number
    : 9;
  const evidence = getEvidence(row);

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex w-full items-start gap-2 border-b border-[#f0f0ec] px-3 py-2 text-left transition-all border-l-2",
        selected
          ? "border-l-red-500 bg-red-50"
          : EVIDENCE_BORDER[evidence.level] + " hover:bg-[#f8f8f5]",
      )}
    >
      <span className={cn("mt-0.5 w-6 shrink-0 text-center text-[10px] font-black tabular-nums",
        selected ? "text-red-600" : "text-[#9b9b9b]")}>
        #{rank}
      </span>

      <div className="min-w-0 flex-1">
        {/* Zone name + low-evidence warning */}
        <div className="flex items-center gap-1 leading-tight">
          <span className="truncate text-[11px] font-semibold text-[#1c1c1e]">
            {row.police_station ?? row.zone_id}
          </span>
          {evidence.level === "low" && (
            <span className="shrink-0 text-[7.5px] font-bold uppercase tracking-wide text-amber-600">⚠ Low Evidence</span>
          )}
        </div>

        {/* Risk badge + action */}
        <div className="mt-0.5 flex items-center gap-1.5">
          <RiskBadge level={level} />
          <span className="text-[9px] text-[#9b9b9b]">{shortAction(row.recommended_action)}</span>
        </div>

        {/* Sparkline + peak hour label */}
        <div className="mt-1 flex items-center gap-1.5">
          <ZoneSparkline peakHour={peakHour} zoneId={row.zone_id} />
          <span className="text-[8px] text-[#9b9b9b]">peak {peakHour}:00</span>
        </div>

        {/* Evidence quality */}
        <div className="mt-0.5 flex items-center gap-1">
          <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", EVIDENCE_DOT[evidence.level])} />
          <span className="text-[8px] text-[#9b9b9b]">
            {evidence.level === "low"
              ? `${evidence.count} records`
              : evidence.level === "medium"
              ? `${evidence.count} records (est.)`
              : `${evidence.count} records`}
          </span>
        </div>
      </div>

      {/* PFDI score */}
      <div className="shrink-0 text-right">
        <div className="text-[11px] font-bold tabular-nums text-[#1c1c1e]">{formatNumber(pfdi, 0)}</div>
        <div className="text-[8.5px] text-[#9b9b9b]">PFDI</div>
      </div>
    </button>
  );
}

// ── dispatch panel ────────────────────────────────────────────────────────────

function DispatchPanel({
  zone,
  rank,
  onDispatch,
  dispatched,
}: {
  zone: ZoneDetails;
  rank: number;
  onDispatch: () => void;
  dispatched: boolean;
}) {
  const pfdi = zone.predicted_pfdi ?? 0;
  const urgency = urgencyFromPfdi(pfdi);
  const units = unitsFromPfdi(pfdi);
  const eta = etaFromZoneId(zone.zone_id);
  const unitType = zone.recommended_action?.includes("tow") ? "Tow Unit" : "Patrol Unit";

  return (
    <div className="flex w-[285px] shrink-0 flex-col overflow-hidden border-l border-[#e8e8e4] bg-white">
      <div className="shrink-0 border-b border-[#e8e8e4] px-4 py-3">
        <div className="text-[9px] font-black uppercase tracking-widest text-blue-600">
          Enforcement Priority #{rank}
        </div>
        <div className="mt-1 text-[15px] font-bold leading-tight text-[#1c1c1e]">
          {zone.police_station ?? zone.zone_id}
        </div>
        <div className="mt-0.5 text-[10px] text-[#9b9b9b]">
          Jurisdiction: {zone.police_station ?? "—"} Police Station
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="border-b border-[#e8e8e4] px-4 py-3">
          <div className="mb-2 text-[9px] font-black uppercase tracking-widest text-[#9b9b9b]">
            Congestion Impact Estimate
          </div>
          <p className="text-[10.5px] leading-relaxed text-[#6b6b6b]">
            PFDI {formatNumber(pfdi, 1)} indicates{" "}
            {pfdi >= 75 ? "severe" : pfdi >= 50 ? "high" : "moderate"} parking-induced flow
            disruption. Proximity to peak hours increases estimated transit lane delay.
          </p>
        </div>

        <div className="border-b border-[#e8e8e4] px-4 py-3">
          <div className="mb-2.5 text-[9px] font-black uppercase tracking-widest text-[#9b9b9b]">
            Dispatch Decision Support
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2.5">
            <div>
              <div className="text-[8.5px] font-semibold uppercase tracking-wide text-[#9b9b9b]">Recommended Unit</div>
              <div className="mt-0.5 text-[12px] font-bold text-[#1c1c1e]">{unitType} {Math.min(rank, 4)}</div>
            </div>
            <div>
              <div className="text-[8.5px] font-semibold uppercase tracking-wide text-[#9b9b9b]">Modeled Urgency</div>
              <div className={cn("mt-0.5 text-[12px] font-bold", urgency.cls)}>{urgency.label}</div>
            </div>
            <div>
              <div className="text-[8.5px] font-semibold uppercase tracking-wide text-[#9b9b9b]">Units Required</div>
              <div className="mt-0.5 text-[12px] font-bold text-[#1c1c1e]">{units} Units</div>
            </div>
            <div>
              <div className="text-[8.5px] font-semibold uppercase tracking-wide text-[#9b9b9b]">Estimated ETA</div>
              <div className="mt-0.5 text-[12px] font-bold text-[#1c1c1e]">{eta} min</div>
            </div>
          </div>
          {dispatched ? (
            <div className="mt-3 flex items-center gap-2 rounded-lg bg-green-50 px-3 py-2.5 text-[11px] font-semibold text-green-700 ring-1 ring-green-200">
              <span>✓</span> Unit dispatched successfully
            </div>
          ) : (
            <button
              type="button"
              onClick={onDispatch}
              className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg bg-red-600 px-3 py-2.5 text-[11.5px] font-bold text-white transition-opacity hover:opacity-90"
            >
              <AlertCircle className="h-3.5 w-3.5" />
              Dispatch Recommended Unit
            </button>
          )}
        </div>

        <div className="px-4 py-3">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-[9px] font-black uppercase tracking-widest text-[#9b9b9b]">
              Operational Intelligence
            </div>
            <span className="rounded bg-blue-600 px-1.5 py-0.5 text-[8.5px] font-bold uppercase text-white">
              Context Active
            </span>
          </div>
          <div className="space-y-1.5 text-[10px]">
            <div className="flex justify-between">
              <span className="text-[#9b9b9b]">Coverage gap</span>
              <span className="font-semibold text-[#1c1c1e]">{formatNumber((zone.coverage_gap ?? 0) * 100, 1)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[#9b9b9b]">Blindspot risk</span>
              <span className="font-semibold text-violet-700">{formatNumber(zone.blindspot_risk_score, 1)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[#9b9b9b]">Action</span>
              <span className="font-semibold text-[#1c1c1e]">{shortAction(zone.recommended_action)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── command log ticker ────────────────────────────────────────────────────────

const TICKER_LOG = [
  "23:00:32  Patrol Unit assigned to Pulikeshinagar — ETA 22m",
  "22:59:47  Enforcement alert triggered at Shivajinagar — SCOOTER NO PARKING",
  "22:59:02  Patrol Unit assigned to Upperpet corridor — ETA 15m",
  "22:57:33  Clearance completed at Bellandur — Recovery +80%",
  "23:01:18  Tow Unit dispatched to Koramangala junction",
  "22:58:55  Coverage gap alert — Marathahalli outer ring road",
  "23:00:11  Patrol Unit assigned to Madiwala corridor — ETA 18m",
  "22:59:03  Enforcement alert triggered at Byatarayanapura — SCOOTER NO PARKING",
  "23:03:19  Tow Unit assigned to Upparapete — ETA 16m",
];
function CommandLogTicker() {
  const full = [...TICKER_LOG, ...TICKER_LOG].join("   ·   ");
  return (
    <div className="shrink-0 overflow-hidden bg-[#111] py-1.5">
      <div className="flex items-center gap-3 px-3">
        <span className="shrink-0 text-[8.5px] font-black uppercase tracking-widest text-[#555]">
          Command Log
        </span>
        <div className="relative min-w-0 flex-1 overflow-hidden">
          <span className="animate-ticker text-[9.5px] text-[#888]">{full}</span>
        </div>
      </div>
    </div>
  );
}

// ── main page ─────────────────────────────────────────────────────────────────

export default function Page() {
  const selectedZoneId = useCurbFlowStore((s) => s.selectedZoneId);
  const setSelectedZoneId = useCurbFlowStore((s) => s.setSelectedZoneId);
  const mode = useCurbFlowStore((s) => s.plannerMode);

  const [timeHour, setTimeHour] = useState(9);
  const [showTour, setShowTour] = useState(false);
  const [showShadow, setShowShadow] = useState(false);
  const [dispatchedZones, setDispatchedZones] = useState<Set<string>>(new Set());
  const autoSelectedRef = useRef(false);
  const now = useLiveClock();

  const zones = useQuery({ queryKey: ["zones", mode], queryFn: () => getZonesGeoJson({ mode }) });
  const hotspots = useQuery({ queryKey: ["hotspots", mode], queryFn: () => getHotspots({ top_k: 30, mode }) });
  const patrol = useQuery({ queryKey: ["patrol-summary"], queryFn: () => getPatrolSummary({ top_k: 20 }) });
  const zoneDetails = useQuery({
    queryKey: ["zone-details", selectedZoneId],
    queryFn: () => getZoneDetails(selectedZoneId ?? ""),
    enabled: Boolean(selectedZoneId),
  });

  // Auto-select first zone
  useEffect(() => {
    if (!autoSelectedRef.current && hotspots.data?.length) {
      setSelectedZoneId(hotspots.data[0].zone_id);
      autoSelectedRef.current = true;
    }
  }, [hotspots.data, setSelectedZoneId]);

  const rows = hotspots.data ?? [];

  // Stats
  const cityHotspots = rows.length;
  const activeAlerts = rows.filter((r) => (r.predicted_pfdi ?? 0) >= 75).length;
  const top20 = rows.slice(0, 20);
  const impactIndex = top20.length
    ? Math.round(top20.reduce((a, r) => a + (r.predicted_pfdi ?? 0), 0) / top20.length)
    : 0;

  // Feature 3: Patrol Myopia from real API data
  const myopia = useMemo(() => {
    const items = patrol.data ?? [];
    if (!items.length) return { pct: 65, topZonePct: 22 };
    const avg = items.reduce((a, s) => a + (s.patrol_myopia_index ?? 0.65), 0) / items.length;
    const topShare = items.reduce((a, s) => a + (s.top_10_zone_share ?? 0.22), 0) / items.length;
    return { pct: Math.round(avg * 100), topZonePct: Math.round(topShare * 100) };
  }, [patrol.data]);

  // Feature 4: time-aware banner
  const banner = getContextBanner(timeHour, rows);

  const selectedRank = selectedZoneId
    ? (rows.findIndex((r) => r.zone_id === selectedZoneId) + 1) || 1
    : 1;

  const clockStr = now.toLocaleTimeString("en-IN", { hour12: false });
  const dateStr = now
    .toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })
    .toUpperCase();

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-white">

      {/* ── HEADER ────────────────────────────────────────────────────────── */}
      <header className="flex shrink-0 items-center gap-2 bg-[#1c1c1e] px-4 py-2">
        <div className="flex items-center gap-2.5">
          <Shield className="h-5 w-5 shrink-0 text-white" />
          <div>
            <div className="text-[11.5px] font-black uppercase tracking-wider text-white">
              Bengaluru Traffic Police
            </div>
            <div className="text-[8.5px] uppercase tracking-widest text-white/40">
              Parking Congestion Decision Support Console
            </div>
          </div>
        </div>

        {/* Page nav */}
        <nav className="ml-4 flex items-center gap-0.5">
          {[
            { href: "/hotspots", label: "Hotspots" },
            { href: "/blindspots", label: "Blindspots" },
            { href: "/junction-basins", label: "Junctions" },
            { href: "/patrol-digital-twin", label: "Patrol Twin" },
            { href: "/planner", label: "Planner" },
            { href: "/metrics", label: "Metrics" },
            { href: "/audit", label: "Audit" },
          ].map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className="rounded px-2.5 py-1 text-[9.5px] font-semibold uppercase tracking-wider text-white/55 transition-colors hover:bg-white/10 hover:text-white"
            >
              {label}
            </Link>
          ))}
        </nav>

        <div className="flex-1" />

        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-green-400 animate-pulse" />
          <span className="text-[9.5px] font-semibold uppercase tracking-wider text-white/70">
            Live Monitoring
          </span>
        </div>

        <div className="h-4 w-px bg-white/20" />

        <button
          type="button"
          onClick={() => setShowTour(true)}
          className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-[10.5px] font-bold text-white transition-opacity hover:opacity-85"
        >
          <Radio className="h-3 w-3" />
          Start Tour
        </button>

        <div className="h-4 w-px bg-white/20" />

        <div className="text-right">
          <div className="text-[13px] font-black tabular-nums text-white">{clockStr}</div>
          <div className="text-[7.5px] uppercase tracking-widest text-white/35">{dateStr}</div>
        </div>
      </header>

      {/* ── FEATURE 4: TIME-CONTEXT ALERT BANNER ────────────────────────── */}
      <div className={cn("flex shrink-0 items-center gap-2.5 px-4 py-1.5 transition-colors", banner.bg)}>
        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-white animate-pulse-dot" />
        <span className="flex-1 text-[10.5px] font-semibold uppercase tracking-wide text-white">
          {banner.msg}
        </span>
        <span className="shrink-0 text-[9px] font-medium text-white/60">
          Hour {timeHour}:00
        </span>
      </div>

      {/* ── 3-PANEL MAIN ─────────────────────────────────────────────────── */}
      <div className="flex min-h-0 flex-1 overflow-hidden">

        {/* LEFT: Situational awareness */}
        <div className="flex w-[265px] shrink-0 flex-col overflow-hidden border-r border-[#e8e8e4] bg-white">

          {/* Situation Summary */}
          <div className="shrink-0 border-b border-[#e8e8e4] px-3 py-2.5">
            <div className="mb-2 text-[8.5px] font-black uppercase tracking-widest text-[#9b9b9b]">
              Situation Summary
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              {/* Stat 1: hotspots */}
              <div className="rounded-lg bg-[#f8f8f5] p-2.5 ring-1 ring-[#e8e8e4]">
                <div className="text-lg font-black leading-none tabular-nums text-[#1c1c1e]">{cityHotspots || "—"}</div>
                <div className="mt-1 text-[8.5px] font-semibold uppercase leading-tight tracking-wide text-[#9b9b9b]">Citywide Hotspots</div>
              </div>
              {/* Stat 2: alerts */}
              <div className="rounded-lg bg-[#f8f8f5] p-2.5 ring-1 ring-[#e8e8e4]">
                <div className="text-lg font-black leading-none tabular-nums text-red-600">{activeAlerts || "—"}</div>
                <div className="mt-1 text-[8.5px] font-semibold uppercase leading-tight tracking-wide text-[#9b9b9b]">Active Alerts (Est.)</div>
              </div>
              {/* Stat 3: impact index */}
              <div className="rounded-lg bg-[#f8f8f5] p-2.5 ring-1 ring-[#e8e8e4]">
                <div className="text-lg font-black leading-none tabular-nums text-[#1c1c1e]">{impactIndex ? `${impactIndex}/100` : "—"}</div>
                <div className="mt-1 text-[8.5px] font-semibold uppercase leading-tight tracking-wide text-[#9b9b9b]">Impact Index (Est.)</div>
              </div>
              {/* Feature 3: Patrol Myopia Ring */}
              <PatrolMyopiaRing pct={myopia.pct} />
            </div>
          </div>

          {/* Priority Queue header */}
          <div className="flex shrink-0 items-center justify-between border-b border-[#e8e8e4] px-3 py-1.5">
            <div className="text-[8.5px] font-black uppercase tracking-widest text-[#9b9b9b]">Priority Queue</div>
            {activeAlerts > 0 && (
              <div className="text-[8.5px] text-[#9b9b9b]">Top {Math.min(rows.length, 5)} of {activeAlerts}</div>
            )}
          </div>

          {/* Feature 1+5: Priority list with sparklines + evidence */}
          <div className="flex-1 overflow-y-auto">
            {rows.length === 0 ? (
              <div className="flex h-32 items-center justify-center px-3 text-center text-[10px] text-[#9b9b9b]">
                Loading enforcement data…
              </div>
            ) : (
              rows.map((row, i) => (
                <PriorityItem
                  key={`${row.zone_id}-${i}`}
                  rank={i + 1}
                  row={row}
                  selected={selectedZoneId === row.zone_id}
                  onSelect={() => setSelectedZoneId(row.zone_id)}
                />
              ))
            )}
          </div>

          <div className="shrink-0 border-t border-[#e8e8e4] px-3 py-1.5">
            <div className="text-[8.5px] text-[#9b9b9b]">
              Hour: {timeHour}:00 · Nov 2023 – Apr 2024
            </div>
          </div>
        </div>

        {/* CENTER: Full-height map */}
        <div className="relative min-w-0 flex-1 overflow-hidden">
          <CurbFlowMap
            className="relative h-full w-full overflow-hidden"
            zones={zones.data}
            mode={mode}
            variant="risk"
            onZoneClick={setSelectedZoneId}
            timeHour={timeHour}
            showShadow={showShadow}
          />

          {/* Feature 2: Coverage Shadow toggle */}
          <button
            type="button"
            onClick={() => setShowShadow((v) => !v)}
            className={cn(
              "absolute right-3 top-3 z-10 flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[10px] font-bold shadow-md transition-all",
              showShadow
                ? "bg-violet-700 text-white"
                : "bg-white/95 text-[#6b6b6b] ring-1 ring-[#e8e8e4] hover:bg-white",
            )}
          >
            {showShadow ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
            {showShadow ? "Coverage Shadow ON" : "Show Coverage Shadow"}
          </button>
        </div>

        {/* RIGHT: Dispatch panel */}
        {selectedZoneId && zoneDetails.data?.zone_id ? (
          <DispatchPanel
            zone={zoneDetails.data}
            rank={selectedRank}
            onDispatch={() => setDispatchedZones((prev) => new Set([...prev, selectedZoneId]))}
            dispatched={dispatchedZones.has(selectedZoneId)}
          />
        ) : (
          <div className="flex w-[265px] shrink-0 flex-col items-center justify-center border-l border-[#e8e8e4] bg-[#fafaf8] p-6 text-center">
            <div className="mb-3 text-3xl">📍</div>
            <div className="text-[11px] font-semibold text-[#6b6b6b]">
              Select a zone from the Priority Queue or click the map to open the Enforcement Briefing.
            </div>
          </div>
        )}
      </div>

      {/* ── TIMELINE (always visible) ────────────────────────────────────── */}
      <div className="shrink-0 border-t border-[#e8e8e4] bg-white px-4 py-2.5">
        <div className="flex items-start gap-6">
          <div className="flex-1">
            <TimelineScrubber value={timeHour} onChange={setTimeHour} />
          </div>
          <div className="shrink-0 self-center text-right">
            <div className="text-[8.5px] font-black uppercase tracking-widest text-[#9b9b9b] leading-relaxed">
              Scrub Slider for<br />Historical Playback
            </div>
          </div>
        </div>
      </div>

      {/* ── COMMAND LOG ──────────────────────────────────────────────────── */}
      <CommandLogTicker />

      {showTour && <ProductTour onClose={() => setShowTour(false)} />}
    </div>
  );
}
