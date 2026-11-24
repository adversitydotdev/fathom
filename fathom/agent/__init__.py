"""Pydantic AI agent package (RFC 0003 section 4).

Agents are ordinary callers of the application's services using an `ActorKind.AGENT`
principal. Hard-coded write gates in `ObjectService` prevent an agent from marking
an implementation `implemented`, accepting a mapping review, recording findings or
exceptions, defining a `test.run` block, or revoking any object.
"""

from fathom.agent.assistant import (
    SYSTEM_PROMPT,
    build_agent,
    draft_gap_remediation,
    stream_agent_turn,
)
from fathom.agent.config import AgentConfig
from fathom.agent.deps import AgentDeps, agent_principal, ensure_agent_party

__all__ = [
    "SYSTEM_PROMPT",
    "AgentConfig",
    "AgentDeps",
    "agent_principal",
    "build_agent",
    "draft_gap_remediation",
    "ensure_agent_party",
    "stream_agent_turn",
]
