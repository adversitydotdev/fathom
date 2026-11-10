from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from opengrc import container
from opengrc.access import ActorKind, Principal, Role
from opengrc.api.app import create_app
from opengrc.auth import Credentials
from opengrc.kernel.models import Control, Origin
from opengrc.persistence.memory import MemoryControls

LIBRARY = Control(
    id="control--ogrc-ac-01",
    name="Account management",
    origin=Origin.STANDARD,
    statement="Accounts are approved before access is granted.",
    objective="Only approved people hold accounts.",
    created=datetime(2026, 10, 22, tzinfo=UTC),
    modified=datetime(2026, 10, 22, tzinfo=UTC),
)


class StaticTokens:
    """A test Authenticator: proves the registrar depends only on the protocol."""

    def __init__(self, principals: dict[str, Principal]) -> None:
        self._principals = principals

    async def authenticate(self, credentials: Credentials) -> Principal | None:
        return self._principals.get(credentials.bearer or "")


def as_role(role: Role) -> dict[str, str]:
    return {"Authorization": f"Bearer {role.value}"}


@pytest.fixture
def client() -> TestClient:
    principals = {
        role.value: Principal(f"party--{role.value}", "org", ActorKind.PERSON, frozenset({role}))
        for role in Role
    }
    app = create_app(
        container.build(authenticator=StaticTokens(principals), controls=MemoryControls([LIBRARY]))
    )
    return TestClient(app)


NEW = {
    "id": "control--com.acme.badge-access",
    "name": "Badge access",
    "statement": "Doors to the office require a badge.",
    "objective": "Only staff enter the office.",
}


def test_health_is_public(client):
    assert client.get("/v1/health").json()["status"] == "ok"


def test_no_token_is_401_problem(client):
    response = client.get("/v1/controls")
    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "urn:opengrc:problem:unauthenticated"


def test_viewer_reads_but_cannot_write(client):
    page = client.get("/v1/controls", headers=as_role(Role.VIEWER)).json()
    assert [c["id"] for c in page["data"]] == [LIBRARY.id]
    assert client.post("/v1/controls", json=NEW, headers=as_role(Role.VIEWER)).status_code == 403


def test_contributor_creates_updates_and_revokes(client):
    headers = as_role(Role.CONTRIBUTOR)
    created = client.post("/v1/controls", json=NEW, headers=headers)
    assert created.status_code == 201
    assert created.headers["location"] == f"/v1/controls/{NEW['id']}"
    control = created.json()
    assert control["origin"] == "custom"
    assert control["created_by_ref"] == "party--contributor"

    url = created.headers["location"]
    stale = {**headers, "If-Match": "2000-01-01T00:00:00Z"}
    assert client.patch(url, json={**NEW, "family": "PE"}, headers=stale).status_code == 412

    fresh = {**headers, "If-Match": control["modified"]}
    updated = client.patch(url, json={**NEW, "family": "PE"}, headers=fresh)
    assert updated.status_code == 200, updated.json()
    assert updated.json()["family"] == "PE"

    revoke = client.post(
        f"{url}/revoke", headers={**headers, "If-Match": updated.json()["modified"]}
    )
    assert revoke.json()["revoked"] is True
    listed = client.get("/v1/controls", headers=headers).json()["data"]
    assert NEW["id"] not in [c["id"] for c in listed]


def test_library_control_is_read_only(client):
    headers = {**as_role(Role.ADMINISTRATOR), "If-Match": LIBRARY.modified.isoformat()}
    response = client.patch(f"/v1/controls/{LIBRARY.id}", json=NEW, headers=headers)
    assert response.status_code == 409
    assert response.json()["type"] == "urn:opengrc:problem:library-object"


def test_reserved_slug_is_rejected(client):
    body = {**NEW, "id": "control--ac-99"}
    response = client.post("/v1/controls", json=body, headers=as_role(Role.CONTRIBUTOR))
    assert response.status_code == 400
    assert response.json()["errors"][0]["pointer"] == "/id"
