from __future__ import annotations

from src.jobs.queue import InMemoryJobQueue, Job, JobType
from src.jobs.tasks import TaskRegistry
from src.jobs.workers import JobWorker


async def test_worker_dispatches_and_acks_successful_task() -> None:
    queue = InMemoryJobQueue()
    registry = TaskRegistry()
    payloads: list[dict[str, object]] = []

    async def handler(payload: dict[str, object]) -> None:
        payloads.append(payload)

    registry.register(JobType.PARSE_DOCUMENT, handler)
    await queue.enqueue(Job(JobType.PARSE_DOCUMENT, {"raw_id": "raw-1"}))
    result = await JobWorker(queue, registry, base_delay_seconds=0).run_once(timeout_seconds=0.1)

    assert result.processed == 1
    assert payloads == [{"raw_id": "raw-1"}]
    assert len(queue.acked) == 1


async def test_worker_retries_then_dead_letters_after_budget() -> None:
    queue = InMemoryJobQueue()
    registry = TaskRegistry()
    calls = 0

    async def failing_handler(payload: dict[str, object]) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("broken")

    registry.register(JobType.EXTRACT_ENTITY, failing_handler)
    await queue.enqueue(Job(JobType.EXTRACT_ENTITY, {"record_id": "r1"}))
    worker = JobWorker(queue, registry, max_retries=1, base_delay_seconds=0)

    first = await worker.run_once(timeout_seconds=0.1)
    second = await worker.run_once(timeout_seconds=0.1)

    assert first.retried == 1
    assert second.dead_lettered == 1
    assert calls == 2
    assert queue.dead_letters[0][1].startswith("max_retries:")


async def test_worker_dead_letters_unknown_job_handler() -> None:
    queue = InMemoryJobQueue()
    await queue.enqueue(Job(JobType.EXPORT_RECORD, {"record_id": "r1"}))

    result = await JobWorker(queue, TaskRegistry()).run_once(timeout_seconds=0.1)

    assert result.dead_lettered == 1
    assert queue.dead_letters[0][1] == "unknown_job_type"
