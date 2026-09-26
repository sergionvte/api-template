"""Verificación de controles de seguridad contra el laboratorio local (ronda 1).

Uso:
    ./security/lab.sh 8901            # en otra terminal
    LAB_CREDS=$LAB_DIR/credentials.json .venv/bin/python security/checks/lab_checks.py 8901

Solo habla con 127.0.0.1. Respeta los límites de login (10/min, 50/h por IP)
intercalando esperas, así que tarda varios minutos. No imprime contraseñas.
Cada comprobación imprime OK / FALLO / INFO con la evidencia mínima.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import statistics
import sys
import time
import uuid

import httpx

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8901
BASE = f"http://127.0.0.1:{PORT}"
API = f"{BASE}/api/v1"
CREDS = json.load(open(os.environ["LAB_CREDS"]))
# El lab crea usuarios @lab.test, que EmailStr rechaza al serializar (500). Antes de
# ejecutar: sqlite3 $LAB_DIR/lab.db "update users set email=replace(email,'@lab.test','@example.com')"
PW = {email.replace("@lab.test", "@example.com"): d["password"] for email, d in CREDS.items()}

client = httpx.Client(base_url=BASE, timeout=30)
results: list[tuple[str, str, str]] = []
_login_times: list[float] = []


def record(status: str, name: str, evidence: str = "") -> None:
    results.append((status, name, evidence))
    print(f"[{status:5}] {name}" + (f"  -> {evidence}" if evidence else ""), flush=True)


def check(cond: bool, name: str, evidence: str = "") -> None:
    record("OK" if cond else "FALLO", name, evidence)


def short(r: httpx.Response, n: int = 160) -> str:
    return f"{r.request.method} {r.request.url.path} -> {r.status_code} {r.text[:n]!r}"


def login_budget() -> None:
    """Mantiene <= 5 logins por ventana de 60 s (el límite es 10/min con ventana deslizante)."""
    now = time.time()
    recent = [t for t in _login_times if now - t < 62]
    if len(recent) >= 5:
        wait = 62 - (now - recent[0])
        print(f"        (esperando {wait:.0f}s por el límite de login)", flush=True)
        time.sleep(max(wait, 0))
    _login_times.append(time.time())


def login(email: str, password: str, scope: str | None = None, budget: bool = True) -> httpx.Response:
    if budget:
        login_budget()
    data = {"username": email, "password": password}
    if scope:
        data["scope"] = scope
    return client.post("/api/v1/auth/login", data=data)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def b64(obj: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


# ---------------------------------------------------------------------------
def main() -> None:
    # --- 0. Superficie en producción ----------------------------------------
    for path in ("/docs", "/redoc", "/openapi.json"):
        r = client.get(path)
        check(r.status_code == 404, f"{path} deshabilitado en producción", short(r, 60))
    r = client.get("/health/live")
    need = [
        "x-content-type-options", "x-frame-options", "content-security-policy",
        "referrer-policy", "cache-control", "x-request-id",
    ]
    missing = [h for h in need if h not in r.headers]
    check(not missing, "cabeceras de seguridad presentes", f"faltan={missing}")
    check("server" not in r.headers, "sin cabecera Server")
    check("strict-transport-security" not in r.headers, "HSTS no se envía sobre HTTP (esperado)")
    r = client.get("/health/live", headers={"Host": "evil.example"})
    check(r.status_code == 400, "Host no permitido rechazado (TrustedHost)", short(r, 40))
    r = client.get("/health/live", headers={"X-Request-ID": "abc<script>{}\t%0a;x"})
    check(r.headers.get("x-request-id", "").isalnum(), "X-Request-ID malicioso se sustituye")

    # --- 1. Tokens base -------------------------------------------------------
    tok = {}
    ref = {}
    for email in ("admin@example.com", "alice@example.com", "bob@example.com"):
        r = login(email, PW[email])
        check(r.status_code == 200, f"login {email}", str(r.status_code))
        tok[email] = r.json()["access_token"]
        ref[email] = r.json()["refresh_token"]
    admin, alice, bob = (bearer(tok[e]) for e in ("admin@example.com", "alice@example.com", "bob@example.com"))
    alice_id = client.get("/api/v1/users/me", headers=alice).json()["id"]
    bob_id = client.get("/api/v1/users/me", headers=bob).json()["id"]
    admin_id = client.get("/api/v1/users/me", headers=admin).json()["id"]

    # --- 2. Validación de JWT -------------------------------------------------
    hdr, payload, sig = tok["alice@example.com"].split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    header = json.loads(base64.urlsafe_b64decode(hdr + "=="))
    record("INFO", "claims del access token", ",".join(sorted(claims)) + f" typ={claims.get('typ')}")
    forged = f"{hdr}.{b64({**claims, 'role': 'admin', 'scope': 'admin read write'})}.{sig}"
    r = client.get("/api/v1/users", headers=bearer(forged))
    check(r.status_code == 401, "payload modificado (role/scope admin) rechazado", short(r, 60))
    none_tok = f"{b64({'alg': 'none', 'typ': 'JWT', 'kid': header['kid']})}.{payload}."
    r = client.get("/api/v1/users/me", headers=bearer(none_tok))
    check(r.status_code == 401, "alg=none rechazado", short(r, 60))
    for kid in (["x"], {"a": 1}, 123, "../../etc/passwd"):
        t = f"{b64({**header, 'kid': kid})}.{payload}.{sig}"
        r = client.get("/api/v1/users/me", headers=bearer(t))
        check(r.status_code == 401, f"kid={kid!r} rechazado sin 500", short(r, 60))
    r = client.get("/api/v1/users/me", headers=bearer("x" * 5000))
    check(r.status_code == 401, "token > 4096 bytes rechazado", short(r, 40))
    r = client.get("/api/v1/categories", headers=bearer("garbage"))
    check(r.status_code == 401, "token inválido rechazado incluso en endpoint público", short(r, 40))
    r = client.get("/api/v1/users/me", headers=bearer(ref["alice@example.com"]))
    check(r.status_code == 401, "refresh token no sirve como access token", short(r, 40))

    # --- 3. Autorización por función (BFLA) -----------------------------------
    r = client.get("/api/v1/users", headers=alice)
    check(r.status_code == 403, "usuario normal no lista usuarios", short(r, 60))
    r = client.patch(f"/api/v1/users/{alice_id}", json={"role": "admin"}, headers=alice)
    check(r.status_code == 403, "usuario normal no se autopromociona vía /users/{id}", short(r, 60))
    r = client.patch("/api/v1/users/me", json={"role": "admin"}, headers=alice)
    check(r.status_code == 422, "PATCH /users/me no acepta role (mass assignment)", short(r, 80))
    r = client.post("/api/v1/categories", json={"name": "x", "slug": "x"}, headers=alice)
    check(r.status_code == 403, "usuario normal no crea categorías", short(r, 60))
    r = client.post("/api/v1/categories", json={"name": "x", "slug": "x"})
    check(r.status_code == 401, "anónimo no crea categorías", short(r, 60))

    # --- 4. Datos de catálogo (admin) ------------------------------------------
    r = client.post("/api/v1/categories", json={"name": "Libros", "slug": "libros"}, headers=admin)
    check(r.status_code == 201, "admin crea categoría", short(r, 80))
    cat_id = r.json()["id"]
    prod = {"name": "Libro", "sku": "SKU-1", "price": "10.00", "category_id": cat_id}
    r = client.post("/api/v1/products", json=prod, headers=admin)
    check(r.status_code == 201, "admin crea producto", short(r, 80))
    prod_id = r.json()["id"]
    r = client.post("/api/v1/products", json={**prod, "sku": "SKU-2"}, headers=admin)
    prod2_id = r.json()["id"]
    r = client.post("/api/v1/products", json={**prod, "sku": "SKU-3", "price": "-1"}, headers=admin)
    check(r.status_code == 422, "precio negativo rechazado", short(r, 80))
    r = client.post("/api/v1/products", json={**prod, "sku": "SKU-4", "price": "1.234"}, headers=admin)
    check(r.status_code == 422, "decimal con más decimales de los permitidos rechazado", short(r, 60))
    r = client.post("/api/v1/products", json={**prod, "sku": "SKU-5", "rating": "NaN"}, headers=admin)
    check(r.status_code == 422, "float NaN rechazado", short(r, 60))
    r = client.post("/api/v1/products", json={**prod, "sku": "SKU-6", "category_id": str(uuid.uuid4())}, headers=admin)
    check(r.status_code == 422, "FK a categoría inexistente -> 422 (no 409/500)", short(r, 100))
    # Entero fuera del rango de la BD (campo int sin `le`)
    r = client.post("/api/v1/products", json={**prod, "sku": "SKU-7", "stock": 2**63}, headers=admin)
    record("OK" if r.status_code in (409, 422) else "FALLO",
           "int sin límite superior (stock=2**63) no provoca 500", short(r, 120))
    if r.status_code >= 500:
        missing = [h for h in ("content-security-policy", "x-content-type-options", "x-request-id") if h not in r.headers]
        record("INFO", "cabeceras ausentes en la respuesta 500", f"faltan={missing}")
    raw ='{"name":"n","sku":"SKU-8","price":"1","category_id":"%s","attributes":%s}' % (
        cat_id, "[" * 100000 + "]" * 100000)
    r = client.post("/api/v1/products", content=raw, headers={**admin, "Content-Type": "application/json"})
    check(r.status_code in (400, 422), "JSON profundamente anidado no provoca 500", short(r, 80))
    # soft delete del producto 2
    r = client.delete(f"/api/v1/products/{prod2_id}", headers=admin)
    check(r.status_code == 204, "admin borra (soft) producto 2", short(r, 40))
    r = client.get(f"/api/v1/products/{prod2_id}")
    check(r.status_code == 404, "producto borrado lógicamente no visible", short(r, 40))

    # --- 5. Autorización por objeto (BOLA) en orders ---------------------------
    order = {"product_id": prod_id, "quantity": 2, "contact_email": "alice@example.com",
             "internal_ref": "SECRETO-INTERNO"}
    r = client.post("/api/v1/orders", json=order, headers=alice)
    check(r.status_code == 201, "alice crea pedido", short(r, 60))
    order_id = r.json()["id"]
    check("internal_ref" not in r.json(), "campo write_only no se devuelve")
    check(r.json()["owner_id"] == alice_id, "owner_id asignado por el servidor")
    r = client.post("/api/v1/orders", json={**order, "owner_id": bob_id}, headers=alice)
    check(r.status_code == 422, "no se puede fijar owner_id (mass assignment)", short(r, 80))
    r = client.get(f"/api/v1/orders/{order_id}", headers=bob)
    check(r.status_code == 404, "bob no lee el pedido de alice (404)", short(r, 60))
    r = client.patch(f"/api/v1/orders/{order_id}", json={"quantity": 99}, headers=bob)
    check(r.status_code == 404, "bob no modifica el pedido de alice", short(r, 60))
    r = client.delete(f"/api/v1/orders/{order_id}", headers=bob)
    check(r.status_code == 404, "bob no borra el pedido de alice", short(r, 60))
    r = client.get("/api/v1/orders", params={"product_id": prod_id}, headers=bob)
    check(r.status_code == 200 and r.json()["total"] == 0, "listado de bob no incluye pedidos ajenos",
          short(r, 80))
    r = client.get(f"/api/v1/orders/{order_id}", headers=admin)
    check(r.status_code == 200, "admin ve el pedido de alice", short(r, 40))
    r = client.patch(f"/api/v1/orders/{order_id}", json={"owner_id": bob_id}, headers=alice)
    check(r.status_code == 422, "PATCH no permite cambiar owner_id", short(r, 60))
    r = client.patch(f"/api/v1/orders/{order_id}", json={"quantity": None}, headers=alice)
    check(r.status_code == 422, "PATCH con null en campo obligatorio rechazado", short(r, 80))
    r = client.post("/api/v1/orders", json={**order, "product_id": prod2_id}, headers=alice)
    check(r.status_code == 422, "no se puede referenciar un producto borrado lógicamente", short(r, 100))
    r = client.post("/api/v1/orders", json={**order, "delivery_at": "2026-01-01T10:00:00"}, headers=alice)
    check(r.status_code == 422, "datetime sin zona horaria rechazado", short(r, 80))
    r = client.post("/api/v1/orders", json={**order, "quantity": 0}, headers=alice)
    check(r.status_code == 422 and "input" not in r.text, "422 no refleja la entrada", short(r, 120))

    # --- 6. Scopes -------------------------------------------------------------
    r = login("alice@example.com", PW["alice@example.com"], scope="read")
    ro = bearer(r.json()["access_token"])
    check(r.json()["scope"] == "read", "token de solo lectura emitido", r.json()["scope"])
    r = client.post("/api/v1/orders", json=order, headers=ro)
    check(r.status_code == 403, "token read no puede escribir", short(r, 60))
    r = client.get("/api/v1/orders", headers=ro)
    check(r.status_code == 200, "token read puede leer", short(r, 30))
    r = login("alice@example.com", PW["alice@example.com"], scope="admin")
    check(r.status_code == 400, "usuario no obtiene scope admin", short(r, 60))

    # --- 7. Paginación, orden, búsqueda ----------------------------------------
    for params, desc in (
        ({"limit": 101}, "limit > PAGE_SIZE_MAX"),
        ({"limit": 0}, "limit = 0"),
        ({"offset": 10001}, "offset > MAX_OFFSET"),
        ({"order_by": "hashed_password"}, "order_by fuera de lista blanca"),
        ({"q": "x" * 101}, "q > 100 caracteres"),
    ):
        r = client.get("/api/v1/products", params=params)
        check(r.status_code == 422, f"{desc} rechazado", short(r, 50))
    r = client.get("/api/v1/products", params={"q": "%"})
    check(r.status_code == 200 and r.json()["total"] == 0, "comodín LIKE '%' escapado", short(r, 60))
    r = client.get("/api/v1/products", params={"q": "' OR 1=1 --"})
    check(r.status_code == 200 and r.json()["total"] == 0, "búsqueda con SQL no inyecta", short(r, 60))

    # --- 8. Tamaño del cuerpo --------------------------------------------------
    big = b'{"name":"' + b"a" * (1_100_000) + b'"}'
    r = client.patch("/api/v1/users/me", content=big, headers={**alice, "Content-Type": "application/json"})
    check(r.status_code == 413, "cuerpo > 1 MiB rechazado (Content-Length)", short(r, 50))

    def gen():
        for _ in range(20):
            yield b"a" * 100_000

    r = client.patch("/api/v1/users/me", content=gen(), headers={**alice, "Content-Type": "application/json"})
    check(r.status_code == 413, "cuerpo > 1 MiB rechazado (chunked)", short(r, 50))
    r = client.patch("/api/v1/users/me", content=b'{"full_name": ', headers={**alice, "Content-Type": "application/json"})
    check(r.status_code == 422, "JSON malformado -> 422", short(r, 80))
    r = client.patch("/api/v1/users/me", content=b'{"full_name":"x"}', headers={**alice, "Content-Type": "text/plain"})
    check(r.status_code == 422, "JSON sin Content-Type JSON rechazado", short(r, 60))

    # --- 9. Errores ------------------------------------------------------------
    r = client.get("/api/v1/orders/not-a-uuid", headers=alice)
    check(r.status_code == 422, "ID no UUID -> 422", short(r, 80))
    r = client.get("/api/v1/nope")
    check(r.status_code == 404 and "Traceback" not in r.text, "404 genérico", short(r, 60))
    r = client.request("PUT", "/api/v1/orders", headers=alice)
    check(r.status_code == 405, "método no permitido -> 405", short(r, 60))

    # --- 10. Refresh: rotación, reutilización, carrera, logout ------------------
    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": ref["bob@example.com"]})
    check(r1.status_code == 200, "refresh rota el token", short(r1, 40))
    new_ref = r1.json()["refresh_token"]
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": ref["bob@example.com"]})
    check(r.status_code == 401, "reutilizar refresh rotado -> 401", short(r, 60))
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": new_ref})
    check(r.status_code == 401, "reutilización revoca toda la familia (el nuevo también muere)", short(r, 60))
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": tok["bob@example.com"]})
    check(r.status_code in (401, 422), "access token no sirve como refresh", short(r, 60))
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": ref["alice@example.com"], "x": 1})
    check(r.status_code == 422, "campos extra en /refresh rechazados", short(r, 60))

    # carrera: dos refresh simultáneos con el mismo token
    r = login("bob@example.com", PW["bob@example.com"])
    race_ref = r.json()["refresh_token"]

    async def race():
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as ac:
            return await asyncio.gather(*(
                ac.post("/api/v1/auth/refresh", json={"refresh_token": race_ref}) for _ in range(5)
            ))

    codes = sorted(x.status_code for x in asyncio.run(race()))
    check(codes.count(200) <= 1, "refresh concurrente: como mucho uno gana", str(codes))

    # logout
    r = login("bob@example.com", PW["bob@example.com"])
    lo_ref, lo_acc = r.json()["refresh_token"], r.json()["access_token"]
    r = client.post("/api/v1/auth/logout", json={"refresh_token": lo_ref})
    check(r.status_code == 204, "logout", short(r, 30))
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": lo_ref})
    check(r.status_code == 401, "refresh tras logout -> 401", short(r, 40))
    r = client.get("/api/v1/users/me", headers=bearer(lo_acc))
    record("INFO" if r.status_code == 200 else "OK",
           "access token sigue válido tras /logout hasta expirar (15 min)", short(r, 30))

    # --- 11. Revocación por cambio de rol / desactivación ------------------------
    r = client.patch(f"/api/v1/users/{bob_id}", json={"is_active": False}, headers=admin)
    check(r.status_code == 200, "admin desactiva a bob", short(r, 30))
    r = client.get("/api/v1/users/me", headers=bearer(lo_acc))
    check(r.status_code == 401, "access token de usuario desactivado -> 401", short(r, 40))
    r = client.patch(f"/api/v1/users/{bob_id}", json={"is_active": True}, headers=admin)
    r = client.patch(f"/api/v1/users/{admin_id}", json={"role": "user"}, headers=admin)
    check(r.status_code == 409, "no se puede degradar al último admin", short(r, 60))

    # --- 12. Registro -------------------------------------------------------------
    carol_pw = "lab-" + uuid.uuid4().hex  # no puede contener el email
    r = client.post("/api/v1/auth/register", json={"email": "carol@example.com", "password": carol_pw})
    check(r.status_code == 201, "registro carol", short(r, 40))
    r = client.post("/api/v1/auth/register", json={"email": "ALICE@example.com", "password": carol_pw + "x"})
    record("FALLO" if r.status_code == 409 else "OK",
           "registro no revela emails existentes (enumeración)", short(r, 80))
    r = client.post("/api/v1/auth/register", json={"email": "role@example.com", "password": carol_pw, "role": "admin"})
    check(r.status_code == 422, "registro rechaza role (mass assignment)", short(r, 60))
    r = client.post("/api/v1/auth/register", json={"email": "weak@example.com", "password": "password1234"})
    check(r.status_code == 422, "contraseña común rechazada", short(r, 80))
    r = client.post("/api/v1/auth/register", json={"email": "weak2@example.com", "password": "Weakpass1"})
    check(r.status_code == 422, "contraseña corta rechazada", short(r, 80))
    codes = []
    for i in range(4):
        r = client.post("/api/v1/auth/register",
                        json={"email": f"spam{i}@example.com", "password": carol_pw})
        codes.append(r.status_code)
    check(429 in codes, "registro limitado (5/hora por IP)", str(codes))
    check("retry-after" in r.headers or r.status_code != 429, "429 incluye Retry-After",
          r.headers.get("retry-after", "-"))

    # --- 13. Enumeración por tiempo en login ---------------------------------------
    t_exist, t_missing = [], []
    for i in range(4):
        for email, bucket in (("alice@example.com", t_exist), (f"noexiste{i}@example.com", t_missing)):
            login_budget()
            s = time.perf_counter()
            client.post("/api/v1/auth/login", data={"username": email, "password": "wrong-password-x"})
            bucket.append((time.perf_counter() - s) * 1000)
    record("INFO", "tiempo login (ms) email existente vs inexistente",
           f"mediana {statistics.median(t_exist):.1f} vs {statistics.median(t_missing):.1f}")
    r = login("alice@example.com", PW["alice@example.com"])  # resetea el contador de fallos de alice
    check(r.status_code == 200, "login correcto resetea fallos de alice", str(r.status_code))

    # --- 14. Bloqueo de cuenta (DoS de cuenta ajena) -------------------------------
    for _ in range(5):
        login("carol@example.com", "wrong-password-x")
    r = login("carol@example.com", carol_pw)
    record("FALLO" if r.status_code == 401 else "OK",
           "5 fallos de un tercero bloquean la cuenta de carol (DoS de cuenta)",
           f"login con contraseña correcta -> {r.status_code}")
    # Un admin también puede ser bloqueado por un anónimo
    for _ in range(5):
        login("admin@example.com", "wrong-password-x")
    r = login("admin@example.com", PW["admin@example.com"])
    record("FALLO" if r.status_code == 401 else "OK",
           "cuenta admin bloqueable por un anónimo", f"login correcto -> {r.status_code}")
    r = client.post(f"/api/v1/users/{admin_id}/unlock", headers=admin)
    check(r.status_code == 200, "admin se desbloquea con su token vigente", short(r, 30))

    # --- 15. Rate limiting -----------------------------------------------------------
    codes = [login("x@example.com", "wrong-password-x", budget=False).status_code for _ in range(12)]
    check(429 in codes, "login limitado por IP", str(codes))
    r = client.post("/api/v1/auth/login", data={"username": "x@example.com", "password": "y"},
                    headers={"X-Forwarded-For": "203.0.113.9"})
    check(r.status_code == 429, "X-Forwarded-For no evade el límite (sin TRUSTED_PROXIES)", short(r, 60))
    check("retry-after" in r.headers, "429 de login incluye Retry-After", r.headers.get("retry-after", "-"))

    codes = [client.get("/api/v1/users/me", headers=alice).status_code for _ in range(125)]
    first = codes.index(429) + 1 if 429 in codes else None
    check(first is not None, "límite por defecto 120/min por usuario", f"primer 429 en la petición {first}")
    r = client.get("/api/v1/orders", headers=alice)
    record("INFO", "otro endpoint del mismo usuario sigue disponible (contador por endpoint)",
           short(r, 30))

    codes = [client.get("/api/v1/does-not-exist").status_code for _ in range(200)]
    record("FALLO" if 429 not in codes else "OK",
           "rutas inexistentes también limitadas (200 peticiones anónimas)",
           f"{codes.count(404)}x404 {codes.count(429)}x429")

    # log injection (solo afecta al formato de texto; en producción el formato es JSON)
    client.get("/api/v1/x%0aFAKE%20LOG%20admin%20login%20ok")

    # --- 16. Cambio de contraseña ------------------------------------------------------
    r = client.post("/api/v1/users/me/password",
                    json={"current_password": "wrong", "new_password": carol_pw + "Z"}, headers=alice)
    check(r.status_code == 400, "cambio de contraseña exige la actual", short(r, 60))

    # --- 17. logout-all -----------------------------------------------------------------
    r = client.post("/api/v1/auth/logout-all", headers=bob)
    record("INFO", "logout-all con token antiguo de bob (ya revocado por la desactivación)", short(r, 40))

    print("\nResumen:", {s: sum(1 for x in results if x[0] == s) for s in ("OK", "FALLO", "INFO")})


if __name__ == "__main__":
    main()
