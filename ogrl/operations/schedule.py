"""Scheduled snapshot runs, RFC 0005 section 6.

Each tick finds `rule` and `integration` tests that are due for an
implementation with a bound connection, and asks the harness to run them.
The harness's snapshot selection collects whatever is missing or older than
the reuse window, so a tick never calls a vendor directly.

A pair is due when it has no current result, or its current result is older
than its cadence: one hour for `continuous`, otherwise the freshness window
less a margin, so a new result lands before the previous one stops counting.
`event-driven` tests are never scheduled.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from ogrl.access import Principal
from ogrl.kernel import rules
from ogrl.kernel.graph import Graph
from ogrl.kernel.models import Implementation, Test
from ogrl.kernel.timeutil import FRESHNESS_DAYS, now, utc
from ogrl.operations.connections import ConnectionStore
from ogrl.operations.harness import SNAPSHOT_RUNNERS, HarnessService, RunRequest
from ogrl.operations.integrations import IntegrationService
from ogrl.operations.records import Job
from ogrl.operations.store import ObjectStore

log = logging.getLogger(__name__)

MARGIN = timedelta(hours=2)
CONTINUOUS = timedelta(hours=1)


def cadence(test: Test) -> timedelta | None:
    if test.interval == "continuous":
        return CONTINUOUS
    days = FRESHNESS_DAYS.get(test.interval or "")
    if days is None:
        return None
    return max(timedelta(days=days) - MARGIN, CONTINUOUS)


@dataclass(frozen=True)
class Due:
    test: Test
    implementation: Implementation


class IntegrationScheduler:
    def __init__(
        self,
        store: ObjectStore,
        connections: ConnectionStore,
        integrations: IntegrationService,
        harness: HarnessService,
        clock: Callable[[], datetime] = now,
    ) -> None:
        self._store = store
        self._connections = connections
        self._integrations = integrations
        self._harness = harness
        self._clock = clock
        self._in_flight: dict[tuple[str, str], str] = {}

    async def due(self, graph: Graph, at: datetime) -> list[Due]:
        connections = await self._connections.list_connections()
        out = []
        for test in graph.all(Test):
            if test.run is None or test.run.runner not in SNAPSHOT_RUNNERS:
                continue
            every = cadence(test)
            if every is None:
                continue
            try:
                needed = {rules.parse_reference(s).integration for s in test.run.sources_read()}
            except ValueError:
                continue
            for impl in graph.implementations:
                if impl.is_revoked or impl.is_provider or impl.control_ref != test.control_ref:
                    continue
                if test.system_refs and impl.system_ref not in test.system_refs:
                    continue
                bound = IntegrationService.bound(impl, graph, connections)
                if not needed or not needed <= {c.integration_id for c in bound}:
                    continue  # nothing to collect from; the run would only record an error
                results = [
                    r for r in graph.results_by_pair.get((test.id, impl.id), []) if not r.is_revoked
                ]
                latest = max((utc(r.observed) for r in results), default=None)
                if latest is None or at - latest >= every:
                    out.append(Due(test, impl))
        return out

    async def tick(self, principal: Principal) -> list[Job]:
        at = utc(self._clock())
        await self._integrations.ready()
        graph = await self._store.graph()
        jobs = []
        for item in await self.due(graph, at):
            key = (item.test.id, item.implementation.id)
            previous = self._in_flight.get(key)
            if previous is not None:
                job = await self._store.get_job(previous)
                if job is not None and job.status in ("queued", "running"):
                    continue
            try:
                job = await self._harness.run(
                    principal, item.test.id, RunRequest(implementation_id=item.implementation.id)
                )
            except Exception:
                log.exception("scheduled run of %s on %s could not start", *key)
                continue
            self._in_flight[key] = job.id
            jobs.append(job)
        return jobs
