# AI assistant

Pydantic AI assistant wired through RFC 0003 §4 write gates (`ActorKind.AGENT` principal).

## Sub-features

- backend-config: `fathom/agent/config.py` auto-detects `ANTHROPIC_API_KEY` (`anthropic:claude-sonnet-4-5`) or `OPENAI_API_KEY` / `FATHOM_AI_BASE_URL` (`openai:gpt-4o`), or explicit `FATHOM_AI_MODEL`.
- http-endpoints: `GET /v1/agent/status` and `POST /v1/agent/stream` (SSE streaming of `tool_call`, `tool_result`, `draft`, `delta`, `done`, `error`).
- assistant-drawer: `web/src/components/agent/assistant-drawer.tsx` slide-over drawer toggled from the header `Ask AI` button, displaying active model, RFC 0003 §4 guardrails, live tool-call pills, clickable created-draft cards, and ephemeral browser session history.
- contextual-triggers: `Analyze gaps` on Overview, `Draft with AI` on Control Detail & Policies, `Propose crosswalk` on Requirements.
- query-source-drafts (RFC 0006 section 9): tools `list_integrations`, `search_operations`, `describe_operation`, `validate_query`, `dry_run_query`, `preview_rule`, and `propose_query_source` (`fathom/agent/tools.py`). The agent may validate, sample, and preview but cannot save a query source or a test with a run block (`tests:define-run`); `propose_query_source` validates and emits a `draft` event with `object_type: query_source`, the `definition`, and an optional `rule`. The drawer links it to `/programs/{id}/integrations?draft=<json>`, which opens `New query source on <integration>` prefilled with an `Assistant draft` banner and the suggested rule; the person validates, samples, and saves. In mock mode a message mentioning `security group` or `query source` scripts the flow (a misspelt `GroupID` fixed after validation) in `web/src/app/api/agent/stream/route.ts`. Backend test: `tests/test_agent_queries.py`; e2e: the last test in `web/e2e/query-editor.spec.ts`.
- accept-draft: 1-click `Accept draft` button inside the `AgentMark` banner on agent-authored `planned` implementations to promote them to `implemented` as the human reviewer.

## Driving it

```bash
uv run pytest tests/test_agent.py -vv
pnpm --dir web e2e agent
```
