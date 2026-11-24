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
  const drafts: Array<{
    object_type: string;
    id: string;
    control_ref?: string;
    label: string;
    definition?: Record<string, unknown>;
    rule?: Record<string, unknown>;
  }> = [];
  const mockApi = async (path: string, payload?: unknown) => {
    const res = await handleMockRequest(
      new Request(`http://fathom.mock/v1${path}`, {
        method: payload === undefined ? "GET" : "POST",
        headers: { "Content-Type": "application/json" },
        ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
      }),
    );
    return (await res.json()) as Record<string, unknown>;
  };

  if (msg.includes("security group") || msg.includes("query source")) {
    // RFC 0006 section 9: search, describe, validate, fix, sample, then propose a draft.
    const aws = "dev.adversity.aws";
    const definition = {
      integration_id: aws,
      name: "internet-open-groups",
      version: 1,
      description: "Security groups with an inbound rule from 0.0.0.0/0.",
      operation: "ec2.DescribeSecurityGroups",
      params: { Filters: '[{"Name": "ip-permission.cidr", "Values": ["0.0.0.0/0"]}]' },
      regions: "*",
      fields: { id: "GroupId", name: "GroupName", vpc: "VpcId", rules: "IpPermissions" },
    };
    const rule = { source: `${aws}/internet-open-groups@1`, assert: "item.rules == []" };
    const step = async (name: string, args: Record<string, unknown>, run: () => Promise<unknown>) => {
      events.push({ type: "tool_call", name, args });
      const out = await run();
      events.push({ type: "tool_result", name });
      return out;
    };
    await step("list_integrations", {}, () => mockApi("/integrations"));
    await step("search_operations", { integration_id: aws, text: "security groups" }, () =>
      mockApi(`/integrations/${aws}/operations?q=security%20groups`),
    );
    await step("describe_operation", { integration_id: aws, operation: definition.operation }, () =>
      mockApi(`/integrations/${aws}/operations/${definition.operation}`),
    );
    const misspelt = { ...definition, fields: { ...definition.fields, id: "GroupID" } };
    await step("validate_query", { definition: misspelt }, () => mockApi("/queries/validate", misspelt));
    await step("validate_query", { definition }, () => mockApi("/queries/validate", definition));
    const sample = (await step("dry_run_query", { definition, connection_id: "connection--aws-prod" }, () =>
      mockApi("/queries/dry-run", { ...definition, connection_id: "connection--aws-prod", max_items: 20 }),
    )) as { count?: number };
    await step("propose_query_source", { definition, rule }, async () => ({ proposed: true }));
    const draft = {
      object_type: "query_source",
      id: rule.source,
      label: `Draft query source: ${rule.source}`,
      definition,
      rule,
    };
    drafts.push(draft);
    events.push({ type: "draft", ...draft });
    const text =
      `I drafted **internet-open-groups@1** over \`ec2.DescribeSecurityGroups\`, filtered to inbound rules from 0.0.0.0/0, in every connected region. ` +
      `My first draft read \`GroupID\`; validation pointed at \`GroupId\` and I fixed it. A dry run through AWS production returned ${sample.count ?? 0} items. ` +
      "Agents cannot save query sources, so review the draft in the query editor and save it, then add the rule `item.rules == []`.";
    events.push({ type: "delta", text });
    events.push({ type: "done", text, drafts });
  } else if (msg.includes("policy")) {
    events.push({ type: "tool_call", name: "draft_policy", args: { name: "AI-Drafted Acceptable Use Policy" } });
    const res = await handleMockRequest(
      new Request("http://fathom.mock/v1/policies", {
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
      "Checked computed status from the Fathom kernel. Open gaps include **IAM-01** (unset `review_period`), **IAM-02** (failing MFA check), **LOG-02** (expired weekly review evidence), and **CHG-01** (missing test methodology). Ask me to draft any implementation or policy for human review.";
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
