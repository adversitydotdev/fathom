"use client";

import { Plus, RefreshCw, ShieldCheck } from "lucide-react";
import { useState, useTransition } from "react";

import { CrudDialog, Field, FormActions, FormError, RevokeButton, Select } from "@/components/crud";
import { LoadingButton } from "@/components/spectrumui/loading-button-dependencies";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  collectConnection,
  createConnection,
  deleteConnection,
  enableTemplate,
  setConnectionState,
  validateConnection,
  type ActionState,
} from "@/lib/actions";
import type { Connection, Integration } from "@/lib/api/types";

type Option = { id: string; label: string };

/** Validate, Collect, Disable or Enable, and Remove for one connection row. */
export function ConnectionActions({ connection }: { connection: Connection }) {
  const [pending, start] = useTransition();
  const [state, setState] = useState<ActionState & { what?: string }>({});
  const disabled = connection.state === "disabled";

  const run = (what: string, action: () => Promise<ActionState>) =>
    start(async () => setState({ ...(await action()), what }));

  return (
    <div className="flex flex-wrap items-center justify-end gap-1">
      {state.jobId && (
        <span className="font-mono text-xs text-met-ink" title={state.jobId}>
          {state.what} queued
        </span>
      )}
      {state.error && <span className="text-xs text-gap-ink">{state.error}</span>}
      <Button
        variant="ghost"
        size="xs"
        disabled={pending || disabled}
        aria-label={`Validate ${connection.name}`}
        onClick={() => run("Validation", () => validateConnection(connection.id))}
      >
        <ShieldCheck className="size-3.5" aria-hidden />
        Validate
      </Button>
      <Button
        variant="ghost"
        size="xs"
        disabled={pending || disabled}
        aria-label={`Collect ${connection.name}`}
        onClick={() => run("Collection", () => collectConnection(connection.id))}
      >
        <RefreshCw className="size-3.5" aria-hidden />
        Collect
      </Button>
      <Button
        variant="ghost"
        size="xs"
        disabled={pending}
        aria-label={`${disabled ? "Enable" : "Disable"} ${connection.name}`}
        onClick={() =>
          run("Update", () => setConnectionState(connection.id, connection.modified, disabled ? "pending" : "disabled"))
        }
      >
        {disabled ? "Enable" : "Disable"}
      </Button>
      <RevokeButton compact label={`Remove ${connection.name}`} onRevoke={() => deleteConnection(connection.id)} />
    </div>
  );
}

export function EnableTemplateButton({ integrationId, name, label }: { integrationId: string; name: string; label: string }) {
  const [pending, start] = useTransition();
  const [state, setState] = useState<ActionState>({});
  if (state.id) {
    return (
      <span className="font-mono text-xs text-met-ink" title={state.id}>
        Enabled
      </span>
    );
  }
  return (
    <span className="inline-flex shrink-0 items-center gap-1.5">
      {state.error && <span className="text-xs text-gap-ink">{state.error}</span>}
      <LoadingButton
        variant="outline"
        size="sm"
        className="h-7 px-2.5 text-xs"
        loading={pending}
        disabled={pending}
        aria-label={`Enable ${label}`}
        onClick={() => start(async () => setState(await enableTemplate(integrationId, name)))}
      >
        Enable
      </LoadingButton>
    </span>
  );
}

/**
 * Create a connection, then write each secret through the write-only route.
 * Secret inputs are password fields and are cleared when the dialog closes.
 */
export function NewConnectionDialog({ integrations, bindings }: { integrations: Integration[]; bindings: Option[] }) {
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  const [error, setError] = useState<string>();

  const [integrationId, setIntegrationId] = useState(integrations[0]?.id ?? "");
  const integration = integrations.find((i) => i.id === integrationId);
  const supported = integration?.auth.filter((a) => a.supported) ?? [];
  const [authKind, setAuthKind] = useState<string>(supported[0]?.kind ?? "");
  const auth = supported.find((a) => a.kind === authKind) ?? supported[0];
  const [name, setName] = useState("");
  const [config, setConfig] = useState<Record<string, string>>({});
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [bound, setBound] = useState<string[]>([]);

  function reset(next?: string) {
    const target = integrations.find((i) => i.id === (next ?? integrationId));
    setAuthKind(target?.auth.find((a) => a.supported)?.kind ?? "");
    setConfig({});
    setSecrets({});
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    start(async () => {
      const res = await createConnection(
        {
          integration_id: integrationId,
          name: name.trim(),
          config: Object.fromEntries(Object.entries(config).filter(([, v]) => v.trim())),
          auth_kind: auth?.kind ?? "",
          bindings: bound,
        },
        secrets,
      );
      if (res.error) {
        setError(res.error);
        return;
      }
      setOpen(false);
      setName("");
      setBound([]);
      reset();
    });
  }

  return (
    <CrudDialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setSecrets({});
      }}
      title="New connection"
      description="Link an installed integration to one vendor account. Secrets are write-only."
      trigger={
        <Button size="sm" className="h-8 gap-1.5 px-3 text-xs">
          <Plus className="size-3.5" aria-hidden />
          New connection
        </Button>
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <FormError error={error} />
        <Field label="Integration" required htmlFor="connection-integration">
          <Select
            id="connection-integration"
            value={integrationId}
            onChange={(e) => {
              setIntegrationId(e.target.value);
              reset(e.target.value);
            }}
          >
            {integrations.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name} ({i.id})
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Name" required htmlFor="connection-name">
          <Input
            id="connection-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={`${integration?.name ?? "Vendor"} production`}
            required
          />
        </Field>
        {integration?.config.map((c) => (
          <Field key={c.name} label={c.label} required={c.required} htmlFor={`config-${c.name}`}>
            <Input
              id={`config-${c.name}`}
              value={config[c.name] ?? ""}
              onChange={(e) => setConfig({ ...config, [c.name]: e.target.value })}
              required={c.required}
            />
          </Field>
        ))}
        {supported.length > 1 && (
          <Field label="Authentication" htmlFor="connection-auth">
            <Select id="connection-auth" value={auth?.kind} onChange={(e) => setAuthKind(e.target.value)}>
              {supported.map((a) => (
                <option key={a.kind} value={a.kind}>
                  {a.label}
                </option>
              ))}
            </Select>
          </Field>
        )}
        {supported.length === 0 && (
          <FormError error="This server cannot run any of this integration's authentication methods yet." />
        )}
        {auth?.fields?.map((f) => (
          <Field key={f.name} label={f.label} required htmlFor={`secret-${f.name}`} hint={f.name}>
            <Input
              id={`secret-${f.name}`}
              type={f.secret === false ? "text" : "password"}
              autoComplete="off"
              value={secrets[f.name] ?? ""}
              onChange={(e) => setSecrets({ ...secrets, [f.name]: e.target.value })}
              required
            />
          </Field>
        ))}
        <fieldset className="flex flex-col gap-1.5">
          <legend className="pb-1.5 font-mono text-[11px] tracking-[0.1em] text-muted-foreground uppercase">
            Bound to
          </legend>
          {bindings.map((b) => (
            <label key={b.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={bound.includes(b.id)}
                onChange={(e) => setBound(e.target.checked ? [...bound, b.id] : bound.filter((x) => x !== b.id))}
              />
              {b.label}
            </label>
          ))}
        </fieldset>
        <FormActions pending={pending} submitLabel="Connect" onCancel={() => setOpen(false)} />
      </form>
    </CrudDialog>
  );
}
