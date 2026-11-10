import { Sparkles } from "lucide-react";
import { cn } from "cn";

import type { ControlState, RequirementState } from "@/lib/api/types";

const controlStyle: Record<ControlState, { label: string; pill: string; bar: string }> = {
  met: { label: "met", pill: "bg-met-soft text-met-ink", bar: "bg-met" },
  gap: { label: "gap", pill: "bg-gap-soft text-gap-ink", bar: "bg-gap" },
  waived: { label: "waived", pill: "bg-waived-soft text-waived-ink", bar: "bg-waived" },
  out_of_scope: { label: "out of scope", pill: "bg-oos-soft text-oos-ink", bar: "bg-oos" },
};

const requirementStyle: Record<RequirementState, { label: string; pill: string; bar: string }> = {
  covered: { label: "covered", pill: "bg-met-soft text-met-ink", bar: "bg-met" },
  gap: { label: "gap", pill: "bg-gap-soft text-gap-ink", bar: "bg-gap" },
  contribution: { label: "contribution", pill: "bg-contribution-soft text-contribution-ink", bar: "bg-contribution" },
  unmapped: { label: "unmapped", pill: "bg-oos-soft text-oos-ink", bar: "bg-oos" },
};

export const CONTROL_STATES = Object.keys(controlStyle) as ControlState[];
export const REQUIREMENT_STATES = ["covered", "gap", "contribution", "unmapped"] as RequirementState[];

export function controlStateLabel(state: ControlState) {
  return controlStyle[state].label;
}

function Pill({ className, children }: { className: string; children: React.ReactNode }) {
  return (
    <span className={cn("inline-flex h-5 items-center rounded-full px-2 text-xs font-medium whitespace-nowrap", className)}>
      {children}
    </span>
  );
}

export function ControlStateBadge({ state }: { state: ControlState }) {
  const s = controlStyle[state];
  return <Pill className={s.pill}>{s.label}</Pill>;
}

export function RequirementStateBadge({ state }: { state: RequirementState }) {
  const s = requirementStyle[state];
  return <Pill className={s.pill}>{s.label}</Pill>;
}

export function FailedPill({ children }: { children: React.ReactNode }) {
  return <Pill className="bg-gap-soft text-gap-ink">{children}</Pill>;
}

type Segment = { key: string; value: number; className: string; label: string };

export function SegmentBar({ segments, className }: { segments: Segment[]; className?: string }) {
  const total = segments.reduce((n, s) => n + s.value, 0);
  return (
    <div
      className={cn("flex h-2 gap-0.5 overflow-hidden rounded-full bg-muted", className)}
      role="img"
      aria-label={segments.map((s) => `${s.value} ${s.label}`).join(", ")}
    >
      {total > 0 &&
        segments
          .filter((s) => s.value > 0)
          .map((s) => <div key={s.key} className={s.className} style={{ flexGrow: s.value }} />)}
    </div>
  );
}

export function controlSegments(counts: Record<ControlState, number>): Segment[] {
  return CONTROL_STATES.map((k) => ({ key: k, value: counts[k], className: controlStyle[k].bar, label: controlStyle[k].label }));
}

export function requirementSegments(counts: Record<RequirementState, number>): Segment[] {
  return REQUIREMENT_STATES.map((k) => ({ key: k, value: counts[k], className: requirementStyle[k].bar, label: requirementStyle[k].label }));
}

export function Legend({ kind }: { kind: "control" | "requirement" }) {
  const entries = kind === "control" ? Object.values(controlStyle) : REQUIREMENT_STATES.map((k) => requirementStyle[k]);
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
      {entries.map((e) => (
        <span key={e.label} className="inline-flex items-center gap-1.5">
          <span className={cn("size-2 rounded-full", e.bar)} />
          {e.label}
        </span>
      ))}
    </div>
  );
}

/** RFC 0003 section 8: show which drafts an agent produced. */
export function AgentMark({ label = "Agent draft" }: { label?: string }) {
  return (
    <span className="inline-flex items-center text-agent" title={label}>
      <Sparkles className="size-3.5" aria-hidden />
      <span className="sr-only">{label}</span>
    </span>
  );
}
