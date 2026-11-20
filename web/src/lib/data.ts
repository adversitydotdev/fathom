import "server-only";

import { cache } from "react";

import { api, unwrap } from "./api/client";
import type { Party } from "./api/types";

type Paged<T> = { data: T[]; page: { next_cursor?: string } };

/** Follows `next_cursor` until the last page (RFC 0004 section 3). */
async function all<T>(fetchPage: (cursor?: string) => Promise<Paged<T>>): Promise<T[]> {
  const out: T[] = [];
  let cursor: string | undefined;
  do {
    const page = await fetchPage(cursor);
    out.push(...page.data);
    cursor = page.page.next_cursor;
  } while (cursor);
  return out;
}

/** `?at=YYYY-MM-DD` on the URL becomes an RFC 3339 instant for the API. */
export function evaluationInstant(at: string | undefined): string | undefined {
  return at && /^\d{4}-\d{2}-\d{2}$/.test(at) ? `${at}T23:59:59Z` : undefined;
}

export const getPrograms = cache(() =>
  all((cursor) => unwrap(api.GET("/programs", { params: { query: { cursor, limit: 200 } } }))),
);

export const getProgram = cache((id: string) =>
  unwrap(api.GET("/programs/{id}", { params: { path: { id } } })),
);

export const getSystem = cache((id: string) =>
  unwrap(api.GET("/systems/{id}", { params: { path: { id } } })),
);

export const getBaseline = cache((id: string) =>
  unwrap(api.GET("/baselines/{id}", { params: { path: { id } } })),
);

export const getBaselines = cache(() =>
  all((cursor) => unwrap(api.GET("/baselines", { params: { query: { cursor, limit: 200 } } }))),
);

export const getProgramSummary = cache((id: string, at?: string) =>
  unwrap(api.GET("/programs/{id}/summary", { params: { path: { id }, query: { at } } })),
);

export const getProgramStatus = cache((id: string, at?: string, framework_id?: string) =>
  unwrap(api.GET("/programs/{id}/status", { params: { path: { id }, query: { at, framework_id } } })),
);

export const getSystemGaps = cache((id: string, at?: string) =>
  unwrap(api.GET("/systems/{id}/gaps", { params: { path: { id }, query: { at } } })),
);

export const getFrameworks = cache(() =>
  all((cursor) => unwrap(api.GET("/frameworks", { params: { query: { cursor, limit: 200 } } }))),
);

export const getControls = cache(() =>
  all((cursor) => unwrap(api.GET("/controls", { params: { query: { cursor, limit: 200 } } }))),
);

export const getControl = cache((id: string) =>
  unwrap(api.GET("/controls/{id}", { params: { path: { id } } })),
);

export const getControlMappings = cache((id: string) =>
  all((cursor) => unwrap(api.GET("/controls/{id}/mappings", { params: { path: { id }, query: { cursor } } }))),
);

export const getControlTests = cache((id: string) =>
  all((cursor) => unwrap(api.GET("/controls/{id}/tests", { params: { path: { id }, query: { cursor } } }))),
);

export const getControlImplementations = cache((id: string) =>
  all((cursor) =>
    unwrap(api.GET("/controls/{id}/implementations", { params: { path: { id }, query: { cursor } } })),
  ),
);

export const getImplementations = cache((systemId: string) =>
  all((cursor) =>
    unwrap(api.GET("/implementations", { params: { query: { system_id: systemId, cursor, limit: 200 } } })),
  ),
);

export const getImplementationResults = cache((id: string) =>
  all((cursor) => unwrap(api.GET("/implementations/{id}/results", { params: { path: { id }, query: { cursor } } }))),
);

export const getImplementationEvidence = cache((id: string) =>
  all((cursor) => unwrap(api.GET("/implementations/{id}/evidence", { params: { path: { id }, query: { cursor } } }))),
);

export const getRequirements = cache((frameworkId?: string) =>
  all((cursor) =>
    unwrap(api.GET("/requirements", { params: { query: { framework_id: frameworkId, cursor, limit: 200 } } })),
  ),
);

export const getExceptions = cache((implementationId: string) =>
  all((cursor) =>
    unwrap(api.GET("/exceptions", { params: { query: { implementation_id: implementationId, cursor } } })),
  ),
);

export const getJobs = cache(() => unwrap(api.GET("/jobs", { params: { query: { limit: 5 } } })));

export const getAllJobs = cache(() =>
  all((cursor) => unwrap(api.GET("/jobs", { params: { query: { cursor, limit: 200 } } }))),
);

export const getMappings = cache(() =>
  all((cursor) => unwrap(api.GET("/mappings", { params: { query: { cursor, limit: 200 } } }))),
);

export const getTests = cache(() =>
  all((cursor) => unwrap(api.GET("/tests", { params: { query: { cursor, limit: 200 } } }))),
);

export const getResults = cache(() =>
  all((cursor) => unwrap(api.GET("/results", { params: { query: { cursor, limit: 200 } } }))),
);

export const getEvidence = cache(() =>
  all((cursor) => unwrap(api.GET("/evidence", { params: { query: { cursor, limit: 200 } } }))),
);

export const getAllExceptions = cache(() =>
  all((cursor) => unwrap(api.GET("/exceptions", { params: { query: { cursor, limit: 200 } } }))),
);

export const getFindings = cache((systemId?: string) =>
  all((cursor) =>
    unwrap(api.GET("/findings", { params: { query: { system_id: systemId, cursor, limit: 200 } } })),
  ),
);

export const getRisks = cache((systemId?: string) =>
  all((cursor) =>
    unwrap(api.GET("/risks", { params: { query: { system_id: systemId, cursor, limit: 200 } } })),
  ),
);

export const getPolicies = cache(() =>
  all((cursor) => unwrap(api.GET("/policies", { params: { query: { cursor, limit: 200 } } }))),
);

export const getProcedures = cache(() =>
  all((cursor) => unwrap(api.GET("/procedures", { params: { query: { cursor, limit: 200 } } }))),
);

export const getSystems = cache(() =>
  all((cursor) => unwrap(api.GET("/systems", { params: { query: { cursor, limit: 200 } } }))),
);

export const getComponents = cache(() =>
  all((cursor) => unwrap(api.GET("/components", { params: { query: { cursor, limit: 200 } } }))),
);

export const getLibraryPin = cache(() => unwrap(api.GET("/library")));

export const getProviders = cache(() => unwrap(api.GET("/providers")));

export const getParties = cache(async () => {
  const parties = await all((cursor) => unwrap(api.GET("/parties", { params: { query: { cursor, limit: 200 } } })));
  return new Map<string, Party>(parties.map((p) => [p.id, p]));
});
