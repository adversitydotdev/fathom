"""Shared fixtures: a small library on disk, principals per role, and an API client."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from opengrc import container
from opengrc.access import ActorKind, Principal, Role
from opengrc.adapters.library import DirectoryLibrary
from opengrc.adapters.secrets import StaticSecrets
from opengrc.api.app import create_app
from opengrc.auth import Credentials
from opengrc.operations.exports import ExportSettings
from opengrc.persistence.memory import MemoryStore

STAMP = "2026-10-22T11:30:00Z"
FW = "framework--nist-sp-800-53-r5"
AC2 = "requirement--nist-sp-800-53-r5-ac-2"
AC3 = "requirement--nist-sp-800-53-r5-ac-3"
C1 = "control--ogrc-ac-01"
C2 = "control--ogrc-ac-02"
LIB_TEST = "test--ogrc-ac-01-unique-idp-users"
LIB_BASELINE = "baseline--ogrc-ac"


def library_objects() -> list[dict[str, Any]]:
    env = {"spec_version": "0.1.0", "created": STAMP, "modified": STAMP}
    return [
        {"type": "framework", "id": FW, **env, "name": "NIST SP 800-53 Revision 5",
         "publisher": "NIST", "version": "5.2.0", "reproduction": "permitted",
         "source": {"format": "oscal-catalog", "uri": "https://github.com/usnistgov/oscal-content",
                    "path": "nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json",
                    "commit": "f0de6d8"}},
        {"type": "requirement", "id": AC2, **env, "display_id": "AC-2", "name": "Account Management",
         "framework_ref": FW, "class": "control",
         "parameters": {"ac_02_odp_10": {"label": "frequency"}},
         "parts": [{"id": "a", "statement": "Define account types."},
                   {"id": "j", "statement": "Review accounts {{ ac_02_odp_10 }}."}],
         "objectives": [{"id": "a", "statement": "Determine if account types are defined."}]},
        {"type": "requirement", "id": AC3, **env, "display_id": "AC-3", "name": "Access Enforcement",
         "framework_ref": FW, "class": "control"},
        {"type": "control", "id": C1, **env, "display_id": "OGRC-AC-01", "name": "Unique identities",
         "origin": "standard", "family": "ac",
         "statement": "Each user has a unique identity, reviewed {{ shared_account_review }}.",
         "objective": "Every account traces to one owner.",
         "parameters": {"shared_account_review": {"label": "review", "value": "quarterly"}}},
        {"type": "control", "id": C2, **env, "display_id": "OGRC-AC-02", "name": "Access reviews",
         "origin": "standard", "family": "ac", "statement": "Accounts are reviewed.",
         "objective": "Stale access is removed.",
         "parameters": {"access_review_frequency": {"label": "how often", "value": "monthly"}}},
        {"type": "mapping", "id": "mapping--ogrc-ac-01_to_nist-sp-800-53-r5-ac-2_part_a", **env,
         "source_ref": C1, "target_ref": f"{AC2}#a", "relationship": "equal-to",
         "rationale": "functional", "review_status": "reviewed"},
        {"type": "mapping", "id": "mapping--ogrc-ac-02_to_nist-sp-800-53-r5-ac-2_part_j", **env,
         "source_ref": C2, "target_ref": f"{AC2}#j", "relationship": "subset-of",
         "rationale": "functional", "review_status": "draft",
         "parameter_map": {"ac_02_odp_10": "access_review_frequency"}},
        {"type": "mapping", "id": "mapping--ogrc-ac-02_to_nist-sp-800-53-r5-ac-3", **env,
         "source_ref": C2, "target_ref": AC3, "relationship": "intersects-with",
         "review_status": "draft"},
        {"type": "baseline", "id": LIB_BASELINE, **env, "name": "Access control",
         "framework_refs": [FW], "control_refs": [C1, C2]},
        {"type": "test", "id": LIB_TEST, **env, "name": "Active IdP users are unique",
         "control_ref": C1, "method": "automated", "interval": "monthly", "required": True,
         "objective_refs": [f"{AC2}#obj.a"]},
    ]


def write_library(root: Path, objects: list[dict[str, Any]], version: str = "0.1.0") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "bundle.yaml").write_text(yaml.safe_dump({
        "type": "bundle", "id": "bundle--ogrc-library", "spec_version": "0.1.0",
        "created": STAMP, "modified": STAMP, "name": "Test library", "version": version,
    }))
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
        if response.headers.get("content-type", "").startswith(("application/json", "application/problem")):
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
def make_app(library_dir: Path, secrets: StaticSecrets, tmp_path: Path) -> Callable[..., Any]:
    def make(**overrides: Any) -> tuple[TestClient, container.Container]:
        kwargs: dict[str, Any] = {
            "authenticator": Tokens(PRINCIPALS),
            "store": MemoryStore(),
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
    prog = pulled.post("/programs", {"name": "2026", "system_ref": system["id"],
                                     "baseline_ref": LIB_BASELINE})
    return {"owner": owner["id"], "system": system["id"], "program": prog["id"]}
