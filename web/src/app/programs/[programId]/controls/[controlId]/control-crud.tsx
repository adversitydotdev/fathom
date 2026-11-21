"use client";

import { Check, CheckCircle2, Pencil, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { CrudDialog, Field, FormActions, FormError, RevokeButton, Select, Textarea } from "@/components/crud";
import { LoadingButton } from "@/components/spectrumui/loading-button-dependencies";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  createEvidence,
  createImplementation,
  createResult,
  revokeControl,
  revokeImplementation,
  updateControl,
  updateImplementation,
} from "@/lib/actions";
import type { Control, Evidence, Implementation, Result } from "@/lib/api/types";

const IMPL_STATUSES: Implementation["status"][] = [
  "implemented",
  "partial",
  "planned",
  "exception",
  "not-applicable",
];
const RESPONSIBILITIES: Implementation["responsibility"][] = ["provider", "shared", "subservice", "customer"];
const OUTCOMES: Result["outcome"][] = ["pass", "fail", "error", "skip"];

export type PartyOption = { id: string; name: string };

export function ImplementationCrudButton({
  systemId,
  controlId,
  parameters,
  parties,
  existing,
}: {
  systemId: string;
  controlId: string;
  parameters?: Record<string, { label?: string; value?: string }>;
  parties: PartyOption[];
  existing?: {
    id: string;
    modified: string;
    status: Implementation["status"];
    responsibility: Implementation["responsibility"];
    owner_ref?: string;
    narrative?: string;
    customer_responsibility?: string;
    parameter_values?: Record<string, string>;
  };
}) {
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  const [error, setError] = useState<string>();

  const [status, setStatus] = useState<Implementation["status"]>(existing?.status ?? "implemented");
  const [responsibility, setResponsibility] = useState<Implementation["responsibility"]>(
    existing?.responsibility ?? "provider",
  );
  const [ownerRef, setOwnerRef] = useState(existing?.owner_ref ?? "");
  const [narrative, setNarrative] = useState(existing?.narrative ?? "");
  const [customerResp, setCustomerResp] = useState(existing?.customer_responsibility ?? "");
  const [paramValues, setParamValues] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const [k, def] of Object.entries(parameters ?? {})) {
      init[k] = existing?.parameter_values?.[k] ?? def?.value ?? "";
    }
    return init;
  });

  const paramKeys = Object.keys(parameters ?? {});

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    const cleanedParams: Record<string, string> = {};
    for (const k of paramKeys) {
      if (paramValues[k]?.trim()) cleanedParams[k] = paramValues[k].trim();
    }

    start(async () => {
      const payload = {
        status,
        responsibility,
        owner_ref: ownerRef || undefined,
        narrative: narrative.trim() || undefined,
        customer_responsibility: customerResp.trim() || undefined,
        ...(paramKeys.length > 0 ? { parameter_values: cleanedParams } : {}),
      };
      const res = existing
        ? await updateImplementation(existing.id, existing.modified, payload)
        : await createImplementation({
            ...payload,
            system_ref: systemId,
            control_ref: controlId,
          });
      if (res.error) {
        setError(res.error);
        return;
      }
      setOpen(false);
    });
  }

  return (
    <div className="inline-flex items-center gap-1.5">
      <CrudDialog
        open={open}
        onOpenChange={(v) => {
          setOpen(v);
          if (!v) setError(undefined);
        }}
        title={existing ? "Edit implementation" : "Add implementation"}
        description="Updates are sent with If-Match and re-evaluated live by the OGRL kernel."
        trigger={
          <Button size="xs" variant="outline" className="gap-1">
            {existing ? <Pencil className="size-3" aria-hidden /> : <Plus className="size-3" aria-hidden />}
            {existing ? "Edit" : "Add implementation"}
          </Button>
        }
      >
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <FormError error={error} />
          <div className="grid grid-cols-2 gap-3">
            <Field label="Status" htmlFor="impl-status" required>
              <Select
                id="impl-status"
                value={status}
                onChange={(e) => setStatus(e.target.value as Implementation["status"])}
              >
                {IMPL_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Responsibility" htmlFor="impl-resp" required>
              <Select
                id="impl-resp"
                value={responsibility}
                onChange={(e) => setResponsibility(e.target.value as Implementation["responsibility"])}
              >
                {RESPONSIBILITIES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label="Owner" htmlFor="impl-owner">
            <Select id="impl-owner" value={ownerRef} onChange={(e) => setOwnerRef(e.target.value)}>
              <option value="">Unassigned</option>
              {parties.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </Field>
          {paramKeys.length > 0 && (
            <div className="flex flex-col gap-3 rounded-xl border bg-background/40 p-3.5">
              <span className="font-mono text-[11px] tracking-[0.1em] text-muted-foreground uppercase">
                Control parameters
              </span>
              {paramKeys.map((key) => (
                <Field
                  key={key}
                  label={parameters?.[key]?.label ?? key}
                  htmlFor={`param-${key}`}
                  hint={`{{ ${key} }}`}
                >
                  <Input
                    id={`param-${key}`}
                    value={paramValues[key] ?? ""}
                    onChange={(e) => setParamValues((prev) => ({ ...prev, [key]: e.target.value }))}
                  />
                </Field>
              ))}
            </div>
          )}
          <Field label="Narrative" htmlFor="impl-narrative">
            <Textarea
              id="impl-narrative"
              value={narrative}
              onChange={(e) => setNarrative(e.target.value)}
              placeholder="Describe how this system implements the control…"
              className="min-h-24"
            />
          </Field>
          {responsibility === "shared" && (
            <Field label="Customer responsibility" htmlFor="impl-cust-resp">
              <Textarea
                id="impl-cust-resp"
                value={customerResp}
                onChange={(e) => setCustomerResp(e.target.value)}
                className="min-h-16"
              />
            </Field>
          )}
          <FormActions
            pending={pending}
            submitLabel={existing ? "Save changes" : "Create implementation"}
            onCancel={() => setOpen(false)}
          />
        </form>
      </CrudDialog>
      {existing && (
        <RevokeButton
          compact
          label="Revoke implementation"
          onRevoke={() => revokeImplementation(existing.id, existing.modified)}
        />
      )}
    </div>
  );
}

export function RecordManualResultButton({
  testId,
  testName,
  implementationId,
}: {
  testId: string;
  testName: string;
  implementationId: string;
}) {
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  const [error, setError] = useState<string>();
  const [outcome, setOutcome] = useState<Result["outcome"]>("pass");
  const [summary, setSummary] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    start(async () => {
      const res = await createResult({
        test_ref: testId,
        implementation_ref: implementationId,
        observed: new Date().toISOString(),
        outcome,
        summary: summary.trim() || undefined,
      });
      if (res.error) {
        setError(res.error);
        return;
      }
      setSummary("");
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
      title="Record manual result"
      description={testName}
      trigger={
        <Button size="xs" variant="outline" className="gap-1">
          <CheckCircle2 className="size-3" aria-hidden />
          Record
        </Button>
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <FormError error={error} />
        <Field label="Outcome" htmlFor={`outcome-${testId}`} required>
          <Select
            id={`outcome-${testId}`}
            value={outcome}
            onChange={(e) => setOutcome(e.target.value as Result["outcome"])}
          >
            {OUTCOMES.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Summary" htmlFor={`summary-${testId}`}>
          <Textarea
            id={`summary-${testId}`}
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="Notes or verification findings…"
          />
        </Field>
        <FormActions pending={pending} submitLabel="Record result" onCancel={() => setOpen(false)} />
      </form>
    </CrudDialog>
  );
}

export function QuickAddEvidenceButton({ implementationId }: { implementationId: string }) {
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  const [error, setError] = useState<string>();

  const [name, setName] = useState("");
  const [method, setMethod] = useState<Evidence["method"]>("attestation");
  const [validUntil, setValidUntil] = useState(() =>
    new Date(Date.now() + 90 * 86_400_000).toISOString().slice(0, 10),
  );
  const [uri, setUri] = useState("");
  const [file, setFile] = useState<File | null>(null);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    start(async () => {
      const today = new Date().toISOString().slice(0, 10);
      const fd = file ? new FormData() : undefined;
      if (fd && file) fd.append("file", file);
      const res = await createEvidence(
        {
          name: name.trim(),
          method,
          collected: new Date().toISOString(),
          valid_from: today,
          valid_until: validUntil || undefined,
          implementation_ref: implementationId,
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
      title="Attach evidence"
      description="Attach an attestation, link, or uploaded artifact to this implementation."
      trigger={
        <Button size="xs" variant="outline" className="gap-1">
          <Plus className="size-3" aria-hidden />
          Add
        </Button>
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <FormError error={error} />
        <Field label="Name" htmlFor="qev-name" required>
          <Input id="qev-name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Q4 access review sign-off" />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Method" htmlFor="qev-method" required>
            <Select id="qev-method" value={method} onChange={(e) => setMethod(e.target.value as Evidence["method"])}>
              <option value="attestation">attestation</option>
              <option value="upload">upload</option>
              <option value="link">link</option>
            </Select>
          </Field>
          <Field label="Valid until" htmlFor="qev-until">
            <Input id="qev-until" type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} />
          </Field>
        </div>
        {method === "upload" ? (
          <Field label="Upload file" htmlFor="qev-file" hint="Stored in S3 with computed SHA-256 digest.">
            <Input id="qev-file" type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </Field>
        ) : (
          <Field label="Resource URI" htmlFor="qev-uri" hint="Optional link or ticket URL">
            <Input id="qev-uri" value={uri} onChange={(e) => setUri(e.target.value)} placeholder="https://…" />
          </Field>
        )}
        <FormActions pending={pending} submitLabel="Attach evidence" onCancel={() => setOpen(false)} />
      </form>
    </CrudDialog>
  );
}

export function CustomControlActions({
  control,
  backHref,
}: {
  control: {
    id: string;
    modified: string;
    display_id?: string;
    name?: string;
    family?: string;
    statement: string;
    objective: string;
    guidance?: string;
  };
  backHref: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  const [error, setError] = useState<string>();

  const [displayId, setDisplayId] = useState(control.display_id ?? "");
  const [name, setName] = useState(control.name ?? "");
  const [family, setFamily] = useState(control.family ?? "");
  const [statement, setStatement] = useState(control.statement);
  const [objective, setObjective] = useState(control.objective);
  const [guidance, setGuidance] = useState(control.guidance ?? "");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    start(async () => {
      const res = await updateControl(control.id, control.modified, {
        display_id: displayId.trim() || undefined,
        name: name.trim(),
        family: family.trim() || undefined,
        statement: statement.trim(),
        objective: objective.trim(),
        guidance: guidance.trim() || undefined,
      } as Partial<Control>);
      if (res.error) {
        setError(res.error);
        return;
      }
      setOpen(false);
    });
  }

  return (
    <div className="inline-flex items-center gap-1.5">
      <CrudDialog
        open={open}
        onOpenChange={(v) => {
          setOpen(v);
          if (!v) setError(undefined);
        }}
        title="Edit custom control"
        trigger={
          <Button size="xs" variant="outline" className="gap-1">
            <Pencil className="size-3" aria-hidden />
            Edit control
          </Button>
        }
      >
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <FormError error={error} />
          <div className="grid grid-cols-2 gap-3">
            <Field label="Display ID" htmlFor="ec-disp">
              <Input id="ec-disp" value={displayId} onChange={(e) => setDisplayId(e.target.value)} />
            </Field>
            <Field label="Family" htmlFor="ec-fam">
              <Input id="ec-fam" value={family} onChange={(e) => setFamily(e.target.value)} />
            </Field>
          </div>
          <Field label="Name" htmlFor="ec-name" required>
            <Input id="ec-name" required value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Statement" htmlFor="ec-stmt" required>
            <Textarea id="ec-stmt" required value={statement} onChange={(e) => setStatement(e.target.value)} />
          </Field>
          <Field label="Objective" htmlFor="ec-obj" required>
            <Textarea id="ec-obj" required value={objective} onChange={(e) => setObjective(e.target.value)} />
          </Field>
          <Field label="Guidance" htmlFor="ec-guid">
            <Textarea id="ec-guid" value={guidance} onChange={(e) => setGuidance(e.target.value)} />
          </Field>
          <FormActions pending={pending} submitLabel="Save changes" onCancel={() => setOpen(false)} />
        </form>
      </CrudDialog>
      <RevokeButton
        label="Revoke"
        onRevoke={async () => {
          const res = await revokeControl(control.id, control.modified);
          if (!res.error) router.push(backHref);
          return res;
        }}
      />
    </div>
  );
}

export function AcceptDraftButton({ id, modified }: { id: string; modified: string }) {
  const [pending, start] = useTransition();
  const [error, setError] = useState<string>();

  return (
    <span className="inline-flex items-center gap-2">
      {error && <span className="text-xs text-gap-ink">{error}</span>}
      <LoadingButton
        type="button"
        variant="outline"
        size="sm"
        className="h-7 gap-1 border-agent/40 px-2.5 text-xs hover:bg-agent/15"
        loading={pending}
        disabled={pending}
        onClick={() =>
          start(async () => {
            setError(undefined);
            const res = await updateImplementation(id, modified, { status: "implemented" });
            if (res.error) setError(res.error);
          })
        }
      >
        {!pending && <Check className="size-3 text-met" aria-hidden />}
        Accept draft
      </LoadingButton>
    </span>
  );
}
