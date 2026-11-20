"""Library revisions (RFC 0002 section 3): the files under `library/` at one commit."""

import asyncio
import shutil
import tempfile
from pathlib import Path

from ogrl.kernel.bundles import BundleError, load_text, read_manifest
from ogrl.operations.sources import LibraryRevision


def _version_of(root: Path) -> str:
    try:
        manifest = read_manifest(load_text((root / "bundle.yaml").read_bytes()))
    except (OSError, BundleError) as exc:
        raise ValueError(f"no readable library manifest in {root}: {exc}") from exc
    return str(manifest.get("version", ""))


class DirectoryLibrary:
    """A library directory on disk, such as this repository's `library/`.

    It holds one revision. A pull that names a different version or any
    commit is refused rather than served the wrong content.
    """

    def __init__(self, root: Path, commit: str | None = None) -> None:
        self._root = root
        self._commit = commit

    async def checkout(self, version: str | None, commit: str | None) -> LibraryRevision:
        held = _version_of(self._root)
        if version and version != held:
            raise ValueError(f"this deployment holds library {held}, not {version}")
        if commit and commit != self._commit:
            raise ValueError(f"this deployment's library directory is not at commit {commit}")
        return LibraryRevision(self._root, held, self._commit)


class GitLibrary:
    """A git repository of this project. `version` resolves through a tag.

    The tag is `library-v{version}` or `v{version}`. `commit` is any revision
    git can name. The checkout is a temporary worktree of the `library/` tree.
    """

    def __init__(self, repository: str, subdir: str = "library") -> None:
        self._repository = repository
        self._subdir = subdir
        self._checkouts: list[Path] = []

    async def _git(self, *args: str, cwd: Path | None = None) -> str:
        process = await asyncio.create_subprocess_exec(
            "git", *args, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        out, err = await process.communicate()
        if process.returncode != 0:
            raise ValueError(err.decode(errors="replace").strip() or f"git {args[0]} failed")
        return out.decode().strip()

    async def checkout(self, version: str | None, commit: str | None) -> LibraryRevision:
        target = Path(tempfile.mkdtemp(prefix="ogrl-library-"))
        self._checkouts.append(target)
        await self._git("clone", "--quiet", "--no-checkout", self._repository, str(target))
        revision = commit
        if revision is None and version:
            for tag in (f"library-v{version}", f"v{version}"):
                try:
                    revision = await self._git("rev-parse", f"{tag}^{{commit}}", cwd=target)
                    break
                except ValueError:
                    continue
            if revision is None:
                raise ValueError(f"no tag names library version {version}")
        revision = await self._git("rev-parse", revision or "HEAD", cwd=target)
        await self._git("checkout", "--quiet", revision, "--", self._subdir, cwd=target)
        root = target / self._subdir
        held = _version_of(root)
        if version and held != version:
            raise ValueError(f"commit {revision} holds library {held}, not {version}")
        return LibraryRevision(root, held, revision)

    def cleanup(self) -> None:
        for path in self._checkouts:
            shutil.rmtree(path, ignore_errors=True)
        self._checkouts.clear()
