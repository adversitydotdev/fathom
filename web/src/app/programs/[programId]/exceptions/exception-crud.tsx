"use client";

import { Pencil, Plus } from "lucide-react";
import { useState, useTransition } from "react";

import { CrudDialog, Field, FormActions, FormError, RevokeButton, Select, Textarea } from "@/components/crud";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createException, revokeException, updateException } from "@/lib/actions";

export type Option = { id: string; label: string };

export function ExceptionCrudDialog({
  implementations,
  parties,
  risks,
  existing,
}: {
  implementations: Option[];
  parties: Option[];
  risks: Option[];
  existing?: {
    id: string;
    modified: string;
    implementationId: string;
    justification: string;
    expires: string;
    approverId: string;
    riskId?: string;
  };
}) {
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  const [error, setError] = useState<string>();

  const [implRef, setImplRef] = useState(existing?.implementationId ?? implementations[0]?.id ?? "");
  const [approverRef, setApproverRef] = useState(existing?.approverId ?? parties[0]?.id ?? "");
  const [riskRef, setRiskRef] = useState(existing?.riskId ?? "");
  const [expires, setExpires] = useState(
    () => existing?.expires ?? new Date(Date.now() + 30 * 86_400_000).toISOString().slice(0, 10),
  );
  const [justification, setJustification] = useState(existing?.justification ?? "");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    start(async () => {
      const payload = {
        implementation_ref: implRef,
        approver_ref: approverRef,
        expires,
        justification: justification.trim(),
        risk_ref: riskRef || undefined,
      };
      const res = existing
        ? await updateException(existing.id, existing.modified, payload)
        : await createException(payload);
      if (res.error) {
        setError(res.error);
        return;
      }
      if (!existing) setJustification("");
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
        title={existing ? "Edit exception" : "New exception"}
        description="A time-bound waiver marks a control implementation as waived until its expiry date."
        trigger={
          existing ? (
            <Button size="icon-xs" variant="ghost" aria-label="Edit exception" title="Edit exception">
              <Pencil className="size-3.5" aria-hidden />
            </Button>
          ) : (
            <Button size="sm" variant="outline" className="gap-1.5">
              <Plus className="size-3.5" aria-hidden />
              New exception
            </Button>
          )
        }
      >
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <FormError error={error} />
          <Field label="Control implementation" htmlFor="ex-impl" required>
            <Select id="ex-impl" value={implRef} onChange={(e) => setImplRef(e.target.value)} disabled={Boolean(existing)}>
              {implementations.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.label}
                </option>
              ))}
            </Select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Approver" htmlFor="ex-approver" required>
              <Select id="ex-approver" value={approverRef} onChange={(e) => setApproverRef(e.target.value)}>
                {parties.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Expires" htmlFor="ex-expires" required>
              <Input id="ex-expires" type="date" required value={expires} onChange={(e) => setExpires(e.target.value)} />
            </Field>
          </div>
          <Field label="Linked risk" htmlFor="ex-risk">
            <Select id="ex-risk" value={riskRef} onChange={(e) => setRiskRef(e.target.value)}>
              <option value="">None</option>
              {risks.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Justification" htmlFor="ex-just" required>
            <Textarea id="ex-just" required value={justification} onChange={(e) => setJustification(e.target.value)} />
          </Field>
          <FormActions pending={pending} submitLabel={existing ? "Save changes" : "Create exception"} onCancel={() => setOpen(false)} />
        </form>
      </CrudDialog>
      {existing && (
        <RevokeButton
          compact
          label="Revoke exception"
          onRevoke={() => revokeException(existing.id, existing.modified)}
        />
      )}
    </div>
  );
}
