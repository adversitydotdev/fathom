"""The role catalog: which permissions each role grants, and what it inherits."""

from dataclasses import dataclass
from enum import StrEnum

from ogrl.access.permissions import Permission as P


class Role(StrEnum):
    VIEWER = "viewer"
    CONTRIBUTOR = "contributor"
    AUDITOR = "auditor"
    AGENT = "agent"
    ADMINISTRATOR = "administrator"


@dataclass(frozen=True, slots=True)
class RoleDefinition:
    id: Role
    name: str
    description: str
    permissions: frozenset[P] = frozenset()
    inherits: tuple[Role, ...] = ()


ROLES: tuple[RoleDefinition, ...] = (
    RoleDefinition(
        id=Role.VIEWER,
        name="Viewer",
        description="Read the program, its status, and the library.",
        permissions=frozenset({P.LIBRARY_READ, P.CONTROLS_READ, P.PROGRAMS_READ}),
    ),
    RoleDefinition(
        id=Role.AGENT,
        name="Agent",
        description="Drafts objects a person later accepts. Cannot attest or review.",
        inherits=(Role.VIEWER,),
        # The gates in RFC 0003 section 4 still apply on top of these: an agent
        # never sets a status past `planned`, writes a run block, or revokes.
        permissions=frozenset(
            {
                P.MAPPINGS_WRITE,
                P.IMPLEMENTATIONS_WRITE,
                P.EVIDENCE_WRITE,
                P.TESTS_WRITE,
                P.TESTS_RUN,
                P.POLICIES_WRITE,
                P.RISKS_WRITE,
            }
        ),
    ),
    RoleDefinition(
        id=Role.CONTRIBUTOR,
        name="Contributor",
        description="Operate the program: controls, implementations, tests, evidence, risks.",
        inherits=(Role.AGENT,),
        permissions=frozenset(
            {
                P.CONTROLS_WRITE,
                P.CONTROLS_REVOKE,
                P.IMPLEMENTATIONS_ATTEST,
                P.TESTS_DEFINE_RUN,
                P.SYSTEMS_WRITE,
                P.OBJECTS_REVOKE,
            }
        ),
    ),
    RoleDefinition(
        id=Role.AUDITOR,
        name="Auditor",
        description="Read everything and record findings. Cannot change the program.",
        inherits=(Role.VIEWER,),
        permissions=frozenset({P.FINDINGS_WRITE}),
    ),
    RoleDefinition(
        id=Role.ADMINISTRATOR,
        name="Administrator",
        description="Everything, including library pulls, waivers, exports, and membership.",
        inherits=(Role.CONTRIBUTOR, Role.AUDITOR),
        permissions=frozenset(
            {
                P.LIBRARY_PULL,
                P.MAPPINGS_REVIEW,
                P.PROGRAMS_WRITE,
                P.PROGRAMS_RENDER,
                P.EXCEPTIONS_APPROVE,
                P.POLICIES_ADOPT,
                P.RISKS_ACCEPT,
                P.PROVIDERS_IMPORT,
                P.EXPORTS_RUN,
                P.RESTORE_RUN,
                P.CONNECTORS_RUN,
                P.MEMBERS_MANAGE,
            }
        ),
    ),
)
