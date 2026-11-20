"""Binds a catalog `Endpoint` to a handler and enforces the endpoint's rules.

Before any handler runs, the guard authenticates, checks the endpoint's
permission and feature, enforces same-origin CSRF checks for cookie-authenticated
unsafe requests, and puts the `Principal` on the request. Handlers read it with
the `CurrentPrincipal` dependency and never touch credentials.
"""

from collections.abc import Callable, Iterable
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request

from ogrl.access import Authorizer, Principal
from ogrl.api.paths import Endpoint
from ogrl.auth import SESSION_COOKIE, Authenticator, Credentials
from ogrl.errors import FeatureDisabled, Forbidden, Unauthenticated
from ogrl.features import FeatureEvaluator

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def credentials_from(request: Request) -> Credentials:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    bearer = token.strip() if scheme.lower() == "bearer" and token.strip() else None
    return Credentials(bearer=bearer, session=request.cookies.get(SESSION_COOKIE))


def _check_csrf_origin(request: Request, allowed_origins: frozenset[str]) -> None:
    """Cookie-authenticated unsafe methods must carry a matching Origin or Referer."""
    if request.method.upper() not in UNSAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if origin:
        parsed = urlparse(origin)
        candidate = f"{parsed.scheme}://{parsed.netloc}".lower() if parsed.scheme else ""
    else:
        referer = request.headers.get("referer")
        if not referer:
            raise Forbidden("missing Origin header on cookie-authenticated write", slug="csrf")
        parsed = urlparse(referer)
        candidate = f"{parsed.scheme}://{parsed.netloc}".lower() if parsed.scheme else ""

    expected_host = (
        request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    ).lower()
    expected_scheme = (
        request.headers.get("x-forwarded-proto") or request.url.scheme or "http"
    ).lower()
    expected_origin = f"{expected_scheme}://{expected_host}"

    if candidate == expected_origin or candidate in allowed_origins:
        return
    raise Forbidden("Origin does not match request host", slug="csrf")


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
        allowed_origins: Iterable[str] = (),
    ) -> None:
        self._router = router
        self._authenticator = authenticator
        self._authorizer = authorizer
        self._features = features
        self._allowed_origins = frozenset(o.rstrip("/").lower() for o in allowed_origins if o)
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
                creds = credentials_from(request)
                principal = await self._authenticator.authenticate(creds)
                if principal is None:
                    raise Unauthenticated("a session or bearer token is required")
                if creds.bearer is None and creds.session is not None:
                    _check_csrf_origin(request, self._allowed_origins)
                if endpoint.permission and not self._authorizer.allows(
                    principal, endpoint.permission
                ):
                    raise Forbidden(f"missing permission {endpoint.permission.value}")
            if endpoint.feature and not self._features.enabled(endpoint.feature, principal):
                raise FeatureDisabled(f"{endpoint.feature.value} is not enabled")
            request.state.principal = principal

        return guard
