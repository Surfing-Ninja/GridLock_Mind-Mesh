"use client";

import type { PlannerMode } from "@/lib/store";
import type { DemoPreset } from "@/lib/demoPresets";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Play, Wand2 } from "lucide-react";
import Link from "next/link";

type PlannerControlsProps = {
  windowStart: string;
  station: string;
  officers: number;
  towUnits: number;
  mode: PlannerMode;
  demoPresets?: DemoPreset[];
  stationOptions?: string[];
  windowOptions?: string[];
  onWindowStartChange: (value: string) => void;
  onStationChange: (value: string) => void;
  onOfficersChange: (value: number) => void;
  onTowUnitsChange: (value: number) => void;
  onModeChange: (value: PlannerMode) => void;
  onDemoPreset: (preset: DemoPreset) => void;
  onSubmit: () => void;
  loading?: boolean;
};

function isLimitedHistoricalWindow(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return false;
  const hour = Number(
    new Intl.DateTimeFormat("en-IN", {
      hour: "numeric",
      hour12: false,
      timeZone: "Asia/Kolkata",
    }).format(parsed),
  );
  return hour >= 15 && hour < 20;
}

export function PlannerControls({
  windowStart,
  station,
  officers,
  towUnits,
  mode,
  demoPresets = [],
  stationOptions = [],
  windowOptions = [],
  onWindowStartChange,
  onStationChange,
  onOfficersChange,
  onTowUnitsChange,
  onModeChange,
  onDemoPreset,
  onSubmit,
  loading,
}: PlannerControlsProps) {
  const presetVariant = (id: string) => {
    if (id === "morning_known_hotspot") return "danger" as const;
    if (id === "evening_blindspot") return "purple" as const;
    return "success" as const;
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Resource Inputs</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
          <label className="space-y-1">
            <span className="text-xs font-medium uppercase text-slate-500">Police station</span>
            <Select value={station} onChange={(event) => onStationChange(event.target.value)}>
              <option value="">All stations</option>
              {stationOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </Select>
          </label>
          <label className="space-y-1">
            <span className="text-xs font-medium uppercase text-slate-500">Time window</span>
            <Select
              value={windowStart}
              onChange={(event) => onWindowStartChange(event.target.value)}
              className={isLimitedHistoricalWindow(windowStart) ? "border-amber-300 bg-amber-50" : undefined}
            >
              <option value="">Select window</option>
              {windowOptions.map((option) => (
                <option key={option} value={option}>
                  {isLimitedHistoricalWindow(option) ? `⚠ ${option}` : option}
                </option>
              ))}
            </Select>
            {isLimitedHistoricalWindow(windowStart) ? (
              <div className="rounded-md border border-amber-300 bg-amber-50 px-2 py-1.5 text-xs font-medium text-amber-950">
                ⚠ Limited historical data for this window — see{" "}
                <Link href="/blindspots#evening-blindspot" className="underline underline-offset-2">
                  Blindspot Analysis
                </Link>
              </div>
            ) : null}
          </label>
          <label className="space-y-1">
            <span className="text-xs font-medium uppercase text-slate-500">Available officers</span>
            <Input type="number" min={0} value={officers} onChange={(event) => onOfficersChange(Number(event.target.value))} />
          </label>
          <label className="space-y-1">
            <span className="text-xs font-medium uppercase text-slate-500">Available tow units</span>
            <Input type="number" min={0} value={towUnits} onChange={(event) => onTowUnitsChange(Number(event.target.value))} />
          </label>
          <label className="space-y-1">
            <span className="text-xs font-medium uppercase text-slate-500">Mode</span>
            <Select value={mode} onChange={(event) => onModeChange(event.target.value as PlannerMode)}>
              <option value="conservative">Conservative</option>
              <option value="balanced">Balanced</option>
              <option value="discovery">Discovery</option>
            </Select>
          </label>
          <div className="flex items-end">
            <Button className="flex-1 gap-2" onClick={onSubmit} disabled={loading || !windowStart}>
              <Play className="h-4 w-4" />
              {loading ? "Planning" : "Run"}
            </Button>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {demoPresets.map((preset) => (
            <Button
              key={preset.id}
              type="button"
              variant={presetVariant(preset.id)}
              className="gap-2"
              onClick={() => onDemoPreset(preset)}
            >
              <Wand2 className="h-4 w-4" />
              {preset.buttonLabel}
            </Button>
          ))}
        </div>
        {!windowOptions.length ? (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            No prediction windows are available yet. Run prediction and recommendation artifacts, then seed the app database.
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
