"""Tests for OIDC PKCE sign-in, cookie sessions, CSRF origin checks, and minted API tokens."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from ogrl import container
from ogrl.access import ActorKind, Principal, Role
from ogrl.api.app import create_app
from ogrl.auth import SESSION_COOKIE
from ogrl.auth.oidc import VerifiedIdentity, pkce_challenge
from ogrl.auth.store import MemoryAuthStore, PostgresAuthStore
from ogrl.main import authenticator_from
from tests.conftest import postgres_store, services_available


class FakeOidcProvider:
    name = "okta"

    def __init__(self, identity: VerifiedIdentity) -> None:
        self._identity = identity
        self.last_challenge: str | None = None
        self.last_nonce: str | None = None

    async def authorization_url(self, state: str, nonce: str, code_verifier: str) -> str:
        self.last_challenge = pkce_challenge(code_verifier)
        self.last_nonce = nonce
        return (
            f"https://idp.example/authorize?state={state}&nonce={nonce}"
            f"&code_challenge={self.last_challenge}&code_challenge_method=S256"
        )

    async def exchange(self, code: str, code_verifier: str, nonce: str) -> VerifiedIdentity:
        assert code == "good-code"
        assert pkce_challenge(code_verifier) == self.last_challenge
        assert nonce == self.last_nonce
        return self._identity


def _make_auth_client(
    *,
    email: str = "alice@acme.example",
    bootstrap_admins: frozenset[str] = frozenset({"alice@acme.example"}),
) -> tuple[TestClient, container.Container]:
    auth_store = MemoryAuthStore()
    provider = FakeOidcProvider(
        VerifiedIdentity(
            issuer="https://idp.example",
            subject="sub-alice-123",
            email=email,
            name="Alice Example",
        )
    )
    c = container.build(
        authenticator=authenticator_from("", auth_store=auth_store),
        auth_store=auth_store,
        oidc_providers={"okta": provider},
        bootstrap_admin_emails=bootstrap_admins,
        allowed_origins=("https://app.acme.example",),
    )
    return TestClient(create_app(c), follow_redirects=False), c


def test_oidc_pkce_login_session_csrf_and_logout():
    client, _ = _make_auth_client()

    begin = client.get("/v1/auth/oidc/okta/begin?redirect_to=/controls")
    assert begin.status_code == 302
    loc = urlparse(begin.headers["location"])
    qs = parse_qs(loc.query)
    assert qs["code_challenge_method"] == ["S256"]
    state = qs["state"][0]

    cb = client.get(f"/v1/auth/oidc/okta/callback?code=good-code&state={state}")
    assert cb.status_code == 302
    assert cb.headers["location"] == "/controls"
    assert SESSION_COOKIE in cb.cookies

    me = client.get("/v1/auth/session")
    assert me.status_code == 200
    data = me.json()
    assert data["actor_id"].startswith("party--")
    assert data["roles"] == ["administrator"]
    assert "members:manage" in data["permissions"]

    # Cookie-authenticated unsafe requests require a matching Origin (CSRF guard)
    no_origin = client.post("/v1/parties", json={"name": "SecOps", "kind": "team"})
    assert no_origin.status_code == 403
    assert no_origin.json()["type"] == "urn:ogrl:problem:csrf"

    evil_origin = client.post(
        "/v1/parties",
        json={"name": "SecOps", "kind": "team"},
        headers={"Origin": "https://evil.example"},
    )
    assert evil_origin.status_code == 403

    good_origin = client.post(
        "/v1/parties",
        json={"name": "SecOps", "kind": "team"},
        headers={"Origin": "http://testserver"},
    )
    assert good_origin.status_code == 201

    allowed_origin = client.post(
        "/v1/auth/logout",
        headers={"Origin": "https://app.acme.example"},
    )
    assert allowed_origin.status_code == 204
    assert client.get("/v1/auth/session").status_code == 401


def test_mint_use_list_and_revoke_api_tokens():
    client, c = _make_auth_client()
    # Seed an admin session via OIDC
    begin = client.get("/v1/auth/oidc/okta/begin")
    state = parse_qs(urlparse(begin.headers["location"]).query)["state"][0]
    client.get(f"/v1/auth/oidc/okta/callback?code=good-code&state={state}")

    # Mint a personal CLI token
    minted = client.post(
        "/v1/auth/tokens",
        json={"name": "laptop-cli", "expires_in_days": 30},
        headers={"Origin": "http://testserver"},
    )
    assert minted.status_code == 201
    pat = minted.json()["token"]
    rec = minted.json()["record"]
    assert pat.startswith("ogrl_pat_")

    # Mint an agent token (admin only)
    agent_minted = client.post(
        "/v1/auth/tokens",
        json={
            "name": "ci-agent",
            "actor_id": "party--com.acme.bot",
            "actor_kind": "agent",
            "roles": ["agent"],
        },
        headers={"Origin": "http://testserver"},
    )
    assert agent_minted.status_code == 201
    agent_pat = agent_minted.json()["token"]

    # Fresh client (no cookie) authenticates with minted Bearer token without needing Origin header
    bearer_client = TestClient(create_app(c))
    who = bearer_client.get("/v1/auth/session", headers={"Authorization": f"Bearer {pat}"})
    assert who.status_code == 200 and who.json()["roles"] == ["administrator"]

    who_agent = bearer_client.get(
        "/v1/auth/session", headers={"Authorization": f"Bearer {agent_pat}"}
    )
    assert who_agent.status_code == 200
    assert who_agent.json()["kind"] == "agent"
    assert who_agent.json()["roles"] == ["agent"]

    listed = bearer_client.get("/v1/auth/tokens", headers={"Authorization": f"Bearer {pat}"})
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 2
    assert "token" not in listed.json()["data"][0]

    revoked = bearer_client.post(
        f"/v1/auth/tokens/{rec['id']}/revoke",
        headers={"Authorization": f"Bearer {pat}"},
    )
    assert revoked.status_code == 204
    assert (
        bearer_client.get(
            "/v1/auth/session", headers={"Authorization": f"Bearer {pat}"}
        ).status_code
        == 401
    )


@pytest.mark.skipif(
    not services_available(), reason="the compose stack is not running (docker compose up -d)"
)
def test_postgres_auth_store_roundtrip():
    pg = postgres_store()
    auth_store = PostgresAuthStore(pg.engine)

    async def scenario() -> tuple[Principal | None, str | None, str | None, int]:
        await auth_store.upsert_identity(
            "party--com.acme.pguser",
            kind=ActorKind.PERSON,
            roles=[Role.CONTRIBUTOR],
            issuer="https://idp.example",
            subject="pg-sub-1",
            email="pg@acme.example",
        )
        principal = await auth_store.principal("party--com.acme.pguser")
        secret, _ = await auth_store.create_session("party--com.acme.pguser")
        from ogrl.auth.authenticator import digest

        session_actor = await auth_store.actor_for_session(digest(secret))
        await auth_store.revoke_session(digest(secret))
        assert await auth_store.actor_for_session(digest(secret)) is None

        rec, pat = await auth_store.create_token(
            "party--com.acme.pguser",
            "pg-cli",
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        token_actor = await auth_store.actor_for_token(digest(pat))
        tokens = await auth_store.list_tokens("party--com.acme.pguser")
        await auth_store.revoke_token(rec.id, actor_id="party--com.acme.pguser")
        assert await auth_store.actor_for_token(digest(pat)) is None
        return principal, session_actor, token_actor, len(tokens)

    principal, session_actor, token_actor, count = asyncio.run(scenario())
    assert principal is not None and Role.CONTRIBUTOR in principal.roles
    assert session_actor == "party--com.acme.pguser"
    assert token_actor == "party--com.acme.pguser"
    assert count == 1
