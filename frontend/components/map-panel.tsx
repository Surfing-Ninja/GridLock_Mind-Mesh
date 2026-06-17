"use client";

import { useMemo } from "react";
import DeckGL from "@deck.gl/react";
import { ScatterplotLayer } from "@deck.gl/layers";
import Map from "react-map-gl/maplibre";
import type { ZonePoint } from "@/lib/types";

type Props = {
  points: ZonePoint[];
  mode: "hotspot" | "blindspot" | "planner";
};

export function MapPanel({ points, mode }: Props) {
  const layer = useMemo(() => {
    return new ScatterplotLayer<ZonePoint>({
      id: `${mode}-zones`,
      data: points,
      getPosition: (d) => [d.zone_center_lon ?? d.lon, d.zone_center_lat ?? d.lat],
      getRadius: (d) => 40 + Math.max(d.final_risk_score ?? d.blindspot_risk ?? d.observed_pfdi ?? 20, 10) * 4,
      radiusUnits: "meters",
      getFillColor: (d) => {
        if (mode === "blindspot") return [126, 58, 180, 190];
        if (mode === "planner") return [20, 132, 140, 190];
        const risk = d.observed_pfdi ?? d.final_risk_score ?? 0;
        return risk > 70 ? [218, 60, 42, 200] : risk > 40 ? [232, 139, 34, 190] : [229, 196, 73, 180];
      },
      pickable: true
    });
  }, [mode, points]);

  const first = points[0];
  const latitude = first?.zone_center_lat ?? first?.lat ?? 12.9716;
  const longitude = first?.zone_center_lon ?? first?.lon ?? 77.5946;

  return (
    <div className="h-[420px] overflow-hidden rounded-lg border border-border">
      <DeckGL initialViewState={{ latitude, longitude, zoom: 10.8, pitch: 35, bearing: 0 }} controller layers={[layer]}>
        <Map mapStyle="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json" />
      </DeckGL>
    </div>
  );
}
