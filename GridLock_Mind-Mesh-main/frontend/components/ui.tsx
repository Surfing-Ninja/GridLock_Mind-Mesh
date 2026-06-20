import { type HTMLAttributes, type ButtonHTMLAttributes } from "react";
import { twMerge } from "tailwind-merge";
import clsx from "clsx";

export function cn(...values: Array<string | false | null | undefined>) {
  return twMerge(clsx(values));
}

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-lg border border-border bg-panel p-4 shadow-sm", className)} {...props} />;
}

export function Button({ className, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={cn(
        "inline-flex h-9 items-center justify-center rounded-md bg-primary px-3 text-sm font-medium text-white transition hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-60",
        className
      )}
      {...props}
    />
  );
}

export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn("inline-flex rounded-md bg-muted px-2 py-1 text-xs font-medium", className)} {...props} />;
}

export function Metric({ label, value, tone }: { label: string; value: string; tone?: "risk" | "blind" | "good" }) {
  return (
    <Card>
      <div className="text-xs font-medium uppercase tracking-normal text-slate-500">{label}</div>
      <div className={cn("mt-2 text-2xl font-semibold", tone === "risk" && "text-risk", tone === "blind" && "text-blind", tone === "good" && "text-accent")}>
        {value}
      </div>
    </Card>
  );
}
