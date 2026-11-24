"""Long work is a job (RFC 0004 section 3, RFC 0003 section 2).

A route validates what it can, records a `queued` job, hands the work to an
executor, and returns 202. The client polls `GET /jobs/{id}`. The executor
is a port: `InlineExecutor` finishes the work before the route returns (tests
and the CLI), `BackgroundExecutor` runs it on the event loop beside the API.
A job's failure is a problem+json body on the job, never a 500 on the route.
"""

import asyncio
import logging
import os
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from http import HTTPStatus
from typing import Any, Protocol

from fathom.access import Authorizer, Permission, Principal, require
from fathom.errors import Conflict, FathomError, Invalid, NotFound
from fathom.kernel import ids
from fathom.kernel.timeutil import now, utc
from fathom.operations.pagination import Page, PageInfo, PageRequest, decode_cursor, encode_cursor
from fathom.operations.records import Job, JobProblem, JobStatus, JobType
from fathom.operations.store import BlobStore, ObjectStore

log = logging.getLogger(__name__)

STATUS_OF: dict[str, HTTPStatus] = {
    "Invalid": HTTPStatus.BAD_REQUEST,
    "Forbidden": HTTPStatus.FORBIDDEN,
    "NotFound": HTTPStatus.NOT_FOUND,
    "FeatureDisabled": HTTPStatus.NOT_FOUND,
    "Conflict": HTTPStatus.CONFLICT,
    "PreconditionFailed": HTTPStatus.PRECONDITION_FAILED,
    "UnsupportedMediaType": HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
}


@dataclass
class JobFile:
    name: str
    media_type: str
    content: bytes


@dataclass
class JobOutcome:
    result_id: str | None = None
    files: list[JobFile] = field(default_factory=list)
    report: dict[str, Any] | None = None


Work = Callable[[Job], Awaitable[JobOutcome]]


class Executor(Protocol):
    async def submit(self, run: Callable[[], Awaitable[None]]) -> None: ...


class InlineExecutor:
    async def submit(self, run: Callable[[], Awaitable[None]]) -> None:
        await run()


class BackgroundExecutor:
    """Runs jobs as tasks on the API's loop. Blocking work inside uses threads."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()

    async def submit(self, run: Callable[[], Awaitable[None]]) -> None:
        task = asyncio.create_task(run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)


class QueuedExecutor:
    """Defers job execution to a dedicated `FATHOM_PROCESS=jobs` worker via a wakeup queue."""

    def __init__(self, queue: Any | None = None) -> None:
        self._queue = queue

    async def submit(self, run: Callable[[], Awaitable[None]]) -> None:
        job_id = getattr(run, "job_id", None)
        if self._queue is not None and job_id:
            await self._queue.enqueue(job_id)


def problem_of(exc: BaseException) -> JobProblem:
    if isinstance(exc, FathomError):
        status = STATUS_OF.get(type(exc).__name__, HTTPStatus.INTERNAL_SERVER_ERROR)
        errors = None
        if isinstance(exc, Invalid) and exc.errors:
            errors = [
                {k: v for k, v in (("detail", e.detail), ("pointer", e.pointer)) if v}
                for e in exc.errors
            ]
        return JobProblem(
            type=f"urn:fathom:problem:{exc.slug}",
            title=status.phrase,
            status=status,
            detail=exc.detail or None,
            errors=errors,
        )
    return JobProblem(
        type="urn:fathom:problem:job-failed",
        title=HTTPStatus.INTERNAL_SERVER_ERROR.phrase,
        status=HTTPStatus.INTERNAL_SERVER_ERROR,
        detail=f"{type(exc).__name__}: {exc}",
    )


class JobQuery(PageRequest):
    type: JobType | None = None
    status: JobStatus | None = None


class JobService:
    def __init__(
        self,
        store: ObjectStore,
        blobs: BlobStore,
        authorizer: Authorizer,
        executor: Executor | None = None,
        clock: Callable[[], datetime] = now,
    ) -> None:
        self._store = store
        self._blobs = blobs
        self._authorizer = authorizer
        self._executor = executor or InlineExecutor()
        self._clock = clock
        self._worker = f"{socket.gethostname()}:{os.getpid()}"

    async def submit(
        self,
        principal: Principal,
        job_type: JobType,
        request: dict[str, Any],
        work: Work,
    ) -> Job:
        job = Job(
            id=ids.mint("job"),
            type=job_type,
            status="queued",
            created=utc(self._clock()),
            request=request,
            created_by_ref=principal.actor_id,
        )
        await self._store.save_job(job)

        async def run() -> None:
            await self._run(job, work)

        run.job_id = job.id  # type: ignore[attr-defined]
        await self._executor.submit(run)
        return await self._store.get_job(job.id) or job

    async def run_existing(self, job: Job, work: Work) -> None:
        """Claim and execute an already-persisted queued job (used by `FATHOM_PROCESS=jobs`)."""
        await self._run(job, work)

    async def _run(self, job: Job, work: Work) -> None:
        if not await self._store.claim_job(job.id, self._worker):
            return  # another process took the row first (RFC 0003 section 2)
        await self._store.save_job(job := job.model_copy(update={"status": "running"}))
        try:
            outcome = await work(job)
        except Exception as exc:  # the job records it; the route already returned 202
            if not isinstance(exc, FathomError):
                log.exception("job %s failed", job.id)
            await self._store.save_job(
                job.model_copy(
                    update={
                        "status": "failed",
                        "finished": utc(self._clock()),
                        "error": problem_of(exc),
                    }
                )
            )
            return
        names: list[str] = []
        for file in outcome.files:
            uri = await self._blobs.put(f"jobs/{job.id}/{file.name}", file.content, file.media_type)
            await self._store.set_meta(f"job-file:{job.id}:{file.name}", f"{file.media_type} {uri}")
            names.append(file.name)
        await self._store.save_job(
            job.model_copy(
                update={
                    "status": "succeeded",
                    "finished": utc(self._clock()),
                    "result_id": outcome.result_id,
                    "files": names or None,
                    "report": outcome.report,
                }
            )
        )

    async def get(self, principal: Principal, job_id: str) -> Job:
        require(self._authorizer, principal, Permission.PROGRAMS_READ)
        job = await self._store.get_job(job_id)
        if job is None:
            raise NotFound(f"no job {job_id}")
        return job

    async def list(self, principal: Principal, query: JobQuery) -> Page[Job]:
        require(self._authorizer, principal, Permission.PROGRAMS_READ)
        after = decode_cursor(query.cursor)
        jobs = [
            j
            for j in await self._store.list_jobs()
            if (query.type is None or j.type == query.type)
            and (query.status is None or j.status == query.status)
        ]
        jobs.sort(key=lambda j: j.id)
        jobs = [j for j in jobs if after is None or j.id > after]
        page = jobs[: query.limit]
        more = len(jobs) > query.limit
        return Page[Job](
            data=page,
            page=PageInfo(
                next_cursor=encode_cursor(page[-1].id) if more else None, limit=query.limit
            ),
        )

    async def file(self, principal: Principal, job_id: str, name: str) -> tuple[bytes, str]:
        job = await self.get(principal, job_id)
        if job.status != "succeeded":
            raise Conflict(f"job {job_id} is {job.status}", slug="job-not-succeeded")
        if name not in (job.files or []):
            raise NotFound(f"job {job_id} has no file {name}")
        held = await self._store.get_meta(f"job-file:{job.id}:{name}")
        if held is None:
            raise NotFound(f"job {job_id} has no file {name}")
        media_type, uri = held.split(" ", 1)
        content = await self._blobs.get(uri)
        if content is None:
            raise NotFound(f"the bytes for {name} are gone")
        return content, media_type
