import { Card, CardContent } from "@/components/ui/card";
import { cn, formatNumber } from "@/lib/utils";

type StatCardProps = {
  label: string;
  value?: number | string | null;
  detail?: string;
  tone?: "neutral" | "hotspot" | "blindspot" | "visibility" | "success";
};

const toneClass = {
  neutral: "bg-slate-500",
  hotspot: "bg-orange-600",
  blindspot: "bg-purple-600",
  visibility: "bg-blue-600",
  success: "bg-emerald-600",
};

export function StatCard({ label, value, detail, tone = "neutral" }: StatCardProps) {
  const display = typeof value === "number" ? formatNumber(value, value % 1 === 0 ? 0 : 2) : value ?? "—";
  const valueClass = typeof value === "number" ? "text-2xl" : "text-base leading-snug";
  return (
    <Card className="overflow-hidden">
      <div className={cn("h-1", toneClass[tone])} />
      <CardContent className="space-y-1">
        <div className="text-xs font-medium uppercase text-slate-500">{label}</div>
        <div className={`${valueClass} break-words font-semibold text-slate-950`}>{display}</div>
        {detail ? <div className="text-xs text-slate-500">{detail}</div> : null}
      </CardContent>
    </Card>
  );
}
