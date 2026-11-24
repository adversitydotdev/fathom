import type { Metadata } from "next";

import { AskAgentButton } from "@/components/agent/assistant-drawer";
import { SegmentBar, requirementSegments } from "@/components/status";
import { PageTitle } from "@/components/typography";
import type { RequirementState } from "@/lib/api/types";
import {
  evaluationInstant,
  getBaseline,
  getControls,
  getFrameworks,
  getMappings,
  getProgram,
  getProgramStatus,
  getRequirements,
} from "@/lib/data";
import { isoDate, percent } from "@/lib/format";

import { RequirementsTable, type RequirementRow } from "./requirements-table";

export const metadata: Metadata = { title: "Requirements" };

export default async function RequirementsPage({
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
  const [baseline, status, frameworks, requirements, controls, mappings] = await Promise.all([
    getBaseline(program.baseline_ref),
    getProgramStatus(programId, instant),
    getFrameworks(),
    getRequirements(),
    getControls(),
    getMappings(),
  ]);

  const fwById = new Map(frameworks.map((f) => [f.id, f]));
  const reqById = new Map(requirements.map((r) => [r.id, r]));
  const ctrlById = new Map(controls.map((c) => [c.id, c]));
  const mappingById = new Map(mappings.map((m) => [m.id, m]));
  const controlStateById = new Map(status.controls.map((c) => [c.control_id, c.state]));

  const rows: RequirementRow[] = status.requirements.map((cov) => {
    const req = reqById.get(cov.requirement_id);
    const fwId = req?.framework_ref ?? "";
    const linked = new Map<string, string>();
    for (const mid of cov.mapping_ids ?? []) {
      const m = mappingById.get(mid);
      if (m?.source_ref.startsWith("control--")) {
        const ctrl = ctrlById.get(m.source_ref);
        linked.set(m.source_ref, ctrl?.display_id ?? m.source_ref);
      }
    }
    const linkedControls = Array.from(linked, ([id, displayId]) => ({ id, displayId }));
    const unmetCount = linkedControls.filter((c) => controlStateById.get(c.id) === "gap").length;
    return {
      id: cov.requirement_id,
      displayId: req?.display_id ?? cov.requirement_id,
      name: req?.name ?? cov.requirement_id,
      frameworkId: fwId,
      frameworkName: fwById.get(fwId)?.name ?? fwId,
      state: cov.state,
      controls: linkedControls,
      unmetCount,
    };
  });

  const activeFrameworks = (baseline.framework_refs ?? [])
    .map((id) => fwById.get(id))
    .filter((f): f is NonNullable<typeof f> => Boolean(f));

  const perFramework = activeFrameworks.map((fw) => {
    const counts = { covered: 0, gap: 0, contribution: 0, unmapped: 0 } as Record<RequirementState, number>;
    for (const r of rows) if (r.frameworkId === fw.id) counts[r.state]++;
    const total = counts.covered + counts.gap + counts.contribution + counts.unmapped;
    return { fw, counts, total };
  });

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageTitle
        eyebrow={program.name}
        title="Requirements"
        aside={
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-xs font-medium text-muted-foreground">
              {rows.length} in scope · at <span className="text-foreground">{isoDate(status.at)}</span>
            </p>
            <AskAgentButton
              label="Propose crosswalk"
              size="sm"
              prompt={`Inspect unmapped requirements for program ${program.name} and propose draft crosswalk mappings to our controls for human review.`}
            />
          </div>
        }
      />

      <section aria-label="Framework coverage" className="flex flex-col gap-2 rounded-xl border bg-card px-4 py-3 shadow-xs">
        {perFramework.map(({ fw, counts, total }) => (
          <div key={fw.id} className="grid grid-cols-[minmax(0,14rem)_minmax(0,1fr)_auto] items-center gap-4 text-sm">
            <span className="truncate font-medium">{fw.name}</span>
            <SegmentBar segments={requirementSegments(counts)} />
            <span className="text-muted-foreground tabular-nums">
              <span className="font-semibold text-foreground">{percent(counts.covered, total)}</span> covered
            </span>
          </div>
        ))}
      </section>

      <RequirementsTable
        rows={rows}
        frameworks={activeFrameworks.map((f) => ({ id: f.id, name: f.name ?? f.id }))}
        programId={programId}
        at={atParam}
      />
    </div>
  );
}
