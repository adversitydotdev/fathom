"""Library pull, RFC 0002 section 5.

A pull replaces the library projection with one revision, revokes library
ids the revision no longer has, and moves the pin, in one store operation. An
interrupted pull leaves the previous pin. Before it moves the pin, the job
computes every program's status at the old and the new revision on the same
evaluation date and reports what moved, including mapping reviews the pull
made stale and baseline requirements the publisher withdrew.
"""

import asyncio
from collections.abc import Callable
from datetime import datetime

import ogrl_rs
from pydantic import BaseModel, model_validator

from fathom.access import Authorizer, Permission, Principal, require
from fathom.errors import Invalid
from fathom.kernel import bundles
from fathom.kernel.graph import Graph
from fathom.kernel.models import Envelope
from fathom.kernel.timeutil import now, utc
from fathom.operations.jobs import JobOutcome, JobService
from fathom.operations.records import LIBRARY, Job, LibraryPin
from fathom.operations.sources import LibrarySource
from fathom.operations.store import ObjectStore


class LibraryPullRequest(BaseModel):
    """Provide `version` or `commit`."""

    version: str | None = None
    commit: str | None = None

    @model_validator(mode="after")
    def _one(self) -> "LibraryPullRequest":
        if not (self.version or self.commit):
            raise ValueError("provide version or commit")
        return self


def check_library(objects: list[Envelope]) -> None:
    """Every object is a library type, and the revision is a self-contained graph."""
    bodies = [o.body() for o in objects]
    rs_graph = ogrl_rs.OgrlGraph.from_objects(bodies, library_ids=[o.id for o in objects])
    diagnostics = rs_graph.check_all()
    if diagnostics:
        first = diagnostics[0]
        obj_id = first.get("object_id") or ""
        pointer = first.get("pointer") or ""
        detail = first.get("detail") or "invalid library object"
        raise Invalid(f"{obj_id}{pointer}: {detail}")


def with_library(current: Graph, library: list[Envelope]) -> Graph:
    """The current graph with its library projection replaced by `library`."""
    kept = [o for o in current.objects.values() if not current.is_library(o.id)]
    incoming = {o.id for o in library}
    gone = [
        o.model_copy(update={"revoked": True})
        for o in current.objects.values()
        if current.is_library(o.id) and o.id not in incoming
    ]
    objects = [*kept, *library, *gone]
    return Graph(objects, [*incoming, *(o.id for o in gone)], current.provider_ids)


def compare(before: Graph, after: Graph, at: datetime) -> dict:
    """What a revision moves, for every program, at one evaluation date."""
    after_lib = [
        o.body() for o in after.objects.values() if after.is_library(o.id) and not o.is_revoked
    ]
    diff = ogrl_rs.compare_library_revisions(
        [o.body() for o in before.objects.values()],
        after_lib,
        at,
        library_ids=before.library_ids,
        provider_ids=before.provider_ids,
    )
    moved = [
        {
            "program_id": p["program_id"],
            "controls": [
                {"control_id": c["id"], "before": c["before"], "after": c["after"]}
                for c in p.get("controls", [])
            ],
            "requirements": [
                {"requirement_id": r["id"], "before": r["before"], "after": r["after"]}
                for r in p.get("requirements", [])
            ],
        }
        for p in diff.get("programs", [])
    ]
    return {
        "at": at.isoformat(),
        "programs": moved,
        "stale_reviews": diff.get("stale_reviews", []),
        "withdrawn": diff.get("withdrawn", []),
    }


class LibraryService:
    def __init__(
        self,
        store: ObjectStore,
        authorizer: Authorizer,
        jobs: JobService,
        source: LibrarySource,
        clock: Callable[[], datetime] = now,
    ) -> None:
        self._store = store
        self._authorizer = authorizer
        self._jobs = jobs
        self._source = source
        self._clock = clock

    async def pin(self, principal: Principal) -> LibraryPin | None:
        require(self._authorizer, principal, Permission.LIBRARY_READ)
        return await self._store.library_pin()

    async def pull(self, principal: Principal, request: LibraryPullRequest) -> Job:
        require(self._authorizer, principal, Permission.LIBRARY_PULL)

        async def work(job: Job) -> JobOutcome:
            revision = await self._source.checkout(request.version, request.commit)
            try:
                _, objects = await asyncio.to_thread(bundles.read_directory, revision.root)
            except bundles.BundleError as exc:
                raise Invalid(str(exc)) from exc
            await asyncio.to_thread(check_library, objects)
            at = utc(self._clock())
            before = await self._store.graph()
            report = await asyncio.to_thread(compare, before, with_library(before, objects), at)
            pin = LibraryPin(version=revision.version, commit=revision.commit)
            change = await self._store.replace_projection(
                LIBRARY, objects, at, principal.actor_id, library_pin=pin
            )
            report.update(
                version=revision.version,
                commit=revision.commit,
                objects=len(objects),
                added=len(change.added),
                replaced=len(change.replaced),
                revoked=change.revoked,
            )
            return JobOutcome(report=report)

        return await self._jobs.submit(
            principal, "library_pull", request.model_dump(exclude_none=True), work
        )
