"""Where jobs read from and write to, declared by the operations that use them.

`opengrc.adapters` implements these against the filesystem, HTTP, and git.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class Fetcher(Protocol):
    async def fetch(self, url: str) -> bytes:
        """`https://`, `http://`, `file://`, or a local path. Raises ValueError."""
        ...


@dataclass(frozen=True)
class LibraryRevision:
    root: Path  # the directory holding bundle.yaml and the object tree
    version: str
    commit: str | None


class LibrarySource(Protocol):
    async def checkout(self, version: str | None, commit: str | None) -> LibraryRevision:
        """Materialize one revision of the library. Raises ValueError when unknown."""
        ...


class Git(Protocol):
    """The few git operations export and restore need. Raises ValueError on failure."""

    async def clone(self, remote: str, into: Path, commit: str | None = None) -> str:
        """Clone, check out `commit` or the default head, and return the head commit."""
        ...

    async def head(self, repo: Path) -> str | None: ...

    async def ancestors(self, repo: Path) -> list[str]: ...

    async def commit_all(self, repo: Path, message: str) -> str | None:
        """Stage every change and commit. None when the tree did not change."""
        ...

    async def push(self, repo: Path) -> None: ...
