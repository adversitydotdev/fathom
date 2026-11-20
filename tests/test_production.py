"""Tests for production readiness: /health probe, CloudFormation env vars, SSM, telemetry, SQS."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi.testclient import TestClient

from ogrl import container, telemetry
from ogrl.access import ActorKind, Principal, Role
from ogrl.adapters.queue import MemoryJobQueue
from ogrl.adapters.secrets import EnvSecrets, SsmSecrets
from ogrl.api.app import create_app
from ogrl.main import (
    build_from_env,
    database_url_from_env,
    dispatch_queued_job,
    parse_bind,
)
from ogrl.operations.jobs import QueuedExecutor
from ogrl.operations.library import LibraryPullRequest
from ogrl.persistence.postgres import PostgresStore


def test_root_health_and_v1_health():
    c = build_from_env({})
    client = TestClient(create_app(c))
    root = client.get("/health")
    v1 = client.get("/v1/health")
    assert root.status_code == 200 and root.json() == {"status": "ok", "version": "0.1.0"}
    assert v1.status_code == 200 and v1.json() == {"status": "ok", "version": "0.1.0"}


def test_cloudformation_database_env_components_and_bind():
    env = {
        "OGRL_DATABASE_HOST": "ogrl-db.internal",
        "OGRL_DATABASE_PORT": "5432",
        "OGRL_DATABASE_NAME": "ogrl",
        "OGRL_DATABASE_USER": "ogrl",
        "OGRL_DATABASE_PASSWORD": "secret-pass",
        "OGRL_DATABASE_SSLMODE": "require",
        "OGRL_BIND": "127.0.0.1:9090",
    }
    url = database_url_from_env(env)
    assert url == "postgresql://ogrl:secret-pass@ogrl-db.internal:5432/ogrl?ssl=require"
    assert parse_bind(env) == ("127.0.0.1", 9090)

    c = build_from_env(env)
    assert isinstance(c.store, PostgresStore)
    assert c.store.engine.url.host == "ogrl-db.internal"


def test_ssm_secrets_reads_harness_prefix_with_env_fallback():
    class FakeSsm:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get_parameter(self, Name: str, WithDecryption: bool = True) -> dict:  # noqa: N803
            assert WithDecryption is True
            self.calls.append(Name)
            if Name == "/ogrl/prod/harness/AWS_TOKEN":
                return {"Parameter": {"Value": "from-ssm"}}
            raise KeyError(Name)

    ssm = FakeSsm()
    secrets = SsmSecrets(
        "/ogrl/prod",
        fallback=EnvSecrets({"OGRL_HARNESS_LOCAL_ONLY": "from-env"}),
        client=ssm,
    )
    assert secrets.get("LOCAL_ONLY") == "from-env"
    assert secrets.get("AWS_TOKEN") == "from-ssm"
    assert secrets.get("MISSING") is None
    assert "/ogrl/prod/harness/AWS_TOKEN" in ssm.calls


def test_structured_json_telemetry_formatter():
    mode = telemetry.configure({}, force=True)
    assert mode == "json"
    fmt = telemetry.JsonLogFormatter()
    record = logging.LogRecord(
        name="ogrl.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    parsed = json.loads(fmt.format(record))
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "ogrl.test"
    assert parsed["message"] == "hello world"
    assert parsed["timestamp"].endswith("Z")


def test_queued_executor_and_worker_dispatch(library_dir):
    from ogrl.adapters.library import DirectoryLibrary

    queue = MemoryJobQueue()
    api_c = container.build(
        authenticator=build_from_env({}).authenticator,
        executor=QueuedExecutor(queue),
        queue=queue,
        library_source=DirectoryLibrary(library_dir),
    )
    worker_c = container.build(
        authenticator=api_c.authenticator,
        store=api_c.store,
        blobs=api_c.blobs,
        library_source=DirectoryLibrary(library_dir),
    )
    admin = Principal(
        "party--com.acme.admin", "organization", ActorKind.PERSON, frozenset({Role.ADMINISTRATOR})
    )

    async def scenario():
        queued = await api_c.library.pull(admin, LibraryPullRequest(version="0.1.0"))
        assert queued.status == "queued"
        msgs = await queue.receive()
        assert len(msgs) == 1 and msgs[0].job_id == queued.id
        held = await worker_c.store.get_job(msgs[0].job_id)
        assert held is not None
        await dispatch_queued_job(worker_c, held)
        pin = await worker_c.store.library_pin()
        return pin

    pin = asyncio.run(scenario())
    assert pin is not None and pin.version == "0.1.0"
