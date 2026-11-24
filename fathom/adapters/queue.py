"""Optional SQS wakeup queue for multi-process job workers (RFC 0003 section 2).

The PostgreSQL `jobs` row remains authoritative; SQS messages carry only the
`job_id` as a wakeup hint so workers don't need tight DB polling loops.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class QueueMessage:
    job_id: str
    receipt_handle: str


class JobQueue(Protocol):
    async def enqueue(self, job_id: str) -> None: ...

    async def receive(
        self, *, wait_seconds: int = 20, max_messages: int = 5
    ) -> list[QueueMessage]: ...

    async def delete(self, receipt_handle: str) -> None: ...


class MemoryJobQueue:
    """In-memory JobQueue for unit tests and local multi-worker simulation."""

    def __init__(self) -> None:
        self._items: deque[tuple[str, str]] = deque()
        self._seq = 0

    async def enqueue(self, job_id: str) -> None:
        self._seq += 1
        self._items.append((job_id, f"mem-{self._seq}"))

    async def receive(self, *, wait_seconds: int = 20, max_messages: int = 5) -> list[QueueMessage]:
        del wait_seconds
        out: list[QueueMessage] = []
        while self._items and len(out) < max_messages:
            job_id, receipt = self._items.popleft()
            out.append(QueueMessage(job_id=job_id, receipt_handle=receipt))
        return out

    async def delete(self, receipt_handle: str) -> None:
        del receipt_handle


class SqsJobQueue:
    """AWS SQS implementation using boto3 offloaded to a worker thread."""

    def __init__(
        self,
        queue_url: str,
        *,
        region: str | None = None,
        endpoint_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._queue_url = queue_url
        self._region = region
        self._endpoint_url = endpoint_url
        self._client = client

    def _sqs(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client(
                "sqs", region_name=self._region, endpoint_url=self._endpoint_url
            )
        return self._client

    async def enqueue(self, job_id: str) -> None:
        await asyncio.to_thread(
            self._sqs().send_message,
            QueueUrl=self._queue_url,
            MessageBody=job_id,
        )

    async def receive(self, *, wait_seconds: int = 20, max_messages: int = 5) -> list[QueueMessage]:
        resp = await asyncio.to_thread(
            self._sqs().receive_message,
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=wait_seconds,
        )
        return [
            QueueMessage(job_id=m["Body"].strip(), receipt_handle=m["ReceiptHandle"])
            for m in resp.get("Messages", [])
            if m.get("Body") and m.get("ReceiptHandle")
        ]

    async def delete(self, receipt_handle: str) -> None:
        await asyncio.to_thread(
            self._sqs().delete_message,
            QueueUrl=self._queue_url,
            ReceiptHandle=receipt_handle,
        )
