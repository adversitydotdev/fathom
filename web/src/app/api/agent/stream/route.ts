import { apiMocking, apiOrigin, apiToken } from "@/lib/env";

type StreamReq = {
  message?: string;
  history?: Array<{ role: string; content: string }>;
  context?: {
    program_id?: string;
    system_id?: string;
    control_id?: string;
    route?: string;
  };
};

async function mockStream(body: StreamReq): Promise<Response> {
  const { handleMockRequest } = await import("@/mocks/dispatch");
  const msg = (body.message ?? "").toLowerCase();
  const ctx = body.context ?? {};

  const events: unknown[] = [];
  const drafts: Array<{ object_type: string; id: string; control_ref?: string; label: string }> = [];

  if (msg.includes("policy")) {
    events.push({ type: "tool_call", name: "draft_policy", args: { name: "AI-Drafted Acceptable Use Policy" } });
    const res = await handleMockRequest(
      new Request("http://ogrl.mock/v1/policies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: "AI-Drafted Acceptable Use Policy",
          status: "draft",
          version: "0.1",
          review_interval: "annual",
          created_by_ref: "party--compliance-agent",
        }),
      }),
    );
    const created = (await res.json()) as { id: string };
    events.push({ type: "tool_result", name: "draft_policy" });
    const draft = {
      object_type: "policy",
      id: created.id,
      label: "Draft policy: AI-Drafted Acceptable Use Policy",
    };
    drafts.push(draft);
    events.push({ type: "draft", ...draft });
    const text =
      "I created a draft **AI-Drafted Acceptable Use Policy** (`status: draft`) attributed to the Compliance agent. Review the wording and adopt it when ready.";
    events.push({ type: "delta", text });
    events.push({ type: "done", text, drafts });
  } else if (ctx.control_id && msg.includes("draft")) {
    events.push({
      type: "tool_call",
      name: "get_control_detail",
      args: { control_id: ctx.control_id },
    });
    events.push({ type: "tool_result", name: "get_control_detail" });
    const text = `Reviewed **${ctx.control_id}**. Because agents only author \`planned\` drafts under RFC 0003 §4, I prepared a suggested narrative and parameter set for human review and attestation.`;
    events.push({ type: "delta", text });
    events.push({ type: "done", text, drafts });
  } else {
    events.push({
      type: "tool_call",
      name: "get_program_status",
      args: { program_id: ctx.program_id ?? "program--acme-platform-800-171" },
    });
    events.push({ type: "tool_result", name: "get_program_status" });
    const text =
      "Checked computed status from the OGRL kernel. Open gaps include **IAM-01** (unset `review_period`), **IAM-02** (failing MFA check), **LOG-02** (expired weekly review evidence), and **CHG-01** (missing test methodology). Ask me to draft any implementation or policy for human review.";
    events.push({ type: "delta", text });
    events.push({ type: "done", text, drafts });
  }

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      for (const ev of events) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(ev)}\n\n`));
      }
      controller.close();
    },
  });

  return new Response(stream, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
    },
  });
}

export async function POST(request: Request): Promise<Response> {
  const body = (await request.json().catch(() => ({}))) as StreamReq;

  if (apiMocking) {
    return mockStream(body);
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  if (apiToken) headers.Authorization = `Bearer ${apiToken}`;

  const upstream = await fetch(`${apiOrigin}/v1/agent/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    cache: "no-store",
  });

  if (!upstream.ok || !upstream.body) {
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
    });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
    },
  });
}
