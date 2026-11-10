"""Alembic environment. The URL comes from OPENGRC_DATABASE_URL, or from the
`sqlalchemy.url` option a caller sets (the test suite does)."""

import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from opengrc.persistence.postgres import async_url
from opengrc.persistence.tables import metadata

config = context.config
target_metadata = metadata


def url() -> str:
    configured = config.get_main_option("sqlalchemy.url")
    value = configured or os.environ.get("OPENGRC_DATABASE_URL")
    if not value:
        raise RuntimeError("set OPENGRC_DATABASE_URL")
    return async_url(value)


def run_offline() -> None:
    context.configure(url=url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _migrate(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    engine = create_async_engine(url())
    async with engine.connect() as connection:
        await connection.run_sync(_migrate)
    await engine.dispose()


if context.is_offline_mode():
    run_offline()
else:
    asyncio.run(run_online())
