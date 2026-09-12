"""Stateless queue worker with bounded retries and dead-lettering."""

from __future__ import annotations

from dataclasses import dataclass

from src.jobs.queue import JobQueue, QueueMessage
from src.jobs.tasks import TaskRegistry


@dataclass(frozen=True, slots=True)
class WorkerResult:
    processed: int = 0
    retried: int = 0
    dead_lettered: int = 0
    idle: bool = False


class JobWorker:
    def __init__(
        self,
        queue: JobQueue,
        registry: TaskRegistry,
        *,
        max_retries: int = 3,
        base_delay_seconds: float = 0.5,
        max_delay_seconds: float = 8.0,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        if base_delay_seconds < 0 or max_delay_seconds < 0:
            raise ValueError("retry delays must not be negative")
        self._queue = queue
        self._registry = registry
        self._max_retries = max_retries
        self._base_delay = base_delay_seconds
        self._max_delay = max_delay_seconds

    async def run_once(self, *, timeout_seconds: float | None = None) -> WorkerResult:
        message = await self._queue.receive(timeout_seconds=timeout_seconds)
        if message is None:
            return WorkerResult(idle=True)
        return await self._process(message)

    async def run_forever(self, *, poll_timeout_seconds: float = 5.0) -> None:
        while True:
            await self.run_once(timeout_seconds=poll_timeout_seconds)

    async def _process(self, message: QueueMessage) -> WorkerResult:
        handler = self._registry.handler_for(message.job.job_type)
        if handler is None:
            await self._queue.dead_letter(message, reason="unknown_job_type")
            return WorkerResult(dead_lettered=1)
        try:
            await handler(message.job.payload)
        except Exception as exc:
            if message.job.attempts >= self._max_retries:
                await self._queue.dead_letter(message, reason=f"max_retries:{type(exc).__name__}")
                return WorkerResult(dead_lettered=1)
            delay = min(self._max_delay, self._base_delay * (2**message.job.attempts))
            await self._queue.retry(message, delay_seconds=delay)
            return WorkerResult(retried=1)
        await self._queue.ack(message)
        return WorkerResult(processed=1)
