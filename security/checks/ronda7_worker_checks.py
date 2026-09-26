"""Ronda 7: comprobaciones del lado del worker contra la BD del laboratorio.

Requiere el laboratorio (`./security/lab.sh 8901`) y un worker arrancado con
`ronda7_worker.py` (mismas variables, LAB7_MARK_DIR y opcionalmente TMPDIR).
Se ejecuta con el código de la copia del laboratorio:

    cd $LAB_DIR/app-copy && PYTHONPATH=$PWD:<repo>/security/checks \
      DATABASE_URL=sqlite+aiosqlite:///$LAB_DIR/lab.db ENVIRONMENT=production \
      ALLOWED_HOSTS=127.0.0.1 ALLOW_SQLITE_IN_PRODUCTION=true SECRET_KEY=... \
      LAB7_MARK_DIR=... python <repo>/security/checks/ronda7_worker_checks.py

Imprime OK/FALLO/INFO. Solo escribe en la BD del laboratorio.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import time

import ronda7_lab_tasks  # noqa: F401
from sqlmodel import col, select

import app.tasks  # noqa: F401
from app.core.config import settings
from app.core.exceptions import APIError
from app.db.session import SessionFactory, engine
from app.models.job import Job
from app.models.user import User
from app.schemas.job import JobRead
from app.tasks.queue import enqueue

MARK = pathlib.Path(os.environ["LAB7_MARK_DIR"])
results: list[str] = []


def check(label: str, ok: bool, detail: str = "", info: bool = False) -> None:
    status = "INFO" if info else ("OK" if ok else "FALLO")
    results.append(status)
    print(f"[{status}] {label} {('-> ' + detail) if detail else ''}", flush=True)


async def user_id(email: str):
    async with SessionFactory() as s:
        return (await s.exec(select(User.id).where(User.email == email))).one()


async def put(name: str, payload: dict | None = None, owner=None, **kw) -> Job:
    async with SessionFactory() as s:
        return await enqueue(s, name, payload or {}, owner_id=owner, **kw)


async def wait(job_id, timeout: float = 40) -> Job:
    deadline = time.time() + timeout
    while True:
        async with SessionFactory() as s:
            job = await s.get(Job, job_id)
        if job.status in {"succeeded", "failed", "cancelled"} or time.time() > deadline:
            return job
        await asyncio.sleep(0.5)


async def main() -> None:
    alice = await user_id("alice@example.com")
    admin = await user_id("admin@example.com")

    # 1. Qué ve el cliente cuando la tarea falla -----------------------------------
    j = await wait((await put("lab7.boom", owner=alice)).id)
    view = JobRead.model_validate(j).model_dump()
    check("excepción interna -> cliente ve 'Task failed' (sin el mensaje)",
          j.status == "failed" and view["error"] == "Task failed" and "S3cr3t" not in str(view),
          f"{j.status} {view['error']!r}")
    j = await wait((await put("lab7.bizerr", owner=alice)).id)
    check("TaskError -> mensaje de negocio visible, sin reintento",
          j.error == "Invoice not available for this order" and j.attempts == 1, repr(j.error))
    j = await wait((await put("lab7.bigresult", owner=alice)).id)
    check("resultado > JOBS_MAX_RESULT_BYTES -> truncado",
          j.status == "succeeded" and j.result == {"truncated": True,
                                                    "detail": "Result too large to store"},
          str(j.result)[:80])

    # 2. Límite de payload ----------------------------------------------------------
    try:
        await put("system.echo", {"x": "a" * (settings.JOBS_MAX_PAYLOAD_BYTES + 10)}, owner=alice)
        check("payload > JOBS_MAX_PAYLOAD_BYTES rechazado", False, "aceptado")
    except APIError as exc:
        check("payload > JOBS_MAX_PAYLOAD_BYTES rechazado", exc.status_code == 413,
              f"{exc.status_code} {exc.code}")

    # 3. Executor process: timeout y procesos fuera de control ----------------------
    for f in MARK.glob("*.done"):
        f.unlink()
    t0 = time.time()
    s1 = await put("lab7.slowproc", {"tag": "a", "sleep": 12}, owner=admin)
    s2 = await put("lab7.slowproc", {"tag": "b", "sleep": 12}, owner=admin)
    await asyncio.sleep(1.5)
    fast = await put("lab7.fastproc", {}, owner=admin)
    j1, jf = await wait(s1.id, 20), await wait(fast.id, 20)
    check("slowproc (timeout=2 s) marcado como fallido por timeout",
          j1.status == "failed" and "Timed out" in (j1.error or ""),
          f"{j1.status} {j1.error!r} a los {time.time() - t0:.1f}s")
    check("fastproc (trivial) con el pool ocupado por procesos 'vencidos'",
          jf.status == "succeeded", f"{jf.status} {jf.error!r}", info=jf.status == "succeeded")
    await asyncio.sleep(max(0, 14 - (time.time() - t0)))
    marks = sorted(p.name for p in MARK.glob("slowproc-*.done"))
    check("tras el timeout, los procesos siguen ejecutándose hasta el final",
          True, f"marcas escritas después del 'failed': {marks}", info=True)

    # 4. Executor thread: abandonado al vencer y reintentado en paralelo -------------
    t0 = time.time()
    th = await put("lab7.slowthread", {"tag": "t", "sleep": 14}, owner=admin)
    jt = await wait(th.id, 40)
    await asyncio.sleep(max(0, 30 - (time.time() - t0)))
    tmarks = sorted(p.name for p in MARK.glob("slowthread-*.done"))
    check("thread vencido: el hilo sigue y el reintento lo ejecuta otra vez",
          True, f"estado={jt.status} intentos={jt.attempts} marcas={len(tmarks)}", info=True)

    # 5. Contrapresión por usuario y carrera ----------------------------------------
    bob = await user_id("bob@example.com")
    async with SessionFactory() as s:
        before = (await s.exec(select(Job).where(col(Job.owner_id) == bob,
                                                 col(Job.status).in_(["queued", "running"])))).all()
    n_before = len(before)
    limit = settings.JOBS_MAX_PENDING_PER_USER
    outcomes = await asyncio.gather(
        *[put("system.echo", {}, owner=bob, delay=3600) for _ in range(40)],
        return_exceptions=True,
    )
    ok = sum(1 for o in outcomes if isinstance(o, Job))
    r429 = sum(1 for o in outcomes if isinstance(o, APIError) and o.status_code == 429)
    other = [type(o).__name__ for o in outcomes if not isinstance(o, Job | APIError)]
    total = n_before + ok
    check(f"límite de pendientes ({limit}) con 40 encolados concurrentes",
          total <= limit, f"previos={n_before} aceptados={ok} 429={r429} otros={other[:3]} "
          f"=> pendientes={total}")
    try:
        await put("system.echo", {}, owner=bob, delay=3600)
        check("encolado secuencial por encima del límite -> 429", False, "aceptado")
    except APIError as exc:
        check("encolado secuencial por encima del límite -> 429", exc.status_code == 429,
              exc.code)
    # Limpieza: cancelar los trabajos diferidos de Bob.
    async with SessionFactory() as s:
        for job in (await s.exec(select(Job).where(col(Job.owner_id) == bob,
                                                   col(Job.status) == "queued"))).all():
            job.status = "cancelled"
            s.add(job)
        await s.commit()

    # 6. Heartbeat ------------------------------------------------------------------
    victim = MARK / "victim.txt"
    if victim.exists():
        content = victim.read_text()
        check("heartbeat sigue enlaces simbólicos (escribe en el destino)",
              content == "CONTENIDO-ORIGINAL", f"victim.txt contiene {content!r}",
              info=content != "CONTENIDO-ORIGINAL")

    await engine.dispose()
    print(f"\nResumen: {results.count('OK')} OK, {results.count('FALLO')} FALLO, "
          f"{results.count('INFO')} INFO")


asyncio.run(main())
