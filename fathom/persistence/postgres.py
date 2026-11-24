"""The Postgres store: the same protocol as `MemoryStore`, over SQLAlchemy's async
engine and asyncpg (RFC 0003 section 7).

- `If-Match` is enforced in the update itself:
  `UPDATE objects ... WHERE id = :id AND modified = :expected`. An update that
  matches no row is 412. The check and the write are one statement.
- Every write appends a row to `revisions` in the same transaction.
- A projection (library pull, provider import) replaces its rows and its pin
  in one transaction, under an advisory lock per projection, so an
  interrupted pull leaves the previous pin.
- The current graph is cached per process and keyed by `store_state.version`,
  which every write advances, so two API processes never serve a stale graph.
"""

import hashlib
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from fathom.errors import Conflict, PreconditionFailed
from fathom.kernel.graph import Graph
from fathom.kernel.models import Envelope, parse
from fathom.kernel.timeutil import later_than, now
from fathom.operations.connections import (
    Connection,
    InstallRecord,
    QueryDefinition,
    Snapshot,
    connection_body,
)
from fathom.operations.records import (
    LIBRARY,
    ORGANIZATION,
    PROVIDER_PREFIX,
    Job,
    LibraryPin,
    ProviderPin,
)
from fathom.operations.store import ProjectionChange, Row
from fathom.persistence.tables import (
    connections,
    integration_installs,
    jobs,
    objects,
    provider_pins,
    queries,
    revisions,
    settings,
    snapshots,
    store_state,
)


def async_url(url: str) -> str:
    """Accept the plain `postgresql://` form RDS, Neon, and libpq tools print."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix) :]
    return url


def _lock_key(name: str) -> int:
    return int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], "big", signed=True)


class PostgresStore:
    def __init__(self, url: str | None = None, *, engine: AsyncEngine | None = None) -> None:
        if engine is None:
            if url is None:
                raise ValueError("a database URL or an engine is required")
            engine = create_async_engine(async_url(url), pool_pre_ping=True)
        self._engine = engine
        self._cache: tuple[int, Graph] | None = None

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    async def close(self) -> None:
        await self._engine.dispose()

    # --- helpers ----------------------------------------------------------------------

    @staticmethod
    def _row(source: str, body: dict[str, Any]) -> Row:
        return Row(parse(body), source)

    @staticmethod
    def _values(obj: Envelope, source: str) -> dict[str, Any]:
        return {
            "id": obj.id,
            "type": obj.type,
            "source": source,
            "modified": obj.modified,
            "revoked": obj.is_revoked,
            "body": obj.body(),
        }

    @staticmethod
    async def _revision(
        conn: AsyncConnection,
        obj: Envelope,
        source: str,
        writer: str,
        stored_at: datetime | None = None,
    ) -> None:
        await conn.execute(
            revisions.insert().values(
                object_id=obj.id,
                stored_at=stored_at or now(),
                source=source,
                writer=writer,
                body=obj.body(),
            )
        )

    @staticmethod
    async def _bump(conn: AsyncConnection) -> None:
        await conn.execute(
            update(store_state)
            .where(store_state.c.id == 1)
            .values(version=store_state.c.version + 1)
        )

    # --- objects ----------------------------------------------------------------------

    async def get(self, object_id: str) -> Row | None:
        async with self._engine.connect() as conn:
            found = (
                await conn.execute(
                    select(objects.c.source, objects.c.body).where(objects.c.id == object_id)
                )
            ).first()
        return self._row(found.source, found.body) if found else None

    async def scan(self, object_type: str) -> list[Row]:
        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(objects.c.source, objects.c.body)
                .where(objects.c.type == object_type)
                .order_by(objects.c.id)
            )
            return [self._row(r.source, r.body) for r in result]

    async def insert(self, row: Row, writer: str) -> None:
        async with self._engine.begin() as conn:
            inserted = await conn.execute(
                insert(objects)
                .values(**self._values(row.obj, row.source))
                .on_conflict_do_nothing(index_elements=["id"])
                .returning(objects.c.id)
            )
            if inserted.first() is None:
                raise Conflict(f"id {row.obj.id} is in use", slug="id-taken")
            await self._revision(conn, row.obj, row.source, writer)
            await self._bump(conn)

    async def replace(self, obj: Envelope, expected_modified: datetime, writer: str) -> None:
        async with self._engine.begin() as conn:
            updated = await conn.execute(
                update(objects)
                .where(and_(objects.c.id == obj.id, objects.c.modified == expected_modified))
                .values(modified=obj.modified, revoked=obj.is_revoked, body=obj.body())
                .returning(objects.c.source)
            )
            found = updated.first()
            if found is None:
                raise PreconditionFailed("the object changed since it was read")
            await self._revision(conn, obj, found.source, writer)
            await self._bump(conn)

    async def graph(self, at: datetime | None = None) -> Graph:
        async with self._engine.connect() as conn:
            if at is None:
                version = (
                    await conn.execute(select(store_state.c.version).where(store_state.c.id == 1))
                ).scalar_one()
                if self._cache is not None and self._cache[0] == version:
                    return self._cache[1]
                result = await conn.execute(select(objects.c.source, objects.c.body))
                graph = self._build(self._row(r.source, r.body) for r in result)
                self._cache = (version, graph)
                return graph
            in_force = (
                select(revisions.c.source, revisions.c.body)
                .where(revisions.c.stored_at <= at)
                .distinct(revisions.c.object_id)
                .order_by(
                    revisions.c.object_id, revisions.c.stored_at.desc(), revisions.c.seq.desc()
                )
            )
            result = await conn.execute(in_force)
            return self._build(self._row(r.source, r.body) for r in result)

    @staticmethod
    def _build(rows: Iterable[Row]) -> Graph:
        rows = list(rows)
        return Graph(
            (row.obj for row in rows),
            library_ids=(row.obj.id for row in rows if row.source == LIBRARY),
            provider_ids=(row.obj.id for row in rows if row.source.startswith(PROVIDER_PREFIX)),
        )

    async def history_start(self) -> datetime | None:
        async with self._engine.connect() as conn:
            return (
                await conn.execute(select(store_state.c.history_start).where(store_state.c.id == 1))
            ).scalar_one_or_none()

    async def has_organization_objects(self) -> bool:
        async with self._engine.connect() as conn:
            return await self._has_organization(conn)

    @staticmethod
    async def _has_organization(conn: AsyncConnection) -> bool:
        found = await conn.execute(
            select(objects.c.id).where(objects.c.source == ORGANIZATION).limit(1)
        )
        return found.first() is not None

    async def replace_projection(
        self,
        source: str,
        objects_in: Sequence[Envelope],
        revoked_at: datetime,
        writer: str,
        *,
        library_pin: LibraryPin | None = None,
        provider_pin: ProviderPin | None = None,
    ) -> ProjectionChange:
        incoming = {o.id: o for o in objects_in}
        async with self._engine.begin() as conn:
            await conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _lock_key(source)})
            held = {
                r.id: (r.source, r.body)
                for r in await conn.execute(
                    select(objects.c.id, objects.c.source, objects.c.body).where(
                        (objects.c.source == source) | objects.c.id.in_(list(incoming))
                    )
                )
            }
            for object_id, (held_source, _) in held.items():
                if object_id in incoming and held_source != source:
                    raise Conflict(f"{object_id} belongs to {held_source}", slug="id-taken")
            added = [i for i in incoming if i not in held]
            replaced = [i for i in incoming if i in held]
            for obj in objects_in:
                previous = held.get(obj.id)
                if previous is not None and parse(previous[1]) == obj:
                    continue
                values = self._values(obj, source)
                await conn.execute(
                    insert(objects)
                    .values(**values)
                    .on_conflict_do_update(
                        index_elements=["id"],
                        set_={k: values[k] for k in ("modified", "revoked", "body")},
                    )
                )
                await self._revision(conn, obj, source, writer)
            revoked: list[str] = []
            for object_id, (held_source, body) in held.items():
                if object_id in incoming or held_source != source:
                    continue
                old = parse(body)
                if old.is_revoked:
                    continue
                gone = old.model_copy(
                    update={"revoked": True, "modified": later_than(old.modified, revoked_at)}
                )
                await conn.execute(
                    update(objects)
                    .where(objects.c.id == object_id)
                    .values(modified=gone.modified, revoked=True, body=gone.body())
                )
                await self._revision(conn, gone, source, writer)
                revoked.append(object_id)
            if library_pin is not None:
                await conn.execute(
                    update(store_state)
                    .where(store_state.c.id == 1)
                    .values(library_pin=library_pin.model_dump(exclude_none=True))
                )
            if provider_pin is not None:
                body = provider_pin.model_dump(exclude_none=True)
                await conn.execute(
                    insert(provider_pins)
                    .values(id=provider_pin.id, body=body)
                    .on_conflict_do_update(index_elements=["id"], set_={"body": body})
                )
            await self._bump(conn)
        return ProjectionChange(replaced=replaced, added=added, revoked=revoked)

    async def restore(self, organization: Sequence[Envelope], writer: str, at: datetime) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                select(store_state.c.id).where(store_state.c.id == 1).with_for_update()
            )
            if await self._has_organization(conn):
                raise Conflict("the database already holds organization objects", slug="not-empty")
            ids = [o.id for o in organization]
            taken = (
                await conn.execute(select(objects.c.id).where(objects.c.id.in_(ids)).limit(1))
            ).first()
            if taken is not None:
                raise Conflict(f"id {taken.id} is in use", slug="id-taken")
            for obj in organization:
                await conn.execute(objects.insert().values(**self._values(obj, ORGANIZATION)))
                await self._revision(conn, obj, ORGANIZATION, writer, at)
            await conn.execute(
                update(store_state).where(store_state.c.id == 1).values(history_start=at)
            )
            await self._bump(conn)

    # --- pins, jobs, and settings ------------------------------------------------------

    async def library_pin(self) -> LibraryPin | None:
        async with self._engine.connect() as conn:
            body = (
                await conn.execute(select(store_state.c.library_pin).where(store_state.c.id == 1))
            ).scalar_one_or_none()
        return LibraryPin.model_validate(body) if body else None

    async def provider_pins(self) -> list[ProviderPin]:
        async with self._engine.connect() as conn:
            result = await conn.execute(select(provider_pins.c.body).order_by(provider_pins.c.id))
            return [ProviderPin.model_validate(r.body) for r in result]

    async def save_job(self, job: Job) -> None:
        body = job.model_dump(mode="json", exclude_none=True)
        values = {"type": job.type, "status": job.status, "created": job.created, "body": body}
        async with self._engine.begin() as conn:
            await conn.execute(
                insert(jobs)
                .values(id=job.id, **values)
                .on_conflict_do_update(index_elements=["id"], set_=values)
            )

    async def claim_job(self, job_id: str, worker: str) -> bool:
        """The claim RFC 0003 section 2 requires before a process runs a job row."""
        async with self._engine.begin() as conn:
            claimed = await conn.execute(
                update(jobs)
                .where(and_(jobs.c.id == job_id, jobs.c.claimed_by.is_(None)))
                .values(claimed_by=worker)
                .returning(jobs.c.id)
            )
            return claimed.first() is not None

    async def get_job(self, job_id: str) -> Job | None:
        async with self._engine.connect() as conn:
            body = (
                await conn.execute(select(jobs.c.body).where(jobs.c.id == job_id))
            ).scalar_one_or_none()
        return Job.model_validate(body) if body else None

    async def list_jobs(self) -> list[Job]:
        async with self._engine.connect() as conn:
            result = await conn.execute(select(jobs.c.body).order_by(jobs.c.created, jobs.c.id))
            return [Job.model_validate(r.body) for r in result]

    async def get_meta(self, key: str) -> str | None:
        async with self._engine.connect() as conn:
            return (
                await conn.execute(select(settings.c.value).where(settings.c.key == key))
            ).scalar_one_or_none()

    async def set_meta(self, key: str, value: str | None) -> None:
        async with self._engine.begin() as conn:
            if value is None:
                await conn.execute(settings.delete().where(settings.c.key == key))
            else:
                await conn.execute(
                    insert(settings)
                    .values(key=key, value=value)
                    .on_conflict_do_update(index_elements=["key"], set_={"value": value})
                )

    async def object_count(self) -> int:
        async with self._engine.connect() as conn:
            return (await conn.execute(select(func.count()).select_from(objects))).scalar_one()


class PostgresConnections:
    """Connections and snapshot rows (RFC 0005) in the organization database."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get_connection(self, connection_id: str) -> Connection | None:
        async with self._engine.connect() as conn:
            body = (
                await conn.execute(
                    select(connections.c.body).where(connections.c.id == connection_id)
                )
            ).scalar_one_or_none()
        return Connection.model_validate(body) if body else None

    async def list_connections(self) -> list[Connection]:
        async with self._engine.connect() as conn:
            result = await conn.execute(select(connections.c.body).order_by(connections.c.id))
            return [Connection.model_validate(r.body) for r in result]

    async def insert_connection(self, connection: Connection) -> None:
        async with self._engine.begin() as conn:
            inserted = await conn.execute(
                insert(connections)
                .values(
                    id=connection.id,
                    integration_id=connection.integration_id,
                    modified=connection.modified,
                    body=connection_body(connection),
                )
                .on_conflict_do_nothing(index_elements=["id"])
                .returning(connections.c.id)
            )
            if inserted.first() is None:
                raise Conflict(f"{connection.id} already exists")

    async def replace_connection(self, connection: Connection, expected_modified: datetime) -> None:
        async with self._engine.begin() as conn:
            updated = await conn.execute(
                update(connections)
                .where(
                    and_(
                        connections.c.id == connection.id,
                        connections.c.modified == expected_modified,
                    )
                )
                .values(modified=connection.modified, body=connection_body(connection))
                .returning(connections.c.id)
            )
            if updated.first() is None:
                raise PreconditionFailed(f"{connection.id} changed since {expected_modified}")

    async def delete_connection(self, connection_id: str) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(connections.delete().where(connections.c.id == connection_id))

    async def insert_snapshot(self, snapshot: Snapshot) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                insert(snapshots).values(
                    id=snapshot.id,
                    connection_id=snapshot.connection_id,
                    source=snapshot.source,
                    collected=snapshot.collected,
                    complete=snapshot.complete,
                    body=snapshot.model_dump(mode="json", exclude_none=True),
                )
            )

    async def get_snapshot(self, snapshot_id: str) -> Snapshot | None:
        async with self._engine.connect() as conn:
            body = (
                await conn.execute(select(snapshots.c.body).where(snapshots.c.id == snapshot_id))
            ).scalar_one_or_none()
        return Snapshot.model_validate(body) if body else None

    async def list_snapshots(
        self, connection_id: str | None = None, source: str | None = None
    ) -> list[Snapshot]:
        query = select(snapshots.c.body)
        if connection_id is not None:
            query = query.where(snapshots.c.connection_id == connection_id)
        if source is not None:
            query = query.where(snapshots.c.source == source)
        query = query.order_by(snapshots.c.collected.desc(), snapshots.c.id.desc())
        async with self._engine.connect() as conn:
            return [Snapshot.model_validate(r.body) for r in await conn.execute(query)]

    async def latest_snapshot(
        self, connection_id: str, source: str, not_before: datetime, not_after: datetime
    ) -> Snapshot | None:
        query = (
            select(snapshots.c.body)
            .where(
                and_(
                    snapshots.c.connection_id == connection_id,
                    snapshots.c.source == source,
                    snapshots.c.complete.is_(True),
                    snapshots.c.collected >= not_before,
                    snapshots.c.collected <= not_after,
                )
            )
            .order_by(snapshots.c.collected.desc(), snapshots.c.id.desc())
            .limit(1)
        )
        async with self._engine.connect() as conn:
            body = (await conn.execute(query)).scalar_one_or_none()
        return Snapshot.model_validate(body) if body else None

    async def list_installs(self) -> list[InstallRecord]:
        query = select(integration_installs.c.body).order_by(
            integration_installs.c.id, integration_installs.c.installed
        )
        async with self._engine.connect() as conn:
            return [InstallRecord.model_validate(r.body) for r in await conn.execute(query)]

    async def put_install(self, record: InstallRecord) -> None:
        async with self._engine.begin() as conn:
            inserted = await conn.execute(
                insert(integration_installs)
                .values(
                    id=record.id,
                    version=record.version,
                    enabled=record.enabled,
                    installed=record.installed,
                    body=record.model_dump(mode="json", exclude_none=True),
                )
                .on_conflict_do_nothing(index_elements=["id", "version"])
                .returning(integration_installs.c.id)
            )
            if inserted.first() is None:
                raise Conflict(f"{record.id} {record.version} is already installed")

    async def enable_install(self, integration_id: str, version: str) -> None:
        async with self._engine.begin() as conn:
            rows = (
                await conn.execute(
                    select(integration_installs.c.version, integration_installs.c.body)
                    .where(integration_installs.c.id == integration_id)
                    .with_for_update()
                )
            ).all()
            if version not in {r.version for r in rows}:
                raise Conflict(f"{integration_id} {version} is not installed")
            for row in rows:
                enabled = row.version == version
                await conn.execute(
                    update(integration_installs)
                    .where(
                        and_(
                            integration_installs.c.id == integration_id,
                            integration_installs.c.version == row.version,
                        )
                    )
                    .values(enabled=enabled, body={**row.body, "enabled": enabled})
                )

    async def list_queries(self) -> list[QueryDefinition]:
        query = select(queries.c.body).order_by(
            queries.c.integration_id, queries.c.name, queries.c.version
        )
        async with self._engine.connect() as conn:
            return [QueryDefinition.model_validate(r.body) for r in await conn.execute(query)]

    async def put_query(self, query: QueryDefinition) -> None:
        async with self._engine.begin() as conn:
            inserted = await conn.execute(
                insert(queries)
                .values(
                    id=query.id,
                    integration_id=query.integration_id,
                    name=query.name,
                    version=query.version,
                    body=query.model_dump(mode="json", exclude_none=True),
                )
                .on_conflict_do_nothing()
                .returning(queries.c.id)
            )
            if inserted.first() is None:
                raise Conflict(f"{query.source} already exists", slug="query-exists")

    async def delete_query(self, query_id: str) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(queries.delete().where(queries.c.id == query_id))
