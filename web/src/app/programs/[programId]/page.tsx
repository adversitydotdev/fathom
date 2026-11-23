import {
  AlertTriangle,
  Info,
  BookDown,
  ChevronRight,
  FileOutput,
  FlaskConical,
  Gavel,
  GitBranch,
  History,
  PackageOpen,
  Paperclip,
  PauseCircle,
  Plug,
  Sparkles,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { AskAgentButton } from "@/components/agent/assistant-drawer";
import { PageTitle } from "@/components/typography";
import { CountUp } from "@/components/motion";
import { PanelSequence } from "@/components/shell/side-panel";
import { Legend, Ring, SegmentBar, requirementSegments } from "@/components/status";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Job, RequirementState } from "@/lib/api/types";
import {
  evaluationInstant,
  getBaseline,
  getControls,
  getFrameworks,
  getImplementations,
  getJobs,
  getParties,
  getProgram,
  getProgramStatus,
  getProgramSummary,
  getSystem,
  getSystemGaps,
} from "@/lib/data";
import { createdByAgent } from "@/lib/agents";
import { isoDate, percent } from "@/lib/format";

export const metadata: Metadata = { title: "Overview" };

export default async function OverviewPage({ params, searchParams }: PageProps<"/programs/[programId]">) {
  const { programId } = await params;
  const { at } = await searchParams;
  const atParam = typeof at === "string" ? at : undefined;
  const instant = evaluationInstant(atParam);
  const q = atParam ? `?at=${atParam}` : "";

  const program = await getProgram(programId);
  const [summary, baseline, system, controls, frameworks, gaps, jobs, impls, parties] = await Promise.all([
    getProgramSummary(programId, instant),
    getBaseline(program.baseline_ref),
    getSystem(program.system_ref),
    getControls(),
    getFrameworks(),
    getSystemGaps(program.system_ref, instant),
    getJobs(),
    getImplementations(program.system_ref),
    getParties(),
  ]);
  const coverage = await Promise.all(
    (baseline.framework_refs ?? []).map(async (fw) => {
      const status = await getProgramStatus(programId, instant, fw);
      const counts = { covered: 0, gap: 0, contribution: 0, unmapped: 0 } as Record<RequirementState, number>;
      for (const r of status.requirements) counts[r.state]++;
      return { framework: frameworks.find((f) => f.id === fw), counts, total: status.requirements.length };
    }),
  );

  const controlById = new Map(controls.map((c) => [c.id, c]));
  const programGaps = gaps.gaps.filter((g) => g.program_id === programId);
  const agentDrafts = impls.filter((i) => createdByAgent(i.created_by_ref, parties)).length;
  const c = summary.controls;
  const totalControls = c.met + c.gap + c.waived + c.out_of_scope;
  const base = `/programs/${programId}`;

  const stateHref = (state?: string) =>
    `${base}/controls${state ? `?state=${state}` : ""}${atParam ? `${state ? "&" : "?"}at=${atParam}` : ""}`;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageTitle
        eyebrow={system.name}
        title={program.name}
        aside={
          <p className="text-sm text-muted-foreground">
            Evaluated at <span className="font-medium text-foreground tabular-nums">{isoDate(summary.at)}</span>
          </p>
        }
      >
        <p className="text-sm text-muted-foreground">
          Baseline <span className="text-foreground">{baseline.name}</span>
        </p>
      </PageTitle>

      <div className="grid items-stretch gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section aria-label="Control status" className="motion-rise flex" style={{ ["--i" as string]: 1 }}>
          <Card className="flex-1 bg-linear-to-br from-primary/[0.035] via-card to-card">
            <CardHeader>
              <CardTitle>Control readiness</CardTitle>
              <CardAction>
                <Link href={stateHref()} className="group inline-flex items-center gap-0.5 text-sm text-muted-foreground hover:text-foreground">
                  All controls
                  <ChevronRight className="size-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
                </Link>
              </CardAction>
            </CardHeader>
            <CardContent className="flex items-center gap-6">
              <Ring value={totalControls ? c.met / totalControls : 0}>
                <CountUp
                  value={totalControls ? Math.round((c.met / totalControls) * 100) : 0}
                  suffix="%"
                  className="text-2xl font-semibold tracking-tight tabular-nums"
                />
              </Ring>
              <div className="min-w-0 flex-1">
                <div className="text-lg font-semibold">
                  {c.gap === 0 ? "Every control is accounted for" : `${c.gap} ${c.gap === 1 ? "gap" : "gaps"} to close`}
                </div>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  {c.met} of {totalControls} controls met
                </p>
                <div className="mt-3 -ml-2 flex flex-wrap gap-1">
                  <StateLink label="Met" value={c.met} dot="bg-met" href={stateHref("met")} />
                  <StateLink label="Gap" value={c.gap} dot="bg-gap" tone="gap" href={stateHref("gap")} />
                  <StateLink label="Waived" value={c.waived} dot="bg-waived" href={stateHref("waived")} />
                  <StateLink label="Out of scope" value={c.out_of_scope} dot="bg-oos" href={stateHref("out_of_scope")} />
                </div>
              </div>
            </CardContent>
          </Card>
        </section>

        <Card className="motion-rise" style={{ ["--i" as string]: 2 }}>
          <CardHeader>
            <div className="flex items-center gap-1.5">
              <CardTitle>Requirement coverage</CardTitle>
              <span
                className="text-muted-foreground"
                title="Covered when every part has a reviewed mapping whose controls are met. Unmapped means nobody has reviewed a crosswalk yet."
              >
                <Info className="size-3.5" aria-hidden />
                <span className="sr-only">
                  Covered when every part has a reviewed mapping whose controls are met. Unmapped means nobody has reviewed a crosswalk yet.
                </span>
              </span>
            </div>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {coverage.map(({ framework, counts, total }) => (
              <div key={framework?.id} className="flex flex-col gap-2">
                <div className="flex items-baseline justify-between gap-4 text-sm">
                  <span className="truncate font-medium">{framework?.name}</span>
                  <span className="shrink-0 text-muted-foreground tabular-nums">
                    <span className="font-semibold text-foreground">{percent(counts.covered, total)}</span> · {counts.covered}/{total}
                  </span>
                </div>
                <SegmentBar segments={requirementSegments(counts)} />
              </div>
            ))}
            <Legend kind="requirement" />
          </CardContent>
        </Card>
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Card className="motion-rise" style={{ ["--i" as string]: 3 }}>
          <CardHeader>
            <div className="flex items-center gap-2">
              <CardTitle>Gaps</CardTitle>
              {programGaps.length > 0 && (
                <span className="rounded-full bg-gap-soft px-2 py-0.5 text-xs font-medium text-gap-ink tabular-nums">{programGaps.length}</span>
              )}
            </div>
            <CardAction className="flex items-center gap-3">
              {programGaps.length > 0 && (
                <AskAgentButton
                  label="Analyze gaps"
                  prompt={`Analyze the open control gaps for program ${program.name} (${program.id}) and suggest prioritized remediation steps or offer to draft planned implementations.`}
                />
              )}
              <Link href={stateHref("gap")} className="text-sm text-muted-foreground hover:text-foreground">
                View all
              </Link>
            </CardAction>
          </CardHeader>
          <CardContent>
            {programGaps.length === 0 ? (
              <p className="text-sm text-muted-foreground">Every control on the baseline is met, waived, or out of scope.</p>
            ) : (
              <ul className="-mx-2 divide-y">
                {programGaps.slice(0, 6).map((g) => {
                  const control = controlById.get(g.control_id);
                  return (
                    <li key={g.control_id}>
                      <Link
                        href={`${base}/controls/${g.control_id}${q}`}
                        className="group grid grid-cols-[4.5rem_minmax(0,1fr)_auto] items-center gap-3 rounded-md px-2 py-2.5 text-sm transition-colors hover:bg-muted"
                      >
                        <span className="font-mono text-xs text-muted-foreground">{control?.display_id}</span>
                        <span className="min-w-0">
                          <span className="block truncate font-medium">{control?.name}</span>
                          <span className="block truncate text-xs text-gap-ink">{g.failed[0]}</span>
                        </span>
                        <ChevronRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" aria-hidden />
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
            <PanelSequence hrefs={programGaps.map((g) => `${base}/controls/${g.control_id}`)} />
            {programGaps.length > 6 && <p className="pt-2 text-xs text-muted-foreground">+ {programGaps.length - 6} more</p>}
          </CardContent>
        </Card>

        <div className="motion-rise flex flex-col gap-6" style={{ ["--i" as string]: 4 }}>
          <Card>
            <CardHeader>
              <CardTitle>Needs attention</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="-mx-2 text-sm">
                <Attention icon={FlaskConical} label="Tests not passing" value={summary.failing_tests} href={`${base}/tests${q}`} />
                <Attention icon={Paperclip} label="Evidence expiring in 30 days" value={summary.expiring_evidence} href={`${base}/evidence${q}`} />
                <Attention icon={PauseCircle} label="Exceptions expiring in 30 days" value={summary.expiring_exceptions} href={`${base}/exceptions${q}`} />
                <Attention icon={Gavel} label="Open findings" value={summary.open_findings} href={`${base}/findings${q}`} />
                <Attention icon={AlertTriangle} label="Open risks" value={summary.open_risks} href={`${base}/risks${q}`} />
                <Attention icon={Sparkles} label="Agent drafts to review" value={agentDrafts} href={`${base}/controls${q}`} />
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Recent jobs</CardTitle>
              <CardAction>
                <Link href={`${base}/jobs${q}`} className="text-sm text-muted-foreground hover:text-foreground">
                  View all
                </Link>
              </CardAction>
            </CardHeader>
            <CardContent>
              <ul className="divide-y text-sm">
                {jobs.data.slice(0, 3).map((j) => (
                  <li key={j.id} className="flex items-center gap-3 py-2.5">
                    <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground [&>svg]:size-3.5">
                      <JobIcon type={j.type} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{JOB_LABEL[j.type]}</span>
                      <span className={j.status === "failed" ? "block truncate text-xs text-gap-ink" : "block truncate text-xs text-muted-foreground"}>
                        {j.status === "failed" ? `Failed: ${j.error?.title ?? "see job"}` : j.status}
                        {j.finished ? ` · ${duration(j.created, j.finished)}` : ""}
                      </span>
                    </span>
                    <span className="text-xs text-muted-foreground tabular-nums">{isoDate(j.created).slice(5)}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function StateLink({
  label,
  value,
  dot,
  tone,
  href,
}: {
  label: string;
  value: number;
  dot: string;
  tone?: "gap";
  href: string;
}) {
  return (
    <Link href={href} className="flex items-center gap-1.5 rounded-md px-2 py-1 text-sm transition-colors hover:bg-foreground/5">
      <span className={`size-2 rounded-full ${dot}`} aria-hidden />
      <span className="text-muted-foreground">{label}</span>
      <CountUp value={value} className={tone === "gap" && value > 0 ? "font-semibold tabular-nums text-gap-ink" : "font-semibold tabular-nums"} />
    </Link>
  );
}

function Attention({
  icon: Icon,
  label,
  value,
  href,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value?: number;
  href: string;
}) {
  const n = value ?? 0;
  return (
    <li>
      <Link href={href} className="flex items-center justify-between rounded-md px-2 py-2 transition-colors hover:bg-muted">
        <span className="flex items-center gap-2.5">
          <Icon className="size-4 text-muted-foreground" />
          {label}
        </span>
        <span
          className={
            n > 0
              ? "min-w-6 rounded-full bg-waived-soft px-2 py-0.5 text-center text-xs font-semibold text-waived-ink tabular-nums"
              : "min-w-6 px-2 text-center text-xs text-muted-foreground tabular-nums"
          }
        >
          {n}
        </span>
      </Link>
    </li>
  );
}

const JOB_LABEL: Record<Job["type"], string> = {
  library_pull: "Library pull",
  provider_import: "Provider import",
  test_run: "Test run",
  render: "Render",
  git_export: "Git export",
  restore: "Restore",
  collection: "Collection",
  integration_install: "Integration install",
};

function JobIcon({ type }: { type: Job["type"] }) {
  const Icon = {
    library_pull: BookDown,
    provider_import: PackageOpen,
    test_run: FlaskConical,
    render: FileOutput,
    git_export: GitBranch,
    restore: History,
    collection: Plug,
    integration_install: PackageOpen,
  }[type];
  return <Icon />;
}

function duration(from: string, to: string): string {
  const s = Math.max(0, Math.round((Date.parse(to) - Date.parse(from)) / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}
