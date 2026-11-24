import asyncio
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

MAX_BYTES = 64 * 1024 * 1024


class UrlFetcher:
    """Reads `https://`, `http://`, `file://`, and bare paths.

    `allow_files=False` refuses local paths, for a deployment where callers of
    the import routes should not read the task's filesystem.

    `s3://bucket/key` reads only the URIs in `s3_uris` (the seed bundle the
    operator configured), so an administrator posting an import URL cannot read
    other objects the task role can reach, such as evidence.
    """

    def __init__(
        self,
        *,
        allow_files: bool = True,
        timeout: float = 30.0,
        s3_uris: frozenset[str] = frozenset(),
        s3_client: Any | None = None,
    ) -> None:
        self._allow_files = allow_files
        self._timeout = timeout
        self._s3_uris = s3_uris
        self._s3_client = s3_client

    def _s3(self) -> Any:
        if self._s3_client is not None:
            return self._s3_client  # injected, for tests
        import boto3

        return boto3.client("s3")

    def _read_s3(self, url: str) -> bytes:
        parsed = urlparse(url)
        key = parsed.path.lstrip("/")
        if not parsed.netloc or not key:
            raise ValueError(f"{url} is not s3://bucket/key")
        try:
            response = self._s3().get_object(Bucket=parsed.netloc, Key=key)
            if response.get("ContentLength", 0) > MAX_BYTES:
                raise ValueError(f"{url} is larger than {MAX_BYTES} bytes")
            return response["Body"].read()
        except ValueError:
            raise
        except Exception as exc:  # botocore ClientError and friends
            raise ValueError(f"could not read {url}: {exc}") from exc

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
        if parsed.scheme == "s3" and url in self._s3_uris:
            return await asyncio.to_thread(self._read_s3, url)
        raise ValueError(f"{parsed.scheme}:// URLs are not supported")
