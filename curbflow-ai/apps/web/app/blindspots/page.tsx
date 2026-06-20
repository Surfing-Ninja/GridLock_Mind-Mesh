"use client";

import { useQuery } from "@tanstack/react-query";
import { EyeOff } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { BlindSpotTable } from "@/components/blindspot-table";
import { CurbFlowMap } from "@/components/curbflow-map";
import { StatCard } from "@/components/stat-card";
import { ZoneDetailsDrawer } from "@/components/zone-details-drawer";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getBlindspotHourlyVolume,
  getBlindspots,
  getStationShiftCutoff,
  getZoneDetails,
  getZonesGeoJson,
  type StationShiftCutoffRow,
} from "@/lib/api";
import { useCurbFlowStore } from "@/lib/store";
import { formatNumber } from "@/lib/utils";

function cutoffColor(row: StationShiftCutoffRow) {
  const hour = Number(row.median_last_hour ?? 0);
  if (hour >= 15) return "#16a34a";
  if (hour >= 12) return "#d97706";
  return "#dc2626";
}

function EvidenceGapSection() {
  const [mounted, setMounted] = useState(false);
  const hourly = useQuery({ queryKey: ["blindspot-hourly-volume"], queryFn: getBlindspotHourlyVolume });
  const cutoff = useQuery({ queryKey: ["station-shift-cutoff"], queryFn: () => getStationShiftCutoff({ top_k: 12 }) });
  const hourlyRows = useMemo(() => hourly.data ?? [], [hourly.data]);
  const cutoffRows = useMemo(() => cutoff.data ?? [], [cutoff.data]);

  useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <Card id="evening-blindspot" className="border-purple-200">
      <CardHeader>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle>Where enforcement stops</CardTitle>
            <p className="mt-1 text-sm text-slate-600">
              Hourly challan volume and station median last-active hour show why evening zeros are low evidence.
            </p>
          </div>
          <Badge variant="purple">Evening blindspot evidence</Badge>
        </div>
      </CardHeader>
      <CardContent className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="h-72 rounded-lg border border-slate-200 bg-white p-3">
          {mounted ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={hourlyRows}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="hour" tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} tickFormatter={(value) => formatNumber(Number(value), 0)} />
                <Tooltip formatter={(value) => [formatNumber(Number(value), 0), "records"]} labelFormatter={(value) => `${value}:00`} />
                <ReferenceArea x1={15} x2={20} fill="#a855f7" fillOpacity={0.12} />
                <ReferenceLine x={15} stroke="#7e22ce" strokeDasharray="4 4" />
                <Bar dataKey="record_count" radius={[4, 4, 0, 0]}>
                  {hourlyRows.map((row) => (
                    <Cell key={row.hour} fill={row.hour >= 15 && row.hour <= 20 ? "#9333ea" : "#2563eb"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-slate-400">Loading hourly volume</div>
          )}
        </div>
        <div className="space-y-3">
          <div className="rounded-lg border border-orange-200 bg-orange-50 p-3 text-sm text-orange-950">
            The dataset shows very low evening enforcement records. A normal ML model would treat that as low risk.
            CurbFlow treats it as low evidence and recommends discovery patrols.
          </div>
          <div className="h-64 rounded-lg border border-slate-200 bg-white p-3">
            {mounted ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={cutoffRows} layout="vertical" margin={{ left: 22 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" domain={[0, 24]} tickLine={false} axisLine={false} />
                  <YAxis
                    type="category"
                    dataKey="police_station"
                    width={110}
                    tickLine={false}
                    axisLine={false}
                    tick={{ fontSize: 11 }}
                  />
                  <Tooltip
                    formatter={(value, name) => [
                      name === "median_last_hour" ? `${formatNumber(Number(value), 1)}:00` : value,
                      name === "median_last_hour" ? "median last active hour" : name,
                    ]}
                  />
                  <ReferenceLine x={15} stroke="#7e22ce" strokeDasharray="4 4" />
                  <Bar dataKey="median_last_hour" radius={[0, 4, 4, 0]}>
                    {cutoffRows.map((row) => (
                      <Cell key={row.police_station} fill={cutoffColor(row)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-slate-400">Loading station cutoff</div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function BlindspotsPage() {
  const selectedZoneId = useCurbFlowStore((state) => state.selectedZoneId);
  const setSelectedZoneId = useCurbFlowStore((state) => state.setSelectedZoneId);
  const zones = useQuery({ queryKey: ["zones", "discovery"], queryFn: () => getZonesGeoJson({ mode: "discovery" }) });
  const blindspots = useQuery({ queryKey: ["blindspots"], queryFn: () => getBlindspots({ top_k: 50 }) });
  const zoneDetails = useQuery({
    queryKey: ["zone-details", selectedZoneId],
    queryFn: () => getZoneDetails(selectedZoneId ?? ""),
    enabled: Boolean(selectedZoneId),
  });
  const topBlindspot = blindspots.data?.[0];

  return (
    <div className="space-y-4">
      <Card className="border-purple-200 bg-purple-50">
        <CardContent className="flex gap-3">
          <EyeOff className="mt-0.5 h-5 w-5 shrink-0 text-purple-700" />
          <p className="text-sm font-medium text-purple-950">
            A blindspot is a zone with high static obstruction potential but low enforcement visibility. CurbFlow does not
            mark it as a proven hotspot; it marks it as an audit priority.
          </p>
        </CardContent>
      </Card>

      <section className="grid gap-3 md:grid-cols-3">
        <StatCard label="Displayed blindspots" value={blindspots.data?.length ?? 0} detail="Audit-priority zones" tone="blindspot" />
        <StatCard label="Top blindspot risk" value={topBlindspot?.blindspot_risk_score} detail={topBlindspot?.zone_id ?? "Waiting for API"} tone="blindspot" />
        <StatCard
          label="Coverage gap"
          value={topBlindspot?.coverage_gap ? `${formatNumber(topBlindspot.coverage_gap * 100, 1)}%` : "—"}
          detail={topBlindspot?.police_station ?? "Low visibility signal"}
          tone="visibility"
        />
      </section>

      <EvidenceGapSection />

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_520px]">
        <CurbFlowMap zones={zones.data} mode="discovery" variant="blindspot" onZoneClick={setSelectedZoneId} />
        <BlindSpotTable rows={blindspots.data?.slice(0, 10)} onSelect={setSelectedZoneId} />
      </section>
      <BlindSpotTable rows={blindspots.data} onSelect={setSelectedZoneId} />
      <ZoneDetailsDrawer zone={zoneDetails.data} onClose={() => setSelectedZoneId(undefined)} />
    </div>
  );
}
