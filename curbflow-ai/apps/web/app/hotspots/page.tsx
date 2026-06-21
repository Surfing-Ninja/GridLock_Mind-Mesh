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
      <Card data-tour="hotspots-warning" className="border-red-200 bg-red-50">
        <CardContent className="flex gap-3">
          <Info className="mt-0.5 h-5 w-5 shrink-0 text-red-700" />
          <p className="text-sm font-medium text-red-950">
            Parking-Induced Flow Disruption Index is a proxy score built from violation severity, vehicle obstruction,
            location criticality, repeat behavior, and evidence confidence. It does not claim measured speed reduction.
          </p>
        </CardContent>
      </Card>

      <section data-tour="hotspots-kpis" className="grid gap-3 md:grid-cols-3">
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
        <div data-tour="hotspots-map" className="space-y-2">
          <CurbFlowMap
            zones={zones.data}
            mode={mode}
            selectedZoneId={selectedZoneId}
            onZoneClick={setSelectedZoneId}
            className="sm:h-[620px]"
          />
          <p className="rounded-md border border-slate-200 bg-white px-3 py-2 text-xs leading-5 text-slate-600 shadow-sm">
            Predictions are based on historical challan patterns (Nov 2023–Apr 2024). Each record represents a
            challan issued by an officer, not a camera detection. Evening hours (3–8PM IST) are structurally
            underrepresented in this dataset.
          </p>
        </div>
        <div data-tour="hotspots-list" className="max-h-[620px] overflow-y-auto pr-1">
          <HotspotTable rows={hotspots.data} onSelect={setSelectedZoneId} />
        </div>
      </section>
      <ZoneDetailsDrawer zone={zoneDetails.data} onClose={() => setSelectedZoneId(undefined)} />
    </div>
  );
}
