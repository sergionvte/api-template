# ruff: noqa: E501
"""E2E de seguridad de la fase 2 contra el laboratorio Docker (modo producción).

Requiere la pila `-p apisec2` (API en 127.0.0.1:8901, Mailpit web en 127.0.0.1:8925,
PostgreSQL, worker con SMTP STARTTLS verificado contra una CA de laboratorio).

    .venv/bin/python security/checks/fase2_docker_e2e.py <dir-del-compose>

Solo 127.0.0.1. Imprime una línea por comprobación (OK / FALLO / DATO).
"""

from __future__ import annotations

import concurrent.futures
import math
import os
import re
import statistics
import subprocess
import sys
import time
import uuid

import httpx

# Parametrizable (fase2-correcciones): E2E_PROJECT, E2E_API_PORT, E2E_MAILPIT_PORT.
PROJECT = os.environ.get("E2E_PROJECT", "apisec2")
API_PORT = os.environ.get("E2E_API_PORT", "8901")
API = f"http://127.0.0.1:{API_PORT}/api/v1"
MAILPIT = f"http://127.0.0.1:{os.environ.get('E2E_MAILPIT_PORT', '8925')}/api/v1"
COMPOSE_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
COMPOSE = [
    "docker", "compose", "-p", PROJECT, "-f", "docker-compose.yml",
    "-f", "compose.mail.yml", "-f", "../override.yml",
]  # fmt: skip
TOKEN = re.compile(r"#token=((?:pr|ev|ec)_[A-Za-z0-9_\-%]+)")
ANY_TOKEN = re.compile(r"\b(pr|ev|ec)_[A-Za-z0-9_\-]{30,}")
PASSWORD = "lab passphrase 2026 ok"
results: list[tuple[str, str, str]] = []


def report(tag: str, ok: bool | None, detail: str) -> None:
    state = "DATO" if ok is None else ("OK" if ok else "FALLO")
    results.append((tag, state, detail))
    print(f"[{state:5}] {tag}: {detail}", flush=True)


def uid() -> str:
    return uuid.uuid4().hex[:10]


def mann_whitney_p(a: list[float], b: list[float]) -> float:
    """p bilateral (aproximación normal, sin corrección de empates)."""
    combined = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    ranks_a = sum(i + 1 for i, (_, g) in enumerate(combined) if g == 0)
    n1, n2 = len(a), len(b)
    u = ranks_a - n1 * (n1 + 1) / 2
    mu, sigma = n1 * n2 / 2, math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
    z = abs(u - mu) / sigma
    return math.erfc(z / math.sqrt(2))


def compose(*args: str) -> str:
    return subprocess.run(
        [*COMPOSE, *args], cwd=COMPOSE_DIR, capture_output=True, text=True, check=False
    ).stdout


def psql(sql: str) -> str:
    return compose("exec", "-T", "db", "psql", "-U", "api", "-d", "api", "-At", "-c", sql).strip()


def mails_to(address: str, expect: int = 1, timeout: float = 25) -> list[dict]:
    deadline = time.time() + timeout
    found: list[dict] = []
    while time.time() < deadline:
        r = httpx.get(f"{MAILPIT}/search", params={"query": f'to:"{address}"', "limit": 50})
        found = r.json().get("messages", [])
        if len(found) >= expect:
            break
        time.sleep(1)
    return sorted(found, key=lambda m: m["Created"])


def message(msg_id: str) -> dict:
    return httpx.get(f"{MAILPIT}/message/{msg_id}").json()


def raw(msg_id: str) -> str:
    return httpx.get(f"{MAILPIT}/message/{msg_id}/raw").text


def drain(limit: float = 300) -> float:
    """Espera a que el worker vacíe la cola; devuelve los segundos que tardó."""
    t0 = time.time()
    while time.time() - t0 < limit:
        if psql("SELECT count(*) FROM jobs WHERE status IN ('queued','running')") == "0":
            break
        time.sleep(2)
    return time.time() - t0


def token_of(msg: dict) -> str:
    from urllib.parse import unquote

    return unquote(TOKEN.search(message(msg["ID"])["Text"]).group(1))


def timed(client: httpx.Client, url: str, **kw) -> tuple[float, httpx.Response]:
    t0 = time.perf_counter()
    r = client.post(url, **kw)
    return (time.perf_counter() - t0) * 1000, r


def login(client: httpx.Client, email: str, password: str = PASSWORD) -> httpx.Response:
    return client.post(f"{API}/auth/login", data={"username": email, "password": password})


def main() -> None:
    c = httpx.Client(timeout=30, headers={"Host": f"127.0.0.1:{API_PORT}"})
    assert c.get(f"http://127.0.0.1:{API_PORT}/health/live").status_code == 200

    # --- ST-01/03 registro en PostgreSQL --------------------------------------
    existing = f"exist-{uid()}@lab-cliente.dev"
    c.post(f"{API}/auth/register", json={"email": existing, "password": PASSWORD})
    samples = {"new": [], "existing": []}
    shapes = set()
    for i in range(120):
        kind = "new" if i % 2 == 0 else "existing"
        email = f"t{i}-{uid()}@lab-cliente.dev" if kind == "new" else existing
        ms, r = timed(c, f"{API}/auth/register", json={"email": email, "password": PASSWORD})
        samples[kind].append(ms)
        hdrs = tuple(
            sorted(
                (k, v)
                for k, v in r.headers.items()
                if k not in {"x-request-id", "date", "content-length"}
                and not k.startswith("x-ratelimit")
            )
        )
        shapes.add((r.status_code, r.content, hdrs))
    a, b = statistics.median(samples["new"]), statistics.median(samples["existing"])
    p = mann_whitney_p(samples["new"], samples["existing"])
    report(
        "ST-01", len(shapes) == 1, f"{len(shapes)} forma(s) de respuesta distintas en 120 registros"
    )
    report(
        "ST-03 register/PG",
        abs(a - b) < 5 and p > 0.01,
        f"mediana nuevo={a:.2f} ms existente={b:.2f} ms dif={a - b:+.2f} ms p={p:.3f}",
    )

    # --- ST-03 forgot ------------------------------------------------------------
    samples = {"exists": [], "missing": []}
    for i in range(300):
        kind = "exists" if i % 2 == 0 else "missing"
        email = existing if kind == "exists" else f"none{i}-{uid()}@lab-cliente.dev"
        ms, r = timed(c, f"{API}/auth/password/forgot", json={"email": email})
        samples[kind].append(ms)
    a, b = statistics.median(samples["exists"]), statistics.median(samples["missing"])
    p = mann_whitney_p(samples["exists"], samples["missing"])
    report(
        "ST-03 forgot/PG",
        abs(a - b) < 5 and p > 0.01,
        f"mediana existe={a:.2f} ms no existe={b:.2f} ms dif={a - b:+.2f} ms p={p:.3f}",
    )

    pending = psql("SELECT count(*) FROM jobs WHERE status IN ('queued','running')")
    waited = drain()
    report(
        "DATO cola",
        None,
        f"{pending} trabajos pendientes tras la ráfaga; el worker tardó {waited:.0f} s en vaciarla",
    )

    # --- Registro nuevo + duplicado: correos --------------------------------------
    victim = f"victim-{uid()}@lab-cliente.dev"
    lure = "<b>Hola</b><script>alert(1)</script> http://evil.example"
    c.post(f"{API}/auth/register", json={"email": victim, "password": PASSWORD, "full_name": lure})
    # fase2-correcciones: con el cupo serializado (SEC-41), un segundo correo a la misma
    # cuenta antes de 60 s se descarta (D3). Se espera al enfriamiento para ver el aviso.
    time.sleep(61)
    c.post(f"{API}/auth/register", json={"email": victim, "password": "other passphrase 99 x"})
    msgs = mails_to(victim, expect=2)
    with_token = [m for m in msgs if "#token=" in message(m["ID"])["Text"]]
    report(
        "ST-02",
        len(msgs) == 2 and len(with_token) == 1,
        f"{len(msgs)} correos a la cuenta: verificación + 'ya tienes cuenta' sin enlace",
    )
    msgs = with_token
    first = message(msgs[0]["ID"])
    rawtext = raw(msgs[0]["ID"])
    report(
        "ST-30/M06",
        "evil.example" not in first["Text"] and "script" not in first["HTML"].lower(),
        "full_name no aparece en el correo de verificación (dirección no probada)",
    )
    report(
        "M04/M09",
        "Auto-Submitted: auto-generated" in rawtext
        and "From: Cliente Lab <no-reply@lab-cliente.dev>" in rawtext,
        "cabeceras From de cliente y Auto-Submitted presentes",
    )
    link = TOKEN.search(first["Text"])
    report(
        "L01/L03",
        bool(link) and "https://app.lab-cliente.dev/verify-email#token=ev_" in first["Text"],
        "enlace de verificación en el fragmento y con el dominio configurado",
    )

    # --- ST-08 login sin verificar --------------------------------------------------
    r_bad = login(c, victim, "wrong passphrase 123 x")
    r_ok = login(c, victim)
    report(
        "ST-08",
        r_bad.status_code == 401 and r_ok.status_code == 403 and "access_token" not in r_ok.text,
        f"contraseña mala={r_bad.status_code}, buena={r_ok.status_code} {r_ok.json().get('code')}",
    )

    # --- Verificación ---------------------------------------------------------------
    ev = token_of(msgs[0])
    r1 = c.post(f"{API}/auth/email/verify", json={"token": ev})
    r2 = c.post(f"{API}/auth/email/verify", json={"token": ev})
    report(
        "ST-22/L05",
        r1.status_code == 204
        and r2.status_code == 204
        and r1.headers.get("cache-control") == "no-store"
        and "access_token" not in r1.text,
        f"verify={r1.status_code} repetido={r2.status_code} cache={r1.headers.get('cache-control')}",
    )
    tokens = login(c, victim).json()
    access = {"Authorization": f"Bearer {tokens['access_token']}"}

    # --- ST-28 forgot con cabeceras maliciosas -----------------------------------------
    time.sleep(61)  # enfriamiento por cuenta (60 s) tras el correo de verificación
    r = c.post(
        f"{API}/auth/password/forgot",
        json={"email": victim},
        headers={
            "X-Forwarded-Host": "evil.example",
            "Origin": "https://evil.example",
            "Referer": "https://evil.example/x",
            "Forwarded": "host=evil.example",
        },
    )
    r_host = httpx.post(
        f"{API}/auth/password/forgot", json={"email": victim}, headers={"Host": "evil.example"}
    )
    msgs = [m for m in mails_to(victim, expect=3) if "reset-password" in message(m["ID"])["Text"]]
    reset_msg = message(msgs[-1]["ID"])
    report(
        "ST-28",
        "evil.example" not in reset_msg["Text"]
        and "https://app.lab-cliente.dev/reset-password#token=pr_" in reset_msg["Text"],
        f"enlace limpio; Host: evil.example -> {r_host.status_code} (ALLOWED_HOSTS)",
    )
    pr = token_of(msgs[-1])

    # --- Reset ------------------------------------------------------------------------
    weak = c.post(f"{API}/auth/password/reset", json={"token": pr, "new_password": "short"})
    val = c.post(f"{API}/auth/password/reset/validate", json={"token": pr})
    ok = c.post(
        f"{API}/auth/password/reset", json={"token": pr, "new_password": "new lab passphrase 77"}
    )
    again = c.post(
        f"{API}/auth/password/reset", json={"token": pr, "new_password": "new lab passphrase 88"}
    )
    me = c.get(f"{API}/users/me", headers=access)
    refresh = c.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    report(
        "ST-17/11/18",
        weak.status_code == 422
        and val.status_code == 204
        and ok.status_code == 204
        and again.status_code == 400
        and me.status_code == 401
        and refresh.status_code == 401,
        f"débil={weak.status_code} validate={val.status_code} reset={ok.status_code} reuso={again.status_code} access={me.status_code} refresh={refresh.status_code}",
    )
    time.sleep(8)
    msgs = [m for m in mails_to(victim, expect=4) if "#token=" not in message(m["ID"])["Text"]]
    notice = message(msgs[-1]["ID"])
    report(
        "ST-44",
        "#token=" not in notice["Text"] and not ANY_TOKEN.search(notice["Text"]),
        f"aviso '{notice['Subject']}' sin tokens",
    )

    # --- SEC-42 en el laboratorio: el aviso final lleva full_name (ya verificado) ------
    report(
        "DATO M07",
        None,
        f"aviso de contraseña con full_name escapado en HTML: {'&lt;script&gt;' in notice['HTML']}",
    )

    # --- Cambio de email + SEC-40 --------------------------------------------------------
    tokens = login(c, victim, "new lab passphrase 77").json()
    access = {"Authorization": f"Bearer {tokens['access_token']}"}
    targets = [f"new{i}-{uid()}@lab-cliente.dev" for i in range(6)]
    for t in targets:
        c.post(
            f"{API}/users/me/email",
            headers=access,
            json={"new_email": t, "current_password": "new lab passphrase 77"},
        )
    time.sleep(12)
    old_notices = [
        m for m in mails_to(victim, expect=4 + 6) if "#token=" not in message(m["ID"])["Text"]
    ]
    confirmations = sum(len(mails_to(t, expect=1, timeout=1)) for t in targets)
    report(
        "SEC-40",
        None,
        f"6 peticiones de cambio -> {len(old_notices) - 2} avisos a la dirección antigua, {confirmations} enlaces a las nuevas",
    )

    # --- SEC-41 carrera del cupo en PostgreSQL ---------------------------------------------
    racer = f"racer-{uid()}@lab-cliente.dev"
    c.post(f"{API}/auth/register", json={"email": racer, "password": PASSWORD})
    ev = token_of(mails_to(racer)[0])
    c.post(f"{API}/auth/email/verify", json={"token": ev})
    time.sleep(61)  # que pase el enfriamiento del correo de alta

    def fire(i: int) -> int:
        return httpx.post(
            f"{API}/auth/password/forgot",
            json={"email": racer},
            headers={"X-Forwarded-For": f"198.51.100.{i + 1}"},
        ).status_code

    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        codes = list(pool.map(fire, range(8)))
    time.sleep(15)
    resets = [
        m
        for m in mails_to(racer, expect=9, timeout=5)
        if "reset-password" in message(m["ID"])["Text"]
    ]
    report(
        "SEC-41",
        None,
        f"8 forgot simultáneos ({set(codes)}) con enfriamiento de 60 s -> {len(resets)} correos de reset",
    )

    # --- PostgreSQL: tokens y jobs -----------------------------------------------------------
    bad_hash = psql("SELECT count(*) FROM account_tokens WHERE token_hash !~ '^[0-9a-f]{64}$'")
    leaks = psql(
        "SELECT count(*) FROM jobs WHERE payload::text ~ '(pr|ev|ec)_[A-Za-z0-9_-]{30}' OR coalesce(result::text,'') ~ '(pr|ev|ec)_' OR coalesce(error,'') ~ '(pr|ev|ec)_'"
    )
    filled = psql(
        "SELECT count(*) FROM jobs WHERE status IN ('succeeded','failed') AND payload::text <> '{}'"
    )
    owners = psql("SELECT count(*) FROM jobs WHERE name LIKE 'auth.%' AND owner_id IS NOT NULL")
    report(
        "ST-10/Q01/Q03",
        bad_hash == "0" and leaks == "0" and filled == "0" and owners == "0",
        f"hashes no hex={bad_hash}, jobs con token={leaks}, terminados con payload={filled}, con owner={owners}",
    )

    # --- Logs -------------------------------------------------------------------------------
    logs = compose("logs", "--no-color", "api", "worker")
    smtp_pw = open(os.path.join(COMPOSE_DIR, "..", "smtp_password.txt")).read().strip()
    hits = {
        "token": bool(ANY_TOKEN.search(logs)),
        "#token=": "#token=" in logs,
        "email@lab": "@lab-cliente.dev" in logs.replace("no-reply@lab-cliente.dev", ""),
        "smtp_password": smtp_pw in logs,
    }
    report(
        "ST-37/G01",
        not any(hits.values()),
        f"{len(logs.splitlines())} líneas de log (DEBUG); coincidencias: {hits}",
    )


def timing_only(n: int = 200) -> None:
    """ST-03 del registro con el worker en reposo (cola vacía) y más muestras."""
    c = httpx.Client(timeout=30, headers={"Host": f"127.0.0.1:{API_PORT}"})
    drain()
    existing = f"exist-{uid()}@lab-cliente.dev"
    c.post(f"{API}/auth/register", json={"email": existing, "password": PASSWORD})
    samples = {"new": [], "existing": []}
    for i in range(2 * n):
        kind = "new" if i % 2 == 0 else "existing"
        email = f"q{i}-{uid()}@lab-cliente.dev" if kind == "new" else existing
        ms, _ = timed(c, f"{API}/auth/register", json={"email": email, "password": PASSWORD})
        samples[kind].append(ms)
    a, b = statistics.median(samples["new"]), statistics.median(samples["existing"])
    p = mann_whitney_p(samples["new"], samples["existing"])
    report(
        "ST-03 register/PG (reposo)",
        abs(a - b) < 5 and p > 0.01,
        f"n={n}+{n} mediana nuevo={a:.2f} ms existente={b:.2f} ms dif={a - b:+.2f} ms p={p:.4f}",
    )


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "timing":
        timing_only()
    else:
        main()
    fails = [r for r in results if r[1] == "FALLO"]
    print(f"\n{len(results)} comprobaciones, {len(fails)} fallos")
