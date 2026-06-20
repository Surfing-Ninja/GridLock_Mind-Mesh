"use client";

import { X } from "lucide-react";
import { useState } from "react";

export type AlertSeverity = "critical" | "high" | "warning";

const STYLES: Record<AlertSeverity, { bar: string; dot: string; text: string; btn: string }> = {
  critical: {
    bar: "bg-red-600",
    dot: "bg-white",
    text: "text-white",
    btn: "hover:bg-red-700 text-white/80 hover:text-white",
  },
  high: {
    bar: "bg-amber-500",
    dot: "bg-white",
    text: "text-white",
    btn: "hover:bg-amber-600 text-white/80 hover:text-white",
  },
  warning: {
    bar: "bg-amber-50 border-b border-amber-200",
    dot: "bg-amber-500",
    text: "text-amber-900",
    btn: "hover:bg-amber-100 text-amber-700",
  },
};

export function AlertBanner({
  message,
  severity = "critical",
}: {
  message: string;
  severity?: AlertSeverity;
}) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed || !message) return null;

  const s = STYLES[severity];
  return (
    <div className={`flex shrink-0 items-center gap-2.5 px-3 py-2 ${s.bar}`}>
      <span className={`h-2 w-2 shrink-0 rounded-full ${s.dot} animate-pulse-dot`} />
      <span className={`min-w-0 flex-1 truncate text-[11px] font-semibold tracking-wide uppercase ${s.text}`}>
        {message}
      </span>
      <button
        onClick={() => setDismissed(true)}
        className={`shrink-0 rounded p-0.5 transition-colors ${s.btn}`}
        aria-label="Dismiss"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}
