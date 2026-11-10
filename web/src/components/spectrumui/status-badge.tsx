/**
 * Adapted from Spectrum UI's `status-badge` (Apache-2.0,
 * https://ui.spectrumhq.in/docs/status-badge). The upstream item is a fixed
 * demo of seven statuses; this keeps its pill (inset ring, leading icon) and
 * takes the tone and icon as props so callers map their own states onto it.
 */
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

export type StatusTone = "met" | "gap" | "waived" | "neutral" | "contribution";

const tones: Record<StatusTone, string> = {
  met: "bg-met-soft text-met-ink ring-met/30",
  gap: "bg-gap-soft text-gap-ink ring-gap/30",
  waived: "bg-waived-soft text-waived-ink ring-waived/40",
  neutral: "bg-oos-soft text-oos-ink ring-oos/60",
  contribution: "bg-contribution-soft text-contribution-ink ring-contribution/30",
};

export function StatusBadge({
  tone,
  icon: Icon,
  spin = false,
  className,
  children,
}: {
  tone: StatusTone;
  icon?: LucideIcon;
  spin?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex select-none items-center gap-1 rounded-full px-2 py-1 text-xs font-medium leading-none whitespace-nowrap ring-1 ring-inset",
        tones[tone],
        className,
      )}
    >
      {Icon && (
        <Icon
          className={cn("size-3 shrink-0", spin && "animate-spin [animation-duration:3s] motion-reduce:animate-none")}
          strokeWidth={2.25}
          aria-hidden="true"
        />
      )}
      {children}
    </span>
  );
}
