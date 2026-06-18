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
              <div className="font-medium">{zone.recommended_action ?? "—"}</div>
            </div>
          </CardContent>
        </Card>
      </SheetContent>
    </Sheet>
  );
}
