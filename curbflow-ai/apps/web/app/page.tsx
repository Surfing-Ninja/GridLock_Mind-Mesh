"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, EyeOff, MapPinned, Radar, ShieldCheck, Siren } from "lucide-react";
import Link from "next/link";

import { CurbFlowMap } from "@/components/curbflow-map";
import { StatCard } from "@/components/stat-card";
import { ZoneDetailsDrawer } from "@/components/zone-details-drawer";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getAuditSummary, getBlindspots, getHotspots, getZoneDetails, getZonesGeoJson } from "@/lib/api";
import { formatNumber } from "@/lib/utils";
import { useCurbFlowStore } from "@/lib/store";

const buttonLinkClass =
  "inline-flex h-9 items-center justify-center rounded-md px-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400";

function FeatureCard({
  title,
  text,
  href,
  icon: Icon,
  badge,
  tone,
}: {
  title: string;
  text: string;
  href: string;
  icon: typeof Siren;
  badge: string;
  tone: "danger" | "purple" | "success";
}) {
  const toneClass = {
    danger: "bg-red-50 text-red-700 ring-red-200",
    purple: "bg-purple-50 text-purple-700 ring-purple-200",
    success: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  }[tone];

  return (
    <Card className="overflow-hidden">
      <CardHeader className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className={`flex h-10 w-10 items-center justify-center rounded-lg ring-1 ring-inset ${toneClass}`}>
            <Icon className="h-5 w-5" />
          </div>
          <Badge variant={tone}>{badge}</Badge>
        </div>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm leading-6 text-slate-600">{text}</p>
        <Link
          href={href}
          className={`${buttonLinkClass} w-full justify-between bg-white text-slate-950 shadow-sm ring-1 ring-inset ring-slate-200 hover:bg-slate-50`}
        >
          Open
          <ArrowRight className="h-4 w-4" />
        </Link>
      </CardContent>
    </Card>
  );
}

function TopRows({
  title,
  rows,
  variant,
  onSelect,
}: {
  title: string;
  rows: Array<{ zone_id: string; police_station?: string | null; predicted_pfdi?: number | null; blindspot_risk_score?: number | null; window_start?: string | null }>;
  variant: "hotspot" | "blindspot";
  onSelect: (zoneId: string) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {rows.slice(0, 6).map((row) => (
          <button
            key={`${row.zone_id}-${row.window_start}-${variant}`}
            className="flex w-full items-center justify-between gap-3 rounded-md border border-slate-200 px-3 py-2 text-left text-sm hover:bg-slate-50"
            onClick={() => onSelect(row.zone_id)}
          >
            <div className="min-w-0">
              <div className="font-medium text-slate-950">{row.zone_id}</div>
              <div className="truncate text-xs text-slate-500">{row.police_station ?? "Unknown station"}</div>
            </div>
            <Badge variant={variant === "hotspot" ? "danger" : "purple"}>
              {variant === "hotspot"
                ? formatNumber(row.predicted_pfdi, 0)
                : formatNumber(row.blindspot_risk_score, 0)}
            </Badge>
          </button>
        ))}
      </CardContent>
    </Card>
  );
}

export default function Page() {
  const selectedZoneId = useCurbFlowStore((state) => state.selectedZoneId);
  const setSelectedZoneId = useCurbFlowStore((state) => state.setSelectedZoneId);
  const mode = useCurbFlowStore((state) => state.plannerMode);
  const audit = useQuery({ queryKey: ["audit-summary"], queryFn: getAuditSummary });
  const zones = useQuery({ queryKey: ["zones", mode], queryFn: () => getZonesGeoJson({ mode }) });
  const hotspots = useQuery({ queryKey: ["hotspots", mode], queryFn: () => getHotspots({ top_k: 8, mode }) });
  const blindspots = useQuery({ queryKey: ["landing-blindspots"], queryFn: () => getBlindspots({ top_k: 8 }) });
  const zoneDetails = useQuery({
    queryKey: ["zone-details", selectedZoneId],
    queryFn: () => getZoneDetails(selectedZoneId ?? ""),
    enabled: Boolean(selectedZoneId),
  });

  return (
    <div className="space-y-5">
      <section className="overflow-hidden rounded-xl bg-slate-950 text-white shadow-lg">
        <div className="grid gap-6 p-5 lg:grid-cols-[minmax(0,1fr)_360px] lg:p-7">
          <div className="space-y-5">
            <div className="flex flex-wrap gap-2">
              <Badge variant="info">Theme 1</Badge>
              <Badge variant="secondary" className="bg-white/10 text-white ring-white/20">
                Parking-induced congestion
              </Badge>
            </div>
            <div className="max-w-4xl space-y-3">
              <h1 className="text-3xl font-semibold tracking-normal sm:text-4xl">
                CurbFlow AI: Bias-Aware Parking Enforcement Intelligence
              </h1>
              <p className="text-lg text-slate-200">CurbFlow does not confuse no challan with no problem.</p>
            </div>
            <div className="rounded-lg border border-orange-400/30 bg-orange-500/10 p-4">
              <div className="flex gap-3">
                <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-orange-300" />
                <p className="text-sm leading-6 text-orange-50">
                  Data audit revealed a strong morning-heavy enforcement pattern and sparse evening visibility. CurbFlow
                  explicitly models this bias instead of treating evening zeros as safe.
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link href="/hotspots" className={`${buttonLinkClass} bg-red-600 text-white shadow-sm hover:bg-red-700`}>
                Observed hotspots
              </Link>
              <Link
                href="/blindspots"
                className={`${buttonLinkClass} bg-white text-slate-950 shadow-sm ring-1 ring-inset ring-white/70 hover:bg-slate-50`}
              >
                Blind spots
              </Link>
              <Link href="/planner" className={`${buttonLinkClass} bg-emerald-600 text-white shadow-sm hover:bg-emerald-700`}>
                Planner
              </Link>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
            <StatCard label="Records" value={audit.data?.row_count} detail="Theme 1 CSV" tone="visibility" />
            <StatCard label="Morning count" value={audit.data?.morning_count} detail="07:30-15:30 IST" tone="hotspot" />
            <StatCard label="Evening count" value={audit.data?.evening_count} detail="15:30-20:30 IST" tone="blindspot" />
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <FeatureCard
          title="Observed Hotspots"
          text="Rank zones with strong observed disruption signals and high-confidence enforcement records."
          href="/hotspots"
          icon={Siren}
          badge="Observed"
          tone="danger"
        />
        <FeatureCard
          title="Blind Spots"
          text="Surface high-potential, low-visibility zones where zero challans should trigger audit priority."
          href="/blindspots"
          icon={EyeOff}
          badge="Audit"
          tone="purple"
        />
        <FeatureCard
          title="Enforcement Planner"
          text="Allocate officers and tow units with conservative, balanced, and discovery operating modes."
          href="/planner"
          icon={MapPinned}
          badge="Feasible"
          tone="success"
        />
      </section>

      <Tabs defaultValue="map">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <TabsList>
            <TabsTrigger value="map">Risk Map</TabsTrigger>
            <TabsTrigger value="hotspots">Hotspots</TabsTrigger>
            <TabsTrigger value="blindspots">Blindspots</TabsTrigger>
          </TabsList>
          <Badge variant="info">Live DuckDB-backed API</Badge>
        </div>
        <TabsContent value="map">
          <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
            <CurbFlowMap zones={zones.data} mode={mode} onZoneClick={setSelectedZoneId} />
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Radar className="h-4 w-4 text-blue-600" />
                  Operating Picture
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="flex items-start gap-3 rounded-md bg-red-50 p-3 text-red-900">
                  <Siren className="mt-0.5 h-4 w-4" />
                  <div>
                    <div className="font-medium">Observed hotspot layer</div>
                    <p className="text-red-800">Red/orange zones indicate high observed PFDI and exploit priority.</p>
                  </div>
                </div>
                <div className="flex items-start gap-3 rounded-md bg-purple-50 p-3 text-purple-900">
                  <EyeOff className="mt-0.5 h-4 w-4" />
                  <div>
                    <div className="font-medium">Blindspot layer</div>
                    <p className="text-purple-800">Purple zones indicate high audit priority under sparse visibility.</p>
                  </div>
                </div>
                <div className="flex items-start gap-3 rounded-md bg-emerald-50 p-3 text-emerald-900">
                  <ShieldCheck className="mt-0.5 h-4 w-4" />
                  <div>
                    <div className="font-medium">Planner feasibility</div>
                    <p className="text-emerald-800">Green resource summaries show allocations that fit officer and tow limits.</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </section>
        </TabsContent>
        <TabsContent value="hotspots">
          <TopRows title="Observed Hotspot Candidates" rows={hotspots.data ?? []} variant="hotspot" onSelect={setSelectedZoneId} />
        </TabsContent>
        <TabsContent value="blindspots">
          <TopRows title="Blindspot Audit Candidates" rows={blindspots.data ?? []} variant="blindspot" onSelect={setSelectedZoneId} />
        </TabsContent>
      </Tabs>

      <ZoneDetailsDrawer zone={zoneDetails.data} onClose={() => setSelectedZoneId(undefined)} />
    </div>
  );
}
