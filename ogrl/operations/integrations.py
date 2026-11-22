"""Integrations, connections, collection, and snapshot runs (RFC 0005).

- Installed packages come from the plugin registry. Connections and snapshot
  rows come from a `ConnectionStore`; secret values from a `SecretVault`.
- Validation and collection are jobs. Only they hand credentials to the
  integration process.
- `evaluate` is the harness's entry for `runner: rule` and `runner: integration`:
  select snapshots (RFC 0001 section 7.6), then run the rule in the kernel or
  the check in the integration, and report the snapshots as artifacts.
"""

import asyncio
import base64
import hashlib
import json
import logging
import re
import secrets
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlencode, urlsplit

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field

from ogrl.access import Authorizer, Permission, Principal, require
from ogrl.errors import Conflict, FieldError, Invalid, NotFound, PreconditionFailed
from ogrl.integrations.apimodel import ApiModel, QuerySpec
from ogrl.integrations.archive import read_archive
from ogrl.integrations.manifest import (
    AwsRoleAuth,
    FieldsAuth,
    Manifest,
    OAuth2Auth,
    Package,
    PackageError,
    load_files,
)
from ogrl.kernel import ids, rules
from ogrl.kernel.bundles import canonical_json, digest
from ogrl.kernel.constraints import timeout_seconds
from ogrl.kernel.graph import Graph
from ogrl.kernel.models import Component, Implementation, Run, System, Test
from ogrl.kernel.parameters import control_values
from ogrl.kernel.timeutil import FRESHNESS_DAYS, format_timestamp, later_than, now, utc
from ogrl.operations.catalog import PackageCatalog
from ogrl.operations.connections import (
    Connection,
    ConnectionStore,
    ForEach,
    InstallRecord,
    QueryDefinition,
    Snapshot,
)
from ogrl.operations.jobs import JobOutcome, JobService
from ogrl.operations.objects import ObjectService
from ogrl.operations.records import Job
from ogrl.operations.sources import Fetcher
from ogrl.operations.store import BlobStore
from ogrl.operations.types import SPECS
from ogrl.plugins import Registry
from ogrl.plugins.ports import (
    IntegrationError,
    IntegrationHost,
    OAuthClient,
    RoleAssumer,
    RunReport,
    SecretVault,
    StoredArtifact,
)

log = logging.getLogger(__name__)

SUPPORTED_AUTH = frozenset({"fields", "oauth2", "aws_role"})
OAUTH_CLIENT_ID = "OAUTH_CLIENT_ID"
OAUTH_CLIENT_SECRET = "OAUTH_CLIENT_SECRET"
OAUTH_REFRESH_TOKEN = "OAUTH_REFRESH_TOKEN"  # written only by the callback
OAUTH_STATE_TTL = timedelta(minutes=10)
AWS_ROLE_ARN = "aws_role_arn"  # the config key an aws_role connection carries
ROLE_ARN = re.compile(r"^arn:aws[a-z-]*:iam::\d{12}:role/[\w+=,.@/-]+$")
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
RATE_LIMIT_RETRIES = 3
SNAPSHOT_REUSE = timedelta(hours=1)  # RFC 0005 section 6: OGRL_SNAPSHOT_REUSE
RETRY_CAP_SECONDS = 60
SNAPSHOT_MAX_BYTES = 100 * 1024 * 1024


def secret_name(connection_id: str, name: str) -> str:
    return f"integrations/{connection_id}/{name}"


def window_days(test: Test) -> int:
    """The freshness window snapshots must fall in. `event-driven` has none; use a day."""
    return FRESHNESS_DAYS.get(test.interval or "", 1)


# --- Request and response shapes --------------------------------------------------------------


class ConnectionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    integration_id: str
    name: str = Field(min_length=1)
    config: dict[str, str] = Field(default_factory=dict)
    auth_kind: str
    bindings: list[str] = Field(default_factory=list)


class ConnectionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    config: dict[str, str] | None = None
    bindings: list[str] | None = None
    state: Literal["disabled", "pending"] | None = None


class SecretWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1)


class CollectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[str] | None = None


class TemplateEnable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    system_refs: list[str] | None = None


class InstallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    enable: bool = True


class QueryWrite(BaseModel):
    """A query source definition (RFC 0006 section 3; `regions` from RFC 0007 section 4)."""

    model_config = ConfigDict(extra="forbid")

    integration_id: str
    name: str
    version: int = Field(default=1, ge=1)
    description: str | None = None
    operation: str
    params: dict[str, str] = Field(default_factory=dict)
    items: str = ""
    fields: dict[str, str] = Field(default_factory=dict)
    regions: list[str] | Literal["*"] | None = None
    for_each: ForEach | None = None


class QueryCheck(BaseModel):
    """Static validation (RFC 0006 section 6)."""

    valid: bool
    source: str
    errors: list["PreviewProblem"] = Field(default_factory=list)
    warnings: list["PreviewProblem"] = Field(default_factory=list)
    item_schema: dict[str, Any] | None = None
    fields: list[dict[str, Any]] = Field(default_factory=list)


class DryRunRequest(QueryWrite):
    connection_id: str
    max_items: int = Field(default=50, ge=1, le=500)


class DryRun(BaseModel):
    """One sample of a query through a real connection; nothing is stored."""

    check: QueryCheck
    items: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    warnings: list["PreviewProblem"] = Field(default_factory=list)
    error: str | None = None


class OperationView(BaseModel):
    id: str  # an operationId (OpenAPI) or <service>.<Operation> (Smithy)
    method: str
    path: str
    summary: str
    protocol: str | None = None  # Smithy: the AWS wire protocol
    regional: bool | None = None  # Smithy: collected once per region
    queryable: bool = True
    reason: str | None = None  # why it cannot be queried, when it cannot
    parameters: list[dict[str, Any]] = Field(default_factory=list)
    items: str | None = None  # where the list is, when described
    fields: list[dict[str, Any]] | None = None  # the item schema, when described


class RulePreviewRequest(BaseModel):
    """A rule run block to try against the latest snapshots, before saving it as a test."""

    model_config = ConfigDict(extra="forbid")

    run: dict[str, Any]
    items: list[dict[str, Any]] | None = None  # evaluate these (a dry run's) instead of snapshots
    query: QueryWrite | None = None  # the unsaved definition those items came from
    control_ref: str | None = None
    implementation_id: str | None = None
    params: dict[str, str] | None = None
    limit: int = Field(default=50, ge=1, le=500)


class PreviewSnapshot(BaseModel):
    id: str
    connection_id: str
    connection_name: str
    collected: datetime
    item_count: int


class PreviewProblem(BaseModel):
    pointer: str
    detail: str


class RulePreview(BaseModel):
    outcome: Literal["pass", "fail", "error", "invalid", "no-data"]
    summary: str
    selected: int = 0
    total: int = 0
    subjects: list[dict[str, str]] = Field(default_factory=list)
    errors: list[PreviewProblem] = Field(default_factory=list)
    warnings: list[PreviewProblem] = Field(default_factory=list)
    snapshots: list[PreviewSnapshot] = Field(default_factory=list)
    params: dict[str, str] = Field(default_factory=dict)
    sample: list[dict[str, Any]] = Field(default_factory=list)


QueryCheck.model_rebuild()
DryRun.model_rebuild()


class TemplateUpdate(BaseModel):
    """A test created from a template whose integration now ships a different version of it."""

    test_id: str
    test_name: str
    template: str
    from_version: str | None = None
    to_version: str
    changes: list[str]
    modified: datetime


class OAuthStart(BaseModel):
    authorize_url: str
    expires: datetime


def _state_key(state: str) -> str:
    """Pending OAuth state is stored under its hash, never as the value itself."""
    return "oauth-state:" + hashlib.sha256(state.encode()).hexdigest()


class IntegrationView(BaseModel):
    id: str
    name: str
    version: str
    publisher: str
    description: str | None = None
    tier: str
    digest: str
    runtime: str
    egress: list[str]
    config: list[dict[str, Any]]
    auth: list[dict[str, Any]]
    resources: list[dict[str, Any]]
    checks: list[dict[str, Any]]
    templates: list[dict[str, Any]]


def integration_view(package: Package) -> IntegrationView:
    m = package.manifest
    return IntegrationView(
        id=m.id,
        name=m.name,
        version=m.version,
        publisher=m.publisher,
        description=m.description,
        tier=package.tier,
        digest=package.digest,
        runtime=m.runtime.kind,
        egress=list(m.egress),
        config=[c.model_dump(exclude_none=True) for c in m.config],
        auth=[
            {**a.model_dump(exclude_none=True), "supported": a.kind in SUPPORTED_AUTH}
            for a in m.auth
        ],
        resources=[
            {
                "name": r.name,
                "version": r.version,
                "source": f"{m.id}/{r.name}@{r.version}",
                "fields": schema_fields(package.schema(r.name, r.version)),
            }
            for r in m.resources
        ],
        checks=[
            {
                "name": c.name,
                "version": c.version,
                "check": f"{m.id}/{c.name}@{c.version}",
                "sources": [f"{m.id}/{name}@{_major(m, name)}" for name in c.sources],
            }
            for c in m.checks
        ],
        templates=[
            {
                "name": t.name,
                "fulfills_ref": t.fulfills_ref,
                "test_name": t.test.get("name"),
                "control_ref": t.test.get("control_ref"),
                "runner": (t.test.get("run") or {}).get("runner"),
            }
            for t in m.templates
        ],
    )


def schema_fields(schema: Mapping[str, Any]) -> list[dict[str, Any]]:
    """What a rule author can write after `item.`: each property, its type, its description."""
    required = set(schema.get("required") or [])
    out = []
    for name, spec in (schema.get("properties") or {}).items():
        kind = spec.get("type", "any")
        kinds = kind if isinstance(kind, list) else [kind]
        if spec.get("type") == "array" and isinstance(spec.get("items"), dict):
            kinds = [f"array of {spec['items'].get('type', 'any')}"]
        out.append(
            {
                "name": name,
                "type": " or ".join(k for k in kinds if k != "null") or "null",
                "nullable": "null" in kinds,
                "required": name in required,
                **({"description": spec["description"]} if spec.get("description") else {}),
            }
        )
    return out


def _major(manifest: Any, resource: str) -> int:
    return max(r.version for r in manifest.resources if r.name == resource)


# --- Snapshots ---------------------------------------------------------------------------------


def _strip(value: Any, schema: Mapping[str, Any], path: str, removed: list[str]) -> Any:
    """Drop object properties the schema does not declare (RFC 0005 section 6, step 1)."""
    if isinstance(value, dict) and isinstance(schema.get("properties"), dict):
        properties = schema["properties"]
        if schema.get("additionalProperties") is True:
            return value
        kept = {}
        for key, item in value.items():
            if key in properties:
                kept[key] = _strip(item, properties[key], f"{path}/{key}", removed)
            else:
                removed.append(f"{path}/{key}")
        return kept
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        return [_strip(v, schema["items"], f"{path}/{i}", removed) for i, v in enumerate(value)]
    return value


def build_snapshot(
    source: str,
    collected: datetime,
    complete: bool,
    items: list[Mapping[str, Any]],
    schema: Mapping[str, Any],
    extra: Mapping[str, Any] | None = None,
) -> tuple[bytes, list[str]]:
    """The RFC 0001 snapshot document in canonical JSON, and warnings."""
    validator = Draft202012Validator(schema)
    cleaned = []
    removed: list[str] = []
    for index, item in enumerate(items):
        kept = _strip(dict(item), schema, f"/items/{index}", removed)
        error = next(iter(validator.iter_errors(kept)), None)
        if error is not None:
            where = "/".join(str(p) for p in error.absolute_path)
            raise IntegrationError(
                "protocol", f"item {index}{' at ' + where if where else ''}: {error.message}"
            )
        cleaned.append(kept)
    warnings = []
    if removed:
        fields = sorted({r.split("/", 3)[-1] for r in removed})
        warnings.append(f"removed undeclared fields: {', '.join(fields)}")
    document = {
        "source": source,
        "collected": format_timestamp(collected),
        "complete": complete,
        "items": cleaned,
        **(extra or {}),
    }
    return canonical_json(document), warnings


@dataclass(frozen=True)
class Selected:
    connection: Connection
    snapshot: Snapshot
    document: dict[str, Any]


class SelectionError(Exception):
    pass


# --- The service -------------------------------------------------------------------------------


class IntegrationService:
    def __init__(
        self,
        objects: ObjectService,
        blobs: BlobStore,
        authorizer: Authorizer,
        jobs: JobService,
        connections: ConnectionStore,
        vault: SecretVault,
        host: IntegrationHost,
        packages: "Registry[Package] | PackageCatalog",
        clock: Callable[[], datetime] = now,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        reuse: timedelta = SNAPSHOT_REUSE,
        oauth: OAuthClient | None = None,
        assumer: RoleAssumer | None = None,
        public_url: str | None = None,
        fetcher: Fetcher | None = None,
        allow_local: bool = False,
    ) -> None:
        self._fetcher = fetcher
        self._allow_local = allow_local
        self._reuse = reuse
        self._oauth = oauth
        self._assumer = assumer
        self._public_url = public_url.rstrip("/") if public_url else None
        self._objects = objects
        self._blobs = blobs
        self._authorizer = authorizer
        self._jobs = jobs
        self._store = connections
        self._vault = vault
        self._host = host
        self._packages = packages
        self._clock = clock
        self._sleep = sleep
        self._locks: dict[str, asyncio.Lock] = {}

    # --- installed integrations ----------------------------------------------------------------

    def package(self, integration_id: str) -> Package:
        package = self._packages.get(integration_id)
        if package is None:
            raise NotFound(f"no integration {integration_id} is installed")
        return package

    async def ready(self) -> None:
        """Load whatever versions another process enabled since we last looked."""
        if isinstance(self._packages, PackageCatalog):
            await self._packages.sync()

    async def list_integrations(self, principal: Principal) -> list[IntegrationView]:
        require(self._authorizer, principal, Permission.PROGRAMS_READ)
        await self.ready()
        return [integration_view(self.package(i)) for i in self._packages.names()]

    async def get_integration(self, principal: Principal, integration_id: str) -> IntegrationView:
        require(self._authorizer, principal, Permission.PROGRAMS_READ)
        await self.ready()
        return integration_view(self.package(integration_id))

    async def enable_template(
        self, principal: Principal, integration_id: str, name: str, request: TemplateEnable
    ) -> Any:
        """Create an organization test from a template (RFC 0005 section 8)."""
        await self.ready()
        package = self.package(integration_id)
        template = package.manifest.template(name)
        if template is None:
            raise NotFound(f"{integration_id} has no template {name}")
        body = {
            **template.test,
            "id": request.id,
            "fulfills_ref": template.fulfills_ref,
            "system_refs": request.system_refs,
            "extensions": {
                "dev.ogrl.integration": {
                    "integration": integration_id,
                    "version": package.manifest.version,
                    "template": name,
                }
            },
        }
        return await self._objects.create(principal, SPECS["test"], body)

    # --- connections ---------------------------------------------------------------------------

    async def list_connections(self, principal: Principal) -> list[Connection]:
        require(self._authorizer, principal, Permission.PROGRAMS_READ)
        return await self._store.list_connections()

    async def get_connection(self, principal: Principal, connection_id: str) -> Connection:
        require(self._authorizer, principal, Permission.PROGRAMS_READ)
        return await self._connection(connection_id)

    async def _connection(self, connection_id: str) -> Connection:
        connection = await self._store.get_connection(connection_id)
        if connection is None:
            raise NotFound(f"no connection {connection_id}")
        return connection

    def _check_config(
        self, package: Package, config: Mapping[str, str], auth_kind: str
    ) -> list[FieldError]:
        errors = []
        declared = {c.name: c for c in package.manifest.config}
        if auth_kind == "aws_role":
            arn = config.get(AWS_ROLE_ARN, "")
            if not ROLE_ARN.match(arn):
                errors.append(
                    FieldError(
                        "an IAM role ARN is required for aws_role", f"/config/{AWS_ROLE_ARN}"
                    )
                )
        extra = set(config) - set(declared) - ({AWS_ROLE_ARN} if auth_kind == "aws_role" else set())
        for key in sorted(extra):
            errors.append(FieldError(f"{package.id} has no config {key}", f"/config/{key}"))
        for field in declared.values():
            value = config.get(field.name)
            if value in (None, ""):
                if field.required:
                    errors.append(FieldError(f"{field.label} is required", f"/config/{field.name}"))
                continue
            if field.pattern and not rules_match(field.pattern, value):
                errors.append(
                    FieldError(f"{field.label} must match {field.pattern}", f"/config/{field.name}")
                )
        return errors

    async def _check_bindings(self, bindings: list[str]) -> list[FieldError]:
        errors = []
        if len(set(bindings)) != len(bindings):
            errors.append(FieldError("each binding is listed once", "/bindings"))
        for index, ref in enumerate(bindings):
            row = await self._objects.store.get(ref)
            if row is None or not isinstance(row.obj, (Component, System)) or row.obj.is_revoked:
                errors.append(
                    FieldError("a binding is a component or system id", f"/bindings/{index}")
                )
        return errors

    async def create_connection(self, principal: Principal, write: ConnectionWrite) -> Connection:
        require(self._authorizer, principal, Permission.INTEGRATIONS_MANAGE)
        await self.ready()
        package = self._packages.get(write.integration_id)
        if package is None:
            raise Invalid(errors=[FieldError("no such integration", "/integration_id")])
        errors = self._check_config(package, write.config, write.auth_kind)
        if package.manifest.auth_kind(write.auth_kind) is None:
            errors.append(FieldError(f"{package.id} offers no {write.auth_kind}", "/auth_kind"))
        elif write.auth_kind not in SUPPORTED_AUTH:
            errors.append(FieldError(f"{write.auth_kind} is not supported yet", "/auth_kind"))
        errors += await self._check_bindings(write.bindings)
        if errors:
            raise Invalid(errors=errors)
        connection_id = write.id or ids.mint("connection")
        try:
            ids.split(connection_id)
        except ValueError as exc:
            raise Invalid(errors=[FieldError(str(exc), "/id")]) from exc
        if await self._store.get_connection(connection_id) is not None:
            raise Conflict(f"id {connection_id} is in use", slug="id-taken")
        stamp = utc(self._clock())
        connection = Connection(
            id=connection_id,
            integration_id=write.integration_id,
            name=write.name,
            config=write.config,
            auth_kind=write.auth_kind,
            bindings=write.bindings,
            external_id=secrets.token_urlsafe(24) if write.auth_kind == "aws_role" else None,
            created=stamp,
            modified=stamp,
            created_by_ref=principal.actor_id,
        )
        await self._store.insert_connection(connection)
        return connection

    async def _save(self, old: Connection, **changes: Any) -> Connection:
        updated = old.model_copy(
            update={**changes, "modified": later_than(old.modified, self._clock())}
        )
        await self._store.replace_connection(updated, old.modified)
        return updated

    async def update_connection(
        self, principal: Principal, connection_id: str, patch: ConnectionPatch, if_match: datetime
    ) -> Connection:
        require(self._authorizer, principal, Permission.INTEGRATIONS_MANAGE)
        old = await self._connection(connection_id)
        changes = patch.model_dump(exclude_unset=True, exclude_none=True)
        errors: list[FieldError] = []
        if "config" in changes:
            package = self.package(old.integration_id)
            errors += self._check_config(package, changes["config"], old.auth_kind)
        if "bindings" in changes:
            errors += await self._check_bindings(changes["bindings"])
        if errors:
            raise Invalid(errors=errors)
        if changes.get("state") == "pending":
            changes.update(identity=None, last_error=None)
        if utc(if_match) != old.modified:
            raise PreconditionFailed(f"{connection_id} changed since {if_match}")
        return await self._save(old, **changes)

    async def delete_connection(self, principal: Principal, connection_id: str) -> None:
        require(self._authorizer, principal, Permission.INTEGRATIONS_MANAGE)
        connection = await self._connection(connection_id)
        for name in connection.secrets_set:
            await asyncio.to_thread(self._vault.delete, secret_name(connection_id, name))
        await self._store.delete_connection(connection_id)

    async def put_secret(
        self, principal: Principal, connection_id: str, name: str, write: SecretWrite
    ) -> Connection:
        require(self._authorizer, principal, Permission.INTEGRATIONS_MANAGE)
        connection = await self._connection(connection_id)
        auth = self.package(connection.integration_id).manifest.auth_kind(connection.auth_kind)
        names = (
            [f.name for f in auth.fields]
            if isinstance(auth, FieldsAuth)
            else [OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET]
            if isinstance(auth, OAuth2Auth)
            else []
        )
        if name not in names:
            raise NotFound(f"{connection.auth_kind} has no secret {name}")
        await asyncio.to_thread(self._vault.put, secret_name(connection_id, name), write.value)
        secrets = sorted({*connection.secrets_set, name})
        return await self._save(connection, secrets_set=secrets, state="pending", identity=None)

    async def _secret(self, connection_id: str, name: str) -> str | None:
        return await asyncio.to_thread(self._vault.get, secret_name(connection_id, name))

    async def _credentials(self, connection: Connection, package: Package) -> dict[str, str]:
        """The environment one validate or collect operation gets (RFC 0005 section 7)."""
        auth = package.manifest.auth_kind(connection.auth_kind)
        env = {"OGRL_CONNECTION_ID": connection.id}
        if isinstance(auth, FieldsAuth):
            missing = []
            for field in auth.fields:
                value = await self._secret(connection.id, field.name)
                if value is None:
                    missing.append(field.name)
                else:
                    env[field.name] = value
            if missing:
                raise IntegrationError("invalid_config", f"no value set for {', '.join(missing)}")
            return env
        if isinstance(auth, OAuth2Auth):
            env["OGRL_ACCESS_TOKEN"] = await self._access_token(connection, auth)
            return env
        if isinstance(auth, AwsRoleAuth):
            if self._assumer is None:
                raise IntegrationError("invalid_config", "this server has no STS client")
            arn = connection.config.get(AWS_ROLE_ARN, "")
            session = f"ogrl-{connection.id.rsplit('--', 1)[-1][:40]}"
            env.update(await self._assumer.assume(arn, connection.external_id or "", session))
            return env
        raise IntegrationError("invalid_config", f"{connection.auth_kind} is not supported")

    # --- bring-your-own OAuth ------------------------------------------------------------------

    def _redirect_uri(self) -> str:
        if not self._public_url:
            raise Invalid(
                "OAuth needs a stable origin: set OGRL_PUBLIC_URL (RFC 0005 section 5)",
                slug="oauth-needs-public-url",
            )
        return f"{self._public_url}/v1/oauth/callback"

    @staticmethod
    def _vendor_url(template: str, config: Mapping[str, str]) -> str:
        try:
            url = template.format_map(dict(config))
        except (KeyError, ValueError) as exc:
            raise IntegrationError("invalid_config", f"{template} needs config {exc}") from exc
        parts = urlsplit(url)
        if parts.scheme != "https" and not (
            parts.scheme == "http" and parts.hostname in LOCAL_HOSTS
        ):
            raise IntegrationError("invalid_config", f"{url} is not an https URL")
        return url

    def _oauth_auth(self, connection: Connection) -> OAuth2Auth:
        auth = self.package(connection.integration_id).manifest.auth_kind(connection.auth_kind)
        if not isinstance(auth, OAuth2Auth):
            raise Invalid(f"{connection.id} does not use oauth2")
        if self._oauth is None:
            raise Invalid("this server has no OAuth client")
        return auth

    async def _access_token(self, connection: Connection, auth: OAuth2Auth) -> str:
        assert self._oauth is not None
        client_id = await self._secret(connection.id, OAUTH_CLIENT_ID)
        client_secret = await self._secret(connection.id, OAUTH_CLIENT_SECRET)
        refresh = await self._secret(connection.id, OAUTH_REFRESH_TOKEN)
        if not client_id or not client_secret:
            raise IntegrationError("invalid_config", "set OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET")
        if not refresh:
            raise IntegrationError("invalid_config", "authorize the connection with the vendor")
        body = await self._oauth.token(
            self._vendor_url(auth.token_url, connection.config),
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        token = body.get("access_token")
        if not isinstance(token, str) or not token:
            raise IntegrationError("auth_failed", "the token endpoint returned no access_token")
        rotated = body.get("refresh_token")
        if isinstance(rotated, str) and rotated and rotated != refresh:
            await asyncio.to_thread(
                self._vault.put, secret_name(connection.id, OAUTH_REFRESH_TOKEN), rotated
            )
        return token

    async def oauth_start(self, principal: Principal, connection_id: str) -> "OAuthStart":
        """Step 1 of RFC 0005 section 5: the vendor URL to send the operator to."""
        require(self._authorizer, principal, Permission.INTEGRATIONS_MANAGE)
        connection = await self._connection(connection_id)
        auth = self._oauth_auth(connection)
        redirect_uri = self._redirect_uri()
        client_id = await self._secret(connection.id, OAUTH_CLIENT_ID)
        if not client_id:
            raise Invalid(f"set {OAUTH_CLIENT_ID} and {OAUTH_CLIENT_SECRET} first")
        try:
            authorize = self._vendor_url(auth.authorize_url, connection.config)
        except IntegrationError as exc:
            raise Invalid(exc.message) from exc
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        expires = utc(self._clock()) + OAUTH_STATE_TTL
        pending = {
            "connection_id": connection.id,
            "actor": principal.actor_id,
            "verifier": verifier if auth.pkce else None,
            "expires": format_timestamp(expires),
        }
        await self._objects.store.set_meta(_state_key(state), json.dumps(pending))
        query = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            **({"scope": " ".join(auth.scopes)} if auth.scopes else {}),
        }
        if auth.pkce:
            challenge = hashlib.sha256(verifier.encode()).digest()
            query["code_challenge"] = base64.urlsafe_b64encode(challenge).rstrip(b"=").decode()
            query["code_challenge_method"] = "S256"
        separator = "&" if urlsplit(authorize).query else "?"
        return OAuthStart(authorize_url=authorize + separator + urlencode(query), expires=expires)

    async def oauth_callback(
        self, state: str | None, code: str | None, error: str | None
    ) -> Connection:
        """Steps 2 and 3: verify state, exchange the code, keep the refresh token."""
        if not state:
            raise Invalid("the callback carries no state", slug="oauth-state")
        key = _state_key(state)
        raw = await self._objects.store.get_meta(key)
        if raw is None:
            raise Invalid("this authorization is unknown or was already used", slug="oauth-state")
        await self._objects.store.set_meta(key, None)  # single use, before anything can fail
        pending = json.loads(raw)
        if utc(datetime.fromisoformat(pending["expires"].replace("Z", "+00:00"))) < utc(
            self._clock()
        ):
            raise Invalid("this authorization expired; start again", slug="oauth-state")
        connection = await self._connection(pending["connection_id"])
        if error:
            raise Invalid(f"the vendor refused: {error}", slug="oauth-denied")
        if not code:
            raise Invalid("the callback carries no code", slug="oauth-state")
        auth = self._oauth_auth(connection)
        assert self._oauth is not None
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._redirect_uri(),
            "client_id": await self._secret(connection.id, OAUTH_CLIENT_ID) or "",
            "client_secret": await self._secret(connection.id, OAUTH_CLIENT_SECRET) or "",
        }
        if pending.get("verifier"):
            form["code_verifier"] = pending["verifier"]
        try:
            body = await self._oauth.token(
                self._vendor_url(auth.token_url, connection.config), form
            )
        except IntegrationError as exc:
            await self._save(connection, state="failing", last_error=f"{exc.kind}: {exc.message}")
            raise Invalid(exc.message, slug=f"integration-{exc.kind}") from exc
        refresh = body.get("refresh_token")
        if not isinstance(refresh, str) or not refresh:
            message = "the vendor issued no refresh token; request offline access in its app"
            await self._save(connection, state="failing", last_error=f"auth_failed: {message}")
            raise Invalid(message, slug="integration-auth_failed")
        await asyncio.to_thread(
            self._vault.put, secret_name(connection.id, OAUTH_REFRESH_TOKEN), refresh
        )
        secrets_set = sorted({*connection.secrets_set, OAUTH_REFRESH_TOKEN})
        return await self._save(
            connection, secrets_set=secrets_set, state="pending", identity=None, last_error=None
        )

    # --- validation and collection -------------------------------------------------------------

    async def validate(self, principal: Principal, connection_id: str) -> Job:
        require(self._authorizer, principal, Permission.COLLECTIONS_RUN)
        await self.ready()
        connection = await self._connection(connection_id)
        package = self.package(connection.integration_id)

        async def work(job: Job) -> JobOutcome:
            current = await self._connection(connection_id)
            try:
                env = await self._credentials(current, package)
                report = await self._host.validate(package, current.config, env)
            except IntegrationError as exc:
                await self._save(current, state="failing", last_error=f"{exc.kind}: {exc}")
                raise Invalid(f"{exc.kind}: {exc.message}", slug=f"integration-{exc.kind}") from exc
            await self._save(
                current,
                state="active" if current.state != "disabled" else "disabled",
                identity=report.identity,
                granted_scopes=list(report.granted_scopes),
                last_validated=utc(self._clock()),
                last_error=None,
            )
            return JobOutcome(
                report={"identity": report.identity, "warnings": list(report.warnings)}
            )

        return await self._jobs.submit(
            principal, "collection", {"connection_id": connection_id, "validate": True}, work
        )

    async def collect(
        self, principal: Principal, connection_id: str, request: CollectionRequest
    ) -> Job:
        require(self._authorizer, principal, Permission.COLLECTIONS_RUN)
        connection = await self._connection(connection_id)
        if connection.state == "disabled":
            raise Invalid(f"{connection_id} is disabled")
        await self.ready()
        package = self.package(connection.integration_id)
        manifest = package.manifest
        if request.sources is None:
            sources = [f"{manifest.id}/{r.name}@{r.version}" for r in manifest.resources]
        else:
            sources = request.sources
            errors = []
            for index, text in enumerate(sources):
                try:
                    ref = rules.parse_reference(text)
                except ValueError as exc:
                    errors.append(FieldError(str(exc), f"/sources/{index}"))
                    continue
                defined = {q.source for q in await self._store.list_queries()}
                if ref.integration != manifest.id or (
                    not manifest.resource(ref.name, ref.major) and text not in defined
                ):
                    errors.append(
                        FieldError(f"{manifest.id} does not emit {text}", f"/sources/{index}")
                    )
            if errors:
                raise Invalid(errors=errors)

        async def work(job: Job) -> JobOutcome:
            made = []
            for text in sources:
                snapshot = await self.collect_now(
                    connection_id, rules.parse_reference(text), job.id
                )
                made.append(snapshot.id)
            return JobOutcome(report={"snapshots": made})

        return await self._jobs.submit(
            principal, "collection", {"connection_id": connection_id, "sources": sources}, work
        )

    async def collect_now(
        self, connection_id: str, source: rules.Reference, job_id: str | None = None
    ) -> Snapshot:
        """One collection. Raises Invalid (carrying the integration error) when it fails."""
        lock = self._locks.setdefault(connection_id, asyncio.Lock())
        async with lock:  # one collection at a time per connection (RFC 0005 section 6)
            connection = await self._connection(connection_id)
            package, schema, query = await self.resolve(source)
            try:
                env = await self._credentials(connection, package)
                report = await self._collect_with_retries(
                    package, source, connection, env, query.query() if query else None
                )
                collected = utc(self._clock())
                content, warnings = build_snapshot(
                    str(source),
                    collected,
                    report.complete,
                    list(report.items),
                    schema,
                    # The snapshot records the definition it was collected with (RFC 0006 s7).
                    {"query": _definition(query)} if query else None,
                )
                if len(content) > SNAPSHOT_MAX_BYTES:
                    raise IntegrationError(
                        "protocol", f"the snapshot exceeds {SNAPSHOT_MAX_BYTES} bytes"
                    )
            except IntegrationError as exc:
                await self._save(
                    connection, state="failing", last_error=f"{exc.kind}: {exc.message}"
                )
                raise Invalid(f"{exc.kind}: {exc.message}", slug=f"integration-{exc.kind}") from exc

            snapshot_id = ids.mint("snapshot")
            sha = digest(content)
            key = (
                f"snapshots/{connection_id}/{source}/{format_timestamp(collected)}-{sha[:12]}.json"
            )
            uri = await self._blobs.put(key, content, rules.SNAPSHOT_MEDIA_TYPE)
            snapshot = Snapshot(
                id=snapshot_id,
                connection_id=connection_id,
                source=str(source),
                collected=collected,
                complete=report.complete,
                reason=report.reason,
                item_count=len(report.items),
                size=len(content),
                uri=uri,
                digest=sha,
                job_id=job_id,
                warnings=warnings or None,
            )
            await self._store.insert_snapshot(snapshot)
            if connection.state in ("pending", "failing"):
                await self._save(connection, state="active", last_error=None)
            return snapshot

    async def _collect_with_retries(
        self,
        package: Package,
        source: rules.Reference,
        connection: Connection,
        env: dict[str, str],
        query: Mapping[str, Any] | None = None,
    ) -> Any:
        attempt = 0
        while True:
            try:
                return await self._host.collect(
                    package, source.name, source.major, connection.config, env, query
                )
            except IntegrationError as exc:
                attempt += 1
                if exc.kind != "rate_limited" or attempt > RATE_LIMIT_RETRIES:
                    raise
                await self._sleep(min(exc.retry_after or 1, RETRY_CAP_SECONDS))

    # --- snapshots -----------------------------------------------------------------------------

    async def list_snapshots(
        self, principal: Principal, connection_id: str | None, source: str | None
    ) -> list[Snapshot]:
        require(self._authorizer, principal, Permission.PROGRAMS_READ)
        return await self._store.list_snapshots(connection_id, source)

    async def get_snapshot(self, principal: Principal, snapshot_id: str) -> Snapshot:
        require(self._authorizer, principal, Permission.PROGRAMS_READ)
        snapshot = await self._store.get_snapshot(snapshot_id)
        if snapshot is None:
            raise NotFound(f"no snapshot {snapshot_id}")
        return snapshot

    async def snapshot_content(self, principal: Principal, snapshot_id: str) -> bytes:
        snapshot = await self.get_snapshot(principal, snapshot_id)
        content = await self._blobs.get(snapshot.uri)
        if content is None:
            raise NotFound(f"the bytes of {snapshot_id} are missing")
        return content

    # --- harness entry -------------------------------------------------------------------------

    @staticmethod
    def bound(
        impl: Implementation, graph: Graph, connections: list[Connection]
    ) -> list[Connection]:
        """Connections bound to the implementation's scope (RFC 0005 section 5)."""
        if impl.component_ref:
            targets = {impl.component_ref}
        else:
            targets = {impl.system_ref} if impl.system_ref else set()
            system = graph.get(impl.system_ref) if impl.system_ref else None
            if isinstance(system, System):
                targets |= set(system.component_refs or [])
        return [
            c for c in connections if c.state != "disabled" and targets.intersection(c.bindings)
        ]

    async def select(
        self, test: Test, impl: Implementation, graph: Graph, at: datetime
    ) -> dict[str, list[Selected]]:
        """Snapshot selection, RFC 0001 section 7.6. Raises SelectionError."""
        assert test.run is not None
        bound = self.bound(impl, graph, await self._store.list_connections())
        # The freshness window bounds what RFC 0001 allows; the reuse window keeps a run from
        # re-reading old vendor state when a fresh collection is cheap (RFC 0005 section 6).
        not_before = max(at - timedelta(days=window_days(test)), at - self._reuse)
        chosen: dict[str, list[Selected]] = {}
        for text in test.run.sources_read():
            source = rules.parse_reference(text)
            matching = [c for c in bound if c.integration_id == source.integration]
            if not matching:
                scope = impl.component_ref or impl.system_ref or impl.id
                raise SelectionError(f"no connection of {source.integration} is bound to {scope}")
            picked = []
            for connection in matching:
                snapshot = await self._store.latest_snapshot(connection.id, text, not_before, at)
                if snapshot is None:
                    try:
                        snapshot = await self.collect_now(connection.id, source)
                    except (Invalid, NotFound) as exc:
                        raise SelectionError(
                            f"collecting {text} from {connection.name}: {exc.detail}"
                        ) from exc
                    if not snapshot.complete:
                        reason = snapshot.reason or "no reason given"
                        raise SelectionError(
                            f"{text} from {connection.name} is incomplete: {reason}"
                        )
                content = await self._blobs.get(snapshot.uri)
                if content is None or digest(content) != snapshot.digest:
                    raise SelectionError(f"the bytes of {snapshot.id} are missing or altered")
                picked.append(Selected(connection, snapshot, json.loads(content)))
            chosen[text] = picked
        return chosen

    async def evaluate(
        self, test: Test, impl: Implementation, parameters: Mapping[str, str], graph: Graph
    ) -> RunReport:
        assert test.run is not None
        await self.ready()
        at = utc(self._clock())
        try:
            chosen = await self.select(test, impl, graph, at)
        except SelectionError as exc:
            return RunReport("error", str(exc)[:2048], at)
        selected = [s for group in chosen.values() for s in group]
        observed = min(s.snapshot.collected for s in selected)
        artifacts = [
            StoredArtifact(
                name=f"{s.snapshot.source} from {s.connection.name}",
                media_type=rules.SNAPSHOT_MEDIA_TYPE,
                uri=s.snapshot.uri,
                digest=s.snapshot.digest,
                collected=s.snapshot.collected,
            )
            for s in selected
        ]
        if test.run.runner == "rule":
            items = [item for s in chosen[test.run.source or ""] for item in s.document["items"]]
            out = rules.evaluate(test.run, items, parameters, observed)
            subjects = [{k: v for k, v in vars(s).items() if v is not None} for s in out.subjects]
            return RunReport(
                out.outcome, out.summary, observed, artifacts=artifacts, subjects=subjects
            )

        check = rules.parse_reference(test.run.check or "")
        package = self._packages.get(check.integration)
        if package is None or package.manifest.check(check.name, check.major) is None:
            return RunReport("error", f"no installed integration provides {check}", observed)
        documents = {
            source: canonical_json(
                {
                    "source": source,
                    "collected": format_timestamp(min(s.snapshot.collected for s in group)),
                    "complete": True,
                    "items": [item for s in group for item in s.document["items"]],
                }
            )
            for source, group in chosen.items()
        }
        try:
            report = await self._host.check(
                package,
                check.name,
                check.major,
                test.run.with_ or {},
                parameters,
                documents,
                timeout_seconds(test.run.timeout),
            )
        except IntegrationError as exc:
            return RunReport(
                "error", f"{check}: {exc.message}"[:2048], observed, artifacts=artifacts
            )
        return RunReport(
            report.outcome,
            report.summary,
            observed,
            artifacts=artifacts,
            subjects=list(report.subjects),
        )

    # --- query sources (RFC 0006) ------------------------------------------------------------

    async def resolve(
        self, source: rules.Reference
    ) -> tuple[Package, dict[str, Any], QueryDefinition | None]:
        """The package, item schema, and (for a query source) definition behind a source."""
        package = self.package(source.integration)
        if package.manifest.resource(source.name, source.major) is not None:
            return package, package.schema(source.name, source.major), None
        for query in await self._store.list_queries():
            if query.source == str(source):
                if not package.manifest.queryable:
                    raise Invalid(
                        f"{package.id} {package.manifest.version} no longer supports query sources"
                    )
                return package, query.item_schema, query
        raise Invalid(
            f"{package.id} {package.manifest.version} does not emit {source}, "
            "and no query source defines it"
        )

    def _api_model(self, integration_id: str) -> tuple[Package, ApiModel]:
        package = self.package(integration_id)
        try:
            model = package.api_model()
        except PackageError as exc:
            raise Invalid(str(exc)) from exc
        if model is None:
            raise Invalid(
                f"{integration_id} does not support query sources (no API model in its manifest)",
                errors=[
                    FieldError(
                        "this integration bundles no OpenAPI description or Smithy model",
                        "/integration_id",
                    )
                ],
            )
        return package, model

    async def search_operations(
        self, principal: Principal, integration_id: str, text: str
    ) -> list[OperationView]:
        """Queryable operations whose name, path, or summary contain every word."""
        require(self._authorizer, principal, Permission.PROGRAMS_READ)
        await self.ready()
        _, model = self._api_model(integration_id)
        return [OperationView(**view) for view in model.search(text, limit=100)]

    async def describe_operation(
        self, principal: Principal, integration_id: str, operation: str
    ) -> OperationView:
        """Parameters, the flattened item schema, and the read classification of one operation."""
        require(self._authorizer, principal, Permission.PROGRAMS_READ)
        await self.ready()
        _, model = self._api_model(integration_id)
        view = model.describe(operation)
        if view is None:
            raise NotFound(f"{integration_id} has no operation {operation}")
        return OperationView(**view)

    async def _check_query(self, write: QueryWrite) -> QueryCheck:
        source = f"{write.integration_id}/{write.name}@{write.version}"
        try:
            package, model = self._api_model(write.integration_id)
        except (Invalid, NotFound) as exc:
            problem = PreviewProblem(pointer="/integration_id", detail=exc.detail)
            return QueryCheck(valid=False, source=source, errors=[problem])
        spec = QuerySpec(
            write.operation,
            write.params,
            write.items,
            write.fields,
            write.regions,
            write.for_each.model_dump() if write.for_each else None,
        )
        problems, schema = model.validate(spec, name=write.name)
        errors = [
            PreviewProblem(pointer=p.pointer, detail=p.detail) for p in problems if not p.warning
        ]
        warnings = [
            PreviewProblem(pointer=p.pointer, detail=p.detail) for p in problems if p.warning
        ]
        if any(r.name == write.name for r in package.manifest.resources):
            errors.append(
                PreviewProblem(
                    pointer="/name", detail=f"{package.id} has a built-in resource {write.name!r}"
                )
            )
        if any(q.source == source for q in await self._store.list_queries()):
            errors.append(
                PreviewProblem(
                    pointer="/version",
                    detail=f"{source} exists; versions are immutable, so save it as a new version",
                )
            )
        return QueryCheck(
            valid=not errors,
            source=source,
            errors=errors,
            warnings=warnings,
            item_schema=schema,
            fields=schema_fields(schema) if schema else [],
        )

    async def validate_query(self, principal: Principal, write: QueryWrite) -> QueryCheck:
        require(self._authorizer, principal, Permission.TESTS_WRITE)
        await self.ready()
        return await self._check_query(write)

    async def dry_run(self, principal: Principal, request: DryRunRequest) -> DryRun:
        """Collect one sample through a real connection, without storing a snapshot."""
        require(self._authorizer, principal, Permission.TESTS_WRITE)
        await self.ready()
        write = QueryWrite(**request.model_dump(exclude={"connection_id", "max_items"}))
        check = await self._check_query(write)
        # A dry run of an existing version is fine: only "exists" stops a save, not a sample.
        blocking = [e for e in check.errors if e.pointer != "/version"]
        if blocking or check.item_schema is None:
            return DryRun(check=check, error="fix the definition first")
        connection = await self._connection(request.connection_id)
        if connection.integration_id != write.integration_id or connection.state == "disabled":
            return DryRun(
                check=check,
                error=f"{connection.name} is not an enabled {write.integration_id} connection",
            )
        package = self.package(write.integration_id)
        query = {
            "operation": write.operation,
            "params": write.params,
            "items": write.items,
            "fields": write.fields,
            **({"regions": write.regions} if write.regions else {}),
            **({"for_each": write.for_each.model_dump()} if write.for_each else {}),
            "max_items": request.max_items,
        }
        try:
            env = await self._credentials(connection, package)
            report = await self._host.collect(
                package, write.name, write.version, connection.config, env, query
            )
            _, schema_warnings = build_snapshot(
                check.source, utc(self._clock()), True, list(report.items), check.item_schema
            )
        except IntegrationError as exc:
            return DryRun(check=check, error=f"{exc.kind}: {exc.message}")
        items = list(report.items)
        warnings = [PreviewProblem(pointer="/fields", detail=w) for w in schema_warnings]
        for key in write.fields:
            if items and all(item.get(key) is None for item in items):
                warnings.append(
                    PreviewProblem(
                        pointer=f"/fields/{key}",
                        detail=f"{key} is empty in all {len(items)} items; check the path",
                    )
                )
        return DryRun(check=check, items=items, count=len(items), warnings=warnings)

    async def create_query(self, principal: Principal, write: QueryWrite) -> QueryDefinition:
        """Save a validated definition. Executable on a schedule, so tests:define-run."""
        require(self._authorizer, principal, Permission.TESTS_DEFINE_RUN)
        await self.ready()
        check = await self._check_query(write)
        if not check.valid or check.item_schema is None:
            conflict = any(e.pointer == "/version" for e in check.errors)
            errors = [FieldError(e.detail, e.pointer) for e in check.errors]
            if conflict and len(errors) == 1:
                raise Conflict(errors[0].detail, slug="query-exists")
            raise Invalid("the query source does not validate", errors=errors)
        query = QueryDefinition(
            id=ids.mint("query"),
            integration_id=write.integration_id,
            name=write.name,
            version=write.version,
            description=write.description,
            operation=write.operation,
            params=write.params,
            items=write.items,
            fields=write.fields,
            regions=write.regions,
            for_each=write.for_each,
            item_schema=check.item_schema,
            created=utc(self._clock()),
            created_by_ref=principal.actor_id,
        )
        await self._store.put_query(query)
        return query

    async def list_queries(self, principal: Principal) -> list[QueryDefinition]:
        require(self._authorizer, principal, Permission.PROGRAMS_READ)
        return await self._store.list_queries()

    async def get_query(self, principal: Principal, query_id: str) -> QueryDefinition:
        require(self._authorizer, principal, Permission.PROGRAMS_READ)
        for query in await self._store.list_queries():
            if query.id == query_id:
                return query
        raise NotFound(f"no query {query_id}")

    async def delete_query(self, principal: Principal, query_id: str) -> None:
        require(self._authorizer, principal, Permission.TESTS_DEFINE_RUN)
        query = await self.get_query(principal, query_id)
        graph = await self._objects.store.graph()
        readers = [
            t.id
            for t in graph.all(Test)
            if t.run is not None and query.source in t.run.sources_read()
        ]
        if readers:
            raise Conflict(
                f"{query.source} is read by {', '.join(readers)}; revoke those tests first",
                slug="query-in-use",
            )
        await self._store.delete_query(query_id)

    # --- rule preview -----------------------------------------------------------------------

    async def preview_rule(self, principal: Principal, request: RulePreviewRequest) -> RulePreview:
        """Evaluate a rule over the latest complete snapshots, exactly as the rule runner would,
        without collecting, without a freshness window, and without recording anything."""
        require(self._authorizer, principal, Permission.TESTS_WRITE)
        await self.ready()
        try:
            run = Run.model_validate({**request.run, "runner": "rule"})
        except Exception as exc:  # pydantic.ValidationError
            return RulePreview(
                outcome="invalid",
                summary="the run block is malformed",
                errors=[PreviewProblem(pointer="/run", detail=str(exc).splitlines()[0])],
            )
        errors = [PreviewProblem(pointer=p, detail=d) for p, d in rules.rule_errors(run)]
        if errors:
            return RulePreview(
                outcome="invalid", summary="the rule does not compile", errors=errors
            )

        source = rules.parse_reference(run.source or "")
        try:
            package, schema, _ = await self.resolve(source)
        except (Invalid, NotFound) as exc:
            # A draft query source has no saved definition yet: preview its dry-run items
            # against the schema its (unsaved) definition derives (RFC 0006 section 6).
            draft = request.query
            if request.items is None or draft is None:
                problem = PreviewProblem(pointer="/run/source", detail=exc.detail)
                return RulePreview(outcome="invalid", summary=exc.detail, errors=[problem])
            check = await self._check_query(draft)
            if check.source != str(source) or check.item_schema is None:
                detail = f"the draft defines {check.source}, not {source}"
                problem = PreviewProblem(pointer="/run/source", detail=detail)
                return RulePreview(outcome="invalid", summary=detail, errors=[problem])
            schema = check.item_schema
        warnings = [
            PreviewProblem(pointer=p, detail=d) for p, d in rules.unknown_fields(run, schema)
        ]

        graph = await self._objects.store.graph()
        params: dict[str, str] = {}
        impl = None
        if request.implementation_id:
            impl = graph.typed(request.implementation_id, Implementation)
            if impl is None:
                raise NotFound(f"no implementation {request.implementation_id}")
        control = graph.control(request.control_ref or (impl.control_ref if impl else None))
        if control is not None:
            params = {k: v for k, v in control_values(control, impl, {}).items() if v is not None}
        params.update(request.params or {})

        connections = [
            c
            for c in (
                self.bound(impl, graph, await self._store.list_connections())
                if impl
                else await self._store.list_connections()
            )
            if c.integration_id == source.integration and c.state != "disabled"
        ]
        far_past = datetime(1970, 1, 1, tzinfo=UTC)
        at = utc(self._clock())
        chosen: list[tuple[Connection, Snapshot, dict[str, Any]]] = []
        for connection in [] if request.items is not None else connections:
            snapshot = await self._store.latest_snapshot(connection.id, str(source), far_past, at)
            if snapshot is None:
                continue
            content = await self._blobs.get(snapshot.uri)
            if content is not None and digest(content) == snapshot.digest:
                chosen.append((connection, snapshot, json.loads(content)))
        if request.items is not None:  # a dry run's sample, not stored snapshots
            items = list(request.items)
            out = rules.evaluate(run, items, params, at)
            return RulePreview(
                outcome=out.outcome,
                summary=out.summary,
                selected=out.selected,
                total=len(items),
                subjects=[
                    {k: v for k, v in vars(s).items() if v is not None}
                    for s in out.subjects[: request.limit]
                ],
                warnings=warnings,
                params=params,
                sample=items[:3],
            )
        if not chosen:
            scope = "bound to that implementation" if impl else "for it"
            return RulePreview(
                outcome="no-data",
                summary=f"no complete snapshot of {source} from a connection {scope}; "
                "collect one first",
                warnings=warnings,
                params=params,
            )

        items = [item for _, _, document in chosen for item in document.get("items", [])]
        observed = min(snapshot.collected for _, snapshot, _ in chosen)
        out = rules.evaluate(run, items, params, observed)
        return RulePreview(
            outcome=out.outcome,
            summary=out.summary,
            selected=out.selected,
            total=len(items),
            subjects=[
                {k: v for k, v in vars(s).items() if v is not None}
                for s in out.subjects[: request.limit]
            ],
            warnings=warnings,
            snapshots=[
                PreviewSnapshot(
                    id=s.id,
                    connection_id=c.id,
                    connection_name=c.name,
                    collected=s.collected,
                    item_count=s.item_count,
                )
                for c, s, _ in chosen
            ],
            params=params,
            sample=items[:3],
        )

    # --- archive installs and upgrades (RFC 0005 sections 4 and 8) --------------------------

    def _catalog(self) -> PackageCatalog:
        if not isinstance(self._packages, PackageCatalog):
            raise Invalid("this deployment installs integrations from a directory only")
        return self._packages

    async def list_versions(self, principal: Principal, integration_id: str) -> list[InstallRecord]:
        require(self._authorizer, principal, Permission.PROGRAMS_READ)
        records = [r for r in await self._store.list_installs() if r.id == integration_id]
        if not records and self._packages.get(integration_id) is None:
            raise NotFound(f"no integration {integration_id} is installed")
        return records

    async def install(
        self,
        principal: Principal,
        request: InstallRequest | None = None,
        upload: bytes | None = None,
        expected: str | None = None,
        enable: bool = True,
    ) -> Job:
        """Install an archive from a URL or an upload, as a job."""
        require(self._authorizer, principal, Permission.INTEGRATIONS_MANAGE)
        catalog = self._catalog()
        if request is not None:
            expected, enable = request.digest, request.enable
        if upload is None and (request is None or self._fetcher is None):
            raise Invalid("send an archive URL or upload one")

        async def work(job: Job) -> JobOutcome:
            content = upload
            if content is None:
                assert request is not None and self._fetcher is not None
                try:
                    content = await self._fetcher.fetch(request.url)
                except ValueError as exc:
                    raise Invalid(str(exc), slug="fetch-failed") from exc
            sha = digest(content)
            if expected and sha != expected:
                raise Invalid(
                    f"the archive digest is {sha}, not {expected}", slug="digest-mismatch"
                )
            try:
                files = await asyncio.to_thread(read_archive, content)
                package = await asyncio.to_thread(load_files, files)
            except PackageError as exc:
                raise Invalid(str(exc), slug="bad-package") from exc
            manifest = package.manifest
            if not self._allow_local:
                raise Invalid(
                    "unsigned packages install only with OGRL_ALLOW_LOCAL_INTEGRATIONS=true; "
                    "signature verification arrives with the registry (RFC 0005 section 4)",
                    slug="untrusted-integration",
                )
            if catalog.is_static(manifest.id):
                raise Conflict(
                    f"{manifest.id} is loaded from OGRL_INTEGRATIONS_DIR", slug="static-integration"
                )
            existing = next(
                (
                    r
                    for r in await self._store.list_installs()
                    if (r.id, r.version) == (manifest.id, manifest.version)
                ),
                None,
            )
            if existing is not None and existing.digest != sha:
                raise Conflict(
                    f"{manifest.id} {manifest.version} is installed with other bytes; "
                    "a version is immutable, so publish a new one",
                    slug="version-immutable",
                )
            if existing is None:
                uri = await self._blobs.put(
                    f"integrations/{manifest.id}/{manifest.version}/{sha}.tar.gz",
                    content,
                    "application/gzip",
                )
                await self._store.put_install(
                    InstallRecord(
                        id=manifest.id,
                        version=manifest.version,
                        digest=sha,
                        uri=uri,
                        tier="local",
                        installed=utc(self._clock()),
                        installed_by=principal.actor_id,
                        source=request.url if request else "upload",
                    )
                )
            if enable:
                await self._enable(manifest)
            return JobOutcome(
                report={
                    "id": manifest.id,
                    "version": manifest.version,
                    "digest": sha,
                    "enabled": enable,
                }
            )

        return await self._jobs.submit(
            principal,
            "integration_install",
            {"url": request.url if request else "upload", "digest": expected, "enable": enable},
            work,
        )

    async def enable_version(
        self, principal: Principal, integration_id: str, version: str
    ) -> IntegrationView:
        """Enable an installed version: an upgrade, or a rollback."""
        require(self._authorizer, principal, Permission.INTEGRATIONS_MANAGE)
        catalog = self._catalog()
        record = next(
            (
                r
                for r in await self._store.list_installs()
                if (r.id, r.version) == (integration_id, version)
            ),
            None,
        )
        if record is None:
            raise NotFound(f"{integration_id} {version} is not installed")
        try:
            package = await catalog.load(record)
        except PackageError as exc:
            raise Invalid(str(exc), slug="bad-package") from exc
        await self._enable(package.manifest)
        return integration_view(self.package(integration_id))

    async def _enable(self, manifest: Manifest) -> None:
        taken = {
            q.name for q in await self._store.list_queries() if q.integration_id == manifest.id
        } & {r.name for r in manifest.resources}
        if taken:
            raise Conflict(
                f"{manifest.id} {manifest.version} adds built-in resources named like query "
                f"sources: {', '.join(sorted(taken))}",
                slug="upgrade-breaks-tests",
            )
        if not manifest.queryable and any(
            q.integration_id == manifest.id for q in await self._store.list_queries()
        ):
            raise Conflict(
                f"{manifest.id} {manifest.version} drops the API model that query sources use",
                slug="upgrade-breaks-tests",
            )
        broken = await self._dependents_missing(manifest)
        if broken:
            listing = "; ".join(f"{test} reads {ref}" for test, ref in broken)
            raise Conflict(
                f"{manifest.id} {manifest.version} drops what enabled tests read: {listing}",
                slug="upgrade-breaks-tests",
            )
        await self._store.enable_install(manifest.id, manifest.version)
        await self.ready()

    async def _dependents_missing(self, manifest: Manifest) -> list[tuple[str, str]]:
        """Tests that read a source or check this version no longer provides (RFC 0005 s4)."""
        graph = await self._objects.store.graph()
        broken = []
        for test in graph.all(Test):
            if test.run is None:
                continue
            refs = [*test.run.sources_read(), *([test.run.check] if test.run.check else [])]
            for text in refs:
                try:
                    ref = rules.parse_reference(text)
                except ValueError:
                    continue
                if ref.integration != manifest.id:
                    continue
                is_check = text == test.run.check
                found = (
                    manifest.check(ref.name, ref.major)
                    if is_check
                    else manifest.resource(ref.name, ref.major)
                )
                if found is None:
                    broken.append((test.id, text))
        return broken

    @staticmethod
    def _proposed(template_test: Mapping[str, Any], fulfills_ref: str | None) -> dict[str, Any]:
        proposed = {**template_test, "fulfills_ref": fulfills_ref}
        if isinstance(proposed.get("run"), dict):
            proposed["run"] = Run.model_validate(proposed["run"]).model_dump(
                by_alias=True, exclude_none=True
            )
        return proposed

    async def template_updates(
        self, principal: Principal, integration_id: str
    ) -> list[TemplateUpdate]:
        require(self._authorizer, principal, Permission.PROGRAMS_READ)
        await self.ready()
        package = self.package(integration_id)
        graph = await self._objects.store.graph()
        out = []
        for test in graph.all(Test):
            origin = (test.extensions or {}).get("dev.ogrl.integration") or {}
            if test.is_revoked or origin.get("integration") != integration_id:
                continue
            template = package.manifest.template(str(origin.get("template")))
            if template is None or origin.get("version") == package.manifest.version:
                continue
            body = test.body()
            proposed = self._proposed(template.test, template.fulfills_ref)
            changes = sorted(k for k, v in proposed.items() if body.get(k) != v)
            out.append(
                TemplateUpdate(
                    test_id=test.id,
                    test_name=test.name,
                    template=template.name,
                    from_version=origin.get("version"),
                    to_version=package.manifest.version,
                    changes=changes,
                    modified=test.modified,
                )
            )
        return out

    async def apply_template_update(
        self, principal: Principal, integration_id: str, test_id: str, if_match: datetime
    ) -> Any:
        """Accept a template update: the test takes the new template's fields and version."""
        updates = {u.test_id: u for u in await self.template_updates(principal, integration_id)}
        update = updates.get(test_id)
        if update is None:
            raise NotFound(f"{test_id} has no pending update from {integration_id}")
        package = self.package(integration_id)
        template = package.manifest.template(update.template)
        assert template is not None
        row = await self._objects.store.get(test_id)
        assert row is not None
        extensions = dict(row.obj.extensions or {})
        extensions["dev.ogrl.integration"] = {
            **extensions.get("dev.ogrl.integration", {}),
            "version": package.manifest.version,
        }
        patch = {
            **self._proposed(template.test, template.fulfills_ref),
            "extensions": extensions,
        }
        return await self._objects.update(principal, SPECS["test"], test_id, patch, if_match)


def _problem(problem: Any) -> "PreviewProblem":
    return PreviewProblem(pointer=problem.pointer, detail=problem.detail)


def _definition(query: QueryDefinition) -> dict[str, Any]:
    return {
        "source": query.source,
        "operation": query.operation,
        "params": dict(query.params),
        "items": query.items,
        "fields": dict(query.fields),
        **({"regions": query.regions} if query.regions else {}),
        **({"for_each": query.for_each.model_dump()} if query.for_each else {}),
    }


def rules_match(pattern: str, value: str) -> bool:
    return re.fullmatch(pattern, value) is not None
