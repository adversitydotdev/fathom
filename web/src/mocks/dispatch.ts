import { delay, getResponse } from "msw";

import { handlers, problem } from "./handlers";

const latency = Number(process.env.FATHOM_MOCK_LATENCY_MS ?? 0);

/**
 * Resolves a request against the MSW handlers in-process. Used as the API
 * client's `fetch` in mock mode and by the `/v1` route handler.
 */
export async function handleMockRequest(request: Request): Promise<Response> {
  if (latency > 0) await delay(latency);
  const response = await getResponse(handlers, request);
  return response ?? problem(404, "not-found", `No mock for ${request.method} ${new URL(request.url).pathname}`);
}
