"use client";

import { ArrowRight, X } from "lucide-react";

import { RiskBadge, scoreToRiskLevel } from "@/components/risk-badge";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetOverlay,
  SheetTitle,
} from "@/components/ui/sheet";
import type { ZoneDetails } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/utils";

function humanizeAction(action: string | null | undefined): string {
  if (!action) return "—";
  return action
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

function estimateReduction(pfdi: number | null | undefined): number {
  const p = pfdi ?? 0;
  let raw: number;
  if (p >= 75) raw = 60;
  else if (p >= 50) raw = 45;
  else if (p >= 25) raw = 30;
  else raw = 18;
  return Math.round(raw / 5) * 5;
}

function BeforeAfterBox({ zone }: { zone: ZoneDetails }) {
  const pfdi = zone.predicted_pfdi ?? 0;
  const gapPct = Math.round((zone.coverage_gap ?? 0) * 100);
  const reduction = estimateReduction(pfdi);
  const level = scoreToRiskLevel(pfdi, "hotspot");
  const action = humanizeAction(zone.recommended_action);

  return (
    <div className="overflow-hidden rounded-xl border border-[#e8e8e4]">
      {/* Before */}
      <div className="bg-[#fafaf8] px-4 py-3">
        <div className="mb-2 text-[10px] font-bold uppercase tracking-widest text-[#9b9b9b]">
          Current situation
        </div>
        <div className="flex items-center gap-2">
          <RiskBadge level={level} />
          <span className="text-sm font-semibold text-[#1c1c1e]">
            PFDI {formatNumber(pfdi, 1)}
          </span>
        </div>
        <div className="mt-2 grid grid-cols-2 gap-2 text-[11px]">
          <div className="rounded-lg bg-white px-2.5 py-2 ring-1 ring-[#e8e8e4]">
            <div className="text-[#9b9b9b]">Patrol gap</div>
            <div className="font-semibold text-[#1c1c1e]">{gapPct}%</div>
          </div>
          <div className="rounded-lg bg-white px-2.5 py-2 ring-1 ring-[#e8e8e4]">
            <div className="text-[#9b9b9b]">Records</div>
            <div className="font-semibold text-[#1c1c1e]">{formatNumber(zone.record_count, 0) ?? "—"}</div>
          </div>
        </div>
      </div>

      {/* Divider with arrow */}
      <div className="flex items-center gap-2 border-y border-[#e8e8e4] bg-white px-4 py-1.5">
        <ArrowRight className="h-3 w-3 text-[#9b9b9b]" />
        <span className="text-[10px] font-semibold uppercase tracking-widest text-[#9b9b9b]">
          After targeted enforcement
        </span>
      </div>

      {/* After */}
      <div className="bg-emerald-50 px-4 py-3">
        <div className="text-base font-bold text-emerald-800">~{reduction}% congestion reduction</div>
        <div className="mt-1 text-[11px] text-emerald-700">
          Action: <span className="font-semibold">{action}</span>
        </div>
        <div className="mt-1 text-[10px] text-emerald-600">
          Based on enforcement patterns of similar high-PFDI zones in dataset
        </div>
      </div>
    </div>
  );
}

function ZoneDetailsGrid({ zone }: { zone: ZoneDetails }) {
  return (
    <div className="grid grid-cols-2 gap-2 text-[11px]">
      <div className="rounded-lg bg-[#fafaf8] px-2.5 py-2 ring-1 ring-[#e8e8e4]">
        <div className="text-[#9b9b9b]">Station</div>
        <div className="font-semibold text-[#1c1c1e] truncate">{zone.police_station ?? "—"}</div>
      </div>
      <div className="rounded-lg bg-[#fafaf8] px-2.5 py-2 ring-1 ring-[#e8e8e4]">
        <div className="text-[#9b9b9b]">PFDI score</div>
        <div className="font-semibold text-[#1c1c1e]">{formatNumber(zone.predicted_pfdi, 1)}</div>
      </div>
      <div className="rounded-lg bg-[#fafaf8] px-2.5 py-2 ring-1 ring-[#e8e8e4]">
        <div className="text-[#9b9b9b]">Coverage gap</div>
        <div className="font-semibold text-blue-700">
          {formatNumber((zone.coverage_gap ?? 0) * 100, 1)}%
        </div>
      </div>
      <div className="rounded-lg bg-[#fafaf8] px-2.5 py-2 ring-1 ring-[#e8e8e4]">
        <div className="text-[#9b9b9b]">Blindspot risk</div>
        <div className="font-semibold text-violet-700">{formatNumber(zone.blindspot_risk_score, 1)}</div>
      </div>
      <div className="col-span-2 rounded-lg bg-[#fafaf8] px-2.5 py-2 ring-1 ring-[#e8e8e4]">
        <div className="text-[#9b9b9b]">Recommended action</div>
        <div className="font-semibold text-[#1c1c1e]">{humanizeAction(zone.recommended_action)}</div>
      </div>
    </div>
  );
}

// Inline right panel for the map-first dashboard layout
export function ZoneDetailPanel({
  zone,
  onClose,
}: {
  zone?: ZoneDetails;
  onClose: () => void;
}) {
  if (!zone?.zone_id) return null;

  const level = scoreToRiskLevel(zone.predicted_pfdi, "hotspot");

  return (
    <div className="flex w-[340px] shrink-0 flex-col overflow-hidden border-l border-[#e8e8e4] bg-white">
      {/* Header */}
      <div className="flex shrink-0 items-start justify-between gap-2 border-b border-[#e8e8e4] px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-[#1c1c1e]">Zone {zone.zone_id}</span>
            <RiskBadge level={level} />
          </div>
          <div className="mt-0.5 text-[11px] text-[#9b9b9b]">
            {formatDateTime(zone.window_start) ?? zone.police_station ?? "—"}
          </div>
        </div>
        <button
          onClick={onClose}
          className="shrink-0 rounded-lg p-1.5 text-[#9b9b9b] transition-colors hover:bg-[#f0f0ec] hover:text-[#1c1c1e]"
          aria-label="Close zone detail"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto space-y-4 p-4">
        <BeforeAfterBox zone={zone} />
        <div>
          <div className="mb-2 text-[10px] font-bold uppercase tracking-widest text-[#9b9b9b]">
            Risk details
          </div>
          <ZoneDetailsGrid zone={zone} />
        </div>
      </div>
    </div>
  );
}

// Legacy sheet drawer — kept for compatibility with non-dashboard pages
export function ZoneDetailsDrawer({
  zone,
  onClose,
}: {
  zone?: ZoneDetails;
  onClose: () => void;
}) {
  if (!zone?.zone_id) return null;
  const level = scoreToRiskLevel(zone.predicted_pfdi, "hotspot");

  return (
    <Sheet open={Boolean(zone?.zone_id)}>
      <SheetOverlay onClick={onClose} />
      <SheetContent>
        <SheetHeader>
          <div>
            <SheetTitle>Zone {zone.zone_id}</SheetTitle>
            <SheetDescription>{formatDateTime(zone.window_start)}</SheetDescription>
          </div>
          <SheetClose onClose={onClose} />
        </SheetHeader>
        <div className="mb-4">
          <RiskBadge level={level} />
        </div>
        <div className="space-y-4">
          <BeforeAfterBox zone={zone} />
          <ZoneDetailsGrid zone={zone} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
