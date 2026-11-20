"""Persistent auth store for OIDC identities, browser sessions, and minted API tokens."""

from __future__ import annotations

import secrets
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from pydantic import BaseModel
from sqlalchemy import and_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from ogrl.access import ActorKind, Principal, Role
from ogrl.auth.authenticator import API_TOKEN_PREFIX, Memberships, SessionStore, TokenStore, digest
from ogrl.kernel import ids
from ogrl.kernel.timeutil import now, utc
from ogrl.persistence.tables import auth_identities, auth_sessions, auth_tokens

ORGANIZATION = "organization"
DEFAULT_SESSION_TTL = timedelta(days=7)


class TokenRecord(BaseModel):
    """Metadata for a minted API token (plaintext is only returned once at creation)."""

    id: str
    actor_id: str
    name: str
    created_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    created_by_ref: str | None = None


@dataclass(frozen=True, slots=True)
class IdentityRecord:
    actor_id: str
    issuer: str | None
    subject: str | None
    email: str | None
    kind: ActorKind
    roles: frozenset[Role]


class AuthStore(SessionStore, TokenStore, Memberships, Protocol):
    """Combined identity, session, and API token repository."""

    async def lookup_oidc(self, issuer: str, subject: str) -> IdentityRecord | None: ...

    async def upsert_identity(
        self,
        actor_id: str,
        *,
        kind: ActorKind = ActorKind.PERSON,
        roles: Iterable[Role] = (Role.VIEWER,),
        issuer: str | None = None,
        subject: str | None = None,
        email: str | None = None,
    ) -> IdentityRecord: ...

    async def create_session(
        self, actor_id: str, *, ttl: timedelta = DEFAULT_SESSION_TTL
    ) -> tuple[str, datetime]: ...

    async def revoke_session(self, session_digest: str) -> bool: ...

    async def create_token(
        self,
        actor_id: str,
        name: str,
        *,
        created_by_ref: str | None = None,
        expires_at: datetime | None = None,
    ) -> tuple[TokenRecord, str]: ...

    async def list_tokens(self, actor_id: str | None = None) -> list[TokenRecord]: ...

    async def revoke_token(self, token_id: str, *, actor_id: str | None = None) -> bool: ...


def _new_secret() -> str:
    return secrets.token_urlsafe(32)


def _new_pat() -> str:
    return API_TOKEN_PREFIX + secrets.token_urlsafe(32)


class MemoryAuthStore:
    """In-memory AuthStore for tests and ephemeral local runs."""

    def __init__(self, clock: Callable[[], datetime] = now) -> None:
        self._clock = clock
        self._identities: dict[str, IdentityRecord] = {}
        self._oidc: dict[tuple[str, str], str] = {}
        self._sessions: dict[str, tuple[str, datetime, datetime | None]] = {}
        self._tokens: dict[str, TokenRecord] = {}
        self._token_by_id: dict[str, str] = {}

    async def principal(self, actor_id: str) -> Principal | None:
        rec = self._identities.get(actor_id)
        if rec is None:
            return None
        return Principal(rec.actor_id, ORGANIZATION, rec.kind, rec.roles)

    async def lookup_oidc(self, issuer: str, subject: str) -> IdentityRecord | None:
        actor_id = self._oidc.get((issuer, subject))
        return self._identities.get(actor_id) if actor_id else None

    async def upsert_identity(
        self,
        actor_id: str,
        *,
        kind: ActorKind = ActorKind.PERSON,
        roles: Iterable[Role] = (Role.VIEWER,),
        issuer: str | None = None,
        subject: str | None = None,
        email: str | None = None,
    ) -> IdentityRecord:
        rec = IdentityRecord(
            actor_id=actor_id,
            issuer=issuer,
            subject=subject,
            email=email,
            kind=kind,
            roles=frozenset(roles),
        )
        self._identities[actor_id] = rec
        if issuer and subject:
            self._oidc[(issuer, subject)] = actor_id
        return rec

    async def create_session(
        self, actor_id: str, *, ttl: timedelta = DEFAULT_SESSION_TTL
    ) -> tuple[str, datetime]:
        secret = _new_secret()
        expires = utc(self._clock()) + ttl
        self._sessions[digest(secret)] = (actor_id, expires, None)
        return secret, expires

    async def actor_for_session(self, session_digest: str) -> str | None:
        entry = self._sessions.get(session_digest)
        if entry is None:
            return None
        actor_id, expires, revoked = entry
        if revoked is not None or expires <= utc(self._clock()):
            return None
        return actor_id

    async def revoke_session(self, session_digest: str) -> bool:
        entry = self._sessions.get(session_digest)
        if entry is None or entry[2] is not None:
            return False
        self._sessions[session_digest] = (entry[0], entry[1], utc(self._clock()))
        return True

    async def create_token(
        self,
        actor_id: str,
        name: str,
        *,
        created_by_ref: str | None = None,
        expires_at: datetime | None = None,
    ) -> tuple[TokenRecord, str]:
        plaintext = _new_pat()
        token_digest = digest(plaintext)
        rec = TokenRecord(
            id=ids.mint("token"),
            actor_id=actor_id,
            name=name,
            created_at=utc(self._clock()),
            expires_at=utc(expires_at) if expires_at is not None else None,
            created_by_ref=created_by_ref,
        )
        self._tokens[token_digest] = rec
        self._token_by_id[rec.id] = token_digest
        return rec, plaintext

    async def actor_for_token(self, token_digest: str) -> str | None:
        rec = self._tokens.get(token_digest)
        if rec is None or rec.revoked_at is not None:
            return None
        if rec.expires_at is not None and rec.expires_at <= utc(self._clock()):
            return None
        return rec.actor_id

    async def list_tokens(self, actor_id: str | None = None) -> list[TokenRecord]:
        items = [
            rec for rec in self._tokens.values() if actor_id is None or rec.actor_id == actor_id
        ]
        return sorted(items, key=lambda r: (r.created_at, r.id))

    async def revoke_token(self, token_id: str, *, actor_id: str | None = None) -> bool:
        token_digest = self._token_by_id.get(token_id)
        if token_digest is None:
            return False
        rec = self._tokens[token_digest]
        if actor_id is not None and rec.actor_id != actor_id:
            return False
        if rec.revoked_at is not None:
            return False
        self._tokens[token_digest] = rec.model_copy(update={"revoked_at": utc(self._clock())})
        return True


class PostgresAuthStore:
    """PostgreSQL-backed AuthStore sharing the application's AsyncEngine."""

    def __init__(self, engine: AsyncEngine, clock: Callable[[], datetime] = now) -> None:
        self._engine = engine
        self._clock = clock

    @staticmethod
    def _identity(row: object) -> IdentityRecord:
        return IdentityRecord(
            actor_id=row.actor_id,  # type: ignore[attr-defined]
            issuer=row.issuer,  # type: ignore[attr-defined]
            subject=row.subject,  # type: ignore[attr-defined]
            email=row.email,  # type: ignore[attr-defined]
            kind=ActorKind(row.kind),  # type: ignore[attr-defined]
            roles=frozenset(Role(r) for r in row.roles),  # type: ignore[attr-defined]
        )

    async def principal(self, actor_id: str) -> Principal | None:
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(
                    select(auth_identities).where(auth_identities.c.actor_id == actor_id)
                )
            ).first()
        if row is None:
            return None
        rec = self._identity(row)
        return Principal(rec.actor_id, ORGANIZATION, rec.kind, rec.roles)

    async def lookup_oidc(self, issuer: str, subject: str) -> IdentityRecord | None:
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(
                    select(auth_identities).where(
                        and_(
                            auth_identities.c.issuer == issuer,
                            auth_identities.c.subject == subject,
                        )
                    )
                )
            ).first()
        return self._identity(row) if row is not None else None

    async def upsert_identity(
        self,
        actor_id: str,
        *,
        kind: ActorKind = ActorKind.PERSON,
        roles: Iterable[Role] = (Role.VIEWER,),
        issuer: str | None = None,
        subject: str | None = None,
        email: str | None = None,
    ) -> IdentityRecord:
        stamp = utc(self._clock())
        role_values = sorted({Role(r).value for r in roles})
        stmt = (
            insert(auth_identities)
            .values(
                actor_id=actor_id,
                issuer=issuer,
                subject=subject,
                email=email,
                kind=kind.value,
                roles=role_values,
                created_at=stamp,
                updated_at=stamp,
            )
            .on_conflict_do_update(
                index_elements=[auth_identities.c.actor_id],
                set_={
                    "issuer": issuer,
                    "subject": subject,
                    "email": email,
                    "kind": kind.value,
                    "roles": role_values,
                    "updated_at": stamp,
                },
            )
        )
        async with self._engine.begin() as conn:
            await conn.execute(stmt)
        return IdentityRecord(
            actor_id=actor_id,
            issuer=issuer,
            subject=subject,
            email=email,
            kind=kind,
            roles=frozenset(Role(r) for r in role_values),
        )

    async def create_session(
        self, actor_id: str, *, ttl: timedelta = DEFAULT_SESSION_TTL
    ) -> tuple[str, datetime]:
        secret = _new_secret()
        stamp = utc(self._clock())
        expires = stamp + ttl
        async with self._engine.begin() as conn:
            await conn.execute(
                insert(auth_sessions).values(
                    token_digest=digest(secret),
                    actor_id=actor_id,
                    created_at=stamp,
                    expires_at=expires,
                )
            )
        return secret, expires

    async def actor_for_session(self, session_digest: str) -> str | None:
        stamp = utc(self._clock())
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(
                    select(auth_sessions.c.actor_id).where(
                        and_(
                            auth_sessions.c.token_digest == session_digest,
                            auth_sessions.c.revoked_at.is_(None),
                            auth_sessions.c.expires_at > stamp,
                        )
                    )
                )
            ).first()
        return row.actor_id if row is not None else None

    async def revoke_session(self, session_digest: str) -> bool:
        stamp = utc(self._clock())
        async with self._engine.begin() as conn:
            res = await conn.execute(
                update(auth_sessions)
                .where(
                    and_(
                        auth_sessions.c.token_digest == session_digest,
                        auth_sessions.c.revoked_at.is_(None),
                    )
                )
                .values(revoked_at=stamp)
            )
        return bool(res.rowcount)

    async def create_token(
        self,
        actor_id: str,
        name: str,
        *,
        created_by_ref: str | None = None,
        expires_at: datetime | None = None,
    ) -> tuple[TokenRecord, str]:
        plaintext = _new_pat()
        stamp = utc(self._clock())
        exp = utc(expires_at) if expires_at is not None else None
        token_id = ids.mint("token")
        async with self._engine.begin() as conn:
            await conn.execute(
                insert(auth_tokens).values(
                    token_digest=digest(plaintext),
                    id=token_id,
                    actor_id=actor_id,
                    name=name,
                    created_by_ref=created_by_ref,
                    created_at=stamp,
                    expires_at=exp,
                )
            )
        return (
            TokenRecord(
                id=token_id,
                actor_id=actor_id,
                name=name,
                created_at=stamp,
                expires_at=exp,
                created_by_ref=created_by_ref,
            ),
            plaintext,
        )

    async def actor_for_token(self, token_digest: str) -> str | None:
        stamp = utc(self._clock())
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    select(auth_tokens.c.actor_id, auth_tokens.c.expires_at).where(
                        and_(
                            auth_tokens.c.token_digest == token_digest,
                            auth_tokens.c.revoked_at.is_(None),
                        )
                    )
                )
            ).first()
            if row is None:
                return None
            if row.expires_at is not None and row.expires_at <= stamp:
                return None
            await conn.execute(
                update(auth_tokens)
                .where(auth_tokens.c.token_digest == token_digest)
                .values(last_used_at=stamp)
            )
        return row.actor_id

    async def list_tokens(self, actor_id: str | None = None) -> list[TokenRecord]:
        stmt = select(auth_tokens).order_by(auth_tokens.c.created_at, auth_tokens.c.id)
        if actor_id is not None:
            stmt = stmt.where(auth_tokens.c.actor_id == actor_id)
        async with self._engine.connect() as conn:
            rows = (await conn.execute(stmt)).all()
        return [
            TokenRecord(
                id=r.id,
                actor_id=r.actor_id,
                name=r.name,
                created_at=r.created_at,
                expires_at=r.expires_at,
                revoked_at=r.revoked_at,
                created_by_ref=r.created_by_ref,
            )
            for r in rows
        ]

    async def revoke_token(self, token_id: str, *, actor_id: str | None = None) -> bool:
        stamp = utc(self._clock())
        conds = [auth_tokens.c.id == token_id, auth_tokens.c.revoked_at.is_(None)]
        if actor_id is not None:
            conds.append(auth_tokens.c.actor_id == actor_id)
        async with self._engine.begin() as conn:
            res = await conn.execute(
                update(auth_tokens).where(and_(*conds)).values(revoked_at=stamp)
            )
        return bool(res.rowcount)


class CompositeMemberships:
    """Checks multiple membership sources in order (e.g., DB identities, then static env tokens)."""

    def __init__(self, sources: Sequence[Memberships]) -> None:
        self._sources = sources

    async def principal(self, actor_id: str) -> Principal | None:
        for source in self._sources:
            principal = await source.principal(actor_id)
            if principal is not None:
                return principal
        return None


class CompositeTokenStore:
    """Checks multiple token stores in order (e.g., static bootstrap tokens, then DB tokens)."""

    def __init__(self, sources: Sequence[TokenStore]) -> None:
        self._sources = sources

    async def actor_for_token(self, token_digest: str) -> str | None:
        for source in self._sources:
            actor_id = await source.actor_for_token(token_digest)
            if actor_id is not None:
                return actor_id
        return None
