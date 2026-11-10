"""The four ports from RFC 0003 section 5.

The kernel calls these; it does not implement them. Status, parameter
resolution, and mapping semantics are deliberately not ports: a plugin that
changed them would make two installations disagree about one bundle.
"""

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from opengrc.kernel.models import Envelope


@dataclass(frozen=True, slots=True)
class RenderedFile:
    name: str
    media_type: str
    content: bytes


@dataclass(frozen=True, slots=True)
class SecretHandle:
    """Names the `run.env` variables. Values come from the harness, never the test."""

    names: Sequence[str]


class Importer(Protocol):
    name: str

    def accepts(self, media_type: str) -> bool: ...

    def import_bytes(self, content: bytes) -> Sequence[Envelope]: ...


class Renderer(Protocol):
    name: str  # the view: "git", "oscal"

    def render(self, graph: Sequence[Envelope]) -> Sequence[RenderedFile]: ...


class Runner(Protocol):
    name: str  # matches the test's run block: "shell", or an org-defined runner

    async def run(
        self, test: Envelope, implementation: Envelope, secrets: SecretHandle
    ) -> Sequence[Envelope]:
        """Returns a `result` and its `evidence`. Failure is a result with outcome: error."""
        ...


class Connector(Protocol):
    name: str

    def collect(self, job: Mapping[str, object]) -> AsyncIterator[Envelope]:
        """Yields `evidence`. Shipped as a subprocess speaking RFC 0001 JSON."""
        ...
