import { apiMocking, apiOrigin, apiToken } from "@/lib/env";

export async function GET(): Promise<Response> {
  if (apiMocking) {
    return Response.json({
      enabled: true,
      model: "anthropic:claude-sonnet-4-5",
      provider: "anthropic",
      actor_id: "party--compliance-agent",
      hint: null,
    });
  }

  const headers: Record<string, string> = { Accept: "application/json" };
  if (apiToken) headers.Authorization = `Bearer ${apiToken}`;

  const upstream = await fetch(`${apiOrigin}/v1/agent/status`, {
    headers,
    cache: "no-store",
  });
  const body = await upstream.text();
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
