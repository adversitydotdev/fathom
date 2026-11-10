"""Authorization behind an interface.

`Authorizer` is what callers depend on. `StaticPolicy` compiles the in-code
role catalog once at startup. A Casbin- or Cerbos-backed authorizer is a
second implementation of the same protocol; nothing else changes.
"""

from collections.abc import Iterable
from typing import Protocol

from opengrc.access.permissions import Permission
from opengrc.access.principal import Principal
from opengrc.access.roles import ROLES, Role, RoleDefinition
from opengrc.errors import Forbidden


class Authorizer(Protocol):
    def allows(self, principal: Principal, permission: Permission) -> bool: ...


class StaticPolicy:
    def __init__(self, roles: Iterable[RoleDefinition] = ROLES) -> None:
        definitions = {role.id: role for role in roles}
        self._effective = {
            role_id: self._resolve(role_id, definitions, ()) for role_id in definitions
        }

    @staticmethod
    def _resolve(
        role_id: Role,
        definitions: dict[Role, RoleDefinition],
        path: tuple[Role, ...],
    ) -> frozenset[Permission]:
        if role_id in path:
            raise ValueError(f"role inheritance cycle: {' -> '.join((*path, role_id))}")
        if role_id not in definitions:
            raise ValueError(f"unknown role {role_id!r}")
        role = definitions[role_id]
        granted = set(role.permissions)
        for parent in role.inherits:
            granted |= StaticPolicy._resolve(parent, definitions, (*path, role_id))
        return frozenset(granted)

    def effective_permissions(self, role: Role) -> frozenset[Permission]:
        return self._effective.get(role, frozenset())

    def allows(self, principal: Principal, permission: Permission) -> bool:
        return any(permission in self.effective_permissions(role) for role in principal.roles)


def require(authorizer: Authorizer, principal: Principal, permission: Permission) -> None:
    if not authorizer.allows(principal, permission):
        raise Forbidden(f"missing permission {permission.value}")
