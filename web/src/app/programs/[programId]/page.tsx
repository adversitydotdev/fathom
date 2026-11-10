import {
  AlertTriangle,
  ChevronRight,
  FlaskConical,
  Gavel,
  Paperclip,
  PauseCircle,
  Sparkles,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import {
  Legend,
  SegmentBar,
  controlSegments,
  requirementSegments,
} from "@/components/status";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { RequirementState } from "@/lib/api/types";
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
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-medium">{program.name}</h1>
          <p className="text-sm text-muted-foreground">
            {system.name} · baseline <span className="font-mono text-xs">{baseline.name}</span>
          </p>
        </div>
        <p className="text-xs text-muted-foreground">
          Evaluated at <span className="font-mono">{isoDate(summary.at)}</span>
        </p>
      </div>

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

          <Card>
            <CardHeader>
              <CardTitle>Recent jobs</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="divide-y text-sm">
                {jobs.data.map((j) => (
                  <li key={j.id} className="flex items-center justify-between gap-3 py-2">
                    <span className="font-mono text-xs">{j.type}</span>
                    <span className="flex items-center gap-3">
                      <span className="font-mono text-xs text-muted-foreground">{isoDate(j.created)}</span>
                      <span className={j.status === "failed" ? "text-xs text-gap-ink" : "text-xs text-muted-foreground"}>{j.status}</span>
                    </span>
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

function Metric({ label, value, hint, tone, href }: { label: string; value: number; hint?: string; tone?: "gap"; href: string }) {
  return (
    <Link href={href} className="rounded-lg bg-muted/60 px-4 py-3 transition-colors hover:bg-muted">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="flex items-baseline gap-2">
        <span className={tone === "gap" && value > 0 ? "text-2xl font-medium text-gap-ink" : "text-2xl font-medium"}>{value}</span>
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
