"use client";

import { CircleCheck, FileWarning, Play, Plus, Search, ShieldCheck, Sparkles, X } from "lucide-react";
import { useEffect, useMemo, useState, useTransition } from "react";

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
type Bind = { param: string; path: string };

/** What the assistant proposes (RFC 0006 section 9): an unsaved definition and the rule that reads it. */
export type QueryDraft = { definition: QueryWrite; rule?: { source?: string; select?: string; assert?: string; aggregate?: string } };

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
export function QueryEditorDialog({
  integration,
  connections,
  draft,
}: {
  integration: Integration;
  connections: Connection[];
  draft?: QueryDraft;
}) {
  const initial = draft?.definition;
  const [open, setOpen] = useState(Boolean(draft));
  const [error, setError] = useState<string>();
  const [searching, search] = useTransition();
  const [checking, startCheck] = useTransition();
  const [running, startRun] = useTransition();
  const [saving, save] = useTransition();

  const [text, setText] = useState(initial?.operation ?? "");
  const [found, setFound] = useState<Operation[]>();
  const [operation, setOperation] = useState<Operation>();
  const [name, setName] = useState(initial?.name ?? "");
  const [version, setVersion] = useState(String(initial?.version ?? 1));
  const [description, setDescription] = useState(initial?.description ?? "");
  const [params, setParams] = useState<Record<string, string>>(initial?.params ?? {});
  const [regions, setRegions] = useState(
    Array.isArray(initial?.regions) ? initial.regions.join(", ") : (initial?.regions ?? "*"),
  );
  const [items, setItems] = useState(initial?.items ?? "");
  const [rows, setRows] = useState<Row[]>(
    initial?.fields ? Object.entries(initial.fields).map(([key, path]) => ({ key, path })) : START,
  );
  const [focused, setFocused] = useState<number>();
  const [check, setCheck] = useState<QueryCheck>();
  const [run, setRun] = useState<DryRun>();
  const [connectionId, setConnectionId] = useState(connections[0]?.id ?? "");

  // for_each (RFC 0006 section 3): a list operation, and the parameters each listed item fills.
  const initialEach = initial?.for_each;
  const [each, setEach] = useState(Boolean(initialEach));
  const [listText, setListText] = useState(initialEach?.operation ?? "");
  const [listFound, setListFound] = useState<Operation[]>();
  const [listOperation, setListOperation] = useState<Operation>();
  const [listParams, setListParams] = useState<Record<string, string>>(initialEach?.params ?? {});
  const [listItems, setListItems] = useState(initialEach?.items ?? "");
  const [binds, setBinds] = useState<Bind[]>(
    initialEach ? Object.entries(initialEach.bind).map(([param, path]) => ({ param, path })) : [],
  );
  const [limit, setLimit] = useState(String(initialEach?.limit ?? 1000));
  const [bindFocus, setBindFocus] = useState<number>();
  const boundParams = new Set(each ? binds.map((b) => b.param).filter(Boolean) : []);

  const smithy = integration.query_model === "smithy";

  // A draft names its operation; describe it once so parameters and item fields show.
  useEffect(() => {
    if (!initial?.operation) return;
    let active = true;
    void describeOperation(integration.id, initial.operation).then((res) => {
      if (active && res.operation) setOperation(res.operation);
    });
    return () => {
      active = false;
    };
  }, [integration.id, initial?.operation]);
  useEffect(() => {
    if (!initialEach?.operation) return;
    let active = true;
    void describeOperation(integration.id, initialEach.operation).then((res) => {
      if (active && res.operation) setListOperation(res.operation);
    });
    return () => {
      active = false;
    };
  }, [integration.id, initialEach?.operation]);
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
      params: set(Object.fromEntries(Object.entries(params).filter(([k]) => !boundParams.has(k)))),
      items: items.trim(),
      fields: Object.fromEntries(rows.filter((r) => r.key.trim()).map((r) => [r.key.trim(), r.path.trim()])),
      ...(regional
        ? { regions: regions.trim() === "*" ? "*" : regions.split(",").map((r) => r.trim()).filter(Boolean) }
        : {}),
      ...(each
        ? {
            for_each: {
              operation: listOperation?.id ?? listText.trim(),
              params: set(listParams),
              items: listItems.trim(),
              bind: Object.fromEntries(binds.filter((b) => b.param).map((b) => [b.param, b.path.trim()])),
              limit: Number(limit) || 1000,
            },
          }
        : {}),
    };
  }

  /** The parameters a listed item should fill: the required ones nothing else sets. */
  function defaultBinds(op: Operation | undefined): Bind[] {
    const required = (op?.parameters ?? []).filter((p) => p.required && !params[p.name]);
    return (required.length ? required : (op?.parameters ?? []).slice(0, 1)).map((p) => ({ param: p.name, path: "" }));
  }

  function runListSearch() {
    setError(undefined);
    search(async () => {
      const res = await searchOperations(integration.id, listText.trim());
      if (res.error) setError(res.error);
      setListFound(res.operations ?? []);
    });
  }

  function chooseList(id: string) {
    setError(undefined);
    search(async () => {
      const res = await describeOperation(integration.id, id);
      if (res.error || !res.operation) {
        setError(res.error);
        return;
      }
      setListOperation(res.operation);
      setListText(res.operation.id);
      setListFound(undefined);
      setListParams({});
      setListItems("");
      if (binds.length === 0) setBinds(defaultBinds(operation));
    });
  }

  /** A listed item's field fills the focused binding, or becomes a `$parent.` field. */
  function pickParent(path: string) {
    if (bindFocus !== undefined && bindFocus < binds.length) {
      setBinds(binds.map((b, i) => (i === bindFocus ? { ...b, path } : b)));
      setBindFocus(undefined);
      return;
    }
    pick(`$parent.${path}`);
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
    setEach(false);
    setListText("");
    setListFound(undefined);
    setListOperation(undefined);
    setListParams({});
    setListItems("");
    setBinds([]);
    setLimit("1000");
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
    const taken = new Set(rows.map((r) => r.key));
    const derived = fieldName(path);
    const key = !taken.has(derived) ? derived : path.startsWith("$parent.") ? `parent_${derived}` : `${derived}_2`;
    const at = focused ?? rows.findIndex((r) => !r.path);
    if (at === -1 || at === undefined || at >= rows.length) {
      setRows([...rows, { key, path }]);
      return;
    }
    setRows(rows.map((r, i) => (i === at ? { key: r.key || key, path } : r)));
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
    (p) =>
      !p.pointer.startsWith("/params/") &&
      !p.pointer.startsWith("/fields/") &&
      !p.pointer.startsWith("/for_each") &&
      p.pointer !== "/regions",
  );
  const eachProblems = (check?.errors ?? []).filter(
    (p) => p.pointer.startsWith("/for_each") && !p.pointer.startsWith("/for_each/bind/") && !p.pointer.startsWith("/for_each/params/"),
  );
  const problemText = (pointer: string) =>
    problems.get(pointer)?.map((d) => (
      <span key={d} className="text-[11px] text-gap-ink">
        {d}
      </span>
    ));

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
          {draft && (
            <div className="flex flex-col gap-1 rounded-xl border border-agent/35 bg-agent/8 px-3 py-2 text-xs" aria-label="Assistant draft">
              <span className="flex items-center gap-1.5 font-medium">
                <Sparkles className="size-3.5 text-agent" aria-hidden />
                Drafted by the assistant. Nothing is saved until you save it.
              </span>
              <span className="text-muted-foreground">Check it and run a sample before saving.</span>
              {draft.rule?.assert && (
                <span>
                  Suggested rule: <code className="font-mono">{draft.rule.assert}</code>
                </span>
              )}
            </div>
          )}
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
                if (boundParams.has(p.name)) {
                  return (
                    <Field key={p.name} label={p.name} htmlFor={id} required={p.required} hint="Filled from each listed item (For each, below).">
                      <Input id={id} disabled value={`from ${binds.find((b) => b.param === p.name)?.path || "each listed item"}`} className="font-mono text-xs" />
                    </Field>
                  );
                }
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
          {operation && (
            <fieldset aria-label="For each listed item" className="flex flex-col gap-3 rounded-xl border p-3">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={each}
                  onChange={(e) => {
                    setEach(e.target.checked);
                    if (e.target.checked && binds.length === 0) setBinds(defaultBinds(operation));
                  }}
                />
                Call once for each item another operation lists
              </label>
              <p className="text-[11px] text-muted-foreground">
                For settings read one resource at a time, such as each bucket&apos;s encryption or each group&apos;s members.
                Items gain <span className="font-mono">error</span> when a call fails.
              </p>
              {each && (
                <>
                  <Field label="List operation" htmlFor="query-list-search" required>
                    <div className="flex gap-2">
                      <Input
                        id="query-list-search"
                        value={listText}
                        onChange={(e) => setListText(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            runListSearch();
                          }
                        }}
                        placeholder={smithy ? "s3 buckets" : "groups"}
                      />
                      <Button type="button" variant="outline" size="sm" className="h-8 gap-1.5" onClick={runListSearch} aria-label="Search list operations">
                        <Search className="size-3.5" aria-hidden />
                        Search
                      </Button>
                    </div>
                  </Field>
                  {listFound && (
                    <ul aria-label="List operations" className="flex max-h-48 flex-col divide-y overflow-auto rounded-xl border bg-card">
                      {listFound.length === 0 && <li className="px-3 py-2 text-xs text-muted-foreground">No read operations match.</li>}
                      {listFound.map((o) => (
                        <li key={o.id}>
                          <button
                            type="button"
                            onClick={() => chooseList(o.id)}
                            className="flex w-full flex-col gap-0.5 px-3 py-2 text-left hover:bg-muted/30"
                            aria-label={`List with ${o.id}`}
                          >
                            <span className="font-mono text-xs">{o.id}</span>
                            <span className="text-[11px] text-muted-foreground">{o.summary}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                  {eachProblems.map((p) => (
                    <span key={p.pointer + p.detail} className="text-[11px] text-gap-ink">
                      {p.detail}
                    </span>
                  ))}
                  {listOperation?.parameters.map((p) => (
                    <Field
                      key={p.name}
                      label={`${p.name} (list)`}
                      htmlFor={`query-list-param-${p.name}`}
                      required={p.required}
                      hint={smithy && operation.regional ? "$region fills in the region being collected." : p.type}
                    >
                      <Input
                        id={`query-list-param-${p.name}`}
                        value={listParams[p.name] ?? ""}
                        onChange={(e) => setListParams({ ...listParams, [p.name]: e.target.value })}
                        className="font-mono text-xs"
                      />
                      {problemText(`/for_each/params/${p.name}`)}
                    </Field>
                  ))}
                  <Field
                    label="List items"
                    htmlFor="query-list-items"
                    hint={listOperation?.items ? `Empty uses ${listOperation.items}.` : "Dotted path to the list. Empty when the response is the list."}
                  >
                    <Input id="query-list-items" value={listItems} onChange={(e) => setListItems(e.target.value)} className="font-mono" placeholder={listOperation?.items ?? ""} />
                  </Field>
                  <div className="flex flex-col gap-2" aria-label="Bindings">
                    <span className="font-mono text-[11px] tracking-[0.1em] text-muted-foreground uppercase">Each listed item fills</span>
                    {binds.map((b, i) => (
                      <div key={i} className="flex flex-col gap-1">
                        <div className="grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)_auto] items-center gap-2">
                          <Select
                            aria-label={`Bound parameter ${i + 1}`}
                            value={b.param}
                            onChange={(e) => setBinds(binds.map((x, n) => (n === i ? { ...x, param: e.target.value } : x)))}
                          >
                            <option value="">— parameter —</option>
                            {operation.parameters.map((p) => (
                              <option key={p.name} value={p.name}>
                                {p.name}
                              </option>
                            ))}
                          </Select>
                          <Input
                            aria-label={`Listed item path for ${b.param || `binding ${i + 1}`}`}
                            value={b.path}
                            onChange={(e) => setBinds(binds.map((x, n) => (n === i ? { ...x, path: e.target.value } : x)))}
                            onFocus={() => setBindFocus(i)}
                            aria-invalid={problems.has(`/for_each/bind/${b.param}`)}
                            placeholder="path in each listed item"
                            className="font-mono text-xs"
                          />
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon-xs"
                            aria-label={`Remove binding ${b.param || i + 1}`}
                            onClick={() => setBinds(binds.filter((_, n) => n !== i))}
                          >
                            <X className="size-3.5" aria-hidden />
                          </Button>
                        </div>
                        {problemText(`/for_each/bind/${b.param}`)}
                      </div>
                    ))}
                    <Button type="button" variant="outline" size="xs" className="self-start" onClick={() => setBinds([...binds, { param: "", path: "" }])}>
                      <Plus className="size-3.5" aria-hidden />
                      Add binding
                    </Button>
                  </div>
                  <Field label="Limit" htmlFor="query-list-limit" hint="At most this many listed items; more makes the collection incomplete.">
                    <Input id="query-list-limit" type="number" min={1} max={5000} value={limit} onChange={(e) => setLimit(e.target.value)} className="w-32" />
                  </Field>
                </>
              )}
            </fieldset>
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
            {each && listOperation && (
              <>
                <span className="mt-2 font-mono text-[11px] tracking-[0.1em] text-muted-foreground uppercase">Listed item fields</span>
                <p className="text-[11px] text-muted-foreground">Fills the focused binding, or adds a field read from the listed item.</p>
                <ul aria-label="Listed item fields" className="flex max-h-56 flex-col divide-y overflow-auto rounded-xl border bg-card">
                  {(listOperation.fields ?? []).map((f) => (
                    <li key={f.path}>
                      <button
                        type="button"
                        onClick={() => pickParent(f.path)}
                        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-muted/30"
                        aria-label={`Use $parent.${f.path}`}
                      >
                        <span className="font-mono text-xs">$parent.{f.path}</span>
                        <span className="font-mono text-[10px] text-muted-foreground">{f.type}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </aside>
        </div>
      </form>
    </CrudDialog>
  );
}
