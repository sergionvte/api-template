"""`apigen docs`: README.md para el cliente final, generado desde los recursos.

La parte entre los marcadores `<!-- apigen:docs:start ... -->` y `<!-- apigen:docs:end -->`
se regenera cada vez (endpoints, campos, permisos, acciones, configuración...).
Lo que escribas fuera de los marcadores (introducción, contacto, notas) se conserva.
El marcador de inicio recuerda el idioma y la URL base (`lang=es base_url=...`), así
`apigen docs` sin opciones mantiene lo elegido la primera vez (UX-52).

No importa la app: lee `resources/*.yaml`, `app/api/versions.py`, `.env.example` y los
`APIError(..., code=...)` de `app/hooks/` (errores propios, siempre al día), así
funciona aunque el `.env` local sea de producción.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from apigen import docs_accounts
from apigen.project import load_all_specs, version_info
from apigen.spec import FieldSpec, ResourceSpec

START, END = "<!-- apigen:docs:start -->", "<!-- apigen:docs:end -->"
_START_RE = re.compile(r"<!-- apigen:docs:start(?P<attrs>[^>]*?)\s*-->")
DEFAULT_BASE_URL = "http://127.0.0.1:8000"

T = {
    "en": {
        "intro": "Describe here what this API does, who it is for and the main use cases.",
        "contact": "## Support\n\nContact: _(your name, email or platform profile)_.\n",
        "features": "Features",
        "feat_list": [
            "JWT authentication (short-lived access token + rotating refresh token), roles and scopes",
            "Argon2id password hashing, smart account lockout and rate limiting",
            "Per-user data isolation, input validation and security headers",
            "Versioned REST API with interactive OpenAPI docs",
        ],
        "feat_jobs": "Background jobs for heavy work (the API answers `202 Accepted` instantly)",
        # --- Para integrar ---------------------------------------------------------
        "integrate": "Integration guide (front-end / mobile)",
        "integrate_body": (
            "Base URL: `{base}` · API prefix: `{p}` · JSON in and out (`Content-Type: application/json`). "
            "Interactive docs at `{base}/docs` when `DOCS_ENABLED=true` (off by default in production).\n"
        ),
        "first_steps": "First steps",
        "first_steps_body": (
            "1. **Register** (if public sign-up is enabled):\n\n"
            "   ```bash\n"
            "   curl -X POST {base}{p}/auth/register -H 'Content-Type: application/json' \\\n"
            '     -d \'{{"email": "ana@example.com", "password": "a long passphrase"}}\'\n'
            "   ```\n\n"
            '   `201` → `{{"id": "…", "email": "ana@example.com", "full_name": null, "role": "user", '
            '"is_active": true, "email_verified": false, "created_at": "…"}}`\n'
            "2. **Log in** (form data, not JSON):\n\n"
            "   ```bash\n"
            "   curl -X POST {base}{p}/auth/login -d 'username=ana@example.com' "
            "--data-urlencode 'password=a long passphrase'\n"
            "   ```\n\n"
            '   `200` → `{{"access_token": "eyJ…", "refresh_token": "…", "token_type": "bearer", '
            '"expires_in": {expires}, "scope": "read write"}}`\n'
            "3. **Call the API** with the access token:\n\n"
            "   ```bash\n"
            '   curl {base}{p}/users/me -H "Authorization: Bearer $ACCESS_TOKEN"\n'
            "   ```\n"
            "4. **Refresh** when you get `401` with `code: token_expired`:\n\n"
            "   ```bash\n"
            "   curl -X POST {base}{p}/auth/refresh -H 'Content-Type: application/json' "
            '-d \'{{"refresh_token": "…"}}\'\n'
            "   ```\n\n"
            "   Same response as the login: **store the new pair** (the old refresh token stops working).\n"
        ),
        "auth": "Authentication",
        "auth_body": (
            "- The access token lasts {access} minutes (`expires_in`, in seconds); the refresh token "
            "{refresh} days.\n"
            "- `scope=read` in the login form returns a read-only token (writes answer `403 insufficient_scope`).\n"
            "- `POST {p}/auth/logout` (with `refresh_token`) closes one session; "
            "`POST {p}/auth/logout-all` closes all of them.\n"
            "- Repeated failed logins lock the account for a while; the login keeps answering "
            "`401 invalid_credentials` (it does not reveal the lock). Admins can unlock it.\n"
        ),
        "pagination": "Lists and pagination",
        "pagination_body": (
            'Every list answers `{{"items": [...], "total": 42, "limit": {defp}, "offset": 0}}`. '
            "Use `limit` (1-{maxp}, default {defp}) and `offset` (up to {maxo}) to page; `total` counts "
            "all matching rows. `order_by` accepts the fields listed per resource (prefix `-` for "
            "descending). Unknown query parameters answer `422` with a hint (e.g. use `q`, not `search`).\n"
        ),
        "errors": "Errors",
        "errors_body": (
            "Errors return JSON with `detail` (human-readable) and `code` (stable, for your code). "
            "Validation errors (`422`) list each problem with its field in `loc`.\n"
        ),
        "err_rows": [
            (
                "401",
                "not_authenticated / invalid_token / token_expired",
                "Missing or invalid token",
            ),
            ("403", "forbidden / insufficient_scope", "Not allowed"),
            ("404", "not_found", "Does not exist (or is not yours)"),
            ("409", "unique_violation / has_dependents", "Conflicts with existing data"),
            ("413 / 415", "body_too_large / expects_json", "Request body problems"),
            ("422", "validation_error", "Invalid data (see `detail[].loc`)"),
            (
                "429",
                "rate_limited / too_many_pending_jobs",
                "Too many requests (see `Retry-After`)",
            ),
        ],
        "custom_errors": "Business errors of this API",
        "custom_errors_body": (
            "Returned by the business rules of this API (same JSON format). Extracted from "
            "`app/hooks/` every time the docs are generated.\n"
        ),
        "accounts": "Accounts and roles",
        "accounts_body": (
            "Sign-up creates users with role `user`. Admins (role `admin`) can see and manage "
            "everything; the first admin is created by the operator (`apigen createsuperuser`) and "
            'others are promoted with `PATCH {p}/users/{{id}}` (`{{"role": "admin"}}`).\n\n'
            "| Method | Path | Who | Description |\n|---|---|---|---|\n"
            "| GET / PATCH | `{p}/users/me` | Logged-in user | Own profile |\n"
            "| POST | `{p}/users/me/password` | Logged-in user | Change password (closes all sessions) |\n"
            "| GET / POST | `{p}/users` | Admins | List / create users |\n"
            "| GET / PATCH / DELETE | `{p}/users/{{id}}` | Admins | Manage a user (role, active) |\n"
            "| POST | `{p}/users/{{id}}/unlock` | Admins | Unlock a locked account |\n"
        ),
        "resources": "Resources",
        "no_resources": "_No resources yet._\n",
        "version": "API version",
        "deprecated": "**Deprecated** (sunset: {sunset}). Responses include `Deprecation` and `Sunset` headers.",
        "method": "Method",
        "path": "Path",
        "who": "Who can call it",
        "desc": "Description",
        "list": "List (paginated)",
        "create": "Create",
        "read": "Get one",
        "update": "Partial update",
        "delete": "Delete",
        "delete_soft": "Delete (soft: it can no longer be listed or read)",
        "field": "Field",
        "type": "Type",
        "required": "Required",
        "rules": "Rules",
        "yes": "yes",
        "no": "no",
        "read_only": "read-only",
        "query": "List parameters: `limit`, `offset`, `order_by` ({order}){search}{filters}.",
        "search": ", `q` (text search in {fields})",
        "filters": ", filters: {fields}",
        "owned": "Each record belongs to the user who creates it (`owner_id`, set by the server).",
        "rl": "Rate limit: reads {read}, writes {write}.",
        "examples": "Examples",
        "ex_create": "# Create",
        "ex_list": "# List (page, order and filter)",
        "actions": "Actions",
        "action_bg": (
            'background job: `202` → `{{"job_id": "…", "status": "queued", '
            '"status_url": "{p}/jobs/…"}}` (also in `Location`); the outcome is in `result` '
            "of the job (see Background jobs)"
        ),
        "action_sync": "`200` → a JSON object",
        "action_body": "body: {fields}",
        "action_no_body": "no body needed (or `{}`)",
        "action_rate": "rate limit {rate}",
        "levels": {
            "public": "Anyone",
            "user": "Any logged-in user",
            "owner": "The owner (admins: any)",
            "admin": "Admins",
        },
        "jobs": "Background jobs",
        "jobs_body": (
            "Heavy actions answer `202` at once and run in a separate worker. Poll `status_url` "
            "every 1-2 s (or with a growing interval) until `status` is final:\n\n"
            "`queued` → `running` → `succeeded` (see `result`) · `failed` (see `error`) · "
            "`cancelled`.\n\n"
            "| Method | Path | Description |\n|---|---|---|\n"
            "| GET | `{p}/jobs` | Your jobs, newest first (admins: all). Filters: `status`, `name`, `limit`, `offset` |\n"
            "| GET | `{p}/jobs/{{id}}` | One job |\n"
            "| POST | `{p}/jobs/{{id}}/cancel` | Cancel a job that has not started; otherwise `409 job_not_cancellable` |\n\n"
            "Job fields: `id`, `name`, `status`, `attempts` / `max_attempts`, `result` (JSON, when "
            "`succeeded`), `error` (text, when `failed`), `created_at`, `run_after` (next attempt), "
            "`started_at`, `finished_at`.\n\n"
            "- Failures are retried automatically with a growing wait (the job goes back to `queued`).\n"
            "- `error` shows business messages of the API; any other failure shows `Task failed`.\n"
            "- At most {pending} pending jobs per user: beyond that, `429 too_many_pending_jobs` "
            "with `Retry-After`.\n"
        ),
        "task_errors": "Messages that `error` can show",
        "limits": "Rate limits",
        "limits_body": (
            "Default: {default} per endpoint and {glob} in total per client (user or IP). "
            "Login: {login}. Register: {register} (production). Exceeding a limit returns `429` "
            "with a `Retry-After` header.\n"
        ),
        # --- Para desplegar -------------------------------------------------------
        "deploy_title": "Deployment (operators)",
        "quick": "Quick start (Docker)",
        "quick_body": (
            "Requirements: Docker with Docker Compose.\n\n"
            "```bash\n"
            "cp .env.example .env\n"
            "# Edit .env — the API refuses to start in production with the example values:\n"
            "#   SECRET_KEY=...         random, 32+ chars:  openssl rand -base64 48\n"
            "#   POSTGRES_PASSWORD=...  random:             openssl rand -hex 24\n"
            "#   ALLOWED_HOSTS=api.example.com,localhost,127.0.0.1   (your domain(s))\n"
            "#   CORS_ORIGINS=https://app.example.com                (your front-end, if any)\n"
            "docker compose up -d --build\n"
            "docker compose exec api apigen createsuperuser --email admin@example.com\n"
            "```\n\n"
            'Without `openssl`: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`. '
            "The API listens on `http://127.0.0.1:8000` (put an HTTPS proxy in front); database "
            "migrations run automatically on start. Check with `docker compose ps` (all `healthy`).\n"
        ),
        "config": "Configuration",
        "config_body": "All settings are environment variables (see `.env.example`). The most important:",
        "cfg_rows": [
            ("SECRET_KEY", "**Required.** Random secret, 32+ characters (signs the tokens)"),
            (
                "POSTGRES_PASSWORD",
                "**Required with Docker.** Database password (letters and digits)",
            ),
            (
                "ALLOWED_HOSTS",
                "**Required in production.** Public domain(s) of the API, comma-separated",
            ),
            ("CORS_ORIGINS", "Front-end origins allowed to call the API from a browser"),
            ("ENVIRONMENT", "`production` enables strict security checks (Docker forces it)"),
            ("DATABASE_URL", "`postgresql+asyncpg://user:pass@host:5432/db` (Docker sets it)"),
            (
                "RATE_LIMIT_STORAGE_URI",
                "`redis://host:6379/0` with several processes (Docker sets it)",
            ),
            ("TRUSTED_PROXIES", "IP of the reverse proxy, to trust `X-Forwarded-For`"),
            ("ALLOW_REGISTRATION", "`false` to close public sign-up"),
        ],
        "deploy": "Operations",
        "deploy_body": (
            "`docker compose up -d` starts the API, the background worker, PostgreSQL and Redis.\n\n"
            "- Put the API behind HTTPS (nginx, Caddy, a load balancer...) that **overwrites** "
            "`X-Forwarded-For`, and set `TRUSTED_PROXIES` to its IP.\n"
            "- More capacity for background jobs: `docker compose up -d --scale worker=3`.\n"
            "- Run `docker compose exec api apigen db prune` daily (old sessions and finished jobs).\n"
            "- Back up the PostgreSQL volume regularly.\n"
            "- Health checks: `GET /health/live` (process) and `GET /health/ready` (database). "
            "An `unhealthy` container is not restarted automatically without an orchestrator.\n"
        ),
        # --- Para desarrollar -----------------------------------------------------
        "local": "Development (without Docker)",
        "local_body": (
            "Requirements: Python 3.12+ and [uv](https://docs.astral.sh/uv/).\n\n"
            "```bash\n"
            "uv sync\n"
            "uv run apigen init-env      # creates .env with a random SECRET_KEY\n"
            "uv run apigen db upgrade\n"
            "uv run apigen createsuperuser --email admin@example.com\n"
            "uv run apigen run           # http://127.0.0.1:8000/docs\n"
            "{worker}"
            "uv run pytest               # test suite\n"
            "```\n"
        ),
        "worker_line": "uv run apigen worker        # background jobs (second terminal)\n",
        "generated": "_Sections between the markers are generated by `apigen docs` from the API definition._",
    },
}

T["es"] = {
    **T["en"],
    "intro": "Describe aquí qué hace esta API, para quién es y sus casos de uso principales.",
    "contact": "## Soporte\n\nContacto: _(tu nombre, email o perfil de la plataforma)_.\n",
    "features": "Características",
    "feat_list": [
        "Autenticación JWT (token de acceso corto + refresh rotatorio), roles y scopes",
        "Contraseñas con Argon2id, bloqueo inteligente de cuentas y rate limiting",
        "Aislamiento de datos por usuario, validación de entrada y cabeceras de seguridad",
        "API REST versionada con documentación OpenAPI interactiva",
    ],
    "feat_jobs": "Tareas en segundo plano para procesos pesados (la API responde `202 Accepted` al instante)",
    "integrate": "Guía de integración (frontend / móvil)",
    "integrate_body": (
        "URL base: `{base}` · prefijo: `{p}` · JSON de entrada y salida (`Content-Type: application/json`). "
        "Documentación interactiva en `{base}/docs` con `DOCS_ENABLED=true` (desactivada por defecto en producción).\n"
    ),
    "first_steps": "Primeros pasos",
    "first_steps_body": (
        "1. **Registro** (si el registro público está activado):\n\n"
        "   ```bash\n"
        "   curl -X POST {base}{p}/auth/register -H 'Content-Type: application/json' \\\n"
        '     -d \'{{"email": "ana@example.com", "password": "una frase larga"}}\'\n'
        "   ```\n\n"
        '   `201` → `{{"id": "…", "email": "ana@example.com", "full_name": null, "role": "user", '
        '"is_active": true, "email_verified": false, "created_at": "…"}}`\n'
        "2. **Login** (formulario, no JSON):\n\n"
        "   ```bash\n"
        "   curl -X POST {base}{p}/auth/login -d 'username=ana@example.com' "
        "--data-urlencode 'password=una frase larga'\n"
        "   ```\n\n"
        '   `200` → `{{"access_token": "eyJ…", "refresh_token": "…", "token_type": "bearer", '
        '"expires_in": {expires}, "scope": "read write"}}`\n'
        "3. **Llama a la API** con el token de acceso:\n\n"
        "   ```bash\n"
        '   curl {base}{p}/users/me -H "Authorization: Bearer $ACCESS_TOKEN"\n'
        "   ```\n"
        "4. **Renueva** al recibir `401` con `code: token_expired`:\n\n"
        "   ```bash\n"
        "   curl -X POST {base}{p}/auth/refresh -H 'Content-Type: application/json' "
        '-d \'{{"refresh_token": "…"}}\'\n'
        "   ```\n\n"
        "   Misma respuesta que el login: **guarda el par nuevo** (el refresh anterior deja de valer).\n"
    ),
    "auth": "Autenticación",
    "auth_body": (
        "- El token de acceso dura {access} minutos (`expires_in`, en segundos); el refresh, "
        "{refresh} días.\n"
        "- Con `scope=read` en el formulario de login se obtiene un token de solo lectura (las "
        "escrituras responden `403 insufficient_scope`).\n"
        "- `POST {p}/auth/logout` (con `refresh_token`) cierra una sesión; "
        "`POST {p}/auth/logout-all`, todas.\n"
        "- Tras varios intentos fallidos la cuenta se bloquea un tiempo; el login sigue respondiendo "
        "`401 invalid_credentials` (no revela el bloqueo). Un admin puede desbloquearla.\n"
    ),
    "pagination": "Listados y paginación",
    "pagination_body": (
        'Todo listado responde `{{"items": [...], "total": 42, "limit": {defp}, "offset": 0}}`. '
        "Pagina con `limit` (1-{maxp}, por defecto {defp}) y `offset` (hasta {maxo}); `total` cuenta "
        "todas las filas que cumplen el filtro. `order_by` admite los campos indicados en cada "
        "recurso (prefijo `-` descendente). Un parámetro desconocido responde `422` con una pista "
        "(p. ej. usa `q`, no `search`).\n"
    ),
    "errors": "Errores",
    "errors_body": (
        "Los errores devuelven JSON con `detail` (texto para humanos) y `code` (estable, para tu "
        "código). Los `422` listan cada problema con su campo en `loc`.\n"
    ),
    "err_rows": [
        ("401", "not_authenticated / invalid_token / token_expired", "Token ausente o inválido"),
        ("403", "forbidden / insufficient_scope", "Sin permiso"),
        ("404", "not_found", "No existe (o no es tuyo)"),
        ("409", "unique_violation / has_dependents", "Conflicto con datos existentes"),
        ("413 / 415", "body_too_large / expects_json", "Problemas con el cuerpo"),
        ("422", "validation_error", "Datos no válidos (ver `detail[].loc`)"),
        (
            "429",
            "rate_limited / too_many_pending_jobs",
            "Demasiadas peticiones (ver `Retry-After`)",
        ),
    ],
    "custom_errors": "Errores de negocio de esta API",
    "custom_errors_body": (
        "Los devuelven las reglas de negocio de esta API (mismo formato JSON). Se extraen de "
        "`app/hooks/` cada vez que se genera esta documentación.\n"
    ),
    "accounts": "Cuentas y roles",
    "accounts_body": (
        "El registro crea usuarios con rol `user`. Los admins (rol `admin`) ven y gestionan todo; "
        "el primer admin lo crea quien opera la API (`apigen createsuperuser`) y los demás se "
        'promueven con `PATCH {p}/users/{{id}}` (`{{"role": "admin"}}`).\n\n'
        "| Método | Ruta | Quién | Descripción |\n|---|---|---|---|\n"
        "| GET / PATCH | `{p}/users/me` | Usuario autenticado | Perfil propio |\n"
        "| POST | `{p}/users/me/password` | Usuario autenticado | Cambiar contraseña (cierra sesiones) |\n"
        "| GET / POST | `{p}/users` | Admins | Listar / crear usuarios |\n"
        "| GET / PATCH / DELETE | `{p}/users/{{id}}` | Admins | Gestionar un usuario (rol, activo) |\n"
        "| POST | `{p}/users/{{id}}/unlock` | Admins | Desbloquear una cuenta |\n"
    ),
    "resources": "Recursos",
    "no_resources": "_Aún no hay recursos._\n",
    "version": "Versión de la API",
    "deprecated": "**Deprecada** (retirada: {sunset}). Las respuestas llevan `Deprecation` y `Sunset`.",
    "method": "Método",
    "path": "Ruta",
    "who": "Quién puede",
    "desc": "Descripción",
    "list": "Listar (paginado)",
    "create": "Crear",
    "read": "Ver uno",
    "update": "Modificar (parcial)",
    "delete": "Borrar",
    "delete_soft": "Borrar (lógico: deja de listarse y leerse)",
    "field": "Campo",
    "type": "Tipo",
    "required": "Obligatorio",
    "rules": "Reglas",
    "yes": "sí",
    "no": "no",
    "read_only": "solo lectura",
    "query": "Parámetros del listado: `limit`, `offset`, `order_by` ({order}){search}{filters}.",
    "search": ", `q` (búsqueda en {fields})",
    "filters": ", filtros: {fields}",
    "owned": "Cada registro pertenece al usuario que lo crea (`owner_id`, lo fija el servidor).",
    "rl": "Rate limit: lecturas {read}, escrituras {write}.",
    "examples": "Ejemplos",
    "ex_create": "# Crear",
    "ex_list": "# Listar (página, orden y filtro)",
    "actions": "Acciones",
    "action_bg": (
        'en segundo plano: `202` → `{{"job_id": "…", "status": "queued", '
        '"status_url": "{p}/jobs/…"}}` (también en `Location`); el resultado queda en '
        "`result` del trabajo (ver Tareas en segundo plano)"
    ),
    "action_sync": "`200` → un objeto JSON",
    "action_body": "cuerpo: {fields}",
    "action_no_body": "sin cuerpo (o `{}`)",
    "action_rate": "rate limit {rate}",
    "levels": {
        "public": "Cualquiera",
        "user": "Usuario autenticado",
        "owner": "El dueño (admins: cualquiera)",
        "admin": "Admins",
    },
    "jobs": "Tareas en segundo plano",
    "jobs_body": (
        "Las acciones pesadas responden `202` al instante y se ejecutan en un worker aparte. "
        "Consulta `status_url` cada 1-2 s (o con un intervalo creciente) hasta un estado final:\n\n"
        "`queued` → `running` → `succeeded` (ver `result`) · `failed` (ver `error`) · "
        "`cancelled`.\n\n"
        "| Método | Ruta | Descripción |\n|---|---|---|\n"
        "| GET | `{p}/jobs` | Tus trabajos, los más recientes primero (admins: todos). Filtros: `status`, `name`, `limit`, `offset` |\n"
        "| GET | `{p}/jobs/{{id}}` | Un trabajo |\n"
        "| POST | `{p}/jobs/{{id}}/cancel` | Cancela un trabajo que aún no ha empezado; si no, `409 job_not_cancellable` |\n\n"
        "Campos del trabajo: `id`, `name`, `status`, `attempts` / `max_attempts`, `result` (JSON, "
        "si `succeeded`), `error` (texto, si `failed`), `created_at`, `run_after` (próximo intento), "
        "`started_at`, `finished_at`.\n\n"
        "- Los fallos se reintentan solos con una espera creciente (el trabajo vuelve a `queued`).\n"
        "- `error` muestra los mensajes de negocio de la API; cualquier otro fallo, `Task failed`.\n"
        "- Como mucho {pending} trabajos pendientes por usuario: a partir de ahí, "
        "`429 too_many_pending_jobs` con `Retry-After`.\n"
    ),
    "task_errors": "Mensajes que puede mostrar `error`",
    "limits": "Límites de peticiones",
    "limits_body": (
        "Por defecto: {default} por endpoint y {glob} en total por cliente (usuario o IP). "
        "Login: {login}. Registro: {register} (producción). Al superarlo se responde `429` "
        "con la cabecera `Retry-After`.\n"
    ),
    "deploy_title": "Despliegue (operación)",
    "quick": "Arranque rápido (Docker)",
    "quick_body": (
        "Requisitos: Docker con Docker Compose.\n\n"
        "```bash\n"
        "cp .env.example .env\n"
        "# Edita .env — en producción la API no arranca con los valores de ejemplo:\n"
        "#   SECRET_KEY=...         aleatoria, 32+ caracteres:  openssl rand -base64 48\n"
        "#   POSTGRES_PASSWORD=...  aleatoria:                  openssl rand -hex 24\n"
        "#   ALLOWED_HOSTS=api.example.com,localhost,127.0.0.1   (tus dominios)\n"
        "#   CORS_ORIGINS=https://app.example.com                (tu frontend, si lo hay)\n"
        "docker compose up -d --build\n"
        "docker compose exec api apigen createsuperuser --email admin@example.com\n"
        "```\n\n"
        'Sin `openssl`: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`. '
        "La API escucha en `http://127.0.0.1:8000` (pon delante un proxy con HTTPS); las "
        "migraciones se aplican solas al arrancar. Compruébalo con `docker compose ps` (todo `healthy`).\n"
    ),
    "config": "Configuración",
    "config_body": "Todo se configura con variables de entorno (ver `.env.example`). Las más importantes:",
    "cfg_rows": [
        ("SECRET_KEY", "**Obligatoria.** Secreto aleatorio de 32+ caracteres (firma los tokens)"),
        (
            "POSTGRES_PASSWORD",
            "**Obligatoria con Docker.** Contraseña de la base de datos (letras y números)",
        ),
        (
            "ALLOWED_HOSTS",
            "**Obligatoria en producción.** Dominio(s) públicos de la API, separados por comas",
        ),
        ("CORS_ORIGINS", "Orígenes del frontend que pueden llamar a la API desde el navegador"),
        ("ENVIRONMENT", "`production` activa las comprobaciones estrictas (Docker la fuerza)"),
        ("DATABASE_URL", "`postgresql+asyncpg://usuario:clave@host:5432/bd` (Docker la fija)"),
        ("RATE_LIMIT_STORAGE_URI", "`redis://host:6379/0` con varios procesos (Docker la fija)"),
        ("TRUSTED_PROXIES", "IP del proxy inverso, para confiar en `X-Forwarded-For`"),
        ("ALLOW_REGISTRATION", "`false` para cerrar el registro público"),
    ],
    "deploy": "Operación",
    "deploy_body": (
        "`docker compose up -d` arranca la API, el worker, PostgreSQL y Redis.\n\n"
        "- Pon la API detrás de HTTPS (nginx, Caddy, un balanceador...) que **sobrescriba** "
        "`X-Forwarded-For`, y configura `TRUSTED_PROXIES` con su IP.\n"
        "- Más capacidad para tareas pesadas: `docker compose up -d --scale worker=3`.\n"
        "- Ejecuta `docker compose exec api apigen db prune` a diario (sesiones antiguas y trabajos terminados).\n"
        "- Haz copias de seguridad del volumen de PostgreSQL.\n"
        "- Salud: `GET /health/live` (proceso) y `GET /health/ready` (base de datos). Sin un "
        "orquestador, un contenedor `unhealthy` no se reinicia solo.\n"
    ),
    "local": "Desarrollo (sin Docker)",
    "local_body": (
        "Requisitos: Python 3.12+ y [uv](https://docs.astral.sh/uv/).\n\n"
        "```bash\n"
        "uv sync\n"
        "uv run apigen init-env      # crea .env con una SECRET_KEY aleatoria\n"
        "uv run apigen db upgrade\n"
        "uv run apigen createsuperuser --email admin@example.com\n"
        "uv run apigen run           # http://127.0.0.1:8000/docs\n"
        "{worker}"
        "uv run pytest               # tests\n"
        "```\n"
    ),
    "worker_line": "uv run apigen worker        # tareas en segundo plano (otra terminal)\n",
    "generated": "_Las secciones entre los marcadores las genera `apigen docs` a partir de la definición de la API._",
}

_TYPE = {
    "en": {
        "str": "string",
        "text": "string (long)",
        "int": "integer",
        "float": "number",
        "decimal": "decimal (string)",
        "bool": "boolean",
        "date": "date `YYYY-MM-DD`",
        "datetime": "datetime (ISO 8601 with timezone)",
        "uuid": "UUID",
        "email": "email",
        "json": "JSON object/array",
    },
    "es": {
        "str": "texto",
        "text": "texto (largo)",
        "int": "entero",
        "float": "número",
        "decimal": "decimal (texto)",
        "bool": "booleano",
        "date": "fecha `AAAA-MM-DD`",
        "datetime": "fecha y hora (ISO 8601 con zona)",
        "uuid": "UUID",
        "email": "email",
        "json": "objeto/lista JSON",
    },
}


def read_env_example(base: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    path = base / ".env.example"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", line.strip())
            if m:
                values[m.group(1)] = m.group(2).strip().strip('"')
    return values


def _field_type(f: FieldSpec, lang: str, specs: dict[str, ResourceSpec]) -> str:
    if f.type == "enum":
        return (
            ("one of" if lang == "en" else "uno de")
            + ": "
            + ", ".join(f"`{c}`" for c in f.choices or [])
        )
    if f.type == "fk":
        target = "user" if f.to == "user" else specs[f.to].plural if f.to in specs else f.to
        return f"UUID → `{target}`"
    return _TYPE[lang][f.type]


def _field_rules(f: FieldSpec, lang: str, owned: bool) -> str:
    es = lang == "es"
    rules: list[str] = []
    if f.min_length:
        rules.append(f"min {f.min_length}")
    if f.max_length and f.type in {"str", "text", "email"}:
        rules.append(f"max {f.max_length}")
    for key, sym in (("ge", "≥"), ("gt", ">"), ("le", "≤"), ("lt", "<")):
        value = getattr(f, key)
        if value is not None and not (f.type == "int" and abs(value) >= 2**31):
            rules.append(f"{sym} {int(value) if float(value).is_integer() else value}")
    if f.type == "decimal":
        rules.append(f"{f.max_digits} {'dígitos' if es else 'digits'}, {f.decimal_places} dec.")
    if f.pattern:
        rules.append(f"`{f.pattern}`")
    if f.unique:
        scope = (" por usuario" if es else " per user") if owned else ""
        rules.append(("único" if es else "unique") + scope)
    if f.default is not None:
        rules.append(f"{'por defecto' if es else 'default'} `{f.default}`")
    if f.immutable:
        rules.append("no modificable" if es else "cannot be changed")
    if f.write_only:
        rules.append("no se devuelve" if es else "never returned")
    if f.nullable:
        rules.append("admite null" if es else "nullable")
    if f.description:
        rules.append(f.description)
    return "; ".join(rules) or "—"


def _example_value(f: FieldSpec, specs: dict[str, ResourceSpec]) -> object:
    """Valor de ejemplo para los `curl` del README (el `example` del YAML si lo hay)."""
    if f.example is not None:
        return f.example
    if f.default is not None:
        return f.default
    samples: dict[str, object] = {
        "str": "text",
        "text": "Some text",
        "email": "ana@example.com",
        "bool": True,
        "date": "2030-01-10",
        "datetime": "2030-01-10T10:00:00+00:00",
        "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "json": {"key": "value"},
    }
    if f.type in {"int", "float", "decimal"}:
        low = f.ge if f.ge is not None else (f.gt + 1 if f.gt is not None else 1)
        if f.type == "int":
            return int(low)
        if f.type == "float":
            return float(low)
        return f"{float(low) + 9:.{f.decimal_places or 2}f}"
    if f.type == "enum":
        return (f.choices or [""])[0]
    if f.type == "fk":
        target = specs[f.to].name if f.to in specs else f.to
        return f"<{target} id>"
    return samples.get(f.type, "…")


def _examples(
    spec: ResourceSpec,
    base_url: str,
    path: str,
    lang: str,
    env: dict[str, str],
    specs: dict[str, ResourceSpec],
) -> str:
    t = T[lang]
    body = {
        name: _example_value(f, specs)
        for name, f in spec.fields.items()
        if f.required or f.example is not None
    }
    data = json.dumps(body, ensure_ascii=False).replace("'", "'\\''")
    auth_create = (
        "" if spec.permissions.create == "public" else ' -H "Authorization: Bearer $TOKEN"'
    )
    auth_list = "" if spec.permissions.list == "public" else ' -H "Authorization: Bearer $TOKEN"'
    query = f"limit={env.get('PAGE_SIZE_DEFAULT', '20')}&offset=0&order_by=-created_at"
    for fname in spec.filters[:1]:
        value = _example_value(spec.fields[fname], specs)
        if isinstance(value, bool):
            value = str(value).lower()
        query += f"&{fname}={value}"
    return (
        f"{t['examples']}:\n\n```bash\n"
        f"{t['ex_create']}\n"
        f"curl -X POST {base_url}{path}{auth_create} -H 'Content-Type: application/json' \\\n"
        f"  -d '{data}'\n"
        f"{t['ex_list']}\n"
        f'curl "{base_url}{path}?{query}"{auth_list}\n'
        "```\n"
    )


def _resource_section(
    spec: ResourceSpec,
    prefix: str,
    lang: str,
    env: dict[str, str],
    specs: dict[str, ResourceSpec],
    base_url: str = DEFAULT_BASE_URL,
    jobs_prefix: str = "",
) -> str:
    t = T[lang]
    lv = t["levels"]
    p = spec.permissions
    base = f"{prefix}/{spec.plural}"
    out = [f"##### `{spec.plural}`\n"]
    if spec.description:
        out.append(spec.description + "\n")
    if spec.owned:
        out.append(t["owned"] + "\n")
    rows = [
        ("GET", base, p.list, t["list"]),
        ("POST", base, p.create, t["create"]),
        ("GET", f"{base}/{{id}}", p.read, t["read"]),
        ("PATCH", f"{base}/{{id}}", p.update, t["update"]),
        (
            "DELETE",
            f"{base}/{{id}}",
            p.delete,
            t["delete_soft"] if spec.soft_delete else t["delete"],
        ),
    ]
    for a in spec.actions:
        path = f"{base}/{{id}}/{a.name}" if a.scope == "item" else f"{base}/{a.name}"
        desc = a.description or a.name
        if a.background:
            desc += " — " + ("background (202)" if lang == "en" else "segundo plano (202)")
        rows.append(("POST", path, a.permission, desc))
    out.append(f"| {t['method']} | {t['path']} | {t['who']} | {t['desc']} |\n|---|---|---|---|")
    out += [f"| {m} | `{path}` | {lv[level]} | {d} |" for m, path, level, d in rows]
    out.append("")
    order = ", ".join(f"`{o}`" for o in sorted({"created_at", *spec.ordering}))
    search = (
        t["search"].format(fields=", ".join(f"`{f}`" for f in spec.search)) if spec.search else ""
    )
    filters = (
        t["filters"].format(fields=", ".join(f"`{f}`" for f in spec.filters))
        if spec.filters
        else ""
    )
    out.append(t["query"].format(order=order, search=search, filters=filters) + "\n")
    out.append(
        f"| {t['field']} | {t['type']} | {t['required']} | {t['rules']} |\n|---|---|---|---|"
    )
    for name, f in spec.fields.items():
        req = t["yes"] if f.required else t["no"]
        out.append(
            f"| `{name}` | {_field_type(f, lang, specs)} | {req} | {_field_rules(f, lang, spec.owned)} |"
        )
    out.append(
        "| `id`, `created_at`, `updated_at`"
        + (", `owner_id`" if spec.owned else "")
        + f" | {t['read_only']} | — | — |\n"
    )
    if spec.rate_limits.read or spec.rate_limits.write:
        default = env.get("RATE_LIMIT_DEFAULT", "120/minute")
        out.append(
            t["rl"].format(
                read=spec.rate_limits.read or default, write=spec.rate_limits.write or default
            )
            + "\n"
        )
    out.append(_examples(spec, base_url, base, lang, env, specs))
    if spec.actions:
        out.append(f"{t['actions']}:\n")
    for a in spec.actions:
        path = f"{base}/{{id}}/{a.name}" if a.scope == "item" else f"{base}/{a.name}"
        parts = [t["action_bg"].format(p=jobs_prefix) if a.background else t["action_sync"]]
        if a.fields:
            fields = ", ".join(
                f"`{n}` ({_field_type(f, lang, specs)}{'' if f.required else ', opt.'})"
                for n, f in a.fields.items()
            )
            parts.append(t["action_body"].format(fields=fields))
        else:
            parts.append(t["action_no_body"])
        if a.rate_limit:
            parts.append(t["action_rate"].format(rate=a.rate_limit))
        out.append(f"- `POST {path}`: " + "; ".join(parts) + ".")
    if spec.actions:
        out.append("")
    return "\n".join(out)


def _call_name(node: ast.Call) -> str:
    func = node.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


def _literal_text(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):  # f-string: se muestra con … en lo variable
        return "".join(
            v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else "…"
            for v in node.values
        )
    return None


def _status_code(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return str(node.value)
    if isinstance(node, ast.Attribute):  # status.HTTP_409_CONFLICT
        m = re.match(r"HTTP_(\d{3})", node.attr)
        return m.group(1) if m else None
    return None


def custom_errors(base: Path) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Errores propios: `APIError(status, "msg", code="...")` de app/hooks/ y los
    mensajes de `TaskError("...")` de app/tasks/resources/ (los ve el cliente)."""
    api_errors: dict[tuple[str, str], str] = {}
    task_errors: list[str] = []
    for folder, kind in (("app/hooks", "api"), ("app/tasks/resources", "task")):
        for path in sorted((base / folder).glob("*.py")):
            if path.name == "__init__.py":
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = _call_name(node)
                if kind == "api" and name == "APIError":
                    code = next(
                        (_literal_text(k.value) for k in node.keywords if k.arg == "code"), None
                    )
                    status = _status_code(node.args[0]) if node.args else None
                    message = _literal_text(node.args[1]) if len(node.args) > 1 else None
                    if code and status:
                        api_errors.setdefault((status, code), message or "")
                elif kind == "task" and name == "TaskError" and node.args:
                    message = _literal_text(node.args[0])
                    if message and message not in task_errors:
                        task_errors.append(message)
    rows = [(status, code, msg) for (status, code), msg in sorted(api_errors.items())]
    return rows, task_errors


def readme_settings(base: Path) -> dict[str, str]:
    """Idioma y URL base guardados en el marcador de inicio del README actual."""
    path = base / "README.md"
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    m = _START_RE.search(text)
    if m is None:
        return {}
    found = dict(re.findall(r"(\w+)=(\S+)", m.group("attrs")))
    if "lang" not in found:
        # README anterior al marcador con idioma: se deduce del texto generado.
        found["lang"] = "es" if "## Características" in text or "## Autenticación" in text else "en"
    return found


_POSTMAN = {
    "en": (
        "### Postman\n\n"
        "Import `docs/postman/API.postman_collection.json` into Postman. Set the collection "
        "variables `baseUrl`, `email` and `password` (use *Current value*), run **Auth > Login** "
        "and every other request is sent with `Bearer {{accessToken}}`; the token is refreshed "
        "automatically before it expires. The **Account** folder covers password reset and email "
        "verification: paste the token from the email link (after `#token=`) into `resetToken` "
        "or `verifyToken`.\n"
    ),
    "es": (
        "### Postman\n\n"
        "Importa `docs/postman/API.postman_collection.json` en Postman. Ajusta las variables de la "
        "colección `baseUrl`, `email` y `password` (en *Current value*), ejecuta **Auth > Login** "
        "y el resto de peticiones van con `Bearer {{accessToken}}`; el token se renueva solo "
        "antes de caducar. La carpeta **Account** cubre la recuperación de contraseña y la "
        "verificación del email: pega el token del enlace del correo (lo que va tras `#token=`) "
        "en `resetToken` o `verifyToken`.\n"
    ),
}


def render_docs(base: Path, lang: str = "en", base_url: str = DEFAULT_BASE_URL) -> str:
    """Contenido generado (entre marcadores)."""
    t = T[lang]
    env = read_env_example(base)
    specs = load_all_specs(base)
    versions = version_info(base) or {"v1": {"deprecated": False, "sunset": None}}
    api_prefix = env.get("API_PREFIX", "/api") or "/api"
    active = [v for v, i in versions.items() if not i["deprecated"]] or list(versions)
    latest = sorted(active, key=lambda v: int(v[1:]))[-1]
    p = f"{api_prefix}/{latest}"
    has_jobs = any(a.background for s in specs.values() for a in s.actions)
    access = env.get("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
    page = {
        "maxp": env.get("PAGE_SIZE_MAX", "100"),
        "defp": env.get("PAGE_SIZE_DEFAULT", "20"),
        "maxo": env.get("MAX_OFFSET", "10000"),
    }

    account = docs_accounts.account_settings(base, env)
    mode, reset = docs_accounts.modes(account)
    mail_flows = mode != "off" or reset
    ta = docs_accounts.T[lang]

    parts = [f"<!-- apigen:docs:start lang={lang} base_url={base_url} -->", ""]
    feats = (
        t["feat_list"]
        + ([ta["feature"]] if mail_flows else [])
        + ([t["feat_jobs"]] if has_jobs else [])
    )
    parts.append(f"## {t['features']}\n\n" + "\n".join(f"- {f}" for f in feats) + "\n")

    # --- Para integrar (frontend / móvil) -----------------------------------------------
    parts.append(f"## {t['integrate']}\n\n" + t["integrate_body"].format(base=base_url, p=p))
    expires = str(int(access) * 60) if access.isdigit() else "900"
    first_steps = t["first_steps_body"].format(base=base_url, p=p, expires=expires)
    if mode != "off":
        # Con verificación, el registro responde 202 igual para cualquier email.
        first_steps = re.sub(
            r"   `201` → `\{.*?\}`\n", lambda _m: ta["register_202"], first_steps, flags=re.S
        )
    parts.append(f"### {t['first_steps']}\n\n" + first_steps)
    parts.append(
        f"### {t['auth']}\n\n"
        + t["auth_body"].format(
            p=p, access=access, refresh=env.get("REFRESH_TOKEN_EXPIRE_DAYS", "7")
        )
    )
    if (base / "docs/postman/API.postman_collection.json").exists():
        parts.append(_POSTMAN[lang])
    parts.append(f"### {t['pagination']}\n\n" + t["pagination_body"].format(**page))
    err_rows = list(t["err_rows"]) + (ta["err_rows"] if mail_flows else [])
    err = "\n".join(f"| {a} | `{b}` | {c} |" for a, b, c in err_rows)
    parts.append(
        f"### {t['errors']}\n\n{t['errors_body']}\n| HTTP | code | |\n|---|---|---|\n{err}\n"
    )
    own, task_messages = custom_errors(base)
    if own:
        rows = "\n".join(f"| {s} | `{c}` | {m} |" for s, c, m in own)
        parts.append(
            f"#### {t['custom_errors']}\n\n{t['custom_errors_body']}\n"
            f"| HTTP | code | detail |\n|---|---|---|\n{rows}\n"
        )
    parts.append(f"### {t['accounts']}\n\n" + t["accounts_body"].format(p=p))
    if mail_flows:
        parts.append(docs_accounts.account_section(account, lang, p))

    parts.append(f"### {t['resources']}\n")
    for version in sorted(versions, key=lambda v: int(v[1:]), reverse=True):
        info = versions[version]
        in_version = [s for s in specs.values() if version in s.versions]
        parts.append(f"#### {t['version']} `{version}` — `{api_prefix}/{version}`\n")
        if info["deprecated"]:
            parts.append(t["deprecated"].format(sunset=info.get("sunset") or "—") + "\n")
        if not in_version:
            parts.append(t["no_resources"])
        for spec in sorted(in_version, key=lambda s: s.plural):
            parts.append(
                _resource_section(
                    spec,
                    f"{api_prefix}/{version}",
                    lang,
                    env,
                    specs,
                    base_url,
                    f"{api_prefix}/{version}",
                )
            )
    if has_jobs:
        jobs = f"### {t['jobs']}\n\n" + t["jobs_body"].format(
            p=p, pending=env.get("JOBS_MAX_PENDING_PER_USER", "20")
        )
        if task_messages:
            jobs += f"\n{t['task_errors']}: " + ", ".join(f"`{m}`" for m in task_messages) + ".\n"
        parts.append(jobs)
    parts.append(
        f"### {t['limits']}\n\n"
        + t["limits_body"].format(
            default=env.get("RATE_LIMIT_DEFAULT", "120/minute"),
            glob=env.get("RATE_LIMIT_GLOBAL", "1000/minute"),
            login=env.get("RATE_LIMIT_LOGIN", "10/minute;50/hour"),
            register=env.get("RATE_LIMIT_REGISTER") or "5/hour",
        )
    )

    # --- Para desplegar y para desarrollar ------------------------------------------
    parts.append(f"## {t['deploy_title']}\n")
    parts.append(f"### {t['quick']}\n\n{t['quick_body']}")
    cfg_rows = list(t["cfg_rows"]) + (ta["cfg_rows"] if mail_flows else [])
    rows = "\n".join(f"| `{k}` | {v} |" for k, v in cfg_rows)
    parts.append(f"### {t['config']}\n\n{t['config_body']}\n\n| Variable | |\n|---|---|\n{rows}\n")
    if mail_flows:
        parts.append(f"### {ta['deliver_title']}\n\n{ta['deliver_body']}")
    parts.append(f"### {t['deploy']}\n\n{t['deploy_body']}")
    parts.append(
        f"## {t['local']}\n\n"
        + t["local_body"].replace("{worker}", t["worker_line"] if has_jobs else "")
    )
    parts.append(t["generated"] + "\n")
    parts.append(END)
    return "\n".join(parts)


def write_readme(
    base: Path, lang: str | None = None, title: str | None = None, base_url: str | None = None
) -> tuple[Path, bool, str]:
    """Crea o actualiza README.md. Devuelve (ruta, creado, idioma).

    Sin `lang`/`base_url` se usan los guardados en el README (o `en` y localhost)."""
    path = base / "README.md"
    saved = readme_settings(base)
    lang = lang or saved.get("lang", "en")
    if lang not in T:
        lang = "en"
    base_url = (base_url or saved.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
    generated = render_docs(base, lang, base_url)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    m = _START_RE.search(text)
    if m and END in text[m.end() :]:
        head, rest = text[: m.start()], text[m.end() :]
        _, _, tail = rest.partition(END)
        path.write_text(head + generated + tail, encoding="utf-8")
        return path, False, lang
    env = read_env_example(base)
    name = title or env.get("PROJECT_NAME") or base.name
    intro = env.get("PROJECT_DESCRIPTION") or T[lang]["intro"]
    content = f"# {name}\n\n{intro}\n\n{generated}\n\n{T[lang]['contact']}"
    path.write_text(content, encoding="utf-8")
    return path, True, lang
