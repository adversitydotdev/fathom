"""Interactive authentication use cases: OIDC sign-in, sessions, and API token minting."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel

from fathom.access import ActorKind, Authorizer, Permission, Principal, Role, require
from fathom.auth.authenticator import digest
from fathom.auth.oidc import IdentityProvider, OidcStateStore
from fathom.auth.store import DEFAULT_SESSION_TTL, AuthStore, TokenRecord
from fathom.errors import Forbidden, Invalid, NotFound
from fathom.kernel import ids
from fathom.kernel.models import Party
from fathom.kernel.timeutil import now, utc
from fathom.operations.records import ORGANIZATION
from fathom.operations.store import ObjectStore, Row


class SessionInfo(BaseModel):
    actor_id: str
    organization_id: str
    kind: ActorKind
    roles: list[str]
    permissions: list[str]


class CreateTokenRequest(BaseModel):
    name: str
    actor_id: str | None = None
    actor_kind: ActorKind | None = None
    roles: list[Role] | None = None
    expires_in_days: int | None = None


class CreatedToken(BaseModel):
    token: str
    record: TokenRecord


class AuthService:
    def __init__(
        self,
        store: ObjectStore,
        auth_store: AuthStore,
        authorizer: Authorizer,
        providers: Mapping[str, IdentityProvider] | None = None,
        *,
        default_roles: tuple[Role, ...] = (Role.VIEWER,),
        bootstrap_admin_emails: frozenset[str] = frozenset(),
        session_ttl: timedelta = DEFAULT_SESSION_TTL,
        allow_token_minting: bool = True,
        clock: Callable[[], datetime] = now,
    ) -> None:
        self._store = store
        self._auth = auth_store
        self._authorizer = authorizer
        self._providers = dict(providers or {})
        self._default_roles = default_roles
        self._bootstrap_admins = frozenset(e.lower() for e in bootstrap_admin_emails)
        self._session_ttl = session_ttl
        self._allow_token_minting = allow_token_minting
        self._clock = clock
        self._states = OidcStateStore(clock=clock)

    def _provider(self, name: str) -> IdentityProvider:
        provider = self._providers.get(name)
        if provider is None:
            raise NotFound(f"OIDC provider {name!r} is not configured")
        return provider

    @staticmethod
    def _safe_redirect(target: str | None) -> str:
        if not target or not target.startswith("/") or target.startswith("//"):
            return "/"
        return target

    async def begin_oidc(self, provider_name: str, redirect_to: str | None = None) -> str:
        provider = self._provider(provider_name)
        state, pending = self._states.issue(provider_name, self._safe_redirect(redirect_to))
        return await provider.authorization_url(state, pending.nonce, pending.code_verifier)

    async def finish_oidc(
        self, provider_name: str, code: str, state: str
    ) -> tuple[str, datetime, str]:
        provider = self._provider(provider_name)
        pending = self._states.consume(state, provider_name)
        verified = await provider.exchange(code, pending.code_verifier, pending.nonce)

        existing = await self._auth.lookup_oidc(verified.issuer, verified.subject)
        if existing is not None:
            actor_id = existing.actor_id
        else:
            actor_id = ids.mint("party")
            stamp = utc(self._clock())
            display_name = verified.name or verified.email or verified.subject
            party = Party(
                id=actor_id,
                name=display_name,
                kind="person",
                created=stamp,
                modified=stamp,
                created_by_ref=actor_id,
            )
            await self._store.insert(Row(party, ORGANIZATION), actor_id)
            roles = list(self._default_roles)
            if verified.email and verified.email.lower() in self._bootstrap_admins:
                roles = [Role.ADMINISTRATOR]
            await self._auth.upsert_identity(
                actor_id,
                kind=ActorKind.PERSON,
                roles=roles,
                issuer=verified.issuer,
                subject=verified.subject,
                email=verified.email,
            )

        secret, expires = await self._auth.create_session(actor_id, ttl=self._session_ttl)
        return secret, expires, pending.redirect_to

    def session_info(self, principal: Principal) -> SessionInfo:
        permissions = sorted(p.value for p in Permission if self._authorizer.allows(principal, p))
        return SessionInfo(
            actor_id=principal.actor_id,
            organization_id=principal.organization_id,
            kind=principal.kind,
            roles=sorted(r.value for r in principal.roles),
            permissions=permissions,
        )

    async def logout(self, session_cookie: str | None) -> None:
        if session_cookie:
            await self._auth.revoke_session(digest(session_cookie))

    async def create_token(self, principal: Principal, request: CreateTokenRequest) -> CreatedToken:
        if not self._allow_token_minting and principal.kind is ActorKind.PERSON:
            raise Forbidden("API token minting is disabled for people; sign in through the IdP")
        if not request.name.strip():
            raise Invalid("token name must not be empty")
        target_actor = request.actor_id or principal.actor_id
        if target_actor != principal.actor_id or request.roles is not None:
            require(self._authorizer, principal, Permission.MEMBERS_MANAGE)
            roles = tuple(request.roles) if request.roles else (Role.AGENT,)
            kind = request.actor_kind or ActorKind.AGENT
            await self._auth.upsert_identity(target_actor, kind=kind, roles=roles)
        else:
            existing = await self._auth.principal(target_actor)
            if existing is None:
                await self._auth.upsert_identity(
                    target_actor, kind=principal.kind, roles=principal.roles
                )

        expires_at: datetime | None = None
        if request.expires_in_days is not None:
            if request.expires_in_days <= 0:
                raise Invalid("expires_in_days must be positive")
            expires_at = utc(self._clock()) + timedelta(days=request.expires_in_days)

        record, plaintext = await self._auth.create_token(
            target_actor,
            request.name.strip(),
            created_by_ref=principal.actor_id,
            expires_at=expires_at,
        )
        return CreatedToken(token=plaintext, record=record)

    async def list_tokens(self, principal: Principal) -> dict[str, Any]:
        is_admin = self._authorizer.allows(principal, Permission.MEMBERS_MANAGE)
        records = await self._auth.list_tokens(None if is_admin else principal.actor_id)
        return {"data": records}

    async def revoke_token(self, principal: Principal, token_id: str) -> None:
        is_admin = self._authorizer.allows(principal, Permission.MEMBERS_MANAGE)
        ok = await self._auth.revoke_token(
            token_id, actor_id=None if is_admin else principal.actor_id
        )
        if not ok:
            if not is_admin:
                raise Forbidden("token does not exist or belongs to another actor")
            raise NotFound(f"no active token {token_id}")
