"use client";

import { Pencil, Plus } from "lucide-react";
import { useState, useTransition } from "react";

import { CrudDialog, Field, FormActions, FormError, Select } from "@/components/crud";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createParty, updateParty } from "@/lib/actions";
import type { Party } from "@/lib/api/types";

const KINDS: Party["kind"][] = ["person", "team", "role", "organization"];

export function PartyCrudDialog({
  existing,
}: {
  existing?: {
    id: string;
    modified: string;
    name: string;
    kind: Party["kind"];
    isAgent: boolean;
  };
}) {
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  const [error, setError] = useState<string>();

  const [name, setName] = useState(existing?.name ?? "");
  const [kind, setKind] = useState<Party["kind"]>(existing?.kind ?? "person");
  const [isAgent, setIsAgent] = useState(existing?.isAgent ?? false);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    start(async () => {
      const payload = {
        name: name.trim(),
        kind,
        tags: isAgent ? ["agent"] : [],
      };
      const res = existing
        ? await updateParty(existing.id, existing.modified, payload)
        : await createParty(payload);
      if (res.error) {
        setError(res.error);
        return;
      }
      if (!existing) {
        setName("");
        setIsAgent(false);
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
      title={existing ? "Edit party" : "New party"}
      description="People, teams, roles, AI agents, and external organizations."
      trigger={
        existing ? (
          <Button size="icon-xs" variant="ghost" aria-label={`Edit ${existing.name}`} title="Edit party">
            <Pencil className="size-3.5" aria-hidden />
          </Button>
        ) : (
          <Button size="sm" variant="outline" className="gap-1.5">
            <Plus className="size-3.5" aria-hidden />
            New party
          </Button>
        )
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <FormError error={error} />
        <Field label="Name" htmlFor="party-name" required>
          <Input id="party-name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Alex Rivera" />
        </Field>
        <Field label="Kind" htmlFor="party-kind" required>
          <Select id="party-kind" value={kind} onChange={(e) => setKind(e.target.value as Party["kind"])}>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </Select>
        </Field>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <input type="checkbox" checked={isAgent} onChange={(e) => setIsAgent(e.target.checked)} />
          Mark as automated agent party (RFC 0003 §8)
        </label>
        <FormActions pending={pending} submitLabel={existing ? "Save changes" : "Create party"} onCancel={() => setOpen(false)} />
      </form>
    </CrudDialog>
  );
}
