"use client";

import { Pencil, Plus } from "lucide-react";
import { useState, useTransition } from "react";

import { CrudDialog, Field, FormActions, FormError, Select, Textarea } from "@/components/crud";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createTest, updateTest } from "@/lib/actions";
import type { Test } from "@/lib/api/types";

export type ControlOption = { id: string; label: string };

const INTERVALS = ["continuous", "daily", "weekly", "monthly", "quarterly", "annual", "event-driven"];

export function TestCrudDialog({
  controls,
  existing,
}: {
  controls: ControlOption[];
  existing?: {
    id: string;
    modified: string;
    name: string;
    controlId: string;
    method: Test["method"];
    interval?: string;
    required?: boolean;
    command?: string;
  };
}) {
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  const [error, setError] = useState<string>();

  const [name, setName] = useState(existing?.name ?? "");
  const [controlRef, setControlRef] = useState(existing?.controlId ?? controls[0]?.id ?? "");
  const [method, setMethod] = useState<Test["method"]>(existing?.method ?? "manual");
  const [interval, setInterval] = useState(existing?.interval ?? "quarterly");
  const [required, setRequired] = useState(existing?.required ?? true);
  const [command, setCommand] = useState(existing?.command ?? "");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    start(async () => {
      const body = {
        name: name.trim(),
        control_ref: controlRef,
        method,
        interval,
        required,
        ...(method === "automated" && command.trim()
          ? { run: { runner: "shell" as const, command: command.trim() } }
          : {}),
      };
      const res = existing
        ? await updateTest(existing.id, existing.modified, body)
        : await createTest(body);
      if (res.error) {
        setError(res.error);
        return;
      }
      if (!existing) {
        setName("");
        setCommand("");
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
      title={existing ? "Edit test" : "New test"}
      description="Define a manual verification procedure or automated check for a control."
      trigger={
        existing ? (
          <Button size="icon-xs" variant="ghost" aria-label={`Edit ${existing.name}`} title="Edit test">
            <Pencil className="size-3.5" aria-hidden />
          </Button>
        ) : (
          <Button size="sm" variant="outline" className="gap-1.5">
            <Plus className="size-3.5" aria-hidden />
            New test
          </Button>
        )
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <FormError error={error} />
        <Field label="Control" htmlFor="test-ctrl" required>
          <Select id="test-ctrl" value={controlRef} onChange={(e) => setControlRef(e.target.value)} disabled={Boolean(existing)}>
            {controls.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Name" htmlFor="test-name" required>
          <Input id="test-name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Verify KMS key rotation enabled" />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Method" htmlFor="test-method" required>
            <Select id="test-method" value={method} onChange={(e) => setMethod(e.target.value as Test["method"])}>
              <option value="manual">manual</option>
              <option value="automated">automated</option>
            </Select>
          </Field>
          <Field label="Interval" htmlFor="test-interval">
            <Select id="test-interval" value={interval} onChange={(e) => setInterval(e.target.value)}>
              {INTERVALS.map((i) => (
                <option key={i} value={i}>
                  {i}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        {method === "automated" && (
          <Field label="Shell command" htmlFor="test-cmd" hint="Executed by the harness when Run is clicked.">
            <Textarea
              id="test-cmd"
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              placeholder="./checks/verify-kms.sh"
              className="min-h-14 font-mono text-xs"
            />
          </Field>
        )}
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <input type="checkbox" checked={required} onChange={(e) => setRequired(e.target.checked)} />
          Required to meet control state (RFC 0001 §8)
        </label>
        <FormActions pending={pending} submitLabel={existing ? "Save changes" : "Create test"} onCancel={() => setOpen(false)} />
      </form>
    </CrudDialog>
  );
}
