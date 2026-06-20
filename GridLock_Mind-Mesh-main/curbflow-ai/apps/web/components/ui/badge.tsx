import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  variant?: "default" | "secondary" | "warning" | "success" | "danger" | "info" | "purple";
};

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        variant === "default" && "bg-slate-950 text-white",
        variant === "secondary" && "bg-slate-100 text-slate-700 ring-slate-200",
        variant === "warning" && "bg-orange-100 text-orange-800 ring-orange-200",
        variant === "success" && "bg-emerald-100 text-emerald-800 ring-emerald-200",
        variant === "danger" && "bg-red-100 text-red-800 ring-red-200",
        variant === "info" && "bg-blue-100 text-blue-800 ring-blue-200",
        variant === "purple" && "bg-purple-100 text-purple-800 ring-purple-200",
        className,
      )}
      {...props}
    />
  );
}
