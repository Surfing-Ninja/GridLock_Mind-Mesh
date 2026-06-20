"use client";

import { ArrowRight, EyeOff, MapPinned } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { RiskRow } from "@/lib/api";
import { cn, formatNumber } from "@/lib/utils";

function actionLabel(value?: string | null) {
  return String(value ?? "evening_audit_patrol")
    .replaceAll("_", " ")
    .replace(/\s+/g, " ")
    .trim();
}

function auditLabel(score?: number | null) {
  const value = Number(score ?? 0);
  if (value >= 75) return { label: "Critical audit", className: "bg-red-700 text-white" };
  if (value >= 50) return { label: "High audit", className: "bg-orange-600 text-white" };
  if (value >= 25) return { label: "Coverage gap", className: "bg-blue-700 text-white" };
  return { label: "Low evidence", className: "bg-slate-700 text-white" };
}

export function BlindSpotTable({ rows = [], onSelect }: { rows?: RiskRow[]; onSelect?: (zoneId: string) => void }) {
  if (!rows.length) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
        No blindspot audit rows are available for the selected filters.
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      {rows.map((row, index) => {
        const audit = auditLabel(row.blindspot_risk_score ?? row.explore_score);
        return (
          <button
            key={`${row.zone_id}-${row.window_start}-${index}`}
            type="button"
            onClick={() => onSelect?.(row.zone_id)}
            className="group rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-lg"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-bold uppercase", audit.className)}>
                    {audit.label}
                  </span>
                  <Badge variant="info">Not a proven hotspot</Badge>
                  <span className="font-mono text-xs text-slate-400">#{index + 1}</span>
                </div>
                <div className="mt-2 flex items-center gap-2 text-base font-semibold text-slate-950">
                  <MapPinned className="h-4 w-4 text-blue-700" />
                  {row.police_station ?? "Unknown station"}
                </div>
                <div className="mt-1 font-mono text-xs text-slate-500">{row.zone_id}</div>
              </div>
              <ArrowRight className="mt-2 h-4 w-4 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-slate-950" />
            </div>

            <div className="mt-4 grid grid-cols-3 gap-2 text-sm">
              <div className="rounded-lg bg-blue-50 p-2">
                <div className="text-[11px] uppercase text-blue-700">Coverage gap</div>
                <div className="font-semibold text-blue-950">
                  {formatNumber((row.coverage_gap ?? 0) * 100, 1)}%
                </div>
              </div>
              <div className="rounded-lg bg-orange-50 p-2">
                <div className="text-[11px] uppercase text-orange-600">Audit risk</div>
                <div className="font-semibold text-orange-950">{formatNumber(row.blindspot_risk_score, 1)}</div>
              </div>
              <div className="rounded-lg bg-slate-50 p-2">
                <div className="text-[11px] uppercase text-slate-500">Explore</div>
                <div className="font-semibold text-slate-950">{formatNumber(row.explore_score, 1)}</div>
              </div>
            </div>

            <div className="mt-3 flex items-start gap-2 rounded-lg border border-slate-100 bg-slate-50 p-3 text-sm text-slate-700">
              <EyeOff className="mt-0.5 h-4 w-4 shrink-0 text-blue-700" />
              <span>
                {actionLabel(row.recommended_action)} because this area has low enforcement visibility and enough static
                obstruction potential to justify an audit.
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
