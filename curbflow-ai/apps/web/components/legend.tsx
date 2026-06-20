type LegendProps = {
  variant?: "risk" | "blindspot" | "patrol" | "planner" | "coverageGap";
};

export function Legend({ variant = "risk" }: LegendProps) {
  const items = {
    patrol: [
      { label: "Patrol-connected", className: "bg-blue-600" },
      { label: "Partial route signal", className: "bg-sky-500" },
      { label: "Near-patrol uncovered", className: "bg-red-600" },
      { label: "No route signal", className: "bg-slate-400" },
    ],
    planner: [
      { label: "Beat patrol", className: "bg-blue-600" },
      { label: "Towing support", className: "bg-red-700" },
      { label: "Evening audit", className: "bg-amber-600" },
      { label: "Patrol expansion", className: "bg-teal-600" },
    ],
    blindspot: [
      { label: "Low audit risk", className: "bg-slate-400" },
      { label: "Coverage gap", className: "bg-blue-600" },
      { label: "High blindspot", className: "bg-orange-600" },
      { label: "Critical audit", className: "bg-red-700" },
    ],
    coverageGap: [
      { label: "Low gap", className: "bg-blue-600" },
      { label: "Medium gap", className: "bg-amber-600" },
      { label: "High gap", className: "bg-orange-600" },
      { label: "Severe gap", className: "bg-red-700" },
    ],
    risk: [
      { label: "Low", className: "bg-blue-600" },
      { label: "Elevated", className: "bg-yellow-600" },
      { label: "High", className: "bg-orange-600" },
      { label: "Severe", className: "bg-red-700" },
    ],
  }[variant];
  const title = {
    blindspot: "Blindspot audit",
    coverageGap: "Coverage gaps",
    patrol: "Patrol coverage",
    planner: "Planner actions",
    risk: "Risk priority",
  }[variant];
  return (
    <div className="absolute bottom-3 left-3 rounded-md border border-slate-200 bg-white/95 p-3 text-xs shadow-lg backdrop-blur">
      <div className="mb-2 font-medium text-slate-700">{title}</div>
      <div className="space-y-1">
        {items.map((item) => (
          <div key={item.label} className="flex items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-sm ${item.className}`} />
            <span className="text-slate-600">{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
