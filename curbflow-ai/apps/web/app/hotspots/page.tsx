"use client";

import { useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";

import { CurbFlowMap } from "@/components/curbflow-map";
import { HotspotTable } from "@/components/hotspot-table";
import { StatCard } from "@/components/stat-card";
import { ZoneDetailsDrawer } from "@/components/zone-details-drawer";
import { Card, CardContent } from "@/components/ui/card";
import { getHotspots, getZoneDetails, getZonesGeoJson } from "@/lib/api";
import { useCurbFlowStore } from "@/lib/store";
import { formatNumber } from "@/lib/utils";

export default function HotspotsPage() {
  const mode = useCurbFlowStore((state) => state.plannerMode);
  const selectedZoneId = useCurbFlowStore((state) => state.selectedZoneId);
  const setSelectedZoneId = useCurbFlowStore((state) => state.setSelectedZoneId);
  const zones = useQuery({ queryKey: ["zones", mode], queryFn: () => getZonesGeoJson({ mode }) });
  const hotspots = useQuery({ queryKey: ["hotspots", mode], queryFn: () => getHotspots({ top_k: 50, mode }) });
  const zoneDetails = useQuery({
    queryKey: ["zone-details", selectedZoneId],
    queryFn: () => getZoneDetails(selectedZoneId ?? ""),
    enabled: Boolean(selectedZoneId),
  });
  const topHotspot = hotspots.data?.[0];

  return (
    <div className="space-y-4">
      <Card className="border-red-200 bg-red-50">
        <CardContent className="flex gap-3">
          <Info className="mt-0.5 h-5 w-5 shrink-0 text-red-700" />
          <p className="text-sm font-medium text-red-950">
            Parking-Induced Flow Disruption Index is a proxy score built from violation severity, vehicle obstruction,
            location criticality, repeat behavior, and evidence confidence. It does not claim measured speed reduction.
          </p>
        </CardContent>
      </Card>

      <section className="grid gap-3 md:grid-cols-3">
        <StatCard label="Displayed hotspots" value={hotspots.data?.length ?? 0} detail="Ranked by observed risk" tone="hotspot" />
        <StatCard label="Top PFDI" value={topHotspot?.predicted_pfdi} detail={topHotspot?.zone_id ?? "Waiting for API"} tone="hotspot" />
        <StatCard
          label="Top station"
          value={topHotspot?.police_station ?? "—"}
          detail={topHotspot?.deployment_priority ? `Priority ${formatNumber(topHotspot.deployment_priority, 1)}` : "Planner priority"}
          tone="visibility"
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_520px]">
        <CurbFlowMap zones={zones.data} mode={mode} onZoneClick={setSelectedZoneId} />
        <HotspotTable rows={hotspots.data?.slice(0, 10)} onSelect={setSelectedZoneId} />
      </section>
      <HotspotTable rows={hotspots.data} onSelect={setSelectedZoneId} />
      <ZoneDetailsDrawer zone={zoneDetails.data} onClose={() => setSelectedZoneId(undefined)} />
    </div>
  );
}
