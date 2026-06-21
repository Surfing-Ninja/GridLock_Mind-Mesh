import { AlertTriangle, BarChart3, CheckCircle2, EyeOff, Gauge, Info, Target, TrendingUp } from "lucide-react";

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
  tone?: "curbflow" | "traditional" | "baseline" | "deep";
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

const RANKING_COLUMNS = METRIC_COLUMNS.filter((column) => column.key !== "mae_pfdi" && column.key !== "wape_count");

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

function benchmarkMetrics(metrics: Record<string, unknown>, modelName: string): Partial<Record<MetricKey, number>> {
  return metricsFromSource(comparisonRow(metrics.model_benchmark, modelName));
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

function countBaselineMetrics(metrics: Record<string, unknown>): Partial<Record<MetricKey, number>> {
  const ranker = asRecord(metrics.lightgbm_ranker);
  return metricsFromSource(comparisonRow(ranker, "count_only_baseline"));
}

function ruleBlindspotBaselineMetrics(metrics: Record<string, unknown>): Partial<Record<MetricKey, number>> {
  const ranker = asRecord(metrics.lightgbm_ranker);
  return metricsFromSource(comparisonRow(ranker, "rule_blindspot_baseline"));
}

function lightgbmMetrics(metrics: Record<string, unknown>): Partial<Record<MetricKey, number>> {
  const benchmark = benchmarkMetrics(metrics, "lightgbm_lambdarank");
  if (Object.keys(benchmark).length) return benchmark;
  const ranker = asRecord(metrics.lightgbm_ranker);
  return metricsFromSource(comparisonRow(ranker, "lightgbm_lambdarank") ?? ranker);
}

function deepMetrics(metrics: Record<string, unknown>): Partial<Record<MetricKey, number>> {
  return metricsFromSource(metrics.be_sthgt);
}

function deepRegressionMetrics(metrics: Record<string, unknown>): Partial<Record<MetricKey, number>> {
  const source = deepMetrics(metrics);
  return {
    mae_pfdi: source.mae_pfdi,
    wape_count: source.wape_count,
  };
}

function plannerStackMetrics(metrics: Record<string, unknown>): Partial<Record<MetricKey, number>> {
  const benchmarkPlanner = benchmarkMetrics(metrics, "curbflow_planner_stack");
  const configuredPlanner = metricsFromSource(comparisonRow(asRecord(metrics.lightgbm_ranker), "curbflow_conservative_planner"));
  const planner = Object.keys(benchmarkPlanner).length ? benchmarkPlanner : configuredPlanner;
  const fallback = Object.keys(planner).length ? planner : lightgbmMetrics(metrics);
  return {
    ...fallback,
    ...deepRegressionMetrics(metrics),
  };
}

function buildRows(metrics: Record<string, unknown>): ComparisonRow[] {
  const catboost = benchmarkMetrics(metrics, "catboost_yetirank");
  const xgboost = benchmarkMetrics(metrics, "xgboost_ndcg_ranker");
  const rows: ComparisonRow[] = [
    {
      id: "curbflow_planner",
      label: "CurbFlow planner stack",
      description: "Bias-aware deployment priority with visibility, blindspot, graph, and deep-risk signals.",
      source: "predictions + labels",
      metrics: plannerStackMetrics(metrics),
      tone: "curbflow",
    },
    {
      id: "count_baseline",
      label: "Count-only baseline",
      description: "Traditional heatmap behavior: rank where observed records are high.",
      source: "baseline",
      metrics: countBaselineMetrics(metrics),
      tone: "baseline",
    },
    {
      id: "historical_baseline",
      label: "Historical baseline",
      description: "Same-slot historical PFDI or baseline ranking signal.",
      source: "baseline",
      metrics: historicalBaselineMetrics(metrics),
      tone: "baseline",
    },
    {
      id: "rule_blindspot",
      label: "Rule blindspot baseline",
      description: "Simple rule score for low-visibility audit zones.",
      source: "baseline",
      metrics: ruleBlindspotBaselineMetrics(metrics),
      tone: "baseline",
    },
    {
      id: "lightgbm",
      label: "Traditional LightGBM ranker",
      description: "LightGBM LambdaRank trained on visibility, blindspot, graph, and temporal features.",
      source: "lightgbm_ranker",
      metrics: lightgbmMetrics(metrics),
      tone: "traditional",
    },
    {
      id: "be_sthgt",
      label: "BE-STHGT deep model",
      description: "Bias-Exposure Spatio-Temporal Heterogeneous Graph Transformer.",
      source: "be_sthgt",
      metrics: deepMetrics(metrics),
      tone: "deep",
    },
  ];
  if (Object.keys(catboost).length) {
    rows.push({
      id: "catboost",
      label: "CatBoost ranker",
      description: "Traditional YetiRank boosted-tree benchmark.",
      source: "model_benchmark",
      metrics: catboost,
      tone: "traditional",
    });
  }
  if (Object.keys(xgboost).length) {
    rows.push({
      id: "xgboost",
      label: "XGBoost ranker",
      description: "Traditional NDCG ranker benchmark.",
      source: "model_benchmark",
      metrics: xgboost,
      tone: "traditional",
    });
  }
  return rows;
}

function MetricCell({ value, digits }: { value?: number; digits: number }) {
  if (value === undefined) {
    return <span className="text-sm text-slate-400">Not measured</span>;
  }
  return <span className="font-medium text-slate-950">{formatNumber(value, digits)}</span>;
}

function rankingStrengthLabel(value?: number) {
  if (value === undefined) return "Not measured";
  if (value >= 0.7) return "Strong";
  if (value >= 0.55) return "Usable";
  if (value >= 0.35) return "Limited";
  return "Weak";
}

function topFivePlannerStrength(row: ComparisonRow) {
  const precision = row.metrics.precision_at_5;
  const ndcg = row.metrics.ndcg_at_5 ?? row.metrics.ndcg_at_10;
  const stationPrecision = row.metrics.station_wise_precision_at_5;
  if (precision === undefined && ndcg === undefined && stationPrecision === undefined) return undefined;
  return 0.45 * (precision ?? 0) + 0.35 * (ndcg ?? 0) + 0.2 * (stationPrecision ?? 0);
}

function bestTopFiveStrength(rows: ComparisonRow[]) {
  const scored = rows
    .map((row) => ({ row, value: topFivePlannerStrength(row) }))
    .filter((item): item is { row: ComparisonRow; value: number } => item.value !== undefined);
  if (!scored.length) return undefined;
  return scored.sort((left, right) => right.value - left.value)[0];
}

function chartTone(row: ComparisonRow) {
  if (row.tone === "curbflow") return "bg-emerald-600";
  if (row.tone === "traditional") return "bg-slate-950";
  if (row.tone === "deep") return "bg-blue-700";
  if (row.id === "rule_blindspot") return "bg-amber-600";
  return "bg-slate-400";
}

function RankingComparisonGraph({ rows }: { rows: ComparisonRow[] }) {
  const chartRows = rows
    .map((row) => ({ row, strength: topFivePlannerStrength(row) }))
    .filter((item): item is { row: ComparisonRow; strength: number } => item.strength !== undefined)
    .sort((left, right) => right.strength - left.strength);
  const best = bestTopFiveStrength(rows);
  const lightgbm = rows.find((row) => row.id === "lightgbm");
  const curbflow = rows.find((row) => row.id === "curbflow_planner");
  const improvement =
    curbflow !== undefined && lightgbm !== undefined
      ? (topFivePlannerStrength(curbflow) ?? 0) - (topFivePlannerStrength(lightgbm) ?? 0)
      : undefined;

  return (
    <Card className="curbflow-audit-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TrendingUp className="h-4 w-4" />
          Planner Strength Graph
        </CardTitle>
        <p className="mt-1 text-xs leading-5 text-slate-500">
          This is not a confidence probability. It is a deployment-shortlist score built from Precision@5, NDCG@5,
          and station-wise Precision@5, so it reflects whether the first few recommended zones are useful.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {chartRows.length ? (
          <div className="space-y-3">
            {chartRows.map(({ row, strength }) => {
              return (
                <div key={row.id} className="space-y-1">
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <div>
                      <span className="font-medium text-slate-950">{row.label}</span>
                      <span className="ml-2 text-xs text-slate-500">{rankingStrengthLabel(strength)}</span>
                      <div className="mt-0.5 text-xs text-slate-500">
                        P@5 {row.metrics.precision_at_5 === undefined ? "n/a" : formatNumber(row.metrics.precision_at_5, 3)}
                        {" · "}
                        NDCG@5 {row.metrics.ndcg_at_5 === undefined ? "n/a" : formatNumber(row.metrics.ndcg_at_5, 3)}
                      </div>
                    </div>
                    <span className="font-semibold text-slate-950">{formatNumber(strength * 100, 0)}/100</span>
                  </div>
                  <div className="h-3 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className={`${chartTone(row)} h-full rounded-full transition-all duration-700`}
                      style={{ width: `${Math.max(4, Math.min(100, strength * 100))}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600">
            Ranking metrics are not available yet.
          </div>
        )}

        <div className="grid gap-3 text-sm md:grid-cols-3">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="text-xs font-semibold uppercase text-slate-500">Best available</div>
            <div className="mt-1 font-semibold text-slate-950">{best?.row.label ?? "Not measured"}</div>
            <p className="mt-1 text-xs leading-5 text-slate-600">
              {best ? `${formatNumber(best.value * 100, 0)}/100 top-5 planner strength.` : "Run training first."}
            </p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="text-xs font-semibold uppercase text-slate-500">Lift over LightGBM</div>
            <div className="mt-1 font-semibold text-slate-950">
              {improvement === undefined ? "Not measured" : `+${formatNumber(improvement * 100, 1)} pts`}
            </div>
            <p className="mt-1 text-xs leading-5 text-slate-600">
              Compares the CurbFlow planner stack against the traditional LightGBM ranking row.
            </p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="text-xs font-semibold uppercase text-slate-500">Traditional boosters</div>
            <div className="mt-1 font-semibold text-slate-950">LGBM measured</div>
            <p className="mt-1 text-xs leading-5 text-slate-600">
              CatBoost/XGBoost are not shown because no trained artifact exists in this run.
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
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
                {RANKING_COLUMNS.map((column) => (
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
                  {RANKING_COLUMNS.map((column) => (
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

function SummaryCards({ rows, compact = false }: { rows: ComparisonRow[]; compact?: boolean }) {
  const curbflow = rows.find((row) => row.id === "curbflow_planner");
  const plannerStrength = curbflow ? topFivePlannerStrength(curbflow) : undefined;
  const precision = curbflow?.metrics.precision_at_10;
  const ndcg = curbflow?.metrics.ndcg_at_10;
  const mae = curbflow?.metrics.mae_pfdi;
  return (
    <div className="grid gap-3 md:grid-cols-3">
      <Card className={compact ? "curbflow-audit-card overflow-hidden" : undefined}>
        <CardContent className={compact ? "space-y-2 p-5" : "space-y-1"}>
          <div className="text-xs font-medium uppercase text-slate-500">CurbFlow planner strength</div>
          <div className={compact ? "text-3xl font-semibold text-slate-950" : "text-xl font-semibold text-slate-950"}>
            {plannerStrength !== undefined ? `${formatNumber(plannerStrength * 100, 0)}/100` : "-"}
          </div>
          <div className="text-xs text-slate-500">
            {plannerStrength !== undefined
              ? `${rankingStrengthLabel(plannerStrength)} deployment shortlist; not probability confidence`
              : "Run model benchmark to fill ranking metrics"}
          </div>
        </CardContent>
      </Card>
      <Card className={compact ? "curbflow-audit-card overflow-hidden" : undefined}>
        <CardContent className={compact ? "space-y-2 p-5" : "space-y-1"}>
          <div className="text-xs font-medium uppercase text-slate-500">CurbFlow top-10 hit rate</div>
          <div className={compact ? "text-3xl font-semibold text-slate-950" : "text-xl font-semibold text-slate-950"}>
            {precision !== undefined ? formatNumber(precision, 3) : "-"}
          </div>
          <div className="text-xs text-slate-500">
            {ndcg !== undefined ? `NDCG@10 ${formatNumber(ndcg, 3)} from CurbFlow ranking` : "Ranking metric pending"}
          </div>
        </CardContent>
      </Card>
      <Card className={compact ? "curbflow-audit-card overflow-hidden" : undefined}>
        <CardContent className={compact ? "space-y-2 p-5" : "space-y-1"}>
          <div className="text-xs font-medium uppercase text-slate-500">BE-STHGT calibration</div>
          <div className={compact ? "text-3xl font-semibold text-slate-950" : "text-xl font-semibold text-slate-950"}>
            {mae !== undefined ? formatNumber(mae, 2) : "-"}
          </div>
          <div className="text-xs text-slate-500">MAE PFDI from the deep model calibration head</div>
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
      <CardContent className="grid gap-3 lg:grid-cols-3">
        {sources.map(([source, payload]) => (
          <div key={source} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-slate-950">{source.replaceAll("_", " ")}</div>
                <div className="mt-1 text-xs text-slate-500">
                  {Object.keys(asRecord(payload)).length || "No"} reported fields
                </div>
              </div>
              <Badge variant="secondary">Loaded</Badge>
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm">
              {(["precision_at_10", "ndcg_at_10", "mae_pfdi", "wape_count"] as MetricKey[]).map((key) => {
                const value = metricValue(payload, key);
                return (
                  <div key={key} className="rounded-md bg-slate-50 p-2">
                    <div className="text-[11px] uppercase text-slate-500">{key.replaceAll("_", " ")}</div>
                    <div className="mt-1 font-semibold text-slate-950">
                      {value === undefined ? "—" : formatNumber(value, key === "mae_pfdi" ? 2 : 3)}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function AuditModeMetrics({ rows, metrics }: { rows: ComparisonRow[]; metrics: Record<string, unknown> }) {
  const hasMetrics = Object.keys(metrics).length > 0;
  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full bg-slate-950 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-white">
              <CheckCircle2 className="h-3.5 w-3.5" />
              CurbFlow model stack
            </div>
            <h2 className="mt-3 text-xl font-semibold text-slate-950">Our model values first. Benchmarks below.</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
              The headline cards show CurbFlow's planner stack: bias-aware ranking plus BE-STHGT calibration. The graph
              below compares it with simpler baselines and traditional boosted-tree rankers when those benchmark metrics
              have been generated.
            </p>
          </div>
          <Badge variant={hasMetrics ? "success" : "secondary"}>{hasMetrics ? "Metrics loaded" : "Pending metrics"}</Badge>
        </div>
        {!hasMetrics ? (
          <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600">
            No model metrics are available yet. Run deep training, ranker training, prediction, and seed the DuckDB app database.
          </div>
        ) : (
          <div className="space-y-4">
            <SummaryCards rows={rows} compact />
            <div className="rounded-lg border border-blue-100 bg-blue-50 p-4 text-sm leading-6 text-blue-950">
              Read this as operational ranking strength. CurbFlow still shows explanations, blindspot caveats, and
              resource constraints because the dataset is enforcement visibility evidence, not complete ground truth.
            </div>
          </div>
        )}
      </div>

      {hasMetrics ? <RankingComparisonGraph rows={rows} /> : null}

      <div className="grid gap-3 lg:grid-cols-3">
        <Card className="curbflow-audit-card">
          <CardContent className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
              <Target className="h-4 w-4 text-blue-700" />
              Model stack
            </div>
            <p className="text-sm leading-6 text-slate-600">
              CurbFlow combines BE-STHGT latent risk, a feature-rich LightGBM ranker, and rule blindspot signals to
              rank station-window-zone actions.
            </p>
          </CardContent>
        </Card>
        <Card className="curbflow-audit-card">
          <CardContent className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
              <EyeOff className="h-4 w-4 text-blue-700" />
              Handles sparse evidence
            </div>
            <p className="text-sm leading-6 text-slate-600">
              Evening blindspot outputs are audit recommendations, not validated evening predictions.
            </p>
          </CardContent>
        </Card>
        <Card className="curbflow-audit-card">
          <CardContent className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
              <AlertTriangle className="h-4 w-4 text-amber-700" />
              Does not claim
            </div>
            <p className="text-sm leading-6 text-slate-600">
              PFDI is a proxy for parking-induced flow disruption, not measured speed loss or measured congestion.
            </p>
          </CardContent>
        </Card>
      </div>

      <details className="group rounded-2xl border border-slate-200 bg-white shadow-sm">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-4 text-sm font-semibold text-slate-950">
          View benchmark metric table
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 group-open:bg-slate-950 group-open:text-white">
            Optional
          </span>
        </summary>
        <div className="border-t border-slate-100 p-4">
          <ModelComparison rows={rows} />
        </div>
      </details>
    </div>
  );
}

export function MetricsPanel({
  metrics = {},
  mode = "full",
}: {
  metrics?: Record<string, unknown>;
  mode?: "full" | "audit";
}) {
  const rows = buildRows(metrics);
  const hasMetrics = Object.keys(metrics).length > 0;
  if (mode === "audit") {
    return <AuditModeMetrics rows={rows} metrics={metrics} />;
  }
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
