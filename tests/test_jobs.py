"""Cola de trabajos en segundo plano: ejecución, permisos, reintentos y límites."""

from datetime import timedelta

import pytest
from sqlalchemy import update
from sqlmodel import col

import tests.tasks_for_tests  # noqa: F401  (registra las tareas de prueba)
from app.core.config import settings
from app.core.exceptions import APIError
from app.db.session import SessionFactory
from app.db.types import utcnow
from app.models.job import Job, JobStatus
from app.tasks import queue
from app.tasks.worker import process_pending


async def _enqueue(name, payload=None, owner=None, **kwargs) -> Job:
    async with SessionFactory() as session:
        return await queue.enqueue(
            session, name, payload, owner_id=owner.id if owner else None, **kwargs
        )


async def _job(job_id) -> Job:
    async with SessionFactory() as session:
        return await session.get(Job, job_id)


async def _make_ready(job_id) -> None:
    async with SessionFactory() as session:
        await session.execute(update(Job).where(col(Job.id) == job_id).values(run_after=utcnow()))
        await session.commit()


async def test_job_runs_in_worker_and_owner_sees_result(client, user, user_headers):
    job = await _enqueue("system.echo", {"hello": "world"}, owner=user)
    assert job.status == JobStatus.queued

    queued = await client.get(f"/api/v1/jobs/{job.id}", headers=user_headers)
    assert queued.json()["status"] == "queued"

    assert await process_pending() >= 1
    done = await client.get(f"/api/v1/jobs/{job.id}", headers=user_headers)
    assert done.status_code == 200
    body = done.json()
    assert body["status"] == "succeeded"
    assert body["result"]["echo"] == {"hello": "world"}
    assert body["attempts"] == 1


async def test_jobs_are_private(client, user, other_headers, admin_headers, user_headers):
    job = await _enqueue("system.echo", {}, owner=user)
    assert (await client.get(f"/api/v1/jobs/{job.id}", headers=other_headers)).status_code == 404
    assert (await client.get(f"/api/v1/jobs/{job.id}", headers=admin_headers)).status_code == 200
    mine = await client.get("/api/v1/jobs", headers=user_headers)
    assert str(job.id) in [j["id"] for j in mine.json()["items"]]
    theirs = await client.get("/api/v1/jobs", headers=other_headers)
    assert str(job.id) not in [j["id"] for j in theirs.json()["items"]]
    assert (await client.get(f"/api/v1/jobs/{job.id}")).status_code == 401


async def test_cancel_only_while_queued(client, user, user_headers):
    job = await _enqueue("system.echo", {}, owner=user, delay=3600)
    r = await client.post(f"/api/v1/jobs/{job.id}/cancel", headers=user_headers)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    again = await client.post(f"/api/v1/jobs/{job.id}/cancel", headers=user_headers)
    assert again.status_code == 409 and again.json()["code"] == "job_not_cancellable"


async def test_process_and_thread_executors():
    squared = await _enqueue("tests.square", {"n": 12})
    blocked = await _enqueue("tests.blocking", {})
    await process_pending()
    assert (await _job(squared.id)).result == {"value": 144}
    assert (await _job(blocked.id)).status == JobStatus.succeeded


async def test_failures_retry_with_backoff_and_hide_internal_errors():
    job = await _enqueue("tests.flaky")
    await process_pending()
    first = await _job(job.id)
    assert first.status == JobStatus.queued and first.attempts == 1
    assert first.run_after > utcnow()  # espera antes del reintento
    assert first.error == "Task failed" and "hunter2" not in first.error

    await _make_ready(job.id)
    await process_pending()
    final = await _job(job.id)
    assert final.status == JobStatus.failed and final.attempts == 2


async def test_task_error_message_is_shown_and_not_retried():
    job = await _enqueue("tests.business_error")
    await process_pending()
    done = await _job(job.id)
    assert done.status == JobStatus.failed
    assert done.error == "The report has no rows"
    assert done.attempts == 1


async def test_timeout_marks_job_failed():
    job = await _enqueue("tests.slow")
    await process_pending()
    done = await _job(job.id)
    assert done.status == JobStatus.failed and "Timed out" in done.error


async def test_payload_limits_and_backpressure(user, monkeypatch):
    with pytest.raises(APIError) as too_big:
        await _enqueue("system.echo", {"x": "a" * (settings.JOBS_MAX_PAYLOAD_BYTES + 1)})
    assert too_big.value.status_code == 413

    monkeypatch.setattr(settings, "JOBS_MAX_PENDING_PER_USER", 2)
    await _enqueue("system.echo", {}, owner=user, delay=3600)
    await _enqueue("system.echo", {}, owner=user, delay=3600)
    with pytest.raises(APIError) as full:
        await _enqueue("system.echo", {}, owner=user)
    assert full.value.status_code == 429 and full.value.code == "too_many_pending_jobs"


async def test_unknown_task_cannot_be_enqueued_and_orphans_fail():
    async with SessionFactory() as session:
        with pytest.raises(LookupError):
            await queue.enqueue(session, "does.not.exist")
        orphan = Job(name="removed.task")
        session.add(orphan)
        await session.commit()
        orphan_id = orphan.id
    await process_pending()
    done = await _job(orphan_id)
    assert done.status == JobStatus.failed and done.error == "Unknown task"


async def test_stale_jobs_from_dead_workers_are_reclaimed():
    job = await _enqueue("tests.blocking", {})  # admite reintentos (max_attempts=3)
    claimed = await queue.claim("dead-worker", 50)
    assert job.id in claimed
    async with SessionFactory() as session:
        await session.execute(
            update(Job)
            .where(col(Job.id) == job.id)
            .values(locked_until=utcnow() - timedelta(seconds=1))
        )
        await session.commit()
    assert await queue.reclaim_stale() >= 1
    assert (await _job(job.id)).status == JobStatus.queued
    await process_pending()
    assert (await _job(job.id)).status == JobStatus.succeeded


async def test_a_job_is_claimed_only_once():
    job = await _enqueue("system.echo", {})
    first = await queue.claim("worker-a", 100)
    second = await queue.claim("worker-b", 100)
    assert job.id in first and job.id not in second


async def test_prune_removes_old_finished_jobs():
    job = await _enqueue("system.echo", {})
    await process_pending()
    async with SessionFactory() as session:
        await session.execute(
            update(Job)
            .where(col(Job.id) == job.id)
            .values(finished_at=utcnow() - timedelta(days=settings.JOBS_RETENTION_DAYS + 1))
        )
        await session.commit()
    assert await queue.prune_jobs() >= 1
    assert await _job(job.id) is None
