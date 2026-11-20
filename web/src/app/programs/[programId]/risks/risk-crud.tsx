"use client";

import { Pencil, Plus } from "lucide-react";
import { useState, useTransition } from "react";

import { CrudDialog, Field, FormActions, FormError, Select, Textarea } from "@/components/crud";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createRisk, updateRisk } from "@/lib/actions";
import type { Risk } from "@/lib/api/types";

export type Option = { id: string; label: string };

const TREATMENTS: Risk["treatment"][] = ["mitigate", "accept", "transfer", "avoid"];
const STATUSES: Risk["status"][] = ["open", "treating", "accepted", "closed"];

export function RiskCrudDialog({
  systemId,
  parties,
  controls,
  existing,
}: {
  systemId: string;
  parties: Option[];
  controls: Option[];
  existing?: {
    id: string;
    modified: string;
    name: string;
    statement: string;
    likelihood: number;
    impact: number;
    residualLikelihood?: number;
    residualImpact?: number;
    treatment?: Risk["treatment"];
    status: Risk["status"];
    ownerId?: string;
    controlIds: string[];
  };
}) {
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  const [error, setError] = useState<string>();

  const [name, setName] = useState(existing?.name ?? "");
  const [statement, setStatement] = useState(existing?.statement ?? "");
  const [likelihood, setLikelihood] = useState(String(existing?.likelihood || 3));
  const [impact, setImpact] = useState(String(existing?.impact || 3));
  const [resLikelihood, setResLikelihood] = useState(existing?.residualLikelihood ? String(existing.residualLikelihood) : "");
  const [resImpact, setResImpact] = useState(existing?.residualImpact ? String(existing.residualImpact) : "");
  const [treatment, setTreatment] = useState<Risk["treatment"]>(existing?.treatment ?? "mitigate");
  const [status, setStatus] = useState<Risk["status"]>(existing?.status ?? "open");
  const [ownerRef, setOwnerRef] = useState(existing?.ownerId ?? "");
  const [controlRef, setControlRef] = useState(existing?.controlIds[0] ?? "");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    start(async () => {
      const payload = {
        name: name.trim(),
        system_ref: systemId,
        statement: statement.trim(),
        likelihood: Number(likelihood),
        impact: Number(impact),
        ...(resLikelihood ? { residual_likelihood: Number(resLikelihood) } : {}),
        ...(resImpact ? { residual_impact: Number(resImpact) } : {}),
        treatment,
        status,
        owner_ref: ownerRef || undefined,
        control_refs: controlRef ? [controlRef] : [],
      };
      const res = existing
        ? await updateRisk(existing.id, existing.modified, payload)
        : await createRisk(payload);
      if (res.error) {
        setError(res.error);
        return;
      }
      if (!existing) {
        setName("");
        setStatement("");
        setResLikelihood("");
        setResImpact("");
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
      title={existing ? "Edit risk" : "New risk"}
      description="Changes update the 5×5 risk matrix and register immediately."
      trigger={
        existing ? (
          <Button size="icon-xs" variant="ghost" aria-label={`Edit ${existing.name}`} title="Edit risk">
            <Pencil className="size-3.5" aria-hidden />
          </Button>
        ) : (
          <Button size="sm" variant="outline" className="gap-1.5">
            <Plus className="size-3.5" aria-hidden />
            New risk
          </Button>
        )
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <FormError error={error} />
        <Field label="Name" htmlFor="risk-name" required>
          <Input id="risk-name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Unencrypted staging snapshots" />
        </Field>
        <Field label="Statement" htmlFor="risk-stmt" required>
          <Textarea id="risk-stmt" required value={statement} onChange={(e) => setStatement(e.target.value)} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Likelihood (1–5)" htmlFor="risk-l" required>
            <Select id="risk-l" value={likelihood} onChange={(e) => setLikelihood(e.target.value)}>
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Impact (1–5)" htmlFor="risk-i" required>
            <Select id="risk-i" value={impact} onChange={(e) => setImpact(e.target.value)}>
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Residual likelihood" htmlFor="risk-rl">
            <Select id="risk-rl" value={resLikelihood} onChange={(e) => setResLikelihood(e.target.value)}>
              <option value="">Same as inherent</option>
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Residual impact" htmlFor="risk-ri">
            <Select id="risk-ri" value={resImpact} onChange={(e) => setResImpact(e.target.value)}>
              <option value="">Same as inherent</option>
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Status" htmlFor="risk-status" required>
            <Select id="risk-status" value={status} onChange={(e) => setStatus(e.target.value as Risk["status"])}>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Treatment" htmlFor="risk-treat" required>
            <Select id="risk-treat" value={treatment} onChange={(e) => setTreatment(e.target.value as Risk["treatment"])}>
              {TREATMENTS.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Owner" htmlFor="risk-owner">
            <Select id="risk-owner" value={ownerRef} onChange={(e) => setOwnerRef(e.target.value)}>
              <option value="">Unassigned</option>
              {parties.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Linked control" htmlFor="risk-ctrl">
            <Select id="risk-ctrl" value={controlRef} onChange={(e) => setControlRef(e.target.value)}>
              <option value="">None</option>
              {controls.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <FormActions pending={pending} submitLabel={existing ? "Save changes" : "Create risk"} onCancel={() => setOpen(false)} />
      </form>
    </CrudDialog>
  );
}
