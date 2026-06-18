"use client";

import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { HourlyAuditRow } from "@/lib/api";

export function HourlyChart({ data = [] }: { data?: HourlyAuditRow[] }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Hour-of-Day Records</CardTitle>
          <p className="mt-1 text-xs text-slate-500">Observed enforcement evidence by IST hour</p>
        </div>
      </CardHeader>
      <CardContent>
        <div className="h-80 min-h-80 min-w-0">
          {mounted ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} margin={{ left: 6, right: 12, top: 8, bottom: 4 }}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="hour" tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} width={48} />
                <Tooltip
                  cursor={{ fill: "#f1f5f9" }}
                  contentStyle={{ borderRadius: 8, borderColor: "#e2e8f0" }}
                />
                <Bar dataKey="record_count" fill="#0f766e" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full rounded-md bg-slate-50" />
          )}
        </div>
      </CardContent>
    </Card>
  );
}
