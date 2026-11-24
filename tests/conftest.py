"""Shared fixtures: a small library on disk, principals per role, and an API client."""

import asyncio
import os
import uuid
from collections.abc import Callable, Iterator
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from fathom import container
from fathom.access import ActorKind, Principal, Role
from fathom.adapters.library import DirectoryLibrary
from fathom.adapters.secrets import StaticSecrets
from fathom.api.app import create_app
from fathom.auth import Credentials
from fathom.operations.exports import ExportSettings
from fathom.persistence.memory import MemoryBlobs, MemoryStore

# The compose stack (compose.yaml). Override to point the suite somewhere else.
DATABASE_URL = os.environ.get(
    "FATHOM_TEST_DATABASE_URL", "postgresql://fathom:fathom@localhost:5432/fathom"
)
S3_ENDPOINT = os.environ.get("FATHOM_TEST_S3_ENDPOINT", "http://localhost:8333")
S3_BUCKET = os.environ.get("FATHOM_TEST_S3_BUCKET", "fathom")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "fathom")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "fathom-secret")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
SCHEMAS: list[str] = []


@cache
def services_available() -> bool:
    import asyncpg

    async def ping() -> None:
        from fathom.persistence.postgres import async_url

        url = async_url(DATABASE_URL).replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(url, timeout=2)
        await conn.close()

    try:
        asyncio.run(ping())
        return True
    except Exception:
        return False


def postgres_store():
    """A store in a fresh schema, so each test (and each app in one test) is its own database."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from fathom.persistence.postgres import PostgresStore, async_url
    from fathom.persistence.tables import metadata

    schema = f"test_{uuid.uuid4().hex[:12]}"
    SCHEMAS.append(schema)
    # NullPool: TestClient may run requests on more than one event loop.
    engine = create_async_engine(
        async_url(DATABASE_URL),
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema}},
    )

    async def create() -> None:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            await conn.run_sync(metadata.create_all)
            await conn.execute(text("INSERT INTO store_state (id, version) VALUES (1, 0)"))

    asyncio.run(create())
    return PostgresStore(engine=engine)


INTEGRATIONS_DIR = Path(__file__).parent / "integrations"


def connection_store(store: Any) -> Any:
    from fathom.persistence.memory import MemoryConnections
    from fathom.persistence.postgres import PostgresConnections, PostgresStore

    if isinstance(store, PostgresStore):
        return PostgresConnections(store.engine)
    return MemoryConnections()


def s3_blobs():
    from fathom.adapters.s3 import S3Blobs

    return S3Blobs(S3_BUCKET, prefix=f"test-{uuid.uuid4().hex[:12]}", endpoint_url=S3_ENDPOINT)


@pytest.fixture(scope="session", autouse=True)
def drop_test_schemas() -> Iterator[None]:
    yield
    if not SCHEMAS:
        return
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from fathom.persistence.postgres import async_url

    async def drop() -> None:
        engine = create_async_engine(async_url(DATABASE_URL))
        async with engine.begin() as conn:
            for schema in SCHEMAS:
                await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()

    asyncio.run(drop())


@pytest.fixture(params=["memory", "postgres"])
def backend(request: pytest.FixtureRequest) -> str:
    if request.param == "postgres" and not services_available():
        pytest.skip("the compose stack is not running (docker compose up -d)")
    return request.param


STAMP = "2026-10-22T11:30:00Z"
FW = "framework--nist-sp-800-53-r5"
AC2 = "requirement--nist-sp-800-53-r5-ac-2"
AC3 = "requirement--nist-sp-800-53-r5-ac-3"
C1 = "control--ogrl-ac-01"
C2 = "control--ogrl-ac-02"
LIB_TEST = "test--ogrl-ac-01-unique-idp-users"
LIB_BASELINE = "baseline--ogrl-ac"


def library_objects() -> list[dict[str, Any]]:
    env = {"spec_version": "0.1.0", "created": STAMP, "modified": STAMP}
    return [
        {
            "type": "framework",
            "id": FW,
            **env,
            "name": "NIST SP 800-53 Revision 5",
            "publisher": "NIST",
            "version": "5.2.0",
            "reproduction": "permitted",
            "source": {
                "format": "oscal-catalog",
                "uri": "https://github.com/usnistgov/oscal-content",
                "path": "nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json",
                "commit": "f0de6d8",
            },
        },
        {
            "type": "requirement",
            "id": AC2,
            **env,
            "display_id": "AC-2",
            "name": "Account Management",
            "framework_ref": FW,
            "class": "control",
            "parameters": {"ac_02_odp_10": {"label": "frequency"}},
            "parts": [
                {"id": "a", "statement": "Define account types."},
                {"id": "j", "statement": "Review accounts {{ ac_02_odp_10 }}."},
            ],
            "objectives": [{"id": "a", "statement": "Determine if account types are defined."}],
        },
        {
            "type": "requirement",
            "id": AC3,
            **env,
            "display_id": "AC-3",
            "name": "Access Enforcement",
            "framework_ref": FW,
            "class": "control",
        },
        {
            "type": "control",
            "id": C1,
            **env,
            "display_id": "OGRL-AC-01",
            "name": "Unique identities",
            "origin": "standard",
            "family": "ac",
            "statement": "Each user has a unique identity, reviewed {{ shared_account_review }}.",
            "objective": "Every account traces to one owner.",
            "parameters": {"shared_account_review": {"label": "review", "value": "quarterly"}},
        },
        {
            "type": "control",
            "id": C2,
            **env,
            "display_id": "OGRL-AC-02",
            "name": "Access reviews",
            "origin": "standard",
            "family": "ac",
            "statement": "Accounts are reviewed.",
            "objective": "Stale access is removed.",
            "parameters": {"access_review_frequency": {"label": "how often", "value": "monthly"}},
        },
        {
            "type": "mapping",
            "id": "mapping--ogrl-ac-01_to_nist-sp-800-53-r5-ac-2_part_a",
            **env,
            "source_ref": C1,
            "target_ref": f"{AC2}#a",
            "relationship": "equal-to",
            "rationale": "functional",
            "review_status": "reviewed",
        },
        {
            "type": "mapping",
            "id": "mapping--ogrl-ac-02_to_nist-sp-800-53-r5-ac-2_part_j",
            **env,
            "source_ref": C2,
            "target_ref": f"{AC2}#j",
            "relationship": "subset-of",
            "rationale": "functional",
            "review_status": "draft",
            "parameter_map": {"ac_02_odp_10": "access_review_frequency"},
        },
        {
            "type": "mapping",
            "id": "mapping--ogrl-ac-02_to_nist-sp-800-53-r5-ac-3",
            **env,
            "source_ref": C2,
            "target_ref": AC3,
            "relationship": "intersects-with",
            "review_status": "draft",
        },
        {
            "type": "baseline",
            "id": LIB_BASELINE,
            **env,
            "name": "Access control",
            "framework_refs": [FW],
            "control_refs": [C1, C2],
        },
        {
            "type": "test",
            "id": LIB_TEST,
            **env,
            "name": "Active IdP users are unique",
            "control_ref": C1,
            "method": "automated",
            "interval": "monthly",
            "required": True,
            "objective_refs": [f"{AC2}#obj.a"],
        },
    ]


def write_library(root: Path, objects: list[dict[str, Any]], version: str = "0.1.0") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "bundle.yaml").write_text(
        yaml.safe_dump(
            {
                "type": "bundle",
                "id": "bundle--ogrl-library",
                "spec_version": "0.1.0",
                "created": STAMP,
                "modified": STAMP,
                "name": "Test library",
                "version": version,
            }
        )
    )
    for obj in objects:
        kind, remainder = obj["id"].split("--", 1)
        path = root / kind / f"{remainder}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(obj, sort_keys=False))
    return root


class Tokens:
    def __init__(self, principals: dict[str, Principal]) -> None:
        self._principals = principals

    async def authenticate(self, credentials: Credentials) -> Principal | None:
        return self._principals.get(credentials.bearer or "")


PRINCIPALS = {
    role.value: Principal(f"party--{role.value}", "org", ActorKind.PERSON, frozenset({role}))
    for role in Role
}
PRINCIPALS["agent"] = Principal("party--agent", "org", ActorKind.AGENT, frozenset({Role.AGENT}))
# An agent principal that also holds a person's role: the gates must still hold.
PRINCIPALS["rogue-agent"] = Principal(
    "party--rogue", "org", ActorKind.AGENT, frozenset({Role.ADMINISTRATOR})
)


class Api:
    """A client acting as one role. Methods assert the status and return the JSON."""

    def __init__(self, client: TestClient, token: str) -> None:
        self.client = client
        self.headers = {"Authorization": f"Bearer {token}"}

    def _call(self, method: str, url: str, expect: int, *, json=None, if_match=None, **kw):
        headers = dict(self.headers)
        if if_match is not None:
            headers["If-Match"] = if_match
        response = self.client.request(method, "/v1" + url, json=json, headers=headers, **kw)
        assert response.status_code == expect, (response.status_code, response.text)
        if response.headers.get("content-type", "").startswith(
            ("application/json", "application/problem")
        ):
            return response.json()
        return response

    def get(self, url: str, expect: int = 200, **kw):
        return self._call("GET", url, expect, **kw)

    def post(self, url: str, json=None, expect: int = 201, **kw):
        return self._call("POST", url, expect, json=json, **kw)

    def patch(self, url: str, json, if_match: str, expect: int = 200):
        return self._call("PATCH", url, expect, json=json, if_match=if_match)

    def revoke(self, url: str, if_match: str, expect: int = 200):
        return self._call("POST", url + "/revoke", expect, if_match=if_match)


@pytest.fixture
def library_dir(tmp_path: Path) -> Path:
    return write_library(tmp_path / "library", library_objects())


@pytest.fixture
def secrets() -> StaticSecrets:
    return StaticSecrets({"IDP_TENANT": "acme"})


@pytest.fixture
def make_app(
    library_dir: Path, secrets: StaticSecrets, tmp_path: Path, backend: str
) -> Callable[..., Any]:
    def make(**overrides: Any) -> tuple[TestClient, container.Container]:
        store = MemoryStore() if backend == "memory" else postgres_store()
        kwargs: dict[str, Any] = {
            "authenticator": Tokens(PRINCIPALS),
            "store": store,
            "connections": connection_store(store),
            "integrations_dir": INTEGRATIONS_DIR,
            "blobs": MemoryBlobs() if backend == "memory" else s3_blobs(),
            "library_source": DirectoryLibrary(library_dir, commit="c0ffee"),
            "secrets": secrets,
            "export": ExportSettings(remote=None),
        }
        kwargs.update(overrides)
        c = container.build(**kwargs)
        return TestClient(create_app(c)), c

    return make


@pytest.fixture
def app(make_app) -> tuple[TestClient, container.Container]:
    return make_app()


@pytest.fixture
def client(app) -> TestClient:
    return app[0]


@pytest.fixture
def admin(client) -> Api:
    return Api(client, "administrator")


@pytest.fixture
def contributor(client) -> Api:
    return Api(client, "contributor")


@pytest.fixture
def agent(client) -> Api:
    return Api(client, "agent")


@pytest.fixture
def pulled(admin: Api) -> Api:
    """The library is pulled, so the fixture library is the projection."""
    job = admin.post("/library/pull", {"version": "0.1.0"}, expect=202)
    assert job["status"] == "succeeded", job
    return admin


@pytest.fixture
def program(pulled: Api) -> dict[str, str]:
    """A system, a party, and a program on the library baseline."""
    owner = pulled.post("/parties", {"name": "Security lead", "kind": "role"})
    system = pulled.post("/systems", {"name": "Production"})
    prog = pulled.post(
        "/programs", {"name": "2026", "system_ref": system["id"], "baseline_ref": LIB_BASELINE}
    )
    return {"owner": owner["id"], "system": system["id"], "program": prog["id"]}
