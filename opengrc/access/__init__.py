"""Who may do what: permissions, roles, the principal, and the authorizer."""

from opengrc.access.permissions import Permission
from opengrc.access.policy import Authorizer, StaticPolicy, require
from opengrc.access.principal import ActorKind, Principal
from opengrc.access.roles import Role

__all__ = ["ActorKind", "Authorizer", "Permission", "Principal", "Role", "StaticPolicy", "require"]
