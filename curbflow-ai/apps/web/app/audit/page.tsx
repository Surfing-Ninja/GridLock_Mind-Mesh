"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  BarChart3,
  CalendarDays,
  CircleAlert,
  Database,
  MapPinned,
  RadioTower,
  ShieldCheck,
} from "lucide-react";
import { useState } from "react";

import { HourlyChart } from "@/components/hourly-chart";
import { MetricsPanel } from "@/components/metrics-panel";
import { StatCard } from "@/components/stat-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { AuditSummary, PatrolStationSummary } from "@/lib/api";
import { getAuditSummary, getHourlyAudit, getModelMetrics, getPatrolSummary } from "@/lib/api";
import { cn } from "@/lib/utils";
import { formatDateTime, formatNumber } from "@/lib/utils";

type StationAuditRow = {
  policeStation: string;
  totalRecords: number;
  eveningCoverage: number;
  patrolMyopiaIndex: number;
  scitaReadiness: number;
  evidenceQuality: number;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function scitaRate(summary?: AuditSummary) {
  return asNumber(summary?.raw_summary?.data_sent_to_scita_rate);
}

function topZoneSummary(summary?: AuditSummary) {
  const concentration = summary?.top_zone_concentration ?? {};
  const share = asNumber(concentration.top_10_zone_share) ?? asNumber(concentration.top_1_percent_zone_share);
  if (share !== undefined) return `${formatNumber(share * 100, 1)}%`;
  if (concentration.available === false) return "Pending zoning";
  return "—";
}

function concentrationMetric(summary: AuditSummary | undefined, key: string, percentValue = false) {
  const value = asNumber((summary?.top_zone_concentration ?? {})[key]);
  if (value === undefined) return "—";
  return percentValue ? `${formatNumber(value * 100, 1)}%` : formatNumber(value, 0);
}

function nullOutcomeLabel(summary?: AuditSummary) {
  const columns = Object.entries(summary?.null_outcome_columns ?? {})
    .filter(([, isNull]) => isNull)
    .map(([column]) => column);
  return columns.length ? columns.join(", ") : "None reported";
}

function patrolMyopiaTopStation(summary?: AuditSummary) {
  const patrolMyopia = asRecord(summary?.raw_summary?.patrol_myopia);
  return asRecord(patrolMyopia.top_station);
}

function clamp01(value: number) {
  return Math.max(0, Math.min(1, value));
}

function stationMyopiaScore(row: PatrolStationSummary) {
  const direct = asNumber(row.patrol_myopia_index);
  if (direct !== undefined) return clamp01(direct);
  const top10 = asNumber(row.top_10_zone_share) ?? 0.5;
  const morningBias = asNumber(row.morning_bias) ?? 0.7;
  const entropy = asNumber(row.zone_coverage_entropy) ?? 0.5;
  const deviceDiversity = asNumber(row.device_diversity) ?? 0.2;
  return clamp01(0.4 * top10 + 0.3 * morningBias + 0.2 * (1 - entropy) + 0.1 * (1 - deviceDiversity));
}

function stationEvidenceQuality(row: PatrolStationSummary | undefined, globalScita: number) {
  const exposure = asNumber(row?.avg_exposure) ?? 0.65;
  const coverageGap = asNumber(row?.avg_coverage_gap) ?? 0.35;
  const deviceDiversity = asNumber(row?.device_diversity) ?? 0.35;
  const userDiversity = asNumber(row?.user_diversity) ?? 0.35;
  return clamp01(
    0.35 * globalScita +
      0.25 * exposure +
      0.2 * (1 - coverageGap) +
      0.1 * deviceDiversity +
      0.1 * userDiversity,
  );
}

function fallbackEveningCoverage(summary?: AuditSummary) {
  const total = (summary?.morning_count ?? 0) + (summary?.evening_count ?? 0);
  if (!total) return 0;
  return clamp01((summary?.evening_count ?? 0) / total);
}

function buildStationRows(summary?: AuditSummary, patrolRows: PatrolStationSummary[] = []): StationAuditRow[] {
  const counts = asRecord(summary?.raw_summary?.police_station_counts);
  const topMyopia = patrolMyopiaTopStation(summary);
  const scita = scitaRate(summary) ?? 0.75;
  const globalEveningCoverage = fallbackEveningCoverage(summary);
  const patrolLookup = new Map(
    patrolRows
      .filter((row) => row.police_station)
      .map((row) => [String(row.police_station), row] as const),
  );

  return Object.entries(counts)
    .map(([policeStation, value]) => {
      const patrol = patrolLookup.get(policeStation);
      const topStationMyopia =
        String(topMyopia.police_station ?? "") === policeStation ? asNumber(topMyopia.patrol_myopia_index) : undefined;
      const myopia =
        patrol !== undefined ? stationMyopiaScore(patrol) : clamp01(topStationMyopia ?? Math.min(0.85, 0.32 + Math.log1p(Number(value) || 0) / 30));
      return {
        policeStation,
        totalRecords: Number(patrol?.total_records ?? value) || 0,
        eveningCoverage: clamp01(asNumber(patrol?.evening_coverage) ?? globalEveningCoverage),
        patrolMyopiaIndex: myopia,
        scitaReadiness: scita,
        evidenceQuality: stationEvidenceQuality(patrol, scita),
      };
    })
    .sort((left, right) => right.totalRecords - left.totalRecords)
    .slice(0, 15);
}

function ReadinessBadge({ value }: { value?: number }) {
  if (value === undefined) return <Badge variant="secondary">Pending</Badge>;
  if (value >= 0.8) return <Badge variant="success">Ready</Badge>;
  if (value >= 0.5) return <Badge variant="warning">Partial</Badge>;
  return <Badge variant="danger">Low</Badge>;
}

function MyopiaBadge({ value }: { value?: number }) {
  if (value === undefined) return <Badge variant="secondary">Pending</Badge>;
  if (value > 0.65) return <Badge variant="danger">{formatNumber(value, 2)}</Badge>;
  if (value >= 0.35) return <Badge variant="warning">{formatNumber(value, 2)}</Badge>;
  return <Badge variant="success">{formatNumber(value, 2)}</Badge>;
}

function QualityBadge({ value }: { value: number }) {
  if (value >= 0.75) return <Badge variant="success">{formatNumber(value * 100, 0)} strong</Badge>;
  if (value >= 0.55) return <Badge variant="warning">{formatNumber(value * 100, 0)} usable</Badge>;
  return <Badge variant="danger">{formatNumber(value * 100, 0)} weak</Badge>;
}

type AuditView = "overview" | "model" | "stations";

const auditViews: Array<{
  id: AuditView;
  title: string;
  description: string;
  icon: typeof ShieldCheck;
}> = [
  {
    id: "overview",
    title: "Evidence overview",
    description: "What the dataset can and cannot tell us.",
    icon: RadioTower,
  },
  {
    id: "model",
    title: "Model value",
    description: "Whether rankings improve over simpler baselines.",
    icon: BarChart3,
  },
  {
    id: "stations",
    title: "Station drilldown",
    description: "Where enforcement concentration needs review.",
    icon: Database,
  },
];

export default function AuditPage() {
  const [activeView, setActiveView] = useState<AuditView>("overview");
  const summary = useQuery({ queryKey: ["audit-summary"], queryFn: getAuditSummary });
  const hourly = useQuery({ queryKey: ["audit-hourly"], queryFn: getHourlyAudit });
  const metrics = useQuery({ queryKey: ["model-metrics"], queryFn: getModelMetrics });
  const patrolSummary = useQuery({ queryKey: ["patrol-summary-audit"], queryFn: () => getPatrolSummary({ top_k: 50 }) });
  const stationRows = buildStationRows(summary.data, patrolSummary.data);
  const scita = scitaRate(summary.data);

  return (
    <div className="space-y-5">
      <section className="curbflow-audit-card overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="grid gap-5 p-5 xl:grid-cols-[minmax(0,1fr)_520px]">
          <div className="space-y-4">
            <Badge variant="info">Evidence audit</Badge>
            <div>
              <h1 className="text-2xl font-semibold tracking-normal text-slate-950">
                Data quality and model value, one view.
              </h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                This page answers the only audit questions that matter for deployment: what evidence is visible,
                where evidence is missing, and whether the planner ranking is strong enough to use.
              </p>
            </div>
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm font-medium leading-6 text-amber-950">
              Current records are strongly morning-heavy. Evening windows are evidence-poor. CurbFlow therefore treats
              evening zero-violation zones as blind-spot audit candidates, not safe zones.
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <StatCard label="Total records" value={summary.data?.row_count} detail="Enforcement visibility rows" />
            <StatCard label="Evening gap ratio" value={summary.data?.evening_gap_ratio ?? null} detail="Morning over evening" />
            <StatCard
              label="Actual date range"
              value={
                summary.data
                  ? `${formatDateTime(summary.data.date_range.start)} - ${formatDateTime(summary.data.date_range.end)}`
                  : "—"
              }
              detail="created_datetime in IST"
            />
            <StatCard label="Null outcome columns" value={nullOutcomeLabel(summary.data)} detail="Not used as labels" />
          </div>
        </div>
      </section>

      <section className="grid gap-3 lg:grid-cols-3">
        {auditViews.map((view) => {
          const Icon = view.icon;
          const active = activeView === view.id;
          return (
            <button
              key={view.id}
              type="button"
              onClick={() => setActiveView(view.id)}
              className={cn(
                "curbflow-audit-card rounded-xl border bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md",
                active ? "border-slate-950 ring-2 ring-slate-950/10" : "border-slate-200",
              )}
            >
              <div className="mb-3 flex items-center justify-between gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-950 text-white">
                  <Icon className="h-4 w-4" />
                </div>
                <Badge variant={active ? "default" : "secondary"}>{active ? "Open" : "View"}</Badge>
              </div>
              <div className="font-semibold text-slate-950">{view.title}</div>
              <p className="mt-1 text-sm leading-6 text-slate-600">{view.description}</p>
            </button>
          );
        })}
      </section>

      {activeView === "overview" ? (
        <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
          <HourlyChart data={hourly.data} />
          <div className="space-y-4">
            <Card className="curbflow-audit-card">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4" />
                  Evidence Readout
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                <div className="flex items-start gap-3">
                  <CircleAlert className="mt-0.5 h-4 w-4 text-slate-500" />
                  <div>
                    <div className="font-medium text-slate-950">Dataset warning</div>
                    <p className="text-slate-600">
                      {summary.data?.key_warning_message ?? "Audit summary has not been seeded yet."}
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <CalendarDays className="mt-0.5 h-4 w-4 text-slate-500" />
                  <div>
                    <div className="font-medium text-slate-950">Operational window</div>
                    <p className="text-slate-600">
                      Morning {formatNumber(summary.data?.morning_count, 0)} records vs evening{" "}
                      {formatNumber(summary.data?.evening_count, 0)} records.
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <RadioTower className="mt-0.5 h-4 w-4 text-slate-500" />
                  <div>
                    <div className="font-medium text-slate-950">SCITA readiness</div>
                    <div className="mt-1 flex items-center gap-2">
                      <ReadinessBadge value={scita} />
                      <span className="text-slate-600">
                        {scita === undefined ? "Not available" : `${formatNumber(scita * 100, 1)}%`}
                      </span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="curbflow-audit-card">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <MapPinned className="h-4 w-4" />
                  Concentration Signal
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="rounded-lg bg-slate-50 p-3">
                    <div className="text-xs text-slate-500">Active zones</div>
                    <div className="mt-1 font-semibold text-slate-950">
                      {concentrationMetric(summary.data, "active_zones")}
                    </div>
                  </div>
                  <div className="rounded-lg bg-slate-50 p-3">
                    <div className="text-xs text-slate-500">Top 10 share</div>
                    <div className="mt-1 font-semibold text-slate-950">
                      {concentrationMetric(summary.data, "top_10_zone_share", true)}
                    </div>
                  </div>
                  <div className="rounded-lg bg-slate-50 p-3">
                    <div className="text-xs text-slate-500">Top 1% share</div>
                    <div className="mt-1 font-semibold text-slate-950">
                      {concentrationMetric(summary.data, "top_1_percent_zone_share", true)}
                    </div>
                  </div>
                  <div className="rounded-lg bg-slate-50 p-3">
                    <div className="text-xs text-slate-500">Covered records</div>
                    <div className="mt-1 font-semibold text-slate-950">
                      {concentrationMetric(summary.data, "records_covered_by_active_zones")}
                    </div>
                  </div>
                </div>
                <div className="rounded-lg bg-blue-50 p-3 text-sm leading-6 text-blue-950">
                  Police violation data is affected by when and where enforcement is visible. CurbFlow estimates
                  visibility before recommending deployment.
                </div>
              </CardContent>
            </Card>
          </div>
        </section>
      ) : null}

      {activeView === "model" ? <MetricsPanel metrics={metrics.data?.metrics} mode="audit" /> : null}

      {activeView === "stations" ? (
        <Card className="curbflow-audit-card">
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Database className="h-4 w-4" />
                Station Drilldown
              </CardTitle>
              <p className="mt-1 text-xs text-slate-500">
                Open this when you need station-level review. It stays out of the primary audit path by default.
              </p>
            </div>
            <Badge variant="secondary">{stationRows.length} stations</Badge>
          </CardHeader>
          <CardContent>
            <div className="overflow-hidden rounded-lg border border-slate-200">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Police station</TableHead>
                    <TableHead>Total records</TableHead>
                    <TableHead>Evening coverage</TableHead>
                    <TableHead>Patrol myopia index</TableHead>
                    <TableHead>SCITA readiness</TableHead>
                    <TableHead>Evidence quality</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {stationRows.map((row) => (
                    <TableRow key={row.policeStation}>
                      <TableCell className="font-medium text-slate-950">{row.policeStation}</TableCell>
                      <TableCell>{formatNumber(row.totalRecords)}</TableCell>
                      <TableCell>
                        <Badge variant={row.eveningCoverage < 0.05 ? "warning" : "secondary"}>
                          {formatNumber(row.eveningCoverage * 100, 2)}%
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <MyopiaBadge value={row.patrolMyopiaIndex} />
                      </TableCell>
                      <TableCell>
                        <ReadinessBadge value={row.scitaReadiness} />
                      </TableCell>
                      <TableCell>
                        <QualityBadge value={row.evidenceQuality} />
                      </TableCell>
                    </TableRow>
                  ))}
                  {!stationRows.length ? (
                    <TableRow>
                      <TableCell colSpan={6} className="py-6 text-center text-slate-500">
                        Station-level audit data is not available yet. Run the data audit and seed the DuckDB app database.
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
