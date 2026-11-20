"""Agent runtime dependencies and `ActorKind.AGENT` principal builder."""

from __future__ import annotations

from dataclasses import dataclass

from ogrl.access import ActorKind, Principal, Role
from ogrl.container import Container

DEFAULT_AGENT_ID = "party--ogrl-agent"
ORGANIZATION = "organization"


def agent_principal(actor_id: str = DEFAULT_AGENT_ID) -> Principal:
    """Create the restricted `ActorKind.AGENT` principal enforced by RFC 0003 §4."""
    return Principal(
        actor_id=actor_id,
        organization_id=ORGANIZATION,
        kind=ActorKind.AGENT,
        roles=frozenset({Role.AGENT}),
    )


@dataclass(frozen=True, slots=True)
class AgentDeps:
    container: Container
    principal: Principal
