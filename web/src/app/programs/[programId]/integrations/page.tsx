import type { Metadata } from "next";
import { CircleCheck, CircleDashed, CircleX, PauseCircle, Plug } from "lucide-react";

import { StatusBadge, type StatusTone } from "@/components/spectrumui/status-badge";
import { Eyebrow, PageTitle } from "@/components/typography";
import type { Connection } from "@/lib/api/types";
import { RuleEditorDialog, ruleSourcesOf } from "@/components/rule-editor-sources";
import { Button } from "@/components/ui/button";
import {
  getComponents,
  getConnections,
  getControls,
  getProgramStatus,
  getTests,
  getIntegrationVersions,
  getIntegrations,
  getProgram,
  getSnapshots,
  getSystems,
  getTemplateUpdates,
} from "@/lib/data";
import { isoDate } from "@/lib/format";

import {
  ApplyUpdateButton,
  ConnectionActions,
  EnableTemplateButton,
  EnableVersionButton,
  InstallIntegrationDialog,
  NewConnectionDialog,
  RemoveQueryButton,
} from "./integration-actions";
import { QueryEditorDialog, type QueryDraft } from "./query-editor";

export const metadata: Metadata = { title: "Integrations" };

const STATE: Record<Connection["state"], { tone: StatusTone; icon: typeof CircleCheck }> = {
  active: { tone: "met", icon: CircleCheck },
  failing: { tone: "gap", icon: CircleX },
  pending: { tone: "contribution", icon: CircleDashed },
  disabled: { tone: "waived", icon: PauseCircle },
};

const TIER_TONE: Record<string, StatusTone> = { "first-party": "met", verified: "contribution", local: "waived" };

/** An assistant's query source draft (RFC 0006 section 9), passed in the URL; nothing is saved yet. */
function parseDraft(raw: string | string[] | undefined): QueryDraft | undefined {
  if (typeof raw !== "string") return undefined;
  try {
    const value = JSON.parse(raw) as QueryDraft;
    return typeof value?.definition?.integration_id === "string" ? value : undefined;
  } catch {
    return undefined;
  }
}

export default async function IntegrationsPage({
  params,
  searchParams,
}: {
  params: Promise<{ programId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { programId } = await params;
  const draft = parseDraft((await searchParams).draft);
  const program = await getProgram(programId);
  const [integrations, connections, snapshots, components, systems] = await Promise.all([
    getIntegrations(),
    getConnections(),
    getSnapshots(),
    getComponents(),
    getSystems(),
  ]);

  const [status, controls, tests] = await Promise.all([getProgramStatus(programId), getControls(), getTests()]);
  const controlById = new Map(controls.map((c) => [c.id, c]));
  const inBaseline = new Set(status.controls.map((c) => c.control_id));
  const controlOptions = status.controls.map((c) => {
    const control = controlById.get(c.control_id);
    return { id: c.control_id, label: `${control?.display_id ?? c.control_id} · ${control?.name ?? ""}`.trim() };
  });
  const fulfillOptions = tests
    .filter((t) => !t.fulfills_ref && inBaseline.has(t.control_ref))
    .map((t) => ({ id: t.id, label: t.name ?? t.id, controlId: t.control_ref }));
  const ruleSources = ruleSourcesOf(integrations);
  const [versions, updates] = await Promise.all([
    Promise.all(integrations.map((i) => getIntegrationVersions(i.id))),
    Promise.all(integrations.map((i) => getTemplateUpdates(i.id))),
  ]);
  const versionsOf = new Map(integrations.map((i, n) => [i.id, versions[n]]));
  const updatesOf = new Map(integrations.map((i, n) => [i.id, updates[n]]));
  const integrationName = new Map(integrations.map((i) => [i.id, i.name]));
  const connectionName = new Map(connections.map((c) => [c.id, c.name]));
  const bindingName = new Map<string, string>([
    ...components.map((c): [string, string] => [c.id, c.name ?? c.id]),
    ...systems.map((s): [string, string] => [s.id, s.name ?? s.id]),
  ]);
  const bindingOptions = [...bindingName.entries()].map(([id, label]) => ({ id, label }));

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageTitle
        eyebrow={program.name}
        title="Integrations"
        aside={
          <div className="flex flex-wrap items-center gap-3">
            <p className="font-mono text-[11px] tracking-[0.12em] text-muted-foreground uppercase">
              {integrations.length} installed · {connections.length} connected
            </p>
            <InstallIntegrationDialog />
            {integrations.length > 0 && <NewConnectionDialog integrations={integrations} bindings={bindingOptions} />}
          </div>
        }
      />

      <section className="flex flex-col gap-3" aria-label="Connections">
        <Eyebrow>Connections</Eyebrow>
        {connections.length === 0 ? (
          <div className="rounded-2xl border border-dashed bg-card px-6 py-8 text-sm text-muted-foreground">
            No vendor accounts are connected. Connect one to collect live evidence.
          </div>
        ) : (
          <div className="overflow-hidden rounded-2xl border bg-card">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b bg-muted/30 font-mono text-[11px] tracking-[0.08em] text-muted-foreground uppercase">
                  <tr>
                    <th className="px-4 py-3 font-medium">Connection</th>
                    <th className="px-4 py-3 font-medium">State</th>
                    <th className="px-4 py-3 font-medium">Vendor identity</th>
                    <th className="px-4 py-3 font-medium">Bound to</th>
                    <th className="px-4 py-3 font-medium">Validated</th>
                    <th className="px-4 py-3 font-medium">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {connections.map((c) => {
                    const state = STATE[c.state];
                    return (
                      <tr key={c.id} className="align-top hover:bg-muted/20">
                        <td className="px-4 py-3">
                          <div className="font-medium">{c.name}</div>
                          <div className="font-mono text-[11px] text-muted-foreground">
                            {integrationName.get(c.integration_id) ?? c.integration_id} · {c.auth_kind}
                          </div>
                          {c.external_id && (
                            <div className="mt-1 max-w-56 font-mono text-[11px] break-all text-muted-foreground">
                              External ID <span className="text-foreground select-all">{c.external_id}</span>
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <StatusBadge tone={state.tone} icon={state.icon}>
                            {c.state}
                          </StatusBadge>
                        </td>
                        <td className="max-w-72 px-4 py-3 text-xs">
                          {c.last_error ? (
                            <span className="text-gap-ink">{c.last_error}</span>
                          ) : c.identity ? (
                            <span className="font-mono">{c.identity}</span>
                          ) : (
                            <span className="text-muted-foreground">Not validated</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-xs">
                          {c.bindings.length === 0
                            ? "—"
                            : c.bindings.map((b) => bindingName.get(b) ?? b).join(", ")}
                        </td>
                        <td className="px-4 py-3 font-mono text-xs whitespace-nowrap text-muted-foreground">
                          {c.last_validated ? isoDate(c.last_validated) : "—"}
                        </td>
                        <td className="px-4 py-3">
                          <ConnectionActions connection={c} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      <section className="flex flex-col gap-3" aria-label="Installed integrations">
        <Eyebrow>Installed integrations</Eyebrow>
        {integrations.length === 0 ? (
          <div className="rounded-2xl border border-dashed bg-card px-6 py-8 text-sm text-muted-foreground">
            No integration packages are installed in this deployment.
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {integrations.map((i) => (
              <article key={i.id} className="flex flex-col gap-4 rounded-2xl border bg-card p-5" aria-label={i.name}>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-2.5">
                    <Plug className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                    <div>
                      <h2 className="text-base font-medium">{i.name}</h2>
                      <p className="font-mono text-xs text-muted-foreground">
                        {i.id} · v{i.version}
                      </p>
                    </div>
                  </div>
                  <StatusBadge tone={TIER_TONE[i.tier] ?? "neutral"}>{i.tier}</StatusBadge>
                </div>
                {i.description && <p className="text-sm text-muted-foreground">{i.description}</p>}
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[11px] tracking-[0.1em] text-muted-foreground uppercase">
                      Collects
                    </span>
                    <RuleEditorDialog
                      sources={ruleSources}
                      controls={controlOptions}
                      fulfills={fulfillOptions}
                      initialSource={i.resources[0]?.source}
                      trigger={
                        <Button variant="ghost" size="xs" aria-label={`Write a rule on ${i.name}`}>
                          Write a rule
                        </Button>
                      }
                    />
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {i.resources.map((r) => (
                      <code key={r.source} className="rounded border bg-muted/40 px-1.5 py-0.5 font-mono text-[11px]">
                        {r.name}@{r.version}
                      </code>
                    ))}
                  </div>
                </div>
                {i.query_model && (
                  <div className="flex flex-col gap-1.5" aria-label={`${i.name} query sources`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[11px] tracking-[0.1em] text-muted-foreground uppercase">
                        Query sources · {i.query_model === "smithy" ? "AWS models" : "OpenAPI"}
                      </span>
                      <QueryEditorDialog
                        key={draft?.definition.integration_id === i.id ? JSON.stringify(draft) : "new"}
                        integration={i}
                        connections={connections.filter((c) => c.integration_id === i.id)}
                        draft={draft?.definition.integration_id === i.id ? draft : undefined}
                      />
                    </div>
                    {(i.queries ?? []).length === 0 ? (
                      <p className="text-xs text-muted-foreground">
                        None yet. Define one to read more from {i.name} without code.
                      </p>
                    ) : (
                      (i.queries ?? []).map((q) => (
                        <div key={q.id} className="flex items-center justify-between gap-3 text-xs">
                          <div className="min-w-0">
                            <code className="rounded border bg-muted/40 px-1.5 py-0.5 font-mono text-[11px]">
                              {q.name}@{q.version}
                            </code>{" "}
                            <span className="font-mono text-[11px] text-muted-foreground">{q.operation}</span>
                            {q.description && <div className="truncate text-muted-foreground">{q.description}</div>}
                          </div>
                          <RemoveQueryButton id={q.id} source={q.source} />
                        </div>
                      ))
                    )}
                  </div>
                )}
                {(versionsOf.get(i.id)?.length ?? 0) > 0 && (
                  <div className="flex flex-col gap-1.5" aria-label={`${i.name} versions`}>
                    <span className="font-mono text-[11px] tracking-[0.1em] text-muted-foreground uppercase">
                      Installed versions
                    </span>
                    {versionsOf.get(i.id)!.map((v) => (
                      <div key={v.version} className="flex items-center justify-between gap-3 text-xs">
                        <span className="font-mono">
                          v{v.version} <span className="text-muted-foreground">· {isoDate(v.installed)}</span>
                        </span>
                        {v.enabled ? (
                          <StatusBadge tone="met" icon={CircleCheck}>
                            enabled
                          </StatusBadge>
                        ) : (
                          <EnableVersionButton integrationId={i.id} version={v.version} />
                        )}
                      </div>
                    ))}
                  </div>
                )}
                {(updatesOf.get(i.id)?.length ?? 0) > 0 && (
                  <div
                    className="flex flex-col gap-2 rounded-xl border border-waived/40 bg-waived-soft/40 p-3"
                    aria-label={`${i.name} template updates`}
                  >
                    <span className="font-mono text-[11px] tracking-[0.1em] text-waived-ink uppercase">
                      Template updates
                    </span>
                    {updatesOf.get(i.id)!.map((u) => (
                      <div key={u.test_id} className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate text-sm">{u.test_name}</div>
                          <div className="truncate font-mono text-[11px] text-muted-foreground">
                            v{u.from_version ?? "?"} → v{u.to_version} · changes {u.changes.join(", ") || "none"}
                          </div>
                        </div>
                        <ApplyUpdateButton
                          integrationId={i.id}
                          testId={u.test_id}
                          testName={u.test_name}
                          modified={u.modified}
                        />
                      </div>
                    ))}
                  </div>
                )}
                {i.templates.length > 0 && (
                  <div className="flex flex-col gap-2 border-t pt-3">
                    <span className="font-mono text-[11px] tracking-[0.1em] text-muted-foreground uppercase">
                      Test templates
                    </span>
                    {i.templates.map((t) => (
                      <div key={t.name} className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate text-sm">{t.test_name ?? t.name}</div>
                          <div className="truncate font-mono text-[11px] text-muted-foreground">
                            {t.runner} · fulfills {t.fulfills_ref ?? "—"}
                          </div>
                        </div>
                        <EnableTemplateButton integrationId={i.id} name={t.name} label={t.test_name ?? t.name} />
                      </div>
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="flex flex-col gap-3" aria-label="Recent snapshots">
        <Eyebrow>Recent snapshots</Eyebrow>
        <div className="overflow-hidden rounded-2xl border bg-card">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-muted/30 font-mono text-[11px] tracking-[0.08em] text-muted-foreground uppercase">
                <tr>
                  <th className="px-4 py-3 font-medium">Source</th>
                  <th className="px-4 py-3 font-medium">Connection</th>
                  <th className="px-4 py-3 font-medium">Collected</th>
                  <th className="px-4 py-3 font-medium">Items</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {snapshots.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-6 text-center text-sm text-muted-foreground">
                      No snapshots collected yet.
                    </td>
                  </tr>
                )}
                {snapshots.slice(0, 20).map((s) => (
                  <tr key={s.id} className="hover:bg-muted/20">
                    <td className="px-4 py-3 font-mono text-xs">{s.source}</td>
                    <td className="px-4 py-3 text-xs">{connectionName.get(s.connection_id) ?? s.connection_id}</td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{isoDate(s.collected)}</td>
                    <td className="px-4 py-3 font-mono text-xs tabular-nums">{s.item_count}</td>
                    <td className="px-4 py-3 text-xs">
                      {s.complete ? (
                        <StatusBadge tone="met" icon={CircleCheck}>
                          complete
                        </StatusBadge>
                      ) : (
                        <span className="inline-flex flex-wrap items-center gap-1.5">
                          <StatusBadge tone="gap" icon={CircleX}>
                            incomplete
                          </StatusBadge>
                          <span className="text-muted-foreground">{s.reason}</span>
                        </span>
                      )}
                      {s.warnings?.map((w) => (
                        <div key={w} className="mt-1 text-[11px] text-waived-ink">
                          {w}
                        </div>
                      ))}
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
