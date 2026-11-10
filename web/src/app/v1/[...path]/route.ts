import { apiMocking } from "@/lib/env";

/**
 * In mock mode, `/v1/*` on the web origin is answered from fixtures, so a
 * browser or `curl` sees the same API the server components do. Outside mock
 * mode a `beforeFiles` rewrite in next.config.ts proxies `/v1` to the API and
 * this handler is not reached.
 */
async function handle(request: Request): Promise<Response> {
  if (!apiMocking) {
    return new Response("Not found", { status: 404 });
  }
  const { handleMockRequest } = await import("@/mocks/dispatch");
  return handleMockRequest(request);
}

export { handle as GET, handle as POST, handle as PATCH };
