import type { Metadata } from "next";
import Link from "next/link";
import { CircleCheck, CirclePause, CircleX } from "lucide-react";

import { StatusBadge } from "@/components/spectrumui/status-badge";
import { Eyebrow, PageTitle } from "@/components/typography";
import {
  evaluationInstant,
  getAllExceptions,
  getControls,
  getImplementations,
  getParties,
  getProgram,
  getProgramSummary,
  getRisks,
} from "@/lib/data";
import { daysBetween, isoDate } from "@/lib/format";

import { ExceptionCrudDialog } from "./exception-crud";

export const metadata: Metadata = { title: "Exceptions" };

export default async function ExceptionsPage({
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
  const [summary, exceptions, impls, controls, risks, parties] = await Promise.all([
    getProgramSummary(programId, instant),
    getAllExceptions(),
    getImplementations(program.system_ref),
    getControls(),
    getRisks(program.system_ref),
    getParties(),
  ]);

  const evalDate = isoDate(summary.at);
  const implById = new Map(impls.map((i) => [i.id, i]));
  const controlById = new Map(controls.map((c) => [c.id, c]));
  const riskById = new Map(risks.map((r) => [r.id, r]));

  const rows = exceptions
    .filter((ex) => implById.has(ex.implementation_ref))
    .map((ex) => {
      const impl = implById.get(ex.implementation_ref);
      const ctrl = impl?.control_ref ? controlById.get(impl.control_ref) : undefined;
      const risk = ex.risk_ref ? riskById.get(ex.risk_ref) : undefined;
      const days = daysBetween(evalDate, ex.expires);
      const state: "expired" | "expiring" | "active" = days < 0 ? "expired" : days <= 30 ? "expiring" : "active";
      return {
        id: ex.id,
        modified: ex.modified,
        implementationId: ex.implementation_ref,
        justification: ex.justification,
        expires: ex.expires,
        days,
        state,
        approverId: ex.approver_ref,
        approver: ex.approver_ref ? (parties.get(ex.approver_ref)?.name ?? ex.approver_ref) : "—",
        controlId: ctrl?.id,
        controlDisplayId: ctrl?.display_id ?? ex.implementation_ref,
        controlName: ctrl?.name ?? ex.implementation_ref,
        riskName: risk?.name,
        riskId: ex.risk_ref,
      };
    });

  const implOptions = impls
    .filter((i) => i.control_ref)
    .map((i) => {
      const ctrl = controlById.get(i.control_ref!);
      return { id: i.id, label: `${ctrl?.display_id ?? i.control_ref} · ${ctrl?.name ?? i.id}` };
    });
  const partyOptions = [...parties.values()].map((p) => ({ id: p.id, label: p.name ?? p.id }));
  const riskOptions = risks.map((r) => ({ id: r.id, label: r.name ?? r.id }));

  const active = rows.filter((r) => r.state === "active").length;
  const expiring = rows.filter((r) => r.state === "expiring").length;
  const expired = rows.filter((r) => r.state === "expired").length;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageTitle
        eyebrow={program.name}
        title="Exceptions"
        aside={
          <div className="flex flex-wrap items-center gap-3">
            <p className="font-mono text-[11px] tracking-[0.12em] text-muted-foreground uppercase">
              {rows.length} {rows.length === 1 ? "waiver" : "waivers"} · evaluated at{" "}
              <span className="text-foreground">{evalDate}</span>
            </p>
            <ExceptionCrudDialog implementations={implOptions} parties={partyOptions} risks={riskOptions} />
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Total waivers" value={rows.length} />
        <StatCard label="Active" value={active} tone="met" />
        <StatCard label="Expiring ≤ 30d" value={expiring} tone={expiring > 0 ? "waived" : undefined} />
        <StatCard label="Expired" value={expired} tone={expired > 0 ? "gap" : undefined} />
      </div>

      {rows.length === 0 ? (
        <div className="rounded-2xl border bg-card px-6 py-10 text-center text-sm text-muted-foreground">
          No active or historical exceptions recorded for this system.
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {rows.map((r) => (
            <article key={r.id} className="flex flex-col gap-3 rounded-2xl border bg-card p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex flex-col gap-1">
                  <div className="flex items-center gap-2">
                    {r.controlId ? (
                      <Link
                        href={`/programs/${programId}/controls/${r.controlId}${q}`}
                        className="font-mono text-xs text-muted-foreground hover:text-foreground hover:underline"
                      >
                        {r.controlDisplayId}
                      </Link>
                    ) : (
                      <span className="font-mono text-xs text-muted-foreground">{r.controlDisplayId}</span>
                    )}
                    <h2 className="text-base font-medium">
                      {r.controlId ? (
                        <Link href={`/programs/${programId}/controls/${r.controlId}${q}`} className="hover:underline">
                          {r.controlName}
                        </Link>
                      ) : (
                        r.controlName
                      )}
                    </h2>
                  </div>
                  <p className="text-sm text-muted-foreground">{r.justification}</p>
                </div>

                <div className="flex items-center gap-2">
                  {r.state === "expired" ? (
                    <StatusBadge tone="gap" icon={CircleX}>
                      expired {isoDate(r.expires)}
                    </StatusBadge>
                  ) : r.state === "expiring" ? (
                    <StatusBadge tone="waived" icon={CirclePause}>
                      expires in {r.days}d ({isoDate(r.expires)})
                    </StatusBadge>
                  ) : (
                    <StatusBadge tone="met" icon={CircleCheck}>
                      active until {isoDate(r.expires)}
                    </StatusBadge>
                  )}
                  <ExceptionCrudDialog
                    implementations={implOptions}
                    parties={partyOptions}
                    risks={riskOptions}
                    existing={r}
                  />
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-x-6 gap-y-1 border-t pt-3 font-mono text-xs text-muted-foreground">
                <span>
                  Approver: <span className="text-foreground">{r.approver}</span>
                </span>
                {r.riskId && (
                  <span>
                    Risk:{" "}
                    <Link href={`/programs/${programId}/risks${q}`} className="text-foreground hover:underline">
                      {r.riskName ?? r.riskId}
                    </Link>
                  </span>
                )}
                <span className="ml-auto opacity-70">{r.id}</span>
              </div>
            </article>
          ))}
        </div>
      )}
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
