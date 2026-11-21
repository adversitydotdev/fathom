"""The `ogrl` process: token authentication and configuration from the environment."""

import json

from fastapi.testclient import TestClient

from ogrl.api.app import create_app
from ogrl.main import build_from_env

TOKENS = {
    "ogrl_pat_admin": {"actor_id": "party--com.acme.admin", "roles": ["administrator"]},
    "ogrl_pat_bot": {"actor_id": "party--com.acme.bot", "roles": ["agent"], "kind": "agent"},
}


def test_tokens_from_the_environment():
    c = build_from_env({"OGRL_API_TOKENS": json.dumps(TOKENS)})
    client = TestClient(create_app(c))
    assert client.get("/v1/controls").status_code == 401
    bad = client.get("/v1/controls", headers={"Authorization": "Bearer ogrl_pat_nope"})
    assert bad.status_code == 401
    admin = {"Authorization": "Bearer ogrl_pat_admin"}
    party = client.post("/v1/parties", json={"name": "Ops", "kind": "team"}, headers=admin)
    assert party.status_code == 201 and party.json()["created_by_ref"] == "party--com.acme.admin"
    bot = {"Authorization": "Bearer ogrl_pat_bot"}
    revoke = client.post(
        f"/v1/parties/{party.json()['id']}/revoke",
        headers={**bot, "If-Match": party.json()["modified"]},
    )
    assert revoke.status_code == 403


def test_database_and_bucket_from_the_environment():
    from ogrl.adapters.s3 import S3Blobs
    from ogrl.persistence.postgres import PostgresStore

    c = build_from_env(
        {
            "OGRL_DATABASE_URL": "postgresql://u:p@db.example:5432/ogrl",
            "OGRL_S3_BUCKET": "ogrl-123-us-east-1",
        }
    )
    assert isinstance(c.store, PostgresStore)
    assert c.store.engine.url.drivername == "postgresql+asyncpg"
    assert isinstance(c.blobs, S3Blobs)


def test_local_integrations_need_an_explicit_allow(tmp_path):
    from ogrl.adapters.secrets import FileVault
    from tests.conftest import INTEGRATIONS_DIR

    base = {"OGRL_INTEGRATIONS_DIR": str(INTEGRATIONS_DIR)}
    assert build_from_env(base).plugins.integrations.names() == []
    allowed = build_from_env(
        {
            **base,
            "OGRL_ALLOW_LOCAL_INTEGRATIONS": "true",
            "OGRL_SECRETS_FILE": str(tmp_path / "vault.json"),
        }
    )
    assert allowed.plugins.integrations.names() == ["dev.ogrl.fake"]
    vault = allowed.integrations._vault
    assert isinstance(vault, FileVault)
    vault.put("integrations/x/TOKEN", "v")
    assert (tmp_path / "vault.json").stat().st_mode & 0o777 == 0o600
    assert FileVault(tmp_path / "vault.json").get("integrations/x/TOKEN") == "v"
