"use client";

import { useQuery } from "@tanstack/react-query";
import { EyeOff } from "lucide-react";

import { BlindSpotTable } from "@/components/blindspot-table";
import { CurbFlowMap } from "@/components/curbflow-map";
import { StatCard } from "@/components/stat-card";
import { ZoneDetailsDrawer } from "@/components/zone-details-drawer";
import { Card, CardContent } from "@/components/ui/card";
import { getBlindspots, getZoneDetails, getZonesGeoJson } from "@/lib/api";
import { useCurbFlowStore } from "@/lib/store";
import { formatNumber } from "@/lib/utils";

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

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_520px]">
        <CurbFlowMap zones={zones.data} mode="discovery" variant="blindspot" onZoneClick={setSelectedZoneId} />
        <BlindSpotTable rows={blindspots.data?.slice(0, 10)} onSelect={setSelectedZoneId} />
      </section>
      <BlindSpotTable rows={blindspots.data} onSelect={setSelectedZoneId} />
      <ZoneDetailsDrawer zone={zoneDetails.data} onClose={() => setSelectedZoneId(undefined)} />
    </div>
  );
}
