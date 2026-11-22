"""Agent runtime dependencies and `ActorKind.AGENT` principal builder."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ogrl.access import ActorKind, Principal, Role
from ogrl.operations import types as t

if TYPE_CHECKING:
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


async def ensure_agent_party(container: Container, actor_id: str = DEFAULT_AGENT_ID) -> None:
    """Ensure the agent's organization `party` exists with `tags: ['agent']`."""
    if await container.store.get(actor_id) is not None:
        return
    bootstrap = Principal(
        actor_id="party--ogrl-system",
        organization_id=ORGANIZATION,
        kind=ActorKind.SERVICE,
        roles=frozenset({Role.ADMINISTRATOR}),
    )
    try:
        await container.objects.create(
            bootstrap,
            t.PARTY,
            {
                "id": actor_id,
                "name": "OGRL Compliance Agent",
                "kind": "role",
                "tags": ["agent"],
            },
        )
    except Exception:
        # Ignore race if created concurrently.
        return


@dataclass(frozen=True, slots=True)
class AgentDeps:
    container: Container
    principal: Principal
    created_drafts: list[dict[str, Any]] = field(default_factory=list)
