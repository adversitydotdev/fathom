"""OIDC sign-in: PKCE S256 + state + nonce + JWKS ID token verification.

Flow, all on the API so it stays the only writer of the database:

    GET  /v1/auth/oidc/{provider}/begin     -> 302 to the IdP (PKCE + state + nonce)
    GET  /v1/auth/oidc/{provider}/callback  -> verify, upsert the person's party,
                                               create a session row, set
                                               __Host-fathom_session, 302 to the app
    GET  /v1/auth/session                   -> who am I (Next.js middleware calls this)
    POST /v1/auth/logout                    -> revoke the session row, clear the cookie
    POST /v1/auth/tokens                    -> mint an API token for the CLI or an agent

Works against Okta, Entra, Google, or Keycloak via standard OIDC discovery.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx
from joserfc import jwt
from joserfc.jwk import KeySet

from fathom.errors import Unauthenticated
from fathom.kernel.timeutil import now, utc


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    issuer: str
    subject: str
    email: str | None = None
    name: str | None = None


class IdentityProvider(Protocol):
    name: str

    async def authorization_url(self, state: str, nonce: str, code_verifier: str) -> str: ...

    async def exchange(self, code: str, code_verifier: str, nonce: str) -> VerifiedIdentity: ...


def pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@dataclass(frozen=True, slots=True)
class PendingAuth:
    provider: str
    code_verifier: str
    nonce: str
    redirect_to: str
    expires_at: datetime


class OidcStateStore:
    """Short-lived state/PKCE/nonce store for in-flight OIDC handshakes."""

    def __init__(
        self,
        clock: Callable[[], datetime] = now,
        ttl: timedelta = timedelta(minutes=10),
    ) -> None:
        self._clock = clock
        self._ttl = ttl
        self._pending: dict[str, PendingAuth] = {}

    def issue(self, provider: str, redirect_to: str = "/") -> tuple[str, PendingAuth]:
        state = secrets.token_urlsafe(24)
        pending = PendingAuth(
            provider=provider,
            code_verifier=secrets.token_urlsafe(48),
            nonce=secrets.token_urlsafe(24),
            redirect_to=redirect_to,
            expires_at=utc(self._clock()) + self._ttl,
        )
        self._pending[state] = pending
        return state, pending

    def consume(self, state: str, provider: str) -> PendingAuth:
        pending = self._pending.pop(state, None)
        if pending is None or pending.provider != provider:
            raise Unauthenticated("OIDC state is missing or invalid")
        if pending.expires_at <= utc(self._clock()):
            raise Unauthenticated("OIDC login timed out; try again")
        return pending


class OidcProvider:
    """Standard OIDC Authorization Code + PKCE S256 client backed by Authlib + httpx."""

    def __init__(
        self,
        *,
        name: str,
        issuer: str,
        client_id: str,
        client_secret: str | None = None,
        redirect_uri: str,
        scopes: str = "openid email profile",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.name = name
        self._issuer = issuer.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._scopes = scopes
        self._http = http_client
        self._metadata: dict[str, Any] | None = None
        self._jwks: Any | None = None

    async def _fetch_json(self, url: str) -> dict[str, Any]:
        if self._http is not None:
            resp = await self._http.get(url, timeout=10.0)
            resp.raise_for_status()
            return resp.json()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()

    async def _discover(self) -> dict[str, Any]:
        if self._metadata is None:
            self._metadata = await self._fetch_json(
                f"{self._issuer}/.well-known/openid-configuration"
            )
        return self._metadata

    async def _key_set(self) -> KeySet:
        meta = await self._discover()
        if self._jwks is None:
            jwks_data = await self._fetch_json(meta["jwks_uri"])
            self._jwks = KeySet.import_key_set(jwks_data)
        return self._jwks

    async def authorization_url(self, state: str, nonce: str, code_verifier: str) -> str:
        meta = await self._discover()
        params = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "scope": self._scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": pkce_challenge(code_verifier),
            "code_challenge_method": "S256",
        }
        return f"{meta['authorization_endpoint']}?{urlencode(params)}"

    async def exchange(self, code: str, code_verifier: str, nonce: str) -> VerifiedIdentity:
        meta = await self._discover()
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._redirect_uri,
            "client_id": self._client_id,
            "code_verifier": code_verifier,
        }
        if self._client_secret:
            data["client_secret"] = self._client_secret

        if self._http is not None:
            resp = await self._http.post(meta["token_endpoint"], data=data, timeout=10.0)
        else:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(meta["token_endpoint"], data=data)
        if resp.status_code >= 400:
            raise Unauthenticated("OIDC token exchange failed")
        tokens = resp.json()
        id_token = tokens.get("id_token")
        if not id_token:
            raise Unauthenticated("OIDC response did not include an id_token")

        key_set = await self._key_set()
        try:
            token = jwt.decode(id_token, key_set)
            registry = jwt.JWTClaimsRegistry(
                iss={"essential": True, "value": meta.get("issuer", self._issuer)},
                aud={"essential": True, "value": self._client_id},
                sub={"essential": True},
                nonce={"essential": True, "value": nonce},
            )
            registry.validate(token.claims)
            claims = token.claims
        except Exception as exc:
            raise Unauthenticated(f"invalid OIDC id_token: {exc}") from exc

        return VerifiedIdentity(
            issuer=str(claims["iss"]),
            subject=str(claims["sub"]),
            email=claims.get("email"),
            name=claims.get("name") or claims.get("preferred_username"),
        )
