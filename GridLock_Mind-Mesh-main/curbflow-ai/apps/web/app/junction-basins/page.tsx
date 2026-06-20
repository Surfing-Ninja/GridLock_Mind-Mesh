"use client";

import { useQuery } from "@tanstack/react-query";

import { BlindSpotTable } from "@/components/blindspot-table";
import { CurbFlowMap } from "@/components/curbflow-map";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getBlindspots, getZonesGeoJson } from "@/lib/api";

export default function JunctionBasinsPage() {
  const zones = useQuery({ queryKey: ["zones", "junction-basins"], queryFn: () => getZonesGeoJson({ mode: "discovery" }) });
  const spillovers = useQuery({ queryKey: ["junction-basin-blindspots"], queryFn: () => getBlindspots({ top_k: 25 }) });

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Hidden Junction Basin Detection</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-slate-600">
          Many records are tagged No Junction even when they are spatially close to named junctions. CurbFlow assigns these to
          junction basins to detect spillover around traffic-critical points.
        </CardContent>
      </Card>
      <CurbFlowMap zones={zones.data} mode="discovery" />
      <BlindSpotTable rows={spillovers.data} />
    </div>
  );
}
