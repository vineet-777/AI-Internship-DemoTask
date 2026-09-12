"""Durable Redis Streams queue and an in-memory test implementation."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class JobType(StrEnum):
    DISCOVER_SOURCE = "DISCOVER_SOURCE"
    FETCH_URL = "FETCH_URL"
    PARSE_DOCUMENT = "PARSE_DOCUMENT"
    EXTRACT_ENTITY = "EXTRACT_ENTITY"
    RESOLVE_ENTITY = "RESOLVE_ENTITY"
    FETCH_GITHUB = "FETCH_GITHUB"
    EXPORT_RECORD = "EXPORT_RECORD"


@dataclass(frozen=True, slots=True)
class Job:
    job_type: JobType
    payload: dict[str, Any]
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    attempts: int = 0

    def encode(self) -> str:
        return json.dumps(
            {
                "job_id": self.job_id,
                "job_type": self.job_type.value,
                "payload": self.payload,
                "attempts": self.attempts,
            },
            sort_keys=True,
        )

    @classmethod
    def decode(cls, value: str) -> "Job":
        data = json.loads(value)
        return cls(
            job_id=str(data["job_id"]),
            job_type=JobType(data["job_type"]),
            payload=dict(data["payload"]),
            attempts=int(data.get("attempts", 0)),
        )


@dataclass(frozen=True, slots=True)
class QueueMessage:
    receipt: str
    job: Job


class JobQueue(Protocol):
    async def enqueue(self, job: Job) -> str:
        ...

    async def receive(self, *, timeout_seconds: float | None = None) -> QueueMessage | None:
        ...

    async def ack(self, message: QueueMessage) -> None:
        ...

    async def retry(self, message: QueueMessage, *, delay_seconds: float = 0) -> str:
        ...

    async def dead_letter(self, message: QueueMessage, *, reason: str) -> str:
        ...


class RedisStreamQueue:
    """Redis Streams queue using consumer groups and explicit ACKs."""

    def __init__(
        self,
        redis_url: str,
        *,
        stream: str = "ingestion:jobs",
        group: str = "ingestion-workers",
        consumer: str | None = None,
        dead_letter_stream: str | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._stream = stream
        self._group = group
        self._consumer = consumer or f"worker-{uuid.uuid4().hex}"
        self._dead_letter_stream = dead_letter_stream or f"{stream}:dead-letter"
        self._redis: Any | None = None
        self._group_ready = False

    async def connect(self) -> None:
        if self._redis is not None:
            return
        try:
            import redis.asyncio as redis
        except ImportError as exc:  # pragma: no cover - dependency/environment path
            raise RuntimeError("Install the redis package to use RedisStreamQueue") from exc
        self._redis = redis.from_url(self._redis_url, decode_responses=True)
        await self._ensure_group()

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
            self._group_ready = False

    async def __aenter__(self) -> "RedisStreamQueue":
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def enqueue(self, job: Job) -> str:
        await self.connect()
        return await self._redis.xadd(self._stream, {"job": job.encode()})

    async def receive(self, *, timeout_seconds: float | None = None) -> QueueMessage | None:
        await self.connect()
        block_ms = None if timeout_seconds is None else max(0, int(timeout_seconds * 1000))
        response = await self._redis.xreadgroup(
            self._group,
            self._consumer,
            {self._stream: ">"},
            count=1,
            block=block_ms,
        )
        if not response:
            return None
        _, entries = response[0]
        receipt, values = entries[0]
        return QueueMessage(str(receipt), Job.decode(values["job"]))

    async def ack(self, message: QueueMessage) -> None:
        await self.connect()
        await self._redis.xack(self._stream, self._group, message.receipt)

    async def retry(self, message: QueueMessage, *, delay_seconds: float = 0) -> str:
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)
        receipt = await self.enqueue(
            Job(message.job.job_type, message.job.payload, message.job.job_id, message.job.attempts + 1)
        )
        await self.ack(message)
        return receipt

    async def dead_letter(self, message: QueueMessage, *, reason: str) -> str:
        await self.connect()
        receipt = await self._redis.xadd(
            self._dead_letter_stream,
            {"job": message.job.encode(), "reason": reason},
        )
        await self.ack(message)
        return receipt

    async def _ensure_group(self) -> None:
        if self._group_ready:
            return
        try:
            await self._redis.xgroup_create(self._stream, self._group, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        self._group_ready = True


class InMemoryJobQueue:
    """Queue implementation for tests and local worker wiring."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[QueueMessage] = asyncio.Queue()
        self.dead_letters: list[tuple[QueueMessage, str]] = []
        self.acked: list[QueueMessage] = []

    async def enqueue(self, job: Job) -> str:
        receipt = uuid.uuid4().hex
        await self._queue.put(QueueMessage(receipt, job))
        return receipt

    async def receive(self, *, timeout_seconds: float | None = None) -> QueueMessage | None:
        try:
            if timeout_seconds is None:
                return await self._queue.get()
            return await asyncio.wait_for(self._queue.get(), timeout_seconds)
        except TimeoutError:
            return None

    async def ack(self, message: QueueMessage) -> None:
        self.acked.append(message)

    async def retry(self, message: QueueMessage, *, delay_seconds: float = 0) -> str:
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)
        receipt = await self.enqueue(
            Job(message.job.job_type, message.job.payload, message.job.job_id, message.job.attempts + 1)
        )
        await self.ack(message)
        return receipt

    async def dead_letter(self, message: QueueMessage, *, reason: str) -> str:
        self.dead_letters.append((message, reason))
        await self.ack(message)
        return message.receipt
