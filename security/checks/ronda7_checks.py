"""Ronda 7: cola de trabajos, acciones generadas y NullByteGuard por HTTP.

    ./security/lab.sh 8901        # en otra terminal (SOLO 127.0.0.1)
    LAB_CREDS=$LAB_DIR/credentials.json .venv/bin/python security/checks/ronda7_checks.py 8901

Si hay un worker corriendo contra la BD del laboratorio, espera a que el trabajo
de Alice termine y comprueba la respuesta. Imprime OK/FALLO/INFO. No modifica
el proyecto.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid

import httpx

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8901
BASE = f"http://127.0.0.1:{PORT}"
PW = {e: d["password"] for e, d in json.load(open(os.environ["LAB_CREDS"])).items()}
WAIT_WORKER = os.environ.get("WAIT_WORKER", "0") == "1"
c = httpx.Client(base_url=BASE, timeout=30)
API = "/api/v1"
SEC_HEADERS = ("content-security-policy", "x-content-type-options", "x-request-id")
results: list[tuple[str, str]] = []


def check(label: str, ok: bool, detail: str = "", info: bool = False) -> None:
    status = "INFO" if info else ("OK" if ok else "FALLO")
    results.append((status, label))
    print(f"[{status}] {label} {('-> ' + detail) if detail else ''}", flush=True)


def brief(r: httpx.Response) -> str:
    return f"{r.status_code} {r.text[:200]!r}"


def login(email: str, **data) -> dict:
    r = c.post(f"{API}/auth/login", data={"username": email, "password": PW[email], **data})
    r.raise_for_status()
    return {"Authorization": "Bearer " + r.json()["access_token"]}


ADMIN = login("admin@example.com")
ALICE = login("alice@example.com")
BOB = login("bob@example.com")
ALICE_RO = login("alice@example.com", scope="read")

# --- Datos ---------------------------------------------------------------------
suffix = uuid.uuid4().hex[:6]
cat = c.post(f"{API}/categories", json={"name": f"c{suffix}", "slug": f"c-{suffix}"}, headers=ADMIN)
prod = c.post(
    f"{API}/products",
    json={"name": "P", "sku": f"S{suffix}", "price": "9.99", "category_id": cat.json()["id"]},
    headers=ADMIN,
)
order_body = {"product_id": prod.json()["id"], "quantity": 1, "contact_email": "a@example.com"}
o_alice = c.post(f"{API}/orders", json={**order_body, "internal_ref": "SECRET-REF"}, headers=ALICE)
o_bob = c.post(f"{API}/orders", json=order_body, headers=BOB)
check("preparación (categoría, producto, pedidos)", o_alice.status_code == o_bob.status_code == 201,
      f"{cat.status_code}/{prod.status_code}/{o_alice.status_code}/{o_bob.status_code}")
A, B = o_alice.json()["id"], o_bob.json()["id"]

# --- Acción en segundo plano: autorización y entrada -----------------------------
r = c.post(f"{API}/orders/{A}/export_invoice", json={}, headers=ALICE)
check("export_invoice propio -> 202 + Location + job_id", r.status_code == 202
      and r.headers.get("location", "").startswith("/api/v1/jobs/"), brief(r))
job_a = r.json()["job_id"]
r = c.post(f"{API}/orders/{A}/export_invoice", json={}, headers=BOB)
check("export_invoice sobre pedido ajeno -> 404 (BOLA)", r.status_code == 404, brief(r))
r = c.post(f"{API}/orders/{B}/export_invoice", json={"item_id": A}, headers=BOB)
check("item_id en el cuerpo rechazado (no suplanta el de la ruta)", r.status_code == 422, brief(r))
r = c.post(f"{API}/orders/{B}/export_invoice", json={"format": "x" * 11}, headers=BOB)
check("max_length del campo de entrada -> 422", r.status_code == 422, brief(r))
r = c.post(f"{API}/orders/{B}/export_invoice", json={"format": "a\u0000b"}, headers=BOB)
check("NUL dentro del JSON de la acción -> 422", r.status_code == 422, brief(r))
r = c.post(f"{API}/orders/{B}/export_invoice", json={}, headers=ALICE_RO)
check("token scope=read no puede lanzar acciones -> 403", r.status_code == 403, brief(r))
r = c.post(f"{API}/orders/{B}/export_invoice", json={})
check("acción sin token -> 401", r.status_code == 401, brief(r))

# --- Acción síncrona ---------------------------------------------------------------
r = c.post(f"{API}/orders/{A}/summary", headers=ALICE)
check("summary propio -> 200", r.status_code == 200, brief(r))
r = c.post(f"{API}/orders/{A}/summary", headers=BOB)
check("summary sobre pedido ajeno -> 404", r.status_code == 404, brief(r))

# --- Acción admin (process) ----------------------------------------------------------
r = c.post(f"{API}/products/reindex", headers=ALICE)
check("reindex (admin) como usuario -> 403", r.status_code == 403, brief(r))
r = c.post(f"{API}/products/reindex", headers=ADMIN)
check("reindex como admin -> 202", r.status_code == 202, brief(r))
job_admin = r.json().get("job_id")

# --- /jobs: aislamiento por dueño ------------------------------------------------
r = c.get(f"{API}/jobs/{job_a}", headers=BOB)
check("GET /jobs/{ajeno} -> 404", r.status_code == 404, brief(r))
r = c.post(f"{API}/jobs/{job_a}/cancel", headers=BOB)
check("cancelar trabajo ajeno -> 404", r.status_code == 404, brief(r))
r = c.get(f"{API}/jobs", headers=BOB)
ids = {j["id"] for j in r.json()["items"]}
check("listado de Bob no incluye trabajos de Alice ni del admin",
      job_a not in ids and job_admin not in ids, f"total={r.json()['total']}")
r = c.get(f"{API}/jobs/{job_admin}", headers=ALICE)
check("usuario no ve trabajos del admin", r.status_code == 404, brief(r))
r = c.get(f"{API}/jobs", headers=ADMIN)
check("admin ve todos los trabajos", job_a in {j["id"] for j in r.json()["items"]}, "")
r = c.get(f"{API}/jobs/{job_a}", headers=ALICE)
body = r.json()
leaked = {"payload", "owner_id", "locked_by", "locked_until", "priority"} & set(body)
check("JobRead no expone payload/owner_id/locked_by", not leaked, str(sorted(body)))
r = c.get(f"{API}/jobs", params={"status": "bogus"}, headers=ALICE)
check("filtro status inválido -> 422", r.status_code == 422, str(r.status_code))
r = c.get(f"{API}/jobs", params={"limit": 10_000}, headers=ALICE)
check("paginación acotada en /jobs", r.status_code == 422 or len(r.json()["items"]) <= 100,
      str(r.status_code))

# --- Cancelación --------------------------------------------------------------------
r = c.post(f"{API}/orders/{A}/export_invoice", json={}, headers=ALICE)
job_c = r.json()["job_id"]
r = c.post(f"{API}/jobs/{job_c}/cancel", headers=ALICE_RO)
check("cancelar con token scope=read -> 403", r.status_code == 403, brief(r))
r = c.post(f"{API}/jobs/{job_c}/cancel", headers=ALICE)
cancelled = r.status_code == 200 and r.json()["status"] == "cancelled"
check("cancelar trabajo propio en cola -> 200 cancelled", cancelled or r.status_code == 409,
      brief(r), info=not cancelled)
r = c.post(f"{API}/jobs/{job_c}/cancel", headers=ALICE)
check("cancelar dos veces -> 409 job_not_cancellable",
      r.status_code == 409 and r.json().get("code") == "job_not_cancellable", brief(r))

# --- Rate limit por acción (10/minute) ---------------------------------------------
codes = [c.post(f"{API}/orders/{B}/export_invoice", json={}, headers=BOB).status_code
         for _ in range(11)]
check("rate limit de la acción (10/minute) -> 429", 429 in codes, str(codes))
r429 = c.post(f"{API}/orders/{B}/export_invoice", json={}, headers=BOB)
check("429 con Retry-After y code", r429.status_code == 429 and "retry-after" in r429.headers
      and r429.json().get("code") == "rate_limited", brief(r429))

# --- NullByteGuardMiddleware -------------------------------------------------------
for label, path in [
    ("NUL codificado en query", f"{API}/products?q=%00"),
    ("NUL en parámetro de filtro", f"{API}/products?status=%00draft"),
    ("NUL en la ruta", f"{API}/products/%00"),
    ("NUL en ruta de /jobs", f"{API}/jobs/%00"),
]:
    r = c.get(path, headers=ALICE)
    hdr = all(h in r.headers for h in SEC_HEADERS)
    check(f"{label} -> 422 con cabeceras de seguridad", r.status_code == 422 and hdr,
          f"{r.status_code} hdr={hdr} {r.text[:80]!r}")
r = c.get(f"{API}/products?q=%2500", headers=ALICE)
check("'%2500' (literal %00) no es NUL -> 200", r.status_code == 200, str(r.status_code))
r = c.get(f"{API}/products?q=%00", headers={"Host": "evil.example"})
check("Host no permitido prevalece sobre NUL (400 invalid_host)", r.status_code == 400, brief(r))
r = c.get(f"{API}/products/%00", headers=ALICE)
check("detalle del 422 de ruta dice loc=query (cosmético)", True,
      r.text[:120], info=True)

# --- Resultado del trabajo (si hay worker) -------------------------------------------
if WAIT_WORKER:
    deadline = time.time() + 30
    st = None
    while time.time() < deadline:
        st = c.get(f"{API}/jobs/{job_a}", headers=ALICE).json()
        if st["status"] in {"succeeded", "failed"}:
            break
        time.sleep(1)
    check("worker ejecuta export_invoice -> succeeded", st and st["status"] == "succeeded",
          json.dumps(st)[:200])
    st = c.get(f"{API}/jobs/{job_admin}", headers=ADMIN).json()
    deadline = time.time() + 30
    while st["status"] not in {"succeeded", "failed"} and time.time() < deadline:
        time.sleep(1)
        st = c.get(f"{API}/jobs/{job_admin}", headers=ADMIN).json()
    check("worker ejecuta reindex (executor=process)", st["status"] == "succeeded",
          json.dumps(st)[:200])

fails = sum(1 for s, _ in results if s == "FALLO")
print(f"\nResumen: {sum(1 for s, _ in results if s == 'OK')} OK, {fails} FALLO, "
      f"{sum(1 for s, _ in results if s == 'INFO')} INFO")
