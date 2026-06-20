import type { PlannerMode } from "./store";

export type DemoPresetId = "morning_known_hotspot" | "evening_blindspot" | "balanced_planner";

export type DemoPreset = {
  id: DemoPresetId;
  label: string;
  buttonLabel: string;
  windowStart: string;
  policeStation: string;
  zoneId: string;
  mode: PlannerMode;
  officers: number;
  towUnits: number;
  purpose: string;
  selectionReason: string;
  metrics: {
    recordCount?: number | null;
    observedRiskScore?: number | null;
    blindspotRiskScore?: number | null;
    predictedPfdi?: number | null;
    hotspotProbability?: number | null;
    exposure?: number | null;
    coverageGap?: number | null;
    staticPotential?: number | null;
    deploymentPriority?: number | null;
  };
};

export const demoPresets: DemoPreset[] = [
  {
    id: "morning_known_hotspot",
    label: "Morning known hotspot",
    buttonLabel: "Load Morning Hotspot Demo",
    windowStart: "2024-03-20T09:00:00+05:30",
    policeStation: "rajajinagar",
    zoneId: "4826_28040",
    mode: "conservative",
    officers: 8,
    towUnits: 2,
    purpose: "Show an observed high-confidence hotspot from a high-record morning/midday test-period window.",
    selectionReason:
      "Selected from the final 15 percent chronological test period by high observed risk among high-record morning/midday rows.",
    metrics: {
      recordCount: 9,
      observedRiskScore: 94.42239596451525,
      blindspotRiskScore: 9.331397093675891,
      predictedPfdi: 94.2,
      hotspotProbability: 0.91,
      exposure: 0.35631578947368414,
      coverageGap: 0.6436842105263159,
      staticPotential: 0.3820256900942606,
      deploymentPriority: 80.3967137790699,
    },
  },
  {
    id: "evening_blindspot",
    label: "Evening blindspot",
    buttonLabel: "Load Evening Blindspot Demo",
    windowStart: "2024-04-06T18:00:00+05:30",
    policeStation: "city market",
    zoneId: "4810_28050",
    mode: "discovery",
    officers: 8,
    towUnits: 2,
    purpose: "Show low enforcement visibility and high blindspot audit priority in an evening test-period window.",
    selectionReason:
      "Selected from the final 15 percent chronological test period by highest blindspot risk in evening windows.",
    metrics: {
      recordCount: 1,
      observedRiskScore: 38.506336616186644,
      blindspotRiskScore: 38.37605375590796,
      predictedPfdi: 46.437623737409496,
      hotspotProbability: 0.46437623737409495,
      exposure: 0.13421052631578945,
      coverageGap: 0.8657894736842106,
      staticPotential: 0.33166619325752744,
      deploymentPriority: 50.32610560906039,
    },
  },
  {
    id: "balanced_planner",
    label: "Balanced planner",
    buttonLabel: "Load Balanced Planner Demo",
    windowStart: "2024-04-02T09:00:00+05:30",
    policeStation: "malleshwaram",
    zoneId: "4823_28041",
    mode: "balanced",
    officers: 20,
    towUnits: 4,
    purpose: "Show 70/30 exploit/explore allocation with 20 officers and 4 tow units.",
    selectionReason: "Selected station-window with 17 candidate zones and 17 planner recommendations.",
    metrics: {
      recordCount: 11,
      observedRiskScore: 87.04317084797829,
      blindspotRiskScore: 4.619527856557067,
      predictedPfdi: 87.6,
      hotspotProbability: 0.84,
      exposure: 0.6763157894736842,
      coverageGap: 0.3236842105263158,
      staticPotential: 0.4119888404774939,
      deploymentPriority: 67.59115319109318,
    },
  },
];

export const demoPresetById = Object.fromEntries(
  demoPresets.map((preset) => [preset.id, preset]),
) as Record<DemoPresetId, DemoPreset>;
