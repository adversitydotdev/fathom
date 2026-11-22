"""Connections and snapshots: records the application keeps beside the objects (RFC 0005).

Neither is an RFC 0001 object. A connection is deployment configuration (an
installed integration, its non-secret config, which auth kind it uses, and the
components and systems it is bound to). A snapshot row describes one stored
snapshot document; the bytes live in object storage.
"""

from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

ConnectionState = Literal["pending", "active", "failing", "disabled"]
Tier = Literal["first-party", "verified", "local"]


class InstallRecord(BaseModel):
    """One installed archive version of an integration (RFC 0005 section 4)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    version: str
    digest: str  # sha-256 of the archive bytes
    uri: str  # where the archive lives in object storage
    tier: Tier
    enabled: bool = False
    installed: datetime
    installed_by: str | None = None
    source: str | None = None  # the URL, or "upload"


class Connection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    integration_id: str
    name: str
    config: dict[str, str] = Field(default_factory=dict)
    auth_kind: str
    bindings: list[str] = Field(default_factory=list)
    state: ConnectionState = "pending"
    identity: str | None = None
    granted_scopes: list[str] | None = None
    last_validated: datetime | None = None
    last_error: str | None = None
    secrets_set: list[str] = Field(default_factory=list)  # names only, never values
    external_id: str | None = None  # aws_role: the ExternalId the role's trust policy requires
    created: datetime
    modified: datetime
    created_by_ref: str | None = None


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    connection_id: str
    source: str
    collected: datetime
    complete: bool
    reason: str | None = None
    item_count: int
    size: int
    uri: str
    digest: str
    job_id: str | None = None
    warnings: list[str] | None = None


class QueryDefinition(BaseModel):
    """An organization-defined resource over the vendor's API model (RFC 0006, RFC 0007)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    integration_id: str
    name: str
    version: int
    description: str | None = None
    operation: str
    params: dict[str, str] = Field(default_factory=dict)
    items: str = ""
    fields: dict[str, str]
    regions: list[str] | Literal["*"] | None = None  # Smithy: region codes, or the connection's
    item_schema: dict[str, Any]  # derived from the API model when saved
    created: datetime
    created_by_ref: str | None = None

    @property
    def source(self) -> str:
        return f"{self.integration_id}/{self.name}@{self.version}"

    def query(self) -> dict[str, Any]:
        """What collect sends to the integration (RFC 0006 section 4)."""
        return {
            "operation": self.operation,
            "params": dict(self.params),
            "items": self.items,
            "fields": dict(self.fields),
            **({"regions": self.regions} if self.regions else {}),
        }


class ConnectionStore(Protocol):
    async def get_connection(self, connection_id: str) -> Connection | None: ...

    async def list_connections(self) -> list[Connection]:
        """Ordered by id, which is also the binding order RFC 0001 7.6 concatenates by."""
        ...

    async def insert_connection(self, connection: Connection) -> None: ...

    async def replace_connection(self, connection: Connection, expected_modified: datetime) -> None:
        """Compare-and-set on `modified`. Raises PreconditionFailed when stale."""
        ...

    async def delete_connection(self, connection_id: str) -> None: ...

    async def insert_snapshot(self, snapshot: Snapshot) -> None: ...

    async def get_snapshot(self, snapshot_id: str) -> Snapshot | None: ...

    async def list_snapshots(
        self, connection_id: str | None = None, source: str | None = None
    ) -> list[Snapshot]:
        """Newest first."""
        ...

    async def list_installs(self) -> list[InstallRecord]:
        """Every installed version, ordered by id then installed time."""
        ...

    async def put_install(self, record: InstallRecord) -> None:
        """Insert a version. Raises Conflict when that id and version already exist."""
        ...

    async def enable_install(self, integration_id: str, version: str) -> None:
        """Enable one version and disable the others of that integration, atomically."""
        ...

    async def list_queries(self) -> list[QueryDefinition]:
        """Ordered by integration, name, then version."""
        ...

    async def put_query(self, query: QueryDefinition) -> None:
        """Raises Conflict when that integration, name, and version exist."""
        ...

    async def delete_query(self, query_id: str) -> None: ...

    async def latest_snapshot(
        self, connection_id: str, source: str, not_before: datetime, not_after: datetime
    ) -> Snapshot | None:
        """The latest complete snapshot with `not_before <= collected <= not_after`."""
        ...


def connection_body(connection: Connection) -> dict[str, Any]:
    return connection.model_dump(mode="json", exclude_none=True)
