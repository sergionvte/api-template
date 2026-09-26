"""Ronda 5: re-verificación de extremo a extremo de los controles críticos y de
las sospechas surgidas del grafo de graphify (borrado de usuarios con filas
propias, FK con borrado físico, campos inmutables, email en mayúsculas, último
admin inactivo...).

    ./security/lab.sh 8901        # en otra terminal (SOLO 127.0.0.1)
    LAB_CREDS=$LAB_DIR/credentials.json .venv/bin/python security/checks/ronda5_checks.py 8901

Imprime una línea OK/FALLO/INFO por comprobación. No modifica el proyecto.
"""
from __future__ import annotations

import json
import os
import sys
import uuid

import httpx

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8901
BASE = f"http://127.0.0.1:{PORT}"
PW = {e: d["password"] for e, d in json.load(open(os.environ["LAB_CREDS"])).items()}
c = httpx.Client(base_url=BASE, timeout=30)
API = "/api/v1"
results: list[tuple[str, str, str]] = []

SEC_HEADERS = ("content-security-policy", "x-content-type-options", "x-frame-options", "x-request-id")


def check(label: str, ok: bool, detail: str = "", info: bool = False) -> None:
    status = "INFO" if info else ("OK" if ok else "FALLO")
    results.append((status, label, detail))
    print(f"[{status}] {label} {('-> ' + detail) if detail else ''}", flush=True)


def brief(r: httpx.Response) -> str:
    return f"{r.status_code} {r.text[:160]!r}"


def login(email: str, pw: str, **data) -> httpx.Response:
    return c.post(f"{API}/auth/login", data={"username": email, "password": pw, **data})


def bearer(r: httpx.Response) -> dict:
    return {"Authorization": "Bearer " + r.json()["access_token"]}


# --- Autenticación ------------------------------------------------------------
ra = login("admin@example.com", PW["admin@example.com"])
check("login admin", ra.status_code == 200, str(ra.status_code))
ADMIN = bearer(ra)
rl = login("alice@example.com", PW["alice@example.com"])
ALICE = bearer(rl)
alice_refresh = rl.json()["refresh_token"]
rb = login("bob@example.com", PW["bob@example.com"])
BOB = bearer(rb)

r1 = login("alice@example.com", "wrong-password-xxxx")
r2 = login("nobody@example.com", "wrong-password-xxxx")
check("login fallido uniforme (existe / no existe)", r1.status_code == r2.status_code == 401
      and r1.json() == r2.json(), f"{brief(r1)} | {brief(r2)}")

r = login("ALICE@Example.COM", PW["alice@example.com"])
check("login con email en mayúsculas funciona (normalización)", r.status_code == 200, brief(r))

r = c.get(f"{API}/users/me", headers={"Authorization": "Bearer " + alice_refresh})
check("refresh token no sirve como access", r.status_code == 401, brief(r))

r = c.post(f"{API}/auth/refresh", json={"refresh_token": alice_refresh})
check("rotación de refresh", r.status_code == 200, str(r.status_code))
new_refresh = r.json().get("refresh_token") if r.status_code == 200 else None
r = c.post(f"{API}/auth/refresh", json={"refresh_token": alice_refresh})
check("reutilización del refresh antiguo (misma IP, dentro de la gracia) -> 409 sin tokens",
      r.status_code in (401, 409) and "access_token" not in r.text, brief(r))

rs = login("bob@example.com", PW["bob@example.com"], scope="read")
if rs.status_code == 200:
    r = c.patch(f"{API}/users/me", json={"full_name": "x"}, headers=bearer(rs))
    check("token con scope read no escribe", r.status_code == 403, brief(r))
else:
    check("login con scope=read", False, brief(rs), info=True)

# --- Autorización por objeto (orders, owned) -------------------------------------
r = c.post(f"{API}/categories", json={"name": "R5 cat", "slug": "r5-cat"}, headers=ADMIN)
cat = r.json()["id"]
r = c.post(f"{API}/products", json={"name": "P", "sku": "R5-1", "price": "1.00", "category_id": cat},
           headers=ADMIN)
prod = r.json()["id"]
order_body = {"product_id": prod, "quantity": 1, "contact_email": "alice@example.com",
              "internal_ref": "secret-ref"}
r = c.post(f"{API}/orders", json=order_body, headers=ALICE)
check("alice crea pedido", r.status_code == 201, brief(r))
order = r.json()["id"]
check("write_only no se devuelve", "internal_ref" not in r.text and "secret-ref" not in r.text)
for verb, fn in (("GET", c.get), ("DELETE", c.delete)):
    r = fn(f"{API}/orders/{order}", headers=BOB)
    check(f"bob {verb} pedido de alice -> 404", r.status_code == 404, brief(r))
r = c.patch(f"{API}/orders/{order}", json={"quantity": 2}, headers=BOB)
check("bob PATCH pedido de alice -> 404", r.status_code == 404, brief(r))
r = c.get(f"{API}/orders", headers=BOB)
check("listado de bob no incluye el pedido", order not in r.text, brief(r))
r = c.get(f"{API}/orders?product_id={prod}", headers=BOB)
check("filtro de bob por product_id no incluye el pedido", order not in r.text, brief(r))
r = c.get(f"{API}/orders/{order}", headers=ADMIN)
check("admin ve el pedido de alice", r.status_code == 200, str(r.status_code))

# Asignación masiva
r = c.patch(f"{API}/orders/{order}", json={"owner_id": str(uuid.uuid4())}, headers=ALICE)
check("PATCH owner_id -> 422", r.status_code == 422, brief(r))
r = c.patch(f"{API}/orders/{order}", json={"id": str(uuid.uuid4())}, headers=ALICE)
check("PATCH id -> 422", r.status_code == 422, brief(r))
r = c.patch(f"{API}/orders/{order}", json={"created_at": "2000-01-01T00:00:00Z"}, headers=ALICE)
check("PATCH created_at -> 422", r.status_code == 422, brief(r))
r = c.patch(f"{API}/categories/{cat}", json={"slug": "otro"}, headers=ADMIN)
check("campo immutable (slug) no se modifica por PATCH", r.status_code == 422, brief(r))
r = c.patch(f"{API}/orders/{order}", json={"product_id": None}, headers=ALICE)
check("PATCH FK obligatoria a null -> 422", r.status_code == 422, brief(r))
r = c.patch(f"{API}/users/me", json={"role": "admin"}, headers=BOB)
check("usuario no se autoasciende (role en /users/me)", r.status_code == 422, brief(r))
r = c.patch(f"{API}/products/{prod}", json={"deleted_at": "2000-01-01T00:00:00Z"}, headers=ADMIN)
check("deleted_at no es asignable", r.status_code == 422, brief(r))

# FK hacia fila borrada lógicamente
r = c.post(f"{API}/products", json={"name": "P2", "sku": "R5-2", "price": "1.00", "category_id": cat},
           headers=ADMIN)
prod2 = r.json()["id"]
c.delete(f"{API}/products/{prod2}", headers=ADMIN)
r = c.post(f"{API}/orders", json={**order_body, "product_id": prod2}, headers=BOB)
check("pedido a producto borrado lógicamente -> 422", r.status_code == 422, brief(r))
r = c.patch(f"{API}/orders/{order}", json={"product_id": prod2}, headers=ALICE)
check("PATCH a producto borrado lógicamente -> 422", r.status_code == 422, brief(r))
r = c.get(f"{API}/products/{prod2}", headers=ADMIN)
check("producto borrado lógicamente no se lee (ni admin)", r.status_code == 404, brief(r))

# Borrado físico de una fila referenciada (categoría con productos)
r = c.delete(f"{API}/categories/{cat}", headers=ADMIN)
check("DELETE categoría con productos -> 409 (no 500, no huérfanos)", r.status_code == 409, brief(r))

# --- Administración de usuarios ---------------------------------------------------
me = c.get(f"{API}/users/me", headers=ADMIN).json()
r = c.patch(f"{API}/users/{me['id']}", json={"role": "user"}, headers=ADMIN)
check("último admin no se degrada", r.status_code == 409, brief(r))
r = c.patch(f"{API}/users/{me['id']}", json={"is_active": False}, headers=ADMIN)
check("último admin no se desactiva", r.status_code == 409, brief(r))
r = c.delete(f"{API}/users/{me['id']}", headers=ADMIN)
check("admin no se borra a sí mismo", r.status_code == 409, brief(r))
r = c.get(f"{API}/users", headers=BOB)
check("usuario normal no lista usuarios", r.status_code == 403, brief(r))

# Nuevo admin inactivo: degradar a un admin YA inactivo con un solo admin activo
r = c.post(f"{API}/users", json={"email": "r5-admin2@example.com", "password": "lab-" + uuid.uuid4().hex,
                                  "role": "admin"}, headers=ADMIN)
admin2 = r.json()["id"]
r = c.patch(f"{API}/users/{admin2}", json={"is_active": False}, headers=ADMIN)
check("desactivar segundo admin (quedan 2 activos antes)", r.status_code == 200, brief(r))
r = c.patch(f"{API}/users/{admin2}", json={"role": "user"}, headers=ADMIN)
check("degradar admin YA inactivo con 1 admin activo (no debería bloquearse)",
      r.status_code == 200, brief(r), info=r.status_code != 200)

# Borrar a alice: su pedido (owned, CASCADE) y sus sesiones
alice_id = c.get(f"{API}/users/me", headers=ALICE).json()["id"]
r = c.delete(f"{API}/users/{alice_id}", headers=ADMIN)
check("admin borra a alice (con pedidos)", r.status_code == 204, brief(r))
r = c.get(f"{API}/orders/{order}", headers=ADMIN)
check("pedido de alice eliminado en cascada", r.status_code == 404, brief(r))
r = c.get(f"{API}/users/me", headers=ALICE)
check("access token de usuario borrado -> 401", r.status_code == 401, brief(r))
if new_refresh:
    r = c.post(f"{API}/auth/refresh", json={"refresh_token": new_refresh})
    check("refresh de usuario borrado -> 401", r.status_code == 401, brief(r))

# --- Errores y cabeceras ------------------------------------------------------
for label, req in (
    ("404 ruta", lambda: c.get(f"{API}/nope", headers=BOB)),
    ("405", lambda: c.put(f"{API}/users/me", headers=BOB)),
    ("UUID inválido", lambda: c.get(f"{API}/orders/not-a-uuid", headers=BOB)),
    ("JSON malformado", lambda: c.patch(f"{API}/users/me", content=b"{bad",
                                        headers={**BOB, "Content-Type": "application/json"})),
    ("sin token", lambda: c.get(f"{API}/users/me")),
):
    r = req()
    missing = [h for h in SEC_HEADERS if h not in r.headers]
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    check(f"{label}: {r.status_code} con code y cabeceras", not missing and "code" in body
          and "Traceback" not in r.text, f"{brief(r)} faltan={missing}")
r = c.get("/health/live", headers={"Host": "evil.example"})
check("Host no permitido -> 400", r.status_code == 400, brief(r))
for path in ("/docs", "/redoc", "/openapi.json", f"{API}/openapi.json"):
    r = c.get(path)
    check(f"{path} oculto en producción", r.status_code == 404, str(r.status_code))
r = c.get("/health/ready")
check("/health/ready sin detalles internos", set(r.json()) <= {"status"}, brief(r))
check("sin cabecera Server", "server" not in r.headers)

# --- Rate limit de login (al final: consume el cupo de la IP) -------------------
codes = [login("bob@example.com", f"wrong-{i}-xxxxxxxx").status_code for i in range(12)]
r = login("bob@example.com", "wrong-final-xxxxxxxx")
check("rate limit de login -> 429 con Retry-After", 429 in codes + [r.status_code]
      and "retry-after" in r.headers, f"{codes} {r.status_code}")
check("429 con cabeceras de seguridad", all(h in r.headers for h in SEC_HEADERS))

fails = [x for x in results if x[0] == "FALLO"]
print(f"\nResumen: {sum(x[0] == 'OK' for x in results)} OK, {len(fails)} FALLO, "
      f"{sum(x[0] == 'INFO' for x in results)} INFO")
