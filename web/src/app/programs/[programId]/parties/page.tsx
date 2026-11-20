import type { Metadata } from "next";

import { Eyebrow, PageTitle } from "@/components/typography";
import {
  getImplementations,
  getParties,
  getPolicies,
  getProgram,
  getRisks,
} from "@/lib/data";

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
          <p className="font-mono text-[11px] tracking-[0.12em] text-muted-foreground uppercase">
            {rows.length} parties
          </p>
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

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col gap-2 rounded-2xl border bg-card px-4 py-4">
      <Eyebrow>{label}</Eyebrow>
      <span className="text-3xl font-medium tabular-nums">{value}</span>
    </div>
  );
}
