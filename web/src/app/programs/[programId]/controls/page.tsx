import type { Metadata } from "next";

import { createdByAgent } from "@/lib/agents";
import {
  evaluationInstant,
  getControls,
  getImplementations,
  getParties,
  getProgram,
  getProgramStatus,
} from "@/lib/data";
import { isoDate } from "@/lib/format";

import { ControlsTable, type ControlRow } from "./controls-table";

export const metadata: Metadata = { title: "Controls" };

export default async function ControlsPage({ params, searchParams }: PageProps<"/programs/[programId]/controls">) {
  const { programId } = await params;
  const { at } = await searchParams;
  const atParam = typeof at === "string" ? at : undefined;
  const instant = evaluationInstant(atParam);

  const program = await getProgram(programId);
  const [status, controls, impls, parties] = await Promise.all([
    getProgramStatus(programId, instant),
    getControls(),
    getImplementations(program.system_ref),
    getParties(),
  ]);
  const controlById = new Map(controls.map((c) => [c.id, c]));
  const implById = new Map(impls.map((i) => [i.id, i]));

  const rows: ControlRow[] = status.controls.map((s) => {
    const control = controlById.get(s.control_id);
    const impl = s.implementation_id ? implById.get(s.implementation_id) : undefined;
    return {
      id: s.control_id,
      displayId: control?.display_id ?? s.control_id,
      name: control?.name ?? s.control_id,
      family: control?.family ?? "—",
      state: s.state,
      failed: s.failed ?? [],
      implStatus: impl?.status,
      owner: impl?.owner_ref ? (parties.get(impl.owner_ref)?.name ?? impl.owner_ref) : undefined,
      byAgent: createdByAgent(impl?.created_by_ref, parties),
    };
  });

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <div className="flex flex-wrap items-baseline gap-x-3">
        <h1 className="text-xl font-medium">Controls</h1>
        <p className="text-sm text-muted-foreground">
          {rows.length} on the baseline · at <span className="font-mono text-xs">{isoDate(status.at)}</span>
        </p>
      </div>
      <ControlsTable rows={rows} programId={programId} at={atParam} />
    </div>
  );
}
