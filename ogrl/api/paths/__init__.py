"""The route catalog. The single place a route's method, path, permission, and
response are declared. It never imports handlers; handlers import it.
"""

from ogrl.api.paths import agent, auth, collections, meta, views
from ogrl.api.paths.endpoint import Endpoint


def all_endpoints() -> tuple[Endpoint, ...]:
    return (*meta.ALL, *auth.ALL, *agent.ALL, *collections.ALL, *views.ALL)


__all__ = ["Endpoint", "agent", "all_endpoints", "auth", "collections", "meta", "views"]
