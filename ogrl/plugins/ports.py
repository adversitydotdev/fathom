"""The four ports from RFC 0003 section 5.

The kernel calls these; it does not implement them. Status, parameter
resolution, and mapping semantics are deliberately not ports: a plugin that
changed them would make two installations disagree about one bundle.
"""

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal, Protocol

from ogrl.kernel.graph import Graph
from ogrl.kernel.models import Envelope, Implementation, Program, Test


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
class RunReport:
    """The harness turns this into one `result` and one `evidence` per file."""

    outcome: Literal["pass", "fail", "error"]
    summary: str
    observed: datetime
    files: Sequence[CollectedFile] = ()


class Runner(Protocol):
    name: str  # matches the test's run block: "shell", or an org-defined runner

    async def run(self, request: RunRequest) -> RunReport:
        """A failure is a report with outcome error, never an exception."""
        ...


@dataclass(frozen=True)
class CollectionRequest:
    system_id: str | None
    component_id: str | None
    implementation: Implementation | None


class Connector(Protocol):
    name: str
    description: str

    def collect(self, request: CollectionRequest) -> AsyncIterator[CollectedFile]:
        """Yields files that become `evidence`. Shipped as a subprocess speaking RFC 0001 JSON."""
        ...
