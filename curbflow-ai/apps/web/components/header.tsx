"use client";

import { RefreshCw } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const titles: Record<string, string> = {
  "/": "Command Center",
  "/audit": "Evidence Audit",
  "/hotspots": "Observed Hotspots",
  "/blindspots": "Blindspots",
  "/junction-basins": "Junction Basins",
  "/patrol-twin": "Patrol Digital Twin",
  "/patrol-digital-twin": "Patrol Digital Twin",
  "/planner": "Enforcement Planner",
  "/metrics": "Evidence Audit",
};

const mobileLinks = [
  { href: "/", label: "Map" },
  { href: "/audit", label: "Audit" },
  { href: "/hotspots", label: "Hotspots" },
  { href: "/blindspots", label: "Blindspots" },
  { href: "/patrol-twin", label: "Patrol Twin" },
  { href: "/planner", label: "Planner" },
];

export function Header() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-[#fbfbf9]/95 px-3 py-3 shadow-sm backdrop-blur sm:px-4">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-base font-semibold text-slate-950">{titles[pathname] ?? "CurbFlow AI"}</h1>
            <Badge variant="info" className="hidden sm:inline-flex">
              Bias-aware
            </Badge>
          </div>
          <p className="truncate text-xs text-slate-500">No challan is not treated as no problem.</p>
        </div>
        <Button variant="secondary" onClick={() => window.location.reload()}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh
        </Button>
      </div>
      <nav className="mt-3 flex gap-2 overflow-x-auto pb-1 lg:hidden">
        {mobileLinks.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "shrink-0 rounded-full px-3 py-1.5 text-xs font-medium text-slate-600 ring-1 ring-inset ring-slate-200",
              (pathname === item.href ||
                (item.href === "/patrol-twin" && pathname === "/patrol-digital-twin")) &&
                "bg-slate-950 text-white ring-slate-950",
            )}
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
