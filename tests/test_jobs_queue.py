from __future__ import annotations

import pytest

from src.jobs.queue import InMemoryJobQueue, Job, JobType


@pytest.mark.asyncio
async def test_job_round_trip_and_ack() -> None:
    queue = InMemoryJobQueue()
    job = Job(JobType.FETCH_URL, {"url": "https://example.test"})
    await queue.enqueue(job)
    message = await queue.receive(timeout_seconds=0.1)

    assert message is not None
    assert message.job == job
    await queue.ack(message)
    assert queue.acked == [message]


@pytest.mark.asyncio
async def test_retry_increments_attempt_and_dead_letters() -> None:
    queue = InMemoryJobQueue()
    job = Job(JobType.EXTRACT_ENTITY, {"record_id": "r1"})
    await queue.enqueue(job)
    message = await queue.receive(timeout_seconds=0.1)
    assert message is not None

    await queue.retry(message)
    retried = await queue.receive(timeout_seconds=0.1)
    assert retried is not None
    assert retried.job.job_id == job.job_id
    assert retried.job.attempts == 1

    await queue.dead_letter(retried, reason="max_retries")
    assert queue.dead_letters[0][1] == "max_retries"
