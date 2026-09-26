"""Tareas SOLO para el laboratorio de la ronda 7 (no se copian al proyecto).

Las registra `ronda7_worker.py` antes de arrancar el worker del laboratorio y
`ronda7_worker_checks.py` antes de encolar. Sirven para observar qué ve el
cliente cuando una tarea falla y qué ocurre con los executors al vencer el timeout.
"""

from __future__ import annotations

import os
import pathlib
import time

from app.tasks.registry import TaskError, task

MARK = os.environ.get("LAB7_MARK_DIR", "/tmp")


@task("lab7.boom", max_attempts=1)
async def boom(ctx, payload):
    # Simula una excepción interna con datos sensibles en el mensaje.
    raise RuntimeError("postgresql://api:S3cr3t-lab@db:5432/api connection refused")


@task("lab7.bizerr", max_attempts=1)
async def bizerr(ctx, payload):
    raise TaskError("Invoice not available for this order")


@task("lab7.bigresult", max_attempts=1)
async def bigresult(ctx, payload):
    return {"blob": "x" * 300_000}


@task("lab7.slowproc", executor="process", timeout=2, max_attempts=1)
def slowproc(payload):
    time.sleep(payload.get("sleep", 12))
    pathlib.Path(MARK, f"slowproc-{payload['tag']}.done").write_text(str(time.time()))
    return {"done": True}


@task("lab7.fastproc", executor="process", timeout=5, max_attempts=1)
def fastproc(payload):
    return {"ok": True}


@task("lab7.slowthread", executor="thread", timeout=2, max_attempts=2)
def slowthread(payload):
    time.sleep(payload.get("sleep", 8))
    pathlib.Path(MARK, f"slowthread-{payload['tag']}-{time.time():.0f}.done").write_text("x")
    return {"done": True}
