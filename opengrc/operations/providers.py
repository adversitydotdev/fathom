"""Provider import, RFC 0002 section 7.

The organization picks a bundle revision. The job reads it, checks it, and
replaces that provider's projection and pin in one store operation. It does
not touch the library projection, another provider's projection, or any
organization object. Attaching the component to a system is the
organization's own `PATCH /systems/{id}`.
"""

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from opengrc.access import Authorizer, Permission, Principal, require
from opengrc.errors import FieldError, Invalid, NotFound
from opengrc.kernel import bundles, constraints, ids
from opengrc.kernel.graph import Graph
from opengrc.kernel.models import PROVIDER_TYPES, Envelope, Test
from opengrc.kernel.timeutil import now, utc
from opengrc.operations.jobs import JobOutcome, JobService
from opengrc.operations.records import Job, ProviderPin, provider_source
from opengrc.operations.sources import Fetcher
from opengrc.operations.store import ObjectStore
from opengrc.plugins import Plugins


class ProviderImportRequest(BaseModel):
    kind: Literal["opengrc", "oscal-component"]
    url: str
    version: str | None = None
    digest: str | None = None


def normalize_digest(value: str) -> str:
    return value.removeprefix("sha-256:").lower()


def _newer(left: str | None, right: str | None) -> bool:
    def key(v: str) -> tuple[int, ...]:
        return tuple(int(p) if p.isdigit() else 0 for p in v.split("."))

    return bool(left and right and key(left) > key(right))


def check_projection(source: str, objects: list[Envelope], current: Graph) -> None:
    """Every object is a provider type in the provider id space, and the graph holds."""
    seen: set[str] = set()
    for obj in objects:
        if obj.type not in PROVIDER_TYPES:
            raise Invalid(f"{obj.id}: a provider bundle does not carry a {obj.type}")
        if ids.is_reserved(obj.id):
            raise Invalid(f"{obj.id}: a provider does not mint ids in the standard-library space")
        if isinstance(obj, Test) and obj.run is not None:
            raise Invalid(f"{obj.id}: a provider test describes a check and has no run")
        if obj.id in seen:
            raise Invalid(f"{obj.id} appears twice")
        seen.add(obj.id)
    others = [o for o in current.objects.values() if o.id not in seen]
    provider_ids = {*current.provider_ids, *seen}
    graph = Graph([*others, *objects], current.library_ids, provider_ids)
    for obj in objects:
        violations = constraints.check(obj, graph, "provider")
        if violations:
            first = violations[0]
            raise Invalid(f"{obj.id}{first.pointer}: {first.detail}")


class ProviderService:
    def __init__(
        self,
        store: ObjectStore,
        authorizer: Authorizer,
        jobs: JobService,
        fetcher: Fetcher,
        plugins: Plugins,
        clock: Callable[[], datetime] = now,
    ) -> None:
        self._store = store
        self._authorizer = authorizer
        self._jobs = jobs
        self._fetcher = fetcher
        self._plugins = plugins
        self._clock = clock

    async def list(self, principal: Principal) -> list[ProviderPin]:
        require(self._authorizer, principal, Permission.PROGRAMS_READ)
        return await self._store.provider_pins()

    async def get(self, principal: Principal, bundle_id: str) -> ProviderPin:
        for pin in await self.list(principal):
            if pin.id == bundle_id:
                return pin
        raise NotFound(f"no provider bundle {bundle_id}")

    async def import_bundle(self, principal: Principal, request: ProviderImportRequest) -> Job:
        require(self._authorizer, principal, Permission.PROVIDERS_IMPORT)
        importer = self._plugins.importers.get(request.kind)
        if importer is None:
            raise Invalid(errors=[FieldError(f"no importer for {request.kind}", "/kind")])

        async def work(job: Job) -> JobOutcome:
            try:
                content = await self._fetcher.fetch(request.url)
            except ValueError as exc:
                raise Invalid(f"could not read {request.url}: {exc}") from exc
            sha = bundles.digest(content)
            if request.digest and normalize_digest(request.digest) != sha:
                raise Invalid(f"the bundle's sha-256 is {sha}, not {request.digest}")
            current = await self._store.graph()
            try:
                bundle = await asyncio.to_thread(importer.import_bytes, content, current)
            except ValueError as exc:
                raise Invalid(f"the bundle is refused: {exc}") from exc
            pinned = await self._store.library_pin()
            if _newer(bundle.library_version, pinned.version if pinned else None):
                missing = [
                    o.id
                    for o in bundle.objects
                    if getattr(o, "control_ref", None) and current.get(o.control_ref) is None  # type: ignore[attr-defined]
                ]
                if missing:
                    raise Invalid(
                        f"the bundle was written against library {bundle.library_version}, newer "
                        f"than the pinned {pinned.version if pinned else 'none'}; pull first"
                    )
            objects = list(bundle.objects)
            source = provider_source(bundle.id)
            check_projection(source, objects, current)
            pin = ProviderPin(
                id=bundle.id,
                name=bundle.name,
                version=request.version or bundle.version,
                digest=f"sha-256:{sha}",
                kind=request.kind,
                projection_digest=bundles.projection_digest(objects),
            )
            change = await self._store.replace_projection(
                source, objects, utc(self._clock()), principal.actor_id, provider_pin=pin
            )
            return JobOutcome(
                report={
                    "bundle_id": bundle.id,
                    "version": pin.version,
                    "objects": len(objects),
                    "added": len(change.added),
                    "replaced": len(change.replaced),
                    "revoked": change.revoked,
                    "warnings": bundle.warnings,
                }
            )

        return await self._jobs.submit(principal, "provider_import", request.model_dump(exclude_none=True), work)
