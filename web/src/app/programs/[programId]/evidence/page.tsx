import type { Metadata } from "next";

import { PageTitle } from "@/components/typography";
import {
  evaluationInstant,
  getControls,
  getEvidence,
  getImplementations,
  getProgram,
  getProgramSummary,
} from "@/lib/data";
import { daysBetween, isoDate } from "@/lib/format";

import { EvidenceCrudDialog } from "./evidence-crud";
import { EvidenceTable, type EvidenceRow, type ValidityState } from "./evidence-table";

export const metadata: Metadata = { title: "Evidence" };

export default async function EvidencePage({
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
  const [summary, controls, impls, evidence] = await Promise.all([
    getProgramSummary(programId, instant),
    getControls(),
    getImplementations(program.system_ref),
    getEvidence(),
  ]);

  const evalDate = isoDate(summary.at);
  const controlById = new Map(controls.map((c) => [c.id, c]));
  const implById = new Map(impls.map((i) => [i.id, i]));

  const rows: EvidenceRow[] = evidence.map((e) => {
    const impl = e.implementation_ref ? implById.get(e.implementation_ref) : undefined;
    const ctrl = impl?.control_ref ? controlById.get(impl.control_ref) : undefined;
    let validity: ValidityState = "valid";
    if (e.valid_until) {
      const days = daysBetween(evalDate, e.valid_until);
      if (days < 0) validity = "expired";
      else if (days <= 30) validity = "expiring";
    }
    return {
      id: e.id,
      modified: e.modified,
      name: e.name ?? e.id,
      method: e.method,
      implementationId: e.implementation_ref,
      controlId: ctrl?.id,
      controlDisplayId: ctrl?.display_id,
      collected: e.collected ?? e.created,
      validUntil: e.valid_until,
      validity,
      digestShort: e.resource?.digest?.value?.slice(0, 12),
      mediaType: e.resource?.media_type,
      uri: e.resource?.uri,
    };
  });

  const implOptions = impls
    .filter((i) => i.control_ref)
    .map((i) => {
      const ctrl = controlById.get(i.control_ref!);
      return { id: i.id, label: `${ctrl?.display_id ?? i.control_ref} · ${ctrl?.name ?? i.id}` };
    });

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageTitle
        eyebrow={program.name}
        title="Evidence"
        aside={
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-xs font-medium text-muted-foreground">
              {rows.length} items · validity at <span className="text-foreground">{evalDate}</span>
            </p>
            <EvidenceCrudDialog implementations={implOptions} />
          </div>
        }
      />

      <EvidenceTable rows={rows} implementations={implOptions} programId={programId} at={atParam} />
    </div>
  );
}
