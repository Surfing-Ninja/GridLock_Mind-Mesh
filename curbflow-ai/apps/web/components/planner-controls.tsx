"use client";

import type { PlannerMode } from "@/lib/store";
import type { DemoPreset } from "@/lib/demoPresets";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowRight, CheckCircle2, Clock3, Moon, Play, Scale, Sun } from "lucide-react";
import Link from "next/link";

type PlannerControlsProps = {
  windowStart: string;
  station: string;
  officers: number;
  towUnits: number;
  mode: PlannerMode;
  demoPresets?: DemoPreset[];
  activeDemoId?: string;
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
  activeDemoId,
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
  const presetMeta = (id: string) => {
    if (id === "morning_known_hotspot") {
      return {
        icon: Sun,
        label: "Observed hotspot",
        className: "border-red-200 bg-red-50 text-red-950",
        badge: "bg-red-700 text-white",
      };
    }
    if (id === "evening_blindspot") {
      return {
        icon: Moon,
        label: "Blindspot audit",
        className: "border-blue-200 bg-blue-50 text-blue-950",
        badge: "bg-blue-700 text-white",
      };
    }
    return {
      icon: Scale,
      label: "Balanced resources",
      className: "border-emerald-200 bg-emerald-50 text-emerald-950",
      badge: "bg-emerald-700 text-white",
    };
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
                  {isLimitedHistoricalWindow(option) ? `Limited data · ${option}` : option}
                </option>
              ))}
            </Select>
            {isLimitedHistoricalWindow(windowStart) ? (
              <div className="rounded-md border border-amber-300 bg-amber-50 px-2 py-1.5 text-xs font-medium text-amber-950">
                Limited historical data for this window. See{" "}
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
        <div className="grid gap-3 lg:grid-cols-3">
          {demoPresets.map((preset) => (
            <button
              key={preset.id}
              type="button"
              className={`rounded-xl border p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md ${
                presetMeta(preset.id).className
              } ${activeDemoId === preset.id ? "ring-2 ring-slate-950/20" : ""}`}
              onClick={() => onDemoPreset(preset)}
            >
              {(() => {
                const meta = presetMeta(preset.id);
                const Icon = meta.icon;
                return (
                  <>
                    <div className="mb-3 flex items-start justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <Icon className="h-5 w-5" />
                        <span className="text-sm font-semibold">{preset.label}</span>
                      </div>
                      <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold uppercase ${meta.badge}`}>
                        {activeDemoId === preset.id ? "Loaded" : meta.label}
                      </span>
                    </div>
                    <div className="text-lg font-semibold leading-snug">{preset.buttonLabel.replace("Load ", "")}</div>
                    <p className="mt-2 min-h-12 text-sm leading-6 opacity-85">{preset.purpose}</p>
                    <div className="mt-3 flex flex-wrap items-center gap-2 text-xs font-medium">
                      <span className="inline-flex items-center gap-1 rounded-full bg-white/75 px-2 py-1">
                        <Clock3 className="h-3.5 w-3.5" />
                        {preset.windowStart.replace("T", " ").slice(0, 16)}
                      </span>
                      <span className="rounded-full bg-white/75 px-2 py-1">{preset.officers} officers</span>
                      <span className="rounded-full bg-white/75 px-2 py-1">{preset.towUnits} tow</span>
                    </div>
                    <div className="mt-4 flex items-center justify-between text-sm font-semibold">
                      <span>{activeDemoId === preset.id ? "Planner loaded" : "Load and run plan"}</span>
                      {activeDemoId === preset.id ? (
                        <CheckCircle2 className="h-4 w-4" />
                      ) : (
                        <ArrowRight className="h-4 w-4" />
                      )}
                    </div>
                  </>
                );
              })()}
            </button>
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
