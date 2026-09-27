# ruff: noqa: E501
"""Comprobaciones de seguridad de la fase 2 (validación independiente del experto).

Reutiliza las fixtures de tests/conftest.py (backend `memory`, SQLite temporal):

    .venv/bin/pytest -q -p no:cacheprovider -p tests.conftest security/checks/fase2_checks.py -rA

No modifica app/ ni tests/. Cada test documenta el caso ST o el hallazgo SEC que cubre.
Los tests marcados HALLAZGO pasan cuando el comportamiento inseguro SE REPRODUCE
(sirven de evidencia; al corregirse deben invertirse).
"""

from __future__ import annotations

import asyncio
import logging
import re
import statistics
import time
from datetime import timedelta
from urllib.parse import unquote

from sqlalchemy import update
from sqlmodel import col, select

from app.core.config import settings
from app.db.session import SessionFactory
from app.db.types import utcnow
from app.models.job import Job, JobStatus
from app.models.user import User
from app.tasks import queue
from app.tasks.worker import process_pending, run_job
from tests.conftest import TEST_PASSWORD, client_from, create_user, headers_for
from tests.helpers import _uid

API = "/api/v1"
FORGOT = f"{API}/auth/password/forgot"
RESET = f"{API}/auth/password/reset"
VALIDATE = f"{API}/auth/password/reset/validate"
VERIFY = f"{API}/auth/email/verify"
RESEND = f"{API}/auth/email/verify/resend"
REGISTER = f"{API}/auth/register"
LOGIN = f"{API}/auth/login"
CHANGE_EMAIL = f"{API}/users/me/email"
TOKEN = re.compile(r"#token=([A-Za-z0-9_\-%]+)")
ANY_TOKEN = re.compile(r"\b(pr|ev|ec)_[A-Za-z0-9_\-]{30,}")


def token_from(message) -> str:
    return unquote(TOKEN.search(message.text).group(1))


def sent_to(outbox, address):
    return [m for m in outbox if address in m.to]


# ---------------------------------------------------------------------------
# HALLAZGO SEC-40: los avisos (auth.notice) no tienen cupo por cuenta
# ---------------------------------------------------------------------------
async def test_sec40_notices_bypass_per_account_quota(client, mail, monkeypatch):
    """Una cuenta pide N cambios de email: la dirección ANTIGUA recibe N avisos
    `email_change_requested`, aunque el cupo por cuenta es 3/hora y 60 s de espera."""
    monkeypatch.setattr(settings, "EMAIL_PER_ACCOUNT_COOLDOWN_SECONDS", 60)
    victim = await create_user(email=f"victim-{_uid()}@example.com")
    headers = headers_for(victim)
    n = 8
    for i in range(n):
        r = await client.post(
            CHANGE_EMAIL,
            headers=headers,
            json={"new_email": f"t{i}-{_uid()}@example.com", "current_password": TEST_PASSWORD},
        )
        assert r.status_code == 202, r.text
    await process_pending()
    notices = [m for m in sent_to(mail, victim.email) if "#token=" not in m.text]
    confirms = [m for m in mail if "#token=" in m.text]
    print(
        f"\n[SEC-40] avisos a la dirección antigua: {len(notices)} / confirmaciones: {len(confirms)}"
    )
    # Invertido tras fase2-correcciones: los avisos tienen cupo por cuenta.
    assert len(notices) <= settings.EMAIL_NOTICES_PER_ACCOUNT_PER_HOUR < n
    assert len(confirms) == 1  # el enlace sí respeta el enfriamiento de 60 s


async def test_sec40_notices_consume_global_breaker_and_block_resets(client, mail, monkeypatch):
    """Con EMAIL_MAX_PER_HOUR=5, una sola cuenta agota el presupuesto global con avisos
    y el reset de OTRO usuario deja de enviarse (reintento por circuit_open)."""
    from sqlalchemy import func

    from app.models.email_log import EmailLog

    async with SessionFactory() as session:  # la BD de pruebas es compartida entre tests
        already = (
            await session.exec(
                select(func.count()).select_from(EmailLog).where(col(EmailLog.sent_at).is_not(None))
            )
        ).one()
    monkeypatch.setattr(settings, "EMAIL_MAX_PER_HOUR", already + 5)
    attacker = await create_user(email=f"att-{_uid()}@example.com")
    victim = await create_user(email=f"vic-{_uid()}@example.com")
    for i in range(3):  # 3 peticiones = 3 avisos + 2 confirmaciones (cupo) >= 5
        await client.post(
            CHANGE_EMAIL,
            headers=headers_for(attacker),
            json={"new_email": f"x{i}-{_uid()}@example.com", "current_password": TEST_PASSWORD},
        )
    await process_pending()
    before = len(mail)
    r = await client.post(FORGOT, json={"email": victim.email})
    assert r.status_code == 202
    await process_pending()
    async with SessionFactory() as session:
        job = (
            await session.exec(
                select(Job)
                .where(Job.name == "auth.password_reset")
                .order_by(col(Job.created_at).desc())
            )
        ).first()
    print(f"\n[SEC-40] enviados antes del reset: {before}; job reset: {job.status} / {job.error}")
    # Invertido: el reset tiene su propio presupuesto (seguridad) y se envía.
    assert len(sent_to(mail, victim.email)) == 1
    assert job.status == JobStatus.succeeded


# ---------------------------------------------------------------------------
# HALLAZGO SEC-41: carrera en el cupo por cuenta con varios trabajos a la vez
# ---------------------------------------------------------------------------
async def test_sec41_quota_race_with_concurrent_jobs(client, mail, monkeypatch):
    """El worker ejecuta hasta JOBS_CONCURRENCY trabajos a la vez: el cupo (contar y
    luego insertar) no está serializado por cuenta. En SQLite la carrera no siempre se
    da (se serializa más); se repite con varias cuentas. En PostgreSQL se reproduce
    siempre (ver fase2_docker_e2e.py)."""
    monkeypatch.setattr(settings, "EMAIL_PER_ACCOUNT_COOLDOWN_SECONDS", 60)
    counts = []
    for round_ in range(5):
        user = await create_user(email=f"race{round_}-{_uid()}@example.com")
        for i in range(6):
            async with client_from(f"10.9.{round_}.{i + 1}") as c:
                assert (await c.post(FORGOT, json={"email": user.email})).status_code == 202
        claimed = await queue.claim("race-worker", 10)
        await asyncio.gather(*(run_job(job_id, "race-worker") for job_id in claimed))
        counts.append(len(sent_to(mail, user.email)))
    print(
        f"\n[SEC-41] 6 trabajos simultáneos por cuenta -> correos por cuenta: {counts} (esperado 1)"
    )
    assert max(counts) == 1  # invertido: el cupo se serializa por cuenta


# ---------------------------------------------------------------------------
# HALLAZGO SEC-42: texto libre del usuario hacia una dirección no probada
# ---------------------------------------------------------------------------
async def test_sec42_email_changed_notice_carries_full_name_to_unproven_address(client, mail):
    """Modo optional: alguien registra el email de la víctima con un full_name de
    phishing, entra, cambia el email a uno suyo y confirma. El aviso final
    `email_changed` va a la dirección de la víctima (nunca verificada) con ese texto."""
    victim_addr = f"victim-{_uid()}@example.com"
    lure = "URGENTE visita http://evil.example/claim"
    r = await client.post(
        REGISTER, json={"email": victim_addr, "password": "a long passphrase ok", "full_name": lure}
    )
    assert r.status_code == 202
    await process_pending()
    r = await client.post(LOGIN, data={"username": victim_addr, "password": "a long passphrase ok"})
    assert r.status_code == 200  # optional: el no verificado puede entrar
    access = {"Authorization": f"Bearer {r.json()['access_token']}"}
    mine = f"attacker-{_uid()}@example.com"
    r = await client.post(
        CHANGE_EMAIL,
        headers=access,
        json={"new_email": mine, "current_password": "a long passphrase ok"},
    )
    assert r.status_code == 202
    await process_pending()
    token = token_from(sent_to(mail, mine)[-1])
    assert (await client.post(VERIFY, json={"token": token})).status_code == 204
    await process_pending()
    last = sent_to(mail, victim_addr)[-1]
    print(f"\n[SEC-42] asunto: {last.subject!r}; contiene el señuelo: {lure in last.text}")
    for m in sent_to(mail, victim_addr):
        assert lure not in m.text  # invertido: tampoco el aviso final (REQ-M06)
    assert "changed" in last.subject


# ---------------------------------------------------------------------------
# Q03: trabajos que terminan fuera de run_job no se vacían
# ---------------------------------------------------------------------------
async def test_sec43_reclaimed_and_cancelled_jobs_keep_payload(client, mail, admin_headers):
    user = await create_user()
    assert (await client.post(FORGOT, json={"email": user.email})).status_code == 202
    assert (await client.post(FORGOT, json={"email": f"x-{_uid()}@example.com"})).status_code == 202
    async with SessionFactory() as session:
        jobs = (
            await session.exec(
                select(Job).where(Job.name == "auth.password_reset", Job.status == JobStatus.queued)
            )
        ).all()
        stale, cancelled = jobs[-2], jobs[-1]
        await session.execute(
            update(Job)
            .where(col(Job.id) == stale.id)
            .values(
                status=JobStatus.running,
                attempts=stale.max_attempts,
                locked_until=utcnow() - timedelta(minutes=1),
            )
        )
        await session.commit()
    await queue.reclaim_stale()
    r = await client.post(f"{API}/jobs/{cancelled.id}/cancel", headers=admin_headers)
    assert r.status_code == 200
    async with SessionFactory() as session:
        a = await session.get(Job, stale.id)
        b = await session.get(Job, cancelled.id)
    print(
        f"\n[SEC-43] reclaimed: {a.status} payload={bool(a.payload)}; cancelled: {b.status} payload={bool(b.payload)}"
    )
    assert a.status == JobStatus.failed and a.payload == {}  # invertido
    assert b.status == JobStatus.cancelled and b.payload == {}


# ---------------------------------------------------------------------------
# Verificaciones positivas complementarias
# ---------------------------------------------------------------------------
async def test_st01_register_uniform_bytes_and_headers(client, mail):
    existing = await create_user(email_verified_at=utcnow())
    unverified = await create_user()
    results = []
    for i, email in enumerate((f"new-{_uid()}@example.com", existing.email, unverified.email)):
        async with client_from(f"10.8.0.{i + 1}") as c:
            r = await c.post(REGISTER, json={"email": email, "password": "another long passphrase"})
        hdrs = {
            k: v
            for k, v in r.headers.items()
            if k.lower() not in {"x-request-id", "date"} and not k.lower().startswith("x-ratelimit")
        }
        results.append((r.status_code, r.content, tuple(sorted(hdrs.items()))))
    assert results[0] == results[1] == results[2]
    assert results[0][0] == 202 and b"id" not in results[0][1]


async def test_st05_forgot_uniform_all_account_states(client, mail):
    active = await create_user()
    inactive = await create_user(is_active=False)
    locked = await create_user(locked_until=utcnow() + timedelta(hours=1), failed_login_attempts=5)
    verified = await create_user(email_verified_at=utcnow())
    seen = set()
    for i, email in enumerate(
        (active.email, inactive.email, locked.email, verified.email, f"none-{_uid()}@example.com")
    ):
        async with client_from(f"10.7.0.{i + 1}") as c:
            r = await c.post(FORGOT, json={"email": email})
        seen.add((r.status_code, r.content))
    assert len(seen) == 1 and next(iter(seen))[0] == 202


async def test_st16_st13_bad_tokens_same_400_everywhere(client, mail, user):
    r = await client.post(FORGOT, json={"email": user.email})
    await process_pending()
    reset = token_from(sent_to(mail, user.email)[-1])
    bad = [
        "x" * 10_000,
        "pr_" + "A" * 40 + "\x00",
        "pr_" + "!$" * 30,
        "ev_" + reset[3:],  # prefijo cambiado
        "",
    ]
    bodies = set()
    for token in bad:
        for url, body in (
            (RESET, {"token": token, "new_password": "a long passphrase ok"}),
            (VALIDATE, {"token": token}),
            (VERIFY, {"token": token}),
        ):
            r = await client.post(url, json=body)
            bodies.add((r.status_code, r.json().get("code")))
    r = await client.post(VERIFY, json={"token": reset})  # reset usado en verify
    bodies.add((r.status_code, r.json().get("code")))
    assert bodies == {(400, "invalid_or_expired_token")}
    # el token de reset real sigue valiendo tras todo lo anterior
    assert (await client.post(VALIDATE, json={"token": reset})).status_code == 204


async def test_st29_no_get_route_consumes_tokens(client, mail):
    from app.main import app as fastapi_app

    methods = {
        (route.path, m)
        for route in fastapi_app.routes
        for m in getattr(route, "methods", set())
        if "/auth/" in getattr(route, "path", "") or route.path.endswith("/me/email")
    }
    token_paths = [
        p for p, m in methods if m == "GET" and any(k in p for k in ("verify", "reset", "email"))
    ]
    assert token_paths == []


async def test_st37_logs_all_flows_debug(client, mail, caplog):
    """Registro, verificación, reset, cambio de email y avisos con DEBUG en la raíz."""
    email = f"logs-{_uid()}@example.com"
    with caplog.at_level(logging.DEBUG):
        await client.post(REGISTER, json={"email": email, "password": "a long passphrase ok"})
        await client.post(REGISTER, json={"email": email, "password": "a long passphrase ok"})
        await process_pending()
        ev = token_from(sent_to(mail, email)[0])
        await client.post(VERIFY, json={"token": ev})
        await client.post(FORGOT, json={"email": email})
        await process_pending()
        pr = token_from(sent_to(mail, email)[-1])
        await client.post(RESET, json={"token": pr, "new_password": "brand new passphrase"})
        r = await client.post(LOGIN, data={"username": email, "password": "brand new passphrase"})
        access = {"Authorization": f"Bearer {r.json()['access_token']}"}
        new = f"logs2-{_uid()}@example.com"
        await client.post(
            CHANGE_EMAIL,
            headers=access,
            json={"new_email": new, "current_password": "brand new passphrase"},
        )
        await process_pending()
        ec = token_from(sent_to(mail, new)[-1])
        await client.post(VERIFY, json={"token": ec})
        await process_pending()
    text = caplog.text + " ".join(str(r.__dict__) for r in caplog.records)
    for secret in (ev, pr, ec):
        assert secret not in text and secret[3:20] not in text
    assert not ANY_TOKEN.search(text)
    assert email not in text and new not in text and "#token=" not in text


async def test_st03_forgot_timing_in_process(client, mail, monkeypatch):
    """Réplica pequeña de ST-03 (forgot) sin rate limit: la API solo encola."""
    from app.core.rate_limit import limiter

    monkeypatch.setattr(limiter, "enabled", False)
    user = await create_user()
    samples = {"exists": [], "missing": []}
    for i in range(300):
        key = "exists" if i % 2 == 0 else "missing"
        email = user.email if key == "exists" else f"none-{i}-{_uid()}@example.com"
        t0 = time.perf_counter()
        r = await client.post(FORGOT, json={"email": email})
        samples[key].append((time.perf_counter() - t0) * 1000)
        assert r.status_code == 202
    a, b = statistics.median(samples["exists"]), statistics.median(samples["missing"])
    print(
        f"\n[ST-03] forgot mediana existe={a:.3f} ms / no existe={b:.3f} ms / dif={a - b:+.3f} ms"
    )
    assert abs(a - b) < 5


async def test_user_model_reads_back(client):
    """Sanidad: la BD de pruebas es accesible (evita falsos positivos por fixtures)."""
    user = await create_user()
    async with SessionFactory() as session:
        assert (await session.get(User, user.id)) is not None
