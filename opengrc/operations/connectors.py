"""Connectors (RFC 0003 section 5). The registry is empty until one is installed.

A connector run is a job. Each file the connector yields becomes one
`evidence` object on the implementation the request names.
"""

from collections.abc import Callable
from datetime import datetime

from pydantic import BaseModel

from opengrc.access import Authorizer, Permission, Principal, require
from opengrc.errors import FieldError, Invalid, NotFound
from opengrc.kernel import ids
from opengrc.kernel.bundles import digest
from opengrc.kernel.models import Evidence, Implementation
from opengrc.kernel.timeutil import now, utc
from opengrc.operations.jobs import JobOutcome, JobService
from opengrc.operations.objects import ObjectService
from opengrc.operations.records import Job
from opengrc.operations.store import BlobStore
from opengrc.operations.views import Connector as ConnectorView
from opengrc.plugins import Plugins
from opengrc.plugins.ports import CollectionRequest


class ConnectorRunRequest(BaseModel):
    system_id: str | None = None
    component_id: str | None = None
    implementation_id: str | None = None


class ConnectorService:
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

    async def list(self, principal: Principal) -> list[ConnectorView]:
        require(self._authorizer, principal, Permission.PROGRAMS_READ)
        out = []
        for name in self._plugins.connectors.names():
            connector = self._plugins.connectors.get(name)
            out.append(
                ConnectorView(
                    id=name,
                    name=getattr(connector, "name", name),
                    description=getattr(connector, "description", None),
                )
            )
        return out

    async def run(
        self, principal: Principal, connector_id: str, request: ConnectorRunRequest
    ) -> Job:
        require(self._authorizer, principal, Permission.CONNECTORS_RUN)
        connector = self._plugins.connectors.get(connector_id)
        if connector is None:
            raise NotFound(f"no connector {connector_id} is installed")
        impl: Implementation | None = None
        if request.implementation_id:
            row = await self._objects.store.get(request.implementation_id)
            if row is None or not isinstance(row.obj, Implementation):
                raise Invalid(errors=[FieldError("no such implementation", "/implementation_id")])
            impl = row.obj

        async def work(job: Job) -> JobOutcome:
            created: list[str] = []
            async for file in connector.collect(
                CollectionRequest(request.system_id, request.component_id, impl)
            ):
                if impl is None:
                    continue  # evidence needs an implementation to attach to
                stamp = utc(self._clock())
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
                    collected=stamp,
                    valid_from=stamp.date(),
                    implementation_ref=impl.id,
                    resource={
                        "uri": uri,
                        "media_type": file.media_type,
                        "digest": {"algorithm": "sha-256", "value": sha},
                    },
                )
                await self._objects.store_as(evidence, principal.actor_id)
                created.append(evidence_id)
            return JobOutcome(report={"evidence": created})

        return await self._jobs.submit(
            principal,
            "connector",
            {"connector_id": connector_id, **request.model_dump(exclude_none=True)},
            work,
        )
