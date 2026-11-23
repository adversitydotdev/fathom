import { cn } from "cn";

import { CountUp } from "@/components/motion";

/** Small muted label above a title or value. */
export function Eyebrow({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("text-xs leading-none font-medium text-muted-foreground", className)}>{children}</div>;
}

/** Page title with an optional breadcrumb line above and supporting content below. */
export function PageTitle({
  eyebrow,
  title,
  aside,
  children,
}: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  aside?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      {eyebrow && <Eyebrow className="font-normal">{eyebrow}</Eyebrow>}
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <h1 className="text-2xl leading-tight font-semibold tracking-tight">{title}</h1>
        {aside}
      </div>
      {children}
    </div>
  );
}

const statTone = { met: "text-met-ink", gap: "text-gap-ink", waived: "text-waived-ink" } as const;

/** A labelled count, used in the stat row at the top of list pages. */
export function StatCard({ label, value, tone }: { label: string; value: number; tone?: keyof typeof statTone }) {
  return (
    <div className="flex flex-col gap-2 rounded-xl border bg-card px-4 py-3.5 shadow-xs">
      <Eyebrow>{label}</Eyebrow>
      <CountUp value={value} className={cn("text-2xl font-semibold tabular-nums", value > 0 && tone && statTone[tone])} />
    </div>
  );
}
