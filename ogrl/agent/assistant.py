"""Pydantic AI agent factory and high-level drafting helpers (RFC 0003 §4)."""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName, Model

from ogrl.agent.deps import DEFAULT_AGENT_ID, AgentDeps, agent_principal
from ogrl.agent.tools import register_tools
from ogrl.container import Container

SYSTEM_PROMPT = (
    "You are an OGRL security program assistant operating under RFC 0003 section 4. "
    "You read computed program status and gaps from the OGRL kernel, draft `planned` "
    "implementation narratives, and propose `draft` crosswalk mappings for human review. "
    "Never claim a control is met or implemented; humans review and attest all drafts."
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
