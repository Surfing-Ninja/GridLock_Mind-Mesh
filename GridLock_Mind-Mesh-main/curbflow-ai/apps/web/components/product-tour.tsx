"use client";

import { ArrowRight, X } from "lucide-react";
import { useState } from "react";

// Exact 5 steps from the product spec
const STEPS = [
  {
    icon: "🗺️",
    title: "This map shows where illegal parking is concentrated",
    body: "Darker red zones have the most violations. Click any zone on the map to see its full morning brief — PFDI score, coverage gap, and recommended action.",
    hint: "Darker = more violations",
  },
  {
    icon: "⏱️",
    title: "Drag the slider to see how enforcement coverage changes through the day",
    body: "The timeline at the bottom animates the map by hour. Zones light up when they match peak activity. Watch how enforcement collapses at 3 PM — that is the evening blindspot.",
    hint: "Scrub the bottom timeline",
  },
  {
    icon: "📋",
    title: "Click any zone to see its morning brief",
    body: "Every zone shows its PFDI score, patrol coverage gap, and the exact action recommended — towing support, beat patrol, or mobile camera. The before/after panel shows estimated congestion reduction.",
    hint: "Click any map zone or list item",
  },
  {
    icon: "👁️",
    title: "The blindspot panel shows where your officers are not going",
    body: "Go to Evening Blindspots in the sidebar. Purple zones have high violation potential but near-zero enforcement visibility. Zero challans here means zero coverage — not zero risk.",
    hint: "Sidebar → Evening Blindspots",
  },
  {
    icon: "📌",
    title: "Use the morning brief to plan tomorrow's deployment",
    body: "Go to Enforcement Planner. Enter available officers and tow units, choose a mode — Conservative (exploit known hotspots), Balanced, or Discovery (audit blindspots) — and get a ranked deployment plan.",
    hint: "Sidebar → Planner",
  },
];

export function ProductTour({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(0);
  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="relative w-full max-w-md rounded-2xl bg-white p-7 shadow-2xl">
        {/* Close */}
        <button
          onClick={onClose}
          className="absolute right-4 top-4 rounded-full p-1.5 text-[#9b9b9b] transition-colors hover:bg-[#f0f0ec] hover:text-[#1c1c1e]"
          aria-label="Close tour"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Progress */}
        <div className="mb-5 flex gap-1.5">
          {STEPS.map((_, i) => (
            <button
              key={i}
              onClick={() => setStep(i)}
              className={`h-1 flex-1 rounded-full transition-colors ${i <= step ? "bg-[#1c1c1e]" : "bg-[#e8e8e4]"}`}
              aria-label={`Step ${i + 1}`}
            />
          ))}
        </div>

        {/* Content */}
        <div className="mb-2 text-4xl">{current.icon}</div>
        <div className="mb-1 text-[9px] font-black uppercase tracking-widest text-[#9b9b9b]">
          Step {step + 1} of {STEPS.length}
        </div>
        <h3 className="mb-2 text-[1.05rem] font-bold leading-snug text-[#1c1c1e]">
          {current.title}
        </h3>
        <p className="mb-3 text-sm leading-relaxed text-[#6b6b6b]">{current.body}</p>
        <div className="mb-6 inline-flex items-center gap-1.5 rounded-full bg-blue-50 px-3 py-1 text-[10px] font-semibold text-blue-700">
          💡 {current.hint}
        </div>

        {/* Nav */}
        <div className="flex items-center justify-between gap-3">
          {step > 0 ? (
            <button
              onClick={() => setStep((s) => s - 1)}
              className="rounded-xl border border-[#e8e8e4] px-4 py-2 text-sm text-[#6b6b6b] transition-colors hover:bg-[#f8f8f5]"
            >
              Back
            </button>
          ) : (
            <div />
          )}
          <button
            onClick={() => (isLast ? onClose() : setStep((s) => s + 1))}
            className="flex items-center gap-1.5 rounded-xl bg-[#1c1c1e] px-5 py-2 text-sm font-bold text-white transition-opacity hover:opacity-80"
          >
            {isLast ? "Done" : "Next"}
            {!isLast && <ArrowRight className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>
    </div>
  );
}
