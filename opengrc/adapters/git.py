"""The git CLI, run as a subprocess. Export and restore are its only callers."""

import asyncio
import os
from pathlib import Path

AUTHOR = {
    "GIT_AUTHOR_NAME": "OpenGRC export",
    "GIT_AUTHOR_EMAIL": "export@opengrc.invalid",
    "GIT_COMMITTER_NAME": "OpenGRC export",
    "GIT_COMMITTER_EMAIL": "export@opengrc.invalid",
}


class GitCli:
    def __init__(self, binary: str = "git") -> None:
        self._binary = binary

    async def _run(self, *args: str, cwd: Path | None = None) -> str:
        env = {**os.environ, **AUTHOR, "GIT_TERMINAL_PROMPT": "0"}
        process = await asyncio.create_subprocess_exec(
            self._binary,
            *args,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await process.communicate()
        if process.returncode != 0:
            raise ValueError(f"git {args[0]} failed: {err.decode(errors='replace').strip()}")
        return out.decode().strip()

    async def clone(self, remote: str, into: Path, commit: str | None = None) -> str:
        await self._run("clone", "--quiet", remote, str(into))
        if commit:
            await self._run("checkout", "--quiet", commit, cwd=into)
        return await self.head(into) or ""

    async def head(self, repo: Path) -> str | None:
        try:
            return await self._run("rev-parse", "HEAD", cwd=repo)
        except ValueError:  # an empty repository has no HEAD
            return None

    async def ancestors(self, repo: Path) -> list[str]:
        if await self.head(repo) is None:
            return []
        return (await self._run("rev-list", "HEAD", cwd=repo)).split()

    async def commit_all(self, repo: Path, message: str) -> str | None:
        await self._run("add", "--all", cwd=repo)
        status = await self._run("status", "--porcelain", cwd=repo)
        if not status:
            return None
        await self._run("commit", "--quiet", "-m", message, cwd=repo)
        return await self.head(repo)

    async def push(self, repo: Path) -> None:
        branch = await self._run("rev-parse", "--abbrev-ref", "HEAD", cwd=repo)
        await self._run("push", "--quiet", "origin", f"HEAD:refs/heads/{branch}", cwd=repo)
