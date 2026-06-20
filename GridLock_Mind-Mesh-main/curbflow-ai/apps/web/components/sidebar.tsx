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
  { href: "/",                   label: "Live Map",       icon: LayoutDashboard },
  { href: "/audit",              label: "Bias Audit",     icon: Activity },
  { href: "/hotspots",           label: "Hotspots",       icon: Siren },
  { href: "/blindspots",         label: "Blindspots",     icon: EyeOff },
  { href: "/junction-basins",    label: "Junctions",      icon: GitBranch },
  { href: "/patrol-twin",        label: "Patrol Twin",    icon: Route },
  { href: "/planner",            label: "Planner",        icon: MapPinned },
  { href: "/metrics",            label: "Metrics",        icon: BarChart3 },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden min-h-screen w-[200px] shrink-0 flex-col border-r border-[#e8e8e4] bg-white px-2 py-4 lg:flex">
      {/* Logo */}
      <div className="mb-5 flex items-center gap-2.5 px-2">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#1c1c1e]">
          <Gauge className="h-4 w-4 text-white" />
        </div>
        <div>
          <div className="text-[13px] font-semibold text-[#1c1c1e]">CurbFlow AI</div>
          <div className="text-[10px] text-[#9b9b9b]">Enforcement intel</div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-0.5">
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
                "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] font-medium transition-colors",
                active
                  ? "bg-[#1c1c1e] text-white"
                  : "text-[#6b6b6b] hover:bg-[#f0f0ec] hover:text-[#1c1c1e]",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="mt-4 border-t border-[#e8e8e4] pt-3 px-2">
        <div className="text-[10px] text-[#9b9b9b] leading-relaxed">
          Bias-aware · Theme 1<br />
          Nov 2023 – Apr 2024
        </div>
      </div>
    </aside>
  );
}
