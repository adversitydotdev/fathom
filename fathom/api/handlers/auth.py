"""HTTP handlers for OIDC login, session introspection, logout, and API tokens."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Request, Response
from fastapi.responses import RedirectResponse

from fathom.api.paths import auth as p
from fathom.api.registrar import CurrentPrincipal, Registrar
from fathom.auth import SESSION_COOKIE
from fathom.operations.auth import AuthService, CreatedToken, CreateTokenRequest, SessionInfo


def register(registrar: Registrar, service: AuthService) -> None:
    async def begin_oidc(provider: str, redirect_to: str = "/") -> RedirectResponse:
        url = await service.begin_oidc(provider, redirect_to=redirect_to)
        return RedirectResponse(url=url, status_code=302)

    async def finish_oidc(
        request: Request, provider: str, code: str, state: str
    ) -> RedirectResponse:
        secret, expires, target = await service.finish_oidc(provider, code, state)
        resp = RedirectResponse(url=target, status_code=302)
        secure = request.url.scheme == "https"
        max_age = max(0, int((expires - datetime.now(UTC)).total_seconds()))
        resp.set_cookie(
            key=SESSION_COOKIE,
            value=secret,
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/",
            max_age=max_age,
        )
        return resp

    async def get_session(principal: CurrentPrincipal) -> SessionInfo:
        return service.session_info(principal)

    async def logout(request: Request, principal: CurrentPrincipal) -> Response:
        del principal
        await service.logout(request.cookies.get(SESSION_COOKIE))
        resp = Response(status_code=204)
        resp.delete_cookie(
            key=SESSION_COOKIE,
            path="/",
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
        )
        return resp

    async def list_tokens(principal: CurrentPrincipal) -> dict:
        return await service.list_tokens(principal)

    async def create_token(body: CreateTokenRequest, principal: CurrentPrincipal) -> CreatedToken:
        return await service.create_token(principal, body)

    async def revoke_token(id: str, principal: CurrentPrincipal) -> Response:
        await service.revoke_token(principal, id)
        return Response(status_code=204)

    registrar.handle(p.OIDC_BEGIN, begin_oidc)
    registrar.handle(p.OIDC_CALLBACK, finish_oidc)
    registrar.handle(p.GET_SESSION, get_session)
    registrar.handle(p.LOGOUT, logout)
    registrar.handle(p.LIST_TOKENS, list_tokens)
    registrar.handle(p.CREATE_TOKEN, create_token)
    registrar.handle(p.REVOKE_TOKEN, revoke_token)
