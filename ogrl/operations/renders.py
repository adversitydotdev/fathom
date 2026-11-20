"""Program renders: `oscal` (RFC 0002 section 9) and `ssp` (RFC 0001 section 8.1).

The job's product is files, downloadable from `/jobs/{id}/files/{filename}`.
"""

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from ogrl.access import Authorizer, Permission, Principal, require
from ogrl.errors import FieldError, Invalid, NotFound
from ogrl.kernel.models import Framework, Program
from ogrl.kernel.timeutil import now, utc
from ogrl.operations.jobs import JobFile, JobOutcome, JobService
from ogrl.operations.records import Job
from ogrl.operations.store import ObjectStore
from ogrl.plugins import Plugins
from ogrl.plugins.ports import RenderRequest as PortRequest


class RenderRequest(BaseModel):
    view: Literal["oscal", "ssp"]
    framework_id: str | None = None


class RenderService:
    def __init__(
        self,
        store: ObjectStore,
        authorizer: Authorizer,
        jobs: JobService,
        plugins: Plugins,
        clock: Callable[[], datetime] = now,
    ) -> None:
        self._store = store
        self._authorizer = authorizer
        self._jobs = jobs
        self._plugins = plugins
        self._clock = clock

    async def render(self, principal: Principal, program_id: str, request: RenderRequest) -> Job:
        require(self._authorizer, principal, Permission.PROGRAMS_RENDER)
        row = await self._store.get(program_id)
        if row is None or not isinstance(row.obj, Program):
            raise NotFound(f"no program {program_id}")
        program: Program = row.obj
        if request.view == "oscal":
            if not request.framework_id:
                raise Invalid(errors=[FieldError("required when view is oscal", "/framework_id")])
            framework = await self._store.get(request.framework_id)
            if framework is None or not isinstance(framework.obj, Framework):
                raise Invalid(
                    errors=[FieldError("not a framework in the library", "/framework_id")]
                )
        renderer = self._plugins.renderers.get(request.view)
        if renderer is None:
            raise Invalid(errors=[FieldError(f"no renderer for {request.view}", "/view")])

        async def work(job: Job) -> JobOutcome:
            graph = await self._store.graph()
            port_request = PortRequest(graph, program, utc(self._clock()), request.framework_id)
            try:
                files = await asyncio.to_thread(renderer.render, port_request)
            except ValueError as exc:
                raise Invalid(str(exc)) from exc
            return JobOutcome(files=[JobFile(f.name, f.media_type, f.content) for f in files])

        return await self._jobs.submit(
            principal,
            "render",
            {"program_id": program_id, **request.model_dump(exclude_none=True)},
            work,
        )
