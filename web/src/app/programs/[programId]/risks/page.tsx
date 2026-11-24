import type { Metadata } from "next";

import { PageTitle } from "@/components/typography";
import {
  evaluationInstant,
  getControls,
  getParties,
  getProgram,
  getProgramSummary,
  getRisks,
} from "@/lib/data";
import { isoDate } from "@/lib/format";

import { RiskCrudDialog } from "./risk-crud";
import { RisksView, type RiskRow } from "./risks-table";

export const metadata: Metadata = { title: "Risks" };

export default async function RisksPage({
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

  const program = await getProgram(programId);
  const [summary, risks, controls, parties] = await Promise.all([
    getProgramSummary(programId, instant),
    getRisks(program.system_ref),
    getControls(),
    getParties(),
  ]);

  const controlById = new Map(controls.map((c) => [c.id, c]));

  const rows: RiskRow[] = risks.map((r) => ({
    id: r.id,
    modified: r.modified,
    name: r.name ?? r.id,
    statement: r.statement,
    likelihood: r.likelihood ?? 0,
    impact: r.impact ?? 0,
    residualLikelihood: r.residual_likelihood,
    residualImpact: r.residual_impact,
    treatment: r.treatment,
    status: r.status,
    ownerId: r.owner_ref,
    owner: r.owner_ref ? (parties.get(r.owner_ref)?.name ?? r.owner_ref) : "—",
    controls: (r.control_refs ?? []).map((cid) => ({
      id: cid,
      displayId: controlById.get(cid)?.display_id ?? cid,
    })),
    milestones: (r.milestones ?? []).map((m) => ({
      name: m.name,
      due: m.due,
      completed: m.done,
    })),
  }));

  const partyOptions = [...parties.values()].map((p) => ({ id: p.id, label: p.name ?? p.id }));
  const controlOptions = controls.map((c) => ({ id: c.id, label: `${c.display_id ?? c.id} · ${c.name ?? ""}`.trim() }));

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageTitle
        eyebrow={program.name}
        title="Risks"
        aside={
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-xs font-medium text-muted-foreground">
              {rows.length} risks · at <span className="text-foreground">{isoDate(summary.at)}</span>
            </p>
            <RiskCrudDialog systemId={program.system_ref} parties={partyOptions} controls={controlOptions} />
          </div>
        }
      />

      <RisksView
        rows={rows}
        systemId={program.system_ref}
        parties={partyOptions}
        controls={controlOptions}
        programId={programId}
        at={atParam}
      />
    </div>
  );
}
