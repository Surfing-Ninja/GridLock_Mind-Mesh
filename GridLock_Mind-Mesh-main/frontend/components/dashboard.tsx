"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, BarChart3, Binoculars, Gauge, MapPinned, Network, Route, ShieldCheck } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { apiGet, apiPost } from "@/lib/api";
import type { AuditSummary, HourlyAudit, PlannerResponse, ZonePoint } from "@/lib/types";
import { Badge, Button, Card, Metric, cn } from "@/components/ui";

const MapPanel = dynamic(() => import("@/components/map-panel").then((m) => m.MapPanel), { ssr: false });

const nav = [
  { href: "/", label: "Overview", icon: Gauge },
  { href: "/audit", label: "Audit", icon: ShieldCheck },
  { href: "/hotspots", label: "Hotspots", icon: MapPinned },
  { href: "/blindspots", label: "Blindspots", icon: Binoculars },
  { href: "/junction-basins", label: "Junction Basins", icon: Network },
  { href: "/patrol-digital-twin", label: "Patrol Twin", icon: Route },
  { href: "/planner", label: "Planner", icon: Activity },
  { href: "/metrics", label: "Metrics", icon: BarChart3 }
];

const HourlyChart = dynamic(() => Promise.resolve(HourlyChartInner), { ssr: false });

type PageKind = "overview" | "audit" | "hotspots" | "blindspots" | "junctions" | "patrol" | "planner" | "metrics";

export function Dashboard({ page }: { page: PageKind }) {
  const audit = useQuery({ queryKey: ["audit"], queryFn: () => apiGet<AuditSummary>("/audit/summary") });
  const hourly = useQuery({ queryKey: ["hourly"], queryFn: () => apiGet<HourlyAudit[]>("/audit/hourly") });
  const hotspots = useQuery({ queryKey: ["hotspots"], queryFn: () => apiGet<ZonePoint[]>("/hotspots?limit=40") });
  const blindspots = useQuery({ queryKey: ["blindspots"], queryFn: () => apiGet<ZonePoint[]>("/blindspots?limit=40") });
  const patrol = useQuery({ queryKey: ["patrol"], queryFn: () => apiGet<{ stations: Record<string, number | string>[]; coverage: Record<string, number | string>[] }>("/patrol/summary") });
  const junctions = useQuery({ queryKey: ["junctions"], queryFn: () => apiGet<Record<string, number | string>[]>("/junction-basins?limit=40") });
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: () => apiGet<Record<string, unknown>>("/metrics/model") });

  const title = {
    overview: "CurbFlow AI",
    audit: "Data & Bias Audit",
    hotspots: "Observed Illegal-Parking Hotspots",
    blindspots: "Enforcement Visibility Gaps",
    junctions: "Hidden Junction Basins",
    patrol: "Patrol Digital Twin",
    planner: "Station Enforcement Planner",
    metrics: "Model Metrics"
  }[page];

  return (
    <main className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-border bg-panel p-4 lg:block">
        <div className="mb-6">
          <div className="text-lg font-semibold">CurbFlow AI</div>
          <div className="text-sm text-slate-500">Bias-aware enforcement intelligence</div>
        </div>
        <nav className="space-y-1">
          {nav.map((item) => (
            <Link key={item.href} href={item.href} className="flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-muted">
              <item.icon size={16} />
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
      <section className="lg:pl-64">
        <header className="border-b border-border bg-panel px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold">{title}</h1>
              <p className="text-sm text-slate-600">
                CurbFlow does not confuse no challan with no problem. It separates risk from enforcement visibility bias.
              </p>
            </div>
            <Badge className="bg-amber-100 text-amber-900">Theme 1 CSV only</Badge>
          </div>
        </header>
        <div className="p-5">
          {page === "overview" && <Overview audit={audit.data} hotspots={hotspots.data} blindspots={blindspots.data} />}
          {page === "audit" && <AuditPage audit={audit.data} hourly={hourly.data} stations={patrol.data?.stations ?? []} />}
          {page === "hotspots" && <RiskPage mode="hotspot" points={hotspots.data ?? []} />}
          {page === "blindspots" && <RiskPage mode="blindspot" points={blindspots.data ?? []} />}
          {page === "junctions" && <JunctionPage rows={junctions.data ?? []} />}
          {page === "patrol" && <PatrolPage rows={patrol.data?.stations ?? []} coverage={patrol.data?.coverage ?? []} />}
          {page === "planner" && <PlannerPage />}
          {page === "metrics" && <MetricsPage metrics={metrics.data} />}
        </div>
      </section>
    </main>
  );
}

function Overview({ audit, hotspots, blindspots }: { audit?: AuditSummary; hotspots?: ZonePoint[]; blindspots?: ZonePoint[] }) {
  return (
    <div className="space-y-5">
      <div className="grid gap-4 md:grid-cols-4">
        <Metric label="Records" value={formatNumber(audit?.total_records)} />
        <Metric label="Evening Gap" value={formatPercent(audit?.evening_gap_ratio)} tone="blind" />
        <Metric label="Top PFDI" value={formatScore(hotspots?.[0]?.observed_pfdi)} tone="risk" />
        <Metric label="Top Blindspot" value={formatScore(blindspots?.[0]?.blindspot_risk)} tone="blind" />
      </div>
      <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <Card>
          <div className="mb-3 flex items-center gap-2 font-medium"><AlertTriangle size={18} /> Enforcement visibility warning</div>
          <p className="text-sm leading-6 text-slate-700">{audit?.warning ?? "Run the pipeline and API to load audit warnings."}</p>
          <p className="mt-3 text-sm text-slate-600">Actual date range: {audit?.actual_date_range?.start_ist ?? "-"} to {audit?.actual_date_range?.end_ist ?? "-"}</p>
        </Card>
        <Card>
          <div className="mb-2 font-medium">Product intelligence layers</div>
          <div className="grid gap-2 text-sm text-slate-700">
            <span>PFDI observed disruption proxy</span>
            <span>Visibility digital twin and patrol myopia</span>
            <span>Blindspot audit priority with evening uncertainty</span>
            <span>BE-STHGT + LightGBM rank ensemble</span>
          </div>
        </Card>
      </div>
      <RiskPage mode="hotspot" points={hotspots ?? []} compact />
    </div>
  );
}

function AuditPage({ audit, hourly, stations }: { audit?: AuditSummary; hourly?: HourlyAudit[]; stations: Record<string, number | string>[] }) {
  return (
    <div className="space-y-5">
      <div className="grid gap-4 md:grid-cols-4">
        <Metric label="Total Records" value={formatNumber(audit?.total_records)} />
        <Metric label="Morning Count" value={formatNumber(audit?.morning_count)} />
        <Metric label="Evening Count" value={formatNumber(audit?.evening_count)} tone="blind" />
        <Metric label="SCITA Success" value={formatPercent(audit?.scita_success_rate)} tone="good" />
      </div>
      <Card>
        <div className="mb-3 font-medium">Hour-of-day enforcement evidence</div>
        <HourlyChart hourly={hourly ?? []} />
      </Card>
      <Table title="Station patrol myopia" rows={stations} />
    </div>
  );
}

function HourlyChartInner({ hourly }: { hourly: HourlyAudit[] }) {
  return (
    <div className="h-72 min-h-72">
      <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
        <BarChart data={hourly}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="hour" />
          <YAxis />
          <Tooltip />
          <Bar dataKey="records" fill="#0b83a3" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function RiskPage({ mode, points, compact = false }: { mode: "hotspot" | "blindspot"; points: ZonePoint[]; compact?: boolean }) {
  return (
    <div className="space-y-4">
      <MapPanel points={points} mode={mode} />
      {!compact && (
        <Table
          title={mode === "hotspot" ? "Top observed hotspots" : "Top blindspot audit priorities"}
          rows={points.map((p) => ({
            zone_id: p.zone_id,
            station: p.police_station,
            pfdi: round(p.observed_pfdi),
            blindspot: round(p.blindspot_risk),
            coverage_gap: formatPercent(p.coverage_gap),
            corridor: p.road_corridor,
            place_type: p.place_type
          }))}
        />
      )}
    </div>
  );
}

function JunctionPage({ rows }: { rows: Record<string, number | string>[] }) {
  return <Table title="Junction basin PFDI with hidden No-Junction spillover" rows={rows} />;
}

function PatrolPage({ rows, coverage }: { rows: Record<string, number | string>[]; coverage: Record<string, number | string>[] }) {
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Table title="Patrol myopia by station" rows={rows} />
      <Table title="Coverage gaps by station" rows={coverage} />
    </div>
  );
}

function PlannerPage() {
  const [station, setStation] = useState("");
  const [mode, setMode] = useState("balanced");
  const [officers, setOfficers] = useState(20);
  const [towUnits, setTowUnits] = useState(4);
  const mutation = useMutation({
    mutationFn: () =>
      apiPost<Record<string, unknown>, PlannerResponse>("/planner/recommend", {
        police_station: station || null,
        available_officers: officers,
        available_tow_units: towUnits,
        mode
      })
  });
  const plannerPoints = useMemo(
    () =>
      mutation.data?.recommendations.map((r) => ({
        zone_id: r.zone_id,
        police_station: r.police_station,
        zone_center_lat: r.lat,
        zone_center_lon: r.lon,
        final_risk_score: r.risk_score,
        blindspot_risk: r.blindspot_score,
        observed_pfdi: r.observed_pfdi,
        road_corridor: r.road_corridor
      })) ?? [],
    [mutation.data]
  );
  return (
    <div className="space-y-4">
      <Card className="grid gap-3 md:grid-cols-5">
        <input className="h-9 rounded-md border border-border px-3 text-sm" placeholder="Police station" value={station} onChange={(e) => setStation(e.target.value)} />
        <select className="h-9 rounded-md border border-border px-3 text-sm" value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="conservative">Conservative</option>
          <option value="balanced">Balanced</option>
          <option value="discovery">Discovery</option>
        </select>
        <input className="h-9 rounded-md border border-border px-3 text-sm" type="number" value={officers} onChange={(e) => setOfficers(Number(e.target.value))} />
        <input className="h-9 rounded-md border border-border px-3 text-sm" type="number" value={towUnits} onChange={(e) => setTowUnits(Number(e.target.value))} />
        <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>Recommend</Button>
      </Card>
      {mutation.data && (
        <>
          <div className="grid gap-4 md:grid-cols-4">
            <Metric label="Officers Used" value={String(mutation.data.summary.officers_used)} />
            <Metric label="Tow Units Used" value={String(mutation.data.summary.tow_units_used)} />
            <Metric label="Known Hotspot Allocation" value={String(mutation.data.summary.known_hotspot_allocations)} tone="risk" />
            <Metric label="Blindspot Audit Allocation" value={String(mutation.data.summary.blindspot_audit_allocations)} tone="blind" />
          </div>
          <MapPanel points={plannerPoints} mode="planner" />
          <Table title="Station-wise recommendations" rows={mutation.data.recommendations} />
        </>
      )}
    </div>
  );
}

function MetricsPage({ metrics }: { metrics?: Record<string, unknown> }) {
  const rows = metrics
    ? Object.entries(metrics)
        .filter(([key]) => key !== "model_metadata")
        .map(([model, value]) => ({ model, ...(typeof value === "object" && value ? (value as Record<string, unknown>) : {}) }))
    : [];
  return (
    <div className="space-y-4">
      <Table title="Ranking metrics" rows={rows} />
      <Card>
        <div className="font-medium">Model card caveats</div>
        <p className="mt-2 text-sm leading-6 text-slate-700">
          PFDI is a proxy, not measured congestion. The model uses chronological splits only. Evening sparse observations are treated as uncertain audit priorities, not safe labels.
        </p>
      </Card>
    </div>
  );
}

function Table({ title, rows }: { title: string; rows: Record<string, unknown>[] }) {
  const columns = Object.keys(rows[0] ?? {});
  return (
    <Card className="overflow-hidden">
      <div className="mb-3 font-medium">{title}</div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase text-slate-500">
              {columns.map((col) => <th key={col} className="px-3 py-2 font-medium">{col.replaceAll("_", " ")}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 30).map((row, index) => (
              <tr key={index} className="border-b border-border/70">
                {columns.map((col) => <td key={col} className="max-w-[260px] px-3 py-2 align-top">{formatCell(row[col])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function formatCell(value: unknown) {
  if (Array.isArray(value)) return value.join("; ");
  if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(3);
  if (value === null || value === undefined) return "-";
  return String(value);
}

function formatNumber(value?: number) {
  return value === undefined ? "-" : value.toLocaleString();
}

function formatPercent(value?: number) {
  return value === undefined ? "-" : `${Math.round(value * 100)}%`;
}

function formatScore(value?: number) {
  return value === undefined ? "-" : value.toFixed(1);
}

function round(value?: number) {
  return value === undefined ? "-" : value.toFixed(1);
}
