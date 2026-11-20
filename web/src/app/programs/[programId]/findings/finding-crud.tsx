"use client";

import { Pencil, Plus } from "lucide-react";
import { useState, useTransition } from "react";

import { CrudDialog, Field, FormActions, FormError, RevokeButton, Select, Textarea } from "@/components/crud";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createFinding, revokeFinding, updateFinding } from "@/lib/actions";
import type { Finding } from "@/lib/api/types";

export type Option = { id: string; label: string };

export function FindingCrudDialog({
  systemId,
  implementations,
  defaultObjectiveRef,
  existing,
}: {
  systemId: string;
  implementations: Option[];
  defaultObjectiveRef?: string;
  existing?: {
    id: string;
    modified: string;
    name: string;
    objectiveRef: string;
    determination: Finding["determination"];
    observed: string;
    narrative?: string;
    implementationId?: string;
  };
}) {
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  const [error, setError] = useState<string>();

  const today = new Date().toISOString().slice(0, 10);
  const [name, setName] = useState(existing?.name ?? "");
  const [objectiveRef, setObjectiveRef] = useState(
    existing?.objectiveRef ?? defaultObjectiveRef ?? "requirement--nist-sp-800-171-r3-03-05-03#obj.01",
  );
  const [determination, setDetermination] = useState<Finding["determination"]>(
    existing?.determination ?? "not-satisfied",
  );
  const [observed, setObserved] = useState(existing?.observed ?? today);
  const [implRef, setImplRef] = useState(existing?.implementationId ?? "");
  const [narrative, setNarrative] = useState(existing?.narrative ?? "");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    start(async () => {
      const payload = {
        name: name.trim(),
        system_ref: systemId,
        objective_ref: objectiveRef.trim(),
        determination,
        observed,
        narrative: narrative.trim(),
        implementation_ref: implRef || undefined,
      };
      const res = existing
        ? await updateFinding(existing.id, existing.modified, payload)
        : await createFinding(payload);
      if (res.error) {
        setError(res.error);
        return;
      }
      if (!existing) {
        setName("");
        setNarrative("");
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
        title={existing ? "Edit finding" : "New finding"}
        description="Record an assessment observation targeting a requirement objective (#obj.<id>)."
        trigger={
          existing ? (
            <Button size="icon-xs" variant="ghost" aria-label={`Edit ${existing.name}`} title="Edit finding">
              <Pencil className="size-3.5" aria-hidden />
            </Button>
          ) : (
            <Button size="sm" variant="outline" className="gap-1.5">
              <Plus className="size-3.5" aria-hidden />
              New finding
            </Button>
          )
        }
      >
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <FormError error={error} />
          <Field label="Name" htmlFor="find-name" required>
            <Input id="find-name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Incomplete quarterly access review" />
          </Field>
          <Field label="Objective ref" htmlFor="find-obj" required hint="Format: requirement--<id>#obj.<objective_id>">
            <Input id="find-obj" required value={objectiveRef} onChange={(e) => setObjectiveRef(e.target.value)} className="font-mono text-xs" />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Determination" htmlFor="find-det" required>
              <Select id="find-det" value={determination} onChange={(e) => setDetermination(e.target.value as Finding["determination"])}>
                <option value="not-satisfied">not-satisfied</option>
                <option value="satisfied">satisfied</option>
              </Select>
            </Field>
            <Field label="Observed" htmlFor="find-obs" required>
              <Input id="find-obs" type="date" required value={observed} onChange={(e) => setObserved(e.target.value)} />
            </Field>
          </div>
          <Field label="Control implementation" htmlFor="find-impl">
            <Select id="find-impl" value={implRef} onChange={(e) => setImplRef(e.target.value)}>
              <option value="">None</option>
              {implementations.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Narrative" htmlFor="find-narr" required>
            <Textarea id="find-narr" required value={narrative} onChange={(e) => setNarrative(e.target.value)} />
          </Field>
          <FormActions pending={pending} submitLabel={existing ? "Save changes" : "Create finding"} onCancel={() => setOpen(false)} />
        </form>
      </CrudDialog>
      {existing && (
        <RevokeButton
          compact
          label={`Revoke ${existing.name}`}
          onRevoke={() => revokeFinding(existing.id, existing.modified)}
        />
      )}
    </div>
  );
}
