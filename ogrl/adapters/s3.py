"""S3 object storage for evidence bytes, document bodies, and render files.

In production this is the private bucket the CloudFormation stack creates,
reached with the task role. Locally `endpoint_url` points at the compose
stack's S3-compatible server. URIs are `s3://<bucket>/<key>`.
"""

import asyncio
from functools import cached_property
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


class S3Blobs:
    def __init__(
        self,
        bucket: str,
        *,
        prefix: str = "",
        endpoint_url: str | None = None,
        region: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._endpoint_url = endpoint_url
        self._region = region

    @cached_property
    def _client(self):  # noqa: ANN202 - boto3 clients are untyped
        return boto3.client(
            "s3",
            endpoint_url=self._endpoint_url,
            region_name=self._region,
            config=Config(
                retries={"max_attempts": 5, "mode": "standard"},
                # Path-style addressing works with S3 and every local stand-in.
                s3={"addressing_style": "path"} if self._endpoint_url else {},
            ),
        )

    def _key(self, key: str) -> str:
        return f"{self._prefix}/{key}" if self._prefix else key

    async def put(self, key: str, content: bytes, media_type: str) -> str:
        full = self._key(key)
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=full,
            Body=content,
            ContentType=media_type or "application/octet-stream",
            # Encryption at rest is the bucket's default (BucketEncryption in
            # deploy/aws/template.yaml), so no per-object header is sent.
        )
        return f"s3://{self._bucket}/{full}"

    async def get(self, uri: str) -> bytes | None:
        parsed = urlparse(uri)
        if parsed.scheme != "s3" or parsed.netloc != self._bucket:
            return None

        def read() -> bytes | None:
            try:
                response = self._client.get_object(Bucket=self._bucket, Key=parsed.path.lstrip("/"))
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                    return None
                raise
            return response["Body"].read()

        return await asyncio.to_thread(read)
