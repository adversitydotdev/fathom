"use client";

import { Plus } from "lucide-react";
import { useState, useTransition } from "react";

import { CrudDialog, Field, FormActions, FormError, Select, Textarea } from "@/components/crud";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createControl, updateBaselineControls } from "@/lib/actions";
import type { Control } from "@/lib/api/types";

const CONTROL_TYPES: NonNullable<Control["control_type"]>[] = ["preventive", "detective", "corrective"];
const FREQUENCIES: NonNullable<Control["frequency"]>[] = [
  "continuous",
  "daily",
  "weekly",
  "monthly",
  "quarterly",
  "annual",
  "event-driven",
];

export function NewControlButton({
  baselineId,
  baselineModified,
  baselineControlRefs,
}: {
  baselineId?: string;
  baselineModified?: string;
  baselineControlRefs?: string[];
}) {
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  const [error, setError] = useState<string>();

  const [displayId, setDisplayId] = useState("");
  const [name, setName] = useState("");
  const [family, setFamily] = useState("Access Control");
  const [controlType, setControlType] = useState<NonNullable<Control["control_type"]>>("preventive");
  const [frequency, setFrequency] = useState<NonNullable<Control["frequency"]>>("continuous");
  const [statement, setStatement] = useState("");
  const [objective, setObjective] = useState("");
  const [guidance, setGuidance] = useState("");
  const [addToBaseline, setAddToBaseline] = useState(false);

  function reset() {
    setDisplayId("");
    setName("");
    setFamily("Access Control");
    setControlType("preventive");
    setFrequency("continuous");
    setStatement("");
    setObjective("");
    setGuidance("");
    setAddToBaseline(false);
    setError(undefined);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    start(async () => {
      const res = await createControl({
        display_id: displayId.trim() || undefined,
        name: name.trim(),
        family: family.trim() || undefined,
        control_type: controlType,
        frequency,
        statement: statement.trim(),
        objective: objective.trim(),
        guidance: guidance.trim() || undefined,
      });
      if (res.error) {
        setError(res.error);
        return;
      }
      if (addToBaseline && res.id && baselineId && baselineModified && baselineControlRefs) {
        const bRes = await updateBaselineControls(
          baselineId,
          baselineModified,
          Array.from(new Set([...baselineControlRefs, res.id])),
        );
        if (bRes.error) {
          setError(`Control created, but baseline update failed: ${bRes.error}`);
          return;
        }
      }
      reset();
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
      title="New custom control"
      description="Create an organization-defined control (origin: custom)."
      trigger={
        <Button size="sm" variant="outline" className="gap-1.5">
          <Plus className="size-3.5" aria-hidden />
          New control
        </Button>
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <FormError error={error} />
        <div className="grid grid-cols-2 gap-3">
          <Field label="Display ID" htmlFor="ctrl-display-id" hint="e.g. CUST-01">
            <Input id="ctrl-display-id" value={displayId} onChange={(e) => setDisplayId(e.target.value)} placeholder="CUST-01" />
          </Field>
          <Field label="Family" htmlFor="ctrl-family">
            <Input id="ctrl-family" value={family} onChange={(e) => setFamily(e.target.value)} />
          </Field>
        </div>
        <Field label="Name" htmlFor="ctrl-name" required>
          <Input id="ctrl-name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Production secrets rotation" />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Type" htmlFor="ctrl-type">
            <Select
              id="ctrl-type"
              value={controlType}
              onChange={(e) => setControlType(e.target.value as NonNullable<Control["control_type"]>)}
            >
              {CONTROL_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Frequency" htmlFor="ctrl-freq">
            <Select
              id="ctrl-freq"
              value={frequency}
              onChange={(e) => setFrequency(e.target.value as NonNullable<Control["frequency"]>)}
            >
              {FREQUENCIES.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Statement" htmlFor="ctrl-statement" required hint="Supports {{ parameter_name }} placeholders.">
          <Textarea id="ctrl-statement" required value={statement} onChange={(e) => setStatement(e.target.value)} />
        </Field>
        <Field label="Objective" htmlFor="ctrl-objective" required>
          <Textarea id="ctrl-objective" required value={objective} onChange={(e) => setObjective(e.target.value)} className="min-h-16" />
        </Field>
        <Field label="Guidance" htmlFor="ctrl-guidance">
          <Textarea id="ctrl-guidance" value={guidance} onChange={(e) => setGuidance(e.target.value)} className="min-h-16" />
        </Field>
        {baselineId && baselineModified && (
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={addToBaseline}
              onChange={(e) => setAddToBaseline(e.target.checked)}
              className="rounded border-input"
            />
            Add to active baseline (for organization baselines)
          </label>
        )}
        <FormActions pending={pending} submitLabel="Create control" onCancel={() => setOpen(false)} />
      </form>
    </CrudDialog>
  );
}
