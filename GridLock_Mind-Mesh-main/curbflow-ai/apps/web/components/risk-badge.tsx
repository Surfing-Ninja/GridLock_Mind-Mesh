import { cn } from "@/lib/utils";

export type RiskLevel = "critical" | "high" | "elevated" | "clear" | "blindspot" | "unknown";

const LEVEL_CONFIG: Record<RiskLevel, { label: string; className: string }> = {
  critical: { label: "CRITICAL", className: "bg-red-600 text-white" },
  high:     { label: "HIGH",     className: "bg-amber-500 text-white" },
  elevated: { label: "ELEVATED", className: "bg-yellow-400 text-yellow-900" },
  clear:    { label: "CLEAR",    className: "bg-green-100 text-green-800 ring-1 ring-inset ring-green-300" },
  blindspot:{ label: "BLINDSPOT",className: "bg-violet-600 text-white" },
  unknown:  { label: "—",        className: "bg-[#f0f0ec] text-[#9b9b9b]" },
};

export function scoreToRiskLevel(
  score: number | null | undefined,
  type: "hotspot" | "blindspot" = "hotspot",
): RiskLevel {
  if (score === null || score === undefined) return "unknown";
  if (type === "blindspot") {
    if (score >= 40) return "blindspot";
    if (score >= 20) return "blindspot";
    return "unknown";
  }
  if (score >= 75) return "critical";
  if (score >= 50) return "high";
  if (score >= 25) return "elevated";
  return "clear";
}

export function RiskBadge({
  level,
  className,
}: {
  level: RiskLevel;
  className?: string;
}) {
  const config = LEVEL_CONFIG[level];
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[9px] font-black tracking-widest uppercase",
        config.className,
        className,
      )}
    >
      {config.label}
    </span>
  );
}
