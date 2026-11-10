"""Filesystem object storage. URIs are `file://` paths under one root."""

import asyncio
from pathlib import Path
from urllib.parse import unquote, urlparse


class FileBlobs:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if self._root not in path.parents:
            raise ValueError(f"{key} escapes the storage root")
        return path

    async def put(self, key: str, content: bytes, media_type: str) -> str:
        path = self._path(key)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

        await asyncio.to_thread(write)
        return path.as_uri()

    async def get(self, uri: str) -> bytes | None:
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            return None
        path = Path(unquote(parsed.path))

        def read() -> bytes | None:
            resolved = path.resolve()
            if self._root not in resolved.parents or not resolved.is_file():
                return None
            return resolved.read_bytes()

        return await asyncio.to_thread(read)
