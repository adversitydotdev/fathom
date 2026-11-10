"""The `opengrc` process: configuration from the environment, then the API.

    OPENGRC_API_TOKENS      JSON: {"<token>": {"actor_id": "party--...", "roles": ["administrator"],
                            "kind": "person"}}. Tokens start with `ogrc_pat_`. Only their
                            SHA-256 is kept in memory. RFC 0004 open question 1 is how
                            tokens are issued; until then this is the boundary.
    OPENGRC_LIBRARY_REPO    A git repository of this project. Pulls resolve `version`
                            through a `library-v{version}` or `v{version}` tag. Unset: the
                            `library/` directory beside the package.
    OPENGRC_DATABASE_URL    Postgres: RDS in production, the compose stack locally
                            (`postgresql://...`). Run `alembic upgrade head` first.
                            Unset: an in-memory store that a restart loses.
    OPENGRC_S3_BUCKET       Bucket for evidence bytes, document bodies, and render files.
    OPENGRC_S3_ENDPOINT     Only for an S3-compatible server, such as the compose stack.
    OPENGRC_S3_PREFIX       Key prefix inside the bucket. Optional.
    OPENGRC_BLOB_DIR        A directory instead of S3. Unset with no bucket: memory.
    OPENGRC_EXPORT_REMOTE   Git remote for the snapshot. Unset: export is disabled.
    OPENGRC_RUN_SCHEDULER   `true` runs the export schedule in this process (RFC 0003 2).
    OPENGRC_EXPORT_INTERVAL Seconds between scheduled exports. Default 86400.
    OPENGRC_HARNESS_USER    Operating-system user the shell runner switches to.
    OPENGRC_HARNESS_<NAME>  The value of `run.env` name <NAME> for the harness.

Credentials for S3 come from the standard AWS chain: the task role on
Fargate, AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY locally.
"""

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from opengrc import container
from opengrc.access import ActorKind, Principal, Role
from opengrc.adapters.blobs import FileBlobs
from opengrc.adapters.library import DirectoryLibrary, GitLibrary
from opengrc.adapters.s3 import S3Blobs
from opengrc.api.app import create_app
from opengrc.auth import ApiTokenAuthenticator
from opengrc.auth.authenticator import digest
from opengrc.operations.exports import ExportSettings
from opengrc.operations.jobs import BackgroundExecutor
from opengrc.operations.store import BlobStore, ObjectStore
from opengrc.persistence.memory import MemoryBlobs, MemoryStore
from opengrc.persistence.postgres import PostgresStore

log = logging.getLogger("opengrc")
ORGANIZATION = "organization"


class StaticMemberships:
    def __init__(self, principals: dict[str, Principal]) -> None:
        self._principals = principals

    async def principal(self, actor_id: str) -> Principal | None:
        return self._principals.get(actor_id)


class StaticTokenStore:
    def __init__(self, actors: dict[str, str]) -> None:
        self._actors = actors  # token digest -> actor id

    async def actor_for_token(self, token_digest: str) -> str | None:
        return self._actors.get(token_digest)


def authenticator_from(raw: str) -> ApiTokenAuthenticator:
    tokens: dict[str, str] = {}
    principals: dict[str, Principal] = {}
    for token, entry in (json.loads(raw) if raw else {}).items():
        actor = entry["actor_id"]
        tokens[digest(token)] = actor
        principals[actor] = Principal(
            actor,
            ORGANIZATION,
            ActorKind(entry.get("kind", "person")),
            frozenset(Role(r) for r in entry.get("roles", ["viewer"])),
        )
    return ApiTokenAuthenticator(StaticTokenStore(tokens), StaticMemberships(principals))


def build_from_env(environ: dict[str, str] | None = None) -> container.Container:
    env = dict(os.environ if environ is None else environ)
    repo = env.get("OPENGRC_LIBRARY_REPO")
    database = env.get("OPENGRC_DATABASE_URL")
    store: ObjectStore = PostgresStore(database) if database else MemoryStore()
    bucket, blob_dir = env.get("OPENGRC_S3_BUCKET"), env.get("OPENGRC_BLOB_DIR")
    blobs: BlobStore
    if bucket:
        blobs = S3Blobs(
            bucket,
            prefix=env.get("OPENGRC_S3_PREFIX", ""),
            endpoint_url=env.get("OPENGRC_S3_ENDPOINT") or None,
            region=env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION") or None,
        )
    elif blob_dir:
        blobs = FileBlobs(Path(blob_dir))
    else:
        blobs = MemoryBlobs()
    if not database:
        log.warning("OPENGRC_DATABASE_URL is unset; the organization database is in memory")
    return container.build(
        authenticator=authenticator_from(env.get("OPENGRC_API_TOKENS", "")),
        store=store,
        blobs=blobs,
        executor=BackgroundExecutor(),
        library_source=GitLibrary(repo) if repo else DirectoryLibrary(container.REPOSITORY_LIBRARY),
        export=ExportSettings(remote=env.get("OPENGRC_EXPORT_REMOTE") or None),
        harness_user=env.get("OPENGRC_HARNESS_USER") or None,
    )


async def export_schedule(c: container.Container, interval: float) -> None:
    """The schedule in RFC 0002 section 8: export on an interval, as the system principal."""
    system = Principal(
        "party--opengrc-scheduler", ORGANIZATION, ActorKind.SERVICE, frozenset({Role.ADMINISTRATOR})
    )
    while True:
        await asyncio.sleep(interval)
        try:
            job = await c.exports.export(system)
            log.info("scheduled export %s queued", job.id)
        except Exception:
            log.exception("scheduled export could not start")


def app_from_env() -> FastAPI:
    c = build_from_env()
    app = create_app(c)
    scheduler = os.environ.get("OPENGRC_RUN_SCHEDULER", "false").lower() == "true"
    interval = float(os.environ.get("OPENGRC_EXPORT_INTERVAL", "86400"))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = None
        if scheduler and c.exports is not None and os.environ.get("OPENGRC_EXPORT_REMOTE"):
            task = asyncio.create_task(export_schedule(c, interval))
        yield
        if isinstance(c.store, PostgresStore):
            await c.store.close()
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app.router.lifespan_context = lifespan
    return app


def run() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app_from_env(), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))  # noqa: S104


if __name__ == "__main__":
    run()
