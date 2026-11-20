import { http, HttpResponse, type HttpResponseResolver } from "msw";

import type { Job } from "@/lib/api/types";

import { db } from "./db";
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
  list("/jobs", () => db.jobs, { type: eq("type"), status: eq("status") }),
  one("/jobs", () => db.jobs),
];
