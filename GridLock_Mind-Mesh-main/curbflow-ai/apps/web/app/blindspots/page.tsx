"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { CurbFlowMap } from "@/components/curbflow-map";
import { RiskBadge } from "@/components/risk-badge";
import { ZoneDetailPanel } from "@/components/zone-details-drawer";
import { getBlindspots, getZoneDetails, getZonesGeoJson, type RiskRow } from "@/lib/api";
import { useCurbFlowStore } from "@/lib/store";
import { cn, formatNumber } from "@/lib/utils";

type Tab = "queue" | "legend";

function BlindspotListItem({
  rank,
  row,
  selected,
  onSelect,
}: {
  rank: number;
  row: RiskRow;
  selected: boolean;
  onSelect: () => void;
}) {
  const score = row.blindspot_risk_score ?? 0;
  const gapPct = Math.round((row.coverage_gap ?? 0) * 100);

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex w-full items-center gap-2 border-b border-[#f0f0ec] px-3 py-2.5 text-left transition-all",
        selected
          ? "border-l-2 border-l-violet-500 bg-violet-50"
          : "border-l-2 border-l-transparent hover:bg-[#f8f8f5]",
      )}
    >
      <span
        className={cn(
          "w-5 shrink-0 text-center text-[9.5px] font-black tabular-nums",
          selected ? "text-violet-600" : "text-[#9b9b9b]",
        )}
      >
        #{rank}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[11.5px] font-semibold text-[#1c1c1e]">
          {row.police_station ?? row.zone_id}
        </div>
        <div className="mt-0.5 flex items-center gap-1.5">
          <RiskBadge level="blindspot" />
          <span className="text-[9.5px] text-[#9b9b9b]">Gap: {gapPct}%</span>
        </div>
      </div>
      <div className="shrink-0 text-right">
        <div className="text-[11px] font-bold tabular-nums text-violet-700">{formatNumber(score, 1)}</div>
        <div className="text-[8.5px] text-[#9b9b9b]">Risk</div>
      </div>
    </button>
  );
}

function LegendTab() {
  return (
    <div className="space-y-3 overflow-y-auto px-3 py-3 text-[10px] leading-relaxed text-[#6b6b6b]">
      <div className="rounded-lg bg-violet-50 p-3 ring-1 ring-violet-200">
        <div className="mb-1 text-[9px] font-black uppercase tracking-widest text-violet-700">What is a Blindspot?</div>
        <p>
          A zone with high static violation potential but near-zero enforcement visibility. Zero challans ≠ zero risk
          — it means zero coverage.
        </p>
      </div>
      <div className="rounded-lg bg-amber-50 p-3 ring-1 ring-amber-200">
        <div className="mb-1 text-[9px] font-black uppercase tracking-widest text-amber-700">Evening Blindspot (3–8 PM)</div>
        <p>
          The dataset shows structural underrepresentation of evening challans. Patrol coverage collapses after 3 PM.
          CurbFlow recommends discovery patrols in this window.
        </p>
      </div>
      <div className="rounded-lg bg-[#f8f8f5] p-3 ring-1 ring-[#e8e8e4]">
        <div className="mb-1 text-[9px] font-black uppercase tracking-widest text-[#6b6b6b]">How Blindspot Risk is Scored</div>
        <ul className="space-y-1">
          <li>• High static potential (location, vehicle type, junction proximity)</li>
          <li>• Low enforcement visibility (few or no recent challans)</li>
          <li>• Coverage gap % = (unpatrolled windows / total windows)</li>
        </ul>
      </div>
    </div>
  );
}

export default function BlindspotsPage() {
  const [tab, setTab] = useState<Tab>("queue");
  const selectedZoneId = useCurbFlowStore((s) => s.selectedZoneId);
  const setSelectedZoneId = useCurbFlowStore((s) => s.setSelectedZoneId);

  const zones = useQuery({
    queryKey: ["zones", "discovery"],
    queryFn: () => getZonesGeoJson({ mode: "discovery" }),
  });
  const blindspots = useQuery({
    queryKey: ["blindspots"],
    queryFn: () => getBlindspots({ top_k: 50 }),
  });
  const zoneDetails = useQuery({
    queryKey: ["zone-details", selectedZoneId],
    queryFn: () => getZoneDetails(selectedZoneId ?? ""),
    enabled: Boolean(selectedZoneId),
  });

  const rows = blindspots.data ?? [];
  const avgGap = rows.length
    ? Math.round((rows.reduce((a, r) => a + (r.coverage_gap ?? 0), 0) / rows.length) * 100)
    : 0;

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left: blindspot list */}
      <div className="flex w-[255px] shrink-0 flex-col overflow-hidden border-r border-[#e8e8e4] bg-white">
        {/* Panel header */}
        <div className="shrink-0 border-b border-[#e8e8e4] bg-violet-50 px-3 py-2.5">
          <div className="text-[9px] font-black uppercase tracking-widest text-violet-600">
            Evening Blindspots
          </div>
          <div className="mt-0.5 text-[10.5px] text-[#6b6b6b]">
            {rows.length} zones · avg gap {avgGap}%
          </div>
        </div>

        {/* Tabs */}
        <div className="flex shrink-0 border-b border-[#e8e8e4]">
          {(["queue", "legend"] as Tab[]).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={cn(
                "flex-1 py-1.5 text-[9.5px] font-semibold uppercase tracking-wider transition-colors",
                tab === t
                  ? "border-b-2 border-violet-600 text-violet-600"
                  : "text-[#9b9b9b] hover:text-[#1c1c1e]",
              )}
            >
              {t === "queue" ? "Priority Queue" : "About Blindspots"}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {tab === "queue" ? (
          <div className="flex-1 overflow-y-auto">
            {rows.length === 0 ? (
              <div className="flex h-32 items-center justify-center px-3 text-center text-[10px] text-[#9b9b9b]">
                {blindspots.isLoading ? "Loading blindspot data…" : "No data — run the pipeline first."}
              </div>
            ) : (
              rows.map((row, i) => (
                <BlindspotListItem
                  key={`${row.zone_id}-${i}`}
                  rank={i + 1}
                  row={row}
                  selected={selectedZoneId === row.zone_id}
                  onSelect={() => setSelectedZoneId(row.zone_id)}
                />
              ))
            )}
          </div>
        ) : (
          <LegendTab />
        )}
      </div>

      {/* Center: full-height map */}
      <div className="relative min-w-0 flex-1 overflow-hidden">
        <CurbFlowMap
          className="relative h-full w-full overflow-hidden"
          zones={zones.data}
          mode="discovery"
          variant="blindspot"
          onZoneClick={setSelectedZoneId}
        />
      </div>

      {/* Right: zone detail */}
      {selectedZoneId && (
        <ZoneDetailPanel
          zone={zoneDetails.data}
          onClose={() => setSelectedZoneId(undefined)}
        />
      )}
    </div>
  );
}
