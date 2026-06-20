"use client";

import { usePathname } from "next/navigation";

import { Header } from "@/components/header";
import { Sidebar } from "@/components/sidebar";

// These routes get a full-bleed flex-1 main (map fills height)
const MAP_PAGES = [
  "/hotspots",
  "/blindspots",
  "/junction-basins",
  "/patrol-twin",
  "/patrol-digital-twin",
  "/planner",
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  // Home page is a standalone full-screen command console — no shell at all
  if (pathname === "/") {
    return <div className="h-screen overflow-hidden">{children}</div>;
  }

  const isMapPage = MAP_PAGES.includes(pathname);

  return (
    <div className="flex h-screen overflow-hidden bg-[#fbfbf9] text-[#1c1c1e]">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Header />
        {isMapPage ? (
          <main className="flex min-h-0 flex-1 overflow-hidden">{children}</main>
        ) : (
          <main className="overflow-y-auto">
            <div className="mx-auto w-full max-w-[1680px] p-3 sm:p-4 lg:p-6">{children}</div>
          </main>
        )}
      </div>
    </div>
  );
}
