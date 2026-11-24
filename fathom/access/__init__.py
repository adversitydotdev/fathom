"""Who may do what: permissions, roles, the principal, and the authorizer."""

from fathom.access.permissions import Permission
from fathom.access.policy import Authorizer, StaticPolicy, require
from fathom.access.principal import ActorKind, Principal
from fathom.access.roles import Role

__all__ = ["ActorKind", "Authorizer", "Permission", "Principal", "Role", "StaticPolicy", "require"]
