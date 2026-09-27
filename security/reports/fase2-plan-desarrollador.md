# Fase 2 — Plan técnico del desarrollador: correo, verificación de email y recuperación de contraseña

- **Fecha:** 2026-09-26
- **Estado:** propuesta de diseño para discutir con el experto en seguridad y el usuario. **Sin código ni commits.**
- **Punto de partida (leído con graphify + líneas concretas):** `app/api/v1/endpoints/auth.py` (register/login/refresh/logout/logout-all), `app/api/v1/endpoints/users.py::change_password`, `app/services/auth.py` (`authenticate`, smart lockout, `_is_familiar`, `revoke_all_sessions`), `app/models/user.py`, `app/core/config.py` (`Settings`, `_check_security`, `PROCESS_ROLE`), `app/tasks/{registry,queue,worker}.py` (reintentos con `backoff_seconds`, `TaskError(retry=)`), `app/core/rate_limit.py`, `app/core/security.py` (`hash_token`), `apigen/cli.py` (`init-env`, `db prune`), `scripts/new_api.py`, `apigen/docs.py`, `docs/postman/API.postman_collection.json`, `docker-compose.yml`.

## 0. Principios que condicionan el diseño

1. **Todo configurable por cliente y nada del freelancer.** Remitente, marca, URL del frontend, SMTP e idioma salen del `.env` del cliente. Los valores por defecto son vacíos o de `example.com`. `new_api.py` ya aborta si encuentra emails reales o `*PASSWORD=` con valor en ficheros versionados (SEC-35), así que la configuración real nunca llega al repo.
2. **Desactivado por defecto = compatible.** Con la configuración por defecto (`EMAIL_VERIFICATION=off`), una API ya entregada se comporta igual que hoy. Solo cambia algo de forma aditiva: columna nueva, campo `email_verified` en `UserRead` y endpoints nuevos.
3. **La API no envía correo, solo encola.** Buscar al usuario, generar el token, renderizar y enviar son trabajo del worker. Hay tres consecuencias:
   - el tiempo de respuesta de `forgot-password` no depende de si el email existe;
   - las credenciales SMTP solo las necesita el worker (mínimo privilegio, en la línea de SEC-38);
   - el enlace no puede construirse a partir del `Host`: el worker no tiene petición HTTP.
4. **El token en claro nunca se guarda.** No va en la tabla de tokens (solo su SHA-256), ni en el payload del trabajo, ni en los logs. Lo genera el worker justo antes de enviar.
5. **Cero dependencias nuevas de ejecución** (ver §8).

---

## 1. Modelo de datos

### 1.1 Decisión: tabla de tokens de un solo uso (y no campos en `users`)

| Opción | Pros | Contras |
|---|---|---|
| Campos en `users` (`reset_token_hash`, `reset_expires_at`…) | Simple | Un campo por propósito. No hay historial para limitar envíos por hora, y un segundo enlace pisa al primero, lo que rompe los reintentos (§3.5). Además ensancha `users`. |
| Token firmado sin estado (HMAC de `password_hash` + fecha, al estilo Django) | Sin tabla | Necesita un secreto en el worker, que hoy recibe `SECRET_KEY=""` (SEC-38). No permite limitar envíos, no deja rastro y no se puede revocar uno concreto. |
| **Tabla `account_tokens`** ✅ | Sirve para varios propósitos. El consumo atómico (`UPDATE … WHERE used_at IS NULL`) evita el doble uso. El historial permite limitar envíos. `db prune` la limpia. | Una tabla y una migración más |

### 1.2 `app/models/account_token.py`

```python
class TokenPurpose(StrEnum):
    password_reset = "password_reset"
    email_verify = "email_verify"
    email_change = "email_change"


class AccountToken(IDMixin, table=True):
    __tablename__ = "account_tokens"
    __table_args__ = (
        Index("ix_account_tokens_user_purpose_created", "user_id", "purpose", "created_at"),
    )

    user_id: uuid.UUID = Field(foreign_key="users.id", ondelete="CASCADE")
    purpose: str = Field(max_length=20)
    token_hash: str = Field(max_length=64, unique=True)  # sha256 hex (hash_token)
    # Email al que se envió. Si al consumirlo users.email ya es otro, el token no vale.
    # En email_change es la dirección NUEVA.
    email: str = Field(max_length=320)
    created_at: datetime = Field(default_factory=utcnow, sa_type=UTCDateTime, nullable=False)
    expires_at: datetime = Field(sa_type=UTCDateTime, nullable=False, index=True)
    used_at: datetime | None = Field(default=None, sa_type=UTCDateTime)
```

- **Formato del token:** `secrets.token_urlsafe(32)` (256 bits) con un prefijo por propósito: `pr_`, `ev_`, `ec_`. El prefijo permite rechazar sin consultar la BD un token del tipo equivocado. Como en los refresh tokens, basta SHA-256 sin sal: la entropía hace inútil la fuerza bruta offline. El worker no necesita `SECRET_KEY`.
- **Sin IP** en la tabla: la IP ya va al log de auditoría y así no amplío la retención de datos personales que controla `db prune`.
- **Varios tokens válidos a la vez por propósito**, todos con caducidad corta. Consumir uno invalida los demás del mismo usuario y propósito. Evita que un reintento del worker (§3.5) o un segundo "no me llegó" deje sin validez el enlace que el usuario tiene abierto.

### 1.3 Cambios en `users`

- `email_verified_at: datetime | None` (UTCDateTime).
- **Usuarios existentes:** la migración hace `UPDATE users SET email_verified_at = created_at`. Se les da por verificados; si no, activar `EMAIL_VERIFICATION=required` en una API en producción dejaría fuera a todos. Si un cliente quiere forzar que todos se verifiquen de nuevo, basta con un comando explícito (§6.4, opcional).
- `apigen createsuperuser` y `POST /users` (alta por un admin) marcan `email_verified_at = now`: el alta la hace alguien de confianza.
- `UserRead` gana `email_verified: bool` (derivado). `UserAdminRead` gana `email_verified_at`. Ambos cambios son aditivos.
- **No** añado `users.locale` en esta fase: el idioma del correo sale de la petición (§3.6). Es fácil de añadir más adelante si un cliente lo pide.

### 1.4 Migración

`alembic/versions/2026xxxx_account_tokens_email_verified.py`: `create_table account_tokens` con sus índices, `add_column users.email_verified_at` (nullable, con `batch_alter_table` para SQLite) y el `UPDATE` de relleno. El `downgrade` borra la tabla y la columna.

### 1.5 Limpieza

`apigen db prune` también borra de `account_tokens` los tokens caducados o usados hace más de 24 h (`prune_account_tokens()` en `app/services/account_tokens.py`).

---

## 2. Endpoints

Los códigos de error siguen el formato actual de `APIError(code=...)`, así `apigen docs` los recoge. En los endpoints por email, la respuesta es siempre la misma exista o no la cuenta.

### 2.1 Tabla

| Método y ruta | Auth | Cuerpo | Respuesta | Errores | Rate limit (clave IP) |
|---|---|---|---|---|---|
| `POST /auth/password/forgot` | pública | `{"email"}` | **202** `{"detail":"If an account exists for that email, we have sent instructions"}` | 403 `password_reset_disabled`, 415, 422, 429 | `RATE_LIMIT_EMAIL_REQUEST` (None → `5/hour` en prod, `50/hour` fuera) |
| `POST /auth/password/reset` | pública | `{"token","new_password"}` | **204** | 400 `invalid_token`, 422 `password_policy`, 429 | `RATE_LIMIT_TOKEN_CONFIRM` (`10/minute;50/hour`) |
| `POST /auth/email/verify` | pública | `{"token"}` | **204** | 400 `invalid_token`, 409 `email_taken` (solo en cambio de email), 429 | `RATE_LIMIT_TOKEN_CONFIRM` |
| `POST /auth/email/verify/resend` | pública | `{"email"}` | **202** (mismo texto genérico) | 403 `email_verification_disabled`, 429 | `RATE_LIMIT_EMAIL_REQUEST` |
| `POST /users/me/email` | user + scope write | `{"new_email","current_password"}` | **202** `{"detail":"Check your new inbox to confirm the change"}` | 400 `wrong_password`, 400 `same_email`, 409 `email_taken`, 429 | `RATE_LIMIT_LOGIN` (como `change_password`) |

- **Un solo `verify`** para los dos casos, verificar el alta y confirmar un cambio de email: el prefijo del token (`ev_` o `ec_`) decide qué se hace. El frontend necesita una única pantalla.
- **POST y no GET** para consumir tokens. Los escáneres de enlaces del correo (Outlook Safe Links, antivirus corporativos) hacen GET a los enlaces: consumirían el token de un reset o confirmarían un cambio de email sin que el usuario lo sepa. El enlace del correo apunta al **frontend** del cliente, que lee el token y hace el POST.
- **Un único código `invalid_token`** para "no existe, caducado o ya usado". El usuario solo puede hacer una cosa en cualquiera de los tres casos: pedir otro enlace. Un código distinto para "caducado" no aporta y da información a quien prueba tokens.
- **`include_in_schema`** depende de la configuración. Si el reset o la verificación están desactivados, no aparecen en `/docs` ni en el README del cliente. En tiempo de ejecución responden 403, con el mismo patrón que `ALLOW_REGISTRATION`.

### 2.2 `forgot` y `resend`: trabajo constante en la API

```python
@router.post("/password/forgot", status_code=202, ...)
@limiter.limit(settings.RATE_LIMIT_EMAIL_REQUEST, key_func=ip_key)
async def forgot_password(request, response, payload: EmailRequest, session) -> Accepted:
    _require_feature(settings.password_reset_enabled, "password_reset_disabled")
    await enqueue(session, "auth.password_reset", {"email": payload.email, "lang": request_lang(request)},
                  priority=10)
    audit("auth.password.reset_requested", client_ip=client_ip(request))   # sin email
    return GENERIC_ACCEPTED
```

- La API no consulta `users`: cada petición cuesta un `INSERT` en `jobs`, así que la respuesta no revela si la cuenta existe (ni por el contenido ni por el tiempo).
- **La búsqueda, el filtro y el límite por cuenta los hace el worker.** No se envía nada si la cuenta no existe o está inactiva, ni si ya se generó un token del mismo propósito hace menos de `EMAIL_TOKEN_COOLDOWN_SECONDS` (60) o hay más de `EMAIL_TOKEN_MAX_PER_HOUR` (5) en la última hora. Cada descarte queda en auditoría (`auth.email.throttled`, `reason=...`) con `user_id` si lo hay. Esto limita el bombardeo de correo a una víctima aunque el atacante reparta las peticiones entre muchas IP.
- Los trabajos de auth se encolan con `owner_id=None`: no aparecen en `/jobs` del usuario ni cuentan para `JOBS_MAX_PENDING_PER_USER`. Llevan `priority=10` para no esperar detrás de exportaciones pesadas.
- **Payload sensible:** añado `scrub_payload: bool = False` a `@task`/`TaskDef`. Al llegar a un estado final (`succeeded`/`failed`), `queue.complete/fail` sustituye el payload por `{}`. Así, en `jobs` no quedan emails durante los `JOBS_RETENTION_DAYS` y un admin que consulte `/jobs` no los ve. Son unas 10 líneas en `registry.py` y `queue.py`.

### 2.3 `reset`: orden de operaciones y consumo atómico

1. Se comprueba el formato y el prefijo `pr_` del token. Si falla, 400 `invalid_token` sin tocar la BD.
2. Se busca por `token_hash` con `purpose=password_reset`, `used_at IS NULL` y `expires_at > now`. El usuario debe estar activo, su email debe coincidir con `token.email` y, si existe `password_changed_at`, el token tiene que ser posterior. Esto último invalida los tokens emitidos antes de un cambio de contraseña. Si algo falla, 400 `invalid_token`.
3. `password_problems(new_password, user.email)`. Si hay problemas, **422 con el mismo formato que `change_password`, sin consumir el token**: el usuario puede corregir la contraseña con el mismo enlace.
4. `session.commit()` para liberar la conexión, y después Argon2 (`hash_password`), igual que en `register` y `change_password`.
5. **Consumo atómico:** `UPDATE account_tokens SET used_at=now WHERE id=:id AND used_at IS NULL RETURNING id`. Con 0 filas, 400 `invalid_token`: ganó otra petición concurrente.
6. En la misma transacción:
   - se actualiza el usuario: `hashed_password`, `password_changed_at=now`, `failed_login_attempts=0`, `locked_until=None` y `email_verified_at = coalesce(email_verified_at, now)`, porque el reset demuestra que controla el buzón;
   - se marcan usados los demás `password_reset` del usuario.
7. `revoke_all_sessions(session, user)`: sube `token_version` y revoca los refresh tokens, igual que `change_password`.
8. Se encola `auth.security_notice` con `kind="password_changed"` y se audita `auth.password.reset` con `user_id` e IP.

### 2.4 Encaje con los endpoints actuales

| Endpoint actual | Cambio |
|---|---|
| `POST /auth/register` | Si `EMAIL_VERIFICATION != off`, encola `auth.email_verification` en la **misma transacción** que el alta (`enqueue(..., commit=False)` antes del `commit`), así que no puede quedar un usuario sin su correo. La respuesta sigue siendo 201 `UserRead`, ahora con `email_verified:false`. |
| `POST /auth/login` | Con `required`, si el usuario no está verificado, el login responde **403 `email_not_verified`** y no emite tokens. Esa comprobación va **después** de validar la contraseña y el lockout, así que no revela nada a quien no conoce la contraseña. Con `optional` y `off` no cambia nada. |
| `POST /auth/refresh` | Con `required`, `rotate_refresh_token` también rechaza a los no verificados. Si no, al pasar de `off` a `required` las sesiones ya abiertas seguirían 7 días. En la práctica solo afecta a cuentas creadas con `optional`, porque las existentes se verifican en la migración. |
| `POST /users/me/password` | Además de lo actual, marca como usados los `password_reset` pendientes y encola el aviso `password_changed`. |
| `POST /auth/logout-all` | Sin cambios. |
| **Smart lockout** | Pedir un reset no afecta al contador de fallos. Un reset correcto **desbloquea** la cuenta, así que un atacante que la bloquea a propósito no impide que el titular recupere el acceso. Como `password_changed_at` pasa a "ahora", `_is_familiar` deja de eximir las IP de los logins anteriores al reset, que es lo que queremos si la contraseña antigua estaba comprometida. |
| `PATCH /users/me` | Sin cambios. El email **no** se puede cambiar por aquí; hay que usar `POST /users/me/email`. |
| Dependencias | Nueva `VerifiedUser` (`require_verified`) en `app/api/deps.py` para hooks y endpoints propios en modo `optional`. **No** añado un nivel `verified` al YAML de `apigen` en esta fase, porque implica cambiar el generador y sus plantillas. Queda como propuesta para la siguiente. |

### 2.5 Cambio de email (lo incluyo: sin él, un email mal escrito no se puede corregir y con verificación obligatoria la cuenta se pierde)

- **`POST /users/me/email`:**
  - verifica `current_password` y, si falla, 400 `wrong_password`;
  - normaliza `new_email` a minúsculas;
  - si es igual al email actual, 400 `same_email`;
  - si ya está registrado, **409 `email_taken`**, la misma política de enumeración que `register`, aceptada y documentada;
  - si todo va bien, encola `auth.email_change` con `user_id`, `new_email` y `lang`, y responde 202.
- **El worker:**
  - crea un token `ec_` con `email=new_email` y lo envía a la dirección **nueva**;
  - envía a la dirección **antigua** un aviso sin enlace ("Se ha pedido cambiar el email de tu cuenta a n\*\*\*@dominio; si no has sido tú, cambia tu contraseña").
- **La confirmación, con `POST /auth/email/verify`:**
  - dentro de la transacción se vuelve a comprobar que `new_email` sigue libre; la restricción `UNIQUE` de `users.email` es la red de seguridad y su violación se traduce en 409 `email_taken`;
  - se actualizan `email` y `email_verified_at=now`;
  - se marcan usados todos los tokens del usuario, porque los de reset estaban ligados al email antiguo;
  - se ejecuta `revoke_all_sessions` y se audita `auth.email.changed`.
- **Opcional (lo decide el experto):** que el enlace del aviso a la dirección antigua permita revertir el cambio. Hoy lo dejo fuera por complejidad.

### 2.6 Enumeración en el registro (decisión para el experto)

Con la verificación activa, hay una forma de cerrar la enumeración del registro, hoy aceptada: `REGISTER_HIDE_EXISTING=true`. Con esa opción:

- un email existente responde lo mismo que uno nuevo: **202** `{"detail":"Check your inbox"}`, en vez de 201 con `UserRead`;
- el titular recibe un aviso de que ya tiene una cuenta, con un enlace al reset.

Cambia el contrato de la respuesta, así que propongo que **esté desactivado por defecto** y solo se permita con `EMAIL_VERIFICATION=required`. La validación de la configuración lo impone.

---

## 3. Subsistema de correo (`app/email/`)

### 3.1 Estructura

```
app/email/
  __init__.py        # send_email(): helper público para hooks
  message.py         # EmailMessage (dataclass) y construcción MIME
  backends/
    base.py          # Protocolo EmailBackend y excepciones
    console.py  file.py  memory.py  smtp.py
  render.py          # Jinja: loader con overrides, sandbox y autoescape
  links.py           # build_link(kind, token) desde FRONTEND_URL
  templates/{en,es}/ # plantillas incluidas
app/tasks/email.py   # @task email.send, auth.password_reset, auth.email_verification,
                     # auth.email_change y auth.security_notice
app/services/account_tokens.py  # issue(), consume(), throttle(), prune()
```

### 3.2 Interfaz de backend

```python
@dataclass(frozen=True, slots=True)
class EmailMessage:
    to: tuple[str, ...]  # 1..EMAIL_MAX_RECIPIENTS (10)
    subject: str  # una línea: se eliminan CR/LF y se recorta a 200
    text: str
    html: str | None = None
    reply_to: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict)  # solo X-* permitidas
    message_id: str | None = None  # <job_id@dominio-remitente>: igual en cada reintento


class EmailBackend(Protocol):
    name: str

    async def send(self, message: EmailMessage) -> str | None: ...  # id del proveedor, si lo hay


class TransientEmailError(Exception): ...  # red, 4xx SMTP → se reintenta (backoff de la cola)


class PermanentEmailError(Exception): ...  # 5xx, destinatario rechazado, auth → no se reintenta
```

- El MIME se construye con `email.message.EmailMessage(policy=email.policy.SMTP)`, que rechaza CR/LF en las cabeceras (inyección). Si hay HTML, el mensaje es `multipart/alternative` con texto y HTML. Lleva `Date` y `Message-ID`, y el `From` es siempre `EMAIL_FROM`: una plantilla o un hook no pueden cambiarlo.
- `get_backend()` lo resuelve una sola vez según `settings.EMAIL_BACKEND`.

### 3.3 Backends

| Backend | Uso | Detalle |
|---|---|---|
| `console` | Desarrollo (defecto en `development`) | Escribe el mensaje en el logger `app.email`, con el enlace. **Prohibido en producción** (validación). |
| `file` | Desarrollo sin Docker o demos | Escribe `.eml` en `EMAIL_FILE_DIR` (defecto `var/outbox/`, en `.gitignore` y `.dockerignore`) con un nombre aleatorio, permisos 0600 y `O_EXCL`, siguiendo el patrón del latido (SEC-36). Prohibido en producción. |
| `memory` | Tests (defecto en `testing`) | `app.email.backends.memory.outbox: list[EmailMessage]`. |
| `smtp` | Producción | **`smtplib` de la biblioteca estándar ejecutado con `anyio.to_thread.run_sync`**, con timeout de socket `SMTP_TIMEOUT` (10 s). `SMTP_SECURITY=starttls` (587, por defecto), `ssl` (465) o `none` (Mailpit). Usa `ssl.create_default_context()`, que verifica certificado y nombre y no se puede desactivar. Traduce `SMTPResponseException`: 4xx a transitorio y 5xx a permanente. Abre una conexión por mensaje: a este volumen no merece la pena un pool. |
| `disabled` | Clientes sin correo | `send()` lanza `PermanentEmailError`. Con este backend no se puede activar el reset ni la verificación (validación). |

- **¿`aiosmtplib`?** Descartado por ahora. `smtplib` en un hilo cubre el caso sin dependencias. Lo único que se pierde es cancelar a mitad: si la tarea vence, el hilo termina solo cuando salta el timeout del socket, 10 s como mucho. Si más adelante hay mucho volumen, cambiarlo solo afecta a `smtp.py`.
- **¿Backends HTTP (SES API, Postmark, Resend, SendGrid, Mailgun, Brevo)?** **No en esta fase.** Todos ofrecen relay SMTP con usuario y clave, que es lo que un cliente sabe configurar, y el backend SMTP ya los cubre. Además exigirían mover `httpx` a dependencias de ejecución. Dejo el punto de extensión: `EMAIL_BACKEND=custom` + `EMAIL_BACKEND_CLASS=app.<módulo>:<Clase>`, que tiene que estar dentro del paquete `app.` del proyecto y se valida al arrancar. Así un cliente concreto puede añadir su proveedor sin tocar la plantilla.

### 3.4 Configuración (`Settings`, sección "Correo") y validación

```ini
EMAIL_BACKEND=                 # console|file|memory|smtp|disabled|custom. Vacío: testing→memory,
                               # development→console, production→obligatorio (error si falta)
EMAIL_FROM=                    # "Acme <no-reply@acme.example>". Se valida con parseaddr y EmailStr
EMAIL_REPLY_TO=
EMAIL_FILE_DIR=var/outbox
SMTP_HOST=  SMTP_PORT=587  SMTP_USERNAME=  SMTP_PASSWORD=(SecretStr)
SMTP_SECURITY=starttls  SMTP_TIMEOUT=10
FRONTEND_URL=                  # https://app.acme.example (origen del frontend del cliente)
EMAIL_LINK_RESET_PASSWORD=/reset-password#token={token}
EMAIL_LINK_VERIFY_EMAIL=/verify-email#token={token}
EMAIL_TEMPLATES_DIR=email_templates
EMAIL_LANGUAGES=en,es          # idiomas disponibles; el primero es el de por defecto
EMAIL_BRAND_NAME=              # vacío → PROJECT_NAME
EMAIL_BRAND_URL=               # vacío → FRONTEND_URL
EMAIL_BRAND_LOGO_URL=  EMAIL_BRAND_COLOR=#2563eb  EMAIL_SUPPORT_EMAIL=
EMAIL_VERIFICATION=off         # off|optional|required
PASSWORD_RESET_ENABLED=        # vacío → true si hay backend de correo utilizable
REGISTER_HIDE_EXISTING=false
PASSWORD_RESET_TOKEN_MINUTES=30  (ge=5, le=120)
EMAIL_VERIFY_TOKEN_HOURS=48      (ge=1, le=168)
EMAIL_CHANGE_TOKEN_MINUTES=60    (ge=5, le=1440)
EMAIL_TOKEN_COOLDOWN_SECONDS=60  EMAIL_TOKEN_MAX_PER_HOUR=5
RATE_LIMIT_EMAIL_REQUEST=      # vacío → 5/hour en prod, 50/hour fuera
RATE_LIMIT_TOKEN_CONFIRM=10/minute;50/hour
```

**Validaciones** (en `_check_security`, separadas por rol como hace hoy `_api_production_problems`):

- **Siempre, con el reset o la verificación activos:**
  - `FRONTEND_URL` es obligatorio y debe ser una URL absoluta sin usuario ni contraseña, sin query y sin fragmento;
  - cada `EMAIL_LINK_*` empieza por `/` y contiene `{token}` **exactamente una vez**, lo que impide que un valor de enlace cambie el host;
  - `EMAIL_FROM` es obligatorio;
  - con `EMAIL_BACKEND=disabled` estas funciones no se pueden activar;
  - `REGISTER_HIDE_EXISTING` exige `EMAIL_VERIFICATION=required`.
- **En producción, para la API y el worker:**
  - `FRONTEND_URL` debe ser `https`;
  - `EMAIL_BACKEND` no puede ser `console`, `file` ni `memory`;
  - aviso si el origen de `FRONTEND_URL` no está en `CORS_ORIGINS`.
- **En producción, solo para el worker (`PROCESS_ROLE=worker`), que es quien envía:**
  - con `smtp`, `SMTP_HOST` es obligatorio;
  - `SMTP_SECURITY=none` es un error salvo que el host sea loopback;
  - `SMTP_USERNAME` sin `SMTP_PASSWORD` también es un error.
- **`apigen check`** muestra el backend activo, el remitente y el modo de verificación, pero nunca la contraseña SMTP.

### 3.5 Envío por la cola: tareas, reintentos e idempotencia

```python
@task("email.send", max_attempts=5, timeout=60, payload_model=SendEmailPayload, scrub_payload=True)
async def send(ctx, payload): ...  # genérico: to, template, context, lang


@task("auth.password_reset", max_attempts=5, timeout=60, scrub_payload=True)
async def password_reset(ctx, payload): ...  # email, lang → busca, limita, emite, envía


# y lo mismo para auth.email_verification (user_id, lang), auth.email_change
# (user_id, new_email, lang) y auth.security_notice (user_id, kind, lang)
```

- **Helper para el código del cliente:**

  ```python
  await send_email(session, to=..., template="order_shipped", context={...}, lang=None, commit=False)
  ```

  Encola `email.send`. Con `commit=False` el correo se envía solo si la transacción del hook se confirma.
- **Validación del payload de `email.send` (`SendEmailPayload`):**
  - `template` debe coincidir con `^[a-z][a-z0-9_]*$` y existir en el conjunto de plantillas conocidas; no se aceptan rutas;
  - `context` es JSON y está acotado por `JOBS_MAX_PAYLOAD_BYTES`;
  - `to` admite de 1 a `EMAIL_MAX_RECIPIENTS` direcciones, validadas como `EmailStr`.
- **Reintentos:**
  - `TransientEmailError` y cualquier otro error de red se propagan, y el worker reintenta con el backoff actual (10 s, 20 s, 40 s… hasta 10 min);
  - `PermanentEmailError` se convierte en `TaskError("Email rejected by the server", retry=False)`, un mensaje genérico sin destinatario ni respuesta del servidor. El detalle va al log `app.email` con el destinatario enmascarado (`n***@acme.example`).
- **Idempotencia.** SMTP entrega *al menos una vez*: si el servidor acepta el mensaje y el worker muere antes de `complete()`, al reintentar sale un duplicado. Lo mitigo así:
  - el `Message-ID` es `<{job_id}@{dominio de EMAIL_FROM}>`, igual en todos los reintentos, y los clientes de correo (Gmail entre ellos) agrupan o descartan duplicados por `Message-ID`;
  - en los correos de auth, cada intento emite un token nuevo, pero **los anteriores siguen valiendo** hasta caducar o hasta que se consume uno (§1.2), así que si llegan dos correos funcionan los dos enlaces;
  - antes de emitir, el worker comprueba el límite por cuenta, de modo que un reintento del **mismo** trabajo no cuenta como una solicitud nueva (se compara `ctx.attempt > 1`).
- **Logs y auditoría:**
  - `app.email` registra `job_id`, plantilla, backend, id del proveedor y el dominio del destinatario, nunca el cuerpo ni el enlace; la excepción es `console`, que solo existe fuera de producción;
  - `audit()` registra `auth.email.sent` y `auth.email.throttled` con `user_id`, sin email, igual que hoy.

### 3.6 Plantillas

- **Motor:** `jinja2.sandbox.SandboxedEnvironment` (Jinja2 ya es dependencia).
  - Autoescape según la extensión: activado en `.html`, desactivado en `.txt`.
  - `StrictUndefined`, para que una variable que falte sea un error de test y no un hueco en el correo.
  - Uso el sandbox porque el cliente podrá editar plantillas sin revisar código; su coste es despreciable.
- **Ficheros por plantilla y por idioma:**
  - `templates/<lang>/<name>.subject.txt`;
  - `templates/<lang>/<name>.txt`, **obligatoria**, porque ayuda a la entrega y a la accesibilidad;
  - `templates/<lang>/<name>.html`, opcional, que hereda de `base.html`: un layout de tablas con estilos en línea, sin recursos externos salvo `EMAIL_BRAND_LOGO_URL` si se configura.
- **Personalización por el cliente sin tocar código:**
  - se usa `ChoiceLoader([FileSystemLoader(EMAIL_TEMPLATES_DIR), FileSystemLoader(app/email/templates)])`;
  - un fichero con el mismo nombre en `email_templates/<lang>/` de la raíz del proyecto sustituye al incluido;
  - `apigen` no toca esa carpeta, igual que `app/hooks/`;
  - una plantilla nueva en `email_templates/` basta para usarla con `send_email(template=...)`.
- **Idioma:**
  - `request_lang(request)` elige el mejor idioma de `Accept-Language` que esté en `EMAIL_LANGUAGES`, y el primero de la lista si no hay coincidencia;
  - se guarda en el payload del trabajo;
  - el orden de búsqueda es `<lang>/<name>`, luego el idioma por defecto y por último `en`, el incluido.
- **Contexto común:**
  - `brand` {name, url, logo_url, color, support_email};
  - `user` {full_name}, que en HTML sale escapada;
  - `action_url`, `expires_minutes`/`expires_hours` y `now`.
  - **No** incluye la IP del solicitante: es un dato personal y ayudaría poco.
- **Incluidas, en inglés y español:** `password_reset`, `verify_email`, `email_change_confirm`, `email_change_notice` (para la dirección antigua), `password_changed` (aviso de seguridad) y `account_exists` (solo con `REGISTER_HIDE_EXISTING`).
  - Sin "powered by" ni referencias al freelancer.
  - `test_email_templates.py` recorre todas las combinaciones.

### 3.7 Construcción segura de enlaces

```python
def build_link(kind: Literal["reset_password", "verify_email"], token: str) -> str:
    path = settings.EMAIL_LINK_RESET_PASSWORD if kind == "reset_password" else ...
    return settings.FRONTEND_URL.rstrip("/") + path.replace("{token}", token)
```

- El único origen es `FRONTEND_URL`, validado al arrancar. El worker no tiene `Request`, así que es **imposible** usar `Host` o `X-Forwarded-Host`, y el test lo comprueba enviando `Host: evil.example`.
- **El token va en el fragmento (`#token=`) por defecto:**
  - el navegador no lo manda al servidor del frontend, así que no queda en sus logs ni en los de un CDN;
  - no se filtra por `Referer`.
- El cliente puede cambiarlo a `?token=` si su frontend lo necesita. El README del cliente recomienda en ese caso `Referrer-Policy: no-referrer` en la página de reset, y que la página borre el token de la URL con `history.replaceState` después de leerlo.
- **Apps móviles:** si `FRONTEND_URL` es un dominio con *universal links* o *App Links*, no hay que hacer nada. Esquemas propios como `miapp://` **no** se admiten en producción, porque cualquier app puede registrarlos.

---

## 4. Impacto en herramientas y entregables

### 4.1 `make new-api` (`scripts/new_api.py`)

`new_api.py` funciona con flags, no con preguntas, y lo mantengo así para que se pueda automatizar. Flags nuevos:

- `--email-verification {off,optional,required}` (defecto `off`);
- `--password-reset / --no-password-reset` (defecto activado si hay correo);
- `--frontend-url URL` (opcional).

Reparto de la configuración:

- **`.env` (no versionado)**, escrito después de `apigen init-env`:
  - `EMAIL_VERIFICATION`, `EMAIL_LANGUAGES` (primero el de `--lang`, que ya existe), `EMAIL_BRAND_NAME=<title>` y `FRONTEND_URL` si se pasó;
  - en desarrollo, `EMAIL_BACKEND=console`.
- **`.env.example` (versionado):** solo marcadores `example.com`. El escáner de SEC-35 sigue siendo la red de seguridad.
- **No** copia plantillas a `email_templates/`. Crea la carpeta con un `README.txt` que explica cómo sobrescribirlas; así el proyecto se beneficia de las mejoras de las plantillas incluidas.
- Añade a `docs/DESARROLLO.txt` y al `CLAUDE.md` del proyecto nuevo una sección sobre correo, `send_email()` y cómo probar con Mailpit.

`apigen init-env --production` añade a su lista de comprobación:

- `EMAIL_BACKEND=smtp`, `SMTP_*`, `EMAIL_FROM` en el dominio del cliente y `FRONTEND_URL`;
- recordatorio de configurar **SPF, DKIM y DMARC** en ese dominio.

### 4.2 Comandos `apigen`

- `apigen email test --to <addr> [--lang es]` envía un correo de prueba **directamente**, sin pasar por la cola, con el backend configurado. Sirve para comprobar el SMTP del cliente en la entrega.
- `apigen email preview <plantilla> [--lang es] [--out f.html]` renderiza con datos de ejemplo. Prioridad media.
- `apigen email eject [<plantilla>] [--lang es]` copia plantillas incluidas a `email_templates/` para personalizarlas. Prioridad media.
- `apigen db prune`: añade la limpieza de `account_tokens`.
- `apigen createsuperuser`: crea el usuario con `email_verified_at=now`.

### 4.3 `apigen docs` (README del cliente)

Secciones nuevas, que solo aparecen si las funciones están activas en `.env` o `.env.example` (según `readme_settings`):

1. **Recuperar la contraseña:** flujo (forgot → correo → frontend → reset), cuerpos, 202/204, `invalid_token`, caducidad y límites leídos de la configuración, y que se cierran todas las sesiones.
2. **Verificación de email:** el modo (`optional` o `required`), `email_verified` en `/users/me`, `email_not_verified` en el login, `resend` y el cambio de email.
3. **Qué tiene que implementar el frontend:**
   - las dos pantallas, sus rutas por defecto y cómo leer el token del fragmento;
   - `Referrer-Policy`;
   - que siempre se muestre el mensaje genérico.
4. **Configurar el envío de correo** (para quien despliega):
   - variables;
   - SMTP de proveedores habituales en forma genérica (puerto 587, STARTTLS);
   - SPF, DKIM y DMARC;
   - `apigen email test`;
   - personalizar plantillas.
5. **Tabla de errores:** añadir `invalid_token`, `email_not_verified`, `same_email`, `password_reset_disabled` y `email_verification_disabled`.

Todo en `en` y `es`, como el resto de `apigen/docs.py`.

### 4.4 Colección Postman (`docs/postman/API.postman_collection.json`)

- **Carpeta Auth:** añadir "Olvidé mi contraseña", "Restablecer contraseña", "Verificar email" y "Reenviar verificación".
- **Carpeta Users:** añadir "Cambiar email".
- **Variables nuevas** `reset_token` y `verify_token`, con una descripción: "cópialo del enlace que verás en Mailpit (`http://localhost:8025`) o en la consola del worker".
- El test de coherencia de la colección, si existe (lo compruebo al implementar), debe contemplar las rutas nuevas.

### 4.5 Tests (sin enviar correos reales)

- **Base:**
  - con `ENVIRONMENT=testing`, el backend por defecto es `memory`;
  - un fixture `outbox` vacía `memory.outbox` en cada test;
  - `process_pending()` (ya existe) ejecuta los trabajos encolados;
  - el helper `token_from(outbox[-1])` extrae el token del enlace.
- **Casos previstos** (unos 40; los números son orientativos):
  - **Reset:**
    - flujo completo;
    - 202 idéntico para email existente, inexistente e inactivo, sin correo en los dos últimos casos;
    - token usado, caducado, de otro propósito o con prefijo falso → 400;
    - 422 de política sin consumir el token;
    - doble consumo concurrente: solo gana una petición;
    - revoca refresh tokens y access tokens (`token_version`);
    - desbloquea una cuenta bloqueada;
    - un token emitido antes de un `change_password` ya no vale;
    - límite por cuenta: cooldown y máximo por hora;
    - se encola el aviso `password_changed`.
  - **Verificación:**
    - `off`, `optional` y `required`: login 403 `email_not_verified` solo con la contraseña correcta; refresh rechazado;
    - `resend` genérico;
    - los usuarios existentes quedan verificados tras la migración (test de la migración con SQLite);
    - el superusuario y el alta por admin quedan verificados.
  - **Cambio de email:** contraseña incorrecta, `same_email`, `email_taken` al pedirlo y al confirmar (carrera), aviso a la dirección antigua, revocación de sesiones y un token de reset antiguo que deja de valer.
  - **Correo:**
    - todas las plantillas renderizan en todos los idiomas con `StrictUndefined`;
    - un `full_name` con `<script>` sale escapado en HTML y literal en texto;
    - un override en `email_templates/` gana a la plantilla incluida;
    - un nombre de plantilla con `../` se rechaza;
    - un asunto con `\r\n` no inyecta cabeceras;
    - el `Message-ID` se mantiene entre reintentos;
    - un error 4xx se reintenta y un 5xx falla sin reintento, con el mensaje genérico en `job.error`;
    - `scrub_payload` deja `{}` al terminar.
  - **Enlaces:** el enlace usa `FRONTEND_URL` aunque la petición llegue con `Host: evil.example`.
  - **Configuración** (reutilizando `_prod()`):
    - en producción no se admite `console`, `file` ni `memory`;
    - `FRONTEND_URL` debe ser https;
    - `EMAIL_LINK_*` sin `{token}` o con host son errores;
    - `SMTP_SECURITY=none` con un host remoto es un error en el worker;
    - la API no exige `SMTP_*`.
  - **SMTP:**
    - `smtplib.SMTP` sustituido con `monkeypatch`: se comprueban STARTTLS con contexto verificado, login y traducción de errores;
    - opcionalmente, un test de integración `@pytest.mark.mailpit` que se salta si no está `MAILPIT_URL`: envía por SMTP y lee la API de Mailpit (`/api/v1/messages`).
  - **Generador:** generar `examples/shop.yaml` en una copia temporal y pasar sus tests. `test_new_api.py` comprueba que las flags nuevas escriben en `.env` y no en ficheros versionados.

### 4.6 Docker

- **`docker-compose.yml` (producción):**
  - el `worker` recibe `SMTP_*` del `.env`;
  - la `api` los recibe vacíos (`SMTP_PASSWORD: ""`), con el mismo criterio de SEC-38 para `SECRET_KEY` en el worker: la API nunca envía.
- **Desarrollo:** nuevo `compose.mail.yml` (o un perfil `dev`, a decidir con el usuario) con `axllent/mailpit:<versión fijada>`:
  - puertos `127.0.0.1:1025` (SMTP) y `127.0.0.1:8025` (interfaz web);
  - `MP_MAX_MESSAGES=500`.
- `make mail` lo levanta. El `.env` de desarrollo documenta `EMAIL_BACKEND=smtp SMTP_HOST=localhost SMTP_PORT=1025 SMTP_SECURITY=none`, permitido fuera de producción.
- El laboratorio de seguridad (`security/lab.sh`) puede usar el mismo contenedor.

---

## 5. Dependencias

| Dependencia | Estado |
|---|---|
| `jinja2` | Ya está en `dependencies`. |
| `smtplib`, `email`, `ssl`, `secrets`, `hashlib` | Biblioteca estándar. |
| `anyio` | Ya presente vía Starlette; `to_thread` ya se usa en `rate_limit.py`. |
| `pydantic[email]` | Ya está (`EmailStr`). |
| **Nuevas de ejecución** | **Ninguna.** |
| **Nuevas de desarrollo** | **Ninguna:** SMTP simulado con `monkeypatch` y Mailpit como imagen Docker opcional. |
| Futuro, si hace falta | `aiosmtplib` (SMTP async nativo) o `httpx` como dependencia de ejecución (backends HTTP). Solo si un cliente lo necesita. |

---

## 6. Riesgos y cómo los trato

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | Enumeración de cuentas por `forgot`/`resend` (contenido o tiempo) | Siempre 202 con el mismo texto. La API solo encola y la búsqueda la hace el worker. |
| R2 | Bombardeo de correo a una víctima, o cola llena | Límite por IP (SlowAPI) + límite por cuenta en el worker (cooldown y máximo por hora) + `RATE_LIMIT_GLOBAL`. Los trabajos rechazados cuestan una fila, y `prune` los borra. |
| R3 | Filtración del token (logs, Referer, BD, `/jobs`) | Solo se guarda su hash. El token nunca va en el payload. Va en el fragmento de la URL. Logs sin cuerpo. `scrub_payload`. |
| R4 | Envenenamiento del enlace con la cabecera Host | El enlace sale solo de `FRONTEND_URL` validado y el worker no tiene petición. Hay test. |
| R5 | Uso doble o carrera en el consumo | `UPDATE … WHERE used_at IS NULL RETURNING`. Consumir uno invalida los demás. |
| R6 | Toma de cuenta con un token antiguo tras cambiar contraseña o email | Validez ligada a `password_changed_at` y a `token.email == user.email`. Todos los tokens se invalidan al cambiar el email. |
| R7 | Escáneres de enlaces que consumen tokens | Consumo solo por POST desde el frontend. |
| R8 | Inyección de cabeceras o de HTML en plantillas | `policy.SMTP`, asunto de una sola línea, sandbox + autoescape en HTML, `StrictUndefined`, nombres de plantilla en lista blanca. |
| R9 | Credenciales SMTP expuestas en la API | Solo las recibe el worker. `SecretStr`. No se muestran en `apigen check`. |
| R10 | SMTP sin TLS o con certificado no verificado | `create_default_context()` obligatorio. `none` solo en loopback o fuera de producción. |
| R11 | Duplicados por reintentos (entrega al menos una vez) | `Message-ID` estable. Los enlaces siguen valiendo. Documentado. |
| R12 | Activar `required` deja fuera a usuarios existentes | Relleno en la migración. Refresh también comprueba la verificación. Documentado en el README del cliente. |
| R13 | Entrega (spam) por culpa del dominio del cliente | Fuera del código: lista de comprobación de SPF, DKIM y DMARC en `init-env` y el README. `apigen email test`. |
| R14 | Rebotes o supresiones no gestionados | Fuera de alcance en esta fase. Queda anotado. |
| R15 | Rotura de compatibilidad | Todo desactivado por defecto. Cambios de esquema aditivos. `REGISTER_HIDE_EXISTING` es opcional y desactivado. |

### 6.1 Preguntas abiertas para el experto y el usuario

1. ¿`REGISTER_HIDE_EXISTING` entra en esta fase o se pospone?
2. ¿Enlace de "no fui yo, revertir" en el aviso de cambio de email? Lo propongo para una fase posterior.
3. Mailpit: ¿`compose.mail.yml` separado o un perfil `dev` dentro del compose?
4. ¿Hace falta ya un nivel `verified` en el YAML de `apigen` (permisos por recurso), o basta con `VerifiedUser` en hooks?
5. ¿Código OTP de 6 dígitos como alternativa al enlace, para apps móviles sin *universal links*? Lo dejo fuera; el diseño de la tabla lo admitiría con otro `purpose`.

---

## 7. Orden de implementación y estimación

| Paso | Contenido | Estimación |
|---|---|---|
| 1 | `Settings` (sección Correo) + validaciones por rol + `.env.example` + tests de configuración | 3 h |
| 2 | `app/email/`: `EmailMessage`, MIME, backends `console`/`file`/`memory`/`smtp`/`disabled`, `get_backend()` + tests (SMTP simulado) | 4 h |
| 3 | Renderizado Jinja (sandbox, overrides, idioma) + plantillas `en`/`es` + `build_link()` + tests de plantillas y enlaces | 4 h |
| 4 | `scrub_payload` en `@task`/cola + tarea `email.send` + helper `send_email()` + tests de reintentos | 2 h |
| 5 | Modelo `AccountToken` + `email_verified_at` + migración con relleno + `services/account_tokens.py` (emitir, consumir, limitar, limpiar) + `db prune` | 3 h |
| 6 | Reset de contraseña (forgot/reset, tarea `auth.password_reset`, aviso `password_changed`, integración con `change_password` y el lockout) + tests | 4 h |
| 7 | Verificación (register, login y refresh con `required`, `verify`, `resend`, `VerifiedUser`, superusuario/admin verificados) + tests | 4 h |
| 8 | Cambio de email (endpoint, tarea, doble correo, confirmación con carrera) + tests | 3 h |
| 9 | CLI: `apigen email test` (+ `preview`/`eject` si hay tiempo), `init-env --production`, `createsuperuser` | 2 h |
| 10 | `apigen docs` (en/es), Postman, `new_api.py` (flags, `.env`, `DESARROLLO.txt`, `CLAUDE.md`), `compose.mail.yml` + `make mail`, compose de producción | 4 h |
| 11 | Verificación final: pytest + ruff en el repo, generar `shop.yaml` en una copia temporal, `new_api` en el scratchpad, prueba de extremo a extremo con Mailpit en Docker, `graphify update .` | 3 h |
| | **Total** | **≈ 36 h (4–5 días)** |

Los pasos 1 a 4 (el subsistema de correo) no dependen de auth y se pueden revisar por separado. Los pasos 6 a 8 dependen de 1 a 5. El paso 10 conviene hacerlo al final, cuando los nombres de rutas y códigos estén cerrados.

## 8. Ficheros previstos

- **Nuevos:**
  - `app/email/{__init__,message,render,links}.py`
  - `app/email/backends/{base,console,file,memory,smtp}.py`
  - `app/email/templates/{en,es}/*`
  - `app/tasks/email.py`
  - `app/models/account_token.py`
  - `app/services/account_tokens.py`
  - `app/schemas/account.py` (EmailRequest, PasswordReset, TokenConfirm, EmailChange)
  - migración nueva
  - `compose.mail.yml`
  - `email_templates/README.txt`
  - `tests/test_email.py`, `tests/test_password_reset.py`, `tests/test_email_verification.py`
- **Modificados:**
  - `app/core/config.py`
  - `app/models/user.py`, `app/schemas/user.py`
  - `app/api/v1/endpoints/{auth,users}.py`
  - `app/services/auth.py` (refresh con `required`)
  - `app/api/deps.py` (`VerifiedUser`)
  - `app/tasks/{__init__,registry,queue}.py`
  - `apigen/cli.py`, `apigen/docs.py`
  - `scripts/new_api.py`
  - `docs/postman/API.postman_collection.json`
  - `docker-compose.yml`, `Makefile`
  - `.env.example`, `.gitignore`, `.dockerignore`
  - `README.txt`, `guia/README.txt`
