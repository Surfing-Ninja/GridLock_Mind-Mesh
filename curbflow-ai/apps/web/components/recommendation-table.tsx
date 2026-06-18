"use client";

import { FeedbackForm } from "@/components/feedback-form";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { PlannerRecommendation } from "@/lib/api";
import { formatNumber } from "@/lib/utils";

function riskScore(row: PlannerRecommendation) {
  return Number(row.expected_relief ?? row.exploit_score ?? row.predicted_pfdi ?? 0);
}

function reason(row: PlannerRecommendation) {
  if (row.explanation) return row.explanation;
  if (!row.explanation_json) return "-";
  try {
    const parsed = JSON.parse(row.explanation_json);
    if (Array.isArray(parsed?.reasons)) return parsed.reasons.join("; ");
    if (Array.isArray(parsed?.rule_reasons)) return parsed.rule_reasons.join("; ");
  } catch {
    return row.explanation_json;
  }
  return row.explanation_json;
}

export function RecommendationTable({ rows = [] }: { rows?: PlannerRecommendation[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
      <Table className="min-w-[980px]">
        <TableHeader>
          <TableRow>
            <TableHead>Rank</TableHead>
            <TableHead>Zone</TableHead>
            <TableHead>Risk score</TableHead>
            <TableHead>Blindspot score</TableHead>
            <TableHead>Action</TableHead>
            <TableHead>Officers</TableHead>
            <TableHead>Tow</TableHead>
            <TableHead>Reason</TableHead>
            <TableHead>Feedback</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, index) => (
            <TableRow key={`${row.zone_id}-${row.action}-${index}`}>
              <TableCell>{row.recommendation_rank ?? index + 1}</TableCell>
              <TableCell className="font-medium text-slate-950">{row.zone_id}</TableCell>
              <TableCell>{formatNumber(riskScore(row), 1)}</TableCell>
              <TableCell>{formatNumber(row.blindspot_risk_score, 1)}</TableCell>
              <TableCell>{row.action}</TableCell>
              <TableCell>
                <Badge variant="success">{row.officers_required ?? 0}</Badge>
              </TableCell>
              <TableCell>
                <Badge variant={(row.tow_units_required ?? 0) > 0 ? "warning" : "success"}>{row.tow_units_required ?? 0}</Badge>
              </TableCell>
              <TableCell className="max-w-md">{reason(row)}</TableCell>
              <TableCell>
                <FeedbackForm recommendation={row} />
              </TableCell>
            </TableRow>
          ))}
          {!rows.length ? (
            <TableRow>
              <TableCell colSpan={9} className="py-6 text-center text-slate-500">
                Run the planner to generate resource-constrained recommendations.
              </TableCell>
            </TableRow>
          ) : null}
        </TableBody>
      </Table>
    </div>
  );
}
