"use client";

import { CircleCheck, FileWarning, Play, Plus, Search, ShieldCheck, X } from "lucide-react";
import { useMemo, useState, useTransition } from "react";

import { CrudDialog, Field, FormActions, FormError, Select, Textarea } from "@/components/crud";
import { LoadingButton } from "@/components/spectrumui/loading-button-dependencies";
import { StatusBadge } from "@/components/spectrumui/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  createQuery,
  describeOperation,
  dryRunQuery,
  searchOperations,
  validateQuery,
} from "@/lib/actions";
import type { Connection, DryRun, Integration, Operation, QueryCheck, QueryWrite } from "@/lib/api/types";

type Row = { key: string; path: string };

const START: Row[] = [
  { key: "id", path: "" },
  { key: "name", path: "" },
];

/** `signOnMode` → `sign_on_mode`; the last segment of a dotted path names the field. */
function fieldName(path: string): string {
  const last = path.split(".").pop() ?? path;
  return last
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .toLowerCase()
    .replace(/[^a-z0-9_]/g, "_")
    .replace(/^[^a-z]+/, "");
}

/**
 * Define a query source (RFC 0006; RFC 0007 for AWS): find a read operation in the
 * integration's API model, set its parameters, pick the fields to keep, check it, and
 * sample it through a connection before saving. Every check runs on the server.
 */
export function QueryEditorDialog({ integration, connections }: { integration: Integration; connections: Connection[] }) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string>();
  const [searching, search] = useTransition();
  const [checking, startCheck] = useTransition();
  const [running, startRun] = useTransition();
  const [saving, save] = useTransition();

  const [text, setText] = useState("");
  const [found, setFound] = useState<Operation[]>();
  const [operation, setOperation] = useState<Operation>();
  const [name, setName] = useState("");
  const [version, setVersion] = useState("1");
  const [description, setDescription] = useState("");
  const [params, setParams] = useState<Record<string, string>>({});
  const [regions, setRegions] = useState("*");
  const [items, setItems] = useState("");
  const [rows, setRows] = useState<Row[]>(START);
  const [focused, setFocused] = useState<number>();
  const [check, setCheck] = useState<QueryCheck>();
  const [run, setRun] = useState<DryRun>();
  const [connectionId, setConnectionId] = useState(connections[0]?.id ?? "");

  const smithy = integration.query_model === "smithy";
  const problems = useMemo(() => {
    const by = new Map<string, string[]>();
    for (const p of [...(check?.errors ?? []), ...(run?.warnings ?? [])]) by.set(p.pointer, [...(by.get(p.pointer) ?? []), p.detail]);
    return by;
  }, [check, run]);

  function write(): QueryWrite {
    const set = (record: Record<string, string>) => Object.fromEntries(Object.entries(record).filter(([, v]) => v.trim()));
    const regional = smithy && operation?.regional;
    return {
      integration_id: integration.id,
      name: name.trim(),
      version: Number(version) || 1,
      ...(description.trim() ? { description: description.trim() } : {}),
      operation: operation?.id ?? text.trim(),
      params: set(params),
      items: items.trim(),
      fields: Object.fromEntries(rows.filter((r) => r.key.trim()).map((r) => [r.key.trim(), r.path.trim()])),
      ...(regional
        ? { regions: regions.trim() === "*" ? "*" : regions.split(",").map((r) => r.trim()).filter(Boolean) }
        : {}),
    };
  }

  function reset() {
    setText("");
    setFound(undefined);
    setOperation(undefined);
    setName("");
    setVersion("1");
    setDescription("");
    setParams({});
    setRegions("*");
    setItems("");
    setRows(START);
    setCheck(undefined);
    setRun(undefined);
    setError(undefined);
  }

  function runSearch() {
    setError(undefined);
    search(async () => {
      const res = await searchOperations(integration.id, text.trim());
      if (res.error) setError(res.error);
      setFound(res.operations ?? []);
    });
  }

  function choose(id: string) {
    setError(undefined);
    search(async () => {
      const res = await describeOperation(integration.id, id);
      if (res.error || !res.operation) {
        setError(res.error);
        return;
      }
      setOperation(res.operation);
      setFound(undefined);
      setParams({});
      setItems("");
      setCheck(undefined);
      setRun(undefined);
    });
  }

  function pick(path: string) {
    const at = focused ?? rows.findIndex((r) => !r.path);
    if (at === -1 || at === undefined || at >= rows.length) {
      setRows([...rows, { key: fieldName(path), path }]);
      return;
    }
    setRows(rows.map((r, i) => (i === at ? { key: r.key || fieldName(path), path } : r)));
    setFocused(undefined);
  }

  function runCheck() {
    setError(undefined);
    startCheck(async () => {
      const res = await validateQuery(write());
      if (res.error) setError(res.error);
      setCheck(res.check);
    });
  }

  function runSample() {
    setError(undefined);
    startRun(async () => {
      const res = await dryRunQuery({ ...write(), connection_id: connectionId, max_items: 20 });
      if (res.error) setError(res.error);
      setRun(res.run);
      if (res.run) setCheck(res.run.check);
    });
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    save(async () => {
      const res = await createQuery(write());
      if (res.error) {
        setError(res.error);
        return;
      }
      setOpen(false);
      reset();
    });
  }

  const columns = run?.items.length ? Object.keys(run.items[0]) : [];
  const general = (check?.errors ?? []).filter(
    (p) => !p.pointer.startsWith("/params/") && !p.pointer.startsWith("/fields/") && p.pointer !== "/regions",
  );

  return (
    <CrudDialog
      wide
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setError(undefined);
      }}
      title={`New query source on ${integration.name}`}
      description="Read more from the vendor without code: one read operation, its parameters, and the fields to keep. Rules read it like a built-in resource."
      trigger={
        <Button variant="ghost" size="xs" aria-label={`Define a query on ${integration.name}`}>
          <Plus className="size-3.5" aria-hidden />
          Define a query
        </Button>
      }
    >
      <form onSubmit={handleSubmit} className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
        <div className="flex min-w-0 flex-col gap-4">
          <FormError error={error} />
          <Field
            label="Operation"
            htmlFor="query-search"
            required
            hint={smithy ? "Search AWS operations, such as security groups or s3 buckets." : "Search the vendor's API by name, path, or summary."}
          >
            <div className="flex gap-2">
              <Input
                id="query-search"
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    runSearch();
                  }
                }}
                placeholder={smithy ? "security groups" : "applications"}
              />
              <LoadingButton type="button" variant="outline" size="sm" className="h-8 gap-1.5" loading={searching} onClick={runSearch}>
                {!searching && <Search className="size-3.5" aria-hidden />}
                Search
              </LoadingButton>
            </div>
          </Field>
          {found && (
            <ul aria-label="Operations" className="flex max-h-56 flex-col divide-y overflow-auto rounded-xl border bg-card">
              {found.length === 0 && <li className="px-3 py-2 text-xs text-muted-foreground">No read operations match.</li>}
              {found.map((o) => (
                <li key={o.id}>
                  <button
                    type="button"
                    onClick={() => choose(o.id)}
                    className="flex w-full flex-col gap-0.5 px-3 py-2 text-left hover:bg-muted/30"
                    aria-label={`Use ${o.id}`}
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs">{o.id}</span>
                      <span className="font-mono text-[10px] text-muted-foreground">{o.protocol ?? `${o.method} ${o.path}`}</span>
                    </span>
                    <span className="text-[11px] text-muted-foreground">{o.summary}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {operation && (
            <div className="flex flex-col gap-1 rounded-xl border bg-muted/20 px-3 py-2" aria-label="Chosen operation">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-sm">{operation.id}</span>
                {operation.protocol && <StatusBadge tone="neutral">{operation.protocol}</StatusBadge>}
                {smithy && <StatusBadge tone="contribution">{operation.regional ? "regional" : "global"}</StatusBadge>}
              </div>
              <span className="text-xs text-muted-foreground">{operation.summary}</span>
            </div>
          )}

          <div className="grid grid-cols-[minmax(0,1fr)_6rem] gap-3">
            <Field label="Name" htmlFor="query-name" required hint="Lowercase letters, digits, and dashes.">
              <Input id="query-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="active-apps" required />
            </Field>
            <Field label="Version" htmlFor="query-version" required>
              <Input id="query-version" type="number" min={1} value={version} onChange={(e) => setVersion(e.target.value)} />
            </Field>
          </div>
          <Field label="Description" htmlFor="query-description">
            <Input id="query-description" value={description} onChange={(e) => setDescription(e.target.value)} />
          </Field>

          {operation && operation.parameters.length > 0 && (
            <fieldset className="flex flex-col gap-3">
              <legend className="pb-1.5 font-mono text-[11px] tracking-[0.1em] text-muted-foreground uppercase">Parameters</legend>
              {operation.parameters.map((p) => {
                const id = `query-param-${p.name}`;
                const json = p.in === "json";
                return (
                  <Field key={p.name} label={p.name} htmlFor={id} required={p.required} hint={json ? `JSON (${p.type})` : (p.description ?? p.type)}>
                    {json ? (
                      <Textarea
                        id={id}
                        spellCheck={false}
                        className="min-h-12 font-mono text-xs"
                        value={params[p.name] ?? ""}
                        onChange={(e) => setParams({ ...params, [p.name]: e.target.value })}
                        aria-invalid={problems.has(`/params/${p.name}`)}
                      />
                    ) : (
                      <Input
                        id={id}
                        value={params[p.name] ?? ""}
                        onChange={(e) => setParams({ ...params, [p.name]: e.target.value })}
                        aria-invalid={problems.has(`/params/${p.name}`)}
                      />
                    )}
                    {problems.get(`/params/${p.name}`)?.map((d) => (
                      <span key={d} className="text-[11px] text-gap-ink">
                        {d}
                      </span>
                    ))}
                  </Field>
                );
              })}
            </fieldset>
          )}

          {smithy && operation?.regional && (
            <Field label="Regions" htmlFor="query-regions" hint="Region codes, comma-separated, or * for the connection's regions. Items gain region.">
              <Input id="query-regions" value={regions} onChange={(e) => setRegions(e.target.value)} className="font-mono" />
              {problems.get("/regions")?.map((d) => (
                <span key={d} className="text-[11px] text-gap-ink">
                  {d}
                </span>
              ))}
            </Field>
          )}
          <Field
            label="Items"
            htmlFor="query-items"
            hint={operation?.items ? `Where the list is. Empty uses ${operation.items}.` : "Dotted path to the list in the response. Empty when the response is the list."}
          >
            <Input id="query-items" value={items} onChange={(e) => setItems(e.target.value)} className="font-mono" placeholder={operation?.items ?? ""} />
          </Field>

          <fieldset className="flex flex-col gap-2" aria-label="Fields to keep">
            <legend className="pb-1.5 font-mono text-[11px] tracking-[0.1em] text-muted-foreground uppercase">Fields to keep</legend>
            <p className="text-[11px] text-muted-foreground">
              Output name and the path it reads in each item. <span className="font-mono">id</span> and{" "}
              <span className="font-mono">name</span> name failing items. Click an item field to fill the focused row.
            </p>
            {rows.map((row, i) => (
              <div key={i} className="flex flex-col gap-1">
                <div className="grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)_auto] items-center gap-2">
                  <Input
                    aria-label={`Field name ${i + 1}`}
                    value={row.key}
                    onChange={(e) => setRows(rows.map((r, n) => (n === i ? { ...r, key: e.target.value } : r)))}
                    onFocus={() => setFocused(i)}
                    className="font-mono text-xs"
                  />
                  <Input
                    aria-label={`Path of ${row.key || `field ${i + 1}`}`}
                    value={row.path}
                    onChange={(e) => setRows(rows.map((r, n) => (n === i ? { ...r, path: e.target.value } : r)))}
                    onFocus={() => setFocused(i)}
                    aria-invalid={problems.has(`/fields/${row.key}`)}
                    className="font-mono text-xs"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-xs"
                    aria-label={`Remove field ${row.key || i + 1}`}
                    onClick={() => setRows(rows.filter((_, n) => n !== i))}
                  >
                    <X className="size-3.5" aria-hidden />
                  </Button>
                </div>
                {problems.get(`/fields/${row.key}`)?.map((d) => (
                  <span key={d} className="text-[11px] text-gap-ink">
                    {d}
                  </span>
                ))}
              </div>
            ))}
            <Button type="button" variant="outline" size="xs" className="self-start" onClick={() => setRows([...rows, { key: "", path: "" }])}>
              <Plus className="size-3.5" aria-hidden />
              Add field
            </Button>
          </fieldset>

          <FormActions pending={saving} submitLabel="Save query source" onCancel={() => setOpen(false)} />
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          <section aria-label="Check" className="flex flex-col gap-3 rounded-xl border bg-muted/20 p-4">
            <div className="flex items-center justify-between gap-3">
              <span className="font-mono text-[11px] tracking-[0.1em] text-muted-foreground uppercase">Check</span>
              <LoadingButton type="button" variant="outline" size="sm" className="h-7 gap-1.5 px-2.5 text-xs" loading={checking} onClick={runCheck}>
                {!checking && <ShieldCheck className="size-3.5" aria-hidden />}
                Validate
              </LoadingButton>
            </div>
            {!check && <p className="text-xs text-muted-foreground">Checks the definition against the vendor&apos;s API model. Nothing is called.</p>}
            {check && (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  {check.valid ? (
                    <StatusBadge tone="met" icon={CircleCheck}>
                      valid
                    </StatusBadge>
                  ) : (
                    <StatusBadge tone="gap" icon={FileWarning}>
                      {check.errors.length} {check.errors.length === 1 ? "problem" : "problems"}
                    </StatusBadge>
                  )}
                  <span className="font-mono text-[11px] text-muted-foreground">{check.source}</span>
                </div>
                {general.map((p) => (
                  <p key={p.pointer + p.detail} className="text-[11px] text-gap-ink">
                    <span className="font-mono">{p.pointer}</span> {p.detail}
                  </p>
                ))}
                {check.fields.length > 0 && (
                  <p className="font-mono text-[11px] text-muted-foreground" aria-label="Item schema">
                    {check.fields.map((f) => `${f.name}: ${f.type}${f.nullable ? "?" : ""}`).join(" · ")}
                  </p>
                )}
              </>
            )}
          </section>

          <section aria-label="Dry run" className="flex flex-col gap-3 rounded-xl border bg-muted/20 p-4">
            <div className="flex items-center justify-between gap-3">
              <span className="font-mono text-[11px] tracking-[0.1em] text-muted-foreground uppercase">Dry run</span>
              <LoadingButton
                type="button"
                variant="outline"
                size="sm"
                className="h-7 gap-1.5 px-2.5 text-xs"
                loading={running}
                disabled={running || !connectionId}
                onClick={runSample}
              >
                {!running && <Play className="size-3.5" aria-hidden />}
                Run sample
              </LoadingButton>
            </div>
            {connections.length === 0 ? (
              <p className="text-xs text-muted-foreground">Connect a {integration.name} account to sample this query.</p>
            ) : (
              <Field label="Connection" htmlFor="query-connection">
                <Select id="query-connection" value={connectionId} onChange={(e) => setConnectionId(e.target.value)}>
                  {connections.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            {run?.error && <p className="text-xs text-gap-ink">{run.error}</p>}
            {run && !run.error && <p className="text-xs">{run.count} items sampled. Nothing is stored.</p>}
            {run?.warnings.map((w) => (
              <p key={w.pointer + w.detail} className="text-[11px] text-waived-ink">
                {w.detail}
              </p>
            ))}
            {columns.length > 0 && (
              <div className="max-h-64 overflow-auto rounded-lg border bg-card">
                <table className="w-full text-left text-xs" aria-label="Sample items">
                  <thead className="border-b bg-muted/30 font-mono text-[10px] tracking-[0.08em] text-muted-foreground uppercase">
                    <tr>
                      {columns.map((c) => (
                        <th key={c} className="px-2 py-1.5 font-medium">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {run!.items.map((item, n) => (
                      <tr key={n}>
                        {columns.map((c) => (
                          <td key={c} className="max-w-40 truncate px-2 py-1 font-mono" title={JSON.stringify(item[c])}>
                            {item[c] === null || item[c] === undefined ? "—" : typeof item[c] === "object" ? JSON.stringify(item[c]) : String(item[c])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <aside aria-label="Item fields" className="flex min-w-0 flex-col gap-2">
            <span className="font-mono text-[11px] tracking-[0.1em] text-muted-foreground uppercase">Item fields</span>
            {!operation && <p className="text-[11px] text-muted-foreground">Choose an operation to see what each item holds.</p>}
            {operation && (
              <ul className="flex max-h-72 flex-col divide-y overflow-auto rounded-xl border bg-card">
                {smithy && operation.regional && (
                  <li>
                    <button type="button" onClick={() => pick("$region")} className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-muted/30" aria-label="Use $region">
                      <span className="font-mono text-xs">$region</span>
                      <span className="font-mono text-[10px] text-muted-foreground">the region collected</span>
                    </button>
                  </li>
                )}
                {(operation.fields ?? []).map((f) => (
                  <li key={f.path}>
                    <button
                      type="button"
                      onClick={() => pick(f.path)}
                      className="flex w-full flex-col gap-0.5 px-3 py-2 text-left hover:bg-muted/30"
                      aria-label={`Use ${f.path}`}
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="font-mono text-xs">{f.path}</span>
                        <span className="font-mono text-[10px] text-muted-foreground">{f.type}</span>
                      </span>
                      {f.description && <span className="text-[11px] text-muted-foreground">{f.description}</span>}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </aside>
        </div>
      </form>
    </CrudDialog>
  );
}
