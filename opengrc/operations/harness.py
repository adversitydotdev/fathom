"""Test runs, RFC 0001 section 7.6 and RFC 0004 `POST /tests/{id}/runs`.

The route checks what it can and returns a job. The job hands the test to the
runner its `run` block names, then writes what the run produced: one
`evidence` per collected file, with sha-256 of the bytes and a validity
window from the test's interval, and one `result` citing them. The harness
never edits the test. A second run is a new result.
"""

from collections.abc import Callable
from datetime import datetime, timedelta

from pydantic import BaseModel

from opengrc.access import Authorizer, Permission, Principal, require
from opengrc.errors import FieldError, Invalid, NotFound
from opengrc.kernel import ids
from opengrc.kernel.bundles import digest
from opengrc.kernel.models import Evidence, Implementation, Result, Test
from opengrc.kernel.parameters import control_values
from opengrc.kernel.timeutil import FRESHNESS_DAYS, now, utc
from opengrc.operations.jobs import JobOutcome, JobService
from opengrc.operations.objects import ObjectService
from opengrc.operations.records import Job
from opengrc.operations.store import BlobStore
from opengrc.plugins import Plugins
from opengrc.plugins.ports import RunReport, SecretHandle
from opengrc.plugins.ports import RunRequest as RunnerRequest


class RunRequest(BaseModel):
    implementation_id: str


def valid_until(test: Test, observed: datetime):
    days = FRESHNESS_DAYS.get(test.interval or "")
    return (observed + timedelta(days=days)).date() if days else None


class HarnessService:
    def __init__(
        self,
        objects: ObjectService,
        blobs: BlobStore,
        authorizer: Authorizer,
        jobs: JobService,
        plugins: Plugins,
        clock: Callable[[], datetime] = now,
    ) -> None:
        self._objects = objects
        self._blobs = blobs
        self._authorizer = authorizer
        self._jobs = jobs
        self._plugins = plugins
        self._clock = clock

    async def run(self, principal: Principal, test_id: str, request: RunRequest) -> Job:
        require(self._authorizer, principal, Permission.TESTS_RUN)
        store = self._objects.store
        row = await store.get(test_id)
        if row is None or not isinstance(row.obj, Test):
            raise NotFound(f"no test {test_id}")
        test: Test = row.obj
        if test.is_revoked:
            raise Invalid(f"{test_id} is revoked")
        if test.run is None:
            raise Invalid(
                f"{test_id} has no run block; record a manual result with POST /results",
                errors=[FieldError("the test has no run block", "/run")],
            )
        runner = self._plugins.runners.get(test.run.runner)
        if runner is None:
            raise Invalid(
                errors=[FieldError(f"no runner {test.run.runner!r} is installed", "/run/runner")]
            )
        impl_row = await store.get(request.implementation_id)
        if impl_row is None or not isinstance(impl_row.obj, Implementation):
            raise Invalid(errors=[FieldError("no such implementation", "/implementation_id")])
        impl: Implementation = impl_row.obj
        if impl.control_ref != test.control_ref:
            raise Invalid(
                errors=[
                    FieldError(
                        "the implementation is not of this test's control", "/implementation_id"
                    )
                ]
            )

        async def work(job: Job) -> JobOutcome:
            graph = await store.graph()
            control = graph.control(test.control_ref)
            parameters = {
                k: v
                for k, v in (control_values(control, impl, {}) if control else {}).items()
                if v is not None
            }
            report: RunReport = await runner.run(
                RunnerRequest(
                    test=test,
                    implementation=impl,
                    evaluation_date=utc(self._clock()).date(),
                    parameters=parameters,
                    secrets=SecretHandle(tuple(test.run.env or [])),  # type: ignore[union-attr]
                )
            )
            result_id = await self.record(principal, test, impl, report)
            return JobOutcome(result_id=result_id, report={"outcome": report.outcome})

        return await self._jobs.submit(
            principal, "test_run", {"test_id": test_id, **request.model_dump()}, work
        )

    async def record(
        self, principal: Principal, test: Test, impl: Implementation, report: RunReport
    ) -> str:
        """Steps 8 and 9 of the harness contract."""
        observed = utc(report.observed)
        stamp = utc(self._clock())
        evidence_ids: list[str] = []
        for file in report.files:
            evidence_id = ids.mint("evidence")
            sha = digest(file.content)
            uri = await self._blobs.put(
                f"evidence/{evidence_id}/{sha}", file.content, file.media_type
            )
            evidence = Evidence(
                id=evidence_id,
                created=stamp,
                modified=stamp,
                created_by_ref=principal.actor_id,
                name=file.name,
                method="automated",
                collected=observed,
                valid_from=observed.date(),
                valid_until=valid_until(test, observed),
                implementation_ref=impl.id,
                resource={
                    "uri": uri,
                    "media_type": file.media_type,
                    "digest": {"algorithm": "sha-256", "value": sha},
                },
            )
            await self._objects.store_as(evidence, principal.actor_id)
            evidence_ids.append(evidence_id)
        result = Result(
            id=ids.mint("result"),
            created=stamp,
            modified=stamp,
            created_by_ref=principal.actor_id,
            test_ref=test.id,
            implementation_ref=impl.id,
            observed=observed,
            outcome=report.outcome,
            summary=report.summary or None,
            objective_refs=list(test.objective_refs) if test.objective_refs else None,
            evidence_refs=evidence_ids or None,
        )
        await self._objects.store_as(result, principal.actor_id)
        return result.id
