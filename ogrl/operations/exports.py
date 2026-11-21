"""Git export, RFC 0002 section 8.

The job clones the configured remote, overwrites the files it owns with the
current snapshot, commits only when the tree changed, and pushes. It never
pulls, merges, or rebases. When the remote has a commit this job did not
write, the job stops and records that the export diverged. A later
`POST /exports/git` checks the remote again before it queues anything, and
answers 409 while the remote still holds a commit this job did not write.
Someone resolves that outside the tool; the database is never updated from
the repository.
"""

import asyncio
import shutil
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from ogrl.access import Authorizer, Permission, Principal, require
from ogrl.errors import Conflict, FeatureDisabled
from ogrl.kernel.models import Envelope
from ogrl.kernel.timeutil import now, utc
from ogrl.operations.connections import ConnectionStore, QueryDefinition
from ogrl.operations.jobs import JobOutcome, JobService
from ogrl.operations.records import PROVIDER_PREFIX, Job
from ogrl.operations.sources import Git
from ogrl.operations.store import BlobStore, ObjectStore
from ogrl.renderer.snapshot import OWNED_TOP_LEVEL, manifest, snapshot

WRITTEN_KEY = "export:written-commits"
DIVERGED_KEY = "export:diverged"


@dataclass(frozen=True)
class ExportSettings:
    remote: str | None
    organization_id: str = "bundle--organization"
    organization_name: str = "Organization"


QUERY_DIR = "ogrl-app/queries"


def query_files(queries: Sequence[QueryDefinition]) -> dict[str, bytes]:
    """Query source definitions as YAML beside the objects (RFC 0006 section 8)."""
    return {
        f"{QUERY_DIR}/{q.integration_id}/{q.name}@{q.version}.yaml": yaml.safe_dump(
            q.model_dump(mode="json", exclude_none=True), sort_keys=True
        ).encode()
        for q in queries
    }


async def organization_snapshot(
    store: ObjectStore,
    blobs: BlobStore,
    settings: ExportSettings,
    at: datetime,
    queries: Sequence[QueryDefinition] = (),
) -> dict[str, bytes]:
    graph = await store.graph()
    organization: list[Envelope] = [
        o for o in graph.objects.values() if graph.is_organization(o.id)
    ]
    providers: dict[str, list[Envelope]] = {}
    for kind in {o.type for o in graph.objects.values()}:
        for row in await store.scan(kind):
            if row.source.startswith(PROVIDER_PREFIX):
                providers.setdefault(row.source.removeprefix(PROVIDER_PREFIX), []).append(row.obj)
    bodies: dict[str, bytes] = {}
    for obj in organization:
        resource = getattr(obj, "resource", None)
        if obj.type in ("policy", "procedure") and resource is not None and resource.uri:
            content = await blobs.get(resource.uri)
            if content is not None:
                bodies[obj.id] = content
    pin = await store.library_pin()
    pins = await store.provider_pins()
    # The manifest's time is the newest object's, not the clock's, so an export
    # of an unchanged program writes an unchanged tree and commits nothing.
    newest = max((o.modified for o in organization), default=at)
    body = manifest(
        settings.organization_id,
        settings.organization_name,
        newest,
        pin.model_dump(exclude_none=True) if pin else None,
        [p.model_dump(exclude_none=True, exclude={"name", "kind"}) for p in pins],
    )
    files = snapshot(body, sorted(organization, key=lambda o: o.id), providers, bodies)
    return {**files, **query_files(queries)}


def write_tree(repo: Path, files: dict[str, bytes]) -> None:
    """Replace the trees the job owns. Files it does not own, such as a README, stay."""
    for name in OWNED_TOP_LEVEL:
        target = repo / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    for path, content in files.items():
        destination = repo / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)


class ExportService:
    def __init__(
        self,
        store: ObjectStore,
        blobs: BlobStore,
        authorizer: Authorizer,
        jobs: JobService,
        git: Git,
        settings: ExportSettings,
        clock: Callable[[], datetime] = now,
        connections: ConnectionStore | None = None,
    ) -> None:
        self._connections = connections
        self._store = store
        self._blobs = blobs
        self._authorizer = authorizer
        self._jobs = jobs
        self._git = git
        self._settings = settings
        self._clock = clock

    async def export(self, principal: Principal) -> Job:
        require(self._authorizer, principal, Permission.EXPORTS_RUN)
        if not self._settings.remote:
            raise FeatureDisabled("no export remote is configured")
        if await self._store.get_meta(DIVERGED_KEY):
            workdir = Path(tempfile.mkdtemp(prefix="ogrl-export-check-"))
            try:
                await self._git.clone(self._settings.remote, workdir / "repo")
                await self._check_diverged(workdir / "repo")
            finally:
                shutil.rmtree(workdir, ignore_errors=True)
            await self._store.set_meta(DIVERGED_KEY, None)
        return await self._jobs.submit(principal, "git_export", {}, self._work)

    async def _check_diverged(self, repo: Path) -> None:
        written = set((await self._store.get_meta(WRITTEN_KEY) or "").split())
        foreign = [c for c in await self._git.ancestors(repo) if c not in written]
        if foreign and written:
            await self._store.set_meta(DIVERGED_KEY, foreign[0])
            raise Conflict(
                f"the export repository has {len(foreign)} commit(s) this job did not write; "
                "resolve it outside the tool",
                slug="export-diverged",
            )

    async def _work(self, job: Job) -> JobOutcome:
        assert self._settings.remote is not None
        workdir = Path(tempfile.mkdtemp(prefix="ogrl-export-"))
        try:
            repo = workdir / "repo"
            await self._git.clone(self._settings.remote, repo)
            written = set((await self._store.get_meta(WRITTEN_KEY) or "").split())
            await self._check_diverged(repo)
            at = utc(self._clock())
            queries = await self._connections.list_queries() if self._connections else []
            files = await organization_snapshot(
                self._store, self._blobs, self._settings, at, queries
            )
            await asyncio.to_thread(write_tree, repo, files)
            commit = await self._git.commit_all(repo, f"OGRL export {at.isoformat()}")
            if commit is None:
                return JobOutcome(report={"changed": False, "files": len(files)})
            await self._git.push(repo)
            history = await self._git.ancestors(repo)
            await self._store.set_meta(WRITTEN_KEY, " ".join(sorted(set(history) | written)))
            return JobOutcome(report={"changed": True, "commit": commit, "files": len(files)})
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
