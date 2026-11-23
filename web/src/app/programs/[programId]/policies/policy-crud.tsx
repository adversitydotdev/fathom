"use client";

import { Pencil, Plus } from "lucide-react";
import { useEffect, useState, useTransition } from "react";

import { CrudDialog, Field, FormActions, FormError, RevokeButton, Select } from "@/components/crud";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RichTextEditor } from "@/components/rich-text-editor";
import {
  getDocumentBody,
  createPolicy,
  createProcedure,
  revokePolicy,
  revokeProcedure,
  updatePolicy,
  updateProcedure,
} from "@/lib/actions";
import type { Policy, Procedure } from "@/lib/api/types";

export type Option = { id: string; label: string };

/** Loads the stored body into the editor when an existing document's dialog opens. */
function useStoredBody(kind: "policies" | "procedures", open: boolean, id: string | undefined, hasResource: boolean, set: (md: string) => void) {
  const [original, setOriginal] = useState<string>();
  useEffect(() => {
    if (!open || !id || !hasResource) return;
    let live = true;
    getDocumentBody(kind, id).then(({ body }) => {
      if (!live) return;
      set(body);
      setOriginal(body);
    });
    return () => {
      live = false;
    };
  }, [kind, open, id, hasResource, set]);
  const loading = open && Boolean(id) && hasResource && original === undefined;
  return { loading, original };
}

const DOC_STATUSES: Policy["status"][] = ["draft", "adopted", "retired"];

export function PolicyCrudDialog({
  parties,
  controls,
  existing,
}: {
  parties: Option[];
  controls: Option[];
  existing?: {
    id: string;
    modified: string;
    name: string;
    status: Policy["status"];
    version?: string;
    ownerId?: string;
    reviewInterval?: string;
    controlIds: string[];
    hasResource: boolean;
  };
}) {
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  const [error, setError] = useState<string>();

  const [name, setName] = useState(existing?.name ?? "");
  const [status, setStatus] = useState<Policy["status"]>(existing?.status ?? "draft");
  const [version, setVersion] = useState(existing?.version ?? "1.0");
  const [ownerRef, setOwnerRef] = useState(existing?.ownerId ?? "");
  const [reviewInterval, setReviewInterval] = useState(existing?.reviewInterval ?? "annual");
  const [controlRef, setControlRef] = useState(existing?.controlIds[0] ?? "");
  const [contentMd, setContentMd] = useState("");
  const { loading, original } = useStoredBody("policies", open, existing?.id, Boolean(existing?.hasResource), setContentMd);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    start(async () => {
      const payload = {
        name: name.trim(),
        status,
        version: version.trim() || undefined,
        owner_ref: ownerRef || undefined,
        review_interval: reviewInterval.trim() || undefined,
        control_refs: controlRef ? [controlRef] : [],
      };
      const md =
        (contentMd.trim() && contentMd !== original ? contentMd : undefined) ||
        (status === "adopted" && !existing?.hasResource
          ? `# ${name.trim()} v${version.trim() || "1.0"}\n\nAdopted security policy.\n`
          : undefined);

      const res = existing
        ? await updatePolicy(existing.id, existing.modified, payload, md)
        : await createPolicy(payload, md);
      if (res.error) {
        setError(res.error);
        return;
      }
      if (!existing) {
        setName("");
        setContentMd("");
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
        title={existing ? "Edit policy" : "New policy"}
        size="md"
        description="Adopting a policy stores its text and records the SHA-256 digest."
        trigger={
          existing ? (
            <Button size="icon-xs" variant="ghost" aria-label={`Edit ${existing.name}`} title="Edit policy">
              <Pencil className="size-3.5" aria-hidden />
            </Button>
          ) : (
            <Button size="sm" variant="outline" className="gap-1.5">
              <Plus className="size-3.5" aria-hidden />
              New policy
            </Button>
          )
        }
      >
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <FormError error={error} />
          <Field label="Name" htmlFor="pol-name" required>
            <Input id="pol-name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Data Classification Policy" />
          </Field>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Status" htmlFor="pol-status" required>
              <Select id="pol-status" value={status} onChange={(e) => setStatus(e.target.value as Policy["status"])}>
                {DOC_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Version" htmlFor="pol-ver">
              <Input id="pol-ver" value={version} onChange={(e) => setVersion(e.target.value)} />
            </Field>
            <Field label="Review interval" htmlFor="pol-int">
              <Input id="pol-int" value={reviewInterval} onChange={(e) => setReviewInterval(e.target.value)} />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Owner" htmlFor="pol-owner">
              <Select id="pol-owner" value={ownerRef} onChange={(e) => setOwnerRef(e.target.value)}>
                <option value="">Unassigned</option>
                {parties.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Linked control" htmlFor="pol-ctrl">
              <Select id="pol-ctrl" value={controlRef} onChange={(e) => setControlRef(e.target.value)}>
                <option value="">None</option>
                {controls.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label="Policy text" htmlFor="pol-body" hint={loading ? "Loading the current text…" : "Saved with a SHA-256 digest. Required before adoption."}>
            <RichTextEditor
              id="pol-body"
              label="Policy text"
              value={contentMd}
              onChange={setContentMd}
              placeholder="Write the policy: purpose, scope, and the rules people follow…"
            />
          </Field>
          <FormActions pending={pending} submitLabel={existing ? "Save changes" : "Create policy"} onCancel={() => setOpen(false)} />
        </form>
      </CrudDialog>
      {existing && (
        <RevokeButton
          compact
          label={`Revoke ${existing.name}`}
          onRevoke={() => revokePolicy(existing.id, existing.modified)}
        />
      )}
    </div>
  );
}

export function ProcedureCrudDialog({
  policies,
  parties,
  controls,
  existing,
}: {
  policies: Option[];
  parties: Option[];
  controls: Option[];
  existing?: {
    id: string;
    modified: string;
    name: string;
    status: Procedure["status"];
    policyId?: string;
    ownerId?: string;
    controlIds: string[];
    hasResource: boolean;
  };
}) {
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  const [error, setError] = useState<string>();

  const [name, setName] = useState(existing?.name ?? "");
  const [status, setStatus] = useState<Procedure["status"]>(existing?.status ?? "draft");
  const [policyRef, setPolicyRef] = useState(existing?.policyId ?? policies[0]?.id ?? "");
  const [ownerRef, setOwnerRef] = useState(existing?.ownerId ?? "");
  const [controlRef, setControlRef] = useState(existing?.controlIds[0] ?? "");
  const [contentMd, setContentMd] = useState("");
  const { loading, original } = useStoredBody("procedures", open, existing?.id, Boolean(existing?.hasResource), setContentMd);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    start(async () => {
      const payload = {
        name: name.trim(),
        status,
        policy_ref: policyRef || undefined,
        owner_ref: ownerRef || undefined,
        control_refs: controlRef ? [controlRef] : [],
      };
      const md =
        (contentMd.trim() && contentMd !== original ? contentMd : undefined) ||
        (status === "adopted" && !existing?.hasResource
          ? `# ${name.trim()}\n\nAdopted operating procedure.\n`
          : undefined);

      const res = existing
        ? await updateProcedure(existing.id, existing.modified, payload, md)
        : await createProcedure(payload, md);
      if (res.error) {
        setError(res.error);
        return;
      }
      if (!existing) {
        setName("");
        setContentMd("");
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
        size="md"
        title={existing ? "Edit procedure" : "New procedure"}
        trigger={
          existing ? (
            <Button size="icon-xs" variant="ghost" aria-label={`Edit ${existing.name}`} title="Edit procedure">
              <Pencil className="size-3.5" aria-hidden />
            </Button>
          ) : (
            <Button size="sm" variant="outline" className="gap-1.5">
              <Plus className="size-3.5" aria-hidden />
              New procedure
            </Button>
          )
        }
      >
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <FormError error={error} />
          <Field label="Name" htmlFor="proc-name" required>
            <Input id="proc-name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Key Rotation Runbook" />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Parent policy" htmlFor="proc-pol">
              <Select id="proc-pol" value={policyRef} onChange={(e) => setPolicyRef(e.target.value)}>
                <option value="">None</option>
                {policies.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Status" htmlFor="proc-status" required>
              <Select id="proc-status" value={status} onChange={(e) => setStatus(e.target.value as Procedure["status"])}>
                {DOC_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Owner" htmlFor="proc-owner">
              <Select id="proc-owner" value={ownerRef} onChange={(e) => setOwnerRef(e.target.value)}>
                <option value="">Unassigned</option>
                {parties.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Linked control" htmlFor="proc-ctrl">
              <Select id="proc-ctrl" value={controlRef} onChange={(e) => setControlRef(e.target.value)}>
                <option value="">None</option>
                {controls.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label="Procedure steps" htmlFor="proc-body" hint={loading ? "Loading the current text…" : undefined}>
            <RichTextEditor
              id="proc-body"
              label="Procedure steps"
              value={contentMd}
              onChange={setContentMd}
              placeholder="List the steps someone follows, in order…"
            />
          </Field>
          <FormActions pending={pending} submitLabel={existing ? "Save changes" : "Create procedure"} onCancel={() => setOpen(false)} />
        </form>
      </CrudDialog>
      {existing && (
        <RevokeButton
          compact
          label={`Revoke ${existing.name}`}
          onRevoke={() => revokeProcedure(existing.id, existing.modified)}
        />
      )}
    </div>
  );
}
