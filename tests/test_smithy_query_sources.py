"""Smithy query sources (RFC 0007) end to end: search, describe, validate, dry run, collect.

AWS is a local emulator speaking EC2's query protocol for the models in
tests/packages/sdk-aws; the integration is built with the SDK and runs its generic
Smithy executor. The role is assumed by the in-memory assumer, so requests carry
fake SigV4 credentials, which the emulator only checks are present.
"""

import json
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl

import pytest
from ogrl_integration.cli import build_smithy

from tests.conftest import C1, LIB_TEST, Api
from tests.test_integrations import Assumer

PACKAGE = Path(__file__).parent / "packages" / "sdk-aws"
AWS = "dev.ogrl.aws"
ROLE = "arn:aws:iam::123456789012:role/ogrl-readonly"
GROUPS = {
    "us-east-1": [
        ("sg-1", "default", [("22", "0.0.0.0/0")]),
        ("sg-2", "web", [("443", "0.0.0.0/0")]),
    ],
    "eu-west-1": [("sg-3", "default", [])],
}


def _group(group_id: str, name: str, rules: list[tuple[str, str]]) -> str:
    permissions = "".join(
        f"<item><fromPort>{port}</fromPort><cidrIp>{cidr}</cidrIp></item>" for port, cidr in rules
    )
    return (
        f"<item><groupId>{group_id}</groupId><groupName>{name}</groupName>"
        f"<ipPermissions>{permissions}</ipPermissions></item>"
    )


class Emulator(BaseHTTPRequestHandler):
    requests: list[tuple[str, dict[str, str]]] = []

    def log_message(self, *args):  # quiet
        pass

    def _send(self, status: int, body: str):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/xml")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        form = dict(parse_qsl(self.rfile.read(length).decode()))
        region = self.path.strip("/")
        Emulator.requests.append((region, form))
        if not self.headers.get("Authorization", "").startswith("AWS4-HMAC-SHA256 "):
            return self._send(
                403, "<Response><Errors><Error><Code>MissingAuth</Code></Error></Errors></Response>"
            )
        if form.get("Action") == "DescribeVpcs":
            return self._send(
                200,
                "<DescribeVpcsResponse><vpcSet><item><vpcId>vpc-1</vpcId><isDefault>true</isDefault></item>"
                "<item><vpcId>vpc-gone</vpcId></item></vpcSet></DescribeVpcsResponse>",
            )
        if form.get("Action") == "GetSecurityGroupsForVpc":
            if form.get("VpcId") != "vpc-1":
                return self._send(
                    400,
                    "<Response><Errors><Error><Code>InvalidVpcID.NotFound</Code>"
                    "<Message>no such VPC</Message></Error></Errors></Response>",
                )
            return self._send(
                200,
                "<GetSecurityGroupsForVpcResponse><securityGroupForVpcSet><item><groupId>sg-1</groupId>"
                "<groupName>default</groupName></item></securityGroupForVpcSet>"
                "</GetSecurityGroupsForVpcResponse>",
            )
        if form.get("Action") != "DescribeSecurityGroups":
            return self._send(
                400,
                "<Response><Errors><Error><Code>InvalidAction</Code></Error></Errors></Response>",
            )
        if region not in GROUPS:
            return self._send(
                401,
                "<Response><Errors><Error><Code>AuthFailure</Code>"
                "<Message>region not enabled</Message></Error></Errors></Response>",
            )
        groups = GROUPS[region]
        if form.get("Filter.1.Name") == "group-name":
            groups = [g for g in groups if g[1] == form.get("Filter.1.Value.1")]
        body = "".join(_group(*g) for g in groups)
        self._send(
            200,
            '<DescribeSecurityGroupsResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">'
            f"<securityGroupInfo>{body}</securityGroupInfo></DescribeSecurityGroupsResponse>",
        )


@pytest.fixture
def emulator():
    Emulator.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), Emulator)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()


@pytest.fixture
def app(make_app, tmp_path, emulator):
    package = tmp_path / "packages" / "sdk-aws"
    shutil.copytree(PACKAGE, package)
    manifest = package / "manifest.yaml"
    manifest.write_text(manifest.read_text().replace("PORT", str(emulator)))
    build_smithy(package)  # what `ogrl-integration pack` does
    return make_app(integrations_dir=tmp_path / "packages", role_assumer=Assumer())


@pytest.fixture
def world(app, program, pulled: Api):
    component = pulled.post("/components", {"name": "AWS account", "kind": "service"})
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
            "integration_id": AWS,
            "name": "AWS prod",
            "config": {"regions": "us-east-1,eu-west-1", "aws_role_arn": ROLE},
            "auth_kind": "aws_role",
            "bindings": [component["id"]],
        },
    )
    return {"api": pulled, "impl": impl["id"], "connection": connection["id"]}


QUERY = {
    "integration_id": AWS,
    "name": "security-groups",
    "operation": "ec2.DescribeSecurityGroups",
    "regions": "*",
    "fields": {"id": "GroupId", "name": "GroupName", "rules": "IpPermissions"},
}


def test_operations_search_and_describe(world):
    api = world["api"]
    found = api.get(f"/integrations/{AWS}/operations?q=security")["data"]
    # not the write (RevokeSecurityGroupIngress) or the denied read (GetPasswordData)
    assert [o["id"] for o in found] == ["ec2.DescribeSecurityGroups", "ec2.GetSecurityGroupsForVpc"]
    assert (found[0]["protocol"], found[0]["regional"]) == ("ec2Query", True)
    assert found[0]["summary"] == "Describes the specified security groups."

    described = api.get(f"/integrations/{AWS}/operations/ec2.DescribeSecurityGroups")
    assert described["items"] == "SecurityGroups"
    assert described["parameters"] == [
        {"name": "Filters", "in": "json", "required": False, "type": "array of object"}
    ]
    assert {
        "path": "IpPermissions",
        "type": "array of object",
        "items": "SecurityGroups",
    } in described["fields"]
    denied = api.get(f"/integrations/{AWS}/operations/ec2.GetPasswordData")
    assert denied["queryable"] is False and "denies it" in denied["reason"]
    assert api.get(f"/integrations/{AWS}/operations/iam.ListRoles")["regional"] is False


def test_validation_feedback(world):
    api = world["api"]
    check = api.post("/queries/validate", QUERY, expect=200)
    assert check["valid"], check["errors"]
    assert {f["name"]: f["type"] for f in check["fields"]} == {
        "id": "string",
        "name": "string",
        "region": "string",
        "rules": "array",
    }

    def problems(**changes):
        out = api.post("/queries/validate", {**QUERY, **changes}, expect=200)
        return {p["pointer"]: p["detail"] for p in out["errors"]}

    assert problems(regions=None) == {"/regions": 'ec2 is regional: list regions, or "*"'}
    assert problems(params={"Filters": '[{"Nme": "group-name"}]'}) == {
        "/params/Filters": "Filters[0] has no member 'Nme'; did you mean 'Name'?"
    }
    assert "denies it" in problems(operation="ec2.GetPasswordData")["/operation"]
    assert "not a read" in problems(operation="ec2.RevokeSecurityGroupIngress")["/operation"]
    roles = {**QUERY, "operation": "iam.ListRoles", "fields": {"id": "RoleId", "name": "RoleName"}}
    assert problems(**roles) == {"/regions": "iam is global: leave regions out"}
    assert api.post("/queries/validate", {**roles, "regions": None}, expect=200)["valid"]


def test_dry_run_reads_every_region(world):
    api = world["api"]
    params = {"Filters": '[{"Name": "group-name", "Values": ["default"]}]'}
    run = api.post(
        "/queries/dry-run",
        {**QUERY, "params": params, "connection_id": world["connection"]},
        expect=200,
    )
    assert run.get("error") is None, run
    assert [(i["id"], i["region"]) for i in run["items"]] == [
        ("sg-1", "us-east-1"),
        ("sg-3", "eu-west-1"),
    ]
    assert run["items"][0]["rules"] == [{"FromPort": 22, "CidrIp": "0.0.0.0/0"}]
    region, form = Emulator.requests[0]
    assert region == "us-east-1"
    assert form == {
        "Action": "DescribeSecurityGroups",
        "Version": "2016-11-15",
        "Filter.1.Name": "group-name",
        "Filter.1.Value.1": "default",
    }
    assert api.get("/snapshots")["data"] == []


def test_save_collect_run_and_evidence(world):
    api = world["api"]
    saved = api.post("/queries", QUERY, expect=201)
    assert saved["regions"] == "*"
    test = api.post(
        "/tests",
        {
            "name": "No security group is open to the internet",
            "control_ref": C1,
            "fulfills_ref": LIB_TEST,
            "method": "automated",
            "interval": "daily",
            "run": {
                "runner": "rule",
                "source": f"{AWS}/security-groups@1",
                "assert": "!item.rules.exists(r, r.CidrIp == '0.0.0.0/0')",
            },
        },
    )
    job = api.post(f"/tests/{test['id']}/runs", {"implementation_id": world["impl"]}, expect=202)
    result = api.get(f"/results/{job['result_id']}")
    assert (result["outcome"], result["summary"]) == ("fail", "1 of 3 selected items pass")
    assert sorted(s["name"] for s in result["subjects"]) == ["default", "web"]

    (snapshot,) = api.get(f"/snapshots?source={AWS}/security-groups@1")["data"]
    document = json.loads(api.get(f"/snapshots/{snapshot['id']}/content").content)
    assert document["query"]["regions"] == "*"  # the snapshot records its definition
    assert {i["region"] for i in document["items"]} == {"us-east-1", "eu-west-1"}


def test_a_failing_region_makes_the_snapshot_incomplete(world):
    api = world["api"]
    connection = api.get(f"/connections/{world['connection']}")
    api.patch(
        f"/connections/{world['connection']}",
        {"config": {"regions": "us-east-1,ap-east-1", "aws_role_arn": ROLE}},
        if_match=connection["modified"],
    )
    run = api.post("/queries/dry-run", {**QUERY, "connection_id": world["connection"]}, expect=200)
    assert [i["region"] for i in run["items"]] == ["us-east-1", "us-east-1"]

    api.post("/queries", QUERY, expect=201)
    job = api.post(
        f"/connections/{world['connection']}/collections",
        {"sources": [f"{AWS}/security-groups@1"]},
        expect=202,
    )
    assert job["status"] == "succeeded", job
    (snapshot,) = api.get(f"/snapshots?source={AWS}/security-groups@1")["data"]
    assert snapshot["complete"] is False
    assert (
        "ap-east-1" in snapshot["reason"]
        and "AuthFailure: region not enabled" in snapshot["reason"]
    )


def test_for_each_calls_once_per_listed_item(world):
    api = world["api"]
    per_vpc = {
        "integration_id": AWS,
        "name": "groups-per-vpc",
        "operation": "ec2.GetSecurityGroupsForVpc",
        "regions": ["us-east-1"],
        "for_each": {"operation": "ec2.DescribeVpcs", "bind": {"VpcId": "VpcId"}},
        "fields": {
            "id": "GroupId",
            "name": "GroupName",
            "vpc": "$parent.VpcId",
            "default": "$parent.IsDefault",
        },
    }
    check = api.post("/queries/validate", per_vpc, expect=200)
    assert check["valid"], check["errors"]
    assert check["item_schema"]["properties"]["error"] == {"type": ["string", "null"]}
    bad = api.post(
        "/queries/validate",
        {**per_vpc, "for_each": {**per_vpc["for_each"], "bind": {"VpcId": "Vpcid"}}},
        expect=200,
    )
    assert bad["errors"] == [
        {
            "pointer": "/for_each/bind/VpcId",
            "detail": "items have no 'Vpcid'; did you mean 'VpcId'?",
        }
    ]

    run = api.post(
        "/queries/dry-run", {**per_vpc, "connection_id": world["connection"]}, expect=200
    )
    assert run.get("error") is None, run
    assert run["items"] == [
        {
            "id": "sg-1",
            "name": "default",
            "vpc": "vpc-1",
            "default": True,
            "region": "us-east-1",
            "error": None,
        },
        {
            "id": None,
            "name": None,
            "vpc": "vpc-gone",
            "default": None,
            "region": "us-east-1",
            "error": "InvalidVpcID.NotFound",
        },
    ]
    saved = api.post("/queries", per_vpc, expect=201)
    assert saved["for_each"]["bind"] == {"VpcId": "VpcId"}
