import { StatCard } from "@/components/stat-card";
import type { AuditSummary } from "@/lib/api";

export function BiasAuditCards({ summary }: { summary?: AuditSummary }) {
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      <StatCard label="Rows" value={summary?.row_count} detail="Theme 1 police violation CSV" />
      <StatCard label="Morning records" value={summary?.morning_count} detail="07:30-15:30 IST" />
      <StatCard label="Evening records" value={summary?.evening_count} detail="15:30-20:30 IST" />
      <StatCard label="Evening gap ratio" value={summary?.evening_gap_ratio ?? null} detail="Morning over evening" />
    </div>
  );
}
