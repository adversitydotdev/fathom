"""First-boot seeding: an s3:// tarball of a snapshot restored into an empty database."""

import asyncio
import io
import subprocess
import tarfile
from pathlib import Path

import pytest

from fathom.adapters.fetch import UrlFetcher
from fathom.errors import Invalid
from fathom.main import build_from_env
from fathom.operations.exports import ExportSettings
from fathom.operations.restore import extract_archive
from fathom.operations.seed import seed_organization
from tests.conftest import LIB_BASELINE, Api

URI = "s3://enclave-seed/fathom/bundle.tar.gz"


class FakeS3:
    def __init__(self, objects: dict[tuple[str, str], bytes]) -> None:
        self.objects = objects
        self.reads = 0

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        self.reads += 1
        body = self.objects[(Bucket, Key)]
        return {"Body": io.BytesIO(body), "ContentLength": len(body)}


def run_git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True)


def tarball(root: Path, prefix: str = "") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for path in sorted(root.rglob("*")):
            if ".git" not in path.relative_to(root).parts:
                tar.add(path, arcname=prefix + str(path.relative_to(root)), recursive=False)
    return buffer.getvalue()


@pytest.fixture
def snapshot(make_app, tmp_path: Path) -> tuple[bytes, dict]:
    """An organization with a policy body, exported and packed the way the enclave packs it."""
    remote = tmp_path / "remote.git"
    run_git("init", "--bare", "--quiet", "-b", "main", str(remote))
    client, _ = make_app(export=ExportSettings(remote=str(remote)))
    admin = Api(client, "administrator")
    admin.post("/library/pull", {"version": "0.1.0"}, expect=202)
    owner = admin.post("/parties", {"name": "Lead", "kind": "role"})
    system = admin.post("/systems", {"name": "Prod"})
    admin.post("/programs", {"name": "P", "system_ref": system["id"], "baseline_ref": LIB_BASELINE})
    policy = admin.post(
        "/policies",
        {"name": "Access", "status": "draft", "owner_ref": owner["id"], "adopted": "2026-11-01"},
    )
    uploaded = client.post(
        f"/v1/policies/{policy['id']}/content",
        headers={**admin.headers, "If-Match": policy["modified"]},
        files={"file": ("p.md", io.BytesIO(b"# Access policy"), "text/markdown")},
    )
    admin.patch(f"/policies/{policy['id']}", {"status": "adopted"}, uploaded.json()["modified"])
    admin.post("/exports/git", expect=202)
    checkout = tmp_path / "checkout"
    run_git("clone", "--quiet", str(remote), str(checkout))
    return tarball(checkout), {"system": system, "policy": policy}


def test_seed_restores_once_and_is_a_no_op_after(make_app, snapshot, backend):
    if backend != "memory":
        pytest.skip("drives the seeder on its own event loop")
    archive, made = snapshot
    s3 = FakeS3({("enclave-seed", "fathom/bundle.tar.gz"): archive})
    client, c = make_app(fetcher=UrlFetcher(s3_uris=frozenset({URI}), s3_client=s3))
    admin = Api(client, "administrator")
    assert admin.get("/library") == {}

    job = asyncio.run(seed_organization(c.restore, URI))
    assert job is not None
    assert admin.get("/library")["version"] == "0.1.0"  # the pinned library came with it
    assert admin.get(f"/systems/{made['system']['id']}")["name"] == "Prod"
    body = client.get(f"/v1/policies/{made['policy']['id']}/content", headers=admin.headers)
    assert body.content == b"# Access policy"
    count = len(admin.get("/systems")["data"])

    # A second boot, or a second task, restores nothing and reads nothing.
    reads = s3.reads
    assert asyncio.run(seed_organization(c.restore, URI)) is None
    assert s3.reads == reads
    assert len(admin.get("/systems")["data"]) == count
    jobs = [j for j in admin.get("/jobs")["data"] if j["type"] == "restore"]
    assert len(jobs) == 1


def test_s3_is_readable_only_for_the_configured_uri():
    s3 = FakeS3({("enclave-seed", "other"): b"x", ("enclave-seed", "fathom/bundle.tar.gz"): b"y"})
    fetcher = UrlFetcher(s3_uris=frozenset({URI}), s3_client=s3)
    assert asyncio.run(fetcher.fetch(URI)) == b"y"
    with pytest.raises(ValueError, match="not supported"):
        asyncio.run(fetcher.fetch("s3://enclave-seed/other"))
    with pytest.raises(ValueError, match="not supported"):
        asyncio.run(UrlFetcher(s3_client=s3).fetch(URI))


def test_archive_may_sit_in_one_top_level_directory(tmp_path: Path, snapshot):
    archive, _ = snapshot
    src = tmp_path / "src"
    extract_archive(archive, src)
    nested = tarball(src, prefix="bundle/")
    assert extract_archive(nested, tmp_path / "out").name == "bundle"


def test_archive_refuses_traversal_and_missing_manifest(tmp_path: Path):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo("../escape.yaml")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(Invalid):
        extract_archive(buffer.getvalue(), tmp_path / "a")
    assert not (tmp_path / "escape.yaml").exists()
    with pytest.raises(Invalid, match="bundle.yaml"):
        extract_archive(tarball(tmp_path / "a"), tmp_path / "b")
    with pytest.raises(Invalid):
        extract_archive(b"not a tarball", tmp_path / "c")


def test_the_environment_builds_with_a_seed_uri():
    assert build_from_env({"FATHOM_SEED_BUNDLE_URI": URI}).restore is not None
