from dataclasses import dataclass
from enum import StrEnum

from fathom.access.roles import Role


class ActorKind(StrEnum):
    PERSON = "person"
    AGENT = "agent"
    SERVICE = "service"  # CI, a CLI token, a connector


@dataclass(frozen=True, slots=True)
class Principal:
    """Who is calling, resolved fresh on every request.

    `actor_id` is the caller's `party` id, so it is what `created_by_ref`
    records (RFC 0003 section 4).
    """

    actor_id: str
    organization_id: str
    kind: ActorKind
    roles: frozenset[Role]
