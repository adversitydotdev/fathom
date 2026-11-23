import type { Metadata } from "next";
import Link from "next/link";
import { CircleCheck, CircleDashed, CircleMinus } from "lucide-react";

import { AskAgentButton } from "@/components/agent/assistant-drawer";
import { StatusBadge } from "@/components/spectrumui/status-badge";
import { AgentMark } from "@/components/status";
import { Eyebrow, StatCard, PageTitle } from "@/components/typography";
import { getControls, getParties, getPolicies, getProcedures, getProgram } from "@/lib/data";
import { isoDate } from "@/lib/format";

import { PolicyCrudDialog, ProcedureCrudDialog } from "./policy-crud";

export const metadata: Metadata = { title: "Policies" };

function DocStatusBadge({ status }: { status: "adopted" | "draft" | "retired" }) {
  if (status === "adopted") return <StatusBadge tone="met" icon={CircleCheck}>adopted</StatusBadge>;
  if (status === "draft") return <StatusBadge tone="waived" icon={CircleDashed}>draft</StatusBadge>;
  return <StatusBadge tone="neutral" icon={CircleMinus}>retired</StatusBadge>;
}

export default async function PoliciesPage({
  params,
  searchParams,
}: {
  params: Promise<{ programId: string }>;
  searchParams: Promise<{ at?: string }>;
}) {
  const { programId } = await params;
  const { at } = await searchParams;
  const atParam = typeof at === "string" ? at : undefined;
  const q = atParam ? `?at=${atParam}` : "";

  const program = await getProgram(programId);
  const [policies, procedures, controls, parties] = await Promise.all([
    getPolicies(),
    getProcedures(),
    getControls(),
    getParties(),
  ]);

  const controlById = new Map(controls.map((c) => [c.id, c]));
  const policyById = new Map(policies.map((p) => [p.id, p]));
  const partyOptions = [...parties.values()].map((p) => ({ id: p.id, label: p.name ?? p.id }));
  const controlOptions = controls.map((c) => ({ id: c.id, label: `${c.display_id ?? c.id} · ${c.name ?? ""}`.trim() }));
  const policyOptions = policies.map((p) => ({ id: p.id, label: p.name ?? p.id }));

  const adopted = policies.filter((p) => p.status === "adopted").length;
  const drafts = policies.filter((p) => p.status === "draft").length;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageTitle
        eyebrow={program.name}
        title="Policies"
        aside={
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-xs font-medium text-muted-foreground">
              {policies.length} policies · {procedures.length} procedures
            </p>
            <AskAgentButton
              label="Draft with AI"
              size="sm"
              prompt={`Inspect our controls and existing policies for program ${program.name} and draft a missing security policy in Markdown (status: draft) for human review.`}
            />
            <PolicyCrudDialog parties={partyOptions} controls={controlOptions} />
            <ProcedureCrudDialog policies={policyOptions} parties={partyOptions} controls={controlOptions} />
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Policies" value={policies.length} />
        <StatCard label="Adopted" value={adopted} tone="met" />
        <StatCard label="Drafts" value={drafts} tone={drafts > 0 ? "waived" : undefined} />
        <StatCard label="Procedures" value={procedures.length} />
      </div>

      <section className="flex flex-col gap-3">
        <Eyebrow>Policies</Eyebrow>
        <div className="overflow-hidden rounded-xl border bg-card">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-muted/30 text-xs font-medium text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">Policy</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Version</th>
                  <th className="px-4 py-3 font-medium">Owner</th>
                  <th className="px-4 py-3 font-medium">Reviewed</th>
                  <th className="px-4 py-3 font-medium">Controls</th>
                  <th className="px-4 py-3 text-right font-medium"></th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {policies.map((p) => {
                  const byAgent = p.created_by_ref
                    ? Boolean(parties.get(p.created_by_ref)?.tags?.includes("agent"))
                    : false;
                  const owner = p.owner_ref ? (parties.get(p.owner_ref)?.name ?? p.owner_ref) : "—";
                  return (
                    <tr key={p.id} className="hover:bg-muted/20">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2 font-medium">
                          <span>{p.name}</span>
                          {byAgent && <AgentMark label="Agent-authored policy draft" />}
                        </div>
                        {p.adopted && (
                          <div className="font-mono text-[11px] text-muted-foreground">
                            adopted {isoDate(p.adopted)}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <DocStatusBadge status={p.status} />
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                        {p.version ? `v${p.version}` : "—"}
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{owner}</td>
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                        {isoDate(p.reviewed)}
                        {p.review_interval ? ` · ${p.review_interval}` : ""}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1.5">
                          {(p.control_refs ?? []).map((cid) => {
                            const ctrl = controlById.get(cid);
                            return (
                              <Link
                                key={cid}
                                href={`/programs/${programId}/controls/${cid}${q}`}
                                className="rounded border bg-muted/40 px-1.5 py-0.5 font-mono text-[11px] hover:border-foreground/40"
                              >
                                {ctrl?.display_id ?? cid}
                              </Link>
                            );
                          })}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <PolicyCrudDialog
                          parties={partyOptions}
                          controls={controlOptions}
                          existing={{
                            id: p.id,
                            modified: p.modified,
                            name: p.name ?? p.id,
                            status: p.status,
                            version: p.version,
                            ownerId: p.owner_ref,
                            reviewInterval: p.review_interval,
                            controlIds: p.control_refs ?? [],
                            hasResource: Boolean(p.resource?.digest),
                          }}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <Eyebrow>Procedures</Eyebrow>
        <div className="overflow-hidden rounded-xl border bg-card">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-muted/30 text-xs font-medium text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">Procedure</th>
                  <th className="px-4 py-3 font-medium">Parent policy</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Owner</th>
                  <th className="px-4 py-3 font-medium">Controls</th>
                  <th className="px-4 py-3 text-right font-medium"></th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {procedures.map((proc) => {
                  const owner = proc.owner_ref ? (parties.get(proc.owner_ref)?.name ?? proc.owner_ref) : "—";
                  const parent = proc.policy_ref ? policyById.get(proc.policy_ref)?.name : undefined;
                  return (
                    <tr key={proc.id} className="hover:bg-muted/20">
                      <td className="px-4 py-3 font-medium">{proc.name}</td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{parent ?? "—"}</td>
                      <td className="px-4 py-3">
                        <DocStatusBadge status={proc.status} />
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{owner}</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1.5">
                          {(proc.control_refs ?? []).map((cid) => {
                            const ctrl = controlById.get(cid);
                            return (
                              <Link
                                key={cid}
                                href={`/programs/${programId}/controls/${cid}${q}`}
                                className="rounded border bg-muted/40 px-1.5 py-0.5 font-mono text-[11px] hover:border-foreground/40"
                              >
                                {ctrl?.display_id ?? cid}
                              </Link>
                            );
                          })}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <ProcedureCrudDialog
                          policies={policyOptions}
                          parties={partyOptions}
                          controls={controlOptions}
                          existing={{
                            id: proc.id,
                            modified: proc.modified,
                            name: proc.name ?? proc.id,
                            status: proc.status,
                            policyId: proc.policy_ref,
                            ownerId: proc.owner_ref,
                            controlIds: proc.control_refs ?? [],
                            hasResource: Boolean(proc.resource?.digest),
                          }}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}
