"use client";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import type { RiskRow } from "@/lib/api";
import { formatNumber } from "@/lib/utils";

export function BlindSpotTable({ rows = [], onSelect }: { rows?: RiskRow[]; onSelect?: (zoneId: string) => void }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
      <Table className="min-w-[760px]">
        <TableHeader>
          <TableRow>
            <TableHead>Zone</TableHead>
            <TableHead>Station</TableHead>
            <TableHead>Coverage Gap</TableHead>
            <TableHead>Blindspot Risk</TableHead>
            <TableHead>Explore</TableHead>
            <TableHead>Action</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={`${row.zone_id}-${row.window_start}`} onClick={() => onSelect?.(row.zone_id)}>
              <TableCell className="font-medium text-slate-950">{row.zone_id}</TableCell>
              <TableCell>{row.police_station ?? "—"}</TableCell>
              <TableCell>
                <Badge variant="info">{formatNumber((row.coverage_gap ?? 0) * 100, 1)}%</Badge>
              </TableCell>
              <TableCell>
                <Badge variant="purple">{formatNumber(row.blindspot_risk_score, 1)}</Badge>
              </TableCell>
              <TableCell>{formatNumber(row.explore_score, 1)}</TableCell>
              <TableCell>{row.recommended_action ?? "—"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
