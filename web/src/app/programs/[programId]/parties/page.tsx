import type { Metadata } from "next";

import { StatCard, PageTitle } from "@/components/typography";
import {
  getImplementations,
  getParties,
  getPolicies,
  getProgram,
  getRisks,
} from "@/lib/data";

import { PartyCrudDialog } from "./party-crud";
import { PartiesTable, type PartyRow } from "./parties-table";

export const metadata: Metadata = { title: "Parties" };

export default async function PartiesPage({
  params,
}: {
  params: Promise<{ programId: string }>;
}) {
  const { programId } = await params;

  const program = await getProgram(programId);
  const [partiesMap, impls, risks, policies] = await Promise.all([
    getParties(),
    getImplementations(program.system_ref),
    getRisks(program.system_ref),
    getPolicies(),
  ]);

  const implCounts = new Map<string, number>();
  for (const i of impls) {
    if (i.owner_ref) implCounts.set(i.owner_ref, (implCounts.get(i.owner_ref) ?? 0) + 1);
  }
  const riskCounts = new Map<string, number>();
  for (const r of risks) {
    if (r.owner_ref) riskCounts.set(r.owner_ref, (riskCounts.get(r.owner_ref) ?? 0) + 1);
  }
  const policyCounts = new Map<string, number>();
  for (const p of policies) {
    if (p.owner_ref) policyCounts.set(p.owner_ref, (policyCounts.get(p.owner_ref) ?? 0) + 1);
  }

  const rows: PartyRow[] = [...partiesMap.values()].map((p) => ({
    id: p.id,
    modified: p.modified,
    name: p.name ?? p.id,
    kind: p.kind,
    isAgent: Boolean(p.tags?.includes("agent")),
    tags: p.tags ?? [],
    ownedControls: implCounts.get(p.id) ?? 0,
    ownedRisks: riskCounts.get(p.id) ?? 0,
    ownedPolicies: policyCounts.get(p.id) ?? 0,
  }));

  const people = rows.filter((r) => r.kind === "person").length;
  const teams = rows.filter((r) => r.kind === "team").length;
  const roles = rows.filter((r) => r.kind === "role").length;
  const orgs = rows.filter((r) => r.kind === "organization").length;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageTitle
        eyebrow={program.name}
        title="Parties"
        aside={
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-xs font-medium text-muted-foreground">
              {rows.length} parties
            </p>
            <PartyCrudDialog />
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="People" value={people} />
        <StatCard label="Teams" value={teams} />
        <StatCard label="Roles & agents" value={roles} />
        <StatCard label="Organizations" value={orgs} />
      </div>

      <PartiesTable rows={rows} />
    </div>
  );
}
