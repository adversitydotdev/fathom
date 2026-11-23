import {
  CircleCheck,
  CircleDashed,
  CircleDot,
  CircleMinus,
  CirclePause,
  CircleX,
  type LucideIcon,
  Sparkles,
} from "lucide-react";
import { cn } from "cn";

import { StatusBadge, type StatusTone } from "@/components/spectrumui/status-badge";
import type { ControlState, RequirementState } from "@/lib/api/types";

type Style = { label: string; tone: StatusTone; icon: LucideIcon; bar: string };

const controlStyle: Record<ControlState, Style> = {
  met: { label: "met", tone: "met", icon: CircleCheck, bar: "bg-met" },
  gap: { label: "gap", tone: "gap", icon: CircleX, bar: "bg-gap" },
  waived: { label: "waived", tone: "waived", icon: CirclePause, bar: "bg-waived" },
  out_of_scope: { label: "out of scope", tone: "neutral", icon: CircleMinus, bar: "bg-oos" },
};

const requirementStyle: Record<RequirementState, Style> = {
  covered: { label: "covered", tone: "met", icon: CircleCheck, bar: "bg-met" },
  gap: { label: "gap", tone: "gap", icon: CircleX, bar: "bg-gap" },
  contribution: { label: "contribution", tone: "contribution", icon: CircleDot, bar: "bg-contribution" },
  unmapped: { label: "unmapped", tone: "neutral", icon: CircleDashed, bar: "bg-oos" },
};

export const CONTROL_STATES = Object.keys(controlStyle) as ControlState[];
export const REQUIREMENT_STATES = ["covered", "gap", "contribution", "unmapped"] as RequirementState[];

export function controlStateLabel(state: ControlState) {
  return controlStyle[state].label;
}

export function ControlStateBadge({ state }: { state: ControlState }) {
  const s = controlStyle[state];
  return (
    <StatusBadge tone={s.tone} icon={s.icon}>
      {s.label}
    </StatusBadge>
  );
}

export function RequirementStateBadge({ state }: { state: RequirementState }) {
  const s = requirementStyle[state];
  return (
    <StatusBadge tone={s.tone} icon={s.icon}>
      {s.label}
    </StatusBadge>
  );
}

type Segment = { key: string; value: number; className: string; label: string };

export function SegmentBar({ segments, className }: { segments: Segment[]; className?: string }) {
  const total = segments.reduce((n, s) => n + s.value, 0);
  return (
    <div
      className={cn("h-2 overflow-hidden rounded-full bg-muted", className)}
      role="img"
      aria-label={segments.map((s) => `${s.value} ${s.label}`).join(", ")}
    >
      {total > 0 && (
        <div className="motion-grow-x flex h-full gap-0.5">
          {segments
            .filter((s) => s.value > 0)
            .map((s) => (
              <div key={s.key} className={s.className} style={{ flexGrow: s.value }} />
            ))}
        </div>
      )}
    </div>
  );
}

/**
 * A progress ring that draws itself in. `value` is a 0..1 fraction the API's
 * counts already imply; the ring only presents it.
 */
export function Ring({
  value,
  size = 112,
  stroke = 10,
  className,
  children,
}: {
  value: number;
  size?: number;
  stroke?: number;
  className?: string;
  children?: React.ReactNode;
}) {
  const r = (size - stroke) / 2;
  const length = 2 * Math.PI * r;
  const offset = length * (1 - Math.min(1, Math.max(0, value)));
  return (
    <div className={cn("relative shrink-0", className)} style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} className="stroke-muted" />
        {value > 0 && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            strokeWidth={stroke}
            strokeLinecap="round"
            className="motion-draw stroke-met"
            strokeDasharray={length}
            strokeDashoffset={offset}
            style={{ ["--ring-length" as string]: length }}
          />
        )}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">{children}</div>
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
