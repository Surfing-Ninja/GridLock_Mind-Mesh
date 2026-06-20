"use client";

import { useQuery } from "@tanstack/react-query";

import { MetricsPanel } from "@/components/metrics-panel";
import { getModelMetrics } from "@/lib/api";

export default function MetricsPage() {
  const metrics = useQuery({ queryKey: ["model-metrics"], queryFn: getModelMetrics });
  return <MetricsPanel metrics={metrics.data?.metrics} />;
}
