"""The `ogrl` process: configuration from the environment, then the API.

    OGRL_API_TOKENS      JSON: {"<token>": {"actor_id": "party--...", "roles": ["administrator"],
                            "kind": "person"}}. Tokens start with `ogrl_pat_`. Only their
                            SHA-256 is kept in memory. RFC 0004 open question 1 is how
                            tokens are issued; until then this is the boundary.
    OGRL_LIBRARY_REPO    A git repository for the OGRL standard library (defaults to
                            https://github.com/adversitydotdev/ogrl-library, or a local
                            `library/` / `../ogrl-library/library` checkout if present).
                            Pulls resolve `version` through `library-v{version}` or
                            `v{version}` tags.
    OGRL_DATABASE_URL    Postgres: RDS in production, the compose stack locally
                            (`postgresql://...`). Run `alembic upgrade head` first.
                            Unset: an in-memory store that a restart loses.
    OGRL_S3_BUCKET       Bucket for evidence bytes, document bodies, and render files.
    OGRL_S3_ENDPOINT     Only for an S3-compatible server, such as the compose stack.
    OGRL_S3_PREFIX       Key prefix inside the bucket. Optional.
    OGRL_BLOB_DIR        A directory instead of S3. Unset with no bucket: memory.
    OGRL_EXPORT_REMOTE   Git remote for the snapshot. Unset: export is disabled.
    OGRL_RUN_SCHEDULER   `true` runs the export schedule in this process (RFC 0003 2).
    OGRL_EXPORT_INTERVAL Seconds between scheduled exports. Default 86400.
    OGRL_HARNESS_USER    Operating-system user the shell runner switches to.
    OGRL_HARNESS_<NAME>  The value of `run.env` name <NAME> for the harness.

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

from ogrl import container
from ogrl.access import ActorKind, Principal, Role
from ogrl.adapters.blobs import FileBlobs
from ogrl.adapters.library import GitLibrary
from ogrl.adapters.s3 import S3Blobs
from ogrl.api.app import create_app
from ogrl.auth import ApiTokenAuthenticator
from ogrl.auth.authenticator import digest
from ogrl.operations.exports import ExportSettings
from ogrl.operations.jobs import BackgroundExecutor
from ogrl.operations.store import BlobStore, ObjectStore
from ogrl.persistence.memory import MemoryBlobs, MemoryStore
from ogrl.persistence.postgres import PostgresStore

log = logging.getLogger("ogrl")
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
    repo = env.get("OGRL_LIBRARY_REPO")
    database = env.get("OGRL_DATABASE_URL")
    store: ObjectStore = PostgresStore(database) if database else MemoryStore()
    bucket, blob_dir = env.get("OGRL_S3_BUCKET"), env.get("OGRL_BLOB_DIR")
    blobs: BlobStore
    if bucket:
        blobs = S3Blobs(
            bucket,
            prefix=env.get("OGRL_S3_PREFIX", ""),
            endpoint_url=env.get("OGRL_S3_ENDPOINT") or None,
            region=env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION") or None,
        )
    elif blob_dir:
        blobs = FileBlobs(Path(blob_dir))
    else:
        blobs = MemoryBlobs()
    if not database:
        log.warning("OGRL_DATABASE_URL is unset; the organization database is in memory")
    return container.build(
        authenticator=authenticator_from(env.get("OGRL_API_TOKENS", "")),
        store=store,
        blobs=blobs,
        executor=BackgroundExecutor(),
        library_source=GitLibrary(repo) if repo else container.default_library_source(),
        export=ExportSettings(remote=env.get("OGRL_EXPORT_REMOTE") or None),
        harness_user=env.get("OGRL_HARNESS_USER") or None,
    )


async def export_schedule(c: container.Container, interval: float) -> None:
    """The schedule in RFC 0002 section 8: export on an interval, as the system principal."""
    system = Principal(
        "party--ogrl-scheduler", ORGANIZATION, ActorKind.SERVICE, frozenset({Role.ADMINISTRATOR})
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
    scheduler = os.environ.get("OGRL_RUN_SCHEDULER", "false").lower() == "true"
    interval = float(os.environ.get("OGRL_EXPORT_INTERVAL", "86400"))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = None
        if scheduler and c.exports is not None and os.environ.get("OGRL_EXPORT_REMOTE"):
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
