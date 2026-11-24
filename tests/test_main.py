"""The `fathom` process: token authentication and configuration from the environment."""

import json

from fastapi.testclient import TestClient

from fathom.api.app import create_app
from fathom.main import build_from_env

TOKENS = {
    "fathom_pat_admin": {"actor_id": "party--com.acme.admin", "roles": ["administrator"]},
    "fathom_pat_bot": {"actor_id": "party--com.acme.bot", "roles": ["agent"], "kind": "agent"},
}


def test_tokens_from_the_environment():
    c = build_from_env({"FATHOM_API_TOKENS": json.dumps(TOKENS)})
    client = TestClient(create_app(c))
    assert client.get("/v1/controls").status_code == 401
    bad = client.get("/v1/controls", headers={"Authorization": "Bearer fathom_pat_nope"})
    assert bad.status_code == 401
    admin = {"Authorization": "Bearer fathom_pat_admin"}
    party = client.post("/v1/parties", json={"name": "Ops", "kind": "team"}, headers=admin)
    assert party.status_code == 201 and party.json()["created_by_ref"] == "party--com.acme.admin"
    bot = {"Authorization": "Bearer fathom_pat_bot"}
    revoke = client.post(
        f"/v1/parties/{party.json()['id']}/revoke",
        headers={**bot, "If-Match": party.json()["modified"]},
    )
    assert revoke.status_code == 403


def test_database_and_bucket_from_the_environment():
    from fathom.adapters.s3 import S3Blobs
    from fathom.persistence.postgres import PostgresStore

    c = build_from_env(
        {
            "FATHOM_DATABASE_URL": "postgresql://u:p@db.example:5432/fathom",
            "FATHOM_S3_BUCKET": "fathom-123-us-east-1",
        }
    )
    assert isinstance(c.store, PostgresStore)
    assert c.store.engine.url.drivername == "postgresql+asyncpg"
    assert isinstance(c.blobs, S3Blobs)


def test_local_integrations_need_an_explicit_allow(tmp_path):
    from fathom.adapters.secrets import FileVault
    from tests.conftest import INTEGRATIONS_DIR

    base = {"FATHOM_INTEGRATIONS_DIR": str(INTEGRATIONS_DIR)}
    assert build_from_env(base).plugins.integrations.names() == []
    allowed = build_from_env(
        {
            **base,
            "FATHOM_ALLOW_LOCAL_INTEGRATIONS": "true",
            "FATHOM_SECRETS_FILE": str(tmp_path / "vault.json"),
        }
    )
    assert allowed.plugins.integrations.names() == ["dev.ogrl.fake"]
    vault = allowed.integrations._vault
    assert isinstance(vault, FileVault)
    vault.put("integrations/x/TOKEN", "v")
    assert (tmp_path / "vault.json").stat().st_mode & 0o777 == 0o600
    assert FileVault(tmp_path / "vault.json").get("integrations/x/TOKEN") == "v"


def test_worker_dispatches_collection_jobs(tmp_path):
    import asyncio

    from fathom.main import dispatch_queued_job
    from fathom.operations.integrations import ConnectionWrite, SecretWrite
    from fathom.operations.records import Job
    from tests.conftest import INTEGRATIONS_DIR, PRINCIPALS

    c = build_from_env(
        {
            "FATHOM_INTEGRATIONS_DIR": str(INTEGRATIONS_DIR),
            "FATHOM_ALLOW_LOCAL_INTEGRATIONS": "true",
        }
    )
    admin = PRINCIPALS["administrator"]

    async def scenario() -> int:
        connection = await c.integrations.create_connection(
            admin,
            ConnectionWrite(
                integration_id="dev.ogrl.fake",
                name="fake",
                config={"dataset": "acme"},
                auth_kind="fields",
            ),
        )
        await c.integrations.put_secret(
            admin, connection.id, "FAKE_TOKEN", SecretWrite(value="s3cret")
        )
        job = Job(
            id="job--dispatch",
            type="collection",
            status="queued",
            created="2026-11-21T00:00:00Z",
            request={"connection_id": connection.id, "sources": ["dev.ogrl.fake/users@1"]},
            created_by_ref=admin.actor_id,
        )
        await dispatch_queued_job(c, job)
        await c.jobs._executor.drain()  # BackgroundExecutor
        return len(await c.integrations.list_snapshots(admin, connection.id, None))

    assert asyncio.run(scenario()) == 1


def _providers(cfg: dict, env: dict | None = None):
    from fathom.main import oidc_providers_from_env

    return oidc_providers_from_env(json.dumps(cfg), env or {})


BASE_PROVIDER = {
    "issuer": "https://idp.example",
    "client_id": "cid",
    "redirect_uri": "https://grc.example/v1/auth/oidc/google/callback",
}


def test_oidc_client_secret_from_named_env_var():
    cfg = {"google": {**BASE_PROVIDER, "client_secret_env": "FATHOM_OIDC_CLIENT_SECRET"}}
    providers = _providers(cfg, {"FATHOM_OIDC_CLIENT_SECRET": "from-ssm"})
    assert providers["google"]._client_secret == "from-ssm"
    assert providers["google"]._scopes == "openid email profile"


def test_oidc_client_secret_env_unset_or_empty_fails_startup():
    import pytest

    cfg = {"google": {**BASE_PROVIDER, "client_secret_env": "FATHOM_OIDC_CLIENT_SECRET"}}
    with pytest.raises(ValueError, match="FATHOM_OIDC_CLIENT_SECRET"):
        _providers(cfg, {})
    with pytest.raises(ValueError, match="FATHOM_OIDC_CLIENT_SECRET"):
        _providers(cfg, {"FATHOM_OIDC_CLIENT_SECRET": ""})


def test_oidc_inline_client_secret_and_public_client_still_work():
    cfg = {
        "okta": {**BASE_PROVIDER, "client_secret": "inline", "scopes": "openid"},
        "pub": dict(BASE_PROVIDER),
    }
    providers = _providers(cfg, {"FATHOM_OIDC_CLIENT_SECRET": "ignored"})
    assert providers["okta"]._client_secret == "inline"
    assert providers["okta"]._scopes == "openid"
    assert providers["pub"]._client_secret is None


def test_build_from_env_wires_secret_env_into_the_provider():
    env = {
        "FATHOM_OIDC_PROVIDERS": json.dumps(
            {"google": {**BASE_PROVIDER, "client_secret_env": "S"}}
        ),
        "S": "shh",
    }
    c = build_from_env(env)
    assert c.auth._providers["google"]._client_secret == "shh"


def _person_client(env: dict):
    c = build_from_env({"FATHOM_API_TOKENS": json.dumps(TOKENS), **env})
    return TestClient(create_app(c))


def test_token_minting_allowed_by_default_and_disabled_for_people_by_flag():
    admin = {"Authorization": "Bearer fathom_pat_admin"}
    bot = {"Authorization": "Bearer fathom_pat_bot"}
    body = {"name": "laptop"}
    assert _person_client({}).post("/v1/auth/tokens", json=body, headers=admin).status_code == 201
    off = _person_client({"FATHOM_DISABLE_API_TOKEN_MINTING": "true"})
    assert off.post("/v1/auth/tokens", json=body, headers=admin).status_code == 403
    assert off.post("/v1/auth/tokens", json=body, headers=bot).status_code == 201
    explicit_false = _person_client({"FATHOM_DISABLE_API_TOKEN_MINTING": "false"})
    assert explicit_false.post("/v1/auth/tokens", json=body, headers=admin).status_code == 201
