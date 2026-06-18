import { AlertTriangle } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

export function NullColumnWarning({ columns = {} }: { columns?: Record<string, boolean> }) {
  const nullColumns = Object.entries(columns).filter(([, isNull]) => isNull);
  return (
    <Card className="border-amber-200 bg-amber-50">
      <CardContent className="flex gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 text-amber-700" />
        <div>
          <div className="text-sm font-semibold text-amber-950">Outcome-label warning</div>
          <p className="mt-1 text-sm text-amber-900">
            {nullColumns.length
              ? `${nullColumns.map(([column]) => column).join(", ")} are fully null and must not be used as labels.`
              : "No fully null outcome columns were reported by the audit."}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
