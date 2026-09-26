"""Worker de tareas en segundo plano: `apigen worker` (o `python -m app.tasks.worker`).

Corre en un proceso separado de la API, así que un trabajo pesado nunca
ralentiza las peticiones HTTP. Puedes arrancar tantos workers como quieras
(en la misma máquina o en otras): el reclamo de trabajos es atómico.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import socket
import uuid
from concurrent.futures import ProcessPoolExecutor
from functools import partial

import anyio

from app.core.config import settings
from app.db.session import SessionFactory, engine
from app.models.job import Job
from app.tasks import queue
from app.tasks.registry import REGISTRY, TaskContext, TaskError

logger = logging.getLogger("app.tasks")
_process_pool: ProcessPoolExecutor | None = None


def _pool() -> ProcessPoolExecutor:
    global _process_pool
    if _process_pool is None:
        _process_pool = ProcessPoolExecutor(max_workers=settings.JOBS_PROCESS_WORKERS)
    return _process_pool


async def run_job(job_id: uuid.UUID) -> str:
    """Ejecuta un trabajo ya reclamado y registra el resultado. Nunca lanza."""
    async with SessionFactory() as session:
        job = await session.get(Job, job_id)
    if job is None:
        return "missing"
    task = REGISTRY.get(job.name)
    if task is None:
        logger.error("unknown task %s (job %s)", job.name, job.id)
        return await queue.fail(job.id, "Unknown task", retry=False)

    extra = {"job_id": str(job.id), "task": job.name, "attempt": job.attempts}
    logger.info("job started", extra=extra)
    try:
        if task.executor == "async":
            ctx = TaskContext(job_id=job.id, owner_id=job.owner_id, attempt=job.attempts)
            coro = task.func(ctx, dict(job.payload))
        elif task.executor == "thread":
            coro = anyio.to_thread.run_sync(
                partial(task.func, dict(job.payload)), abandon_on_cancel=True
            )
        else:
            loop = asyncio.get_running_loop()
            coro = loop.run_in_executor(_pool(), task.func, dict(job.payload))
        result = await asyncio.wait_for(coro, timeout=task.timeout)
        json.dumps(result)  # el resultado debe ser serializable
    except TimeoutError:
        logger.warning("job timed out", extra=extra)
        return await queue.fail(job.id, f"Timed out after {task.timeout:g}s", retry=True)
    except TaskError as exc:
        logger.info("job failed: %s", exc, extra=extra)
        return await queue.fail(job.id, str(exc), retry=exc.retry)
    except (TypeError, ValueError) as exc:
        logger.exception("job failed", extra=extra)
        return await queue.fail(job.id, "Task failed", retry=not isinstance(exc, TypeError))
    except Exception:
        # La traza va al log (con job_id); al cliente solo un mensaje genérico.
        logger.exception("job failed", extra=extra)
        return await queue.fail(job.id, "Task failed", retry=True)
    await queue.complete(job.id, result)
    logger.info("job succeeded", extra=extra)
    return "succeeded"


async def process_pending(limit: int = 100, worker_id: str = "inline") -> int:
    """Procesa los trabajos listos y vuelve (útil en tests y en `apigen worker --once`)."""
    done = 0
    while done < limit:
        batch = await queue.claim(worker_id, min(10, limit - done))
        if not batch:
            break
        for job_id in batch:
            await run_job(job_id)
            done += 1
    return done


class Worker:
    def __init__(self, concurrency: int, poll_interval: float) -> None:
        self.concurrency = concurrency
        self.poll_interval = poll_interval
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self._stop = asyncio.Event()
        self._running: set[asyncio.Task[str]] = set()

    def stop(self) -> None:
        if not self._stop.is_set():
            logger.info("worker stopping: finishing running jobs")
            self._stop.set()

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self.stop)
        logger.info(
            "worker %s started (concurrency=%s, tasks=%s)",
            self.worker_id,
            self.concurrency,
            ", ".join(sorted(REGISTRY)) or "-",
        )
        last_reclaim = 0.0
        while not self._stop.is_set():
            now = loop.time()
            if now - last_reclaim > settings.JOBS_RECLAIM_INTERVAL:
                await self._safe(queue.reclaim_stale())
                last_reclaim = now
            free = self.concurrency - len(self._running)
            claimed = await self._safe(queue.claim(self.worker_id, free)) or []
            for job_id in claimed:
                job_task = asyncio.create_task(run_job(job_id))
                self._running.add(job_task)
                job_task.add_done_callback(self._running.discard)
            # Si la cola está vacía o estamos al máximo, espera antes de volver a mirar.
            if not claimed or len(self._running) >= self.concurrency:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)
                except TimeoutError:
                    pass
        if self._running:
            _, pending = await asyncio.wait(self._running, timeout=settings.JOBS_SHUTDOWN_GRACE)
            for job_task in pending:
                job_task.cancel()  # el arrendamiento vencerá y volverán a la cola
        logger.info("worker %s stopped", self.worker_id)

    @staticmethod
    async def _safe(coro):
        try:
            return await coro
        except Exception:
            # La BD puede estar caída un momento: el worker no muere por ello.
            logger.exception("worker loop error")
            return None


async def _main(args: argparse.Namespace) -> None:
    try:
        if args.once:
            count = await process_pending(limit=args.limit)
            logger.info("processed %s jobs", count)
        else:
            await Worker(args.concurrency, args.poll_interval).run()
    finally:
        if _process_pool is not None:
            _process_pool.shutdown(wait=False, cancel_futures=True)
        await engine.dispose()


def main(argv: list[str] | None = None) -> None:
    from app.core.logging import setup_logging

    parser = argparse.ArgumentParser(description="Worker de tareas en segundo plano")
    parser.add_argument("--concurrency", type=int, default=settings.JOBS_CONCURRENCY)
    parser.add_argument("--poll-interval", type=float, default=settings.JOBS_POLL_INTERVAL)
    parser.add_argument("--once", action="store_true", help="Procesar lo pendiente y salir")
    parser.add_argument("--limit", type=int, default=1000, help="Máximo de trabajos con --once")
    args = parser.parse_args(argv)
    setup_logging()
    import app.tasks  # noqa: F401  (registra todas las tareas)

    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
