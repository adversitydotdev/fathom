"""Status reads: the kernel's section 8 computation over the store's graph.

`at` in the past reads the revisions in force at `at` (RFC 0002 section 4),
not today's objects against an old date. After a restore, history before the
restore is unknown, and a request for it is refused.
"""

from collections.abc import Callable
from datetime import datetime

from opengrc.access import Authorizer, Permission, Principal, require
from opengrc.errors import FieldError, Invalid, NotFound
from opengrc.kernel import baselines, status
from opengrc.kernel.graph import Graph
from opengrc.kernel.models import Baseline, Program, System
from opengrc.kernel.timeutil import now, utc
from opengrc.operations import views
from opengrc.operations.store import ObjectStore


class StatusService:
    def __init__(
        self,
        store: ObjectStore,
        authorizer: Authorizer,
        clock: Callable[[], datetime] = now,
    ) -> None:
        self._store = store
        self._authorizer = authorizer
        self._clock = clock

    async def graph_at(self, at: datetime | None) -> tuple[Graph, datetime]:
        current = utc(self._clock())
        at = utc(at) if at is not None else current
        start = await self._store.history_start()
        if start is not None and at < start:
            raise Invalid(
                "status before the restore is not known; history starts at the restore",
                errors=[FieldError(f"at is before {start.isoformat()}", "/at")],
            )
        graph = await self._store.graph(None if at >= current else at)
        return graph, at

    async def effective_baseline(
        self, principal: Principal, baseline_id: str
    ) -> views.EffectiveBaseline:
        require(self._authorizer, principal, Permission.CONTROLS_READ)
        graph = await self._store.graph()
        baseline = graph.baseline(baseline_id)
        if baseline is None:
            raise NotFound(f"no baseline {baseline_id}")
        return views.EffectiveBaseline.of(baselines.effective(graph, baseline))

    async def _program(self, graph: Graph, program_id: str) -> Program:
        program = graph.program(program_id)
        if program is None:
            row = await self._store.get(program_id)
            if row is not None and row.obj.type == "program":
                raise Invalid(
                    f"program {program_id} did not exist at that instant",
                    errors=[FieldError("the program was created later", "/at")],
                )
            raise NotFound(f"no program {program_id}")
        return program

    async def program_status(
        self,
        principal: Principal,
        program_id: str,
        at: datetime | None = None,
        framework_id: str | None = None,
    ) -> views.ProgramStatus:
        require(self._authorizer, principal, Permission.PROGRAMS_READ)
        graph, at = await self.graph_at(at)
        program = await self._program(graph, program_id)
        return views.ProgramStatus.of(status.evaluate(graph, program, at, framework_id))

    async def program_summary(
        self, principal: Principal, program_id: str, at: datetime | None = None
    ) -> views.ProgramSummary:
        require(self._authorizer, principal, Permission.PROGRAMS_READ)
        graph, at = await self.graph_at(at)
        program = await self._program(graph, program_id)
        return views.ProgramSummary.of(status.summarize(graph, program, at))

    async def system_gaps(
        self, principal: Principal, system_id: str, at: datetime | None = None
    ) -> views.SystemGaps:
        require(self._authorizer, principal, Permission.PROGRAMS_READ)
        row = await self._store.get(system_id)
        if row is None or not isinstance(row.obj, System):
            raise NotFound(f"no system {system_id}")
        graph, at = await self.graph_at(at)
        gaps: list[views.Gap] = []
        for program in graph.all(Program):
            if program.system_ref != system_id:
                continue
            for control in status.evaluate(graph, program, at).controls:
                if control.state == status.GAP:
                    gaps.append(
                        views.Gap(
                            program_id=program.id,
                            control_id=control.control_id,
                            implementation_id=control.implementation_id,
                            failed=control.failed,
                        )
                    )
        return views.SystemGaps(at=at, gaps=gaps)


def baseline_of(graph: Graph, program: Program) -> Baseline | None:
    return graph.baseline(program.baseline_ref)
