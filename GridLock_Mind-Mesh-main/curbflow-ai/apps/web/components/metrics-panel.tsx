import { AlertTriangle, BarChart3, EyeOff, Gauge, Info, Target } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatNumber } from "@/lib/utils";

type MetricKey =
  | "precision_at_5"
  | "precision_at_10"
  | "ndcg_at_5"
  | "ndcg_at_10"
  | "station_wise_precision_at_5"
  | "mae_pfdi"
  | "wape_count";

type ComparisonRow = {
  id: string;
  label: string;
  description: string;
  source: string;
  metrics: Partial<Record<MetricKey, number>>;
};

const METRIC_COLUMNS: Array<{ key: MetricKey; label: string; digits: number }> = [
  { key: "precision_at_5", label: "Precision@5", digits: 3 },
  { key: "precision_at_10", label: "Precision@10", digits: 3 },
  { key: "ndcg_at_5", label: "NDCG@5", digits: 3 },
  { key: "ndcg_at_10", label: "NDCG@10", digits: 3 },
  { key: "station_wise_precision_at_5", label: "Station-wise Precision@5", digits: 3 },
  { key: "mae_pfdi", label: "MAE PFDI", digits: 2 },
  { key: "wape_count", label: "WAPE count", digits: 3 },
];

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asNumber(value: unknown): number | undefined {
  if (typeof value !== "number" || !Number.isFinite(value)) return undefined;
  return value;
}

function nestedRecord(root: unknown, path: string[]) {
  return path.reduce<unknown>((current, key) => asRecord(current)[key], root);
}

function metricValue(source: unknown, key: MetricKey): number | undefined {
  const direct = asNumber(asRecord(source)[key]);
  if (direct !== undefined) return direct;
  for (const split of ["test", "val", "validation"]) {
    const splitValue = asNumber(asRecord(nestedRecord(source, [split]))[key]);
    if (splitValue !== undefined) return splitValue;
  }
  return undefined;
}

function metricsFromSource(source: unknown): Partial<Record<MetricKey, number>> {
  return Object.fromEntries(
    METRIC_COLUMNS.flatMap((column) => {
      const value = metricValue(source, column.key);
      return value === undefined ? [] : [[column.key, value]];
    }),
  ) as Partial<Record<MetricKey, number>>;
}

function comparisonRow(source: unknown, modelName: string, split = "test") {
  return asArray(asRecord(source).comparison_table)
    .map(asRecord)
    .find((row) => row.model === modelName && row.split === split);
}

function historicalBaselineMetrics(metrics: Record<string, unknown>): Partial<Record<MetricKey, number>> {
  const ranker = asRecord(metrics.lightgbm_ranker);
  const comparison = comparisonRow(ranker, "historical_pfdi_baseline");
  const values = metricsFromSource(comparison);
  const deepTest = asRecord(asRecord(metrics.be_sthgt).test);
  const baselineMae = asNumber(deepTest.baseline_historical_same_slot_mae_pfdi);
  if (baselineMae !== undefined) {
    values.mae_pfdi = baselineMae;
  }
  return values;
}

function lightgbmMetrics(metrics: Record<string, unknown>): Partial<Record<MetricKey, number>> {
  const ranker = asRecord(metrics.lightgbm_ranker);
  return metricsFromSource(comparisonRow(ranker, "lightgbm_lambdarank") ?? ranker);
}

function deepMetrics(metrics: Record<string, unknown>): Partial<Record<MetricKey, number>> {
  return metricsFromSource(metrics.be_sthgt);
}

function ensembleMetrics(metrics: Record<string, unknown>): Partial<Record<MetricKey, number>> {
  const source = Object.entries(metrics).find(([key]) => key.toLowerCase().includes("ensemble"))?.[1];
  if (source) return metricsFromSource(source);
  const ranker = asRecord(metrics.lightgbm_ranker);
  const row = asArray(ranker.comparison_table)
    .map(asRecord)
    .find((entry) => String(entry.model ?? "").toLowerCase().includes("ensemble") && entry.split === "test");
  return metricsFromSource(row);
}

function buildRows(metrics: Record<string, unknown>): ComparisonRow[] {
  return [
    {
      id: "historical_baseline",
      label: "Historical baseline",
      description: "Same-slot historical PFDI or baseline ranking signal.",
      source: "baseline",
      metrics: historicalBaselineMetrics(metrics),
    },
    {
      id: "lightgbm",
      label: "LightGBM ranker",
      description: "LambdaRank model over engineered feature rows.",
      source: "lightgbm_ranker",
      metrics: lightgbmMetrics(metrics),
    },
    {
      id: "be_sthgt",
      label: "BE-STHGT deep model",
      description: "Bias-Exposure Spatio-Temporal Heterogeneous Graph Transformer.",
      source: "be_sthgt",
      metrics: deepMetrics(metrics),
    },
    {
      id: "ensemble",
      label: "BE-STHGT + LightGBM ensemble",
      description: "Final risk blend with rule blindspot score.",
      source: "ensemble",
      metrics: ensembleMetrics(metrics),
    },
  ];
}

function MetricCell({ value, digits }: { value?: number; digits: number }) {
  if (value === undefined) {
    return <Badge variant="secondary">Pending</Badge>;
  }
  return <span className="font-medium text-slate-950">{formatNumber(value, digits)}</span>;
}

function bestAvailable(rows: ComparisonRow[], key: MetricKey, lowerIsBetter = false) {
  const scored = rows
    .map((row) => ({ row, value: row.metrics[key] }))
    .filter((item): item is { row: ComparisonRow; value: number } => item.value !== undefined);
  if (!scored.length) return undefined;
  return scored.sort((left, right) => (lowerIsBetter ? left.value - right.value : right.value - left.value))[0];
}

function ModelComparison({ rows }: { rows: ComparisonRow[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4" />
          Model Comparison
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-hidden rounded-lg border border-slate-200">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Model</TableHead>
                {METRIC_COLUMNS.map((column) => (
                  <TableHead key={column.key}>{column.label}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="min-w-56">
                    <div className="font-medium text-slate-950">{row.label}</div>
                    <div className="mt-1 text-xs text-slate-500">{row.description}</div>
                  </TableCell>
                  {METRIC_COLUMNS.map((column) => (
                    <TableCell key={column.key}>
                      <MetricCell value={row.metrics[column.key]} digits={column.digits} />
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

function SummaryCards({ rows }: { rows: ComparisonRow[] }) {
  const ndcg = bestAvailable(rows, "ndcg_at_10");
  const precision = bestAvailable(rows, "precision_at_5");
  const mae = bestAvailable(rows, "mae_pfdi", true);
  return (
    <div className="grid gap-3 md:grid-cols-3">
      <Card>
        <CardContent className="space-y-1">
          <div className="text-xs font-medium uppercase text-slate-500">Best NDCG@10</div>
          <div className="text-xl font-semibold text-slate-950">{ndcg ? formatNumber(ndcg.value, 3) : "-"}</div>
          <div className="text-xs text-slate-500">{ndcg?.row.label ?? "Pending metrics"}</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="space-y-1">
          <div className="text-xs font-medium uppercase text-slate-500">Best Precision@5</div>
          <div className="text-xl font-semibold text-slate-950">
            {precision ? formatNumber(precision.value, 3) : "-"}
          </div>
          <div className="text-xs text-slate-500">{precision?.row.label ?? "Pending metrics"}</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="space-y-1">
          <div className="text-xs font-medium uppercase text-slate-500">Lowest MAE PFDI</div>
          <div className="text-xl font-semibold text-slate-950">{mae ? formatNumber(mae.value, 2) : "-"}</div>
          <div className="text-xs text-slate-500">{mae?.row.label ?? "Pending metrics"}</div>
        </CardContent>
      </Card>
    </div>
  );
}

function ModelCardPanel() {
  const cards = [
    {
      icon: Target,
      title: "What the model predicts",
      lines: [
        "Next-window risk ranking, predicted PFDI, hotspot probability, count intensity, and blindspot audit priority.",
        "Parking-Induced Flow Disruption Index is a proxy score built from violation severity, vehicle obstruction, location criticality, repeat behavior, and evidence confidence. It does not claim measured speed reduction.",
      ],
    },
    {
      icon: Gauge,
      title: "What it does not claim",
      lines: [
        "It does not prove that every zero-challan area is safe.",
        "It does not infer legal guilt for any individual vehicle, device, or user.",
      ],
    },
    {
      icon: AlertTriangle,
      title: "Data limitations",
      lines: [
        "The police CSV is an enforcement visibility dataset, not a complete illegal-parking census.",
        "Sparse windows increase uncertainty and should be interpreted operationally.",
      ],
    },
    {
      icon: EyeOff,
      title: "Evening blindspot handling",
      lines: [
        "Evening blindspot outputs are audit recommendations, not validated evening predictions.",
        "Low evening observations raise blindspot priority without manufacturing fake hotspots.",
      ],
    },
    {
      icon: Info,
      title: "No outcome-column caveat",
      lines: [
        "closed_datetime, action_taken_timestamp, and description are fully null and are not outcome labels.",
        "No challan should not be interpreted as no illegal parking.",
      ],
    },
  ];

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <Card key={card.title}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Icon className="h-4 w-4" />
                {card.title}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-slate-600">
              {card.lines.map((line) => (
                <p key={line}>{line}</p>
              ))}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function RawMetricSources({ metrics }: { metrics: Record<string, unknown> }) {
  const sources = Object.entries(metrics);
  if (!sources.length) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Metric Sources</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3 lg:grid-cols-2">
        {sources.map(([source, payload]) => (
          <div key={source} className="rounded-lg border border-slate-200">
            <div className="border-b border-slate-100 px-3 py-2 text-sm font-medium text-slate-950">{source}</div>
            <pre className="max-h-72 overflow-auto bg-slate-950 p-3 text-xs text-slate-50">
              {JSON.stringify(payload, null, 2)}
            </pre>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export function MetricsPanel({ metrics = {} }: { metrics?: Record<string, unknown> }) {
  const rows = buildRows(metrics);
  const hasMetrics = Object.keys(metrics).length > 0;
  return (
    <div className="space-y-4">
      {!hasMetrics ? (
        <Card>
          <CardContent className="text-sm text-slate-500">
            No model metrics are available yet. Run deep training, ranker training, prediction, and seed the DuckDB app database.
          </CardContent>
        </Card>
      ) : null}
      <SummaryCards rows={rows} />
      <ModelComparison rows={rows} />
      <ModelCardPanel />
      <RawMetricSources metrics={metrics} />
    </div>
  );
}
