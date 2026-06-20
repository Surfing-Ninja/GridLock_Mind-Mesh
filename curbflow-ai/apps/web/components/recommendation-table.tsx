"use client";

import { FeedbackForm } from "@/components/feedback-form";
import { Badge } from "@/components/ui/badge";
import type { PlannerRecommendation } from "@/lib/api";
import { formatNumber } from "@/lib/utils";

function riskScore(row: PlannerRecommendation) {
  return Number(row.expected_relief ?? row.exploit_score ?? row.predicted_pfdi ?? 0);
}

function blindspotScore(row: PlannerRecommendation) {
  return Number(row.blindspot_risk_score ?? row.explore_score ?? 0);
}

function label(value?: string | null) {
  return String(value ?? "-").replaceAll("_", " ");
}

function reason(row: PlannerRecommendation) {
  if (row.explanation) return row.explanation;
  if (!row.explanation_json) return "-";
  try {
    const parsed = JSON.parse(row.explanation_json);
    if (Array.isArray(parsed?.reasons)) return parsed.reasons.join("; ");
    if (Array.isArray(parsed?.rule_reasons)) return parsed.rule_reasons.join("; ");
  } catch {
    return "Planner generated an explanation for this action.";
  }
  return "Recommended because this zone ranks highly for the selected deployment mode.";
}

export function RecommendationTable({ rows = [] }: { rows?: PlannerRecommendation[] }) {
  return (
    <div className="grid gap-3">
      {rows.map((row, index) => {
        const exploit = row.action_category !== "blindspot";
        return (
          <div
            key={`${row.zone_id}-${row.action}-${index}`}
            className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-slate-300 hover:shadow-md"
          >
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={exploit ? "danger" : "warning"}>#{row.recommendation_rank ?? index + 1}</Badge>
                  <Badge variant={exploit ? "danger" : "info"}>{exploit ? "Exploit known hotspot" : "Explore blindspot"}</Badge>
                  <span className="font-mono text-xs text-slate-400">{row.zone_id}</span>
                </div>
                <h3 className="mt-2 text-lg font-semibold capitalize text-slate-950">{label(row.action)}</h3>
                <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">{reason(row)}</p>
              </div>
              <div className="grid min-w-[260px] grid-cols-2 gap-2 text-sm">
                <div className="rounded-lg bg-red-50 p-3">
                  <div className="text-xs text-red-600">Risk</div>
                  <div className="font-semibold text-red-950">{formatNumber(riskScore(row), 1)}</div>
                </div>
                <div className="rounded-lg bg-blue-50 p-3">
                  <div className="text-xs text-blue-600">Blindspot</div>
                  <div className="font-semibold text-blue-950">{formatNumber(blindspotScore(row), 1)}</div>
                </div>
                <div className="rounded-lg bg-emerald-50 p-3">
                  <div className="text-xs text-emerald-700">Officers</div>
                  <div className="font-semibold text-emerald-950">{row.officers_required ?? 0}</div>
                </div>
                <div className="rounded-lg bg-amber-50 p-3">
                  <div className="text-xs text-amber-700">Tow units</div>
                  <div className="font-semibold text-amber-950">{row.tow_units_required ?? 0}</div>
                </div>
              </div>
            </div>
            <div className="mt-3 border-t border-slate-100 pt-3">
              <FeedbackForm recommendation={row} />
            </div>
          </div>
        );
      })}
      {!rows.length ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
          Run the planner to generate resource-constrained recommendations.
        </div>
      ) : null}
    </div>
  );
}
