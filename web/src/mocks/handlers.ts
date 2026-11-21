import { http, HttpResponse, type HttpResponseResolver } from "msw";

import type { Connection, Job, Test } from "@/lib/api/types";

import { CelError, evaluate as evaluateCel } from "./cel";
import { db } from "./db";
import { snapshotItems } from "./fixtures/program";
import { programStatus, programSummary, systemGaps } from "./kernel";

/** Matches `/v1` on any origin, so the same handlers serve in-process and HTTP calls. */
const V = "*/v1";

type Obj = { id: string; revoked?: boolean; name?: string; display_id?: string };
type Filters<T> = Record<string, (item: T, value: string) => boolean>;

export function problem(status: number, slug: string, title: string, detail?: string) {
  return HttpResponse.json(
    { type: `urn:ogrl:problem:${slug}`, title, status, detail },
    { status, headers: { "Content-Type": "application/problem+json" } },
  );
}

const notFound = () => problem(404, "not-found", "The id is unknown.");

/** RFC 0004 section 3: cursor pages. The cursor is an opaque offset. */
function page<T>(items: T[], url: URL) {
  const limit = Math.min(200, Math.max(1, Number(url.searchParams.get("limit") ?? 50) || 50));
  const cursor = url.searchParams.get("cursor");
  const offset = cursor ? Number(atob(cursor)) || 0 : 0;
  const next = offset + limit;
  return {
    data: items.slice(offset, next),
    page: { limit, ...(next < items.length ? { next_cursor: btoa(String(next)) } : {}) },
  };
}

const matchesQuery = (item: Obj, q: string) =>
  [item.id, item.name, item.display_id].some((v) => v?.toLowerCase().includes(q.toLowerCase()));

function list<T extends Obj>(path: string, items: () => T[], filters: Filters<T> = {}) {
  return http.get(`${V}${path}`, ({ request }) => {
    const url = new URL(request.url);
    let out = items();
    if (url.searchParams.get("revoked") !== "true") out = out.filter((i) => !i.revoked);
    for (const [key, test] of Object.entries(filters)) {
      const value = url.searchParams.get(key);
      if (value !== null) out = out.filter((i) => test(i, value));
    }
    return HttpResponse.json(page(out, url));
  });
}

function one<T extends Obj>(path: string, items: () => T[]) {
  return http.get(`${V}${path}/:id`, ({ params }) => {
    const item = items().find((i) => i.id === params.id);
    return item ? HttpResponse.json(item) : notFound();
  });
}

function sub<T>(path: string, parent: () => Obj[], children: (id: string) => T[]): ReturnType<typeof http.get> {
  const resolver: HttpResponseResolver<{ id: string }> = ({ params, request }) => {
    if (!parent().some((p) => p.id === params.id)) return notFound();
    return HttpResponse.json(page(children(params.id), new URL(request.url)));
  };
  return http.get(`${V}${path}`, resolver);
}

const eq = (field: string) => (item: object, v: string) => (item as Record<string, unknown>)[field] === v;
const q = (item: Obj, v: string) => matchesQuery(item, v);

type MutableObj = Obj & { type?: string; spec_version?: string; created?: string; modified?: string; [k: string]: unknown };

function crud<T extends MutableObj>(path: string, typeName: string, items: () => T[], extraDefaults: Record<string, unknown> = {}) {
  return [
    http.post(`${V}${path}`, async ({ request }) => {
      const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
      const now = new Date().toISOString();
      const created = {
        type: typeName,
        id: typeof body.id === "string" && body.id ? body.id : `${typeName}--${crypto.randomUUID().slice(0, 8)}`,
        spec_version: "0.1.0",
        created: now,
        modified: now,
        ...extraDefaults,
        ...body,
      } as unknown as T;
      items().unshift(created);
      return HttpResponse.json(created, { status: 201 });
    }),
    http.patch(`${V}${path}/:id`, async ({ params, request }) => {
      const arr = items();
      const idx = arr.findIndex((i) => i.id === params.id);
      if (idx < 0) return notFound();
      const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
      const updated = { ...arr[idx], ...body, modified: new Date().toISOString() } as T;
      arr[idx] = updated;
      return HttpResponse.json(updated);
    }),
    http.post(`${V}${path}/:id/revoke`, ({ params }) => {
      const arr = items();
      const idx = arr.findIndex((i) => i.id === params.id);
      if (idx < 0) return notFound();
      const updated = { ...arr[idx], revoked: true, modified: new Date().toISOString() } as T;
      arr[idx] = updated;
      return HttpResponse.json(updated);
    }),
  ];
}

function contentUpload<T extends MutableObj>(path: string, items: () => T[]) {
  return http.post(`${V}${path}/:id/content`, ({ params }) => {
    const arr = items();
    const idx = arr.findIndex((i) => i.id === params.id);
    if (idx < 0) return notFound();
    const updated = {
      ...arr[idx],
      modified: new Date().toISOString(),
      resource: {
        uri: `s3://acme-ogrl-evidence/${params.id}`,
        media_type: "text/markdown",
        digest: { algorithm: "sha-256", value: "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90" },
      },
    } as T;
    arr[idx] = updated;
    return HttpResponse.json(updated);
  });
}

export const handlers = [
  http.get("*/health", () => HttpResponse.json({ status: "ok" })),

  list("/frameworks", () => db.frameworks),
  one("/frameworks", () => db.frameworks),
  list("/requirements", () => db.requirements, { framework_id: eq("framework_ref"), class: eq("class"), q }),
  one("/requirements", () => db.requirements),
  sub("/requirements/:id/mappings", () => db.requirements, (id) => db.mappings.filter((m) => m.target_ref.split("#")[0] === id)),

  list("/controls", () => db.controls, { origin: eq("origin"), family: eq("family"), q }),
  one("/controls", () => db.controls),
  sub("/controls/:id/mappings", () => db.controls, (id) => db.mappings.filter((m) => m.source_ref === id)),
  sub("/controls/:id/tests", () => db.controls, (id) => db.tests.filter((t) => t.control_ref === id)),
  sub("/controls/:id/implementations", () => db.controls, (id) => db.implementations.filter((i) => i.control_ref === id)),

  list("/mappings", () => db.mappings, { source_id: eq("source_ref"), target_id: (m, v) => m.target_ref.split("#")[0] === v, relationship: eq("relationship"), review_status: eq("review_status") }),
  one("/mappings", () => db.mappings),
  list("/baselines", () => db.baselines),
  one("/baselines", () => db.baselines),
  http.get(`${V}/baselines/:id/effective`, ({ params }) => {
    const b = db.baselines.find((x) => x.id === params.id);
    return b ? HttpResponse.json(b) : notFound();
  }),

  list("/tests", () => db.tests, { control_id: eq("control_ref"), method: eq("method"), required: (t, v) => String(t.required ?? false) === v }),
  one("/tests", () => db.tests),
  http.post(`${V}/tests/:id/runs`, async ({ params, request }) => {
    const test = db.tests.find((t) => t.id === params.id);
    if (!test) return notFound();
    const body = (await request.json().catch(() => ({}))) as { implementation_id?: string };
    if (!db.implementations.some((i) => i.id === body.implementation_id)) {
      return problem(400, "bad-request", "implementation_id must name an implementation.");
    }
    if (!test.run) return problem(400, "bad-request", "This test has no run block.");
    const job: Job = { id: `job--${crypto.randomUUID()}`, type: "test_run", status: "queued", created: new Date().toISOString() };
    db.jobs.unshift(job);
    return HttpResponse.json(job, { status: 202 });
  }),

  list("/parties", () => db.parties, { kind: eq("kind"), q }),
  one("/parties", () => db.parties),
  list("/components", () => db.components),
  one("/components", () => db.components),
  list("/systems", () => db.systems),
  one("/systems", () => db.systems),
  http.get(`${V}/systems/:id/gaps`, ({ params, request }) => {
    if (!db.systems.some((s) => s.id === params.id)) return notFound();
    return HttpResponse.json(systemGaps(params.id as string, new URL(request.url).searchParams.get("at")));
  }),

  list("/programs", () => db.programs, { system_id: eq("system_ref") }),
  one("/programs", () => db.programs),
  http.get(`${V}/programs/:id/summary`, ({ params, request }) => {
    const s = programSummary(params.id as string, new URL(request.url).searchParams.get("at"));
    return s ? HttpResponse.json(s) : notFound();
  }),
  http.get(`${V}/programs/:id/status`, ({ params, request }) => {
    const sp = new URL(request.url).searchParams;
    const s = programStatus(params.id as string, sp.get("at"), sp.get("framework_id"));
    return s ? HttpResponse.json(s) : notFound();
  }),

  list("/implementations", () => db.implementations, {
    system_id: eq("system_ref"),
    control_id: eq("control_ref"),
    component_id: eq("component_ref"),
    status: eq("status"),
    responsibility: eq("responsibility"),
    origin: eq("origin"),
  }),
  one("/implementations", () => db.implementations),
  sub("/implementations/:id/results", () => db.implementations, (id) =>
    db.results.filter((r) => r.implementation_ref === id).sort((a, b) => b.observed.localeCompare(a.observed)),
  ),
  sub("/implementations/:id/evidence", () => db.implementations, (id) => db.evidence.filter((e) => e.implementation_ref === id)),

  list("/results", () => db.results, { test_id: eq("test_ref"), implementation_id: eq("implementation_ref"), outcome: eq("outcome") }),
  one("/results", () => db.results),
  list("/evidence", () => db.evidence, { implementation_id: eq("implementation_ref"), result_id: eq("result_ref"), method: eq("method") }),
  one("/evidence", () => db.evidence),
  list("/exceptions", () => db.exceptions, { implementation_id: eq("implementation_ref") }),
  one("/exceptions", () => db.exceptions),
  list("/findings", () => db.findings, { system_id: eq("system_ref"), determination: eq("determination") }),
  one("/findings", () => db.findings),
  list("/risks", () => db.risks, { system_id: eq("system_ref"), status: eq("status"), treatment: eq("treatment"), control_id: (r, v) => r.control_refs?.includes(v) ?? false }),
  one("/risks", () => db.risks),
  list("/policies", () => db.policies, { status: eq("status"), q }),
  one("/policies", () => db.policies),
  list("/procedures", () => db.procedures, { status: eq("status"), policy_id: eq("policy_ref"), q }),
  one("/procedures", () => db.procedures),

  http.get(`${V}/library`, () => HttpResponse.json(db.libraryPin)),
  http.post(`${V}/library/pull`, async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as { version?: string; commit?: string };
    if (!body.version && !body.commit) return problem(400, "bad-request", "Provide version or commit.");
    const job: Job = { id: `job--${crypto.randomUUID()}`, type: "library_pull", status: "queued", created: new Date().toISOString() };
    db.jobs.unshift(job);
    return HttpResponse.json(job, { status: 202 });
  }),

  http.get(`${V}/providers`, () => HttpResponse.json({ data: db.providers })),
  http.get(`${V}/providers/:id`, ({ params }) => {
    const item = db.providers.find((p) => p.id === params.id);
    return item ? HttpResponse.json(item) : notFound();
  }),

  http.post(`${V}/programs/:id/renders`, async ({ params, request }) => {
    if (!db.programs.some((p) => p.id === params.id)) return notFound();
    const body = (await request.json().catch(() => ({}))) as { view?: string; framework_id?: string };
    if (body.view !== "oscal" && body.view !== "ssp") return problem(400, "bad-request", "view must be oscal or ssp.");
    if (body.view === "oscal" && !body.framework_id) return problem(400, "bad-request", "framework_id is required for oscal.");
    const job: Job = { id: `job--${crypto.randomUUID()}`, type: "render", status: "queued", created: new Date().toISOString() };
    db.jobs.unshift(job);
    return HttpResponse.json(job, { status: 202 });
  }),

  http.post(`${V}/exports/git`, () => {
    const job: Job = { id: `job--${crypto.randomUUID()}`, type: "git_export", status: "queued", created: new Date().toISOString() };
    db.jobs.unshift(job);
    return HttpResponse.json(job, { status: 202 });
  }),

  // Integrations (RFC 0005)
  http.get(`${V}/integrations`, () => HttpResponse.json({ data: db.integrations })),
  http.get(`${V}/integrations/:id`, ({ params }) => {
    const item = db.integrations.find((i) => i.id === params.id);
    return item ? HttpResponse.json(item) : notFound();
  }),
  http.post(`${V}/integrations`, async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as { url?: string };
    if (!body.url?.trim()) return problem(400, "bad-request", "url is required.");
    const job: Job = { id: `job--${crypto.randomUUID()}`, type: "integration_install", status: "queued", created: new Date().toISOString() };
    db.jobs.unshift(job);
    return HttpResponse.json(job, { status: 202 });
  }),
  http.get(`${V}/integrations/:id/versions`, ({ params }) => {
    if (!db.integrations.some((i) => i.id === params.id)) return notFound();
    return HttpResponse.json({ data: db.integrationVersions.filter((v) => v.id === params.id) });
  }),
  http.post(`${V}/integrations/:id/versions/:version/enable`, ({ params }) => {
    const integration = db.integrations.find((i) => i.id === params.id);
    if (!integration || !db.integrationVersions.some((v) => v.id === params.id && v.version === params.version)) {
      return notFound();
    }
    db.integrationVersions = db.integrationVersions.map((v) =>
      v.id === params.id ? { ...v, enabled: v.version === params.version } : v,
    );
    integration.version = params.version as string;
    return HttpResponse.json(integration);
  }),
  http.get(`${V}/integrations/:id/template-updates`, ({ params }) => {
    if (!db.integrations.some((i) => i.id === params.id)) return notFound();
    const updates = db.templateUpdates.filter((u) => u.integration_id === params.id);
    return HttpResponse.json({
      data: updates.map((u) => {
        const copy: Partial<typeof u> = { ...u };
        delete copy.integration_id;
        return copy;
      }),
    });
  }),
  http.post(`${V}/integrations/:id/template-updates/:testId/apply`, ({ params, request }) => {
    const idx = db.templateUpdates.findIndex((u) => u.integration_id === params.id && u.test_id === params.testId);
    if (idx < 0) return notFound();
    if (request.headers.get("If-Match") !== db.templateUpdates[idx].modified) {
      return problem(412, "stale-write", "If-Match does not equal modified.");
    }
    db.templateUpdates.splice(idx, 1);
    const test = db.tests.find((t) => t.id === params.testId);
    return test ? HttpResponse.json({ ...test, modified: new Date().toISOString() }) : notFound();
  }),
  http.post(`${V}/integrations/:id/templates/:name/enable`, ({ params }) => {
    const integration = db.integrations.find((i) => i.id === params.id);
    const template = integration?.templates.find((t) => t.name === params.name);
    if (!integration || !template) return notFound();
    const now = new Date().toISOString();
    const test: Test = {
      type: "test",
      id: `test--${crypto.randomUUID()}`,
      spec_version: "0.1.0",
      created: now,
      modified: now,
      name: template.test_name ?? template.name,
      control_ref: template.control_ref ?? "",
      method: "automated",
      interval: "daily",
      fulfills_ref: template.fulfills_ref,
      run: { runner: template.runner ?? "rule" },
      extensions: { "dev.ogrl.integration": { integration: integration.id, version: integration.version, template: template.name } },
    };
    db.tests.unshift(test);
    return HttpResponse.json(test, { status: 201 });
  }),
  http.get(`${V}/connections`, () => HttpResponse.json({ data: [...db.connections].sort((a, b) => a.id.localeCompare(b.id)) })),
  http.get(`${V}/connections/:id`, ({ params }) => {
    const item = db.connections.find((c) => c.id === params.id);
    return item ? HttpResponse.json(item) : notFound();
  }),
  http.post(`${V}/connections`, async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as Partial<Connection>;
    const integration = db.integrations.find((i) => i.id === body.integration_id);
    if (!integration) return problem(400, "bad-request", "integration_id must name an installed integration.");
    if (!body.name?.trim()) return problem(400, "bad-request", "name is required.");
    const now = new Date().toISOString();
    const connection: Connection = {
      id: body.id || `connection--${crypto.randomUUID()}`,
      integration_id: integration.id,
      name: body.name.trim(),
      config: body.config ?? {},
      auth_kind: body.auth_kind ?? "fields",
      bindings: body.bindings ?? [],
      state: "pending",
      secrets_set: [],
      ...(body.auth_kind === "aws_role" ? { external_id: `ext-${crypto.randomUUID().replaceAll("-", "")}` } : {}),
      created: now,
      modified: now,
    };
    db.connections.push(connection);
    return HttpResponse.json(connection, { status: 201 });
  }),
  http.patch(`${V}/connections/:id`, async ({ params, request }) => {
    const idx = db.connections.findIndex((c) => c.id === params.id);
    if (idx < 0) return notFound();
    if (request.headers.get("If-Match") !== db.connections[idx].modified) {
      return problem(412, "stale-write", "If-Match does not equal modified.");
    }
    const body = (await request.json().catch(() => ({}))) as Partial<Connection>;
    const updated = { ...db.connections[idx], ...body, modified: new Date().toISOString() };
    db.connections[idx] = updated;
    return HttpResponse.json(updated);
  }),
  http.delete(`${V}/connections/:id`, ({ params }) => {
    const idx = db.connections.findIndex((c) => c.id === params.id);
    if (idx < 0) return notFound();
    db.connections.splice(idx, 1);
    return new HttpResponse(null, { status: 204 });
  }),
  http.put(`${V}/connections/:id/secrets/:name`, ({ params }) => {
    const idx = db.connections.findIndex((c) => c.id === params.id);
    if (idx < 0) return notFound();
    const name = params.name as string;
    const current = db.connections[idx];
    const updated: Connection = {
      ...current,
      secrets_set: Array.from(new Set([...current.secrets_set, name])).sort(),
      state: "pending",
      identity: undefined,
      modified: new Date().toISOString(),
    };
    db.connections[idx] = updated;
    return HttpResponse.json(updated);
  }),
  http.post(`${V}/connections/:id/oauth/start`, ({ params }) => {
    const connection = db.connections.find((c) => c.id === params.id);
    if (!connection) return notFound();
    if (connection.auth_kind !== "oauth2") return problem(400, "bad-request", `${connection.id} does not use oauth2`);
    if (!connection.secrets_set.includes("OAUTH_CLIENT_ID")) {
      return problem(400, "bad-request", "set OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET first");
    }
    const domain = connection.config.domain ?? "vendor.example";
    const query = new URLSearchParams({ response_type: "code", state: crypto.randomUUID(), code_challenge_method: "S256" });
    return HttpResponse.json({
      authorize_url: `https://${domain}/oauth2/v1/authorize?${query}`,
      expires: new Date(Date.now() + 10 * 60_000).toISOString(),
    });
  }),
  http.post(`${V}/connections/:id/validate`, ({ params }) => {
    if (!db.connections.some((c) => c.id === params.id)) return notFound();
    const job: Job = { id: `job--${crypto.randomUUID()}`, type: "collection", status: "queued", created: new Date().toISOString() };
    db.jobs.unshift(job);
    return HttpResponse.json(job, { status: 202 });
  }),
  http.post(`${V}/connections/:id/collections`, ({ params }) => {
    const connection = db.connections.find((c) => c.id === params.id);
    if (!connection) return notFound();
    if (connection.state === "disabled") return problem(400, "bad-request", `${connection.id} is disabled`);
    const job: Job = { id: `job--${crypto.randomUUID()}`, type: "collection", status: "queued", created: new Date().toISOString() };
    db.jobs.unshift(job);
    return HttpResponse.json(job, { status: 202 });
  }),
  http.post(`${V}/rules/preview`, async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as {
      run?: Record<string, unknown>;
      params?: Record<string, string>;
    };
    const run = body.run ?? {};
    const source = String(run.source ?? "");
    const resource = db.integrations.flatMap((i) => i.resources).find((r) => r.source === source);
    const empty = { selected: 0, total: 0, subjects: [], warnings: [], snapshots: [], params: body.params ?? {}, sample: [] };
    if (!resource) {
      return HttpResponse.json({
        ...empty,
        outcome: "invalid",
        summary: `no installed integration emits ${source || "that source"}`,
        errors: [{ pointer: "/run/source", detail: `no installed integration emits ${source || "that source"}` }],
      });
    }
    if (!run.assert && !run.aggregate) {
      return HttpResponse.json({
        ...empty,
        outcome: "invalid",
        summary: "the rule does not compile",
        errors: [{ pointer: "/run/assert", detail: "runner rule requires assert, aggregate, or both" }],
      });
    }
    const known = new Set(resource.fields.map((f) => f.name));
    const warnings = (["select", "assert", "aggregate"] as const).flatMap((field) =>
      [...String(run[field] ?? "").matchAll(/\bitem\.([A-Za-z_]\w*)/g)]
        .filter((m) => !known.has(m[1]))
        .map((m) => ({ pointer: `/run/${field}`, detail: `item.${m[1]}: the resource has no field '${m[1]}'` })),
    );
    const items = snapshotItems[source];
    if (!items) {
      return HttpResponse.json({
        ...empty,
        warnings,
        errors: [],
        outcome: "no-data",
        summary: `no complete snapshot of ${source} from a connection for it; collect one first`,
      });
    }
    const variables = { params: body.params ?? {} };
    const errors: { pointer: string; detail: string }[] = [];
    for (const field of ["select", "assert"] as const) {
      const text = run[field];
      if (typeof text !== "string" || !text.trim()) continue;
      try {
        evaluateCel(text, { ...variables, item: items[0] });
      } catch (exc) {
        if (exc instanceof CelError && exc.message.startsWith("Syntax")) errors.push({ pointer: `/run/${field}`, detail: exc.message });
      }
    }
    if (errors.length) {
      return HttpResponse.json({ ...empty, warnings, errors, outcome: "invalid", summary: "the rule does not compile" });
    }
    const snapshot = db.snapshots.find((x) => x.source === source);
    const connection = db.connections.find((x) => x.id === snapshot?.connection_id);
    const base = {
      ...empty,
      warnings,
      errors: [],
      total: items.length,
      sample: items.slice(0, 3),
      snapshots: snapshot
        ? [{ id: snapshot.id, connection_id: snapshot.connection_id, connection_name: connection?.name ?? snapshot.connection_id, collected: snapshot.collected, item_count: items.length }]
        : [],
    };
    if (run.aggregate) {
      return HttpResponse.json({ ...base, outcome: "error", summary: "mock mode evaluates select and assert only" });
    }
    try {
      const selected = items.filter((item) => !run.select || evaluateCel(String(run.select), { ...variables, item }) === true);
      if (!selected.length && !run.allow_empty) {
        return HttpResponse.json({ ...base, outcome: "error", summary: `no items selected from ${source}` });
      }
      const failing = selected.filter((item) => evaluateCel(String(run.assert), { ...variables, item }) !== true);
      return HttpResponse.json({
        ...base,
        outcome: failing.length ? "fail" : "pass",
        summary: `${selected.length - failing.length} of ${selected.length} selected items pass`,
        selected: selected.length,
        subjects: failing.map((item) => ({ kind: resource.name, name: String(item.name ?? item.id), external_id: String(item.id) })),
      });
    } catch (exc) {
      return HttpResponse.json({ ...base, outcome: "error", summary: exc instanceof Error ? exc.message : String(exc) });
    }
  }),
  http.get(`${V}/snapshots`, ({ request }) => {
    const sp = new URL(request.url).searchParams;
    const out = db.snapshots
      .filter((s) => !sp.get("connection_id") || s.connection_id === sp.get("connection_id"))
      .filter((s) => !sp.get("source") || s.source === sp.get("source"))
      .sort((a, b) => b.collected.localeCompare(a.collected));
    return HttpResponse.json({ data: out });
  }),
  http.get(`${V}/snapshots/:id`, ({ params }) => {
    const item = db.snapshots.find((s) => s.id === params.id);
    return item ? HttpResponse.json(item) : notFound();
  }),

  list("/jobs", () => db.jobs, { type: eq("type"), status: eq("status") }),
  one("/jobs", () => db.jobs),

  // Write handlers (POST, PATCH, revoke, content upload) for full CRUD in mock mode
  ...crud("/controls", "control", () => db.controls as unknown as MutableObj[], { origin: "custom" }),
  ...crud("/baselines", "baseline", () => db.baselines as unknown as MutableObj[]),
  ...crud("/tests", "test", () => db.tests as unknown as MutableObj[]),
  ...crud("/parties", "party", () => db.parties as unknown as MutableObj[]),
  ...crud("/components", "component", () => db.components as unknown as MutableObj[]),
  ...crud("/systems", "system", () => db.systems as unknown as MutableObj[]),
  ...crud("/programs", "program", () => db.programs as unknown as MutableObj[]),
  ...crud("/implementations", "implementation", () => db.implementations as unknown as MutableObj[], { origin: "organization" }),
  ...crud("/results", "result", () => db.results as unknown as MutableObj[]),
  ...crud("/evidence", "evidence", () => db.evidence as unknown as MutableObj[]),
  ...crud("/exceptions", "exception", () => db.exceptions as unknown as MutableObj[]),
  ...crud("/findings", "finding", () => db.findings as unknown as MutableObj[]),
  ...crud("/risks", "risk", () => db.risks as unknown as MutableObj[]),
  ...crud("/policies", "policy", () => db.policies as unknown as MutableObj[]),
  ...crud("/procedures", "procedure", () => db.procedures as unknown as MutableObj[]),
  contentUpload("/evidence", () => db.evidence as unknown as MutableObj[]),
  contentUpload("/policies", () => db.policies as unknown as MutableObj[]),
  contentUpload("/procedures", () => db.procedures as unknown as MutableObj[]),
];
