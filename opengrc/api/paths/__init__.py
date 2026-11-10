"""The route catalog. The single place a route's method, path, permission, and
response are declared. It never imports handlers; handlers import it.
"""

from opengrc.api.paths import controls, meta
from opengrc.api.paths.endpoint import Endpoint


def all_endpoints() -> tuple[Endpoint, ...]:
    return (*meta.ALL, *controls.ALL)


__all__ = ["Endpoint", "all_endpoints", "controls", "meta"]
