import {
  AlertTriangle,
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
  Play,
  Plug,
  Sparkles,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { RecentActivity } from "@/components/spectrumui/recent-activity";
import { Eyebrow, PageTitle } from "@/components/typography";
import {
  Legend,
  SegmentBar,
  controlSegments,
  requirementSegments,
} from "@/components/status";
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

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8">
      <PageTitle
        eyebrow={`Program · ${system.name}`}
        title={program.name}
        aside={
          <p className="font-mono text-[11px] tracking-[0.12em] text-muted-foreground uppercase">
            Evaluated at <span className="text-foreground">{isoDate(summary.at)}</span>
          </p>
        }
      >
        <p className="text-sm text-muted-foreground">
          Baseline <span className="font-mono text-xs text-foreground">{baseline.name}</span>
        </p>
      </PageTitle>

      <section aria-label="Control status" className="flex flex-col gap-3">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Metric label="Met" value={c.met} hint={percent(c.met, totalControls)} href={`${base}/controls${q}`} />
          <Metric label="Gap" value={c.gap} tone="gap" href={`${base}/controls?state=gap${atParam ? `&at=${atParam}` : ""}`} />
          <Metric label="Waived" value={c.waived} href={`${base}/controls?state=waived${atParam ? `&at=${atParam}` : ""}`} />
          <Metric label="Out of scope" value={c.out_of_scope} href={`${base}/controls?state=out_of_scope${atParam ? `&at=${atParam}` : ""}`} />
        </div>
        <SegmentBar segments={controlSegments(c)} />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">{totalControls} controls on the baseline.</p>
          <Legend kind="control" />
        </div>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Requirement coverage</CardTitle>
          <CardAction>
            <Legend kind="requirement" />
          </CardAction>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {coverage.map(({ framework, counts, total }) => (
            <div key={framework?.id} className="grid grid-cols-[12rem_minmax(0,1fr)_3rem] items-center gap-3 text-sm">
              <span className="truncate">{framework?.name}</span>
              <SegmentBar segments={requirementSegments(counts)} />
              <span className="text-right font-mono text-xs" title={`${counts.covered} of ${total} covered`}>
                {percent(counts.covered, total)}
              </span>
            </div>
          ))}
          <p className="text-xs text-muted-foreground">
            Covered when every part has a reviewed mapping whose controls are met. Unmapped means nobody has reviewed a crosswalk yet.
          </p>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Card>
          <CardHeader>
            <CardTitle>Gaps</CardTitle>
            <CardAction>
              <Link href={`${base}/controls?state=gap${atParam ? `&at=${atParam}` : ""}`} className="text-xs text-muted-foreground hover:text-foreground">
                View all
              </Link>
            </CardAction>
          </CardHeader>
          <CardContent>
            {programGaps.length === 0 ? (
              <p className="text-sm text-muted-foreground">Every control on the baseline is met, waived, or out of scope.</p>
            ) : (
              <ul className="divide-y">
                {programGaps.slice(0, 6).map((g) => {
                  const control = controlById.get(g.control_id);
                  return (
                    <li key={g.control_id}>
                      <Link
                        href={`${base}/controls/${g.control_id}${q}`}
                        className="-mx-2 grid grid-cols-[4.5rem_minmax(0,1fr)_auto] items-center gap-3 rounded-md px-2 py-2.5 text-sm hover:bg-muted"
                      >
                        <span className="font-mono text-xs">{control?.display_id}</span>
                        <span className="min-w-0">
                          <span className="block truncate">{control?.name}</span>
                          <span className="block truncate text-xs text-gap-ink">{g.failed[0]}</span>
                        </span>
                        <ChevronRight className="size-4 text-muted-foreground" aria-hidden />
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
            {programGaps.length > 6 && <p className="pt-2 text-xs text-muted-foreground">+ {programGaps.length - 6} more</p>}
          </CardContent>
        </Card>

        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Needs attention</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="divide-y text-sm">
                <Attention icon={FlaskConical} label="Tests not passing" value={summary.failing_tests} />
                <Attention icon={Paperclip} label="Evidence expiring in 30 days" value={summary.expiring_evidence} />
                <Attention icon={PauseCircle} label="Exceptions expiring in 30 days" value={summary.expiring_exceptions} />
                <Attention icon={Gavel} label="Open findings" value={summary.open_findings} />
                <Attention icon={AlertTriangle} label="Open risks" value={summary.open_risks} />
                <Attention icon={Sparkles} label="Agent drafts to review" value={agentDrafts} />
              </ul>
            </CardContent>
          </Card>

        </div>
      </div>

      <RecentActivity
        title="Recent jobs"
        titleIcon={<Play />}
        items={jobs.data.map((j) => ({
          icon: <JobIcon type={j.type} />,
          title: JOB_LABEL[j.type],
          duration: j.finished ? duration(j.created, j.finished) : undefined,
          description: j.status === "failed" ? `Failed: ${j.error?.title ?? "see job"}` : j.status,
          timeAgo: isoDate(j.created).slice(5),
        }))}
      />
    </div>
  );
}

function Metric({ label, value, hint, tone, href }: { label: string; value: number; hint?: string; tone?: "gap"; href: string }) {
  return (
    <Link href={href} className="flex flex-col gap-3 rounded-2xl border bg-card px-4 py-4 transition-colors hover:border-foreground/25">
      <Eyebrow>{label}</Eyebrow>
      <div className="flex items-baseline gap-2">
        <span className={tone === "gap" && value > 0 ? "text-3xl font-medium tabular-nums text-gap-ink" : "text-3xl font-medium tabular-nums"}>{value}</span>
        {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
      </div>
    </Link>
  );
}

function Attention({ icon: Icon, label, value }: { icon: React.ComponentType<{ className?: string }>; label: string; value?: number }) {
  return (
    <li className="flex items-center justify-between py-2">
      <span className="flex items-center gap-2 text-muted-foreground">
        <Icon className="size-4" />
        {label}
      </span>
      <span className="font-medium tabular-nums">{value ?? 0}</span>
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
  connector: "Connector",
};

function JobIcon({ type }: { type: Job["type"] }) {
  const Icon = {
    library_pull: BookDown,
    provider_import: PackageOpen,
    test_run: FlaskConical,
    render: FileOutput,
    git_export: GitBranch,
    restore: History,
    connector: Plug,
  }[type];
  return <Icon />;
}

function duration(from: string, to: string): string {
  const s = Math.max(0, Math.round((Date.parse(to) - Date.parse(from)) / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}
