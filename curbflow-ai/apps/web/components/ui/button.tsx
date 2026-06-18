import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "secondary" | "ghost" | "danger" | "success" | "info" | "purple";
};

export function Button({ className, variant = "default", ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex h-9 items-center justify-center rounded-md px-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 disabled:pointer-events-none disabled:opacity-50",
        variant === "default" && "bg-slate-950 text-white shadow-sm hover:bg-slate-800",
        variant === "secondary" && "bg-white text-slate-950 shadow-sm ring-1 ring-inset ring-slate-200 hover:bg-slate-50",
        variant === "ghost" && "text-slate-700 hover:bg-slate-100",
        variant === "danger" && "bg-red-600 text-white shadow-sm hover:bg-red-700",
        variant === "success" && "bg-emerald-600 text-white shadow-sm hover:bg-emerald-700",
        variant === "info" && "bg-blue-600 text-white shadow-sm hover:bg-blue-700",
        variant === "purple" && "bg-purple-600 text-white shadow-sm hover:bg-purple-700",
        className,
      )}
      {...props}
    />
  );
}
