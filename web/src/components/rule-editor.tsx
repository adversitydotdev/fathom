"use client";

import { CircleCheck, CircleDashed, CircleX, Eye, FileWarning, Plus, TriangleAlert } from "lucide-react";
import { useMemo, useRef, useState, useTransition } from "react";

import { CrudDialog, Field, FormActions, FormError, Select, Textarea } from "@/components/crud";
import { StatusBadge, type StatusTone } from "@/components/spectrumui/status-badge";
import { LoadingButton } from "@/components/spectrumui/loading-button-dependencies";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createRuleTest, previewRule, type RulePreview } from "@/lib/actions";

export type RuleSource = {
  source: string;
  integration: string;
  resource: string;
  fields: { name: string; type: string; nullable: boolean; required: boolean; description?: string }[];
};
export type Option = { id: string; label: string };
export type FulfillOption = Option & { controlId: string };

const INTERVALS = ["daily", "weekly", "monthly", "quarterly", "annual", "continuous"];
type Expression = "select" | "assert" | "aggregate";

const OUTCOME: Record<RulePreview["outcome"], { tone: StatusTone; icon: typeof CircleCheck; label: string }> = {
  pass: { tone: "met", icon: CircleCheck, label: "pass" },
  fail: { tone: "gap", icon: CircleX, label: "fail" },
  error: { tone: "gap", icon: TriangleAlert, label: "error" },
  invalid: { tone: "gap", icon: FileWarning, label: "does not compile" },
  "no-data": { tone: "waived", icon: CircleDashed, label: "no snapshot yet" },
};

/**
 * Write a `rule` test over an integration's snapshots (RFC 0001 section 7.6) and try it
 * against the latest snapshot before saving. The preview runs the server's rule runner;
 * nothing is collected or recorded until "Create test".
 */
export function RuleEditorDialog({
  sources,
  controls,
  fulfills,
  initialSource,
  trigger,
}: {
  sources: RuleSource[];
  controls: Option[];
  fulfills: FulfillOption[];
  initialSource?: string;
  trigger?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [saving, save] = useTransition();
  const [previewing, preview] = useTransition();
  const [error, setError] = useState<string>();
  const [result, setResult] = useState<RulePreview>();

  const [name, setName] = useState("");
  const [controlRef, setControlRef] = useState(controls[0]?.id ?? "");
  const [fulfillsRef, setFulfillsRef] = useState("");
  const [interval, setInterval] = useState("daily");
  const [source, setSource] = useState(initialSource ?? sources[0]?.source ?? "");
  const [expressions, setExpressions] = useState<Record<Expression, string>>({ select: "", assert: "", aggregate: "" });
  const [allowEmpty, setAllowEmpty] = useState(false);
  const [focused, setFocused] = useState<Expression>("assert");
  const areas = { select: useRef<HTMLTextAreaElement>(null), assert: useRef<HTMLTextAreaElement>(null), aggregate: useRef<HTMLTextAreaElement>(null) };

  const chosen = sources.find((s) => s.source === source);
  const candidates = fulfills.filter((f) => f.controlId === controlRef);
  const problems = useMemo(() => {
    const by = new Map<string, { errors: string[]; warnings: string[] }>();
    for (const [kind, list] of [["errors", result?.errors ?? []], ["warnings", result?.warnings ?? []]] as const) {
      for (const p of list) {
        const key = p.pointer.replace("/run/", "");
        const entry = by.get(key) ?? { errors: [], warnings: [] };
        entry[kind].push(p.detail);
        by.set(key, entry);
      }
    }
    return by;
  }, [result]);

  const run = () => ({
    source,
    ...(expressions.select.trim() ? { select: expressions.select.trim() } : {}),
    ...(expressions.assert.trim() ? { assert: expressions.assert.trim() } : {}),
    ...(expressions.aggregate.trim() ? { aggregate: expressions.aggregate.trim() } : {}),
    ...(allowEmpty ? { allow_empty: true } : {}),
  });

  function insertField(field: string) {
    const area = areas[focused].current;
    const text = expressions[focused];
    const at = area ? area.selectionStart : text.length;
    const insert = `${focused === "aggregate" ? "items.all(i, i." : "item."}${field}${focused === "aggregate" ? ")" : ""}`;
    const next = text.slice(0, at) + insert + text.slice(area ? area.selectionEnd : at);
    setExpressions({ ...expressions, [focused]: next });
    requestAnimationFrame(() => {
      area?.focus();
      area?.setSelectionRange(at + insert.length, at + insert.length);
    });
  }

  function runPreview() {
    setError(undefined);
    preview(async () => {
      const res = await previewRule({ run: run(), control_ref: controlRef || undefined });
      if (res.error) setError(res.error);
      setResult(res.preview);
    });
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    save(async () => {
      const res = await createRuleTest({
        name: name.trim(),
        control_ref: controlRef,
        method: "automated",
        interval: interval as "daily",
        required: true,
        ...(fulfillsRef ? { fulfills_ref: fulfillsRef } : {}),
        run: { runner: "rule", ...run() },
      });
      if (res.error) {
        setError(res.error);
        return;
      }
      setOpen(false);
      setName("");
      setExpressions({ select: "", assert: "", aggregate: "" });
      setResult(undefined);
    });
  }

  const outcome = result ? OUTCOME[result.outcome] : undefined;

  return (
    <CrudDialog
      wide
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) setError(undefined);
      }}
      title="New rule test"
      description="A rule evaluates an integration's collected snapshot. Preview it against the latest snapshot before saving."
      trigger={
        trigger ?? (
          <Button size="sm" variant="outline" className="gap-1.5">
            <Plus className="size-3.5" aria-hidden />
            New rule test
          </Button>
        )
      }
    >
      <form onSubmit={handleSubmit} className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
        <div className="flex min-w-0 flex-col gap-4">
          <FormError error={error} />
          <Field label="Name" htmlFor="rule-name" required>
            <Input id="rule-name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="No Okta user idle for 90 days" />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Control" htmlFor="rule-control" required>
              <Select
                id="rule-control"
                value={controlRef}
                onChange={(e) => {
                  setControlRef(e.target.value);
                  setFulfillsRef("");
                }}
              >
                {controls.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Fulfills" htmlFor="rule-fulfills" hint="Optional. Replaces that test as the control's methodology.">
              <Select id="rule-fulfills" value={fulfillsRef} onChange={(e) => setFulfillsRef(e.target.value)}>
                <option value="">— none —</option>
                {candidates.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Source" htmlFor="rule-source" required>
              <Select
                id="rule-source"
                value={source}
                onChange={(e) => {
                  setSource(e.target.value);
                  setResult(undefined);
                }}
              >
                {sources.map((s) => (
                  <option key={s.source} value={s.source}>
                    {s.integration} · {s.resource}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Interval" htmlFor="rule-interval">
              <Select id="rule-interval" value={interval} onChange={(e) => setInterval(e.target.value)}>
                {INTERVALS.map((i) => (
                  <option key={i} value={i}>
                    {i}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          {(
            [
              ["select", "Select", "Which items are in scope, such as item.status == \"ACTIVE\". Empty selects all."],
              ["assert", "Assert", "What every selected item must satisfy."],
              ["aggregate", "Aggregate", "A condition over all selected items, as items. Optional."],
            ] as const
          ).map(([key, label, hint]) => (
            <Field key={key} label={label} htmlFor={`rule-${key}`} hint={hint}>
              <Textarea
                id={`rule-${key}`}
                ref={areas[key]}
                value={expressions[key]}
                onFocus={() => setFocused(key)}
                onChange={(e) => setExpressions({ ...expressions, [key]: e.target.value })}
                spellCheck={false}
                className="min-h-12 font-mono text-xs"
                aria-invalid={Boolean(problems.get(key)?.errors.length)}
              />
              {problems.get(key)?.errors.map((d) => (
                <span key={d} className="text-[11px] text-gap-ink">
                  {d}
                </span>
              ))}
              {problems.get(key)?.warnings.map((d) => (
                <span key={d} className="text-[11px] text-waived-ink">
                  {d}
                </span>
              ))}
            </Field>
          ))}
          {problems.get("source")?.errors.map((d) => (
            <FormError key={d} error={d} />
          ))}
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input type="checkbox" checked={allowEmpty} onChange={(e) => setAllowEmpty(e.target.checked)} />
            Pass when nothing is selected (otherwise an empty selection is an error)
          </label>


          <FormActions pending={saving} submitLabel="Create test" onCancel={() => setOpen(false)} />
        </div>

        <div className="flex min-w-0 flex-col gap-4">
            <section aria-label="Preview" className="flex flex-col gap-3 rounded-xl border bg-muted/20 p-4">
              <div className="flex items-center justify-between gap-3">
                <span className="font-mono text-[11px] tracking-[0.1em] text-muted-foreground uppercase">Preview</span>
                <LoadingButton type="button" variant="outline" size="sm" className="h-7 gap-1.5 px-2.5 text-xs" loading={previewing} disabled={previewing || !source} onClick={runPreview}>
                  {!previewing && <Eye className="size-3.5" aria-hidden />}
                  Preview
                </LoadingButton>
              </div>
              {!result && <p className="text-xs text-muted-foreground">Runs the rule over the latest snapshot. Nothing is saved.</p>}
              {result && outcome && (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge tone={outcome.tone} icon={outcome.icon}>
                      {outcome.label}
                    </StatusBadge>
                    <span className="text-sm">{result.summary}</span>
                  </div>
                  {result.snapshots.length > 0 && (
                    <p className="font-mono text-[11px] text-muted-foreground">
                      {result.total} items from {result.snapshots.map((s) => `${s.connection_name} (${s.collected.slice(0, 10)})`).join(", ")}
                      {Object.keys(result.params).length > 0 && ` · params ${Object.keys(result.params).join(", ")}`}
                    </p>
                  )}
                  {result.subjects.length > 0 && (
                    <div className="overflow-hidden rounded-lg border bg-card">
                      <table className="w-full text-left text-xs" aria-label="Failing items">
                        <thead className="border-b bg-muted/30 font-mono text-[10px] tracking-[0.08em] text-muted-foreground uppercase">
                          <tr>
                            <th className="px-3 py-2 font-medium">Failing item</th>
                            <th className="px-3 py-2 font-medium">Id</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y">
                          {result.subjects.slice(0, 10).map((s) => (
                            <tr key={`${s.external_id}-${s.name}`}>
                              <td className="px-3 py-1.5">{s.name}</td>
                              <td className="px-3 py-1.5 font-mono text-muted-foreground">{s.external_id ?? "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {result.subjects.length > 10 && (
                        <p className="border-t px-3 py-1.5 text-[11px] text-muted-foreground">and {result.subjects.length - 10} more</p>
                      )}
                    </div>
                  )}
                  {result.sample.length > 0 && (
                    <details className="text-xs">
                      <summary className="cursor-pointer text-muted-foreground">Sample items</summary>
                      <pre className="mt-2 max-h-48 overflow-auto rounded-lg border bg-card p-2 font-mono text-[11px]">{JSON.stringify(result.sample, null, 2)}</pre>
                    </details>
                  )}
                </>
              )}
            </section>
        <aside aria-label="Fields" className="flex min-w-0 flex-col gap-2">
          <span className="font-mono text-[11px] tracking-[0.1em] text-muted-foreground uppercase">
            Fields of {chosen?.resource ?? "the source"}
          </span>
          <p className="text-[11px] text-muted-foreground">
            Click to insert into <span className="font-mono text-foreground">{focused}</span>.
          </p>
          <ul className="flex flex-col divide-y rounded-xl border bg-card">
            {(chosen?.fields ?? []).map((f) => (
              <li key={f.name}>
                <button
                  type="button"
                  onClick={() => insertField(f.name)}
                  className="flex w-full flex-col gap-0.5 px-3 py-2 text-left hover:bg-muted/30"
                  aria-label={`Insert ${f.name}`}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs">{f.name}</span>
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {f.type}
                      {f.nullable ? " | null" : ""}
                    </span>
                  </span>
                  {f.description && <span className="text-[11px] text-muted-foreground">{f.description}</span>}
                </button>
              </li>
            ))}
          </ul>
          <p className="text-[11px] text-muted-foreground">
            Also available: <span className="font-mono">params.&lt;name&gt;</span> (the control&apos;s parameters),{" "}
            <span className="font-mono">observed</span>, <span className="font-mono">days(&quot;90 days&quot;)</span>.
          </p>
        </aside>
        </div>
      </form>
    </CrudDialog>
  );
}
