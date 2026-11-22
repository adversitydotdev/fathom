/**
 * Mock-mode stand-in for the server's query source checks (RFC 0006 section 6, RFC 0007).
 *
 * The real server validates with the integration SDK against the bundled API model.
 * This covers the subset the UI and the e2e suite exercise: the operation, regions,
 * parameters, `id`/`name`, field paths with a close-match hint, and the derived schema.
 */
import type { Integration, Operation, QueryCheck, QueryDefinition, QueryWrite, ResourceField } from "@/lib/api/types";

import { db } from "./db";
import { apiOperations, queryModels, type MockOperation } from "./fixtures/queries";

type Problem = { pointer: string; detail: string };

const FIELD_NAME = /^[a-z][a-z0-9_]*$/;
const QUERY_NAME = /^[a-z0-9-]+$/;

function distance(a: string, b: string): number {
  const row = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    let prev = row[0];
    row[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const next = row[j];
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
      prev = next;
    }
  }
  return row[b.length];
}

function closest(value: string, known: string[]): string | undefined {
  const ranked = known.map((k) => [distance(value.toLowerCase(), k.toLowerCase()), k] as const).sort((x, y) => x[0] - y[0]);
  return ranked[0] && ranked[0][0] <= Math.max(2, Math.floor(value.length / 3)) ? ranked[0][1] : undefined;
}

/** Mirrors the server's `schema_fields`: what a rule can read after `item.`. */
export function schemaFields(schema: Record<string, unknown>): ResourceField[] {
  const required = new Set((schema.required as string[] | undefined) ?? []);
  const properties = (schema.properties as Record<string, { type?: string | string[]; description?: string }>) ?? {};
  return Object.entries(properties).map(([name, spec]) => {
    const kinds = Array.isArray(spec.type) ? spec.type : [spec.type ?? "any"];
    return {
      name,
      type: kinds.filter((k) => k !== "null").join(" or ") || "null",
      nullable: kinds.includes("null"),
      required: required.has(name),
      ...(spec.description ? { description: spec.description } : {}),
    };
  });
}

/** An integration as the API returns it: with its query model and saved query sources. */
export function withQueries(integration: Integration): Integration {
  const model = queryModels[integration.id];
  return {
    ...integration,
    ...(model ? { query_model: model } : {}),
    queries: db.queries
      .filter((q) => q.integration_id === integration.id)
      .map((q) => ({
        id: q.id,
        name: q.name,
        version: q.version,
        source: sourceOf(q),
        operation: q.operation,
        ...(q.description ? { description: q.description } : {}),
        fields: schemaFields(q.item_schema),
      })),
  };
}

export const sourceOf = (q: { integration_id: string; name: string; version?: number }) =>
  `${q.integration_id}/${q.name}@${q.version ?? 1}`;

export function findOperation(integrationId: string, id: string): MockOperation | undefined {
  return apiOperations[integrationId]?.find((o) => o.id === id);
}

export function searchOperations(integrationId: string, text: string) {
  const words = text.toLowerCase().split(/\s+/).filter(Boolean);
  return (apiOperations[integrationId] ?? [])
    .filter((o) => words.every((w) => `${o.id} ${o.path} ${o.summary}`.toLowerCase().includes(w)))
    .map((o) => without(o, ["sample", "fields", "items"]));
}

/** What describe returns: the operation without the mock's sample items. */
export function describe(op: MockOperation): Operation {
  return without(op, ["sample"]);
}

function without(op: MockOperation, keys: string[]): Operation {
  return Object.fromEntries(Object.entries(op).filter(([k]) => !keys.includes(k))) as Operation;
}

const baseType = (type: string) => (type.startsWith("array") ? "array" : type);

export function checkQuery(write: QueryWrite): QueryCheck {
  const source = sourceOf(write);
  const errors: Problem[] = [];
  const done = (schema?: Record<string, unknown>): QueryCheck => ({
    valid: errors.length === 0,
    source,
    errors,
    warnings: [],
    ...(schema ? { item_schema: schema } : {}),
    fields: schema ? schemaFields(schema) : [],
  });

  const model = queryModels[write.integration_id];
  if (!model) {
    errors.push({ pointer: "/integration_id", detail: `${write.integration_id} does not support query sources` });
    return done();
  }
  if (!QUERY_NAME.test(write.name)) errors.push({ pointer: "/name", detail: "a name matches [a-z0-9-]+" });
  const op = findOperation(write.integration_id, write.operation);
  if (!op) {
    const hint = closest(write.operation, (apiOperations[write.integration_id] ?? []).map((o) => o.id));
    errors.push({
      pointer: "/operation",
      detail: `no queryable operation '${write.operation}'; ${hint ? `did you mean '${hint}'?` : "search for one"}`,
    });
    return done();
  }

  const regional = Boolean(op.regional);
  if (model === "openapi" && write.regions) {
    errors.push({ pointer: "/regions", detail: "regions apply to AWS (Smithy) query sources only" });
  }
  if (model === "smithy" && regional && !write.regions) {
    errors.push({ pointer: "/regions", detail: `${op.id.split(".")[0]} is regional: list regions, or "*"` });
  }
  if (model === "smithy" && !regional && write.regions) {
    errors.push({ pointer: "/regions", detail: `${op.id.split(".")[0]} is global: leave regions out` });
  }

  const declared = new Map(op.parameters.map((p) => [p.name, p]));
  for (const [key, value] of Object.entries(write.params ?? {})) {
    const param = declared.get(key);
    if (!param) {
      errors.push({ pointer: `/params/${key}`, detail: `${op.id} has no parameter '${key}'` });
    } else if (param.type === "integer" && !/^-?\d+$/.test(value)) {
      errors.push({ pointer: `/params/${key}`, detail: `${key} is an integer` });
    } else if (param.in === "json") {
      try {
        JSON.parse(value);
      } catch {
        errors.push({ pointer: `/params/${key}`, detail: `${key} is JSON text` });
      }
    }
  }
  for (const param of op.parameters) {
    if (param.required && !(param.name in (write.params ?? {}))) {
      errors.push({ pointer: `/params/${param.name}`, detail: `${op.id} needs ${param.name}` });
    }
  }

  const fields = write.fields ?? {};
  if (Object.keys(fields).length === 0) errors.push({ pointer: "/fields", detail: "project at least id and name" });
  for (const required of ["id", "name"]) {
    if (Object.keys(fields).length && !(required in fields)) {
      errors.push({ pointer: `/fields/${required}`, detail: `${required} is required: it names failing items` });
    }
  }
  const paths = new Map((op.fields ?? []).map((x) => [x.path, x.type]));
  const properties: Record<string, { type: string[] }> = {};
  for (const [key, path] of Object.entries(fields)) {
    if (!FIELD_NAME.test(key)) {
      errors.push({ pointer: `/fields/${key}`, detail: "output field names match [a-z][a-z0-9_]*" });
      continue;
    }
    if (path === "$region" && regional) {
      properties[key] = { type: ["string"] };
      continue;
    }
    const type = paths.get(path);
    if (!type) {
      const hint = closest(path, [...paths.keys()]);
      errors.push({ pointer: `/fields/${key}`, detail: `items have no '${path}'${hint ? `; did you mean '${hint}'?` : ""}` });
      continue;
    }
    properties[key] = { type: [baseType(type), "null"] };
  }
  if (regional) properties.region = { type: ["string"] };
  if (db.queries.some((q) => sourceOf(q) === source)) {
    errors.push({ pointer: "/version", detail: `${source} exists; versions are immutable, so save it as a new version` });
  }
  return done({
    type: "object",
    required: [...Object.keys(fields), ...(regional ? ["region"] : [])].sort(),
    properties,
  });
}

function get(item: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((at, part) => (at && typeof at === "object" ? (at as Record<string, unknown>)[part] : undefined), item);
}

export function dryRun(write: QueryWrite, connectionId: string, maxItems: number) {
  const check = checkQuery(write);
  const blocking = check.errors.filter((e) => e.pointer !== "/version");
  if (blocking.length || !check.item_schema) {
    return { check, items: [], count: 0, warnings: [], error: "fix the definition first" };
  }
  const connection = db.connections.find((c) => c.id === connectionId);
  if (!connection || connection.integration_id !== write.integration_id || connection.state === "disabled") {
    return {
      check,
      items: [],
      count: 0,
      warnings: [],
      error: `${connection?.name ?? connectionId} is not an enabled ${write.integration_id} connection`,
    };
  }
  const op = findOperation(write.integration_id, write.operation)!;
  const regions = op.regional
    ? write.regions === "*"
      ? (connection.config.regions ?? "us-east-1").split(",")
      : (write.regions ?? [])
    : [undefined];
  const items = regions.flatMap((region) =>
    op.sample.map((raw) => ({
      ...Object.fromEntries(
        Object.entries(write.fields ?? {}).map(([key, path]) => [key, path === "$region" ? region : (get(raw, path) ?? null)]),
      ),
      ...(region ? { region } : {}),
    })),
  ).slice(0, maxItems);
  const warnings = Object.keys(write.fields ?? {})
    .filter((key) => items.length > 0 && items.every((i) => (i as Record<string, unknown>)[key] === null))
    .map((key) => ({ pointer: `/fields/${key}`, detail: `${key} is empty in all ${items.length} items; check the path` }));
  return { check, items, count: items.length, warnings };
}

export function saveQuery(write: QueryWrite, by: string): { query?: QueryDefinition; check: QueryCheck } {
  const check = checkQuery(write);
  if (!check.valid || !check.item_schema) return { check };
  const query: QueryDefinition = {
    id: `query--${crypto.randomUUID()}`,
    integration_id: write.integration_id,
    name: write.name,
    version: write.version ?? 1,
    ...(write.description ? { description: write.description } : {}),
    operation: write.operation,
    params: write.params ?? {},
    items: write.items ?? "",
    fields: write.fields ?? {},
    ...(write.regions ? { regions: write.regions } : {}),
    ...(write.for_each ? { for_each: write.for_each } : {}),
    item_schema: check.item_schema,
    created: new Date().toISOString(),
    created_by_ref: by,
  };
  db.queries.push(query);
  return { query, check };
}
