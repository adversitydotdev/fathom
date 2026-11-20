"use client";

import { Pencil, Plus } from "lucide-react";
import { useState, useTransition } from "react";

import { CrudDialog, Field, FormActions, FormError, Select } from "@/components/crud";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createEvidence, updateEvidence } from "@/lib/actions";
import type { Evidence } from "@/lib/api/types";

export type ImplOption = { id: string; label: string };

export function EvidenceCrudDialog({
  implementations,
  existing,
}: {
  implementations: ImplOption[];
  existing?: {
    id: string;
    modified: string;
    name: string;
    method: Evidence["method"];
    implementationId?: string;
    validUntil?: string;
    uri?: string;
  };
}) {
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  const [error, setError] = useState<string>();

  const [name, setName] = useState(existing?.name ?? "");
  const [implRef, setImplRef] = useState(existing?.implementationId ?? implementations[0]?.id ?? "");
  const [method, setMethod] = useState<Evidence["method"]>(existing?.method ?? "attestation");
  const [validUntil, setValidUntil] = useState(
    () => existing?.validUntil ?? new Date(Date.now() + 90 * 86_400_000).toISOString().slice(0, 10),
  );
  const [uri, setUri] = useState(existing?.uri ?? "");
  const [file, setFile] = useState<File | null>(null);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    start(async () => {
      const today = new Date().toISOString().slice(0, 10);
      if (existing) {
        const res = await updateEvidence(existing.id, existing.modified, {
          name: name.trim(),
          valid_until: validUntil || undefined,
          resource: uri.trim() ? { uri: uri.trim(), media_type: "text/html" } : undefined,
        });
        if (res.error) {
          setError(res.error);
          return;
        }
      } else {
        const fd = file ? new FormData() : undefined;
        if (fd && file) fd.append("file", file);
        const res = await createEvidence(
          {
            name: name.trim(),
            method,
            collected: new Date().toISOString(),
            valid_from: today,
            valid_until: validUntil || undefined,
            implementation_ref: implRef || undefined,
            resource: uri.trim() ? { uri: uri.trim(), media_type: "text/html" } : undefined,
          },
          fd,
        );
        if (res.error) {
          setError(res.error);
          return;
        }
        setName("");
        setUri("");
        setFile(null);
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
      title={existing ? "Edit evidence" : "Add evidence"}
      description="Record an attestation, external link, or uploaded artifact (SHA-256 digested in S3)."
      trigger={
        existing ? (
          <Button size="icon-xs" variant="ghost" aria-label={`Edit ${existing.name}`} title="Edit evidence">
            <Pencil className="size-3.5" aria-hidden />
          </Button>
        ) : (
          <Button size="sm" variant="outline" className="gap-1.5">
            <Plus className="size-3.5" aria-hidden />
            Add evidence
          </Button>
        )
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <FormError error={error} />
        <Field label="Name" htmlFor="ev-name" required>
          <Input id="ev-name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="SOC 2 Type II Bridge Letter" />
        </Field>
        {!existing && (
          <Field label="Control implementation" htmlFor="ev-impl">
            <Select id="ev-impl" value={implRef} onChange={(e) => setImplRef(e.target.value)}>
              <option value="">Unlinked</option>
              {implementations.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.label}
                </option>
              ))}
            </Select>
          </Field>
        )}
        <div className="grid grid-cols-2 gap-3">
          {!existing && (
            <Field label="Method" htmlFor="ev-method" required>
              <Select id="ev-method" value={method} onChange={(e) => setMethod(e.target.value as Evidence["method"])}>
                <option value="attestation">attestation</option>
                <option value="upload">upload</option>
                <option value="link">link</option>
              </Select>
            </Field>
          )}
          <Field label="Valid until" htmlFor="ev-until">
            <Input id="ev-until" type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} />
          </Field>
        </div>
        {!existing && method === "upload" ? (
          <Field label="Artifact file" htmlFor="ev-file" hint="Uploaded via POST /v1/evidence/{id}/content">
            <Input id="ev-file" type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </Field>
        ) : (
          <Field label="Resource URI" htmlFor="ev-uri">
            <Input id="ev-uri" value={uri} onChange={(e) => setUri(e.target.value)} placeholder="https://…" />
          </Field>
        )}
        <FormActions pending={pending} submitLabel={existing ? "Save changes" : "Add evidence"} onCancel={() => setOpen(false)} />
      </form>
    </CrudDialog>
  );
}
