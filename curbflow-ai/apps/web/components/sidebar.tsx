"use client";

import {
  Activity,
  BarChart3,
  EyeOff,
  Gauge,
  GitBranch,
  LayoutDashboard,
  MapPinned,
  Route,
  Siren,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const items = [
  { href: "/", label: "Hotspot Map", icon: LayoutDashboard },
  { href: "/audit", label: "Audit", icon: Activity },
  { href: "/hotspots", label: "Hotspots", icon: Siren },
  { href: "/blindspots", label: "Evening Blindspots", icon: EyeOff },
  { href: "/junction-basins", label: "Junction Basins", icon: GitBranch },
  { href: "/patrol-twin", label: "Patrol Twin", icon: Route },
  { href: "/planner", label: "Planner", icon: MapPinned },
  { href: "/metrics", label: "Metrics", icon: BarChart3 },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden min-h-screen w-64 border-r border-slate-200 bg-[#fbfbf9] px-3 py-4 text-slate-950 lg:block">
      <div className="mb-6 flex items-center gap-2 px-2">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-950 text-white">
          <Gauge className="h-5 w-5" />
        </div>
        <div>
          <div className="text-sm font-semibold">CurbFlow AI</div>
          <div className="text-xs text-slate-500">Enforcement intelligence</div>
        </div>
      </div>
      <nav className="space-y-1">
        {items.map((item) => {
          const Icon = item.icon;
          const active =
            pathname === item.href ||
            (item.href === "/patrol-twin" && pathname === "/patrol-digital-twin");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2 rounded-md px-2 py-2 text-sm text-slate-600 hover:bg-white hover:text-slate-950 hover:shadow-sm",
                active && "bg-slate-950 text-white shadow-sm hover:bg-slate-950 hover:text-white",
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
