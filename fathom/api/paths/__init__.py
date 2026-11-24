"""The route catalog. The single place a route's method, path, permission, and
response are declared. It never imports handlers; handlers import it.
"""

from fathom.api.paths import agent, auth, collections, integrations, meta, views
from fathom.api.paths.endpoint import Endpoint


def all_endpoints() -> tuple[Endpoint, ...]:
    return (
        *meta.ALL,
        *auth.ALL,
        *agent.ALL,
        *collections.ALL,
        *views.ALL,
        *integrations.ALL,
    )


__all__ = [
    "Endpoint",
    "agent",
    "all_endpoints",
    "auth",
    "collections",
    "integrations",
    "meta",
    "views",
]
