"""Restore, RFC 0002 section 8.1.

Runs once, into a database with no organization objects. Every check happens
before anything is stored: the manifest, the pinned library revision, each
provider copy against its pinned digest, and the whole graph under RFC 0001.
A refusal names the object. Objects are stored as they are: the id,
`created`, `modified`, and `created_by_ref` do not change, and history starts
at the restore.

Bytes come back after the objects. A relative `resource.uri` is read from
the snapshot, an absolute one is fetched, and bytes whose sha-256 matches are
copied into this deployment's storage. The object keeps its URI; the store
records where the copy lives, so the content route still serves it.
"""

import asyncio
import shutil
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel

from opengrc.access import Authorizer, Permission, Principal, require
from opengrc.errors import Conflict, Invalid
from opengrc.kernel import bundles, constraints, ids
from opengrc.kernel.graph import Graph
from opengrc.kernel.models import Envelope
from opengrc.kernel.timeutil import now, utc
from opengrc.operations.jobs import JobOutcome, JobService
from opengrc.operations.library import check_library
from opengrc.operations.providers import check_projection
from opengrc.operations.records import LIBRARY, Job, LibraryPin, ProviderPin, provider_source
from opengrc.operations.sources import Fetcher, Git, LibrarySource
from opengrc.operations.store import BlobStore, ObjectStore
from opengrc.renderer.snapshot import BODY_SUFFIX

ALIAS_PREFIX = "blob-alias:"


class RestoreRequest(BaseModel):
    url: str
    commit: str | None = None


def is_git(url: str) -> bool:
    path = Path(url)
    return (
        url.endswith(".git")
        or url.startswith(("git@", "ssh://", "git://"))
        or (urlparse(url).scheme in ("", "file") and path.is_dir())
    )


class Snapshot:
    def __init__(self, manifest: dict, organization: list[Envelope], root: Path | None,
                 providers: dict[str, list[Envelope]]) -> None:
        self.manifest = manifest
        self.organization = organization
        self.root = root
        self.providers = providers


def read_tree(root: Path) -> Snapshot:
    """The layout in RFC 0002 section 8, at one commit."""
    try:
        manifest = bundles.read_manifest(bundles.load_text((root / "bundle.yaml").read_bytes()))
    except (OSError, bundles.BundleError) as exc:
        raise Invalid(f"the snapshot has no readable bundle.yaml: {exc}") from exc
    organization: list[Envelope] = []
    for path in sorted(root.glob("*/*.yaml")):
        if path.parts[-2] == "provider" or path.name.startswith("."):
            continue
        try:
            organization.append(bundles.parse_object(bundles.load_text(path.read_bytes()), str(path)))
        except bundles.BundleError as exc:
            raise Invalid(f"the snapshot is refused at {exc.object_id or path.name}: {exc}") from exc
    providers: dict[str, list[Envelope]] = {}
    for pin in manifest.get("providers", []) or []:
        bundle_id = pin.get("id", "")
        _, remainder = ids.split(bundle_id)
        tree = root / "provider" / remainder
        objects = []
        for path in sorted(tree.rglob("*.yaml")):
            try:
                objects.append(bundles.parse_object(bundles.load_text(path.read_bytes()), str(path)))
            except bundles.BundleError as exc:
                raise Invalid(f"provider copy {bundle_id} is refused: {exc}") from exc
        providers[bundle_id] = objects
    return Snapshot(manifest, organization, root, providers)


def read_exchange(content: bytes) -> Snapshot:
    """The same objects as one exchange-form bundle. Provider copies ride inline on each pin."""
    try:
        manifest, organization = bundles.read_exchange(content)
        providers = {
            pin["id"]: [bundles.parse_object(o) for o in pin.get("objects", [])]
            for pin in manifest.get("providers", []) or []
        }
    except (bundles.BundleError, KeyError) as exc:
        raise Invalid(f"the snapshot is refused: {exc}") from exc
    return Snapshot(manifest, organization, None, providers)


class RestoreService:
    def __init__(
        self,
        store: ObjectStore,
        blobs: BlobStore,
        authorizer: Authorizer,
        jobs: JobService,
        library: LibrarySource,
        fetcher: Fetcher,
        git: Git,
        clock: Callable[[], datetime] = now,
    ) -> None:
        self._store = store
        self._blobs = blobs
        self._authorizer = authorizer
        self._jobs = jobs
        self._library = library
        self._fetcher = fetcher
        self._git = git
        self._clock = clock

    async def restore(self, principal: Principal, request: RestoreRequest) -> Job:
        require(self._authorizer, principal, Permission.RESTORE_RUN)
        if await self._store.has_organization_objects():
            raise Conflict("the database already holds organization objects", slug="not-empty")

        async def work(job: Job) -> JobOutcome:
            workdir = Path(tempfile.mkdtemp(prefix="ogrc-restore-"))
            try:
                return await self._restore(principal, request, workdir)
            finally:
                shutil.rmtree(workdir, ignore_errors=True)

        return await self._jobs.submit(principal, "restore", request.model_dump(exclude_none=True), work)

    async def _read(self, request: RestoreRequest, workdir: Path) -> Snapshot:
        if is_git(request.url):
            try:
                await self._git.clone(request.url, workdir / "snapshot", request.commit)
            except ValueError as exc:
                raise Invalid(f"could not read {request.url}: {exc}") from exc
            return await asyncio.to_thread(read_tree, workdir / "snapshot")
        try:
            content = await self._fetcher.fetch(request.url)
        except ValueError as exc:
            raise Invalid(f"could not read {request.url}: {exc}") from exc
        return read_exchange(content)

    async def _restore(self, principal: Principal, request: RestoreRequest, workdir: Path) -> JobOutcome:
        snapshot = await self._read(request, workdir)

        # Step 2: the library revision the manifest pins.
        pinned = snapshot.manifest.get("library") or {}
        library: list[Envelope] = []
        library_pin: LibraryPin | None = None
        if pinned:
            try:
                revision = await self._library.checkout(pinned.get("version"), pinned.get("commit"))
                _, library = await asyncio.to_thread(bundles.read_directory, revision.root)
            except (ValueError, bundles.BundleError) as exc:
                raise Invalid(f"the pinned library could not be loaded: {exc}") from exc
            check_library(library)
            library_pin = LibraryPin(version=revision.version, commit=revision.commit)

        # Step 3: each provider copy, against its pinned digest.
        provider_pins: list[tuple[ProviderPin, list[Envelope]]] = []
        base = Graph(library, [o.id for o in library])
        for pin_body in snapshot.manifest.get("providers", []) or []:
            pin = ProviderPin.model_validate({k: v for k, v in pin_body.items() if k != "objects"})
            objects = snapshot.providers.get(pin.id, [])
            if pin.projection_digest and bundles.projection_digest(objects) != pin.projection_digest:
                raise Invalid(f"the copy of provider {pin.id} does not match its pinned digest")
            check_projection(provider_source(pin.id), objects, base)
            base = Graph([*base.objects.values(), *objects], base.library_ids,
                         {*base.provider_ids, *(o.id for o in objects)})
            provider_pins.append((pin, objects))

        # Step 4: the whole graph, as a self-contained bundle.
        organization = snapshot.organization
        graph = Graph([*base.objects.values(), *organization], base.library_ids, base.provider_ids)
        for obj in organization:
            if obj.id in base.objects:
                raise Invalid(f"{obj.id} is both an organization object and a projection row")
            violations = constraints.check(obj, graph, "organization")
            if violations:
                first = violations[0]
                raise Invalid(f"the snapshot is refused at {obj.id}{first.pointer}: {first.detail}")

        # Steps 5 and 6: store, then record the pins.
        at = utc(self._clock())
        if library_pin is not None:
            await self._store.replace_projection(LIBRARY, library, at, principal.actor_id,
                                                 library_pin=library_pin)
        for pin, objects in provider_pins:
            await self._store.replace_projection(provider_source(pin.id), objects, at,
                                                 principal.actor_id, provider_pin=pin)
        await self._store.restore(organization, principal.actor_id, at)

        missing = await self._bytes(snapshot, organization)
        return JobOutcome(report={
            "objects": len(organization),
            "library": library_pin.model_dump(exclude_none=True) if library_pin else None,
            "providers": [p.id for p, _ in provider_pins],
            "missing_bytes": missing,
        })

    async def _bytes(self, snapshot: Snapshot, organization: list[Envelope]) -> list[str]:
        """Copy evidence bytes and document bodies; report what could not be found or did not match."""
        missing: list[str] = []
        for obj in organization:
            resource = getattr(obj, "resource", None)
            if resource is None or not resource.uri or resource.digest is None:
                continue
            content = await self._find(snapshot, obj, resource.uri)
            if content is None or bundles.digest(content) != resource.digest.value:
                missing.append(obj.id)
                continue
            local = await self._blobs.put(
                f"{obj.type}/{obj.id}/{resource.digest.value}", content,
                resource.media_type or "application/octet-stream",
            )
            if local != resource.uri:
                await self._store.set_meta(ALIAS_PREFIX + resource.uri, local)
        return missing

    async def _find(self, snapshot: Snapshot, obj: Envelope, uri: str) -> bytes | None:
        if await self._blobs.get(uri) is not None:
            return await self._blobs.get(uri)
        if snapshot.root is not None:
            kind, remainder = ids.split(obj.id)
            beside = snapshot.root / kind / f"{remainder}{BODY_SUFFIX}"
            if beside.is_file():
                return beside.read_bytes()
            if "://" not in uri:
                candidate = (snapshot.root / uri).resolve()
                if snapshot.root.resolve() in candidate.parents and candidate.is_file():
                    return candidate.read_bytes()
        if "://" in uri:
            try:
                return await self._fetcher.fetch(uri)
            except ValueError:
                return None
        return None
