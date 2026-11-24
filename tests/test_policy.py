import pytest

from fathom.access import ActorKind, Permission, Principal, Role, StaticPolicy
from fathom.access.roles import RoleDefinition

policy = StaticPolicy()


def principal(*roles: Role) -> Principal:
    return Principal("party--a", "org", ActorKind.PERSON, frozenset(roles))


def test_administrator_inherits_everything():
    for permission in Permission:
        assert policy.allows(principal(Role.ADMINISTRATOR), permission), permission


def test_agent_drafts_but_cannot_attest_or_review():
    agent = principal(Role.AGENT)
    assert policy.allows(agent, Permission.IMPLEMENTATIONS_WRITE)
    assert not policy.allows(agent, Permission.IMPLEMENTATIONS_ATTEST)
    assert not policy.allows(agent, Permission.MAPPINGS_REVIEW)


def test_auditor_cannot_change_the_program():
    assert not policy.allows(principal(Role.AUDITOR), Permission.CONTROLS_WRITE)
    assert policy.allows(principal(Role.AUDITOR), Permission.FINDINGS_WRITE)


def test_inheritance_cycle_is_rejected():
    with pytest.raises(ValueError, match="cycle"):
        StaticPolicy(
            [
                RoleDefinition(Role.VIEWER, "v", "", inherits=(Role.AGENT,)),
                RoleDefinition(Role.AGENT, "a", "", inherits=(Role.VIEWER,)),
            ]
        )
