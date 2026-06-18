"use client";

import { create } from "zustand";

export type PlannerMode = "conservative" | "balanced" | "discovery";

type AppState = {
  selectedStation?: string;
  selectedWindow?: string;
  selectedZoneId?: string;
  plannerMode: PlannerMode;
  setSelectedStation: (station?: string) => void;
  setSelectedWindow: (window?: string) => void;
  setSelectedZoneId: (zoneId?: string) => void;
  setPlannerMode: (mode: PlannerMode) => void;
};

export const useCurbFlowStore = create<AppState>((set) => ({
  selectedStation: undefined,
  selectedWindow: undefined,
  selectedZoneId: undefined,
  plannerMode: "balanced",
  setSelectedStation: (station) => set({ selectedStation: station }),
  setSelectedWindow: (window) => set({ selectedWindow: window }),
  setSelectedZoneId: (zoneId) => set({ selectedZoneId: zoneId }),
  setPlannerMode: (mode) => set({ plannerMode: mode }),
}));
