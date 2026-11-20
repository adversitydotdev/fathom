"use client";

import { Pencil, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { CrudDialog, Field, FormActions, FormError, RevokeButton, Select, Textarea } from "@/components/crud";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  createComponent,
  createProgram,
  createSystem,
  revokeComponent,
  updateComponent,
  updateSystem,
} from "@/lib/actions";
import type { Component } from "@/lib/api/types";

export type Option = { id: string; label: string };

const COMPONENT_KINDS: Component["kind"][] = [
  "service",
  "infrastructure",
  "software",
  "data",
  "people",
  "procedure",
];

export function SystemCrudDialog({
  existing,
}: {
  existing?: {
    id: string;
    modified: string;
    name: string;
    function?: string;
    boundary?: string;
  };
}) {
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  const [error, setError] = useState<string>();

  const [name, setName] = useState(existing?.name ?? "");
  const [fn, setFn] = useState(existing?.function ?? "");
  const [boundary, setBoundary] = useState(existing?.boundary ?? "");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    start(async () => {
      const payload = {
        name: name.trim(),
        function: fn.trim() || undefined,
        boundary: boundary.trim() || undefined,
      };
      const res = existing
        ? await updateSystem(existing.id, existing.modified, payload)
        : await createSystem(payload);
      if (res.error) {
        setError(res.error);
        return;
      }
      if (!existing) {
        setName("");
        setFn("");
        setBoundary("");
      }
      setOpen(false);
    });
  }

  return (
    <CrudDialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) setError(undefined);
      }}
      title={existing ? "Edit system" : "New system"}
      description="System profile and authorization boundary used in SSP and OSCAL renders."
      trigger={
        existing ? (
          <Button size="xs" variant="outline" className="gap-1">
            <Pencil className="size-3" aria-hidden />
            Edit system
          </Button>
        ) : (
          <Button size="sm" variant="outline" className="gap-1.5">
            <Plus className="size-3.5" aria-hidden />
            New system
          </Button>
        )
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <FormError error={error} />
        <Field label="System name" htmlFor="sys-name" required>
          <Input id="sys-name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Internal Data Warehouse" />
        </Field>
        <Field label="Function" htmlFor="sys-fn">
          <Textarea id="sys-fn" value={fn} onChange={(e) => setFn(e.target.value)} />
        </Field>
        <Field label="Authorization boundary" htmlFor="sys-bound">
          <Textarea id="sys-bound" value={boundary} onChange={(e) => setBoundary(e.target.value)} />
        </Field>
        <FormActions pending={pending} submitLabel={existing ? "Save changes" : "Create system"} onCancel={() => setOpen(false)} />
      </form>
    </CrudDialog>
  );
}

export function ComponentCrudDialog({
  parties,
  attachToSystem,
  existing,
}: {
  parties: Option[];
  attachToSystem?: { id: string; modified: string; currentRefs: string[] };
  existing?: {
    id: string;
    modified: string;
    name: string;
    kind: Component["kind"];
    partyId?: string;
    description?: string;
  };
}) {
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  const [error, setError] = useState<string>();

  const [name, setName] = useState(existing?.name ?? "");
  const [kind, setKind] = useState<Component["kind"]>(existing?.kind ?? "service");
  const [partyRef, setPartyRef] = useState(existing?.partyId ?? "");
  const [description, setDescription] = useState(existing?.description ?? "");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    start(async () => {
      const payload = {
        name: name.trim(),
        kind,
        party_ref: partyRef || undefined,
        description: description.trim() || undefined,
      };
      const res = existing
        ? await updateComponent(existing.id, existing.modified, payload)
        : await createComponent(payload, attachToSystem);
      if (res.error) {
        setError(res.error);
        return;
      }
      if (!existing) {
        setName("");
        setDescription("");
      }
      setOpen(false);
    });
  }

  return (
    <div className="inline-flex items-center gap-1">
      <CrudDialog
        open={open}
        onOpenChange={(v) => {
          setOpen(v);
          if (!v) setError(undefined);
        }}
        title={existing ? "Edit component" : "New component"}
        description="Components are attached to the active system's authorization boundary."
        trigger={
          existing ? (
            <Button size="icon-xs" variant="ghost" aria-label={`Edit ${existing.name}`} title="Edit component">
              <Pencil className="size-3.5" aria-hidden />
            </Button>
          ) : (
            <Button size="xs" variant="outline" className="gap-1">
              <Plus className="size-3" aria-hidden />
              Add component
            </Button>
          )
        }
      >
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <FormError error={error} />
          <Field label="Name" htmlFor="comp-name" required>
            <Input id="comp-name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="GitHub Actions CI/CD" />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Kind" htmlFor="comp-kind" required>
              <Select id="comp-kind" value={kind} onChange={(e) => setKind(e.target.value as Component["kind"])}>
                {COMPONENT_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Provider / Party" htmlFor="comp-party">
              <Select id="comp-party" value={partyRef} onChange={(e) => setPartyRef(e.target.value)}>
                <option value="">None</option>
                {parties.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label="Description" htmlFor="comp-desc">
            <Textarea id="comp-desc" value={description} onChange={(e) => setDescription(e.target.value)} className="min-h-16" />
          </Field>
          <FormActions pending={pending} submitLabel={existing ? "Save changes" : "Add component"} onCancel={() => setOpen(false)} />
        </form>
      </CrudDialog>
      {existing && (
        <RevokeButton
          compact
          label={`Revoke ${existing.name}`}
          onRevoke={() => revokeComponent(existing.id, existing.modified)}
        />
      )}
    </div>
  );
}

export function NewProgramDialog({
  systems,
  baselines,
  defaultSystemId,
}: {
  systems: Option[];
  baselines: Option[];
  defaultSystemId?: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  const [error, setError] = useState<string>();

  const [name, setName] = useState("");
  const [systemRef, setSystemRef] = useState(defaultSystemId ?? systems[0]?.id ?? "");
  const [baselineRef, setBaselineRef] = useState(baselines[0]?.id ?? "");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    start(async () => {
      const res = await createProgram({
        name: name.trim(),
        system_ref: systemRef,
        baseline_ref: baselineRef,
      });
      if (res.error) {
        setError(res.error);
        return;
      }
      setName("");
      setOpen(false);
      if (res.id) router.push(`/programs/${res.id}`);
    });
  }

  return (
    <CrudDialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) setError(undefined);
      }}
      title="New program"
      description="Bind a system to a control baseline."
      trigger={
        <Button size="sm" variant="outline" className="gap-1.5">
          <Plus className="size-3.5" aria-hidden />
          New program
        </Button>
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <FormError error={error} />
        <Field label="Program name" htmlFor="prog-name" required>
          <Input id="prog-name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="ISO 27001 Readiness" />
        </Field>
        <Field label="System" htmlFor="prog-sys" required>
          <Select id="prog-sys" value={systemRef} onChange={(e) => setSystemRef(e.target.value)}>
            {systems.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Baseline" htmlFor="prog-base" required>
          <Select id="prog-base" value={baselineRef} onChange={(e) => setBaselineRef(e.target.value)}>
            {baselines.map((b) => (
              <option key={b.id} value={b.id}>
                {b.label}
              </option>
            ))}
          </Select>
        </Field>
        <FormActions pending={pending} submitLabel="Create program" onCancel={() => setOpen(false)} />
      </form>
    </CrudDialog>
  );
}
