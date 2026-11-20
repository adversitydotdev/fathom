import type { Metadata } from "next";

import { Eyebrow, PageTitle } from "@/components/typography";
import {
  evaluationInstant,
  getControls,
  getImplementations,
  getProgram,
  getProgramStatus,
  getResults,
  getTests,
} from "@/lib/data";
import { isoDate } from "@/lib/format";

import { TestsTable, type TestRow, type TestStatus } from "./tests-table";

export const metadata: Metadata = { title: "Tests" };

export default async function TestsPage({
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
  const [status, controls, impls, tests, results] = await Promise.all([
    getProgramStatus(programId, instant),
    getControls(),
    getImplementations(program.system_ref),
    getTests(),
    getResults(),
  ]);

  const inBaseline = new Set(status.controls.map((c) => c.control_id));
  const controlById = new Map(controls.map((c) => [c.id, c]));
  const implByControl = new Map(impls.filter((i) => i.control_ref).map((i) => [i.control_ref!, i]));

  const latestByTest = new Map<string, (typeof results)[number]>();
  for (const r of results) {
    const prev = latestByTest.get(r.test_ref);
    if (!prev || r.observed > prev.observed) latestByTest.set(r.test_ref, r);
  }

  const rows: TestRow[] = tests
    .filter((t) => inBaseline.has(t.control_ref))
    .map((t) => {
      const ctrl = controlById.get(t.control_ref);
      const impl = implByControl.get(t.control_ref);
      const latest = latestByTest.get(t.id);
      let outcome: TestStatus = "missing";
      if (latest?.outcome === "pass") outcome = "pass";
      else if (latest?.outcome === "fail") outcome = "fail";
      else if (latest?.outcome === "error") outcome = "error";
      return {
        id: t.id,
        name: t.name ?? t.id,
        controlId: t.control_ref,
        controlDisplayId: ctrl?.display_id ?? t.control_ref,
        implementationId: impl?.id,
        method: t.method,
        interval: t.interval,
        hasRun: Boolean(t.run),
        status: outcome,
        observed: latest?.observed,
        summary: latest?.summary,
      };
    });

  const passing = rows.filter((r) => r.status === "pass").length;
  const failing = rows.filter((r) => r.status === "fail" || r.status === "error").length;
  const missing = rows.filter((r) => r.status === "missing").length;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageTitle
        eyebrow={program.name}
        title="Tests"
        aside={
          <p className="font-mono text-[11px] tracking-[0.12em] text-muted-foreground uppercase">
            {rows.length} tests · at <span className="text-foreground">{isoDate(status.at)}</span>
          </p>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Total tests" value={rows.length} />
        <StatCard label="Passing" value={passing} tone="met" />
        <StatCard label="Failing / Error" value={failing} tone={failing > 0 ? "gap" : undefined} />
        <StatCard label="No methodology" value={missing} tone={missing > 0 ? "waived" : undefined} />
      </div>

      <TestsTable rows={rows} programId={programId} at={atParam} />
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
