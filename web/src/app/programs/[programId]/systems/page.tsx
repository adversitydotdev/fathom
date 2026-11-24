import type { Metadata } from "next";
import { Boxes, Cloud, ShieldCheck } from "lucide-react";

import { StatusBadge } from "@/components/spectrumui/status-badge";
import { Eyebrow, PageTitle } from "@/components/typography";
import {
  getBaselines,
  getComponents,
  getParties,
  getProgram,
  getProviders,
  getSystem,
  getSystems,
} from "@/lib/data";

import { ComponentCrudDialog, NewProgramDialog, SystemCrudDialog } from "./system-crud";

export const metadata: Metadata = { title: "Systems" };

function CiaBadge({ label, level }: { label: string; level?: string }) {
  if (!level) return null;
  const tone = level === "high" ? "gap" : level === "moderate" ? "waived" : "met";
  return (
    <StatusBadge tone={tone}>
      {label}: {level}
    </StatusBadge>
  );
}

export default async function SystemsPage({
  params,
}: {
  params: Promise<{ programId: string }>;
}) {
  const { programId } = await params;

  const program = await getProgram(programId);
  const [activeSystem, systems, components, baselines, providersRes, parties] = await Promise.all([
    getSystem(program.system_ref),
    getSystems(),
    getComponents(),
    getBaselines(),
    getProviders(),
    getParties(),
  ]);

  const providers = providersRes.data ?? [];
  const componentById = new Map(components.map((c) => [c.id, c]));
  const partyOptions = [...parties.values()].map((p) => ({ id: p.id, label: p.name ?? p.id }));
  const systemOptions = systems.map((s) => ({ id: s.id, label: s.name ?? s.id }));
  const baselineOptions = baselines.map((b) => ({ id: b.id, label: b.name ?? b.id }));

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageTitle
        eyebrow={program.name}
        title="Systems"
        aside={
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-xs font-medium text-muted-foreground">
              {systems.length} {systems.length === 1 ? "system" : "systems"} · {components.length} components ·{" "}
              {providers.length} provider bundles
            </p>
            <SystemCrudDialog />
            <NewProgramDialog
              systems={systemOptions}
              baselines={baselineOptions}
              defaultSystemId={activeSystem.id}
            />
          </div>
        }
      />

      <section className="flex flex-col gap-4 rounded-xl border bg-card p-6" aria-label="Active system">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex flex-col gap-1">
            <Eyebrow>Program system</Eyebrow>
            <h2 className="text-2xl font-semibold tracking-tight">{activeSystem.name}</h2>
          </div>
          <div className="flex items-center gap-3">
            <span className="font-mono text-xs text-muted-foreground">{activeSystem.id}</span>
            <SystemCrudDialog
              existing={{
                id: activeSystem.id,
                modified: activeSystem.modified,
                name: activeSystem.name ?? activeSystem.id,
                function: activeSystem.function,
                boundary: activeSystem.boundary,
              }}
            />
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          {activeSystem.function && (
            <div className="flex flex-col gap-1.5 rounded-xl border bg-background/40 p-4">
              <span className="text-xs font-medium text-muted-foreground">Function</span>
              <p className="text-sm">{activeSystem.function}</p>
            </div>
          )}
          {activeSystem.boundary && (
            <div className="flex flex-col gap-1.5 rounded-xl border bg-background/40 p-4">
              <span className="text-xs font-medium text-muted-foreground">
                Authorization boundary
              </span>
              <p className="text-sm">{activeSystem.boundary}</p>
            </div>
          )}
        </div>

        {(activeSystem.information_types?.length ?? 0) > 0 && (
          <div className="flex flex-col gap-2">
            <span className="text-xs font-medium text-muted-foreground">
              Information types (FIPS 199)
            </span>
            <div className="flex flex-col gap-2">
              {activeSystem.information_types!.map((info) => (
                <div
                  key={info.name}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-background/40 px-4 py-3"
                >
                  <span className="text-sm font-medium">{info.name}</span>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <CiaBadge label="C" level={info.confidentiality} />
                    <CiaBadge label="I" level={info.integrity} />
                    <CiaBadge label="A" level={info.availability} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {(activeSystem.parties?.length ?? 0) > 0 && (
          <div className="flex flex-col gap-2">
            <span className="text-xs font-medium text-muted-foreground">
              System parties & leveraged services
            </span>
            <div className="grid gap-2 sm:grid-cols-3">
              {activeSystem.parties!.map((sp) => (
                <div
                  key={`${sp.party_ref}-${sp.role}`}
                  className="flex flex-col gap-1 rounded-xl border bg-background/40 px-4 py-3"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium">
                      {parties.get(sp.party_ref)?.name ?? sp.party_ref}
                    </span>
                    <StatusBadge tone="neutral">{sp.role}</StatusBadge>
                  </div>
                  {sp.function && <p className="text-xs text-muted-foreground">{sp.function}</p>}
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="flex flex-col gap-3 rounded-xl border bg-card p-5" aria-label="Components">
          <div className="flex items-center justify-between gap-2">
            <Eyebrow>Components</Eyebrow>
            <div className="flex items-center gap-2">
              <ComponentCrudDialog
                parties={partyOptions}
                attachToSystem={{
                  id: activeSystem.id,
                  modified: activeSystem.modified,
                  currentRefs: activeSystem.component_refs ?? [],
                }}
              />
              <Boxes className="size-4 text-muted-foreground" aria-hidden />
            </div>
          </div>
          <div className="divide-y">
            {(activeSystem.component_refs ?? []).map((cid) => {
              const comp = componentById.get(cid);
              if (!comp) return null;
              const provider = comp.party_ref ? parties.get(comp.party_ref)?.name : undefined;
              return (
                <div key={comp.id} className="flex items-center justify-between gap-3 py-3 first:pt-1 last:pb-0">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{comp.name}</div>
                    <div className="font-mono text-xs text-muted-foreground">
                      {comp.kind}
                      {provider ? ` · ${provider}` : ""}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[11px] text-muted-foreground">{comp.id}</span>
                    <ComponentCrudDialog
                      parties={partyOptions}
                      existing={{
                        id: comp.id,
                        modified: comp.modified,
                        name: comp.name ?? comp.id,
                        kind: comp.kind,
                        partyId: comp.party_ref,
                        description: comp.description,
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <section className="flex flex-col gap-3 rounded-xl border bg-card p-5" aria-label="Provider bundles">
          <div className="flex items-center justify-between">
            <Eyebrow>Imported provider bundles</Eyebrow>
            <Cloud className="size-4 text-muted-foreground" aria-hidden />
          </div>
          {providers.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">No provider responsibility bundles imported yet.</p>
          ) : (
            <div className="divide-y">
              {providers.map((bundle) => (
                <div key={bundle.id} className="flex flex-col gap-1.5 py-3 first:pt-1 last:pb-0">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-sm font-medium">{bundle.name}</span>
                    <StatusBadge tone="met" icon={ShieldCheck}>
                      v{bundle.version}
                    </StatusBadge>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-xs text-muted-foreground">
                    <span>{bundle.kind ?? "ogrl"}</span>
                    <span>{bundle.id}</span>
                    {bundle.digest && (
                      <span className="truncate" title={bundle.digest}>
                        {bundle.digest.slice(0, 20)}…
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
