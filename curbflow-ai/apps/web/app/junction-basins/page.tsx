"use client";

import { useQuery } from "@tanstack/react-query";

import { BlindSpotTable } from "@/components/blindspot-table";
import { CurbFlowMap } from "@/components/curbflow-map";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getBlindspots, getZonesGeoJson } from "@/lib/api";
import { useCurbFlowStore } from "@/lib/store";

export default function JunctionBasinsPage() {
  const selectedZoneId = useCurbFlowStore((state) => state.selectedZoneId);
  const setSelectedZoneId = useCurbFlowStore((state) => state.setSelectedZoneId);
  const zones = useQuery({ queryKey: ["zones", "junction-basins"], queryFn: () => getZonesGeoJson({ mode: "discovery" }) });
  const spillovers = useQuery({ queryKey: ["junction-basin-blindspots"], queryFn: () => getBlindspots({ top_k: 25 }) });

  return (
    <div className="space-y-4">
      <Card data-tour="junction-explainer">
        <CardHeader>
          <CardTitle>Hidden Junction Basin Detection</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-slate-600">
          Many records are tagged No Junction even when they are spatially close to named junctions. CurbFlow assigns these to
          junction basins to detect spillover around traffic-critical points.
        </CardContent>
      </Card>
      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_520px]">
        <div data-tour="junction-map">
          <CurbFlowMap
            zones={zones.data}
            mode="discovery"
            variant="blindspot"
            selectedZoneId={selectedZoneId}
            onZoneClick={setSelectedZoneId}
            className="sm:h-[620px]"
            label="Junction spillover layer"
          />
        </div>
        <div data-tour="junction-list" className="max-h-[620px] overflow-y-auto pr-1">
          <BlindSpotTable rows={spillovers.data} onSelect={setSelectedZoneId} />
        </div>
      </section>
    </div>
  );
}
