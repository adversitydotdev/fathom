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
import Link from "next/link";
import { cn } from "cn";

import { AskAgentButton } from "@/components/agent/assistant-drawer";
import { InlineCode } from "@/components/spectrumui/inline-code";
import { ControlStateBadge } from "@/components/status";
import { PageTitle } from "@/components/typography";
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

import {
  AcceptDraftButton,
  CustomControlActions,
  ImplementationCrudButton,
  QuickAddEvidenceButton,
  RecordManualResultButton,
} from "./control-crud";
import { RunTestButton } from "./run-test-button";

/**
 * Everything about one control on one program. Rendered as a full page on
 * direct loads, and as the right-side panel when a control link is clicked
 * inside the app (see `@panel/(.)controls/[controlId]`).
 */
export async function ControlDetail({
  programId,
  controlId,
  atParam,
  variant,
}: {
  programId: string;
  controlId: string;
  atParam?: string;
  variant: "page" | "panel";
}) {
  const panel = variant === "panel";
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
  const partyOptions = [...parties.values()].map((p) => ({ id: p.id, name: p.name ?? p.id }));

  const meta = (
    <div className="flex flex-wrap items-center gap-3">
      {entry && <ControlStateBadge state={entry.state} />}
      <span className="text-xs font-medium text-muted-foreground">
        {control.family} · {control.control_type} · {control.frequency} · {control.origin === "custom" ? "custom" : "library"}
      </span>
    </div>
  );
  const customActions =
    control.origin === "custom" ? <CustomControlActions control={control} backHref={backHref} /> : undefined;

  return (
    <div className={panel ? "flex flex-col gap-5" : "mx-auto flex max-w-6xl flex-col gap-6"}>
      <div>
        {panel ? (
          <div className="flex flex-col gap-1.5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="font-mono text-xs text-muted-foreground">{control.display_id}</div>
                <h2 id="control-panel-title" className="mt-1 text-xl leading-tight font-semibold tracking-tight">
                  {control.name}
                </h2>
              </div>
              {customActions}
            </div>
            {meta}
          </div>
        ) : (
          <PageTitle
            eyebrow={
              <nav aria-label="Breadcrumb">
                <Link href={backHref} className="hover:text-foreground">
                  Controls
                </Link>{" "}
                / <span className="text-foreground">{control.display_id}</span>
              </nav>
            }
            title={control.name}
            aside={customActions}
          >
            {meta}
          </PageTitle>
        )}
        {entry && entry.failed && entry.failed.length > 0 && (
          <div className="mt-4 flex flex-col gap-1 rounded-xl border border-gap/30 bg-gap-soft px-4 py-3 text-sm text-gap-ink" role="status">
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

      <div className={panel ? "flex flex-col gap-5" : "grid gap-6 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]"}>
        <div className={panel ? "contents" : "flex flex-col gap-6"}>
          <Card className="order-4">
            <CardHeader>
              <CardTitle>Statement</CardTitle>
              <CardAction>
                <InlineCode className="text-xs font-normal text-muted-foreground">{control.id}</InlineCode>
              </CardAction>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 leading-relaxed">
              <Statement text={control.statement} parameters={control.parameters} values={systemImpl?.parameter_values} />
              {control.guidance && <p className="text-sm text-muted-foreground">{control.guidance}</p>}
            </CardContent>
          </Card>

          {systemImpl ? (
            <ImplementationCard
              className="order-5"
              impl={systemImpl}
              parties={parties}
              title="Implementation"
              action={
                <div className="flex items-center gap-1.5">
                  {systemImpl.status === "planned" && (
                    <AskAgentButton
                      label="Draft with AI"
                      prompt={`Inspect control ${control.display_id ?? control.id} (${control.name}) on system ${system.id} and refine its planned implementation narrative and parameter values for human review.`}
                    />
                  )}
                  <ImplementationCrudButton
                    systemId={system.id}
                    controlId={control.id}
                    parameters={control.parameters}
                    parties={partyOptions}
                    existing={systemImpl}
                  />
                </div>
              }
            />
          ) : (
            <Card className="order-5">
              <CardHeader>
                <CardTitle>Implementation</CardTitle>
                <CardAction className="flex items-center gap-1.5">
                  <AskAgentButton
                    label="Draft with AI"
                    prompt={`Inspect control ${control.display_id ?? control.id} (${control.name}) on system ${system.id} and draft a planned implementation narrative with suggested parameter values.`}
                  />
                  <ImplementationCrudButton
                    systemId={system.id}
                    controlId={control.id}
                    parameters={control.parameters}
                    parties={partyOptions}
                  />
                </CardAction>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">
                {system.name} has no implementation of this control yet. Add one manually or let AI draft a{" "}
                <span className="font-mono text-xs">planned</span> narrative for your review.
              </CardContent>
            </Card>
          )}

          {providerHalves.map((impl) => (
            <ImplementationCard className="order-6" key={impl.id} impl={impl} parties={parties} title="Provider's half" />
          ))}
        </div>

        <div className={panel ? "contents" : "flex flex-col gap-6"}>
          <Card className="order-1">
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
                            {t.method} · {t.interval}
                            {r ? <> · {r.outcome} {isoDate(r.observed)}</> : t.method === "automated" && !t.run ? " · no methodology defined" : " · no result"}
                          </div>
                          {r?.summary && r.outcome !== "pass" && <div className="mt-1 text-xs text-gap-ink">{r.summary}</div>}
                        </div>
                        {t.run && systemImpl && <RunTestButton testId={t.id} implementationId={systemImpl.id} />}
                        {t.method === "manual" && systemImpl && (
                          <RecordManualResultButton
                            testId={t.id}
                            testName={t.name ?? t.id}
                            implementationId={systemImpl.id}
                          />
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card className="order-2">
            <CardHeader>
              <CardTitle>Evidence</CardTitle>
              <CardAction className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>valid until</span>
                {systemImpl && <QuickAddEvidenceButton implementationId={systemImpl.id} />}
              </CardAction>
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
            <Card className="order-3">
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

          <Card className="order-7">
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

function ImplementationCard({
  impl,
  parties,
  title,
  action,
  className,
}: {
  impl: Implementation;
  parties: Map<string, Party>;
  title: string;
  action?: React.ReactNode;
  className?: string;
}) {
  const byAgent = createdByAgent(impl.created_by_ref, parties);
  const owner = impl.owner_ref ? (parties.get(impl.owner_ref)?.name ?? impl.owner_ref) : "—";
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardAction className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground tabular-nums" title="Sent as If-Match on the next write">
            Modified {impl.modified.replace("T", " ").replace(/(\.\d+)?Z$/, "")}
          </span>
          {action}
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {byAgent && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-agent/25 bg-agent/8 px-3 py-2 text-xs">
            <span className="flex items-start gap-2">
              <Sparkles className="mt-0.5 size-3.5 shrink-0 text-agent" aria-hidden />
              <span>
                Drafted by <span className="font-medium">{parties.get(impl.created_by_ref!)?.name}</span>. An agent can only write{" "}
                <span className="font-mono">planned</span>; a person accepts the draft by attesting or editing it.
              </span>
            </span>
            {impl.status === "planned" && <AcceptDraftButton id={impl.id} modified={impl.modified} />}
          </div>
        )}
        <dl className="grid grid-cols-[8rem_minmax(0,1fr)] gap-y-1.5">
          <dt className="text-muted-foreground">Status</dt>
          <dd className="capitalize">{impl.status}</dd>
          <dt className="text-muted-foreground">Responsibility</dt>
          <dd>
            {impl.responsibility}
            {impl.origin === "provider" && <span className="text-muted-foreground"> · provider-authored</span>}
          </dd>
          {impl.component_ref && (
            <>
              <dt className="text-muted-foreground">Component</dt>
              <dd>
                <InlineCode className="text-xs font-normal">{impl.component_ref}</InlineCode>
              </dd>
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
