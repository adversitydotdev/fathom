import asyncio
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

MAX_BYTES = 64 * 1024 * 1024


class UrlFetcher:
    """Reads `https://`, `http://`, `file://`, and bare paths.

    `allow_files=False` refuses local paths, for a deployment where callers of
    the import routes should not read the task's filesystem.
    """

    def __init__(self, *, allow_files: bool = True, timeout: float = 30.0) -> None:
        self._allow_files = allow_files
        self._timeout = timeout

    async def fetch(self, url: str) -> bytes:
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https"):
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
                response = await client.get(url)
            if response.status_code != 200:
                raise ValueError(f"{url} answered {response.status_code}")
            if len(response.content) > MAX_BYTES:
                raise ValueError(f"{url} is larger than {MAX_BYTES} bytes")
            return response.content
        if parsed.scheme in ("file", ""):
            if not self._allow_files:
                raise ValueError("local files are not readable by this deployment")
            path = Path(unquote(parsed.path) if parsed.scheme == "file" else url)

            def read() -> bytes:
                if not path.is_file():
                    raise ValueError(f"{path} is not a file")
                return path.read_bytes()

            return await asyncio.to_thread(read)
        raise ValueError(f"{parsed.scheme}:// URLs are not supported")
