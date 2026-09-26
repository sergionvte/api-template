"""Ronda 7: comprobaciones contra el stack de docker compose (PostgreSQL + worker).

Requiere un despliegue local de compose (p. ej. `-p apisec`) con los recursos
de examples/cursos.yaml y usuarios de prueba en un JSON (DOCKER_CREDS).

    DOCKER_CREDS=.../docker_creds.json .venv/bin/python security/checks/ronda7_docker_checks.py

Solo habla con http://127.0.0.1:8000. Imprime OK/FALLO/INFO.
"""

from __future__ import annotations

import json
import os
import time
import uuid

import httpx

PW = {e: d["password"] for e, d in json.load(open(os.environ["DOCKER_CREDS"])).items()}
c = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30)
API = "/api/v1"
results: list[str] = []


def check(label: str, ok: bool, detail: str = "", info: bool = False) -> None:
    status = "INFO" if info else ("OK" if ok else "FALLO")
    results.append(status)
    print(f"[{status}] {label} {('-> ' + detail) if detail else ''}", flush=True)


def login(email: str) -> dict:
    r = c.post(f"{API}/auth/login", data={"username": email, "password": PW[email]})
    r.raise_for_status()
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def wait(job_url: str, headers: dict, timeout: float = 30) -> dict:
    deadline = time.time() + timeout
    while True:
        st = c.get(job_url, headers=headers).json()
        if st["status"] in {"succeeded", "failed", "cancelled"} or time.time() > deadline:
            return st
        time.sleep(1)


ADMIN, ALICE, BOB = (login(e) for e in ("admin@example.com", "alice@example.com",
                                          "bob@example.com"))
s = uuid.uuid4().hex[:6]
cat = c.post(f"{API}/categories", json={"name": f"c{s}", "slug": f"c-{s}"}, headers=ADMIN)
check("crear categoría (admin)", cat.status_code == 201, f"{cat.status_code} {cat.text[:120]}")
course_body = {"title": f"Curso {s}", "price": "10.00", "duration_hours": 5,
               "instructor_email": "profe@example.com", "category_id": cat.json().get("id")}
course = c.post(f"{API}/courses", json=course_body, headers=ADMIN)
if course.status_code != 201:
    print("cuerpo de curso no válido:", course.text[:300])
course_id = course.json().get("id")

enr = c.post(f"{API}/enrollments", json={"course_id": course_id}, headers=ALICE)
check("inscripción de Alice", enr.status_code == 201, f"{enr.status_code} {enr.text[:160]}")
E = enr.json().get("id")

r = c.post(f"{API}/enrollments/{E}/certificate", json={}, headers=ALICE)
check("certificate (background) -> 202", r.status_code == 202, r.text[:120])
st = wait(r.json()["status_url"], ALICE)
check("worker (PostgreSQL) ejecuta certificate -> succeeded", st["status"] == "succeeded",
      json.dumps(st)[:160])
r2 = c.post(f"{API}/enrollments/{E}/certificate", json={}, headers=BOB)
check("certificate sobre inscripción ajena -> 404", r2.status_code == 404, str(r2.status_code))
r = c.get(r.json()["status_url"], headers=BOB)
check("Bob no ve el trabajo de Alice -> 404", r.status_code == 404, str(r.status_code))

r = c.post(f"{API}/courses/reindex", headers=ADMIN)
check("reindex (executor=process) -> 202", r.status_code == 202, r.text[:120])
st = wait(r.json()["status_url"], ADMIN)
check("worker ejecuta la tarea process en Linux (fork, py3.13)", st["status"] == "succeeded",
      json.dumps(st)[:160])

for label, path in [("query", f"{API}/courses?q=%00"), ("ruta", f"{API}/courses/%00"),
                    ("jobs", f"{API}/jobs?name=%00")]:
    r = c.get(path, headers=ALICE)
    check(f"NUL en {label} con PostgreSQL -> 422 (no 500)", r.status_code == 422,
          f"{r.status_code} {r.text[:80]!r}")
r = c.get(f"{API}/jobs", params={"name": "x" * 101}, headers=ALICE)
check("/jobs?name > 100 -> 422", r.status_code == 422, str(r.status_code))

print(f"\nResumen: {results.count('OK')} OK, {results.count('FALLO')} FALLO, "
      f"{results.count('INFO')} INFO")
