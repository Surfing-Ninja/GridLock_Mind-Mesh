"use client";

import { ArrowRight, Flame, MapPinned } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { RiskRow } from "@/lib/api";
import { cn, formatNumber } from "@/lib/utils";

function actionLabel(value?: string | null) {
  return String(value ?? "beat_patrol")
    .replaceAll("_", " ")
    .replace(/\s+/g, " ")
    .trim();
}

function zoneCellExplainer(zoneId?: string | null) {
  return `Area cell ${zoneId ?? "unknown"} is CurbFlow's internal 300 m grid zone for grouping nearby records on the map.`;
}

function hotspotInterpretation(row: RiskRow) {
  const pfdi = Number(row.predicted_pfdi ?? 0);
  const hotspot = Number(row.hotspot_probability ?? 0) * 100;
  const priority = Number(row.deployment_priority ?? 0);

  if (pfdi >= 75 && hotspot >= 75) {
    return "Plain-language read: this is a proven enforcement hotspot, with repeated observed violations and a high parking-disruption proxy.";
  }
  if (priority >= 50) {
    return "Plain-language read: this area has enough observed evidence to prioritize a patrol check, even if every metric is not at the maximum.";
  }
  return "Plain-language read: this area is worth watching, but it is below the strongest observed-hotspot tier.";
}

function priorityLabel(score?: number | null) {
  const value = Number(score ?? 0);
  if (value >= 75) return { label: "Critical", className: "bg-red-700 text-white" };
  if (value >= 50) return { label: "High", className: "bg-orange-600 text-white" };
  if (value >= 25) return { label: "Elevated", className: "bg-amber-500 text-slate-950" };
  return { label: "Watch", className: "bg-blue-700 text-white" };
}

export function HotspotTable({ rows = [], onSelect }: { rows?: RiskRow[]; onSelect?: (zoneId: string) => void }) {
  if (!rows.length) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
        No observed hotspot rows are available for the selected filters.
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      {rows.map((row, index) => {
        const priority = priorityLabel(row.deployment_priority ?? row.predicted_pfdi);
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
                  <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-bold uppercase", priority.className)}>
                    {priority.label}
                  </span>
                  <Badge variant="danger">Observed hotspot</Badge>
                  <span className="font-mono text-xs text-slate-400">#{index + 1}</span>
                </div>
                <div className="mt-2 flex items-center gap-2 text-base font-semibold text-slate-950">
                  <MapPinned className="h-4 w-4 text-red-600" />
                  {row.police_station ?? "Unknown station"}
                </div>
                <div className="mt-1 font-mono text-xs text-slate-500">{row.zone_id}</div>
                <div className="mt-1 max-w-xl text-xs leading-5 text-slate-500">{zoneCellExplainer(row.zone_id)}</div>
              </div>
              <ArrowRight className="mt-2 h-4 w-4 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-slate-950" />
            </div>

            <div className="mt-4 grid grid-cols-3 gap-2 text-sm">
              <div className="rounded-lg bg-red-50 p-2">
                <div className="text-[11px] uppercase text-red-600">PFDI</div>
                <div className="font-semibold text-red-950">{formatNumber(row.predicted_pfdi, 1)}</div>
              </div>
              <div className="rounded-lg bg-orange-50 p-2">
                <div className="text-[11px] uppercase text-orange-600">Hotspot</div>
                <div className="font-semibold text-orange-950">
                  {formatNumber((row.hotspot_probability ?? 0) * 100, 1)}%
                </div>
              </div>
              <div className="rounded-lg bg-slate-50 p-2">
                <div className="text-[11px] uppercase text-slate-500">Priority</div>
                <div className="font-semibold text-slate-950">{formatNumber(row.deployment_priority, 1)}</div>
              </div>
            </div>

            <div className="mt-3 rounded-lg border border-red-100 bg-red-50/50 p-3 text-sm leading-6 text-slate-700">
              {hotspotInterpretation(row)}
            </div>

            <div className="mt-3 flex items-start gap-2 rounded-lg border border-slate-100 bg-slate-50 p-3 text-sm text-slate-700">
              <Flame className="mt-0.5 h-4 w-4 shrink-0 text-orange-600" />
              <span>
                {actionLabel(row.recommended_action)} because this zone has strong observed enforcement evidence and high
                parking disruption proxy.
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
