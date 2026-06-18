"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Clock3, EyeOff, MapPinned, Network, Radar, Route, ShieldAlert } from "lucide-react";

import { CurbFlowMap } from "@/components/curbflow-map";
import { StatCard } from "@/components/stat-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { PatrolRouteRow, PatrolStationSummary } from "@/lib/api";
import { getPatrolRoutes, getPatrolSummary, getZonesGeoJson } from "@/lib/api";
import { formatNumber } from "@/lib/utils";

function asNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function percent(value: unknown, digits = 1) {
  const number = asNumber(value);
  return number === undefined ? "-" : `${formatNumber(number * 100, digits)}%`;
}

function score(value: unknown, digits = 2) {
  const number = asNumber(value);
  return number === undefined ? "-" : formatNumber(number, digits);
}

function myopiaVariant(level?: string | null, value?: number | null) {
  const normalized = String(level ?? "").toLowerCase();
  if (normalized === "high" || Number(value ?? 0) > 0.65) return "danger" as const;
  if (normalized === "medium" || Number(value ?? 0) >= 0.35) return "warning" as const;
  return "success" as const;
}

function categoryLabel(category?: string | null) {
  if (category === "high_coverage_patrol_loop") return "High-coverage loop";
  if (category === "nearby_uncovered_zone") return "Nearby uncovered";
  return "Frequent transition";
}

function categoryVariant(category?: string | null) {
  if (category === "nearby_uncovered_zone") return "danger" as const;
  if (category === "high_coverage_patrol_loop") return "success" as const;
  return "secondary" as const;
}

function filteredRoutes(routes: PatrolRouteRow[], category: string) {
  return routes.filter((route) => route.route_category === category).slice(0, 6);
}

function routeTitle(route: PatrolRouteRow) {
  return `${route.from_zone_id ?? "-"} -> ${route.to_zone_id ?? "-"}`;
}

function StationMyopiaCard({ row }: { row: PatrolStationSummary }) {
  return (
    <Card>
      <CardHeader className="space-y-2">
        <div className="flex items-start justify-between gap-3">
          <CardTitle className="text-base">{row.police_station ?? "Unknown station"}</CardTitle>
          <Badge variant={myopiaVariant(row.patrol_myopia_level, row.patrol_myopia_index)}>
            {row.patrol_myopia_level ?? "Pending"}
          </Badge>
        </div>
        <div className="text-2xl font-semibold text-slate-950">{score(row.patrol_myopia_index)}</div>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-xs uppercase text-slate-500">Top 10 zone share</div>
          <div className="font-medium text-slate-950">{percent(row.top_10_zone_share)}</div>
        </div>
        <div>
          <div className="text-xs uppercase text-slate-500">Evening coverage</div>
          <div className="font-medium text-slate-950">{percent(row.evening_coverage)}</div>
        </div>
        <div>
          <div className="text-xs uppercase text-slate-500">Zone entropy</div>
          <div className="font-medium text-slate-950">{score(row.zone_coverage_entropy)}</div>
        </div>
        <div>
          <div className="text-xs uppercase text-slate-500">Nearby uncovered</div>
          <div className="font-medium text-slate-950">{formatNumber(Number(row.nearby_uncovered_zones ?? 0))}</div>
        </div>
      </CardContent>
    </Card>
  );
}

function RouteTable({ title, rows }: { title: string; rows: PatrolRouteRow[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-hidden rounded-lg border border-slate-200">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Route</TableHead>
                <TableHead>Station</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Transitions</TableHead>
                <TableHead>Weight</TableHead>
                <TableHead>Gap</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row, index) => (
                <TableRow key={`${row.from_zone_id}-${row.to_zone_id}-${index}`}>
                  <TableCell className="font-medium text-slate-950">
                    <span className="inline-flex items-center gap-1">
                      {row.from_zone_id ?? "-"}
                      <ArrowRight className="h-3 w-3 text-slate-400" />
                      {row.to_zone_id ?? "-"}
                    </span>
                  </TableCell>
                  <TableCell>{row.police_station ?? "-"}</TableCell>
                  <TableCell>
                    <Badge variant={categoryVariant(row.route_category)}>{categoryLabel(row.route_category)}</Badge>
                  </TableCell>
                  <TableCell>{formatNumber(Number(row.patrol_transition_count ?? 0))}</TableCell>
                  <TableCell>{score(row.patrol_edge_weight)}</TableCell>
                  <TableCell>
                    {asNumber(row.mean_gap_hours) === undefined ? "-" : `${formatNumber(Number(row.mean_gap_hours), 1)}h`}
                  </TableCell>
                </TableRow>
              ))}
              {!rows.length ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-6 text-center text-slate-500">
                    No aggregate patrol routes are available for this category yet.
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

function RecommendationPanel({
  summaryRows,
  routes,
}: {
  summaryRows: PatrolStationSummary[];
  routes: PatrolRouteRow[];
}) {
  const highMyopiaStations = summaryRows.filter((row) => Number(row.patrol_myopia_index ?? 0) > 0.65).length;
  const lowEveningStations = summaryRows.filter((row) => Number(row.evening_coverage ?? 1) < 0.15).length;
  const uncoveredRoutes = routes.filter((route) => route.route_category === "nearby_uncovered_zone").length;
  const auditStations = summaryRows.filter(
    (row) => Number(row.device_diversity ?? 1) < 0.1 || Number(row.user_diversity ?? 1) < 0.1,
  ).length;

  const recommendations = [
    {
      action: "expand patrol route",
      icon: Route,
      variant: "danger" as const,
      metric: `${formatNumber(uncoveredRoutes)} route gaps`,
      text: "Prioritize zones flagged as near existing patrol movement but still uncovered.",
    },
    {
      action: "evening audit",
      icon: Clock3,
      variant: "warning" as const,
      metric: `${formatNumber(lowEveningStations)} low-evening stations`,
      text: "Schedule short evening audit passes where myopia is high and evening evidence is sparse.",
    },
    {
      action: "evidence quality audit",
      icon: ShieldAlert,
      variant: "secondary" as const,
      metric: `${formatNumber(Math.max(auditStations, highMyopiaStations))} candidate stations`,
      text: "Review aggregate evidence quality where station coverage is narrow or actor diversity is low.",
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recommendation Panel</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-3">
        {recommendations.map((recommendation) => {
          const Icon = recommendation.icon;
          return (
            <div key={recommendation.action} className="rounded-lg border border-slate-200 p-3">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Icon className="h-4 w-4 text-slate-600" />
                  <div className="font-medium text-slate-950">{recommendation.action}</div>
                </div>
                <Badge variant={recommendation.variant}>{recommendation.metric}</Badge>
              </div>
              <p className="text-sm text-slate-600">{recommendation.text}</p>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

export default function PatrolDigitalTwinPage() {
  const zones = useQuery({
    queryKey: ["zones", "patrol-digital-twin"],
    queryFn: () => getZonesGeoJson({ mode: "balanced" }),
  });
  const summary = useQuery({ queryKey: ["patrol-summary"], queryFn: () => getPatrolSummary({ top_k: 24 }) });
  const routes = useQuery({ queryKey: ["patrol-routes"], queryFn: () => getPatrolRoutes({ top_k: 75 }) });

  const summaryRows = summary.data ?? [];
  const routeRows = routes.data ?? [];
  const frequentRoutes = filteredRoutes(routeRows, "frequent_transition");
  const patrolLoops = filteredRoutes(routeRows, "high_coverage_patrol_loop");
  const uncoveredRoutes = filteredRoutes(routeRows, "nearby_uncovered_zone");
  const connectedZones = summaryRows.reduce((sum, row) => sum + Number(row.patrol_connected_zones ?? 0), 0);
  const nearbyUncoveredZones = summaryRows.reduce((sum, row) => sum + Number(row.nearby_uncovered_zones ?? 0), 0);
  const topRoute = routeRows[0];

  return (
    <div className="space-y-4">
      <section className="grid gap-3 md:grid-cols-4">
        <StatCard label="Stations scored" value={summaryRows.length} />
        <StatCard label="Patrol-connected zones" value={connectedZones} />
        <StatCard label="Nearby uncovered zones" value={nearbyUncoveredZones} />
        <StatCard label="Top route" value={topRoute ? routeTitle(topRoute) : "Pending patrol graph"} />
      </section>

      <Card className="border-blue-200 bg-blue-50">
        <CardContent className="flex gap-3">
          <Route className="mt-0.5 h-5 w-5 shrink-0 text-blue-700" />
          <p className="text-sm font-medium text-blue-950">
            Patrol Myopia Index measures whether a station’s enforcement is concentrated in a few repeated zones and time windows,
            potentially missing nearby risk zones.
          </p>
        </CardContent>
      </Card>

      <section className="grid gap-3 xl:grid-cols-3">
        {summaryRows.slice(0, 6).map((row, index) => (
          <StationMyopiaCard key={row.police_station ?? `station-${index}`} row={row} />
        ))}
        {!summaryRows.length ? (
          <Card className="xl:col-span-3">
            <CardContent className="py-8 text-center text-sm text-slate-500">
              Patrol myopia data is not available yet. Run feature building and seed the DuckDB app database.
            </CardContent>
          </Card>
        ) : null}
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <CurbFlowMap zones={zones.data} mode="balanced" variant="patrol" />
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Network className="h-4 w-4" />
                Transition Graph Summary
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex items-start gap-3">
                <Radar className="mt-0.5 h-4 w-4 text-blue-600" />
                <div>
                  <div className="font-medium text-slate-950">Frequent connected zones</div>
                  <p className="text-slate-600">{formatNumber(frequentRoutes.length)} aggregate zone-to-zone routes.</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <MapPinned className="mt-0.5 h-4 w-4 text-emerald-600" />
                <div>
                  <div className="font-medium text-slate-950">High-coverage patrol loops</div>
                  <p className="text-slate-600">{formatNumber(patrolLoops.length)} routes connect consistently covered zones.</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <EyeOff className="mt-0.5 h-4 w-4 text-red-600" />
                <div>
                  <div className="font-medium text-slate-950">Nearby uncovered zones</div>
                  <p className="text-slate-600">{formatNumber(uncoveredRoutes.length)} routes indicate expansion opportunities.</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Map Layer</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-slate-600">Patrol-connected zones</span>
                <Badge variant="secondary">Blue</Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-600">Near-patrol-but-uncovered zones</span>
                <Badge variant="danger">Red</Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-600">No route signal</span>
                <Badge variant="secondary">Muted</Badge>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      <RecommendationPanel summaryRows={summaryRows} routes={routeRows} />

      <section className="grid gap-4">
        <RouteTable title="Zones Frequently Connected By Patrol Transitions" rows={frequentRoutes} />
        <RouteTable title="High-Coverage Patrol Loops" rows={patrolLoops} />
        <RouteTable title="Nearby Uncovered Zones" rows={uncoveredRoutes} />
      </section>
    </div>
  );
}
