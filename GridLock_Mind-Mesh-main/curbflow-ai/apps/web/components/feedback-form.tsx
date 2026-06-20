"use client";

import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, MessageSquarePlus } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { PlannerRecommendation } from "@/lib/api";
import { submitFeedback } from "@/lib/api";

type FeedbackFormProps = {
  recommendation: PlannerRecommendation;
};

function numberValue(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function FeedbackForm({ recommendation }: FeedbackFormProps) {
  const [open, setOpen] = useState(false);
  const [actionTaken, setActionTaken] = useState(recommendation.action);
  const [officersDeployed, setOfficersDeployed] = useState(String(recommendation.officers_required ?? 0));
  const [towUnitsUsed, setTowUnitsUsed] = useState(String(recommendation.tow_units_required ?? 0));
  const [vehiclesFound, setVehiclesFound] = useState("0");
  const [vehiclesRemoved, setVehiclesRemoved] = useState("0");
  const [vehiclesTowed, setVehiclesTowed] = useState("0");
  const [roadCleared, setRoadCleared] = useState(false);
  const [approxQueueLengthM, setApproxQueueLengthM] = useState("");
  const [notes, setNotes] = useState("");

  const feedback = useMutation({
    mutationFn: submitFeedback,
  });

  function submit() {
    if (!recommendation.window_start) return;
    feedback.mutate({
      zone_id: recommendation.zone_id,
      window_start: recommendation.window_start,
      police_station: recommendation.police_station ?? undefined,
      action_taken: actionTaken,
      officers_deployed: numberValue(officersDeployed),
      tow_units_used: numberValue(towUnitsUsed),
      vehicles_found: numberValue(vehiclesFound),
      vehicles_removed: numberValue(vehiclesRemoved),
      vehicles_towed: numberValue(vehiclesTowed),
      road_cleared: roadCleared,
      approx_queue_length_m: approxQueueLengthM ? numberValue(approxQueueLengthM) : null,
      notes: notes || undefined,
    });
  }

  if (!open) {
    return (
      <Button type="button" variant="secondary" className="gap-2" onClick={() => setOpen(true)}>
        <MessageSquarePlus className="h-4 w-4" />
        Feedback
      </Button>
    );
  }

  return (
    <div className="min-w-[360px] space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
      <div className="text-sm font-medium text-slate-950">Deployment feedback</div>
      <p className="text-xs text-slate-600">
        The historical dataset has no outcome columns. This adds the missing feedback layer for future learning.
      </p>
      <div className="grid gap-2 md:grid-cols-2">
        <label className="space-y-1">
          <span className="text-xs font-medium uppercase text-slate-500">Action taken</span>
          <Input value={actionTaken} onChange={(event) => setActionTaken(event.target.value)} />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium uppercase text-slate-500">Officers</span>
          <Input type="number" min={0} value={officersDeployed} onChange={(event) => setOfficersDeployed(event.target.value)} />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium uppercase text-slate-500">Tow units</span>
          <Input type="number" min={0} value={towUnitsUsed} onChange={(event) => setTowUnitsUsed(event.target.value)} />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium uppercase text-slate-500">Vehicles found</span>
          <Input type="number" min={0} value={vehiclesFound} onChange={(event) => setVehiclesFound(event.target.value)} />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium uppercase text-slate-500">Removed</span>
          <Input type="number" min={0} value={vehiclesRemoved} onChange={(event) => setVehiclesRemoved(event.target.value)} />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium uppercase text-slate-500">Towed</span>
          <Input type="number" min={0} value={vehiclesTowed} onChange={(event) => setVehiclesTowed(event.target.value)} />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium uppercase text-slate-500">Queue length m</span>
          <Input
            type="number"
            min={0}
            value={approxQueueLengthM}
            onChange={(event) => setApproxQueueLengthM(event.target.value)}
            placeholder="Optional"
          />
        </label>
        <label className="flex items-center gap-2 pt-6 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={roadCleared}
            onChange={(event) => setRoadCleared(event.target.checked)}
            className="h-4 w-4 rounded border-slate-300"
          />
          Road cleared
        </label>
      </div>
      <label className="space-y-1">
        <span className="text-xs font-medium uppercase text-slate-500">Notes</span>
        <textarea
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          className="min-h-20 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-slate-400"
          placeholder="Optional field observation"
        />
      </label>
      <div className="flex items-center gap-2">
        <Button type="button" onClick={submit} disabled={feedback.isPending || !recommendation.window_start}>
          {feedback.isPending ? "Saving" : "Store feedback"}
        </Button>
        <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
          Close
        </Button>
        {feedback.isSuccess ? (
          <span className="inline-flex items-center gap-1 text-sm font-medium text-emerald-700">
            <CheckCircle2 className="h-4 w-4" />
            Feedback saved
          </span>
        ) : null}
        {feedback.error ? <span className="text-sm text-red-700">{feedback.error.message}</span> : null}
      </div>
    </div>
  );
}
