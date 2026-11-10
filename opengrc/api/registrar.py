"""Binds a catalog `Endpoint` to a handler and enforces the endpoint's rules.

Before any handler runs, the guard authenticates, checks the endpoint's
permission and feature, and puts the `Principal` on the request. Handlers
read it with the `CurrentPrincipal` dependency and never touch credentials.
"""

from collections.abc import Callable, Iterable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from opengrc.access import Authorizer, Principal
from opengrc.api.paths import Endpoint
from opengrc.auth import SESSION_COOKIE, Authenticator, Credentials
from opengrc.errors import FeatureDisabled, Forbidden, Unauthenticated
from opengrc.features import FeatureEvaluator


def credentials_from(request: Request) -> Credentials:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    bearer = token.strip() if scheme.lower() == "bearer" and token.strip() else None
    return Credentials(bearer=bearer, session=request.cookies.get(SESSION_COOKIE))


def current_principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if principal is None:  # an authenticated=False endpoint asked for a principal
        raise Unauthenticated("this endpoint is not authenticated")
    return principal


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


class Registrar:
    def __init__(
        self,
        router: APIRouter,
        authenticator: Authenticator,
        authorizer: Authorizer,
        features: FeatureEvaluator,
    ) -> None:
        self._router = router
        self._authenticator = authenticator
        self._authorizer = authorizer
        self._features = features
        self._bound: set[str] = set()

    def handle(self, endpoint: Endpoint, handler: Callable[..., Any]) -> None:
        if endpoint.id in self._bound:
            raise ValueError(f"{endpoint.id} is already bound")
        self._bound.add(endpoint.id)
        self._router.add_api_route(
            endpoint.path,
            handler,
            methods=[endpoint.method.value],
            status_code=endpoint.success_status,
            response_model=endpoint.response,
            response_model_exclude_none=True,
            operation_id=endpoint.id,
            summary=endpoint.summary,
            description=endpoint.description,
            tags=[endpoint.tag],
            dependencies=[Depends(self._guard(endpoint))],
        )

    def require_complete(self, catalog: Iterable[Endpoint]) -> None:
        """Fail at startup if a catalog endpoint has no handler."""
        missing = [e.id for e in catalog if e.id not in self._bound]
        if missing:
            raise RuntimeError(f"endpoints without handlers: {', '.join(missing)}")

    def _guard(self, endpoint: Endpoint) -> Callable[[Request], Any]:
        async def guard(request: Request) -> None:
            principal: Principal | None = None
            if endpoint.authenticated:
                principal = await self._authenticator.authenticate(credentials_from(request))
                if principal is None:
                    raise Unauthenticated("a session or bearer token is required")
                # TODO: cookie-authenticated unsafe methods must also pass an Origin check (CSRF).
                if endpoint.permission and not self._authorizer.allows(
                    principal, endpoint.permission
                ):
                    raise Forbidden(f"missing permission {endpoint.permission.value}")
            if endpoint.feature and not self._features.enabled(endpoint.feature, principal):
                raise FeatureDisabled(f"{endpoint.feature.value} is not enabled")
            request.state.principal = principal

        return guard
