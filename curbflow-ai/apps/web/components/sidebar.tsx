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
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/audit", label: "Audit", icon: Activity },
  { href: "/hotspots", label: "Hotspots", icon: Siren },
  { href: "/blindspots", label: "Blindspots", icon: EyeOff },
  { href: "/junction-basins", label: "Junction Basins", icon: GitBranch },
  { href: "/patrol-digital-twin", label: "Patrol Twin", icon: Route },
  { href: "/planner", label: "Planner", icon: MapPinned },
  { href: "/metrics", label: "Metrics", icon: BarChart3 },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden min-h-screen w-64 border-r border-slate-800 bg-slate-950 px-3 py-4 text-white lg:block">
      <div className="mb-6 flex items-center gap-2 px-2">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white text-slate-950">
          <Gauge className="h-5 w-5" />
        </div>
        <div>
          <div className="text-sm font-semibold">CurbFlow AI</div>
          <div className="text-xs text-slate-400">Enforcement intelligence</div>
        </div>
      </div>
      <nav className="space-y-1">
        {items.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2 rounded-md px-2 py-2 text-sm text-slate-300 hover:bg-white/10 hover:text-white",
                active && "bg-white text-slate-950 hover:bg-white hover:text-slate-950",
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
