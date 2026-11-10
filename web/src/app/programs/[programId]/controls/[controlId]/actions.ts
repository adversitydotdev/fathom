"use server";

import { api } from "@/lib/api/client";

export type RunState = { jobId?: string; error?: string };

/** RFC 0004: a run is long work, so the API answers 202 with a job to poll. */
export async function runTest(testId: string, implementationId: string): Promise<RunState> {
  const { data, error } = await api.POST("/tests/{id}/runs", {
    params: { path: { id: testId } },
    body: { implementation_id: implementationId },
  });
  if (error || !data) return { error: (error as { title?: string } | undefined)?.title ?? "Couldn't start the run." };
  return { jobId: data.id };
}
