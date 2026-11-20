import type { Metadata } from "next";

import { Eyebrow, PageTitle } from "@/components/typography";
import {
  evaluationInstant,
  getControls,
  getEvidence,
  getImplementations,
  getProgram,
  getProgramSummary,
} from "@/lib/data";
import { daysBetween, isoDate } from "@/lib/format";

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
      name: e.name ?? e.id,
      method: e.method,
      controlId: ctrl?.id,
      controlDisplayId: ctrl?.display_id,
      collected: e.collected ?? e.created,
      validUntil: e.valid_until,
      validity,
      digestShort: e.resource?.digest?.value?.slice(0, 12),
      mediaType: e.resource?.media_type,
    };
  });

  const expired = rows.filter((r) => r.validity === "expired").length;
  const expiring = rows.filter((r) => r.validity === "expiring").length;
  const valid = rows.filter((r) => r.validity === "valid").length;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageTitle
        eyebrow={program.name}
        title="Evidence"
        aside={
          <p className="font-mono text-[11px] tracking-[0.12em] text-muted-foreground uppercase">
            {rows.length} items · validity at <span className="text-foreground">{evalDate}</span>
          </p>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Total records" value={rows.length} />
        <StatCard label="Valid" value={valid} tone="met" />
        <StatCard label="Expiring ≤ 30d" value={expiring} tone={expiring > 0 ? "waived" : undefined} />
        <StatCard label="Expired" value={expired} tone={expired > 0 ? "gap" : undefined} />
      </div>

      <EvidenceTable rows={rows} programId={programId} at={atParam} />
    </div>
  );
}

function StatCard({ label, value, tone }: { label: string; value: number; tone?: "met" | "gap" | "waived" }) {
  const cls =
    tone === "gap"
      ? "text-gap-ink"
      : tone === "met"
        ? "text-met-ink"
        : tone === "waived"
          ? "text-waived-ink"
          : "";
  return (
    <div className="flex flex-col gap-2 rounded-2xl border bg-card px-4 py-4">
      <Eyebrow>{label}</Eyebrow>
      <span className={`text-3xl font-medium tabular-nums ${cls}`}>{value}</span>
    </div>
  );
}
