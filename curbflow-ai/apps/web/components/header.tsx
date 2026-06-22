"use client";

import { ChevronLeft, ChevronRight, HelpCircle, RefreshCw, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { type CSSProperties, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const titles: Record<string, string> = {
  "/": "Command Center",
  "/audit": "Evidence Audit",
  "/hotspots": "Observed Hotspots",
  "/blindspots": "Blindspots",
  "/junction-basins": "Junction Basins",
  "/patrol-twin": "Patrol Digital Twin",
  "/patrol-digital-twin": "Patrol Digital Twin",
  "/planner": "Enforcement Planner",
  "/metrics": "Evidence Audit",
};

const mobileLinks = [
  { href: "/", label: "Map" },
  { href: "/audit", label: "Audit" },
  { href: "/hotspots", label: "Hotspots" },
  { href: "/blindspots", label: "Blindspots" },
  { href: "/patrol-twin", label: "Patrol Twin" },
  { href: "/planner", label: "Planner" },
];

type TourStep = {
  selector: string;
  eyebrow: string;
  title: string;
  body: string;
  values?: string[];
  placement?: "left" | "right" | "bottom" | "top";
};

type TourRect = {
  top: number;
  left: number;
  width: number;
  height: number;
};

const TOUR_MARGIN = 16;
const TOUR_GAP = 18;
const TOUR_CARD_MAX_WIDTH = 460;
const TOUR_CARD_MIN_WIDTH = 300;
const TOUR_CARD_ESTIMATED_HEIGHT = 430;

const fallbackTourSteps: TourStep[] = [
  {
    selector: "[data-tour='page-content']",
    eyebrow: "Page tour",
    title: "Read this page as an operational brief.",
    body: "Each CurbFlow page turns police challan evidence into a planning view. Scores are shown with plain-language labels so a user can act without reading model internals.",
    values: [
      "PFDI is a proxy for parking-induced flow disruption.",
      "Coverage gap means enforcement visibility is weak.",
      "Blindspot risk is an audit priority, not proof of a hidden violation.",
    ],
  },
];

const tours: Record<string, TourStep[]> = {
  "/audit": [
    {
      selector: "[data-tour='audit-hero']",
      eyebrow: "Evidence audit",
      title: "Start here before trusting any map.",
      body: "This panel summarizes what the dataset can and cannot prove. It keeps the core warning visible: police challan records measure enforcement visibility, not all illegal parking.",
      values: [
        "Total records tells you the evidence base size.",
        "Actual date range confirms the true Nov 2023-Apr 2024 period.",
        "Null outcome columns are explicitly excluded from model labels.",
      ],
      placement: "bottom",
    },
    {
      selector: "[data-tour='audit-tabs']",
      eyebrow: "Three audit lenses",
      title: "Switch from data quality to model value to station review.",
      body: "The cards are not decorative. They separate the audit workflow: evidence overview, model comparison, and station-level enforcement concentration.",
      values: [
        "Evidence overview explains morning/evening imbalance.",
        "Model value shows ranking strength against baselines.",
        "Station drilldown exposes patrol myopia and evidence quality.",
      ],
      placement: "bottom",
    },
    {
      selector: "[data-tour='audit-hourly-chart']",
      eyebrow: "Visibility bias",
      title: "Morning-heavy data changes how zeroes are interpreted.",
      body: "The hourly chart and evidence readout explain why evening zero-violation windows are treated as low evidence. This is the product's main guardrail against false safety.",
      values: [
        "Morning count versus evening count drives the evening gap ratio.",
        "SCITA readiness indicates evidence capture reliability.",
        "Top-zone concentration shows whether enforcement is too focused.",
      ],
      placement: "right",
    },
    {
      selector: "[data-tour='audit-tab-model']",
      eyebrow: "Model value",
      title: "The model section translates metrics into deployment confidence.",
      body: "This tour step points to the Model value tab. Open it to see Precision@5, NDCG, hotspot AUC, and baseline comparison in judge-friendly language.",
      values: [
        "Precision@5 asks: are the first few recommended zones useful?",
        "NDCG asks: are severe zones ranked above weaker zones?",
        "Hotspot AUC measures hotspot separation, not measured congestion.",
      ],
    },
  ],
  "/hotspots": [
    {
      selector: "[data-tour='hotspots-warning']",
      eyebrow: "Observed hotspots",
      title: "This page is about visible, recorded enforcement evidence.",
      body: "Hotspots are zones where the recorded challan evidence and PFDI proxy are high. It does not say these are the only problem areas.",
      values: [
        "PFDI combines severity, obstruction, critical location, repeat behavior, and evidence confidence.",
        "Hotspot probability estimates next-window hotspot likelihood.",
        "Priority score blends predicted risk for deployment ranking.",
      ],
    },
    {
      selector: "[data-tour='hotspots-kpis']",
      eyebrow: "Top summary",
      title: "Use these cards as the one-line morning brief.",
      body: "Displayed hotspots tells the shortlist size, Top PFDI identifies the strongest disruption proxy, and Top station shows where the first operational review should start.",
    },
    {
      selector: "[data-tour='hotspots-map']",
      eyebrow: "Map layer",
      title: "Red areas are observed trouble spots, not generic heatmap cells.",
      body: "Clicking a zone opens details and zooms the operational story from citywide pattern to station-zone action.",
      values: [
        "Darker red means higher observed risk.",
        "The map keeps area names visible for field understanding.",
        "Zone IDs are grid cells; station names translate them to patrol context.",
      ],
    },
    {
      selector: "[data-tour='hotspots-list']",
      eyebrow: "Hotspot queue",
      title: "The list is the ranked action queue.",
      body: "Each card explains the zone in normal language so the user understands why a technical score became a deployment candidate.",
    },
  ],
  "/blindspots": [
    {
      selector: "[data-tour='blindspots-warning']",
      eyebrow: "Blindspot audit",
      title: "Purple does not mean proven hotspot. It means investigate.",
      body: "A blindspot has high static obstruction potential but weak enforcement visibility. CurbFlow marks it as an audit priority because no challan does not mean no problem.",
    },
    {
      selector: "[data-tour='blindspots-kpis']",
      eyebrow: "Blindspot values",
      title: "Coverage gap is the key value on this page.",
      body: "Coverage gap is 1 minus estimated enforcement visibility. A high gap increases uncertainty and audit priority, but it does not manufacture fake observed violations.",
      values: [
        "Blindspot risk = static potential x coverage gap x peak/evening priors x uncertainty.",
        "Top blindspot risk points to the strongest audit candidate.",
        "Coverage gap explains why the area needs discovery patrols.",
      ],
    },
    {
      selector: "[data-tour='blindspots-hourly-chart']",
      eyebrow: "Evening gap",
      title: "This chart is why evening zeroes are not treated as safe.",
      body: "The hourly volume and last-active station bars show enforcement fading later in the day. The model therefore recommends audit patrols rather than claiming evening predictions are validated.",
      placement: "right",
    },
    {
      selector: "[data-tour='blindspots-map']",
      eyebrow: "Discovery map",
      title: "Use this map to plan exploration.",
      body: "Purple and red zones are where limited officers can gather missing evidence and check whether obstruction risk is real.",
    },
  ],
  "/junction-basins": [
    {
      selector: "[data-tour='junction-explainer']",
      eyebrow: "Hidden junction basins",
      title: "No Junction does not always mean no junction impact.",
      body: "Many records are tagged No Junction even when their coordinates are close to a named junction. CurbFlow assigns those rows to nearby junction basins to reveal spillover near traffic-critical points.",
      values: [
        "hidden_junction_weight decays with distance from the named junction.",
        "junction_basin_pfdi aggregates spillover impact.",
        "spillover count shows how many No Junction rows were recovered into context.",
      ],
    },
    {
      selector: "[data-tour='junction-map']",
      eyebrow: "Spillover layer",
      title: "The map shows junction-adjacent risk, not just named labels.",
      body: "Use this when junction names are messy or missing. It makes nearby obstruction patterns visible without external datasets.",
    },
    {
      selector: "[data-tour='junction-list']",
      eyebrow: "Basin queue",
      title: "The side list is the audit queue for junction spillover.",
      body: "Click a row to inspect the mapped zone and connect the plain-language explanation to the spatial basin.",
    },
  ],
  "/patrol-digital-twin": [
    {
      selector: "[data-tour='patrol-kpis']",
      eyebrow: "Patrol digital twin",
      title: "This page reconstructs aggregate patrol behavior.",
      body: "CurbFlow uses device/user transitions only as aggregate route patterns. It does not expose raw device_id or created_by_id.",
      values: [
        "Patrol-connected zones are where movement was observed.",
        "Nearby uncovered zones are expansion opportunities.",
        "Top route shows the strongest aggregate transition.",
      ],
    },
    {
      selector: "[data-tour='patrol-myopia']",
      eyebrow: "Patrol myopia",
      title: "Myopia measures whether enforcement repeats the same places.",
      body: "A high Patrol Myopia Index means a station's enforcement is concentrated in a few zones or time windows, potentially missing nearby risk.",
      values: [
        "Top 10 zone share measures concentration.",
        "Zone entropy measures spread across zones.",
        "Evening coverage shows whether patrol visibility extends past the morning-heavy period.",
      ],
    },
    {
      selector: "[data-tour='patrol-map']",
      eyebrow: "Route coverage map",
      title: "Blue means seen by patrol patterns; red means nearby but uncovered.",
      body: "This map helps a station expand route coverage by one logical step instead of randomly adding patrols.",
    },
    {
      selector: "[data-tour='patrol-routes']",
      eyebrow: "Transition graph",
      title: "Routes are aggregate patterns, not officer tracking.",
      body: "The route cards summarize zone-to-zone transitions, high-coverage loops, and uncovered opportunities. They are privacy-safe operational features.",
    },
  ],
  "/planner": [
    {
      selector: "[data-tour='planner-brief']",
      eyebrow: "Morning brief",
      title: "This is the operator-friendly entry point.",
      body: "Instead of starting with model scores, the brief asks a normal planning question: station, weekday, and operating slot. It then returns the most relevant historical zones.",
      values: [
        "PFDI score is the disruption proxy.",
        "Repeat vehicles indicate persistence.",
        "Large vehicle share flags higher obstruction potential.",
      ],
    },
    {
      selector: "[data-tour='planner-controls']",
      eyebrow: "Resource inputs",
      title: "These controls turn ranking into a feasible plan.",
      body: "The planner respects officer and towing constraints. Mode changes the exploit/explore mix: Conservative favors known hotspots, Balanced mixes both, Discovery favors under-covered blindspots.",
    },
    {
      selector: "[data-tour='planner-insights']",
      eyebrow: "Smart insights",
      title: "This is the plain-language explanation of the run.",
      body: "After running, CurbFlow describes allocation mix, resource pressure, top action, and expected risk coverage in words rather than leaving the user with a raw table.",
    },
    {
      selector: "[data-tour='planner-map']",
      eyebrow: "Planner map",
      title: "The map focuses on selected station-window recommendations.",
      body: "Recommended zones are colored by action type so a user can see where beat patrols, towing support, evening audits, and evidence audits will go.",
    },
    {
      selector: "[data-tour='planner-table']",
      eyebrow: "Final dispatch table",
      title: "This is the plan to hand to a station team.",
      body: "Each row contains zone, risk score, blindspot score, action, required resources, and reason. Feedback can be stored after deployment for future learning.",
    },
  ],
  "/metrics": [
    {
      selector: "[data-tour='page-content']",
      eyebrow: "Metrics redirect",
      title: "Model metrics now live inside Evidence Audit.",
      body: "This route redirects to the audit page to avoid overwhelming users with a separate technical-only metrics page.",
    },
  ],
};

function stepsFor(pathname: string) {
  return tours[pathname] ?? fallbackTourSteps;
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function viewportSize() {
  if (typeof window === "undefined") return { width: 1200, height: 800 };
  return { width: window.innerWidth, height: window.innerHeight };
}

function getSpotlightRect(selector: string): TourRect | null {
  if (typeof window === "undefined") return null;
  const element = document.querySelector(selector);
  if (!element) return null;
  const rect = element.getBoundingClientRect();
  const rawTop = rect.top - 8;
  const rawLeft = rect.left - 8;
  const rawWidth = Math.min(window.innerWidth - 16, rect.width + 16);
  const rawHeight = Math.min(window.innerHeight - 16, rect.height + 16);
  const width = rawWidth;
  const height = Math.min(rawHeight, Math.min(560, window.innerHeight - 16));
  return {
    top: clamp(rawTop + Math.max(0, (rawHeight - height) / 2), 8, Math.max(8, window.innerHeight - height - 8)),
    left: clamp(rawLeft + Math.max(0, (rawWidth - width) / 2), 8, Math.max(8, window.innerWidth - width - 8)),
    width,
    height,
  };
}

function tourCardStyle(rect: TourRect | null, placement?: TourStep["placement"]): CSSProperties {
  const viewport = viewportSize();
  const maxWidth = Math.max(TOUR_CARD_MIN_WIDTH, viewport.width - TOUR_MARGIN * 2);
  const defaultWidth = Math.min(TOUR_CARD_MAX_WIDTH, maxWidth);
  const cardHeight = Math.min(TOUR_CARD_ESTIMATED_HEIGHT, viewport.height - TOUR_MARGIN * 2);
  const base = (width = defaultWidth): CSSProperties => ({
    position: "fixed",
    width,
    maxWidth: "calc(100vw - 2rem)",
    maxHeight: "calc(100vh - 2rem)",
    overflowY: "auto",
  });

  if (!rect) {
    return {
      ...base(),
      left: clamp((viewport.width - defaultWidth) / 2, TOUR_MARGIN, Math.max(TOUR_MARGIN, viewport.width - defaultWidth - TOUR_MARGIN)),
      top: clamp((viewport.height - cardHeight) / 2, TOUR_MARGIN, Math.max(TOUR_MARGIN, viewport.height - cardHeight - TOUR_MARGIN)),
    };
  }

  const centeredLeft = clamp(
    rect.left + rect.width / 2 - defaultWidth / 2,
    TOUR_MARGIN,
    Math.max(TOUR_MARGIN, viewport.width - defaultWidth - TOUR_MARGIN),
  );
  const sideTop = clamp(
    rect.top + rect.height / 2 - cardHeight / 2,
    TOUR_MARGIN,
    Math.max(TOUR_MARGIN, viewport.height - cardHeight - TOUR_MARGIN),
  );
  const rightSpace = viewport.width - rect.left - rect.width - TOUR_GAP - TOUR_MARGIN;
  const leftSpace = rect.left - TOUR_GAP - TOUR_MARGIN;
  const rightWidth = Math.min(defaultWidth, Math.max(0, rightSpace));
  const leftWidth = Math.min(defaultWidth, Math.max(0, leftSpace));
  const options: Record<NonNullable<TourStep["placement"]>, CSSProperties | null> = {
    bottom:
      rect.top + rect.height + TOUR_GAP + cardHeight <= viewport.height - TOUR_MARGIN
        ? { ...base(), left: centeredLeft, top: rect.top + rect.height + TOUR_GAP }
        : null,
    top:
      rect.top - TOUR_GAP - cardHeight >= TOUR_MARGIN
        ? { ...base(), left: centeredLeft, top: rect.top - TOUR_GAP - cardHeight }
        : null,
    right:
      rightWidth >= TOUR_CARD_MIN_WIDTH
        ? { ...base(rightWidth), left: rect.left + rect.width + TOUR_GAP, top: sideTop }
        : null,
    left:
      leftWidth >= TOUR_CARD_MIN_WIDTH
        ? { ...base(leftWidth), left: rect.left - TOUR_GAP - leftWidth, top: sideTop }
        : null,
  };

  const orderByPlacement: Record<NonNullable<TourStep["placement"]>, Array<NonNullable<TourStep["placement"]>>> = {
    bottom: ["bottom", "right", "left", "top"],
    top: ["top", "right", "left", "bottom"],
    right: ["right", "left", "bottom", "top"],
    left: ["left", "right", "bottom", "top"],
  };
  const order: Array<NonNullable<TourStep["placement"]>> = placement
    ? orderByPlacement[placement]
    : ["right", "left", "bottom", "top"];
  for (const direction of order) {
    if (options[direction]) return options[direction] as CSSProperties;
  }

  return {
    ...base(),
    left: clamp((viewport.width - defaultWidth) / 2, TOUR_MARGIN, Math.max(TOUR_MARGIN, viewport.width - defaultWidth - TOUR_MARGIN)),
    top: clamp((viewport.height - cardHeight) / 2, TOUR_MARGIN, Math.max(TOUR_MARGIN, viewport.height - cardHeight - TOUR_MARGIN)),
  };
}

function TourOverlay({
  steps,
  step,
  setStep,
  onClose,
}: {
  steps: TourStep[];
  step: number;
  setStep: (step: number) => void;
  onClose: () => void;
}) {
  const current = steps[step] ?? steps[0];
  const [mounted, setMounted] = useState(false);
  const [rect, setRect] = useState(() => getSpotlightRect(current.selector));

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    const update = () => setRect(getSpotlightRect(current.selector));
    update();
    const element = document.querySelector(current.selector);
    element?.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
    const timeout = window.setTimeout(update, 260);
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.clearTimeout(timeout);
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [current.selector, step]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowRight") setStep(Math.min(steps.length - 1, step + 1));
      if (event.key === "ArrowLeft") setStep(Math.max(0, step - 1));
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, setStep, step, steps.length]);

  const cardStyle = tourCardStyle(rect, current.placement);
  const viewport = viewportSize();
  const backdropClass = "absolute bg-slate-950/70 backdrop-blur-lg";

  const overlay = (
    <div className="fixed inset-0 z-[90]">
      {rect ? (
        <>
          <div className={backdropClass} style={{ left: 0, top: 0, width: viewport.width, height: rect.top }} onClick={onClose} />
          <div
            className={backdropClass}
            style={{
              left: 0,
              top: rect.top + rect.height,
              width: viewport.width,
              height: Math.max(0, viewport.height - rect.top - rect.height),
            }}
            onClick={onClose}
          />
          <div className={backdropClass} style={{ left: 0, top: rect.top, width: rect.left, height: rect.height }} onClick={onClose} />
          <div
            className={backdropClass}
            style={{
              left: rect.left + rect.width,
              top: rect.top,
              width: Math.max(0, viewport.width - rect.left - rect.width),
              height: rect.height,
            }}
            onClick={onClose}
          />
        </>
      ) : (
        <div className="absolute inset-0 bg-slate-950/70 backdrop-blur-lg" onClick={onClose} />
      )}
      {rect ? (
        <div
          className="curbflow-tour-spotlight pointer-events-none absolute rounded-2xl border-2 border-white/90 bg-transparent shadow-2xl ring-4 ring-blue-500/60"
          style={rect}
        />
      ) : null}
      <div
        className="curbflow-tour-card fixed rounded-xl border border-slate-200 bg-white p-5 shadow-2xl shadow-slate-950/30"
        style={cardStyle}
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="space-y-2">
            <Badge variant="info">
              {current.eyebrow} · Step {step + 1} of {steps.length}
            </Badge>
            <h2 className="text-lg font-semibold text-slate-950">{current.title}</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-950"
            aria-label="Close tour"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <p className="text-sm leading-6 text-slate-600">{current.body}</p>
        {current.values?.length ? (
          <div className="mt-4 space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3">
            {current.values.map((value) => (
              <div key={value} className="flex gap-2 text-sm leading-5 text-slate-700">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-950" />
                <span>{value}</span>
              </div>
            ))}
          </div>
        ) : null}
        <div className="mt-4 flex items-center justify-between gap-3">
          <div className="flex gap-1">
            {steps.map((item, index) => (
              <button
                key={`${item.title}-${index}`}
                type="button"
                onClick={() => setStep(index)}
                className={cn(
                  "h-1.5 rounded-full transition-all",
                  index === step ? "w-7 bg-slate-950" : "w-2 bg-slate-300 hover:bg-slate-500",
                )}
                aria-label={`Go to tour step ${index + 1}`}
              />
            ))}
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0}>
              <ChevronLeft className="mr-1 h-4 w-4" />
              Back
            </Button>
            {step === steps.length - 1 ? (
              <Button onClick={onClose}>Finish</Button>
            ) : (
              <Button onClick={() => setStep(Math.min(steps.length - 1, step + 1))}>
                Next
                <ChevronRight className="ml-1 h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );

  if (!mounted || typeof document === "undefined") return null;
  return createPortal(overlay, document.body);
}

export function Header() {
  const pathname = usePathname();
  const [tourOpen, setTourOpen] = useState(false);
  const [tourStep, setTourStep] = useState(0);
  const tourSteps = useMemo(() => stepsFor(pathname), [pathname]);

  useEffect(() => {
    setTourOpen(false);
    setTourStep(0);
  }, [pathname]);

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-[#fbfbf9]/95 px-3 py-3 shadow-sm backdrop-blur sm:px-4">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0" data-tour="page-title">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-base font-semibold text-slate-950">{titles[pathname] ?? "CurbFlow AI"}</h1>
            <Badge variant="info" className="hidden sm:inline-flex">
              Bias-aware
            </Badge>
          </div>
          <p className="truncate text-xs text-slate-500">No challan is not treated as no problem.</p>
        </div>
        <div className="flex shrink-0 items-center gap-2" data-tour="page-actions">
          <Button
            variant="secondary"
            onClick={() => {
              setTourStep(0);
              setTourOpen(true);
            }}
          >
            <HelpCircle className="mr-2 h-4 w-4" />
            Tour
          </Button>
          <Button variant="secondary" onClick={() => window.location.reload()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
        </div>
      </div>
      <nav className="mt-3 flex gap-2 overflow-x-auto pb-1 lg:hidden">
        {mobileLinks.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "shrink-0 rounded-full px-3 py-1.5 text-xs font-medium text-slate-600 ring-1 ring-inset ring-slate-200",
              (pathname === item.href ||
                (item.href === "/patrol-twin" && pathname === "/patrol-digital-twin")) &&
                "bg-slate-950 text-white ring-slate-950",
            )}
          >
            {item.label}
          </Link>
        ))}
      </nav>
      {tourOpen ? (
        <TourOverlay steps={tourSteps} step={tourStep} setStep={setTourStep} onClose={() => setTourOpen(false)} />
      ) : null}
    </header>
  );
}
