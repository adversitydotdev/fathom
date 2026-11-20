import type { Metadata } from "next";
import Link from "next/link";
import { CircleCheck, CircleX } from "lucide-react";

import { StatusBadge } from "@/components/spectrumui/status-badge";
import { Eyebrow, PageTitle } from "@/components/typography";
import {
  evaluationInstant,
  getControls,
  getFindings,
  getImplementations,
  getProgram,
  getProgramSummary,
} from "@/lib/data";
import { isoDate, slug } from "@/lib/format";

export const metadata: Metadata = { title: "Findings" };

export default async function FindingsPage({
  params,
  searchParams,
}: {
  params: Promise<{ programId: string }>;
  searchParams: Promise<{ at?: string }>;
}) {
  const { programId } = await params;
  const { at } = await searchParams;
  const atParam = typeof at === "string" ? at : undefined;
  const instant = evaluationInstant(atParam);
  const q = atParam ? `?at=${atParam}` : "";

  const program = await getProgram(programId);
  const [summary, findings, impls, controls] = await Promise.all([
    getProgramSummary(programId, instant),
    getFindings(program.system_ref),
    getImplementations(program.system_ref),
    getControls(),
  ]);

  const implById = new Map(impls.map((i) => [i.id, i]));
  const controlById = new Map(controls.map((c) => [c.id, c]));

  const rows = findings.map((f) => {
    const impl = f.implementation_ref ? implById.get(f.implementation_ref) : undefined;
    const ctrl = impl?.control_ref ? controlById.get(impl.control_ref) : undefined;
    return {
      id: f.id,
      name: f.name,
      determination: f.determination,
      observed: f.observed,
      objectiveRef: f.objective_ref,
      narrative: f.narrative,
      controlId: ctrl?.id,
      controlDisplayId: ctrl?.display_id,
      controlName: ctrl?.name,
    };
  });

  const notSatisfied = rows.filter((r) => r.determination === "not-satisfied").length;
  const satisfied = rows.filter((r) => r.determination === "satisfied").length;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageTitle
        eyebrow={program.name}
        title="Findings"
        aside={
          <p className="font-mono text-[11px] tracking-[0.12em] text-muted-foreground uppercase">
            {rows.length} {rows.length === 1 ? "finding" : "findings"} · at{" "}
            <span className="text-foreground">{isoDate(summary.at)}</span>
          </p>
        }
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatCard label="Total findings" value={rows.length} />
        <StatCard label="Not satisfied" value={notSatisfied} tone={notSatisfied > 0 ? "gap" : undefined} />
        <StatCard label="Satisfied" value={satisfied} tone={satisfied > 0 ? "met" : undefined} />
      </div>

      {rows.length === 0 ? (
        <div className="rounded-2xl border bg-card px-6 py-10 text-center text-sm text-muted-foreground">
          No assessment findings recorded for this system.
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {rows.map((r) => (
            <article key={r.id} className="flex flex-col gap-3 rounded-2xl border bg-card p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex flex-col gap-1">
                  <h2 className="text-base font-medium">{r.name}</h2>
                  {r.narrative && <p className="text-sm text-muted-foreground">{r.narrative}</p>}
                </div>
                {r.determination === "not-satisfied" ? (
                  <StatusBadge tone="gap" icon={CircleX}>
                    not satisfied
                  </StatusBadge>
                ) : (
                  <StatusBadge tone="met" icon={CircleCheck}>
                    satisfied
                  </StatusBadge>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-x-6 gap-y-1 border-t pt-3 font-mono text-xs text-muted-foreground">
                <span>
                  Objective: <span className="text-foreground">{slug(r.objectiveRef)}</span>
                </span>
                <span>
                  Observed: <span className="text-foreground">{isoDate(r.observed)}</span>
                </span>
                {r.controlId && (
                  <span>
                    Control:{" "}
                    <Link
                      href={`/programs/${programId}/controls/${r.controlId}${q}`}
                      className="text-foreground hover:underline"
                    >
                      {r.controlDisplayId} · {r.controlName}
                    </Link>
                  </span>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, tone }: { label: string; value: number; tone?: "met" | "gap" }) {
  const cls = tone === "gap" ? "text-gap-ink" : tone === "met" ? "text-met-ink" : "";
  return (
    <div className="flex flex-col gap-2 rounded-2xl border bg-card px-4 py-4">
      <Eyebrow>{label}</Eyebrow>
      <span className={`text-3xl font-medium tabular-nums ${cls}`}>{value}</span>
    </div>
  );
}
