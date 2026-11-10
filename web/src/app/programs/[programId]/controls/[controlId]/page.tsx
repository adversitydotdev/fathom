import {
  AlertCircle,
  Check,
  CircleCheck,
  CircleDashed,
  FileUp,
  Link2,
  Minus,
  PenLine,
  Sparkles,
  Workflow,
  X,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { cn } from "cn";

import { ControlStateBadge } from "@/components/status";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { createdByAgent } from "@/lib/agents";
import type { Evidence, Implementation, Party, Result } from "@/lib/api/types";
import {
  evaluationInstant,
  getControl,
  getControlImplementations,
  getControlMappings,
  getControlTests,
  getExceptions,
  getFrameworks,
  getImplementationEvidence,
  getImplementationResults,
  getParties,
  getProgram,
  getProgramStatus,
  getRequirements,
  getSystem,
} from "@/lib/data";
import { daysBetween, isoDate } from "@/lib/format";

import { RunTestButton } from "./run-test-button";

export async function generateMetadata({ params }: PageProps<"/programs/[programId]/controls/[controlId]">): Promise<Metadata> {
  const { controlId } = await params;
  const control = await getControl(controlId);
  return { title: `${control.display_id ?? ""} ${control.name}`.trim() };
}

export default async function ControlPage({ params, searchParams }: PageProps<"/programs/[programId]/controls/[controlId]">) {
  const { programId, controlId } = await params;
  const { at } = await searchParams;
  const atParam = typeof at === "string" ? at : undefined;
  const instant = evaluationInstant(atParam);

  const [program, control] = await Promise.all([getProgram(programId), getControl(controlId)]);
  const [system, status, allImpls, tests, mappings, requirements, frameworks, parties] = await Promise.all([
    getSystem(program.system_ref),
    getProgramStatus(programId, instant),
    getControlImplementations(controlId),
    getControlTests(controlId),
    getControlMappings(controlId),
    getRequirements(),
    getFrameworks(),
    getParties(),
  ]);

  const evalAt = status.at;
  const entry = status.controls.find((c) => c.control_id === controlId);
  const systemImpl = allImpls.find((i) => i.system_ref === system.id && !i.component_ref);
  const providerHalves = allImpls.filter(
    (i) => i.origin === "provider" && i.component_ref && system.component_refs?.includes(i.component_ref),
  );
  const applicableTests = tests.filter((t) => !t.revoked && (!t.system_refs || t.system_refs.includes(system.id)));

  const [results, evidence, exceptions] = systemImpl
    ? await Promise.all([
        getImplementationResults(systemImpl.id),
        getImplementationEvidence(systemImpl.id),
        getExceptions(systemImpl.id),
      ])
    : [[], [], []];
  const latestByTest = new Map<string, Result>();
  for (const r of results) {
    const prev = latestByTest.get(r.test_ref);
    if (!prev || prev.observed < r.observed) latestByTest.set(r.test_ref, r);
  }

  const reqById = new Map(requirements.map((r) => [r.id, r]));
  const fwShort = new Map(frameworks.map((f) => [f.id, (f.name ?? f.id).replace(/^NIST SP /, "").replace(/ Revision /, " r")]));
  const backHref = `/programs/${programId}/controls${atParam ? `?at=${atParam}` : ""}`;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5">
      <div>
        <nav className="mb-1 text-xs text-muted-foreground" aria-label="Breadcrumb">
          <Link href={backHref} className="hover:text-foreground">
            Controls
          </Link>{" "}
          / <span className="font-mono">{control.display_id}</span>
        </nav>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-medium">{control.name}</h1>
          {entry && <ControlStateBadge state={entry.state} />}
          <span className="text-xs text-muted-foreground">
            {control.family} · {control.control_type} · {control.frequency} · {control.origin === "custom" ? "custom" : "library"}
          </span>
        </div>
        {entry && entry.failed && entry.failed.length > 0 && (
          <div className="mt-3 flex flex-col gap-1 rounded-lg bg-gap-soft px-3 py-2 text-sm text-gap-ink" role="status">
            {entry.failed.map((f) => (
              <span key={f} className="flex items-start gap-2">
                <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
                {f}
              </span>
            ))}
          </div>
        )}
        {!entry && (
          <p className="mt-3 text-sm text-muted-foreground">This control is not on the baseline for {program.name}.</p>
        )}
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <div className="flex flex-col gap-5">
          <Card>
            <CardHeader>
              <CardTitle>Statement</CardTitle>
              <CardAction className="font-mono text-xs text-muted-foreground">{control.id}</CardAction>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 leading-relaxed">
              <Statement text={control.statement} parameters={control.parameters} values={systemImpl?.parameter_values} />
              {control.guidance && <p className="text-sm text-muted-foreground">{control.guidance}</p>}
            </CardContent>
          </Card>

          {systemImpl ? (
            <ImplementationCard impl={systemImpl} parties={parties} title="Implementation" />
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>Implementation</CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">
                {system.name} has no implementation of this control. Create one with{" "}
                <code className="font-mono text-xs">POST /v1/implementations</code>.
              </CardContent>
            </Card>
          )}

          {providerHalves.map((impl) => (
            <ImplementationCard key={impl.id} impl={impl} parties={parties} title="Provider's half" />
          ))}
        </div>

        <div className="flex flex-col gap-5">
          <Card>
            <CardHeader>
              <CardTitle>Required tests</CardTitle>
            </CardHeader>
            <CardContent>
              {applicableTests.length === 0 ? (
                <p className="text-sm text-muted-foreground">No required test. Unexpired evidence on the implementation meets the control.</p>
              ) : (
                <ul className="divide-y">
                  {applicableTests.map((t) => {
                    const r = latestByTest.get(t.id);
                    return (
                      <li key={t.id} className="flex items-start gap-3 py-2.5">
                        <Outcome outcome={r?.outcome} />
                        <div className="min-w-0 flex-1 text-sm">
                          <div className="truncate">{t.name}</div>
                          <div className="text-xs text-muted-foreground">
                            <span className="font-mono">{t.method}</span> · {t.interval}
                            {r ? <> · {r.outcome} {isoDate(r.observed)}</> : t.method === "automated" && !t.run ? " · no methodology defined" : " · no result"}
                          </div>
                          {r?.summary && r.outcome !== "pass" && <div className="mt-1 text-xs text-gap-ink">{r.summary}</div>}
                        </div>
                        {t.run && systemImpl && <RunTestButton testId={t.id} implementationId={systemImpl.id} />}
                      </li>
                    );
                  })}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Evidence</CardTitle>
              <CardAction className="text-xs text-muted-foreground">valid until</CardAction>
            </CardHeader>
            <CardContent>
              {evidence.length === 0 ? (
                <p className="text-sm text-muted-foreground">No evidence on this implementation.</p>
              ) : (
                <ul className="divide-y">
                  {evidence
                    .slice()
                    .sort((a, b) => (b.valid_until ?? "").localeCompare(a.valid_until ?? ""))
                    .map((e) => (
                      <li key={e.id} className="flex items-center gap-3 py-2 text-sm">
                        <EvidenceIcon method={e.method} />
                        <span className="min-w-0 flex-1 truncate" title={e.resource?.uri}>
                          {e.name}
                        </span>
                        <Validity until={e.valid_until} at={evalAt} />
                      </li>
                    ))}
                </ul>
              )}
            </CardContent>
          </Card>

          {exceptions.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Exceptions</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2 text-sm">
                {exceptions.map((x) => (
                  <div key={x.id}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-muted-foreground">Approved by {parties.get(x.approver_ref)?.name ?? x.approver_ref}</span>
                      <Validity until={x.expires} at={evalAt} />
                    </div>
                    <p className="mt-1">{x.justification}</p>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Maps to</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="divide-y">
                {mappings.map((m) => {
                  const [reqId, part] = m.target_ref.split("#");
                  const req = reqById.get(reqId);
                  return (
                    <li key={m.id} className="flex items-center gap-3 py-2 text-sm">
                      <span className="w-20 shrink-0 truncate text-xs text-muted-foreground">{req ? fwShort.get(req.framework_ref) : ""}</span>
                      <span className="min-w-0 flex-1 truncate" title={req?.name}>
                        <span className="font-mono text-xs">
                          {req?.display_id ?? reqId}
                          {part ? `#${part}` : ""}
                        </span>{" "}
                        <span className="text-muted-foreground">{req?.name}</span>
                      </span>
                      <span className="font-mono text-xs text-muted-foreground">{m.relationship}</span>
                      {m.review_status === "reviewed" ? (
                        <CircleCheck className="size-4 text-met" aria-label="Reviewed" />
                      ) : (
                        <CircleDashed className="size-4 text-muted-foreground" aria-label="Draft, not counted" />
                      )}
                    </li>
                  );
                })}
              </ul>
              <p className="pt-2 text-xs text-muted-foreground">Only reviewed mappings count toward requirement coverage.</p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

/** Renders `{{ param }}` with the implementation's value, or flags it unset. */
function Statement({
  text,
  parameters,
  values,
}: {
  text: string;
  parameters?: Record<string, { label?: string; value?: string }>;
  values?: Record<string, string>;
}) {
  const parts = text.split(/(\{\{\s*[\w.-]+\s*\}\})/g);
  return (
    <p>
      {parts.map((part, i) => {
        const m = part.match(/^\{\{\s*([\w.-]+)\s*\}\}$/);
        if (!m) return part;
        const name = m[1];
        const value = values?.[name] ?? parameters?.[name]?.value;
        const label = parameters?.[name]?.label ?? name;
        return value ? (
          <span key={i} className="rounded bg-contribution-soft px-1 text-contribution-ink" title={`${name}: ${label}`}>
            {value}
          </span>
        ) : (
          <span key={i} className="rounded bg-gap-soft px-1 font-mono text-xs text-gap-ink" title={`${name} has no value`}>
            {label}: unset
          </span>
        );
      })}
    </p>
  );
}

function ImplementationCard({ impl, parties, title }: { impl: Implementation; parties: Map<string, Party>; title: string }) {
  const byAgent = createdByAgent(impl.created_by_ref, parties);
  const owner = impl.owner_ref ? (parties.get(impl.owner_ref)?.name ?? impl.owner_ref) : "—";
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardAction className="font-mono text-xs text-muted-foreground" title="Sent as If-Match on the next write">
          modified {impl.modified.replace("T", " ").replace("Z", "")}
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {byAgent && (
          <div className="flex items-start gap-2 rounded-lg bg-muted px-3 py-2 text-xs">
            <Sparkles className="mt-0.5 size-3.5 shrink-0 text-agent" aria-hidden />
            <span>
              Drafted by <span className="font-medium">{parties.get(impl.created_by_ref!)?.name}</span>. An agent can only write{" "}
              <span className="font-mono">planned</span>; a person accepts the draft by editing it.
            </span>
          </div>
        )}
        <dl className="grid grid-cols-[8rem_minmax(0,1fr)] gap-y-1.5">
          <dt className="text-muted-foreground">Status</dt>
          <dd className="font-mono text-xs leading-5">{impl.status}</dd>
          <dt className="text-muted-foreground">Responsibility</dt>
          <dd>
            {impl.responsibility}
            {impl.origin === "provider" && <span className="text-muted-foreground"> · provider-authored</span>}
          </dd>
          {impl.component_ref && (
            <>
              <dt className="text-muted-foreground">Component</dt>
              <dd className="font-mono text-xs leading-5">{impl.component_ref}</dd>
            </>
          )}
          <dt className="text-muted-foreground">Owner</dt>
          <dd>{owner}</dd>
        </dl>
        {impl.narrative && <p className="leading-relaxed text-muted-foreground">{impl.narrative}</p>}
        {impl.customer_responsibility && (
          <p className="border-l-2 pl-3 text-xs leading-relaxed">
            <span className="text-muted-foreground">Customer responsibility: </span>
            {impl.customer_responsibility}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function Outcome({ outcome }: { outcome?: Result["outcome"] }) {
  const base = "mt-0.5 size-4 shrink-0";
  if (outcome === "pass") return <Check className={cn(base, "text-met")} aria-label="pass" />;
  if (outcome === "fail" || outcome === "error") return <X className={cn(base, "text-gap")} aria-label={outcome} />;
  return <Minus className={cn(base, "text-muted-foreground")} aria-label="no result" />;
}

function EvidenceIcon({ method }: { method: Evidence["method"] }) {
  const Icon = { automated: Workflow, upload: FileUp, attestation: PenLine, link: Link2 }[method];
  return <Icon className="size-4 shrink-0 text-muted-foreground" aria-label={method} />;
}

/** Expired, expiring within 30 days, or valid, relative to the evaluation date. */
function Validity({ until, at }: { until?: string; at: string }) {
  if (!until) return <span className="text-xs text-muted-foreground">no expiry</span>;
  const days = daysBetween(at, until);
  const tone = days < 0 ? "bg-gap-soft text-gap-ink" : days <= 30 ? "bg-waived-soft text-waived-ink" : "bg-met-soft text-met-ink";
  return (
    <span className={cn("rounded-full px-2 py-0.5 font-mono text-xs whitespace-nowrap", tone)} title={days < 0 ? `Expired ${-days} days ago` : `${days} days left`}>
      {isoDate(until)}
    </span>
  );
}
