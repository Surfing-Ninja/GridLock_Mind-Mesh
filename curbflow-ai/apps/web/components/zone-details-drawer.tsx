"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetOverlay,
  SheetTitle,
} from "@/components/ui/sheet";
import type { ZoneDetails } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/utils";

function actionLabel(value?: string | null) {
  return String(value ?? "patrol_check")
    .replaceAll("_", " ")
    .replace(/\s+/g, " ")
    .trim();
}

function zoneCellExplainer(zoneId?: string | null) {
  return `${zoneId ?? "This zone"} is an internal 300 m grid cell used by CurbFlow to group nearby enforcement records. It is not a street address or public ward name.`;
}

function operationalRead(zone: ZoneDetails) {
  const pfdi = Number(zone.predicted_pfdi ?? zone.observed_pfdi ?? 0);
  const coverageGap = Number(zone.coverage_gap ?? 0);
  const blindspotRisk = Number(zone.blindspot_risk_score ?? 0);

  if (coverageGap >= 0.7 && blindspotRisk >= 20) {
    return "Operational read: this zone has weak enforcement visibility and enough static risk to justify an audit patrol. Treat missing challans as missing evidence, not proof that the area is clear.";
  }
  if (pfdi >= 75) {
    return "Operational read: this zone has strong observed parking-disruption evidence. It should be handled as a known hotspot for targeted enforcement.";
  }
  if (coverageGap >= 0.5) {
    return "Operational read: enforcement visibility is limited here. A short patrol check can confirm whether this is genuinely clear or just under-observed.";
  }
  return "Operational read: this zone is currently lower priority than the strongest hotspots and blindspots, but it remains part of the station coverage picture.";
}

export function ZoneDetailsDrawer({
  zone,
  onClose,
}: {
  zone?: ZoneDetails;
  onClose: () => void;
}) {
  if (!zone?.zone_id) return null;
  return (
    <Sheet open={Boolean(zone?.zone_id)}>
      <SheetOverlay onClick={onClose} />
      <SheetContent>
        <SheetHeader>
          <div>
            <SheetTitle>Zone {zone.zone_id}</SheetTitle>
            <SheetDescription>{formatDateTime(zone.window_start)}</SheetDescription>
            <p className="mt-2 max-w-md text-sm leading-6 text-slate-600">{zoneCellExplainer(zone.zone_id)}</p>
          </div>
          <SheetClose onClose={onClose} />
        </SheetHeader>
        <div className="mb-4 flex flex-wrap gap-2">
          <Badge variant="danger">Observed risk</Badge>
          <Badge variant="purple">Blindspot audit</Badge>
          <Badge variant="info">Visibility</Badge>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Risk Details</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <div className="text-slate-500">Station</div>
              <div className="font-medium">{zone.police_station ?? "—"}</div>
            </div>
            <div>
              <div className="text-slate-500">Predicted PFDI</div>
              <div className="font-medium">{formatNumber(zone.predicted_pfdi, 1)}</div>
            </div>
            <div>
              <div className="text-slate-500">Coverage gap</div>
              <div className="font-medium text-blue-700">{formatNumber((zone.coverage_gap ?? 0) * 100, 1)}%</div>
            </div>
            <div>
              <div className="text-slate-500">Blindspot risk</div>
              <div className="font-medium text-purple-700">{formatNumber(zone.blindspot_risk_score, 1)}</div>
            </div>
            <div className="col-span-2">
              <div className="text-slate-500">Recommended action</div>
              <div className="font-medium">{actionLabel(zone.recommended_action)}</div>
            </div>
            <div className="col-span-2 rounded-lg border border-slate-100 bg-slate-50 p-3">
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                What this means
              </div>
              <p className="leading-6 text-slate-700">{operationalRead(zone)}</p>
            </div>
          </CardContent>
        </Card>
      </SheetContent>
    </Sheet>
  );
}
