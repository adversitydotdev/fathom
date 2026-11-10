"""What only a shared database can show: two writers, two processes, and migrations."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from opengrc.errors import Conflict, PreconditionFailed
from opengrc.kernel.models import Party
from opengrc.operations.records import Job
from opengrc.operations.store import Row
from opengrc.persistence.postgres import PostgresStore, async_url
from tests.conftest import DATABASE_URL, SCHEMAS, postgres_store, services_available

pytestmark = pytest.mark.skipif(
    not services_available(), reason="the compose stack is not running (docker compose up -d)"
)
T0 = datetime(2026, 11, 1, tzinfo=UTC)


def party(modified: datetime, name: str = "Ops") -> Party:
    return Party(id="party--com.acme.ops", name=name, kind="team", created=T0, modified=modified)


def test_concurrent_writers_one_wins():
    store = postgres_store()

    async def scenario() -> list[str]:
        await store.insert(Row(party(T0)), "a")
        later = [party(T0 + timedelta(seconds=i + 1), f"v{i}") for i in range(5)]
        outcomes = await asyncio.gather(
            *(store.replace(p, T0, f"w{i}") for i, p in enumerate(later)), return_exceptions=True
        )
        return ["ok" if o is None else type(o).__name__ for o in outcomes]

    outcomes = asyncio.run(scenario())
    assert outcomes.count("ok") == 1
    assert outcomes.count("PreconditionFailed") == 4


def test_ids_are_never_reused_and_history_is_kept():
    store = postgres_store()

    async def scenario():
        await store.insert(Row(party(T0)), "a")
        with pytest.raises(Conflict):
            await store.insert(Row(party(T0, "again")), "b")
        await store.replace(party(T0 + timedelta(days=1), "renamed"), T0, "c")
        with pytest.raises(PreconditionFailed):
            await store.replace(party(T0 + timedelta(days=2), "stale"), T0, "d")
        now_graph = await store.graph()
        past_graph = await store.graph(datetime.now(UTC) - timedelta(days=365))
        return now_graph.get("party--com.acme.ops").name, past_graph.get("party--com.acme.ops")

    current, past = asyncio.run(scenario())
    assert current == "renamed" and past is None


def test_a_second_process_sees_writes():
    store = postgres_store()
    schema = SCHEMAS[-1]
    other = PostgresStore(
        engine=create_async_engine(
            async_url(DATABASE_URL),
            poolclass=NullPool,
            connect_args={"server_settings": {"search_path": schema}},
        )
    )

    async def scenario():
        before = await other.graph()  # cached in the other process
        await store.insert(Row(party(T0)), "a")
        after = await other.graph()
        return before.get("party--com.acme.ops"), after.get("party--com.acme.ops")

    before, after = asyncio.run(scenario())
    assert before is None and after is not None


def test_a_job_is_claimed_once():
    store = postgres_store()

    async def scenario():
        job = Job(id="job--1", type="render", status="queued", created=T0)
        await store.save_job(job)
        claims = await asyncio.gather(*(store.claim_job(job.id, f"w{i}") for i in range(4)))
        await store.save_job(job.model_copy(update={"status": "succeeded"}))
        return claims, (await store.get_job(job.id)).status

    claims, status = asyncio.run(scenario())
    assert sorted(claims) == [False, False, False, True] and status == "succeeded"


def test_migrations_build_the_schema_the_store_uses():
    from alembic import command
    from alembic.config import Config

    schema = f"test_{uuid.uuid4().hex[:12]}"
    SCHEMAS.append(schema)
    url = async_url(DATABASE_URL)

    async def create() -> None:
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        await engine.dispose()

    asyncio.run(create())
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    config.set_main_option("schema", schema)
    command.upgrade(config, "head")
    store = PostgresStore(
        engine=create_async_engine(
            url, poolclass=NullPool, connect_args={"server_settings": {"search_path": schema}}
        )
    )
    asyncio.run(store.insert(Row(party(T0)), "a"))
    assert asyncio.run(store.object_count()) == 1
