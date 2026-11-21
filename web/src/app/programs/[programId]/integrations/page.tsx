import type { Metadata } from "next";
import { CircleCheck, CircleDashed, CircleX, PauseCircle, Plug } from "lucide-react";

import { StatusBadge, type StatusTone } from "@/components/spectrumui/status-badge";
import { Eyebrow, PageTitle } from "@/components/typography";
import type { Connection } from "@/lib/api/types";
import { getComponents, getConnections, getIntegrations, getProgram, getSnapshots, getSystems } from "@/lib/data";
import { isoDate } from "@/lib/format";

import { ConnectionActions, EnableTemplateButton, NewConnectionDialog } from "./integration-actions";

export const metadata: Metadata = { title: "Integrations" };

const STATE: Record<Connection["state"], { tone: StatusTone; icon: typeof CircleCheck }> = {
  active: { tone: "met", icon: CircleCheck },
  failing: { tone: "gap", icon: CircleX },
  pending: { tone: "contribution", icon: CircleDashed },
  disabled: { tone: "waived", icon: PauseCircle },
};

const TIER_TONE: Record<string, StatusTone> = { "first-party": "met", verified: "contribution", local: "waived" };

export default async function IntegrationsPage({ params }: { params: Promise<{ programId: string }> }) {
  const { programId } = await params;
  const program = await getProgram(programId);
  const [integrations, connections, snapshots, components, systems] = await Promise.all([
    getIntegrations(),
    getConnections(),
    getSnapshots(),
    getComponents(),
    getSystems(),
  ]);

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
                            {integrationName.get(c.integration_id) ?? c.integration_id}
                          </div>
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
                        <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
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
                  <span className="font-mono text-[11px] tracking-[0.1em] text-muted-foreground uppercase">Collects</span>
                  <div className="flex flex-wrap gap-1.5">
                    {i.resources.map((r) => (
                      <code key={r.source} className="rounded border bg-muted/40 px-1.5 py-0.5 font-mono text-[11px]">
                        {r.name}@{r.version}
                      </code>
                    ))}
                  </div>
                </div>
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
