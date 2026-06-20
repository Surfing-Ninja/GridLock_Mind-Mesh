import type { HTMLAttributes, ReactNode } from "react";
import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type SheetProps = HTMLAttributes<HTMLDivElement> & {
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  children: ReactNode;
};

export function Sheet({ open, className, children, ...props }: SheetProps) {
  if (!open) return null;
  return (
    <div className={cn("fixed inset-0 z-40", className)} {...props}>
      {children}
    </div>
  );
}

export function SheetOverlay({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("absolute inset-0 bg-slate-950/35 backdrop-blur-sm", className)} {...props} />;
}

export function SheetContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "absolute inset-y-0 right-0 w-full max-w-md overflow-y-auto border-l border-slate-200 bg-white p-4 shadow-2xl",
        className,
      )}
      {...props}
    />
  );
}

export function SheetHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mb-4 flex items-start justify-between gap-4", className)} {...props} />;
}

export function SheetTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={cn("text-lg font-semibold text-slate-950", className)} {...props} />;
}

export function SheetDescription({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-sm text-slate-500", className)} {...props} />;
}

export function SheetClose({ onClose }: { onClose: () => void }) {
  return (
    <Button variant="ghost" onClick={onClose} aria-label="Close sheet">
      <X className="h-4 w-4" />
    </Button>
  );
}
