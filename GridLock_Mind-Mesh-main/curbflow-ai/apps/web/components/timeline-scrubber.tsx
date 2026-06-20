"use client";

import { Pause, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";

const SEGMENT_COLORS = Array.from({ length: 24 }, (_, h) => {
  if (h >= 7 && h < 15) return "#f59e0b";   // amber — morning enforcement window
  if (h >= 15 && h < 21) return "#7c3aed";  // violet — evening blindspot zone
  return "#94a3b8";                           // slate — off-peak
});

function hourLabel(h: number): string {
  if (h === 0) return "12AM";
  if (h === 12) return "12PM";
  return h < 12 ? `${h}AM` : `${h - 12}PM`;
}

function bandLabel(h: number): string {
  if (h >= 7 && h < 15) return "Morning enforcement window";
  if (h >= 15 && h < 21) return "Evening blindspot zone";
  return "Off-peak hours";
}

function bandStyle(h: number): { bg: string; text: string } {
  if (h >= 7 && h < 15)  return { bg: "#fef3c7", text: "#92400e" };
  if (h >= 15 && h < 21) return { bg: "#ede9fe", text: "#5b21b6" };
  return { bg: "#f1f5f9", text: "#64748b" };
}

export function TimelineScrubber({
  value,
  onChange,
}: {
  value: number;
  onChange: (hour: number) => void;
}) {
  const [playing, setPlaying] = useState(false);
  const valueRef = useRef(value);
  useEffect(() => { valueRef.current = value; }, [value]);

  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      const next = (valueRef.current + 1) % 24;
      onChange(next);
    }, 550);
    return () => clearInterval(id);
  }, [playing, onChange]);

  const band = bandStyle(value);
  const display = hourLabel(value);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setPlaying((p) => !p)}
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#1c1c1e] text-white transition-opacity hover:opacity-75"
            aria-label={playing ? "Pause timeline" : "Play timeline"}
          >
            {playing ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3 translate-x-px" />}
          </button>
          <span className="text-sm font-semibold text-[#1c1c1e] tabular-nums">{display}</span>
        </div>
        <span
          className="rounded-full px-2.5 py-0.5 text-[10px] font-semibold"
          style={{ background: band.bg, color: band.text }}
        >
          {bandLabel(value)}
        </span>
      </div>

      {/* Track */}
      <div className="relative">
        <div className="flex h-2 w-full overflow-hidden rounded-full">
          {SEGMENT_COLORS.map((color, i) => (
            <div
              key={i}
              className="flex-1 transition-opacity duration-150"
              style={{ background: color, opacity: i === value ? 1 : 0.22 }}
            />
          ))}
        </div>
        <input
          type="range"
          min={0}
          max={23}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
          aria-label="Timeline hour"
        />
      </div>

      {/* Tick labels */}
      <div className="flex justify-between text-[9px] font-medium text-[#9b9b9b]">
        <span>12AM</span>
        <span className="text-amber-600">6AM</span>
        <span className="text-amber-700 font-semibold">Noon</span>
        <span className="text-violet-600">6PM</span>
        <span>11PM</span>
      </div>
    </div>
  );
}
