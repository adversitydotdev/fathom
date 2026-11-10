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

from pydantic import BaseModel, model_validator

from opengrc.access import Authorizer, Permission, Principal, require
from opengrc.errors import Invalid
from opengrc.kernel import bundles, constraints, status
from opengrc.kernel.graph import Graph
from opengrc.kernel.models import (
    LIBRARY_TYPES,
    Baseline,
    Control,
    Envelope,
    Mapping,
    Origin,
    Program,
)
from opengrc.kernel.timeutil import now, utc
from opengrc.operations.jobs import JobOutcome, JobService
from opengrc.operations.records import LIBRARY, Job, LibraryPin
from opengrc.operations.sources import LibrarySource
from opengrc.operations.store import ObjectStore


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
    graph = Graph(objects, library_ids=[o.id for o in objects])
    for obj in objects:
        if obj.type not in LIBRARY_TYPES:
            raise Invalid(f"{obj.id}: a {obj.type} is not a library object")
        if isinstance(obj, Control) and obj.origin is not Origin.STANDARD:
            raise Invalid(f"{obj.id}: library controls have origin standard")
        violations = constraints.check(obj, graph, LIBRARY)
        if violations:
            first = violations[0]
            raise Invalid(f"{obj.id}{first.pointer}: {first.detail}")


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
    moved: list[dict] = []
    for program in before.all(Program):
        old = status.evaluate(before, program, at)
        new = status.evaluate(after, program, at)
        old_controls = {c.control_id: c.state for c in old.controls}
        new_controls = {c.control_id: c.state for c in new.controls}
        old_reqs = {r.requirement_id: r.state for r in old.requirements}
        new_reqs = {r.requirement_id: r.state for r in new.requirements}
        controls = [
            {"control_id": c, "before": old_controls.get(c), "after": new_controls.get(c)}
            for c in sorted(set(old_controls) | set(new_controls))
            if old_controls.get(c) != new_controls.get(c)
        ]
        requirements = [
            {"requirement_id": r, "before": old_reqs.get(r), "after": new_reqs.get(r)}
            for r in sorted(set(old_reqs) | set(new_reqs))
            if old_reqs.get(r) != new_reqs.get(r)
        ]
        if controls or requirements:
            moved.append(
                {"program_id": program.id, "controls": controls, "requirements": requirements}
            )

    stale: list[str] = []
    for mapping_id, reviews in before.reviews_by_mapping.items():
        old_mapping = before.typed(mapping_id, Mapping)
        new_mapping = after.typed(mapping_id, Mapping)
        for review in reviews:
            was_current = (
                old_mapping is not None and review.mapping_modified == old_mapping.modified
            )
            still = (
                new_mapping is not None
                and not new_mapping.is_revoked
                and review.mapping_modified == new_mapping.modified
            )
            if was_current and not still:
                stale.append(review.id)

    withdrawn: list[dict] = []
    for baseline in after.all(Baseline):
        for ref in baseline.requirement_refs or []:
            old_req, new_req = before.requirement(ref), after.requirement(ref)
            if new_req and new_req.is_withdrawn and not (old_req and old_req.is_withdrawn):
                withdrawn.append({"baseline_id": baseline.id, "requirement_id": ref})

    return {
        "at": at.isoformat(),
        "programs": moved,
        "stale_reviews": sorted(stale),
        "withdrawn": withdrawn,
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
            check_library(objects)
            at = utc(self._clock())
            before = await self._store.graph()
            report = compare(before, with_library(before, objects), at)
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
