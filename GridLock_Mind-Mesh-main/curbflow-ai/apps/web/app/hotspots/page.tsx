"use client";

import { useQuery } from "@tanstack/react-query";

import { CurbFlowMap } from "@/components/curbflow-map";
import { RiskBadge, scoreToRiskLevel } from "@/components/risk-badge";
import { ZoneDetailPanel } from "@/components/zone-details-drawer";
import { getHotspots, getZoneDetails, getZonesGeoJson, type RiskRow } from "@/lib/api";
import { useCurbFlowStore } from "@/lib/store";
import { cn, formatNumber } from "@/lib/utils";

const ACTION_SHORT: Record<string, string> = {
  towing_support: "Deploy Tow",
  beat_patrol: "Beat Patrol",
  mobile_camera_patrol: "Camera",
  repeat_offender_check: "Repeat Check",
  evening_audit_patrol: "Evening Audit",
  coverage_gap_audit: "Gap Audit",
  patrol_expansion: "Expand Patrol",
};
function shortAction(a: string | null | undefined) {
  return a ? (ACTION_SHORT[a] ?? "Enforce") : "—";
}

function HotspotListItem({
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
  const pfdi = row.predicted_pfdi ?? 0;
  const level = scoreToRiskLevel(pfdi, "hotspot");

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex w-full items-center gap-2 border-b border-[#f0f0ec] px-3 py-2.5 text-left transition-all",
        selected
          ? "border-l-2 border-l-red-500 bg-red-50"
          : "border-l-2 border-l-transparent hover:bg-[#f8f8f5]",
      )}
    >
      <span
        className={cn(
          "w-5 shrink-0 text-center text-[9.5px] font-black tabular-nums",
          selected ? "text-red-600" : "text-[#9b9b9b]",
        )}
      >
        #{rank}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[11.5px] font-semibold text-[#1c1c1e]">
          {row.police_station ?? row.zone_id}
        </div>
        <div className="mt-0.5 flex items-center gap-1.5">
          <RiskBadge level={level} />
          <span className="text-[9.5px] text-[#9b9b9b]">{shortAction(row.recommended_action)}</span>
        </div>
      </div>
      <div className="shrink-0 text-right">
        <div className="text-[11px] font-bold tabular-nums text-[#1c1c1e]">{formatNumber(pfdi, 0)}</div>
        <div className="text-[8.5px] text-[#9b9b9b]">PFDI</div>
      </div>
    </button>
  );
}

export default function HotspotsPage() {
  const mode = useCurbFlowStore((s) => s.plannerMode);
  const selectedZoneId = useCurbFlowStore((s) => s.selectedZoneId);
  const setSelectedZoneId = useCurbFlowStore((s) => s.setSelectedZoneId);

  const zones = useQuery({ queryKey: ["zones", mode], queryFn: () => getZonesGeoJson({ mode }) });
  const hotspots = useQuery({
    queryKey: ["hotspots", mode],
    queryFn: () => getHotspots({ top_k: 50, mode }),
  });
  const zoneDetails = useQuery({
    queryKey: ["zone-details", selectedZoneId],
    queryFn: () => getZoneDetails(selectedZoneId ?? ""),
    enabled: Boolean(selectedZoneId),
  });

  const rows = hotspots.data ?? [];
  const criticalCount = rows.filter((r) => (r.predicted_pfdi ?? 0) >= 75).length;

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left: ranked hotspot list */}
      <div className="flex w-[255px] shrink-0 flex-col overflow-hidden border-r border-[#e8e8e4] bg-white">
        {/* Panel header */}
        <div className="shrink-0 border-b border-[#e8e8e4] bg-red-50 px-3 py-2.5">
          <div className="text-[9px] font-black uppercase tracking-widest text-red-600">
            Observed Hotspots
          </div>
          <div className="mt-0.5 text-[10.5px] text-[#6b6b6b]">
            {rows.length} zones · {criticalCount} CRITICAL
          </div>
          <p className="mt-1.5 text-[9.5px] leading-relaxed text-[#9b9b9b]">
            PFDI ranks zones by observed parking-induced disruption. Evening hours are underrepresented
            — use Blindspots for full coverage.
          </p>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto">
          {rows.length === 0 ? (
            <div className="flex h-32 items-center justify-center px-3 text-center text-[10px] text-[#9b9b9b]">
              {hotspots.isLoading ? "Loading hotspot data…" : "No data — run the pipeline first."}
            </div>
          ) : (
            rows.map((row, i) => (
              <HotspotListItem
                key={`${row.zone_id}-${i}`}
                rank={i + 1}
                row={row}
                selected={selectedZoneId === row.zone_id}
                onSelect={() => setSelectedZoneId(row.zone_id)}
              />
            ))
          )}
        </div>
      </div>

      {/* Center: full-height map */}
      <div className="relative min-w-0 flex-1 overflow-hidden">
        <CurbFlowMap
          className="relative h-full w-full overflow-hidden"
          zones={zones.data}
          mode={mode}
          variant="risk"
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
