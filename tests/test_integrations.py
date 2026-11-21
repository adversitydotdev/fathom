"""Connections, collection, and snapshot runs through the services (RFC 0005, RFC 0001 7.6).

The fake integration in tests/integrations/fake stands in for a vendor.
"""

import asyncio
import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest

from ogrl.adapters.oauth import HttpOAuthClient
from ogrl.errors import Invalid, NotFound, PreconditionFailed
from ogrl.operations.integrations import (
    CollectionRequest,
    ConnectionPatch,
    ConnectionWrite,
    SecretWrite,
    TemplateEnable,
    build_snapshot,
)
from ogrl.plugins.ports import IntegrationError
from tests.conftest import C1, LIB_TEST, PRINCIPALS, Api

FAKE = "dev.ogrl.fake"
USERS = "dev.ogrl.fake/users@1"
ADMIN = PRINCIPALS["administrator"]


def run(coro):
    return asyncio.run(coro)


class Clock:
    """Real time until a test moves it forward."""

    def __init__(self) -> None:
        self.offset = timedelta()

    def __call__(self) -> datetime:
        return datetime.now(UTC) + self.offset


@pytest.fixture
def clock() -> Clock:
    return Clock()


class Vendor:
    """A local OAuth authorization server, the emulator the repo rules ask for.

    `authorize` plays the browser and the vendor's consent page: it reads the
    URL OGRL built and issues a code bound to the PKCE challenge. The token
    endpoint checks the client, the redirect URI, and the verifier.
    """

    CLIENT = ("client-1", "client-secret-1")

    def __init__(self) -> None:
        self.codes: dict[str, dict[str, str]] = {}
        self.refresh = 0
        self.issue_refresh = True

    def authorize(self, url: str) -> dict[str, str]:
        query = dict(parse_qsl(urlsplit(url).query))
        code = f"code-{len(self.codes)}"
        self.codes[code] = query
        return {"code": code, "state": query["state"]}

    def handler(self, request: httpx.Request) -> httpx.Response:
        form = dict(parse_qsl(request.content.decode()))
        if (form.get("client_id"), form.get("client_secret")) != self.CLIENT:
            return httpx.Response(401, json={"error": "invalid_client"})
        if form["grant_type"] == "authorization_code":
            issued = self.codes.pop(form.get("code", ""), None)
            challenge = (
                base64.urlsafe_b64encode(
                    hashlib.sha256(form.get("code_verifier", "").encode()).digest()
                )
                .rstrip(b"=")
                .decode()
            )
            if (
                issued is None
                or issued["redirect_uri"] != form["redirect_uri"]
                or issued["code_challenge"] != challenge
            ):
                return httpx.Response(400, json={"error": "invalid_grant"})
            body = {"access_token": "access-0"}
            if self.issue_refresh:
                body["refresh_token"] = "refresh-0"
            return httpx.Response(200, json=body)
        if (
            form["grant_type"] == "refresh_token"
            and form["refresh_token"] == f"refresh-{self.refresh}"
        ):
            self.refresh += 1  # rotate on every use
            return httpx.Response(
                200,
                json={
                    "access_token": f"access-{self.refresh}",
                    "refresh_token": f"refresh-{self.refresh}",
                },
            )
        return httpx.Response(400, json={"error": "invalid_grant"})


class Assumer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def assume(self, role_arn: str, external_id: str, session_name: str):
        self.calls.append((role_arn, external_id, session_name))
        return {
            "AWS_ACCESS_KEY_ID": "ASIAFAKE",
            "AWS_SECRET_ACCESS_KEY": "secret",
            "AWS_SESSION_TOKEN": "fake-session",
        }


@pytest.fixture
def vendor() -> Vendor:
    return Vendor()


@pytest.fixture
def assumer() -> Assumer:
    return Assumer()


@pytest.fixture
def app(make_app, clock, vendor, assumer):
    return make_app(
        clock=clock,
        oauth_client=HttpOAuthClient(transport=httpx.MockTransport(vendor.handler)),
        role_assumer=assumer,
        public_url="https://grc.acme.test/",
    )


@pytest.fixture
def world(app, program, pulled: Api):
    """A component in the program's system, and an implementation of C1 on the system."""
    _, c = app
    component = pulled.post("/components", {"name": "Corporate IdP", "kind": "software"})
    system = pulled.get(f"/systems/{program['system']}")
    pulled.patch(
        f"/systems/{program['system']}",
        {"component_refs": [component["id"]]},
        if_match=system["modified"],
    )
    impl = pulled.post(
        "/implementations",
        {
            "system_ref": program["system"],
            "control_ref": C1,
            "status": "implemented",
            "responsibility": "customer",
        },
    )
    return {"c": c, "api": pulled, "component": component["id"], "impl": impl["id"], **program}


def connect(c, component: str, dataset: str = "acme", mode: str | None = None, name="Fake prod"):
    config = {"dataset": dataset, **({"mode": mode} if mode else {})}
    connection = run(
        c.integrations.create_connection(
            ADMIN,
            ConnectionWrite(
                integration_id=FAKE,
                name=name,
                config=config,
                auth_kind="fields",
                bindings=[component],
            ),
        )
    )
    return run(
        c.integrations.put_secret(ADMIN, connection.id, "FAKE_TOKEN", SecretWrite(value="s3cret"))
    )


def rule_test(api: Api, **run_fields) -> dict:
    return api.post(
        "/tests",
        {
            "name": "Active users have MFA",
            "control_ref": C1,
            "fulfills_ref": LIB_TEST,
            "method": "automated",
            "interval": "daily",
            "run": {
                "runner": "rule",
                "source": USERS,
                "select": 'item.status == "ACTIVE"',
                "assert": "item.mfa",
                **run_fields,
            },
        },
    )


def run_test(api: Api, test_id: str, impl: str) -> dict:
    job = api.post(f"/tests/{test_id}/runs", {"implementation_id": impl}, expect=202)
    assert job["status"] == "succeeded", job
    return api.get(f"/results/{job['result_id']}")


def test_integrations_are_listed(world):
    c = world["c"]
    views = run(c.integrations.list_integrations(ADMIN))
    assert [v.id for v in views] == [FAKE]
    view = views[0]
    assert view.resources == [{"name": "users", "version": 1, "source": USERS}]
    assert view.checks[0]["check"] == "dev.ogrl.fake/admins-have-mfa@1"
    assert view.auth[0]["supported"] is True


def test_connection_lifecycle(world):
    c = world["c"]
    connection = connect(c, world["component"])
    assert (connection.state, connection.secrets_set) == ("pending", ["FAKE_TOKEN"])
    assert "s3cret" not in connection.model_dump_json()

    job = run(c.integrations.validate(ADMIN, connection.id))
    assert job.status == "succeeded", job
    connection = run(c.integrations.get_connection(ADMIN, connection.id))
    assert (connection.state, connection.identity) == ("active", "acme as svc-ogrl")

    renamed = run(
        c.integrations.update_connection(
            ADMIN, connection.id, ConnectionPatch(name="Fake"), connection.modified
        )
    )
    assert renamed.name == "Fake"
    with pytest.raises(PreconditionFailed):
        run(
            c.integrations.update_connection(
                ADMIN, connection.id, ConnectionPatch(name="x"), connection.modified
            )
        )
    run(c.integrations.delete_connection(ADMIN, connection.id))
    with pytest.raises(NotFound):
        run(c.integrations.get_connection(ADMIN, connection.id))


def test_connection_refusals(world):
    c = world["c"]
    with pytest.raises(Invalid) as caught:
        run(
            c.integrations.create_connection(
                ADMIN,
                ConnectionWrite(
                    integration_id=FAKE,
                    name="bad",
                    config={"dataset": "Not Valid", "extra": "x"},
                    auth_kind="kerberos",
                    bindings=[C1],
                ),
            )
        )
    pointers = {e.pointer for e in caught.value.errors}
    assert pointers == {"/config/dataset", "/config/extra", "/auth_kind", "/bindings/0"}
    connection = connect(c, world["component"])
    with pytest.raises(NotFound):
        run(c.integrations.put_secret(ADMIN, connection.id, "OTHER", SecretWrite(value="x")))


def test_failed_validation_marks_the_connection(world):
    c = world["c"]
    connection = connect(c, world["component"], mode="auth_failed")
    job = run(c.integrations.validate(ADMIN, connection.id))
    assert job.status == "failed"
    assert "auth_failed" in job.error.detail
    connection = run(c.integrations.get_connection(ADMIN, connection.id))
    assert connection.state == "failing"
    assert connection.last_error.startswith("auth_failed")


def test_collection_stores_a_snapshot(world):
    c = world["c"]
    connection = connect(c, world["component"], mode="extra_fields")
    job = run(c.integrations.collect(ADMIN, connection.id, CollectionRequest()))
    assert job.status == "succeeded", job
    (snapshot,) = run(c.integrations.list_snapshots(ADMIN, connection.id, None))
    assert (snapshot.source, snapshot.complete, snapshot.item_count) == (USERS, True, 3)
    assert snapshot.warnings == ["removed undeclared fields: password_hash"]
    document = json.loads(run(c.integrations.snapshot_content(ADMIN, snapshot.id)))
    assert document["source"] == USERS
    assert all("password_hash" not in item for item in document["items"])


def test_rule_run_records_result_subjects_and_snapshot_evidence(world):
    c, api = world["c"], world["api"]
    connect(c, world["component"])
    test = rule_test(api)
    result = run_test(api, test["id"], world["impl"])
    assert (result["outcome"], result["summary"]) == ("fail", "1 of 2 selected items pass")
    assert result["subjects"] == [{"kind": "users", "name": "bob@acme.test", "external_id": "u2"}]
    (evidence_id,) = result["evidence_refs"]
    evidence = api.get(f"/evidence/{evidence_id}")
    assert evidence["resource"]["media_type"] == "application/vnd.ogrl.snapshot+json"
    assert evidence["collected"] == result["observed"]
    (snapshot,) = run(c.integrations.list_snapshots(ADMIN, None, USERS))
    assert evidence["resource"]["digest"]["value"] == snapshot.digest

    # A second run reuses the fresh snapshot instead of collecting again.
    run_test(api, test["id"], world["impl"])
    assert len(run(c.integrations.list_snapshots(ADMIN, None, USERS))) == 1


def test_two_connections_concatenate_in_id_order(world):
    c, api = world["c"], world["api"]
    connect(c, world["component"], dataset="acme", name="a")
    connect(c, world["component"], dataset="secure", name="b")
    result = run_test(api, rule_test(api)["id"], world["impl"])
    assert result["summary"] == "2 of 3 selected items pass"
    assert len(result["evidence_refs"]) == 2


def test_selection_errors(world):
    c, api = world["c"], world["api"]
    test = rule_test(api)
    result = run_test(api, test["id"], world["impl"])
    assert result["outcome"] == "error"
    assert result["summary"].startswith("no connection of dev.ogrl.fake is bound to")

    connect(c, world["component"], mode="incomplete")
    result = run_test(api, test["id"], world["impl"])
    assert result["outcome"] == "error"
    assert "incomplete: rate limited after page 1" in result["summary"]


def test_integration_check_run(world):
    c, api = world["c"], world["api"]
    connect(c, world["component"])
    test = api.post(
        "/tests",
        {
            "name": "Admins have MFA",
            "control_ref": C1,
            "method": "automated",
            "interval": "daily",
            "run": {
                "runner": "integration",
                "check": "dev.ogrl.fake/admins-have-mfa@1",
                "sources": [USERS],
            },
        },
    )
    result = run_test(api, test["id"], world["impl"])
    assert (result["outcome"], result["summary"]) == ("fail", "1 admins without MFA")
    assert result["subjects"] == [
        {"kind": "account", "name": "carol@acme.test", "external_id": "u3"}
    ]


def test_template_creates_an_organization_test(world):
    c = world["c"]
    test = run(c.integrations.enable_template(ADMIN, FAKE, "mfa-enforcement", TemplateEnable()))
    assert test.fulfills_ref == LIB_TEST
    assert test.run.runner == "rule"
    assert test.created_by_ref == ADMIN.actor_id
    assert test.extensions["dev.ogrl.integration"]["template"] == "mfa-enforcement"


def test_rate_limits_are_retried(world, monkeypatch):
    c = world["c"]
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(c.integrations, "_sleep", sleep)
    connection = connect(c, world["component"], mode="rate_limited")
    job = run(c.integrations.collect(ADMIN, connection.id, CollectionRequest()))
    assert job.status == "failed"
    assert slept == [1, 1, 1]


def test_build_snapshot_rejects_items_that_break_the_schema():
    schema = {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}}
    collected = datetime(2026, 11, 21, tzinfo=UTC)
    content, warnings = build_snapshot(USERS, collected, True, [{"id": "a"}], schema)
    assert json.loads(content)["collected"] == "2026-11-21T00:00:00Z"
    assert warnings == []
    with pytest.raises(IntegrationError, match="item 0 at id"):
        build_snapshot(USERS, collected, True, [{"id": 1}], schema)


# --- HTTP ------------------------------------------------------------------------------------


def test_routes_end_to_end(world, client):
    api = world["api"]
    assert [i["id"] for i in api.get("/integrations")["data"]] == [FAKE]
    assert api.get(f"/integrations/{FAKE}")["resources"][0]["source"] == USERS
    api.get("/integrations/dev.ogrl.missing", expect=404)

    connection = api.post(
        "/connections",
        {
            "integration_id": FAKE,
            "name": "Fake prod",
            "config": {"dataset": "acme"},
            "auth_kind": "fields",
            "bindings": [world["component"]],
        },
    )
    cid = connection["id"]
    assert connection["state"] == "pending"
    api._call("PUT", f"/connections/{cid}/secrets/FAKE_TOKEN", 200, json={"value": "s3cret"})
    job = api.post(f"/connections/{cid}/validate", expect=202)
    assert job["status"] == "succeeded", job
    connection = api.get(f"/connections/{cid}")
    assert (connection["state"], connection["secrets_set"]) == ("active", ["FAKE_TOKEN"])
    assert "s3cret" not in str(connection)

    job = api.post(f"/connections/{cid}/collections", {"sources": [USERS]}, expect=202)
    assert job["status"] == "succeeded", job
    (snapshot,) = api.get(f"/snapshots?connection_id={cid}")["data"]
    assert api.get(f"/snapshots/{snapshot['id']}")["item_count"] == 3
    content = api.get(f"/snapshots/{snapshot['id']}/content")
    assert content.headers["content-type"] == "application/vnd.ogrl.snapshot+json"
    assert json.loads(content.content)["source"] == USERS

    api.post(f"/connections/{cid}/collections", {"sources": ["x.y/z@1"]}, expect=400)

    test = api.post(f"/integrations/{FAKE}/templates/mfa-enforcement/enable", expect=201)
    result = run_test(api, test["id"], world["impl"])
    assert result["outcome"] == "fail"

    patched = api.patch(
        f"/connections/{cid}", {"state": "disabled"}, if_match=connection["modified"]
    )
    assert patched["state"] == "disabled"
    api.patch(f"/connections/{cid}", {"name": "x"}, if_match=connection["modified"], expect=412)
    api._call("DELETE", f"/connections/{cid}", 204)
    api.get(f"/connections/{cid}", expect=404)


def test_route_permissions(world, client):
    viewer, contributor = Api(client, "viewer"), Api(client, "contributor")
    body = {
        "integration_id": FAKE,
        "name": "x",
        "config": {"dataset": "acme"},
        "auth_kind": "fields",
    }
    viewer.post("/connections", body, expect=403)
    contributor.post("/connections", body, expect=403)
    cid = world["api"].post("/connections", body)["id"]
    viewer.post(f"/connections/{cid}/collections", expect=403)
    contributor.post(f"/connections/{cid}/validate", expect=202)
    assert viewer.get("/connections")["data"][0]["id"] == cid
    Api(client, "agent").post(f"/integrations/{FAKE}/templates/mfa-enforcement/enable", expect=403)


# --- Scheduling (RFC 0005 section 6) ---------------------------------------------------------

SYSTEM = PRINCIPALS["administrator"]


def test_scheduler_runs_due_pairs_and_collects_fresh_snapshots(world, clock):
    c, api = world["c"], world["api"]
    test = rule_test(api)
    assert run(c.scheduler.tick(SYSTEM)) == []  # nothing bound yet

    connect(c, world["component"])
    (job,) = run(c.scheduler.tick(SYSTEM))
    assert (job.type, job.status) == ("test_run", "succeeded")
    assert run(c.scheduler.tick(SYSTEM)) == []  # the result is current

    clock.offset += timedelta(hours=21)
    assert run(c.scheduler.tick(SYSTEM)) == []  # inside the daily cadence
    clock.offset += timedelta(hours=2)
    (job,) = run(c.scheduler.tick(SYSTEM))
    result = api.get(f"/results/{job.result_id}")
    assert result["test_ref"] == test["id"]
    # The day-old snapshot is past the reuse window, so the run collected again.
    assert len(run(c.integrations.list_snapshots(ADMIN, None, USERS))) == 2


def test_scheduler_skips_event_driven_and_other_runners(world):
    c, api = world["c"], world["api"]
    connect(c, world["component"])
    test = rule_test(api)
    api.patch(f"/tests/{test['id']}", {"interval": "event-driven"}, if_match=test["modified"])
    api.post(
        "/tests",
        {
            "name": "shell",
            "control_ref": C1,
            "method": "automated",
            "interval": "daily",
            "run": {"runner": "shell", "command": "true"},
        },
    )
    assert run(c.scheduler.tick(SYSTEM)) == []


# --- Bring-your-own OAuth and AWS roles (RFC 0005 section 5) -----------------------------------


def oauth_connection(c, component: str):
    connection = run(
        c.integrations.create_connection(
            ADMIN,
            ConnectionWrite(
                integration_id=FAKE,
                name="Fake OAuth",
                config={"dataset": "acme"},
                auth_kind="oauth2",
                bindings=[component],
            ),
        )
    )
    for name, value in zip(("OAUTH_CLIENT_ID", "OAUTH_CLIENT_SECRET"), Vendor.CLIENT, strict=True):
        run(c.integrations.put_secret(ADMIN, connection.id, name, SecretWrite(value=value)))
    return connection


def test_oauth_flow_end_to_end(world, client, vendor):
    c, api = world["c"], world["api"]
    connection = oauth_connection(c, world["component"])

    start = api.post(f"/connections/{connection.id}/oauth/start", expect=200)
    url = start["authorize_url"]
    assert url.startswith("http://localhost/acme/authorize?")
    query = dict(parse_qsl(urlsplit(url).query))
    assert query["redirect_uri"] == "https://grc.acme.test/v1/oauth/callback"
    assert (query["scope"], query["code_challenge_method"]) == ("users.read", "S256")

    page = client.get("/v1/oauth/callback", params=vendor.authorize(url))
    assert page.status_code == 200, page.text
    assert "Fake OAuth is authorized" in page.text
    connection = api.get(f"/connections/{connection.id}")
    assert "OAUTH_REFRESH_TOKEN" in connection["secrets_set"]
    assert "refresh-0" not in str(connection)

    # Each operation refreshes; the vendor rotates the refresh token every time.
    assert (
        api.post(f"/connections/{connection['id']}/validate", expect=202)["status"] == "succeeded"
    )
    assert (
        api.post(f"/connections/{connection['id']}/collections", expect=202)["status"]
        == "succeeded"
    )
    assert vendor.refresh == 2

    # The state was single use.
    replay = client.get("/v1/oauth/callback", params={"state": query["state"], "code": "x"})
    assert replay.status_code == 400
    assert "already used" in replay.text


def test_oauth_refusals(world, client, vendor, clock):
    c, api = world["c"], world["api"]
    connection = oauth_connection(c, world["component"])

    url = api.post(f"/connections/{connection.id}/oauth/start", expect=200)["authorize_url"]
    denied = client.get(
        "/v1/oauth/callback",
        params={"state": vendor.authorize(url)["state"], "error": "access_denied"},
    )
    assert (denied.status_code, "the vendor refused: access_denied" in denied.text) == (400, True)

    url = api.post(f"/connections/{connection.id}/oauth/start", expect=200)["authorize_url"]
    clock.offset += timedelta(minutes=11)
    late = client.get("/v1/oauth/callback", params=vendor.authorize(url))
    assert "expired" in late.text

    vendor.issue_refresh = False
    url = api.post(f"/connections/{connection.id}/oauth/start", expect=200)["authorize_url"]
    no_refresh = client.get("/v1/oauth/callback", params=vendor.authorize(url))
    assert "no refresh token" in no_refresh.text
    assert api.get(f"/connections/{connection.id}")["state"] == "failing"

    assert (
        client.get("/v1/oauth/callback", params={"state": "forged", "code": "x"}).status_code == 400
    )
    # A client secret is writable; the refresh token is not.
    api._call(
        "PUT", f"/connections/{connection.id}/secrets/OAUTH_REFRESH_TOKEN", 404, json={"value": "x"}
    )


def test_oauth_needs_a_public_url(make_app, clock):
    no_url, container = make_app(clock=clock, public_url=None)
    api = Api(no_url, "administrator")
    component = api.post("/components", {"name": "IdP", "kind": "software"})
    connection = oauth_connection(container, component["id"])
    problem = api.post(f"/connections/{connection.id}/oauth/start", expect=400)
    assert problem["type"] == "urn:ogrl:problem:oauth-needs-public-url"


def test_aws_role_connections_assume_with_the_external_id(world, assumer):
    api = world["api"]
    arn = "arn:aws:iam::123456789012:role/ogrl-readonly"
    connection = api.post(
        "/connections",
        {
            "integration_id": FAKE,
            "name": "Fake AWS",
            "config": {"dataset": "acme", "aws_role_arn": arn},
            "auth_kind": "aws_role",
            "bindings": [world["component"]],
        },
    )
    assert len(connection["external_id"]) >= 32
    assert (
        api.post(f"/connections/{connection['id']}/validate", expect=202)["status"] == "succeeded"
    )
    ((role, external_id, session),) = assumer.calls
    assert (role, external_id) == (arn, connection["external_id"])
    assert session.startswith("ogrl-")

    bad = api.post(
        "/connections",
        {
            "integration_id": FAKE,
            "name": "x",
            "config": {"dataset": "acme"},
            "auth_kind": "aws_role",
        },
        expect=400,
    )
    assert bad["errors"][0]["pointer"] == "/config/aws_role_arn"
