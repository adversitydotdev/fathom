import "server-only";

import { notFound } from "next/navigation";
import { connection } from "next/server";
import createClient from "openapi-fetch";

import { apiMocking, apiOrigin, apiToken } from "@/lib/env";

import type { paths } from "./schema";
import type { Problem } from "./types";

/** Host used for in-process mock requests. Never resolved on the network. */
const MOCK_ORIGIN = "http://opengrc.mock";

async function mockFetch(request: Request): Promise<Response> {
  // A real fetch is request-time I/O. Without this, Next treats the in-process
  // mock as prerenderable work and rejects MSW's internal Math.random().
  await connection();
  // Imported lazily so fixtures stay out of the server bundle's hot path in real mode.
  const { handleMockRequest } = await import("@/mocks/dispatch");
  return handleMockRequest(request);
}

export const api = createClient<paths>({
  baseUrl: `${apiMocking ? MOCK_ORIGIN : apiOrigin}/v1`,
  headers: !apiMocking && apiToken ? { Authorization: `Bearer ${apiToken}` } : undefined,
  fetch: apiMocking ? mockFetch : undefined,
});

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly problem?: Problem,
  ) {
    super(problem?.title ?? `API request failed with ${status}`);
  }
}

/** Returns `data`, calls `notFound()` on 404, and throws `ApiError` otherwise. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (response.status === 404) notFound();
  if (error !== undefined || data === undefined) {
    throw new ApiError(response.status, error as Problem | undefined);
  }
  return data;
}
