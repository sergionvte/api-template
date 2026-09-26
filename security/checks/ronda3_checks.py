"""Ronda 3: verificación de las correcciones del desarrollador.

Lanzar el laboratorio con TRUSTED_PROXIES=127.0.0.1 para simular varias IPs
de cliente mediante X-Forwarded-For (el script solo habla con 127.0.0.1):

    TRUSTED_PROXIES=127.0.0.1 REFRESH_REUSE_GRACE_SECONDS=<n> ./security/lab.sh 8901
    LAB_CREDS=$LAB_DIR/credentials.json python security/checks/ronda3_checks.py 8901
"""
from __future__ import annotations

import asyncio, json, os, sys, time, uuid
import httpx

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8901
BASE = f"http://127.0.0.1:{PORT}"
PW = {e: d["password"] for e, d in json.load(open(os.environ["LAB_CREDS"])).items()}
c = httpx.Client(base_url=BASE, timeout=30)


def ip(addr: str) -> dict:
    return {"X-Forwarded-For": addr}


def show(label, r):
    print(f"- {label}: {r.request.method} {r.request.url.path} -> {r.status_code} {r.text[:140]!r}", flush=True)


def login(email, pw, addr, **kw):
    return c.post("/api/v1/auth/login", data={"username": email, "password": pw}, headers=ip(addr), **kw)


section = sys.argv[2] if len(sys.argv) > 2 else "all"

if section in ("all", "general"):
    print("== General ==")
    r = login("admin@example.com", PW["admin@example.com"], "198.51.100.1"); show("login admin", r)
    admin = {"Authorization": "Bearer " + r.json()["access_token"]}
    r = c.post("/api/v1/auth/login", json={"username": "a", "password": "b"}); show("login con JSON (415)", r)
    r = login("x\x00@example.com", "whatever-password", "198.51.100.2"); show("login con NUL en username", r)
    r = c.post("/api/v1/auth/register", json={"email": "nul@example.com", "password": "lab-" + uuid.uuid4().hex, "full_name": "a\x00b"}, headers=ip("198.51.100.3")); show("registro con NUL en full_name", r)
    r = c.post("/api/v1/categories", json={"name": "C", "slug": "c"}, headers=admin); cat = r.json()["id"]
    p = {"name": "P", "sku": "S1", "price": "1.00", "category_id": cat}
    r = c.post("/api/v1/products", json={**p, "stock": 2**63}, headers=admin); show("stock=2**63", r)
    r = c.post("/api/v1/products", json={**p, "sku": "S2", "stock": 2**31}, headers=admin); show("stock=2**31 (BIGINT)", r)
    r = c.post("/api/v1/products", json={**p, "sku": "S3", "attributes": {"k": "x" * 20000}}, headers=admin); show("json 20 KB", r)
    deep = {}; cur = deep
    for _ in range(12):
        cur["a"] = {}; cur = cur["a"]
    r = c.post("/api/v1/products", json={**p, "sku": "S4", "attributes": deep}, headers=admin); show("json profundidad 13", r)
    r = c.post("/api/v1/products", json={**p, "sku": "S5", "attributes": {"k": "a\x00"}}, headers=admin); show("json con NUL", r)
    r = c.post("/api/v1/products", json={**p, "sku": "S1"}, headers=admin); show("sku duplicado (409 con fields)", r)
    r = c.post("/api/v1/products", json={**p, "sku": "S6", "category_id": str(uuid.uuid4())}, headers=admin); show("FK inexistente", r)
    codes = [c.get("/api/v1/nope", headers=ip("198.51.100.9")).status_code for _ in range(125)]
    print(f"- 125 GET /nope desde una IP: {codes.count(404)}x404 {codes.count(429)}x429")
    r = c.get("/api/v1/nope", headers=ip("198.51.100.9")); print("  cabeceras 429 unrouted:", {k: v for k, v in r.headers.items() if k.startswith(("x-", "retry", "content-security"))})
    r = c.options("/api/v1/products", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"}); show("preflight desde localhost en producción", r)
    print("  ACAO:", r.headers.get("access-control-allow-origin"))
    big = b'{"full_name":"' + b"a" * 1_100_000 + b'"}'
    def gen():
        for _ in range(20):
            yield b"a" * 100_000
    r = c.patch("/api/v1/users/me", content=gen(), headers={**admin, "Content-Type": "application/json"}); show("chunked > 1 MiB", r)
    print("  x-request-id en 413:", r.headers.get("x-request-id"), "csp:", bool(r.headers.get("content-security-policy")))
    c.get("/api/v1/x%0aFAKE%20LOG%20line", headers=ip("198.51.100.10"))
    r = c.get("/health/live", headers={"X-Forwarded-Proto": "https"}); print("- HSTS con X-Forwarded-Proto=https desde proxy de confianza:", r.headers.get("strict-transport-security"))
    r = c.get("/health/live", headers={"X-Forwarded-For": "203.0.113.50, 198.51.100.77"}); show("XFF con dos saltos (debe tomarse el de la derecha)", r)

if section in ("all", "lockout"):
    print("== Bloqueo inteligente (SEC-02) ==")
    victim, vpw = "alice@example.com", PW["alice@example.com"]
    HOME, ATT1, ATT2, NEW = "198.51.100.20", "203.0.113.1", "203.0.113.2", "192.0.2.77"
    r = login(victim, vpw, HOME); show("alice inicia sesión desde su IP habitual", r)
    for i in range(5):
        login(victim, f"wrong-{i}-xxxxxxxx", ATT1 if i % 2 else ATT2)
    r = login(victim, vpw, HOME); show("alice desde IP conocida tras 5 fallos de un tercero", r)
    r = login(victim, vpw, NEW); show("alice desde IP NUEVA (móvil/viaje) tras el ataque", r)
    r = login(victim, vpw, ATT1); show("contraseña correcta desde IP del atacante (bloqueada)", r)
    # escalado: el éxito desde HOME resetea el contador, así que sin éxito intermedio:
    admin_email, apw = "admin@example.com", PW["admin@example.com"]
    for i in range(5):
        login(admin_email, f"wrong-{i}-xxxxxxxx", f"203.0.113.{10+i}")
    r = login(admin_email, apw, "192.0.2.200"); show("admin desde IP nueva tras 5 fallos anónimos", r)
    r = login(admin_email, apw, "198.51.100.1"); show("admin desde IP conocida (general)", r)
    # atacante que comparte IP (NAT) con la víctima
    bob, bpw = "bob@example.com", PW["bob@example.com"]
    login(bob, bpw, "198.51.100.30")
    for i in range(5):
        login(bob, f"wrong-{i}-xxxxxxxx", "203.0.113.40")
    codes = [login(bob, f"guess-{i}-xxxxxxxx", "198.51.100.30").status_code for i in range(6)]
    print(f"- atacante desde la IP 'conocida' de bob sigue probando contraseñas: {codes}")

if section in ("all", "race"):
    print("== Carrera en refresh (SEC-01) ==")
    async def trial(ac, addr_a, addr_b):
        r = await ac.post("/api/v1/auth/login", data={"username": "bob@example.com", "password": PW["bob@example.com"]}, headers=ip(addr_a))
        tok = r.json()["refresh_token"]
        a, b = await asyncio.gather(
            ac.post("/api/v1/auth/refresh", json={"refresh_token": tok}, headers=ip(addr_a)),
            ac.post("/api/v1/auth/refresh", json={"refresh_token": tok}, headers=ip(addr_b)))
        win = next((x for x in (a, b) if x.status_code == 200), None)
        after = (await ac.post("/api/v1/auth/refresh", json={"refresh_token": win.json()["refresh_token"]}, headers=ip(addr_a))).status_code if win else None
        print(f"- IPs {addr_a} / {addr_b}: códigos={sorted([a.status_code, b.status_code])} token del ganador después -> {after}")
    async def main():
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as ac:
            for i in range(3):
                await trial(ac, f"198.51.100.{60+i}", f"198.51.100.{60+i}")
            for i in range(3):
                await trial(ac, f"198.51.100.{70+i}", f"203.0.113.{99+i}")
    asyncio.run(main())
    # Reutilización secuencial pasada la gracia
    r = login("bob@example.com", PW["bob@example.com"], "198.51.100.80"); t1 = r.json()["refresh_token"]; acc = r.json()["access_token"]
    r = c.post("/api/v1/auth/refresh", json={"refresh_token": t1}, headers=ip("198.51.100.80")); t2 = r.json()["refresh_token"]
    r = c.post("/api/v1/auth/refresh", json={"refresh_token": t1}, headers=ip("198.51.100.80")); show("reutilización inmediata misma IP (gracia)", r)
    r = c.post("/api/v1/auth/refresh", json={"refresh_token": t1}, headers=ip("203.0.113.5")); show("reutilización inmediata desde otra IP", r)
    r = c.post("/api/v1/auth/refresh", json={"refresh_token": t2}, headers=ip("198.51.100.80")); show("token vigente tras la reutilización desde otra IP", r)
    r = c.get("/api/v1/users/me", headers={"Authorization": "Bearer " + acc}); show("access token tras reutilización", r)
