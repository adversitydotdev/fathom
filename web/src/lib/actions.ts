"use server";

import { revalidatePath } from "next/cache";

import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { apiMocking, apiOrigin, apiToken } from "@/lib/env";

type S = components["schemas"];

export type ActionState = { jobId?: string; id?: string; error?: string };

function formatError(error: unknown, fallback: string): string {
  if (!error || typeof error !== "object") return fallback;
  const p = error as {
    title?: string;
    detail?: string;
    errors?: Array<{ detail?: string; pointer?: string }>;
  };
  const fieldMsgs = p.errors?.map((e) => (e.pointer ? `${e.pointer}: ${e.detail}` : e.detail)).filter(Boolean);
  if (fieldMsgs && fieldMsgs.length > 0) return fieldMsgs.join("; ");
  return p.detail ?? p.title ?? fallback;
}

function refresh() {
  revalidatePath("/", "layout");
}

async function uploadMultipart(path: string, ifMatch: string, file: File | { name: string; content: string; type: string }): Promise<{ modified?: string; error?: string }> {
  const form = new FormData();
  if (file instanceof File) {
    form.append("file", file, file.name);
  } else {
    form.append("file", new Blob([file.content], { type: file.type }), file.name);
  }

  const headers: Record<string, string> = {
    Accept: "application/json",
    "If-Match": ifMatch,
  };
  if (!apiMocking && apiToken) {
    headers.Authorization = `Bearer ${apiToken}`;
  }

  let res: Response;
  if (apiMocking) {
    const { handleMockRequest } = await import("@/mocks/dispatch");
    res = await handleMockRequest(
      new Request(`http://ogrl.mock/v1${path}`, { method: "POST", headers, body: form }),
    );
  } else {
    res = await fetch(`${apiOrigin}/v1${path}`, { method: "POST", headers, body: form });
  }

  const body = await res.json().catch(() => undefined);
  if (!res.ok) {
    return { error: formatError(body, `Upload failed (HTTP ${res.status}).`) };
  }
  return { modified: (body as { modified?: string } | undefined)?.modified };
}

// Jobs / Renders / Library -------------------------------------------------

export async function triggerRender(
  programId: string,
  view: "oscal" | "ssp",
  frameworkId?: string,
): Promise<ActionState> {
  const { data, error } = await api.POST("/programs/{id}/renders", {
    params: { path: { id: programId } },
    body: { view, ...(frameworkId ? { framework_id: frameworkId } : {}) },
  });
  if (error || !data) return { error: formatError(error, "Couldn't queue render.") };
  refresh();
  return { jobId: data.id };
}

export async function triggerGitExport(): Promise<ActionState> {
  const { data, error, response } = await api.POST("/exports/git");
  if (response.status === 404) {
    return { error: "Git export is disabled (set OGRL_EXPORT_REMOTE to enable)." };
  }
  if (error || !data) return { error: formatError(error, "Couldn't queue Git export.") };
  refresh();
  return { jobId: data.id };
}

export async function triggerLibraryPull(version: string): Promise<ActionState> {
  const { data, error } = await api.POST("/library/pull", { body: { version } });
  if (error || !data) return { error: formatError(error, "Couldn't queue library pull.") };
  refresh();
  return { jobId: data.id };
}

// Integrations (RFC 0005) --------------------------------------------------

export async function createConnection(
  body: S["ConnectionWrite"],
  secrets: Record<string, string>,
): Promise<ActionState> {
  const { data, error } = await api.POST("/connections", { body });
  if (error || !data) return { error: formatError(error, "Couldn't create connection.") };
  for (const [name, value] of Object.entries(secrets)) {
    if (!value) continue;
    const res = await api.PUT("/connections/{id}/secrets/{name}", {
      params: { path: { id: data.id, name } },
      body: { value },
    });
    if (res.error) {
      refresh();
      return { id: data.id, error: formatError(res.error, `Couldn't store ${name}.`) };
    }
  }
  refresh();
  return { id: data.id };
}

export async function setConnectionState(
  id: string,
  ifMatch: string,
  state: "disabled" | "pending",
): Promise<ActionState> {
  const { data, error } = await api.PATCH("/connections/{id}", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
    body: { state },
  });
  if (error || !data) return { error: formatError(error, "Couldn't update connection.") };
  refresh();
  return { id: data.id };
}

export async function deleteConnection(id: string): Promise<ActionState> {
  const { error, response } = await api.DELETE("/connections/{id}", { params: { path: { id } } });
  if (error || !response.ok) return { error: formatError(error, "Couldn't remove connection.") };
  refresh();
  return { id };
}

export async function validateConnection(id: string): Promise<ActionState> {
  const { data, error } = await api.POST("/connections/{id}/validate", { params: { path: { id } } });
  if (error || !data) return { error: formatError(error, "Couldn't queue validation.") };
  refresh();
  return { jobId: data.id };
}

export async function collectConnection(id: string): Promise<ActionState> {
  const { data, error } = await api.POST("/connections/{id}/collections", {
    params: { path: { id } },
    body: {},
  });
  if (error || !data) return { error: formatError(error, "Couldn't queue collection.") };
  refresh();
  return { jobId: data.id };
}

export async function startOAuth(id: string): Promise<{ url?: string; error?: string }> {
  const { data, error } = await api.POST("/connections/{id}/oauth/start", { params: { path: { id } } });
  if (error || !data) return { error: formatError(error, "Couldn't start authorization.") };
  return { url: data.authorize_url };
}

export async function installIntegration(url: string, digest?: string): Promise<ActionState> {
  const { data, error } = await api.POST("/integrations", {
    body: { url, ...(digest ? { digest } : {}), enable: true },
  });
  if (error || !data) return { error: formatError(error, "Couldn't queue install.") };
  refresh();
  return { jobId: data.id };
}

export async function enableIntegrationVersion(id: string, version: string): Promise<ActionState> {
  const { data, error } = await api.POST("/integrations/{id}/versions/{version}/enable", {
    params: { path: { id, version } },
  });
  if (error || !data) return { error: formatError(error, "Couldn't enable that version.") };
  refresh();
  return { id: data.id };
}

export async function applyTemplateUpdate(id: string, testId: string, ifMatch: string): Promise<ActionState> {
  const { data, error } = await api.POST("/integrations/{id}/template-updates/{test_id}/apply", {
    params: { path: { id, test_id: testId }, header: { "If-Match": ifMatch } },
  });
  if (error || !data) return { error: formatError(error, "Couldn't apply the update.") };
  refresh();
  return { id: data.id };
}

export type RulePreview = S["RulePreview"];

export async function previewRule(body: S["RulePreviewRequest"]): Promise<{ preview?: RulePreview; error?: string }> {
  const { data, error } = await api.POST("/rules/preview", { body });
  if (error || !data) return { error: formatError(error, "Couldn't preview the rule.") };
  return { preview: data };
}

export async function createRuleTest(body: S["TestWrite"]): Promise<ActionState> {
  const { data, error } = await api.POST("/tests", { body });
  if (error || !data) return { error: formatError(error, "Couldn't create the test.") };
  refresh();
  return { id: data.id };
}

export async function enableTemplate(integrationId: string, name: string): Promise<ActionState> {
  const { data, error } = await api.POST("/integrations/{id}/templates/{name}/enable", {
    params: { path: { id: integrationId, name } },
    body: {},
  });
  if (error || !data) return { error: formatError(error, "Couldn't enable template.") };
  refresh();
  return { id: data.id };
}

// Query sources (RFC 0006, 0007) ------------------------------------------

export async function searchOperations(
  integrationId: string,
  q: string,
): Promise<{ operations?: S["Operation"][]; error?: string }> {
  const { data, error } = await api.GET("/integrations/{id}/operations", {
    params: { path: { id: integrationId }, query: { q } },
  });
  if (error || !data) return { error: formatError(error, "Couldn't search operations.") };
  return { operations: data.data };
}

export async function describeOperation(
  integrationId: string,
  operation: string,
): Promise<{ operation?: S["Operation"]; error?: string }> {
  const { data, error } = await api.GET("/integrations/{id}/operations/{operation}", {
    params: { path: { id: integrationId, operation } },
  });
  if (error || !data) return { error: formatError(error, "Couldn't describe the operation.") };
  return { operation: data };
}

export async function validateQuery(body: S["QueryWrite"]): Promise<{ check?: S["QueryCheck"]; error?: string }> {
  const { data, error } = await api.POST("/queries/validate", { body });
  if (error || !data) return { error: formatError(error, "Couldn't validate the query.") };
  return { check: data };
}

export async function dryRunQuery(body: S["DryRunRequest"]): Promise<{ run?: S["DryRun"]; error?: string }> {
  const { data, error } = await api.POST("/queries/dry-run", { body });
  if (error || !data) return { error: formatError(error, "Couldn't run the query.") };
  return { run: data };
}

export async function createQuery(body: S["QueryWrite"]): Promise<ActionState> {
  const { data, error } = await api.POST("/queries", { body });
  if (error || !data) return { error: formatError(error, "Couldn't save the query source.") };
  refresh();
  return { id: data.id };
}

export async function deleteQuery(id: string): Promise<ActionState> {
  const { error } = await api.DELETE("/queries/{id}", { params: { path: { id } } });
  if (error) return { error: formatError(error, "Couldn't remove the query source.") };
  refresh();
  return {};
}

// Controls -----------------------------------------------------------------

export async function createControl(body: S["ControlWrite"]): Promise<ActionState> {
  const { data, error } = await api.POST("/controls", { body });
  if (error || !data) return { error: formatError(error, "Couldn't create control.") };
  refresh();
  return { id: data.id };
}

export async function updateControl(id: string, ifMatch: string, body: Partial<S["ControlWrite"]>): Promise<ActionState> {
  const { data, error } = await api.PATCH("/controls/{id}", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
    body: body as S["ControlWrite"],
  });
  if (error || !data) return { error: formatError(error, "Couldn't update control.") };
  refresh();
  return { id: data.id };
}

export async function revokeControl(id: string, ifMatch: string): Promise<ActionState> {
  const { error } = await api.POST("/controls/{id}/revoke", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
  });
  if (error) return { error: formatError(error, "Couldn't revoke control.") };
  refresh();
  return { id };
}

// Implementations ----------------------------------------------------------

export async function createImplementation(body: S["ImplementationWrite"]): Promise<ActionState> {
  const { data, error } = await api.POST("/implementations", { body });
  if (error || !data) return { error: formatError(error, "Couldn't create implementation.") };
  refresh();
  return { id: data.id };
}

export async function updateImplementation(
  id: string,
  ifMatch: string,
  body: Partial<S["ImplementationWrite"]>,
): Promise<ActionState> {
  const { data, error } = await api.PATCH("/implementations/{id}", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
    body: body as S["ImplementationWrite"],
  });
  if (error || !data) return { error: formatError(error, "Couldn't update implementation.") };
  refresh();
  return { id: data.id };
}

export async function revokeImplementation(id: string, ifMatch: string): Promise<ActionState> {
  const { error } = await api.POST("/implementations/{id}/revoke", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
  });
  if (error) return { error: formatError(error, "Couldn't revoke implementation.") };
  refresh();
  return { id };
}

// Tests & Manual Results ---------------------------------------------------

export async function createTest(body: S["TestWrite"]): Promise<ActionState> {
  const { data, error } = await api.POST("/tests", { body });
  if (error || !data) return { error: formatError(error, "Couldn't create test.") };
  refresh();
  return { id: data.id };
}

export async function updateTest(id: string, ifMatch: string, body: Partial<S["TestWrite"]>): Promise<ActionState> {
  const { data, error } = await api.PATCH("/tests/{id}", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
    body: body as S["TestWrite"],
  });
  if (error || !data) return { error: formatError(error, "Couldn't update test.") };
  refresh();
  return { id: data.id };
}

export async function revokeTest(id: string, ifMatch: string): Promise<ActionState> {
  const { error } = await api.POST("/tests/{id}/revoke", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
  });
  if (error) return { error: formatError(error, "Couldn't revoke test.") };
  refresh();
  return { id };
}

export async function createResult(body: S["ResultWrite"]): Promise<ActionState> {
  const { data, error } = await api.POST("/results", { body });
  if (error || !data) return { error: formatError(error, "Couldn't record result.") };
  refresh();
  return { id: data.id };
}

// Evidence -----------------------------------------------------------------

export async function createEvidence(body: S["EvidenceWrite"], formData?: FormData): Promise<ActionState> {
  const { data, error } = await api.POST("/evidence", { body });
  if (error || !data) return { error: formatError(error, "Couldn't create evidence.") };

  const file = formData?.get("file");
  if (file instanceof File && file.size > 0) {
    const up = await uploadMultipart(`/evidence/${data.id}/content`, data.modified, file);
    if (up.error) return { error: up.error };
  }
  refresh();
  return { id: data.id };
}

export async function updateEvidence(
  id: string,
  ifMatch: string,
  body: Partial<S["EvidenceWrite"]>,
): Promise<ActionState> {
  const { data, error } = await api.PATCH("/evidence/{id}", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
    body: body as S["EvidenceWrite"],
  });
  if (error || !data) return { error: formatError(error, "Couldn't update evidence.") };
  refresh();
  return { id: data.id };
}

export async function revokeEvidence(id: string, ifMatch: string): Promise<ActionState> {
  const { error } = await api.POST("/evidence/{id}/revoke", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
  });
  if (error) return { error: formatError(error, "Couldn't revoke evidence.") };
  refresh();
  return { id };
}

// Risks --------------------------------------------------------------------

export async function createRisk(body: S["RiskWrite"]): Promise<ActionState> {
  const { data, error } = await api.POST("/risks", { body });
  if (error || !data) return { error: formatError(error, "Couldn't create risk.") };
  refresh();
  return { id: data.id };
}

export async function updateRisk(id: string, ifMatch: string, body: Partial<S["RiskWrite"]>): Promise<ActionState> {
  const { data, error } = await api.PATCH("/risks/{id}", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
    body: body as S["RiskWrite"],
  });
  if (error || !data) return { error: formatError(error, "Couldn't update risk.") };
  refresh();
  return { id: data.id };
}

export async function revokeRisk(id: string, ifMatch: string): Promise<ActionState> {
  const { error } = await api.POST("/risks/{id}/revoke", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
  });
  if (error) return { error: formatError(error, "Couldn't revoke risk.") };
  refresh();
  return { id };
}

// Exceptions ---------------------------------------------------------------

export async function createException(body: S["ExceptionWrite"]): Promise<ActionState> {
  const { data, error } = await api.POST("/exceptions", { body });
  if (error || !data) return { error: formatError(error, "Couldn't create exception.") };
  refresh();
  return { id: data.id };
}

export async function updateException(
  id: string,
  ifMatch: string,
  body: Partial<S["ExceptionWrite"]>,
): Promise<ActionState> {
  const { data, error } = await api.PATCH("/exceptions/{id}", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
    body: body as S["ExceptionWrite"],
  });
  if (error || !data) return { error: formatError(error, "Couldn't update exception.") };
  refresh();
  return { id: data.id };
}

export async function revokeException(id: string, ifMatch: string): Promise<ActionState> {
  const { error } = await api.POST("/exceptions/{id}/revoke", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
  });
  if (error) return { error: formatError(error, "Couldn't revoke exception.") };
  refresh();
  return { id };
}

// Findings -----------------------------------------------------------------

export async function createFinding(body: S["FindingWrite"]): Promise<ActionState> {
  const { data, error } = await api.POST("/findings", { body });
  if (error || !data) return { error: formatError(error, "Couldn't create finding.") };
  refresh();
  return { id: data.id };
}

export async function updateFinding(
  id: string,
  ifMatch: string,
  body: Partial<S["FindingWrite"]>,
): Promise<ActionState> {
  const { data, error } = await api.PATCH("/findings/{id}", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
    body: body as S["FindingWrite"],
  });
  if (error || !data) return { error: formatError(error, "Couldn't update finding.") };
  refresh();
  return { id: data.id };
}

export async function revokeFinding(id: string, ifMatch: string): Promise<ActionState> {
  const { error } = await api.POST("/findings/{id}/revoke", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
  });
  if (error) return { error: formatError(error, "Couldn't revoke finding.") };
  refresh();
  return { id };
}

// Policies & Procedures ----------------------------------------------------

export async function createPolicy(body: S["PolicyWrite"], contentMd?: string): Promise<ActionState> {
  const wantAdopt = body.status === "adopted";
  const { data, error } = await api.POST("/policies", {
    body: { ...body, status: wantAdopt ? "draft" : body.status },
  });
  if (error || !data) return { error: formatError(error, "Couldn't create policy.") };

  let currentModified = data.modified;
  if (contentMd && contentMd.trim()) {
    const up = await uploadMultipart(`/policies/${data.id}/content`, currentModified, {
      name: `${data.id}.md`,
      content: contentMd,
      type: "text/markdown",
    });
    if (up.error) return { error: up.error };
    if (up.modified) currentModified = up.modified;
  }

  if (wantAdopt) {
    const { error: patchErr } = await api.PATCH("/policies/{id}", {
      params: { path: { id: data.id }, header: { "If-Match": currentModified } },
      body: {
        status: "adopted",
        adopted: body.adopted ?? new Date().toISOString().slice(0, 10),
      } as S["PolicyWrite"],
    });
    if (patchErr) return { error: formatError(patchErr, "Policy created as draft, but couldn't adopt.") };
  }

  refresh();
  return { id: data.id };
}

export async function updatePolicy(
  id: string,
  ifMatch: string,
  body: Partial<S["PolicyWrite"]>,
  contentMd?: string,
): Promise<ActionState> {
  let currentModified = ifMatch;
  if (contentMd && contentMd.trim()) {
    const up = await uploadMultipart(`/policies/${id}/content`, currentModified, {
      name: `${id}.md`,
      content: contentMd,
      type: "text/markdown",
    });
    if (up.error) return { error: up.error };
    if (up.modified) currentModified = up.modified;
  }
  const { data, error } = await api.PATCH("/policies/{id}", {
    params: { path: { id }, header: { "If-Match": currentModified } },
    body: body as S["PolicyWrite"],
  });
  if (error || !data) return { error: formatError(error, "Couldn't update policy.") };
  refresh();
  return { id: data.id };
}

export async function revokePolicy(id: string, ifMatch: string): Promise<ActionState> {
  const { error } = await api.POST("/policies/{id}/revoke", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
  });
  if (error) return { error: formatError(error, "Couldn't revoke policy.") };
  refresh();
  return { id };
}

export async function createProcedure(body: S["ProcedureWrite"], contentMd?: string): Promise<ActionState> {
  const wantAdopt = body.status === "adopted";
  const { data, error } = await api.POST("/procedures", {
    body: { ...body, status: wantAdopt ? "draft" : body.status },
  });
  if (error || !data) return { error: formatError(error, "Couldn't create procedure.") };

  let currentModified = data.modified;
  if (contentMd && contentMd.trim()) {
    const up = await uploadMultipart(`/procedures/${data.id}/content`, currentModified, {
      name: `${data.id}.md`,
      content: contentMd,
      type: "text/markdown",
    });
    if (up.error) return { error: up.error };
    if (up.modified) currentModified = up.modified;
  }

  if (wantAdopt) {
    const { error: patchErr } = await api.PATCH("/procedures/{id}", {
      params: { path: { id: data.id }, header: { "If-Match": currentModified } },
      body: { status: "adopted" } as S["ProcedureWrite"],
    });
    if (patchErr) return { error: formatError(patchErr, "Procedure created as draft, but couldn't adopt.") };
  }

  refresh();
  return { id: data.id };
}

export async function updateProcedure(
  id: string,
  ifMatch: string,
  body: Partial<S["ProcedureWrite"]>,
  contentMd?: string,
): Promise<ActionState> {
  let currentModified = ifMatch;
  if (contentMd && contentMd.trim()) {
    const up = await uploadMultipart(`/procedures/${id}/content`, currentModified, {
      name: `${id}.md`,
      content: contentMd,
      type: "text/markdown",
    });
    if (up.error) return { error: up.error };
    if (up.modified) currentModified = up.modified;
  }
  const { data, error } = await api.PATCH("/procedures/{id}", {
    params: { path: { id }, header: { "If-Match": currentModified } },
    body: body as S["ProcedureWrite"],
  });
  if (error || !data) return { error: formatError(error, "Couldn't update procedure.") };
  refresh();
  return { id: data.id };
}

export async function revokeProcedure(id: string, ifMatch: string): Promise<ActionState> {
  const { error } = await api.POST("/procedures/{id}/revoke", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
  });
  if (error) return { error: formatError(error, "Couldn't revoke procedure.") };
  refresh();
  return { id };
}

// Systems, Components, Parties, Programs -----------------------------------

export async function createSystem(body: S["SystemWrite"]): Promise<ActionState> {
  const { data, error } = await api.POST("/systems", { body });
  if (error || !data) return { error: formatError(error, "Couldn't create system.") };
  refresh();
  return { id: data.id };
}

export async function updateSystem(id: string, ifMatch: string, body: Partial<S["SystemWrite"]>): Promise<ActionState> {
  const { data, error } = await api.PATCH("/systems/{id}", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
    body: body as S["SystemWrite"],
  });
  if (error || !data) return { error: formatError(error, "Couldn't update system.") };
  refresh();
  return { id: data.id };
}

export async function createComponent(
  body: S["ComponentWrite"],
  attachToSystem?: { id: string; modified: string; currentRefs: string[] },
): Promise<ActionState> {
  const { data, error } = await api.POST("/components", { body });
  if (error || !data) return { error: formatError(error, "Couldn't create component.") };

  if (attachToSystem) {
    const nextRefs = Array.from(new Set([...attachToSystem.currentRefs, data.id]));
    await api.PATCH("/systems/{id}", {
      params: { path: { id: attachToSystem.id }, header: { "If-Match": attachToSystem.modified } },
      body: { component_refs: nextRefs } as S["SystemWrite"],
    });
  }
  refresh();
  return { id: data.id };
}

export async function updateComponent(
  id: string,
  ifMatch: string,
  body: Partial<S["ComponentWrite"]>,
): Promise<ActionState> {
  const { data, error } = await api.PATCH("/components/{id}", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
    body: body as S["ComponentWrite"],
  });
  if (error || !data) return { error: formatError(error, "Couldn't update component.") };
  refresh();
  return { id: data.id };
}

export async function revokeComponent(id: string, ifMatch: string): Promise<ActionState> {
  const { error } = await api.POST("/components/{id}/revoke", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
  });
  if (error) return { error: formatError(error, "Couldn't revoke component.") };
  refresh();
  return { id };
}

export async function createParty(body: S["PartyWrite"] & { tags?: string[] }): Promise<ActionState> {
  const { data, error } = await api.POST("/parties", { body: body as S["PartyWrite"] });
  if (error || !data) return { error: formatError(error, "Couldn't create party.") };
  refresh();
  return { id: data.id };
}

export async function updateParty(
  id: string,
  ifMatch: string,
  body: Partial<S["PartyWrite"]> & { tags?: string[] },
): Promise<ActionState> {
  const { data, error } = await api.PATCH("/parties/{id}", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
    body: body as S["PartyWrite"],
  });
  if (error || !data) return { error: formatError(error, "Couldn't update party.") };
  refresh();
  return { id: data.id };
}

export async function revokeParty(id: string, ifMatch: string): Promise<ActionState> {
  const { error } = await api.POST("/parties/{id}/revoke", {
    params: { path: { id }, header: { "If-Match": ifMatch } },
  });
  if (error) return { error: formatError(error, "Couldn't revoke party.") };
  refresh();
  return { id };
}

export async function createProgram(body: S["ProgramWrite"]): Promise<ActionState> {
  const { data, error } = await api.POST("/programs", { body });
  if (error || !data) return { error: formatError(error, "Couldn't create program.") };
  refresh();
  return { id: data.id };
}

export async function updateBaselineControls(
  baselineId: string,
  ifMatch: string,
  controlRefs: string[],
): Promise<ActionState> {
  const { data, error } = await api.PATCH("/baselines/{id}", {
    params: { path: { id: baselineId }, header: { "If-Match": ifMatch } },
    body: { control_refs: controlRefs } as S["BaselineWrite"],
  });
  if (error || !data) return { error: formatError(error, "Couldn't update baseline.") };
  refresh();
  return { id: data.id };
}

/** The stored Markdown body of a policy or procedure, for editing. Empty if none. */
export async function getDocumentBody(kind: "policies" | "procedures", id: string): Promise<{ body: string; error?: string }> {
  const { data, error, response } =
    kind === "policies"
      ? await api.GET("/policies/{id}/content", { params: { path: { id } }, parseAs: "text" })
      : await api.GET("/procedures/{id}/content", { params: { path: { id } }, parseAs: "text" });
  if (response.status === 404) return { body: "" };
  if (error) return { body: "", error: formatError(error, "Couldn't load the current text.") };
  return { body: (data as string | undefined) ?? "" };
}
