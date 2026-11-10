from dataclasses import dataclass
from http import HTTPMethod, HTTPStatus
from typing import Any

from opengrc.access import Permission
from opengrc.features import Feature


@dataclass(frozen=True, slots=True, kw_only=True)
class Endpoint:
    """One route: the contract, and everything the registrar enforces before a handler runs.

    `id` is the operationId in api/openapi.yaml. tests/test_paths_contract.py
    holds the catalog and the spec to the same method and path.
    """

    id: str
    summary: str
    method: HTTPMethod
    path: str  # relative to /v1, in OpenAPI template syntax
    tag: str
    permission: Permission | None = None
    authenticated: bool = True
    feature: Feature | None = None
    response: Any = None  # the response model, also used for OpenAPI generation
    success_status: HTTPStatus = HTTPStatus.OK
    description: str = ""

    def url(self, **params: str) -> str:
        """Build a concrete URL, e.g. for a Location header."""
        return "/v1" + self.path.format(**params)
