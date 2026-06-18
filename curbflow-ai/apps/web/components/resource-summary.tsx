import { StatCard } from "@/components/stat-card";
import type { PlannerRecommendation } from "@/lib/api";

export function ResourceSummary({ rows = [] }: { rows?: PlannerRecommendation[] }) {
  const officers = rows.reduce((sum, row) => sum + Number(row.officers_required ?? 0), 0);
  const tow = rows.reduce((sum, row) => sum + Number(row.tow_units_required ?? 0), 0);
  const blindspots = rows.filter((row) => row.action_category === "blindspot").length;
  const known = rows.filter((row) => row.action_category !== "blindspot").length;
  const expectedCoverage = rows.reduce((sum, row) => sum + Number(row.expected_relief ?? 0), 0);
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
      <StatCard label="Officers used" value={officers} tone="success" />
      <StatCard label="Tow units used" value={tow} tone="success" />
      <StatCard label="Known hotspot allocations" value={known} tone="hotspot" />
      <StatCard label="Blindspot audit allocations" value={blindspots} tone="blindspot" />
      <StatCard label="Expected risk coverage" value={expectedCoverage} tone="visibility" />
    </div>
  );
}
