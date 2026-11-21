"""Query sources (RFC 0006) end to end: validate, dry run, save, collect, run, preview, delete.

The vendor is a local HTTP emulator of the description in tests/packages/sdk-vendor; the
integration is built with the SDK and runs its generic OpenAPI executor.
"""

import json
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from ogrl_integration.cli import build_openapi

from tests.conftest import C1, LIB_TEST, Api

PACKAGE = Path(__file__).parent / "packages" / "sdk-vendor"
FAKE = Path(__file__).parent / "integrations" / "fake"
VENDOR = "dev.ogrl.vendor"
APPS = [
    {
        "id": "a1",
        "label": "Slack",
        "status": "ACTIVE",
        "signOnMode": "SAML_2_0",
        "settings": {"mfa": True},
    },
    {
        "id": "a2",
        "label": "Jira",
        "status": "ACTIVE",
        "signOnMode": "BOOKMARK",
        "settings": {"mfa": False},
    },
    {"id": "a3", "label": "Wiki", "status": "INACTIVE", "signOnMode": "SAML_2_0", "settings": {}},
]


class Emulator(BaseHTTPRequestHandler):
    requests: list[tuple[str, str, str | None]] = []

    def log_message(self, *args):  # quiet
        pass

    def _send(self, status: int, body, headers=None):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlsplit(self.path)
        Emulator.requests.append(("GET", self.path, self.headers.get("Authorization")))
        if self.headers.get("Authorization") != "Bearer v3nd0r":
            return self._send(401, {"error": "unauthorized"})
        if url.path == "/api/apps":
            query = parse_qs(url.query)
            rows = [a for a in APPS if "status" not in query or a["status"] == query["status"][0]]
            page = int(query.get("page", ["1"])[0])
            if page == 1 and len(rows) > 2:
                port = self.server.server_address[1]
                link = f'<http://127.0.0.1:{port}/api/apps?page=2>; rel="next"'
                return self._send(200, rows[:2], {"Link": link})
            return self._send(200, rows[2:] if page == 2 else rows)
        if url.path.startswith("/api/groups/") and url.path.endswith("/members"):
            return self._send(200, {"value": [{"id": "u1", "login": "ada@acme.test"}]})
        return self._send(404, {"error": "not found"})

    def do_POST(self):  # a query must never send a write
        Emulator.requests.append(("POST", self.path, self.headers.get("Authorization")))
        return self._send(500, {"error": "writes are not allowed"})


@pytest.fixture
def emulator():
    Emulator.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), Emulator)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()


@pytest.fixture
def app(make_app, tmp_path):
    packages = tmp_path / "packages"
    shutil.copytree(PACKAGE, packages / "sdk-vendor")
    shutil.copytree(FAKE, packages / "fake")
    build_openapi(packages / "sdk-vendor")  # what `ogrl-integration pack` does
    return make_app(integrations_dir=packages)


@pytest.fixture
def world(app, program, pulled: Api, emulator):
    component = pulled.post("/components", {"name": "Vendor", "kind": "service"})
    impl = pulled.post(
        "/implementations",
        {
            "component_ref": component["id"],
            "control_ref": C1,
            "status": "implemented",
            "responsibility": "provider",
        },
    )
    connection = pulled.post(
        "/connections",
        {
            "integration_id": VENDOR,
            "name": "Vendor prod",
            "config": {"port": str(emulator)},
            "auth_kind": "fields",
            "bindings": [component["id"]],
        },
    )
    pulled._call(
        "PUT",
        f"/connections/{connection['id']}/secrets/VENDOR_TOKEN",
        200,
        json={"value": "v3nd0r"},
    )
    return {"api": pulled, "impl": impl["id"], "connection": connection["id"], "port": emulator}


QUERY = {
    "integration_id": VENDOR,
    "name": "active-apps",
    "operation": "listApps",
    "params": {"status": "ACTIVE"},
    "fields": {
        "id": "id",
        "name": "label",
        "sign_on": "signOnMode",
        "mfa": "settings.mfa",
        "notes": "notes",
    },
}


def test_operations_search_and_describe(world):
    api = world["api"]
    found = api.get(f"/integrations/{VENDOR}/operations?q=list")["data"]
    assert [o["id"] for o in found] == ["listApps", "listMembers"]  # createApp is a write
    members = api.get(f"/integrations/{VENDOR}/operations/listMembers")
    assert members["parameters"] == [
        {"name": "groupId", "in": "path", "required": True, "type": "string"}
    ]
    assert {f["path"]: f["items"] for f in members["fields"]} == {"id": "value", "login": "value"}
    api.get("/integrations/dev.ogrl.fake/operations?q=x", expect=400)  # no description


def test_validation_feedback(world):
    api = world["api"]
    check = api.post("/queries/validate", QUERY, expect=200)
    assert (check["valid"], check["source"]) == (True, f"{VENDOR}/active-apps@1")
    types = {f["name"]: f["type"] for f in check["fields"]}
    assert types == {
        "id": "string",
        "name": "string",
        "sign_on": "string",
        "mfa": "boolean",
        "notes": "string",
    }

    def problems(**changes):
        out = api.post("/queries/validate", {**QUERY, **changes}, expect=200)
        return {p["pointer"]: p["detail"] for p in out["errors"]}

    assert "only reads" in problems(operation="createApp")["/operation"]
    assert problems(fields={**QUERY["fields"], "name": "lable"})["/fields/name"].endswith(
        "did you mean 'label'?"
    )
    assert problems(params={"limit": "lots"}) == {"/params/limit": "limit is an integer"}
    assert problems(name="status")["/name"] == f"{VENDOR} has a built-in resource 'status'"
    assert problems(operation="listMembers", params={}, fields={"id": "id", "name": "login"}) == {
        "/params/groupId": "/api/groups/{groupId}/members needs groupId",
        "/items": "the response body is not a list; set items to the path of the list",
    }
    fake = api.post("/queries/validate", {**QUERY, "integration_id": "dev.ogrl.fake"}, expect=200)
    assert fake["errors"][0]["pointer"] == "/integration_id"


def test_dry_run_samples_without_storing(world):
    api = world["api"]
    run = api.post(
        "/queries/dry-run",
        {**QUERY, "connection_id": world["connection"], "max_items": 1},
        expect=200,
    )
    assert (run.get("error"), run["count"]) == (None, 1)
    assert run["items"] == [
        {"id": "a1", "name": "Slack", "sign_on": "SAML_2_0", "mfa": True, "notes": None}
    ]
    assert run["warnings"] == [
        {"pointer": "/fields/notes", "detail": "notes is empty in all 1 items; check the path"}
    ]
    assert len(Emulator.requests) == 1  # max_items stopped before page 2
    assert api.get("/snapshots")["data"] == []

    bad = api.post(
        "/queries/dry-run",
        {**QUERY, "operation": "createApp", "connection_id": world["connection"]},
        expect=200,
    )
    assert bad["error"] == "fix the definition first"
    assert all(method == "GET" for method, _, _ in Emulator.requests)


def test_save_collect_run_and_evidence(world):
    api = world["api"]
    saved = api.post("/queries", QUERY, expect=201)
    assert saved["item_schema"]["properties"]["mfa"]["type"] == ["boolean", "null"]
    api.post("/queries", QUERY, expect=409)  # versions are immutable
    assert api.get("/queries")["data"][0]["id"] == saved["id"]

    test = api.post(
        "/tests",
        {
            "name": "Active apps use SSO with MFA",
            "control_ref": C1,
            "fulfills_ref": LIB_TEST,
            "method": "automated",
            "interval": "daily",
            "run": {
                "runner": "rule",
                "source": f"{VENDOR}/active-apps@1",
                "assert": "item.mfa == true",
            },
        },
    )
    job = api.post(f"/tests/{test['id']}/runs", {"implementation_id": world["impl"]}, expect=202)
    result = api.get(f"/results/{job['result_id']}")
    assert (result["outcome"], result["summary"]) == ("fail", "1 of 2 selected items pass")
    assert result["subjects"] == [{"kind": "active-apps", "name": "Jira", "external_id": "a2"}]

    (evidence_id,) = result["evidence_refs"]
    (snapshot,) = api.get(f"/snapshots?source={VENDOR}/active-apps@1")["data"]
    document = json.loads(api.get(f"/snapshots/{snapshot['id']}/content").content)
    assert document["query"]["operation"] == "listApps"  # the snapshot records its definition
    assert document["query"]["params"] == {"status": "ACTIVE"}
    assert api.get(f"/evidence/{evidence_id}")["resource"]["digest"]["value"] == snapshot["digest"]

    preview = api.post(
        "/rules/preview",
        {"run": {"source": f"{VENDOR}/active-apps@1", "assert": "item.sign_on == 'SAML_2_0'"}},
        expect=200,
    )
    assert preview["summary"] == "1 of 2 selected items pass"

    inline = api.post(
        "/rules/preview",
        {
            "run": {"source": f"{VENDOR}/active-apps@1", "assert": "item.mfa == true"},
            "items": [{"id": "x", "name": "X", "mfa": True}],
        },
        expect=200,
    )
    assert (inline["outcome"], inline["snapshots"]) == ("pass", [])

    api._call("DELETE", f"/queries/{saved['id']}", 409)  # a test reads it
    api.revoke(f"/tests/{test['id']}", if_match=api.get(f"/tests/{test['id']}")["modified"])
    api._call("DELETE", f"/queries/{saved['id']}", 204)
    assert all(method == "GET" for method, _, _ in Emulator.requests)


def test_saving_needs_define_run(world, client):
    agent = Api(client, "agent")
    assert (
        agent.post("/queries/validate", QUERY, expect=200)["valid"] is True
    )  # drafting is allowed
    agent.post("/queries", QUERY, expect=403)  # saving an executable definition is not


def test_query_definitions_travel_with_the_git_export(make_app, tmp_path):
    import subprocess

    import yaml

    from ogrl.operations.exports import ExportSettings

    def git(*args, cwd=None):
        subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)

    packages = tmp_path / "packages"
    shutil.copytree(PACKAGE, packages / "sdk-vendor")
    build_openapi(packages / "sdk-vendor")
    remote = tmp_path / "remote.git"
    git("init", "--bare", "--quiet", "-b", "main", str(remote))
    client, _ = make_app(integrations_dir=packages, export=ExportSettings(remote=str(remote)))
    admin = Api(client, "administrator")
    admin.post("/library/pull", {"version": "0.1.0"}, expect=202)
    saved = admin.post("/queries", QUERY, expect=201)
    assert admin.post("/exports/git", expect=202)["status"] == "succeeded"

    checkout = tmp_path / "checkout"
    git("clone", "--quiet", str(remote), str(checkout))
    exported = yaml.safe_load(
        (checkout / "ogrl-app/queries" / VENDOR / "active-apps@1.yaml").read_text()
    )
    assert (exported["id"], exported["operation"]) == (saved["id"], "listApps")

    fresh, _ = make_app(integrations_dir=packages)
    restorer = Api(fresh, "administrator")
    job = restorer.post("/restore", {"url": str(remote)}, expect=202)
    assert job["status"] == "succeeded", job
    assert job["report"]["queries"] == 1
    assert restorer.get(f"/queries/{saved['id']}") == admin.get(f"/queries/{saved['id']}")
