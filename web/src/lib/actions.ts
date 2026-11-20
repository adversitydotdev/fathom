"use server";

import { api } from "@/lib/api/client";

export type ActionState = { jobId?: string; error?: string };

export async function triggerRender(
  programId: string,
  view: "oscal" | "ssp",
  frameworkId?: string,
): Promise<ActionState> {
  const { data, error } = await api.POST("/programs/{id}/renders", {
    params: { path: { id: programId } },
    body: { view, ...(frameworkId ? { framework_id: frameworkId } : {}) },
  });
  if (error || !data) {
    return { error: (error as { title?: string } | undefined)?.title ?? "Couldn't queue render." };
  }
  return { jobId: data.id };
}

export async function triggerGitExport(): Promise<ActionState> {
  const { data, error } = await api.POST("/exports/git");
  if (error || !data) {
    return { error: (error as { title?: string } | undefined)?.title ?? "Couldn't queue Git export." };
  }
  return { jobId: data.id };
}

export async function triggerLibraryPull(version: string): Promise<ActionState> {
  const { data, error } = await api.POST("/library/pull", {
    body: { version },
  });
  if (error || !data) {
    return { error: (error as { title?: string } | undefined)?.title ?? "Couldn't queue library pull." };
  }
  return { jobId: data.id };
}
