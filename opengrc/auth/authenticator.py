"""Authentication behind an interface.

The API owns identity. The browser holds an opaque session in an HttpOnly,
same-origin cookie (the Next.js server forwards /v1 to this process, so the
cookie is first-party). The CLI, CI, and agents send `Authorization: Bearer`
with an API token. Both resolve to the same `Principal`, and roles are read
from the live membership on every request, never from the token.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from opengrc.access import Principal
from opengrc.errors import Unauthenticated

SESSION_COOKIE = "__Host-opengrc_session"
API_TOKEN_PREFIX = "ogrc_pat_"


@dataclass(frozen=True, slots=True)
class Credentials:
    bearer: str | None = None
    session: str | None = None


def digest(secret: str) -> str:
    """Tokens are 256-bit random values, so an unsalted SHA-256 is the lookup key."""
    return hashlib.sha256(secret.encode()).hexdigest()


class Authenticator(Protocol):
    async def authenticate(self, credentials: Credentials) -> Principal | None:
        """None: these credentials are not mine. Raise Unauthenticated: they are, and invalid."""
        ...


class Memberships(Protocol):
    async def principal(self, actor_id: str) -> Principal | None: ...


class SessionStore(Protocol):
    async def actor_for_session(self, session_digest: str) -> str | None:
        """Live, unexpired session only. Sliding expiry is the store's business."""
        ...


class TokenStore(Protocol):
    async def actor_for_token(self, token_digest: str) -> str | None: ...


class SessionAuthenticator:
    def __init__(self, sessions: SessionStore, memberships: Memberships) -> None:
        self._sessions = sessions
        self._memberships = memberships

    async def authenticate(self, credentials: Credentials) -> Principal | None:
        if credentials.session is None:
            return None
        actor_id = await self._sessions.actor_for_session(digest(credentials.session))
        return await _resolve(actor_id, self._memberships)


class ApiTokenAuthenticator:
    def __init__(self, tokens: TokenStore, memberships: Memberships) -> None:
        self._tokens = tokens
        self._memberships = memberships

    async def authenticate(self, credentials: Credentials) -> Principal | None:
        token = credentials.bearer
        if token is None or not token.startswith(API_TOKEN_PREFIX):
            return None
        actor_id = await self._tokens.actor_for_token(digest(token))
        return await _resolve(actor_id, self._memberships)


class ChainAuthenticator:
    """First authenticator that recognises the credentials wins."""

    def __init__(self, authenticators: Sequence[Authenticator]) -> None:
        self._authenticators = authenticators

    async def authenticate(self, credentials: Credentials) -> Principal | None:
        for authenticator in self._authenticators:
            principal = await authenticator.authenticate(credentials)
            if principal is not None:
                return principal
        return None


async def _resolve(actor_id: str | None, memberships: Memberships) -> Principal:
    if actor_id is None:
        raise Unauthenticated("session or token is unknown or expired")
    principal = await memberships.principal(actor_id)
    if principal is None:
        raise Unauthenticated("actor is no longer a member")
    return principal
