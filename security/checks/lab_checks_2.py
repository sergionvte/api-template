"""Verificaciones dirigidas (ronda 1, segunda pasada) sobre un laboratorio NUEVO.

    ./security/lab.sh 8901
    sqlite3 $LAB_DIR/lab.db "update users set email=replace(email,'@lab.test','@example.com')"
    LAB_CREDS=$LAB_DIR/credentials.json .venv/bin/python security/checks/lab_checks_2.py 8901

1. Refresh concurrente: ¿se revoca la familia cuando dos peticiones usan el mismo token?
2. Bloqueo de cuenta provocado por un tercero sobre un usuario registrado.
3. Enumeración de emails en /register.
4. Respuesta 500: cabeceras de seguridad y X-Request-ID.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

import httpx

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8901
BASE = f"http://127.0.0.1:{PORT}"
CREDS = json.load(open(os.environ["LAB_CREDS"]))
PW = {e.replace("@lab.test", "@example.com"): d["password"] for e, d in CREDS.items()}
c = httpx.Client(base_url=BASE, timeout=30)


def login(email: str, password: str) -> httpx.Response:
    return c.post("/api/v1/auth/login", data={"username": email, "password": password})


def show(label: str, r: httpx.Response) -> None:
    print(f"{label}: {r.request.method} {r.request.url.path} -> {r.status_code} {r.text[:120]!r}")


# --- 1. Carrera en /refresh -------------------------------------------------------
r = login("bob@example.com", PW["bob@example.com"])
token = r.json()["refresh_token"]


async def race() -> list[httpx.Response]:
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as ac:
        return await asyncio.gather(
            *(ac.post("/api/v1/auth/refresh", json={"refresh_token": token}) for _ in range(5))
        )


responses = asyncio.run(race())
print("carrera /refresh (5 peticiones con el mismo token):", sorted(x.status_code for x in responses))
winners = [x for x in responses if x.status_code == 200]
if winners:
    new_refresh = winners[0].json()["refresh_token"]
    r = c.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
    show("token del ganador tras la carrera (debería ser 401 si se revocó la familia)", r)
fivehundreds = [x for x in responses if x.status_code == 500]
if fivehundreds:
    h = fivehundreds[0].headers
    print("cabeceras de la respuesta 500:", dict(h))

# --- 2. Bloqueo provocado por un tercero ---------------------------------------------
victim, victim_pw = "victima@example.com", "lab-" + uuid.uuid4().hex
r = c.post("/api/v1/auth/register", json={"email": victim, "password": victim_pw})
show("registro víctima", r)
r = login(victim, victim_pw)
show("login legítimo antes del ataque", r)
for i in range(5):
    login(victim, f"intento-erroneo-{i}")
r = login(victim, victim_pw)
show("login legítimo tras 5 fallos de un tercero", r)

# --- 3. Enumeración en /register ------------------------------------------------------
r = c.post("/api/v1/auth/register", json={"email": "alice@example.com", "password": "lab-" + uuid.uuid4().hex})
show("registro con email existente", r)
r = c.post("/api/v1/auth/register", json={"email": f"nuevo-{uuid.uuid4().hex[:6]}@example.com",
                                          "password": "lab-" + uuid.uuid4().hex})
show("registro con email nuevo", r)
