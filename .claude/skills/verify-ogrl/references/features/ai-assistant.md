# AI assistant

Pydantic AI assistant wired through RFC 0003 §4 write gates (`ActorKind.AGENT` principal).

## Sub-features

- backend-config: `ogrl/agent/config.py` auto-detects `ANTHROPIC_API_KEY` (`anthropic:claude-sonnet-4-5`) or `OPENAI_API_KEY` / `OGRL_AI_BASE_URL` (`openai:gpt-4o`), or explicit `OGRL_AI_MODEL`.
- http-endpoints: `GET /v1/agent/status` and `POST /v1/agent/stream` (SSE streaming of `tool_call`, `tool_result`, `draft`, `delta`, `done`, `error`).
- assistant-drawer: `web/src/components/agent/assistant-drawer.tsx` slide-over drawer toggled from header `AI` button, displaying active model, RFC 0003 §4 guardrails, live tool-call pills, clickable created-draft cards, and ephemeral browser session history.
- contextual-triggers: `Analyze gaps` on Overview, `Draft with AI` on Control Detail & Policies, `Propose crosswalk` on Requirements.
- accept-draft: 1-click `Accept draft` button inside the `AgentMark` banner on agent-authored `planned` implementations to promote them to `implemented` as the human reviewer.

## Driving it

```bash
uv run pytest tests/test_agent.py -vv
pnpm --dir web e2e agent
```
