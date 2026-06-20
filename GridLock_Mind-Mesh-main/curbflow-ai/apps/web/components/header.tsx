"use client";

import { RefreshCw } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const TITLES: Record<string, string> = {
  "/":                    "Live Enforcement Map",
  "/audit":               "Bias Audit",
  "/hotspots":            "Observed Hotspots",
  "/blindspots":          "Evening Blindspots",
  "/junction-basins":     "Junction Basins",
  "/patrol-twin":         "Patrol Digital Twin",
  "/patrol-digital-twin": "Patrol Digital Twin",
  "/planner":             "Enforcement Planner",
  "/metrics":             "Model Metrics",
};

const MOBILE_LINKS = [
  { href: "/",            label: "Map" },
  { href: "/audit",       label: "Audit" },
  { href: "/hotspots",    label: "Hotspots" },
  { href: "/blindspots",  label: "Blindspots" },
  { href: "/patrol-twin", label: "Patrol" },
  { href: "/planner",     label: "Planner" },
  { href: "/metrics",     label: "Metrics" },
];

export function Header() {
  const pathname = usePathname();
  const title = TITLES[pathname] ?? "CurbFlow AI";

  return (
    <header className="shrink-0 border-b border-[#e8e8e4] bg-white px-4 py-2.5 shadow-none">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex items-center gap-2">
          <h1 className="truncate text-[13px] font-semibold text-[#1c1c1e]">{title}</h1>
          <span className="hidden rounded-full bg-[#f0f0ec] px-2 py-0.5 text-[10px] font-semibold text-[#6b6b6b] sm:inline">
            Bias-aware
          </span>
        </div>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="flex items-center gap-1.5 rounded-lg border border-[#e8e8e4] bg-white px-2.5 py-1.5 text-xs font-medium text-[#6b6b6b] transition-colors hover:bg-[#f0f0ec] hover:text-[#1c1c1e]"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </button>
      </div>

      {/* Mobile nav */}
      <nav className="mt-2 flex gap-1.5 overflow-x-auto pb-0.5 lg:hidden">
        {MOBILE_LINKS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "shrink-0 rounded-full px-3 py-1 text-[11px] font-medium transition-colors",
              (pathname === item.href || (item.href === "/patrol-twin" && pathname === "/patrol-digital-twin"))
                ? "bg-[#1c1c1e] text-white"
                : "bg-[#f0f0ec] text-[#6b6b6b] hover:text-[#1c1c1e]",
            )}
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
