"""The repository protocols operations depend on.

Declared here, by the consumer. `opengrc.persistence.memory` implements them
for tests and local runs; a Postgres implementation is the same protocol
over SQLModel rows (RFC 0003 section 7).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from opengrc.kernel.graph import Graph
from opengrc.kernel.models import Envelope
from opengrc.operations.records import ORGANIZATION, Job, LibraryPin, ProviderPin


@dataclass(frozen=True, slots=True)
class Row:
    """One stored object and where it came from: `library`, `provider:<bundle id>`,
    or `organization`. Only organization rows are editable through the API."""

    obj: Envelope
    source: str = ORGANIZATION

    @property
    def editable(self) -> bool:
        return self.source == ORGANIZATION


@dataclass(frozen=True)
class ProjectionChange:
    replaced: list[str]
    added: list[str]
    revoked: list[str]


class ObjectStore(Protocol):
    async def get(self, object_id: str) -> Row | None: ...

    async def scan(self, object_type: str) -> list[Row]:
        """Every row of one type, including revoked ones, ordered by id."""
        ...

    async def insert(self, row: Row, writer: str) -> None:
        """Raises Conflict when the id was ever used."""
        ...

    async def replace(self, obj: Envelope, expected_modified: datetime, writer: str) -> None:
        """Compare-and-set on `modified`. Raises PreconditionFailed when stale."""
        ...

    async def graph(self, at: datetime | None = None) -> Graph:
        """The current objects, or the revisions in force at `at` (RFC 0002 section 4)."""
        ...

    async def history_start(self) -> datetime | None:
        """After a restore, history before this instant is unknown."""
        ...

    async def has_organization_objects(self) -> bool: ...

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
        """Atomically replace one projection and its pin (RFC 0002 sections 5 and 7).

        Ids absent from `objects` are kept with `revoked: true` and `modified`
        set to `revoked_at`.
        """
        ...

    async def restore(
        self,
        organization: Sequence[Envelope],
        writer: str,
        at: datetime,
    ) -> None:
        """Store organization objects as they are, into a store that holds none."""
        ...

    async def library_pin(self) -> LibraryPin | None: ...

    async def provider_pins(self) -> list[ProviderPin]: ...

    async def save_job(self, job: Job) -> None: ...

    async def get_job(self, job_id: str) -> Job | None: ...

    async def list_jobs(self) -> list[Job]: ...

    async def get_meta(self, key: str) -> str | None: ...

    async def set_meta(self, key: str, value: str | None) -> None: ...


class BlobStore(Protocol):
    """Object storage for evidence bytes, document bodies, and render files."""

    async def put(self, key: str, content: bytes, media_type: str) -> str:
        """Store bytes and return the URI recorded in `resource.uri`."""
        ...

    async def get(self, uri: str) -> bytes | None: ...
