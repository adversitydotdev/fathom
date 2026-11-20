"""Pydantic AI agent package (RFC 0003 section 4).

Agents are ordinary callers of the application's services using an `ActorKind.AGENT`
principal. Hard-coded write gates in `ObjectService` prevent an agent from marking
an implementation `implemented`, accepting a mapping review, recording findings or
exceptions, defining a `test.run` block, or revoking any object.
"""

from ogrl.agent.assistant import SYSTEM_PROMPT, build_agent, draft_gap_remediation
from ogrl.agent.deps import AgentDeps, agent_principal

__all__ = [
    "SYSTEM_PROMPT",
    "AgentDeps",
    "agent_principal",
    "build_agent",
    "draft_gap_remediation",
]
