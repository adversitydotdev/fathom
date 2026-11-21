"""The `ogrl` process: configuration from the environment, API server, and job worker.

OGRL_PROCESS             `api` (default) or `jobs` (RFC 0003 section 2).
OGRL_BIND                `host:port` to bind (default `0.0.0.0:8080`; fallback `PORT`).
OGRL_API_TOKENS          JSON: {"<token>": {"actor_id": "party--...", "roles": ["administrator"],
                            "kind": "person"}}. Tokens start with `ogrl_pat_`. Only their
                            SHA-256 is kept in memory.
OGRL_OIDC_PROVIDERS      JSON map: {"okta": {"issuer": "...", "client_id": "...",
                            "client_secret": "...", "redirect_uri": "..."}}.
OGRL_BOOTSTRAP_ADMIN_EMAILS  Comma-separated emails granted `administrator` on first OIDC login.
OGRL_ALLOWED_ORIGINS     Comma-separated extra origins accepted by the cookie CSRF check.
OGRL_LIBRARY_REPO        A git repository for the OGRL standard library (defaults to
                            https://github.com/adversitydotdev/ogrl-library, or a local
                            `library/` / `../ogrl-library/library` checkout if present).
OGRL_DATABASE_URL        Postgres URL (`postgresql://...`). If unset, assembled from
                            OGRL_DATABASE_HOST/PORT/NAME/USER/PASSWORD/SSLMODE (CloudFormation).
                            If neither is set, uses an ephemeral in-memory store.
OGRL_S3_BUCKET           Bucket for evidence bytes, document bodies, and render files.
OGRL_S3_ENDPOINT         Only for an S3-compatible server, such as the compose stack.
OGRL_S3_PREFIX           Key prefix inside the bucket. Optional.
OGRL_BLOB_DIR            A directory instead of S3. Unset with no bucket: memory.
OGRL_EXPORT_REMOTE       Git remote for the snapshot. Unset: export is disabled.
OGRL_RUN_SCHEDULER       `true` runs the export schedule in this process (RFC 0003 section 2).
OGRL_EXPORT_INTERVAL     Seconds between scheduled exports. Default 86400.
OGRL_QUEUE_URL           Optional SQS queue URL for job worker wakeups.
OGRL_SSM_PREFIX          AWS SSM Parameter Store prefix (e.g. `/ogrl/ogrl`) for harness secrets.
OGRL_HARNESS_USER        Operating-system user the shell runner switches to.
OGRL_HARNESS_<NAME>      The value of `run.env` name <NAME> for the harness.
OTEL_EXPORTER_OTLP_ENDPOINT / LOGFIRE_TOKEN   Optional telemetry destinations (RFC 0003 §11).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote_plus

from fastapi import FastAPI

from ogrl import container, telemetry
from ogrl.access import ActorKind, Principal, Role
from ogrl.adapters.blobs import FileBlobs
from ogrl.adapters.library import GitLibrary
from ogrl.adapters.queue import JobQueue, SqsJobQueue
from ogrl.adapters.s3 import S3Blobs
from ogrl.adapters.secrets import EnvSecrets, SsmSecrets
from ogrl.agent.config import AgentConfig
from ogrl.api.app import create_app
from ogrl.auth import (
    ApiTokenAuthenticator,
    Authenticator,
    ChainAuthenticator,
    SessionAuthenticator,
)
from ogrl.auth.authenticator import digest
from ogrl.auth.oidc import IdentityProvider, OidcProvider
from ogrl.auth.store import (
    AuthStore,
    CompositeMemberships,
    CompositeTokenStore,
    MemoryAuthStore,
    PostgresAuthStore,
)
from ogrl.operations.exports import ExportSettings
from ogrl.operations.jobs import BackgroundExecutor, Executor, QueuedExecutor
from ogrl.operations.library import LibraryPullRequest
from ogrl.operations.providers import ProviderImportRequest
from ogrl.operations.records import Job
from ogrl.operations.renders import RenderRequest
from ogrl.operations.restore import RestoreRequest
from ogrl.operations.store import BlobStore, ObjectStore
from ogrl.persistence.memory import MemoryBlobs, MemoryStore
from ogrl.persistence.postgres import PostgresStore
from ogrl.plugins.ports import Secrets

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


def _static_auth_parts(raw: str) -> tuple[StaticTokenStore, StaticMemberships]:
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
    return StaticTokenStore(tokens), StaticMemberships(principals)


def authenticator_from(raw: str, auth_store: AuthStore | None = None) -> Authenticator:
    static_tokens, static_members = _static_auth_parts(raw)
    if auth_store is None:
        return ApiTokenAuthenticator(static_tokens, static_members)
    tokens = CompositeTokenStore([static_tokens, auth_store])
    memberships = CompositeMemberships([auth_store, static_members])
    return ChainAuthenticator(
        [
            ApiTokenAuthenticator(tokens, memberships),
            SessionAuthenticator(auth_store, memberships),
        ]
    )


def database_url_from_env(env: Mapping[str, str]) -> str | None:
    """Resolve `OGRL_DATABASE_URL`, or compose one from CloudFormation's component vars."""
    direct = env.get("OGRL_DATABASE_URL")
    if direct:
        return direct
    host = env.get("OGRL_DATABASE_HOST")
    if not host:
        return None
    port = env.get("OGRL_DATABASE_PORT", "5432")
    name = env.get("OGRL_DATABASE_NAME", "ogrl")
    user = quote_plus(env.get("OGRL_DATABASE_USER", "ogrl"))
    password = quote_plus(env.get("OGRL_DATABASE_PASSWORD", ""))
    sslmode = env.get("OGRL_DATABASE_SSLMODE")
    creds = f"{user}:{password}@" if password else f"{user}@"
    query = f"?ssl={sslmode}" if sslmode else ""
    return f"postgresql://{creds}{host}:{port}/{name}{query}"


def oidc_providers_from_env(raw: str) -> dict[str, IdentityProvider]:
    if not raw:
        return {}
    parsed = json.loads(raw)
    providers: dict[str, IdentityProvider] = {}
    for name, cfg in parsed.items():
        providers[name] = OidcProvider(
            name=name,
            issuer=cfg["issuer"],
            client_id=cfg["client_id"],
            client_secret=cfg.get("client_secret"),
            redirect_uri=cfg["redirect_uri"],
            scopes=cfg.get("scopes", "openid email profile"),
        )
    return providers


def parse_bind(env: Mapping[str, str]) -> tuple[str, int]:
    raw = env.get("OGRL_BIND")
    if raw:
        host, sep, port_str = raw.rpartition(":")
        if sep and port_str.isdigit():
            return host or "0.0.0.0", int(port_str)  # noqa: S104
    return "0.0.0.0", int(env.get("PORT", "8080"))  # noqa: S104


def build_from_env(environ: dict[str, str] | None = None) -> container.Container:
    env = dict(os.environ if environ is None else environ)
    repo = env.get("OGRL_LIBRARY_REPO")
    database = database_url_from_env(env)
    store: ObjectStore
    auth_store: AuthStore
    if database:
        pg = PostgresStore(database)
        telemetry.instrument_engine(pg.engine)
        store = pg
        auth_store = PostgresAuthStore(pg.engine)
    else:
        log.warning("OGRL_DATABASE_URL is unset; the organization database is in memory")
        store = MemoryStore()
        auth_store = MemoryAuthStore()

    bucket, blob_dir = env.get("OGRL_S3_BUCKET"), env.get("OGRL_BLOB_DIR")
    region = env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION") or None
    blobs: BlobStore
    if bucket:
        blobs = S3Blobs(
            bucket,
            prefix=env.get("OGRL_S3_PREFIX", ""),
            endpoint_url=env.get("OGRL_S3_ENDPOINT") or None,
            region=region,
        )
    elif blob_dir:
        blobs = FileBlobs(Path(blob_dir))
    else:
        blobs = MemoryBlobs()

    queue_url = env.get("OGRL_QUEUE_URL") or ""
    queue: JobQueue | None = SqsJobQueue(queue_url, region=region) if queue_url else None

    process_mode = (env.get("OGRL_PROCESS") or "api").lower()
    run_scheduler = env.get("OGRL_RUN_SCHEDULER", "false").lower() == "true"
    executor: Executor
    if process_mode == "api" and queue is not None and not run_scheduler:
        executor = QueuedExecutor(queue)
    else:
        executor = BackgroundExecutor()

    ssm_prefix = env.get("OGRL_SSM_PREFIX") or ""
    secrets_port: Secrets = (
        SsmSecrets(ssm_prefix, fallback=EnvSecrets(env), region=region)
        if ssm_prefix
        else EnvSecrets(env)
    )

    admin_emails = frozenset(
        e.strip().lower()
        for e in env.get("OGRL_BOOTSTRAP_ADMIN_EMAILS", "").split(",")
        if e.strip()
    )
    allowed_origins = tuple(
        o.strip() for o in env.get("OGRL_ALLOWED_ORIGINS", "").split(",") if o.strip()
    )

    return container.build(
        authenticator=authenticator_from(env.get("OGRL_API_TOKENS", ""), auth_store=auth_store),
        store=store,
        blobs=blobs,
        auth_store=auth_store,
        oidc_providers=oidc_providers_from_env(env.get("OGRL_OIDC_PROVIDERS", "")),
        bootstrap_admin_emails=admin_emails,
        executor=executor,
        queue=queue,
        library_source=GitLibrary(repo) if repo else container.default_library_source(),
        secrets=secrets_port,
        export=ExportSettings(remote=env.get("OGRL_EXPORT_REMOTE") or None),
        harness_user=env.get("OGRL_HARNESS_USER") or None,
        allowed_origins=allowed_origins,
        agent_config=AgentConfig.from_env(env),
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


async def dispatch_queued_job(c: container.Container, job: Job) -> None:
    """Reconstruct and execute a persisted queued job in a dedicated `OGRL_PROCESS=jobs` worker."""
    principal = Principal(
        job.created_by_ref or "party--ogrl-worker",
        ORGANIZATION,
        ActorKind.SERVICE,
        frozenset({Role.ADMINISTRATOR}),
    )
    req = job.request or {}

    if job.type == "library_pull":
        await c.library.pull(principal, LibraryPullRequest.model_validate(req))
    elif job.type == "provider_import":
        await c.providers.import_bundle(principal, ProviderImportRequest.model_validate(req))
    elif job.type == "render":
        program_id = req.get("program_id", "")
        await c.renders.render(principal, program_id, RenderRequest.model_validate(req))
    elif job.type == "git_export":
        await c.exports.export(principal)
    elif job.type == "restore":
        await c.restore.restore(principal, RestoreRequest.model_validate(req))
    else:
        log.warning("worker skipping unsupported queued job %s (type=%s)", job.id, job.type)


async def job_worker_loop(c: container.Container, *, poll_interval: float = 5.0) -> None:
    """Dedicated `OGRL_PROCESS=jobs` worker loop (SQS wakeups + DB safety-net poll)."""
    while True:
        try:
            if c.queue is not None:
                messages = await c.queue.receive(wait_seconds=20, max_messages=5)
                for msg in messages:
                    job = await c.store.get_job(msg.job_id)
                    if (
                        job is not None
                        and job.status == "queued"
                        and await c.store.claim_job(job.id, "worker-dispatch")
                    ):
                        await dispatch_queued_job(c, job)
                    await c.queue.delete(msg.receipt_handle)
            else:
                await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("job worker iteration failed")
            await asyncio.sleep(poll_interval)


def app_from_env() -> FastAPI:
    telemetry.configure()
    c = build_from_env()
    app = create_app(c)
    process_mode = os.environ.get("OGRL_PROCESS", "api").lower()
    scheduler = os.environ.get("OGRL_RUN_SCHEDULER", "false").lower() == "true"
    interval = float(os.environ.get("OGRL_EXPORT_INTERVAL", "86400"))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        tasks: list[asyncio.Task[None]] = []
        if scheduler and c.exports is not None and os.environ.get("OGRL_EXPORT_REMOTE"):
            tasks.append(asyncio.create_task(export_schedule(c, interval)))
        if process_mode == "jobs":
            tasks.append(asyncio.create_task(job_worker_loop(c)))
        yield
        for task in tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if isinstance(c.store, PostgresStore):
            await c.store.close()

    app.router.lifespan_context = lifespan
    return app


def run() -> None:
    import uvicorn

    telemetry.configure()
    host, port = parse_bind(os.environ)
    uvicorn.run(app_from_env(), host=host, port=port)


if __name__ == "__main__":
    run()
