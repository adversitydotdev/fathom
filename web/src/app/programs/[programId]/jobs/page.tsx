import type { Metadata } from "next";
import { CircleCheck, CircleX, Clock, Download, LoaderCircle } from "lucide-react";

import { StatusBadge } from "@/components/spectrumui/status-badge";
import { Eyebrow, PageTitle } from "@/components/typography";
import type { Job } from "@/lib/api/types";
import { getAllJobs, getBaseline, getProgram } from "@/lib/data";
import { isoDate } from "@/lib/format";

import { JobActions, JobsAutoRefresh } from "./job-actions";

export const metadata: Metadata = { title: "Jobs" };

const TYPE_LABELS: Record<Job["type"], string> = {
  test_run: "Test run",
  library_pull: "Library pull",
  provider_import: "Provider import",
  render: "Document render",
  git_export: "Git export",
  restore: "Backup restore",
  collection: "Integration collection",
};

function JobStatusBadge({ status }: { status: Job["status"] }) {
  if (status === "succeeded") return <StatusBadge tone="met" icon={CircleCheck}>succeeded</StatusBadge>;
  if (status === "failed") return <StatusBadge tone="gap" icon={CircleX}>failed</StatusBadge>;
  if (status === "running") return <StatusBadge tone="contribution" icon={LoaderCircle} spin>running</StatusBadge>;
  return <StatusBadge tone="waived" icon={Clock}>queued</StatusBadge>;
}

function duration(created: string, finished?: string): string {
  if (!finished) return "—";
  const sec = Math.max(0, Math.round((Date.parse(finished) - Date.parse(created)) / 1000));
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m ${sec % 60}s`;
}

export default async function JobsPage({
  params,
}: {
  params: Promise<{ programId: string }>;
}) {
  const { programId } = await params;

  const program = await getProgram(programId);
  const [baseline, rawJobs] = await Promise.all([
    getBaseline(program.baseline_ref),
    getAllJobs(),
  ]);
  const jobs = [...rawJobs].sort((a, b) => b.created.localeCompare(a.created));

  const primaryFrameworkId = baseline.framework_refs?.[0];

  const succeeded = jobs.filter((j) => j.status === "succeeded").length;
  const failed = jobs.filter((j) => j.status === "failed").length;
  const active = jobs.filter((j) => j.status === "queued" || j.status === "running").length;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <JobsAutoRefresh active={active > 0} />
      <PageTitle
        eyebrow={program.name}
        title="Jobs"
        aside={
          <p className="font-mono text-[11px] tracking-[0.12em] text-muted-foreground uppercase">
            {jobs.length} jobs recorded
          </p>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Total jobs" value={jobs.length} />
        <StatCard label="Succeeded" value={succeeded} tone="met" />
        <StatCard label="Failed" value={failed} tone={failed > 0 ? "gap" : undefined} />
        <StatCard label="Queued / Running" value={active} tone={active > 0 ? "waived" : undefined} />
      </div>

      <section className="flex flex-col gap-3 rounded-2xl border bg-card p-5" aria-label="Exports and renders">
        <Eyebrow>Exports & renders</Eyebrow>
        <p className="text-xs text-muted-foreground">
          Queue OSCAL 1.2.3 packages, narrative System Security Plans (SSP), or full canonical Git mirror exports for{" "}
          <span className="text-foreground">{program.name}</span>.
        </p>
        <JobActions programId={programId} frameworkId={primaryFrameworkId} />
      </section>

      <section className="flex flex-col gap-3">
        <Eyebrow>Job history</Eyebrow>
        <div className="overflow-hidden rounded-2xl border bg-card">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-muted/30 font-mono text-[11px] tracking-[0.08em] text-muted-foreground uppercase">
                <tr>
                  <th className="px-4 py-3 font-medium">Job</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Created</th>
                  <th className="px-4 py-3 font-medium">Duration</th>
                  <th className="px-4 py-3 font-medium">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {jobs.map((j) => (
                  <tr key={j.id} className="hover:bg-muted/20">
                    <td className="px-4 py-3 font-mono text-xs">{j.id}</td>
                    <td className="px-4 py-3 text-xs">{TYPE_LABELS[j.type]}</td>
                    <td className="px-4 py-3">
                      <JobStatusBadge status={j.status} />
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{isoDate(j.created)}</td>
                    <td className="px-4 py-3 font-mono text-xs tabular-nums text-muted-foreground">
                      {duration(j.created, j.finished)}
                    </td>
                    <td className="px-4 py-3 text-xs">
                      {j.error ? (
                        <span className="text-gap-ink">{j.error.title}</span>
                      ) : j.files && j.files.length > 0 ? (
                        <div className="flex flex-wrap gap-1.5">
                          {j.files.map((file) => (
                            <a
                              key={file}
                              href={`/api/jobs/${encodeURIComponent(j.id)}/files/${encodeURIComponent(file)}`}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 rounded border bg-muted/40 px-2 py-0.5 font-mono text-[11px] hover:border-foreground/40 hover:text-foreground"
                            >
                              <Download className="size-3" aria-hidden />
                              {file}
                            </a>
                          ))}
                        </div>
                      ) : j.result_id ? (
                        <span className="font-mono text-muted-foreground">{j.result_id}</span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
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
