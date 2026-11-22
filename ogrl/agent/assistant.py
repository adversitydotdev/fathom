"""Pydantic AI agent factory, streaming runner, and drafting helpers (RFC 0003 §4)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from pydantic_ai import Agent
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    UserPromptPart,
)
from pydantic_ai.models import KnownModelName, Model

from ogrl.agent.config import AgentConfig
from ogrl.agent.deps import DEFAULT_AGENT_ID, AgentDeps, agent_principal, ensure_agent_party
from ogrl.agent.tools import register_tools

if TYPE_CHECKING:
    from ogrl.container import Container

SYSTEM_PROMPT = (
    "You are the OGRL security program assistant operating under RFC 0003 section 4. "
    "Read computed program status, control details, gaps, risks, and policies using your tools—"
    "never recompute control state on your own. When asked to draft work, write real OGRL draft "
    "objects (`implementation` with `status: planned`, `policy` with `status: draft`, `risk` "
    "with `status: open`, or `mapping` with `review_status: draft`) so humans can review and "
    "attest them directly in the UI. Be concise, cite exact control display IDs and requirement "
    "IDs, and never claim a control is met or implemented on a human's behalf. "
    "To test something an integration does not collect yet, define a query source: "
    "list_integrations, search_operations and describe_operation to find the read operation and "
    "its item fields, validate_query until it is valid, dry_run_query through a connection to "
    "check the fields come back filled, preview_rule over the sample items, then "
    "propose_query_source with the definition and the rule. You cannot save query sources or "
    "tests with a run block; the person reviews the draft in the query editor and saves it."
)


def build_agent(model: Model | KnownModelName | str) -> Agent[AgentDeps, str]:
    """Construct a configured Pydantic AI agent bound to OGRL's typed tool wrappers."""
    agent: Agent[AgentDeps, str] = Agent(
        model=model,
        deps_type=AgentDeps,
        system_prompt=SYSTEM_PROMPT,
    )
    register_tools(agent)
    return agent


def _to_message_history(history: list[dict[str, str]] | None) -> list[ModelMessage]:
    out: list[ModelMessage] = []
    for turn in history or []:
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            out.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        elif role == "assistant":
            out.append(ModelResponse(parts=[TextPart(content=content)]))
    return out


def _compose_prompt(message: str, context: dict[str, str | None] | None) -> str:
    if not context:
        return message
    bits = [f"{k}={v}" for k, v in context.items() if v]
    if not bits:
        return message
    return f"[Active UI context: {', '.join(bits)}]\n\n{message}"


async def stream_agent_turn(
    container: Container,
    *,
    config: AgentConfig,
    message: str,
    history: list[dict[str, str]] | None = None,
    context: dict[str, str | None] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Run one agent turn and yield structured SSE event dicts."""
    if not config.enabled:
        yield {"type": "error", "message": config.hint or "AI assistant is not configured."}
        return

    await ensure_agent_party(container, config.actor_id)
    agent = build_agent(config.resolve_model())
    deps = AgentDeps(container=container, principal=agent_principal(config.actor_id))
    prompt = _compose_prompt(message, context)
    msg_history = _to_message_history(history)
    emitted_drafts = 0
    accumulated = ""

    try:
        async with agent.iter(prompt, deps=deps, message_history=msg_history) as run:
            async for node in run:
                if Agent.is_model_request_node(node):
                    need_sep = bool(accumulated) and not accumulated.endswith("\n\n")
                    async with node.stream(run.ctx) as request_stream:
                        async for event in request_stream:
                            if (
                                isinstance(event, PartStartEvent)
                                and isinstance(event.part, TextPart)
                                and event.part.content
                            ):
                                chunk = event.part.content
                                if need_sep:
                                    chunk = ("\n" if accumulated.endswith("\n") else "\n\n") + chunk
                                    need_sep = False
                                accumulated += chunk
                                yield {"type": "delta", "text": chunk}
                            elif (
                                isinstance(event, PartDeltaEvent)
                                and isinstance(event.delta, TextPartDelta)
                                and event.delta.content_delta
                            ):
                                chunk = event.delta.content_delta
                                if need_sep:
                                    chunk = ("\n" if accumulated.endswith("\n") else "\n\n") + chunk
                                    need_sep = False
                                accumulated += chunk
                                yield {"type": "delta", "text": chunk}
                elif Agent.is_call_tools_node(node):
                    async with node.stream(run.ctx) as handle_stream:
                        async for event in handle_stream:
                            if isinstance(event, FunctionToolCallEvent):
                                yield {
                                    "type": "tool_call",
                                    "name": event.part.tool_name,
                                    "args": event.part.args_as_dict(),
                                }
                            elif isinstance(event, FunctionToolResultEvent):
                                yield {
                                    "type": "tool_result",
                                    "name": event.part.tool_name,
                                }
                                while emitted_drafts < len(deps.created_drafts):
                                    yield {"type": "draft", **deps.created_drafts[emitted_drafts]}
                                    emitted_drafts += 1

        final_text = (run.result.output if run.result else "") or accumulated
        if not accumulated and final_text:
            yield {"type": "delta", "text": final_text}
        while emitted_drafts < len(deps.created_drafts):
            yield {"type": "draft", **deps.created_drafts[emitted_drafts]}
            emitted_drafts += 1
        yield {"type": "done", "text": final_text, "drafts": deps.created_drafts}
    except Exception as exc:
        yield {"type": "error", "message": str(exc)}


async def draft_gap_remediation(
    container: Container,
    *,
    system_id: str,
    model: Model | KnownModelName | str,
    actor_id: str = DEFAULT_AGENT_ID,
    prompt: str | None = None,
) -> Any:
    """Run the agent to inspect a system's gaps and draft planned implementations."""
    agent = build_agent(model)
    deps = AgentDeps(container=container, principal=agent_principal(actor_id))
    user_prompt = prompt or (
        f"Inspect open control gaps on system {system_id} and draft `planned` "
        "implementation narratives for any unimplemented controls."
    )
    return await agent.run(user_prompt, deps=deps)
