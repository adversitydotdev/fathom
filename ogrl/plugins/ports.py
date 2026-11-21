"""The ports from RFC 0003 section 5, and the integration host from RFC 0005.

The kernel calls these; it does not implement them. Status, parameter
resolution, and mapping semantics are deliberately not ports: a plugin that
changed them would make two installations disagree about one bundle.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Literal, Protocol

from ogrl.kernel.graph import Graph
from ogrl.kernel.models import Envelope, Implementation, Program, Test

if TYPE_CHECKING:
    from ogrl.integrations.manifest import Package


@dataclass(frozen=True, slots=True)
class RenderedFile:
    name: str
    media_type: str
    content: bytes


@dataclass(frozen=True, slots=True)
class SecretHandle:
    """Names the `run.env` variables. Values come from the harness, never the test."""

    names: Sequence[str]


class Secrets(Protocol):
    """The harness's secret store. A missing value ends the run as `error`."""

    def get(self, name: str) -> str | None: ...


@dataclass(frozen=True)
class ImportedBundle:
    """What an importer read: the manifest fields a pin needs, and the objects."""

    id: str
    name: str | None
    version: str
    objects: Sequence[Envelope]
    library_version: str | None = None
    warnings: list[str] = field(default_factory=list)


class Importer(Protocol):
    name: str  # "ogrl", "oscal-component"

    def import_bytes(self, content: bytes, graph: Graph) -> ImportedBundle:
        """`graph` is the pinned library, for resolving catalog ids. Raises ValueError."""
        ...


@dataclass(frozen=True)
class RenderRequest:
    graph: Graph
    program: Program
    at: datetime
    framework_id: str | None = None


class Renderer(Protocol):
    name: str  # the view: "ssp", "oscal"

    def render(self, request: RenderRequest) -> Sequence[RenderedFile]: ...


@dataclass(frozen=True)
class CollectedFile:
    name: str
    media_type: str
    content: bytes


@dataclass(frozen=True)
class RunRequest:
    test: Test
    implementation: Implementation
    evaluation_date: date
    parameters: Mapping[str, str]
    secrets: SecretHandle


@dataclass(frozen=True)
class StoredArtifact:
    """Bytes already in object storage, such as a snapshot, cited without a second upload."""

    name: str
    media_type: str
    uri: str
    digest: str
    collected: datetime


@dataclass(frozen=True)
class RunReport:
    """The harness turns this into one `result` and one `evidence` per file or artifact."""

    outcome: Literal["pass", "fail", "error"]
    summary: str
    observed: datetime
    files: Sequence[CollectedFile] = ()
    artifacts: Sequence[StoredArtifact] = ()
    subjects: Sequence[Mapping[str, str]] = ()


class Runner(Protocol):
    name: str  # matches the test's run block: "shell", or an org-defined runner

    async def run(self, request: RunRequest) -> RunReport:
        """A failure is a report with outcome error, never an exception."""
        ...


# --- Integrations (RFC 0005) --------------------------------------------------------------------


class IntegrationError(Exception):
    """A failed integration operation. `kind` is one of RFC 0005 section 7's error kinds,
    or `protocol` when the process misbehaved (crash, timeout, malformed output)."""

    def __init__(self, kind: str, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.retry_after = retry_after


@dataclass(frozen=True)
class ValidateReport:
    identity: str
    granted_scopes: Sequence[str] = ()
    warnings: Sequence[str] = ()


@dataclass(frozen=True)
class CollectReport:
    items: Sequence[Mapping[str, Any]]
    complete: bool
    reason: str | None = None


@dataclass(frozen=True)
class CheckReport:
    outcome: Literal["pass", "fail", "error"]
    summary: str
    subjects: Sequence[Mapping[str, str]] = ()


class IntegrationHost(Protocol):
    """Runs one operation of an installed package. Failures raise IntegrationError."""

    async def validate(
        self, package: "Package", config: Mapping[str, str], env: Mapping[str, str]
    ) -> ValidateReport: ...

    async def collect(
        self,
        package: "Package",
        resource: str,
        version: int,
        config: Mapping[str, str],
        env: Mapping[str, str],
    ) -> CollectReport: ...

    async def check(
        self,
        package: "Package",
        check: str,
        version: int,
        args: Mapping[str, str],
        params: Mapping[str, str],
        snapshots: Mapping[str, bytes],
        time_limit: int,
    ) -> CheckReport: ...


class SecretVault(Protocol):
    """Writable secrets for integration connections (RFC 0005 section 5).

    Names look like `integrations/<connection id>/<NAME>`. Values never reach
    the database, an API response, or a log line.
    """

    def get(self, name: str) -> str | None: ...

    def put(self, name: str, value: str) -> None: ...

    def delete(self, name: str) -> None: ...


class OAuthClient(Protocol):
    """Talks to a vendor's OAuth token endpoint (RFC 0005 section 5)."""

    async def token(self, token_url: str, form: Mapping[str, str]) -> Mapping[str, Any]:
        """POST a form to the token endpoint. Raises IntegrationError("auth_failed", ...)."""
        ...


class RoleAssumer(Protocol):
    """Assumes an organization's read-only IAM role for one operation (RFC 0005 section 5)."""

    async def assume(self, role_arn: str, external_id: str, session_name: str) -> Mapping[str, str]:
        """Returns AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_SESSION_TOKEN."""
        ...
