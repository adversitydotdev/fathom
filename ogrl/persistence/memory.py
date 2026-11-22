"""In-memory stores for tests and local runs. Postgres implements the same protocols.

`MemoryStore` keeps every revision of every object (RFC 0002 section 4), so
status at a past instant reads the objects that were in force then. The
compare-and-set in `replace` runs without an `await` between the check and
the write, which is what makes it atomic on one event loop.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from ogrl.errors import Conflict, PreconditionFailed
from ogrl.kernel.graph import Graph
from ogrl.kernel.models import Control, Envelope, Origin
from ogrl.kernel.timeutil import later_than, now
from ogrl.operations.connections import Connection, InstallRecord, QueryDefinition, Snapshot
from ogrl.operations.records import (
    LIBRARY,
    ORGANIZATION,
    PROVIDER_PREFIX,
    Job,
    LibraryPin,
    ProviderPin,
    provider_source,
)
from ogrl.operations.store import ProjectionChange, Row

BEGINNING = datetime.min.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class Revision:
    stored_at: datetime
    row: Row
    writer: str


class MemoryStore:
    def __init__(
        self,
        library: Iterable[Envelope] = (),
        organization: Iterable[Envelope] = (),
        providers: dict[str, Iterable[Envelope]] | None = None,
        library_pin: LibraryPin | None = None,
    ) -> None:
        self._revisions: dict[str, list[Revision]] = {}
        self._library_pin = library_pin
        self._provider_pins: dict[str, ProviderPin] = {}
        self._jobs: dict[str, Job] = {}
        self._claims: dict[str, str] = {}
        self._meta: dict[str, str] = {}
        self._history_start: datetime | None = None
        self._graph: Graph | None = None
        for obj in library:
            self._append(Row(obj, LIBRARY), "seed", BEGINNING)
        for bundle_id, objects in (providers or {}).items():
            for obj in objects:
                self._append(Row(obj, provider_source(bundle_id)), "seed", BEGINNING)
        for obj in organization:
            self._append(Row(obj, ORGANIZATION), "seed", BEGINNING)

    # --- objects ---------------------------------------------------------------------

    def _append(self, row: Row, writer: str, stored_at: datetime | None = None) -> None:
        self._revisions.setdefault(row.obj.id, []).append(Revision(stored_at or now(), row, writer))
        self._graph = None

    def _current(self) -> Iterable[Row]:
        return (revisions[-1].row for revisions in self._revisions.values())

    async def get(self, object_id: str) -> Row | None:
        revisions = self._revisions.get(object_id)
        return revisions[-1].row if revisions else None

    async def scan(self, object_type: str) -> list[Row]:
        rows = [row for row in self._current() if row.obj.type == object_type]
        return sorted(rows, key=lambda row: row.obj.id)

    async def insert(self, row: Row, writer: str) -> None:
        if row.obj.id in self._revisions:
            raise Conflict(f"id {row.obj.id} is in use", slug="id-taken")
        self._append(row, writer)

    async def replace(self, obj: Envelope, expected_modified: datetime, writer: str) -> None:
        current = await self.get(obj.id)
        if current is None or current.obj.modified != expected_modified:
            raise PreconditionFailed("the object changed since it was read")
        self._append(Row(obj, current.source), writer)

    async def graph(self, at: datetime | None = None) -> Graph:
        if at is None:
            if self._graph is None:
                self._graph = self._build(self._current())
            return self._graph
        in_force: list[Row] = []
        for revisions in self._revisions.values():
            held = [r for r in revisions if r.stored_at <= at]
            if held:
                in_force.append(held[-1].row)
        return self._build(in_force)

    @staticmethod
    def _build(rows: Iterable[Row]) -> Graph:
        rows = list(rows)
        return Graph(
            (row.obj for row in rows),
            library_ids=(row.obj.id for row in rows if row.source == LIBRARY),
            provider_ids=(row.obj.id for row in rows if row.source.startswith(PROVIDER_PREFIX)),
        )

    async def history_start(self) -> datetime | None:
        return self._history_start

    async def has_organization_objects(self) -> bool:
        return any(row.source == ORGANIZATION for row in self._current())

    async def replace_projection(
        self,
        source: str,
        objects: Sequence[Envelope],
        revoked_at: datetime,
        writer: str,
        *,
        library_pin: LibraryPin | None = None,
        provider_pin: ProviderPin | None = None,
    ) -> ProjectionChange:
        incoming = {o.id: o for o in objects}
        for object_id in incoming:
            held = await self.get(object_id)
            if held is not None and held.source != source:
                raise Conflict(f"{object_id} belongs to {held.source}", slug="id-taken")
        previous = [row for row in self._current() if row.source == source]
        replaced = [o.id for o in objects if o.id in self._revisions]
        added = [o.id for o in objects if o.id not in self._revisions]
        revoked: list[str] = []
        for obj in objects:
            held = await self.get(obj.id)
            if held is None or held.obj != obj:
                self._append(Row(obj, source), writer)
        for row in previous:
            if row.obj.id in incoming or row.obj.is_revoked:
                continue
            stamp = later_than(row.obj.modified, revoked_at)
            self._append(
                Row(row.obj.model_copy(update={"revoked": True, "modified": stamp}), source),
                writer,
            )
            revoked.append(row.obj.id)
        if library_pin is not None:
            self._library_pin = library_pin
        if provider_pin is not None:
            self._provider_pins[provider_pin.id] = provider_pin
        return ProjectionChange(replaced=replaced, added=added, revoked=revoked)

    async def restore(self, organization: Sequence[Envelope], writer: str, at: datetime) -> None:
        if await self.has_organization_objects():
            raise Conflict("the database already holds organization objects", slug="not-empty")
        for obj in organization:
            if obj.id in self._revisions:
                raise Conflict(f"id {obj.id} is in use", slug="id-taken")
        for obj in organization:
            self._append(Row(obj, ORGANIZATION), writer, at)
        self._history_start = at

    # --- pins, jobs, and settings ------------------------------------------------------

    async def library_pin(self) -> LibraryPin | None:
        return self._library_pin

    async def provider_pins(self) -> list[ProviderPin]:
        return sorted(self._provider_pins.values(), key=lambda p: p.id)

    async def save_job(self, job: Job) -> None:
        self._jobs[job.id] = job

    async def claim_job(self, job_id: str, worker: str) -> bool:
        if job_id in self._claims:
            return False
        self._claims[job_id] = worker
        return True

    async def get_job(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def list_jobs(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: (j.created, j.id))

    async def get_meta(self, key: str) -> str | None:
        return self._meta.get(key)

    async def set_meta(self, key: str, value: str | None) -> None:
        if value is None:
            self._meta.pop(key, None)
        else:
            self._meta[key] = value


class MemoryControls(MemoryStore):
    """A store seeded with controls: standard ones as library rows, custom ones as the org's."""

    def __init__(self, seed: Iterable[Control] | None = None) -> None:
        seed = list(seed or [])
        super().__init__(
            library=[c for c in seed if c.origin is Origin.STANDARD],
            organization=[c for c in seed if c.origin is not Origin.STANDARD],
        )


class MemoryBlobs:
    """Object storage in a dict. URIs are `memory://<key>`."""

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    async def put(self, key: str, content: bytes, media_type: str) -> str:
        uri = f"memory://{key}"
        self._blobs[uri] = content
        return uri

    async def get(self, uri: str) -> bytes | None:
        return self._blobs.get(uri)


class MemoryConnections:
    """Connections and snapshot rows (RFC 0005) for tests and local runs."""

    def __init__(self) -> None:
        self._connections: dict[str, Connection] = {}
        self._snapshots: dict[str, Snapshot] = {}
        self._installs: dict[tuple[str, str], InstallRecord] = {}
        self._queries: dict[str, QueryDefinition] = {}

    async def get_connection(self, connection_id: str) -> Connection | None:
        return self._connections.get(connection_id)

    async def list_connections(self) -> list[Connection]:
        return [self._connections[k] for k in sorted(self._connections)]

    async def insert_connection(self, connection: Connection) -> None:
        if connection.id in self._connections:
            raise Conflict(f"{connection.id} already exists")
        self._connections[connection.id] = connection

    async def replace_connection(self, connection: Connection, expected_modified: datetime) -> None:
        current = self._connections.get(connection.id)
        if current is None or current.modified != expected_modified:
            raise PreconditionFailed(f"{connection.id} changed since {expected_modified}")
        self._connections[connection.id] = connection

    async def delete_connection(self, connection_id: str) -> None:
        self._connections.pop(connection_id, None)

    async def insert_snapshot(self, snapshot: Snapshot) -> None:
        self._snapshots[snapshot.id] = snapshot

    async def get_snapshot(self, snapshot_id: str) -> Snapshot | None:
        return self._snapshots.get(snapshot_id)

    async def list_snapshots(
        self, connection_id: str | None = None, source: str | None = None
    ) -> list[Snapshot]:
        found = [
            s
            for s in self._snapshots.values()
            if (connection_id is None or s.connection_id == connection_id)
            and (source is None or s.source == source)
        ]
        return sorted(found, key=lambda s: (s.collected, s.id), reverse=True)

    async def latest_snapshot(
        self, connection_id: str, source: str, not_before: datetime, not_after: datetime
    ) -> Snapshot | None:
        for snapshot in await self.list_snapshots(connection_id, source):
            if snapshot.complete and not_before <= snapshot.collected <= not_after:
                return snapshot
        return None

    async def list_installs(self) -> list[InstallRecord]:
        return sorted(self._installs.values(), key=lambda r: (r.id, r.installed))

    async def put_install(self, record: InstallRecord) -> None:
        if (record.id, record.version) in self._installs:
            raise Conflict(f"{record.id} {record.version} is already installed")
        self._installs[(record.id, record.version)] = record

    async def enable_install(self, integration_id: str, version: str) -> None:
        if (integration_id, version) not in self._installs:
            raise Conflict(f"{integration_id} {version} is not installed")
        for key, record in self._installs.items():
            if key[0] == integration_id:
                self._installs[key] = record.model_copy(update={"enabled": key[1] == version})

    async def list_queries(self) -> list[QueryDefinition]:
        return sorted(self._queries.values(), key=lambda q: (q.integration_id, q.name, q.version))

    async def put_query(self, query: QueryDefinition) -> None:
        if any(q.source == query.source for q in self._queries.values()):
            raise Conflict(f"{query.source} already exists", slug="query-exists")
        self._queries[query.id] = query

    async def delete_query(self, query_id: str) -> None:
        self._queries.pop(query_id, None)
