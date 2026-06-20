"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CalendarDays, CircleAlert, Database, MapPinned, RadioTower, ShieldCheck } from "lucide-react";

import { HourlyChart } from "@/components/hourly-chart";
import { StatCard } from "@/components/stat-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { AuditSummary } from "@/lib/api";
import { getAuditSummary, getHourlyAudit } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/utils";

type StationAuditRow = {
  policeStation: string;
  totalRecords: number;
  eveningCoverage: string;
  patrolMyopiaIndex?: number;
  scitaReadiness?: number;
  evidenceQuality: string;
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

function buildStationRows(summary?: AuditSummary): StationAuditRow[] {
  const counts = asRecord(summary?.raw_summary?.police_station_counts);
  const topMyopia = patrolMyopiaTopStation(summary);
  const scita = scitaRate(summary);
  const eveningCoverage =
    summary?.morning_count && summary.evening_count
      ? `${formatNumber((summary.evening_count / (summary.morning_count + summary.evening_count)) * 100, 2)}% global`
      : "Pending station split";

  return Object.entries(counts)
    .map(([policeStation, value]) => ({
      policeStation,
      totalRecords: Number(value) || 0,
      eveningCoverage,
      patrolMyopiaIndex:
        String(topMyopia.police_station ?? "") === policeStation ? asNumber(topMyopia.patrol_myopia_index) : undefined,
      scitaReadiness: scita,
      evidenceQuality: "Pending station artifact",
    }))
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

export default function AuditPage() {
  const summary = useQuery({ queryKey: ["audit-summary"], queryFn: getAuditSummary });
  const hourly = useQuery({ queryKey: ["audit-hourly"], queryFn: getHourlyAudit });
  const stationRows = buildStationRows(summary.data);
  const scita = scitaRate(summary.data);

  return (
    <div className="space-y-4">
      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total records" value={summary.data?.row_count} detail="Enforcement visibility rows" />
        <StatCard
          label="Actual date range"
          value={summary.data ? `${formatDateTime(summary.data.date_range.start)} - ${formatDateTime(summary.data.date_range.end)}` : "—"}
          detail="created_datetime converted to IST"
        />
        <StatCard label="Morning enforcement" value={summary.data?.morning_count} detail="07:30-15:30 IST" />
        <StatCard label="Evening enforcement" value={summary.data?.evening_count} detail="15:30-20:30 IST" />
        <StatCard label="Evening gap ratio" value={summary.data?.evening_gap_ratio ?? null} detail="Morning over evening" />
        <StatCard label="Fully null outcomes" value={nullOutcomeLabel(summary.data)} detail="Excluded from model labels" />
        <StatCard label="Active zones" value={summary.data?.active_zones ?? "Pending zoning"} detail="Zones with enough records" />
        <StatCard label="Top-zone concentration" value={topZoneSummary(summary.data)} detail="Audit of patrol concentration" />
      </section>

      <section className="grid gap-3 lg:grid-cols-2">
        <Card className="border-blue-200 bg-blue-50">
          <CardContent className="flex gap-3">
            <RadioTower className="mt-0.5 h-5 w-5 shrink-0 text-blue-700" />
            <p className="text-sm font-medium text-blue-950">
              Police violation data is affected by when and where enforcement is visible. CurbFlow estimates this visibility using
              device activity, user activity, station-hour activity, SCITA success, validation coverage, and patrol route patterns.
            </p>
          </CardContent>
        </Card>
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="flex gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" />
            <p className="text-sm font-medium text-amber-950">
              The dataset shows very low evening enforcement records. A normal ML model would treat that as low risk. CurbFlow
              treats it as low evidence and recommends discovery patrols.
            </p>
          </CardContent>
        </Card>
      </section>

      <Card className="border-amber-200 bg-amber-50">
        <CardContent className="flex gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" />
          <p className="text-sm font-medium text-amber-950">
            Current records are strongly morning-heavy. Evening windows are evidence-poor. CurbFlow therefore treats evening
            zero-violation zones as blind-spot audit candidates, not safe zones.
          </p>
        </CardContent>
      </Card>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <HourlyChart data={hourly.data} />
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4" />
                Audit Status
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div className="flex items-start gap-3">
                <CircleAlert className="mt-0.5 h-4 w-4 text-slate-500" />
                <div>
                  <div className="font-medium text-slate-950">Dataset warning</div>
                  <p className="text-slate-600">{summary.data?.key_warning_message ?? "Audit summary has not been seeded yet."}</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <CalendarDays className="mt-0.5 h-4 w-4 text-slate-500" />
                <div>
                  <div className="font-medium text-slate-950">Date range</div>
                  <p className="text-slate-600">
                    {formatDateTime(summary.data?.date_range.start)} to {formatDateTime(summary.data?.date_range.end)}
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <RadioTower className="mt-0.5 h-4 w-4 text-slate-500" />
                <div>
                  <div className="font-medium text-slate-950">SCITA success rate</div>
                  <div className="mt-1 flex items-center gap-2">
                    <ReadinessBadge value={scita} />
                    <span className="text-slate-600">{scita === undefined ? "Not available" : `${formatNumber(scita * 100, 1)}%`}</span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <MapPinned className="h-4 w-4" />
                Top-Zone Concentration
              </CardTitle>
            </CardHeader>
            <CardContent>
              <pre className="max-h-48 overflow-auto rounded-md bg-slate-50 p-3 text-xs text-slate-700">
                {JSON.stringify(summary.data?.top_zone_concentration ?? {}, null, 2)}
              </pre>
            </CardContent>
          </Card>
        </div>
      </section>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Database className="h-4 w-4" />
              Station-Level Audit
            </CardTitle>
            <p className="mt-1 text-xs text-slate-500">
              Station rows are derived from audit summary counts. Station-specific evening/evidence fields appear when seeded.
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
                      <Badge variant={row.eveningCoverage.includes("global") ? "warning" : "secondary"}>{row.eveningCoverage}</Badge>
                    </TableCell>
                    <TableCell>
                      <MyopiaBadge value={row.patrolMyopiaIndex} />
                    </TableCell>
                    <TableCell>
                      <ReadinessBadge value={row.scitaReadiness} />
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">{row.evidenceQuality}</Badge>
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
    </div>
  );
}
