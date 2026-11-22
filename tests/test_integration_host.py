"""The protocol-1 host against the fake integration in tests/integrations/fake (RFC 0005 s7)."""

import asyncio
import json
from pathlib import Path

import pytest

from ogrl.integrations import host as host_module
from ogrl.integrations.host import SubprocessHost
from ogrl.integrations.manifest import PackageError, load_package
from ogrl.plugins.ports import IntegrationError

FAKE = Path(__file__).parent / "integrations" / "fake"
TOKEN = {"FAKE_TOKEN": "s3cret"}


@pytest.fixture(scope="module")
def package():
    return load_package(FAKE)


def run(coro):
    return asyncio.run(coro)


def test_manifest_loads(package):
    m = package.manifest
    assert (m.id, m.version, package.tier) == ("dev.ogrl.fake", "0.1.0", "local")
    assert (
        m.resource("users", 1) and m.check("admins-have-mfa", 1) and m.template("mfa-enforcement")
    )
    assert package.schema("users", 1)["type"] == "object"


def test_manifest_rejects_bad_packages(tmp_path):
    (tmp_path / "manifest.yaml").write_text(
        (FAKE / "manifest.yaml").read_text().replace("id: dev.ogrl.fake", "id: fake")
    )
    with pytest.raises(PackageError, match="reverse domain"):
        load_package(tmp_path)


def test_validate_and_collect(package):
    host = SubprocessHost()
    report = run(host.validate(package, {"dataset": "acme"}, TOKEN))
    assert report.identity == "acme as svc-ogrl"
    assert list(report.granted_scopes) == ["users.read"]

    collected = run(host.collect(package, "users", 1, {"dataset": "acme"}, TOKEN))
    assert collected.complete is True
    assert [u["id"] for u in collected.items] == ["u1", "u2", "u3"]

    partial = run(
        host.collect(package, "users", 1, {"dataset": "acme", "mode": "incomplete"}, TOKEN)
    )
    assert (partial.complete, partial.reason, len(partial.items)) == (
        False,
        "rate limited after page 1",
        1,
    )


def test_check_gets_snapshots_and_no_credentials(package):
    doc = {
        "source": "dev.ogrl.fake/users@1",
        "items": [{"id": "u1", "name": "a", "status": "ACTIVE", "admin": True, "mfa": False}],
    }
    report = run(
        SubprocessHost().check(
            package,
            "admins-have-mfa",
            1,
            {},
            {},
            {"dev.ogrl.fake/users@1": json.dumps(doc).encode()},
            30,
        )
    )
    assert (report.outcome, report.summary) == ("fail", "1 admins without MFA")
    assert list(report.subjects) == [{"kind": "account", "name": "a", "external_id": "u1"}]


@pytest.mark.parametrize(
    ("mode", "env", "kind", "fragment"),
    [
        ("", {}, "auth_failed", "rejected"),
        ("rate_limited", TOKEN, "rate_limited", "slow down"),
        ("crash", TOKEN, "protocol", "boom: fake crash"),
        ("garbage", TOKEN, "protocol", "not JSON"),
    ],
)
def test_failures_are_integration_errors(package, mode, env, kind, fragment):
    with pytest.raises(IntegrationError) as caught:
        run(SubprocessHost().collect(package, "users", 1, {"dataset": "acme", "mode": mode}, env))
    assert caught.value.kind == kind
    assert fragment in caught.value.message
    if kind == "rate_limited":
        assert caught.value.retry_after == 1


def test_hang_times_out(package, monkeypatch):
    monkeypatch.setattr(host_module, "COLLECT_TIMEOUT", 1)
    with pytest.raises(IntegrationError, match="timed out"):
        run(
            SubprocessHost().collect(
                package, "users", 1, {"dataset": "acme", "mode": "hang"}, TOKEN
            )
        )


def test_version_mismatch_is_refused(package):
    moved = package.manifest.model_copy(update={"version": "9.9.9"})
    stale = type(package)(moved, package.root, package.digest)
    with pytest.raises(IntegrationError, match="installed is dev.ogrl.fake 9.9.9"):
        run(SubprocessHost().validate(stale, {"dataset": "acme"}, TOKEN))


def test_sts_assumer_builds_a_fresh_client_per_call(monkeypatch):
    """A reused STS client stays denied after a trust-policy change (seen against live AWS)."""
    import boto3

    from ogrl.adapters.sts import StsRoleAssumer

    made = []

    class Client:
        def assume_role(self, **kwargs):
            made.append(kwargs["ExternalId"])
            return {
                "Credentials": {"AccessKeyId": "a", "SecretAccessKey": "b", "SessionToken": "c"}
            }

    clients = []

    def factory(service, region_name=None):
        clients.append(Client())
        return clients[-1]

    monkeypatch.setattr(boto3, "client", factory)
    assumer = StsRoleAssumer()
    for external in ("one", "two"):
        run(assumer.assume("arn:aws:iam::123456789012:role/r", external, "ogrl-x"))
    assert made == ["one", "two"]
    assert len(clients) == 2 and clients[0] is not clients[1]
