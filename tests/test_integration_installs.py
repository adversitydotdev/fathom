"""Installing integration archives, upgrades, rollbacks, and template updates (RFC 0005 s4, s8)."""

import asyncio
import gzip
import hashlib
import io
import json
import shutil
import tarfile
from pathlib import Path

import pytest
import yaml

from ogrl import container
from ogrl.integrations.archive import unpack
from ogrl.integrations.host import SubprocessHost
from ogrl.integrations.manifest import PackageError
from tests.conftest import C1, LIB_TEST, PRINCIPALS, Api

FAKE = Path(__file__).parent / "integrations" / "fake"
SDK_ARCHIVE = Path(__file__).parent / "integrations" / "archives" / "dev.ogrl.sdkdemo-0.1.0.tar.gz"
ID = "dev.ogrl.fake2"
ADMIN = PRINCIPALS["administrator"]


def build(tmp: Path, version: str, edit=None) -> bytes:
    """The fake package as `dev.ogrl.fake2` at `version`, as a .tar.gz."""
    root = tmp / f"pkg-{version}-{len(list(tmp.iterdir()))}"
    shutil.copytree(FAKE, root)
    manifest = yaml.safe_load((root / "manifest.yaml").read_text())
    manifest["id"], manifest["version"] = ID, version
    for template in manifest["templates"]:
        template["test"]["run"]["source"] = f"{ID}/users@1"
    if edit:
        edit(manifest)
    (root / "manifest.yaml").write_text(yaml.safe_dump(manifest))
    code = (root / "fake_integration.py").read_text()
    code = code.replace('"dev.ogrl.fake", "0.1.0"', f'"{ID}", "{version}"')
    (root / "fake_integration.py").write_text(code)
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for path in sorted(root.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                tar.add(path, arcname=path.relative_to(root).as_posix())
    return gzip.compress(raw.getvalue(), mtime=0)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def app(make_app, tmp_path):
    return make_app(allow_local_integrations=True, integration_cache=tmp_path / "cache")


@pytest.fixture
def api(app, pulled) -> Api:
    return pulled


def install(api: Api, tmp_path: Path, content: bytes, **body) -> dict:
    path = tmp_path / f"archive-{hashlib.sha256(content).hexdigest()[:8]}.tar.gz"
    path.write_bytes(content)
    return api.post("/integrations", {"url": str(path), **body}, expect=202)


def test_install_from_a_url_and_list_versions(api, tmp_path):
    content = build(tmp_path, "0.1.0")
    job = install(api, tmp_path, content, digest=hashlib.sha256(content).hexdigest())
    assert job["status"] == "succeeded", job
    assert job["report"] == {
        "id": ID,
        "version": "0.1.0",
        "digest": hashlib.sha256(content).hexdigest(),
        "enabled": True,
    }
    view = api.get(f"/integrations/{ID}")
    assert (view["version"], view["tier"]) == ("0.1.0", "local")
    (version,) = api.get(f"/integrations/{ID}/versions")["data"]
    assert (version["enabled"], version["installed_by"]) == (True, ADMIN.actor_id)

    # Reinstalling the same bytes is a no-op; other bytes under the same version are refused.
    assert install(api, tmp_path, content)["status"] == "succeeded"
    other = install(api, tmp_path, build(tmp_path, "0.1.0", lambda m: m.update(name="Other")))
    assert other["error"]["type"] == "urn:ogrl:problem:version-immutable"


def test_install_refusals(make_app, api, tmp_path):
    content = build(tmp_path, "0.1.0")
    wrong = install(api, tmp_path, content, digest="0" * 64)
    assert wrong["error"]["type"] == "urn:ogrl:problem:digest-mismatch"

    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        info = tarfile.TarInfo("../escape.py")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    bad = install(api, tmp_path, gzip.compress(raw.getvalue()))
    assert bad["error"]["type"] == "urn:ogrl:problem:bad-package"

    def as_directory_package(manifest):
        manifest["id"] = "dev.ogrl.fake"
        manifest["templates"][0]["test"]["run"]["source"] = "dev.ogrl.fake/users@1"

    clash = install(api, tmp_path, build(tmp_path, "0.1.0", as_directory_package))
    assert clash["error"]["type"] == "urn:ogrl:problem:static-integration"

    strict, _ = make_app(allow_local_integrations=False)
    job = install(Api(strict, "administrator"), tmp_path, content)
    assert job["error"]["type"] == "urn:ogrl:problem:untrusted-integration"

    Api(api.client, "contributor").post("/integrations", {"url": "x"}, expect=403)


def test_upgrade_with_template_update_breaking_refusal_and_rollback(api, tmp_path):
    assert install(api, tmp_path, build(tmp_path, "0.1.0"))["status"] == "succeeded"
    test = api.post(f"/integrations/{ID}/templates/mfa-enforcement/enable", expect=201)
    assert test["run"]["assert"] == "item.mfa"
    assert api.get(f"/integrations/{ID}/template-updates")["data"] == []

    def stricter(manifest):
        manifest["templates"][0]["test"]["run"]["assert"] = "item.mfa && item.admin != null"

    assert install(api, tmp_path, build(tmp_path, "0.2.0", stricter))["status"] == "succeeded"
    (update,) = api.get(f"/integrations/{ID}/template-updates")["data"]
    assert (update["test_id"], update["from_version"], update["to_version"]) == (
        test["id"],
        "0.1.0",
        "0.2.0",
    )
    assert update["changes"] == ["run"]
    applied = api.post(
        f"/integrations/{ID}/template-updates/{test['id']}/apply",
        if_match=update["modified"],
        expect=200,
    )
    assert applied["run"]["assert"] == "item.mfa && item.admin != null"
    assert applied["extensions"]["dev.ogrl.integration"]["version"] == "0.2.0"
    assert api.get(f"/integrations/{ID}/template-updates")["data"] == []

    def renamed(manifest):
        manifest["resources"][0]["version"] = 2
        manifest["templates"][0]["test"]["run"]["source"] = f"{ID}/users@2"

    breaking = install(api, tmp_path, build(tmp_path, "0.3.0", renamed))
    assert breaking["error"]["type"] == "urn:ogrl:problem:upgrade-breaks-tests"
    assert test["id"] in breaking["error"]["detail"]
    versions = {v["version"]: v["enabled"] for v in api.get(f"/integrations/{ID}/versions")["data"]}
    assert versions == {"0.1.0": False, "0.2.0": True, "0.3.0": False}
    api.post(f"/integrations/{ID}/versions/0.3.0/enable", expect=409)

    assert api.post(f"/integrations/{ID}/versions/0.1.0/enable", expect=200)["version"] == "0.1.0"
    api.post(f"/integrations/{ID}/versions/9.9.9/enable", expect=404)


def test_another_process_loads_what_this_one_enabled(app, api, tmp_path, make_app):
    _, c = app
    assert install(api, tmp_path, build(tmp_path, "0.1.0"))["status"] == "succeeded"
    other = container.build(
        authenticator=c.authenticator,
        store=c.store,
        blobs=c.blobs,
        connections=c.integrations._store,
        allow_local_integrations=True,
        integration_cache=tmp_path / "other-cache",
    )
    assert [v.id for v in run(other.integrations.list_integrations(ADMIN))] == [ID]
    assert (tmp_path / "other-cache").is_dir()


def test_an_sdk_built_archive_runs_from_its_bundled_wheel(api, tmp_path, app):
    _, c = app
    content = SDK_ARCHIVE.read_bytes()
    job = api._call(
        "POST",
        "/integrations/archives",
        202,
        files={"file": ("sdkdemo.tar.gz", content, "application/gzip")},
        data={"digest": hashlib.sha256(content).hexdigest()},
    )
    assert job["status"] == "succeeded", job
    package = c.integrations.package("dev.ogrl.sdkdemo")
    assert any(p.suffix == ".whl" for p in (package.root / "wheels").iterdir())
    snapshot = {"items": [{"id": "1", "name": "alpha", "enabled": False}]}
    out = run(
        SubprocessHost().check(
            package,
            "all-enabled",
            1,
            {},
            {},
            {"dev.ogrl.sdkdemo/items@1": json.dumps(snapshot).encode()},
            30,
        )
    )
    assert (out.outcome, out.summary) == ("fail", "1 of 1 items are disabled")


def test_template_tests_still_run_after_install(api, tmp_path, app, program):
    """An installed package drives a rule run end to end, like a directory one."""
    _, c = app
    assert install(api, tmp_path, build(tmp_path, "0.1.0"))["status"] == "succeeded"
    component = api.post("/components", {"name": "IdP", "kind": "software"})
    impl = api.post(
        "/implementations",
        {
            "component_ref": component["id"],
            "control_ref": C1,
            "status": "implemented",
            "responsibility": "customer",
        },
    )
    connection = api.post(
        "/connections",
        {
            "integration_id": ID,
            "name": "fake2",
            "config": {"dataset": "acme"},
            "auth_kind": "fields",
            "bindings": [component["id"]],
        },
    )
    api._call(
        "PUT", f"/connections/{connection['id']}/secrets/FAKE_TOKEN", 200, json={"value": "s3cret"}
    )
    test = api.post(f"/integrations/{ID}/templates/mfa-enforcement/enable", expect=201)
    assert test["fulfills_ref"] == LIB_TEST
    job = api.post(f"/tests/{test['id']}/runs", {"implementation_id": impl["id"]}, expect=202)
    result = api.get(f"/results/{job['result_id']}")
    assert (result["outcome"], result["summary"]) == ("fail", "1 of 2 selected items pass")


@pytest.mark.parametrize(
    ("name", "kind"),
    [("/abs.py", tarfile.REGTYPE), ("a/../../b.py", tarfile.REGTYPE), ("link", tarfile.SYMTYPE)],
)
def test_unpack_refuses_unsafe_entries(tmp_path, name, kind):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        info = tarfile.TarInfo(name)
        info.type = kind
        info.linkname = "/etc/passwd" if kind == tarfile.SYMTYPE else ""
        tar.addfile(info, io.BytesIO(b"") if kind == tarfile.REGTYPE else None)
    with pytest.raises(PackageError):
        unpack(gzip.compress(raw.getvalue()), tmp_path / "out")
