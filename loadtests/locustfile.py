"""Pruebas de estrés con Locust.

Usuarios virtuales (el peso indica la proporción):
- Visitor   (anónimo): navega el catálogo público, busca, filtra y pagina.
- Member    (autenticado): CRUD de sus notas privadas, /users/me y refresh.
- Attacker  (solo con LOADTEST_ATTACKERS=1): fuerza bruta de login, tokens
  falsificados, bodies enormes, inyección SQL, paginación abusiva y escritura
  anónima. Para él, "éxito" significa que la API RECHAZA la petición.

Cómo leer el informe:
- Un 429 (rate limit) nunca cuenta como fallo: aparece como "<endpoint> [429]"
  para ver cuánto tráfico frenó el limitador.
- Fallo = 5xx, error de red o un código que no era el esperado.

Uso directo: locust -f loadtests/locustfile.py --host http://127.0.0.1:8000
(normalmente se lanza con loadtests/run_loadtest.sh)
"""

import json
import os
import random
import urllib.request
import uuid
from urllib.parse import quote

from locust import FastHttpUser, between, events, tag, task

API = "/api/v1"
PASSWORD = os.environ.get("LOADTEST_PASSWORD", "bench-password-123456")
SEED_USERS = int(os.environ.get("SEED_USERS", "200"))
ATTACKERS = os.environ.get("LOADTEST_ATTACKERS") == "1"
_product_ids: list[str] = []


@events.test_start.add_listener
def _load_products(environment, **_):
    """Carga IDs de productos existentes para pedirlos por ID."""
    host = environment.host or "http://127.0.0.1:8000"
    with urllib.request.urlopen(f"{host}{API}/bench_products?limit=100") as resp:  # noqa: S310
        _product_ids.extend(item["id"] for item in json.load(resp)["items"])


def call(user, method, url, name, expected=(200,), **kwargs):
    """Hace la petición y la clasifica. Devuelve la respuesta (o None si fue 429)."""
    with user.client.request(method, url, name=name, catch_response=True, **kwargs) as r:
        if r.status_code == 429:
            r.request_meta["name"] = f"{name} [429]"
            r.success()
            return None
        if r.status_code in expected:
            r.success()
            return r
        r.failure(f"status {r.status_code}")
        return None


class Visitor(FastHttpUser):
    weight = 5
    wait_time = between(0.05, 0.3)

    @task(6)
    def list_products(self):
        offset = random.randint(0, 400)  # noqa: S311
        call(self, "GET", f"{API}/bench_products?limit=20&offset={offset}", "GET /bench_products")

    @task(3)
    def get_product(self):
        if _product_ids:
            pid = random.choice(_product_ids)  # noqa: S311
            call(self, "GET", f"{API}/bench_products/{pid}", "GET /bench_products/{id}")

    @task(2)
    def search(self):
        term = quote(random.choice(["azul", "rojo", "verde", "Producto 1"]))  # noqa: S311
        url = f"{API}/bench_products?q={term}&order_by=-price"
        call(self, "GET", url, "GET /bench_products?q=")

    @task(1)
    def filter_category(self):
        cat = random.choice(["books", "games", "music", "tools"])  # noqa: S311
        url = f"{API}/bench_products?category={cat}&active=true"
        call(self, "GET", url, "GET /bench_products?category=")

    @task(1)
    def health(self):
        call(self, "GET", "/health/live", "GET /health/live")


class Member(FastHttpUser):
    weight = 3
    wait_time = between(0.1, 0.5)

    def on_start(self):
        self.email = f"bench-user-{random.randrange(SEED_USERS)}@example.com"  # noqa: S311
        self.notes: list[str] = []
        self.access = self.refresh = None
        self._login()

    def _login(self):
        form = {"username": self.email, "password": PASSWORD}
        r = call(self, "POST", f"{API}/auth/login", "POST /auth/login", data=form)
        if r is not None:
            body = r.json()
            self.access, self.refresh = body["access_token"], body["refresh_token"]

    @property
    def auth(self):
        return {"Authorization": f"Bearer {self.access}"}

    @task(4)
    def create_note(self):
        if not self.access:
            return self._login()
        body_len = random.randint(10, 500)  # noqa: S311
        payload = {"title": f"nota {uuid.uuid4().hex[:8]}", "body": "x" * body_len}
        if _product_ids and random.random() < 0.5:  # noqa: S311
            payload["product_id"] = random.choice(_product_ids)  # noqa: S311
        r = call(
            self, "POST", f"{API}/bench_notes", "POST /bench_notes",
            expected=(201,), json=payload, headers=self.auth,
        )  # fmt: skip
        if r is not None:
            self.notes.append(r.json()["id"])

    @task(6)
    def list_notes(self):
        if self.access:
            call(self, "GET", f"{API}/bench_notes?limit=20", "GET /bench_notes", headers=self.auth)

    @task(3)
    def get_note(self):
        if self.access and self.notes:
            nid = random.choice(self.notes)  # noqa: S311
            call(
                self, "GET", f"{API}/bench_notes/{nid}", "GET /bench_notes/{id}", headers=self.auth
            )

    @task(2)
    def update_note(self):
        if self.access and self.notes:
            nid = random.choice(self.notes)  # noqa: S311
            pinned = random.random() < 0.5  # noqa: S311
            call(
                self, "PATCH", f"{API}/bench_notes/{nid}", "PATCH /bench_notes/{id}",
                json={"pinned": pinned}, headers=self.auth,
            )  # fmt: skip

    @task(1)
    def delete_note(self):
        if self.access and len(self.notes) > 5:
            nid = self.notes.pop(0)
            call(
                self, "DELETE", f"{API}/bench_notes/{nid}", "DELETE /bench_notes/{id}",
                expected=(204,), headers=self.auth,
            )  # fmt: skip

    @task(2)
    def me(self):
        if self.access:
            call(self, "GET", f"{API}/users/me", "GET /users/me", headers=self.auth)

    @task(1)
    def refresh_token(self):
        if not self.refresh:
            return
        r = call(
            self, "POST", f"{API}/auth/refresh", "POST /auth/refresh",
            json={"refresh_token": self.refresh},
        )  # fmt: skip
        if r is not None:
            body = r.json()
            self.access, self.refresh = body["access_token"], body["refresh_token"]


class Attacker(FastHttpUser):
    """Tráfico hostil: aquí la respuesta "esperada" es un rechazo."""

    weight = 1
    wait_time = between(0.05, 0.2)

    @tag("attack")
    @task(4)
    def brute_force_login(self):
        form = {"username": "bench-user-0@example.com", "password": uuid.uuid4().hex}
        call(
            self, "POST", f"{API}/auth/login", "ATTACK brute-force login",
            expected=(401,), data=form,
        )  # fmt: skip

    @tag("attack")
    @task(3)
    def forged_token(self):
        token = "eyJhbGciOiJub25lIn0.eyJzdWIiOiJ4Iiwicm9sZSI6ImFkbWluIn0."
        call(
            self, "GET", f"{API}/users", "ATTACK alg=none token",
            expected=(401,), headers={"Authorization": f"Bearer {token}"},
        )  # fmt: skip

    @tag("attack")
    @task(2)
    def oversized_body(self):
        # El servidor responde 413 y corta la conexión sin leer los 2 MB: el
        # cliente puede ver el 413 o un cierre de conexión (status 0). Ambos = OK.
        call(
            self, "POST", f"{API}/auth/register", "ATTACK 2MB body",
            expected=(413, 0), data=b'{"email":"' + b"a" * 2_000_000 + b'"}',
            headers={"Content-Type": "application/json"},
        )  # fmt: skip

    @tag("attack")
    @task(2)
    def abusive_pagination(self):
        url = f"{API}/bench_products?limit=100000&offset=99999999"
        call(self, "GET", url, "ATTACK huge pagination", expected=(422,))

    @tag("attack")
    @task(2)
    def sql_injection_probe(self):
        url = (
            f"{API}/bench_products?q={quote(chr(39) + ' OR 1=1 --')}"
            f"&order_by={quote('price;DROP TABLE users')}"
        )
        call(self, "GET", url, "ATTACK sqli order_by", expected=(422,))

    @tag("attack")
    @task(2)
    def anonymous_write(self):
        call(
            self, "POST", f"{API}/bench_products", "ATTACK create as anonymous",
            expected=(401,), json={"name": "x", "sku": uuid.uuid4().hex[:10], "price": "1"},
        )  # fmt: skip


if not ATTACKERS:
    del Attacker  # Locust ejecuta todas las clases User del módulo
