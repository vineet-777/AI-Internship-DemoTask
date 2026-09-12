"""Task registration and dispatch for queued ingestion jobs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from src.jobs.queue import JobType

TaskHandler = Callable[[dict[str, Any]], Awaitable[None]]


class TaskRegistry:
    """Explicit job-type to async-handler mapping."""

    def __init__(self) -> None:
        self._handlers: dict[JobType, TaskHandler] = {}

    def register(self, job_type: JobType, handler: TaskHandler) -> None:
        if job_type in self._handlers:
            raise ValueError(f"A handler is already registered for {job_type.value}")
        self._handlers[job_type] = handler

    def handler_for(self, job_type: JobType) -> TaskHandler | None:
        return self._handlers.get(job_type)

    @property
    def handlers(self) -> dict[JobType, TaskHandler]:
        return dict(self._handlers)
