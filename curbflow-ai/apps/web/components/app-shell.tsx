"use client";

import { Header } from "@/components/header";
import { Sidebar } from "@/components/sidebar";
import { usePathname } from "next/navigation";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (pathname === "/") {
    return <div className="min-h-screen bg-[#fbfbf9] text-slate-950">{children}</div>;
  }

  return (
    <div className="min-h-screen bg-[#fbfbf9] text-slate-950">
      <div className="flex">
        <Sidebar />
        <div className="min-w-0 flex-1">
          <Header />
          <main data-tour="page-content" className="mx-auto w-full max-w-[1680px] p-3 sm:p-4 lg:p-6">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
