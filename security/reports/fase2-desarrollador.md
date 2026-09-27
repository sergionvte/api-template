# Fase 2: implementación del desarrollador (correo, verificación de email y recuperación de contraseña)

- **Fecha:** 2026-09-26
- **Entradas:**
  - `security/reports/fase2-plan.md` (plan consolidado, decisiones D1–D10), que prevalece sobre mi diseño previo.
  - `fase2-plan-seguridad.md` (REQ-xxx y casos ST-01..45).
  - `fase2-plan-usuario.md` (historias MUST).
- **Estado final:**
  - **Repo:** 305 tests en verde (antes 205). `ruff check` y `ruff format --check` limpios.
  - **Generador:** en copias temporales, `examples/shop.yaml` da 330 tests en verde y `examples/cursos.yaml` 335. Cada copia tiene 1 test omitido: el de `new_api` necesita repositorio git y la copia no lo tiene. Ruff limpio en ambas. No se han tocado las plantillas de `apigen/templates/`.
  - **Postman:** `npx newman@6` contra una API local con los flujos activos:
    - `Register + Login + Account` sin tokens: 10/10 aserciones;
    - `Login + Account` con los tokens leídos de los `.eml`: 9/9;
    - `Auth + Health`: 9/9.
  - **Docker (proyecto `-p apimail`):** API + worker + PostgreSQL + Redis + Mailpit, todo en modo **producción**, con SMTP **STARTTLS y certificado verificado**. De 29 comprobaciones E2E, todas en verde. Al repetir el script sin reiniciar, las 2 de registro dan 429 por `RATE_LIMIT_REGISTER=5/hour`, que es lo esperado. Terminado con `down -v --rmi local`.
  - **`scripts/new_api.py`:** probado con las flags nuevas en el scratchpad y el proyecto se crea con sus tests en verde (detalle en §5).
- **Sin commits en el repo.** No se han tocado `.claude/` ni el `CLAUDE.md` del repo. `graphify update .` ejecutado al terminar.

---

## 1. Pasos del plan (§6): cambio → ficheros → tests

| Paso | Cambio | Ficheros | Tests |
|---|---|---|---|
| **1. Subsistema `app/email/`** | Mensaje MIME (`policy.default`, `formataddr`, `Auto-Submitted`, `Message-ID` estable). Backends `console`/`file`/`memory`/`smtp`/`disabled`/`custom`. Renderizado Jinja en sandbox con plantillas es/en, sobrescribibles en `email_templates/`. Enlaces solo desde `FRONTEND_URL`. Configuración y validación en `Settings` (`_email_problems`). Idioma por `Accept-Language` dentro de `MAIL_LANGUAGES` | `app/email/{__init__,message,links,render}.py`, `app/email/backends/*.py`, `app/email/templates/{en,es}/*` (8 plantillas × 3 ficheros + layout), `app/core/config.py`, `app/core/logging.py`, `.env.example` | `tests/test_email.py`: backends, SMTP simulado, plantillas, enlaces, 20 configuraciones de producción erróneas, CLI, README del cliente y compose |
| **2. Modelo y migración** | `account_tokens` (sha256, `purpose`, email destino, caducidad, `used_at`). `email_log` (registro mínimo por trabajo, para cupos, idempotencia y cortacircuitos). `users.email_verified_at` con relleno para los usuarios existentes. `UserRead.email_verified` y `UserAdminRead.email_verified_at` | `app/models/{account_token,email_log,user}.py`, `alembic/versions/20260926_1800_5e2b7c9d1a34_…py`, `app/schemas/user.py`, `app/services/account_tokens.py` | `alembic upgrade head` → `alembic check` ("No new upgrade operations") → `downgrade -1` en SQLite. En Docker, la migración corrió sobre PostgreSQL. Tests de tokens en `test_account.py` |
| **3. Tareas del worker** | `auth.password_reset`, `auth.email_verification`, `auth.account_exists`, `auth.email_change`, `auth.notice` y `email.send`. Incluyen revalidación, cupos por cuenta (60 s / 3 por hora / 10 al día), idempotencia por `job_id` + `sent_at`, cortacircuitos, errores transitorios o permanentes con mensaje genérico y `scrub_payload`. `claim(job_id=)` y `run_now()` para el envío `inline` | `app/tasks/mail.py`, `app/tasks/{registry,queue,worker,__init__}.py`, `app/email/__init__.py` | Cupos entre IPs, enfriamiento, trabajos obsoletos o revalidados, reintento con `sent_at`, transitorio frente a permanente, cortacircuitos, payload vaciado, `inline` |
| **4. Recuperación de contraseña** | `POST /auth/password/forgot`, `/reset/validate` y `/reset`. El reset revoca sesiones, fija `password_changed_at`, desbloquea (D2), marca el email como verificado y envía un aviso. `POST /users/me/password` invalida los resets pendientes y avisa | `app/api/v1/endpoints/account.py`, `app/api/v1/endpoints/users.py`, `app/schemas/account.py`, `app/api/v1/router.py` | Flujo completo, respuesta uniforme, tokens malos, propósito cruzado, 422 que conserva el token, caducidad, concurrencia, invalidación, bloqueo e IP conocida, toma previa de la cuenta, logs |
| **5. Verificación, modos y registro uniforme (D1)** | `EMAIL_VERIFICATION=off|optional|required`: 403 `email_not_verified` en login solo con la contraseña correcta, y refresh rechazado. `POST /auth/email/verify` (idempotente) y `/verify/resend` (con sesión o `{email}`). Con `optional`/`required`, el registro responde **202 idéntico** con Argon2 en ambos caminos; un email existente recibe "ya tienes cuenta". `VerifiedUser`. `createsuperuser` y las altas de admin nacen verificados | `app/api/v1/endpoints/auth.py`, `account.py`, `app/services/auth.py`, `app/api/deps.py`, `apigen/cli.py` | Registro uniforme (3 casos) y carrera de registros; modo `required`; refresh; usuarios de admin; resend; token ligado al email; `VerifiedUser` |
| **6. Cambio de email** | `POST /users/me/email` pide la contraseña actual y responde 202 aunque la dirección esté ocupada. El enlace va a la dirección nueva y se envía un aviso a la antigua al pedirlo y al completarlo. Al confirmar: revoca sesiones, invalida todos los tokens y aplica `UNIQUE` → 409 | `users.py`, `account.py`, `app/tasks/mail.py` | Flujo completo, dirección ocupada con respuesta uniforme, esquemas que no aceptan `email`/`email_verified_at` |
| **7. CLI** | `apigen email test` (errores del proveedor traducidos), `email preview`, `email eject`. `check` muestra las filas de correo y renderiza las plantillas. `init-env --production` incluye el bloque de correo. `db prune` purga tokens y registro de envíos | `apigen/cli.py` | `test_cli_email_test_preview_and_eject`, `test_cli_translates_provider_errors` |
| **8. `apigen docs`, Postman y `make new-api`** | README del cliente (en/es) con la sección "Correos de cuenta" (flujos, enlace, frontend, errores, SMTP/SPF/DKIM/DMARC); el registro pasa a 202 si procede. Postman: carpeta **Account** (7 peticiones, variables `resetToken`, `verifyToken`, `newPassword`, `newEmail`). `new_api.py` gana `--email-verification`, `--password-reset` y `--frontend-url` (solo escriben en `.env`) y `account.py` como endpoint base. Nombres de recurso reservados | `apigen/docs.py`, `apigen/docs_accounts.py`, `docs/postman/API.postman_collection.json`, `scripts/new_api.py`, `apigen/spec.py` | `test_client_readme_documents_account_flows[en/es]`, `test_email_flags_go_only_to_the_untracked_env`, `test_account_flow_names_are_reserved`, newman |
| **9. Mailpit y Docker** | `compose.mail.yml` (D7) + `make mail`. En `docker-compose.yml` la API recibe `SMTP_USER`/`SMTP_PASSWORD`/`SMTP_PASSWORD_FILE` vacíos (REQ-C10). El Dockerfile copia `email_templates/`. `var/` en `.gitignore` y `.dockerignore` | `compose.mail.yml`, `docker-compose.yml`, `Makefile`, `Dockerfile`, `.gitignore`, `.dockerignore`, `email_templates/README.txt` | `test_compose_api_gets_no_mail_credentials` y E2E en Docker (§5) |
| **10. Documentación y grafo** | README §1, 5, 6, 7, 9, 10, 13, 14 y la nueva **§15**. Guía §4, 9, 16 y la nueva **§17**. `docs/DESARROLLO.txt` de los proyectos nuevos incluye README §15 y guía §17. CLAUDE.md de los proyectos nuevos con una viñeta de correo | `README.txt`, `guia/README.txt`, `scripts/new_api.py` | `graphify update .` |

Arreglos que salieron durante la verificación:
- **Aislamiento de tests:** el `.env` que deja `make new-api` rompía tests del proyecto generado. Ahora los tests no leen el `.env` local: `APP_ENV_FILE`, fijado en `conftest.py`.
- **Cupo de cambio de email:** se agotaba por los correos del alta. El cambio de email tiene ahora su propio cupo; los correos provocables sin sesión comparten uno.
- **Avisos en modo `inline`:** los avisos que encola el propio trabajo no salían. Ahora se ejecutan también en ese modo.
- **Logs de dependencias:** `aiosqlite`, `httpx` y `httpcore` nunca por debajo de WARNING (volcaban parámetros SQL con emails en DEBUG).

---

## 2. Requisitos MUST de seguridad (`fase2-plan-seguridad.md` §4)

| REQ | Cumplimiento | Prueba |
|---|---|---|
| **T01** CSPRNG ≥256 bits, sin JWT | `prefijo + secrets.token_urlsafe(32)` (`services/account_tokens.issue`) | `test_password_reset_full_flow` (≥46 caracteres), ST-10 |
| **T02** Prefijo por propósito y validación de forma previa | `pr_` / `ev_` / `ec_` (D: `ev_`, según el plan consolidado). `purpose_of()` comprueba longitud 40–128 y base64url **antes** de hashear | `test_bad_tokens_get_the_same_400` |
| **T04** Tokens enormes, con NUL o raros → mismo 400 | El esquema no valida el token (`_TokenInput` sin `StrictInput`); `purpose_of` lo rechaza | ST-16: 10 KB, NUL y `!$` → 400 |
| **T05/T06** `purpose` en toda consulta; el prefijo no basta | `find_valid`/`consume` filtran por `purpose` | `test_token_of_one_purpose_never_serves_another` (prefijo cambiado) |
| **T07** Consumo atómico en la misma transacción | `UPDATE … WHERE used_at IS NULL AND expires_at > now` y `rowcount == 1`, junto con el cambio de contraseña o email | `test_concurrent_resets_only_one_wins` |
| **T08** Invalidación al consumir, al cambiar la contraseña y al cambiar el email | `invalidate()` en reset, verify, `/users/me/password` y confirmación de email | ST-14 (`test_using_one_reset_invalidates_the_others`, `test_email_change_flow`) |
| **T09** Caducidades 30 min / 48 h / 60 min con rangos | `TOKEN_TTL_*` con `ge`/`le` (10–60 min, ≤168 h, ≤1440 min) | `test_expired_token_is_rejected` |
| **T10** Solo sha256, nunca en claro | Solo `token_hash`. El token lo genera el worker y no va en payload, result, error ni respuestas | ST-10 (`test_tokens_never_stored_in_clear`) y en Docker, consulta a PostgreSQL (§5) |
| **T11** Vinculado a `user_id` y email; cuenta inactiva → inválido | `find_valid`: usuario activo, `user.email == token.email` (salvo en `ec_`) y creado después de `password_changed_at` | `test_verification_token_bound_to_email` |
| **E01–E04** Registro uniforme | D1: 202 con el mismo cuerpo y sin `Location`. Argon2 en los dos caminos. El existente no se modifica y recibe `account_exists`. `IntegrityError` → 202 | ST-01/02/04. Medición ST-03: diferencia de medianas +0,23 ms, p = 0,099 (§5) |
| **E05** Riesgo aceptado T3/SEC-05 | Cerrado con verificación activa. El 409 solo queda con `off` y está documentado como riesgo aceptado (README §10 y docstring) | — |
| **E06–E08** `forgot`/`resend` uniformes; la API no consulta al usuario | Solo `enqueue()` de un trabajo de sistema. El 422 depende solo de la forma | ST-05 y medición ST-03 de `forgot`: +0,00 ms, p = 0,971 |
| **E09** `EmailStr` estricto | `EmailRequest(StrictInput)` | ST-06 |
| **E10** Destinatario = `users.email` de la BD | El worker usa `user.email`; `forgot` con mayúsculas se normaliza | ST-07 |
| **F01–F03** Orden del reset y política de contraseñas | Forma → token vigente → `password_problems` (422 sin consumir) → Argon2 fuera de la transacción → consumo + actualización | ST-17 |
| **F04** Aviso de "contraseña cambiada" | `auth.notice` tras el reset y tras `/users/me/password` | ST-44 |
| **F11** Verificar no inicia sesión | 204 sin cuerpo. Repetir da 204 (D: el plan consolidado lo cuenta como éxito) | ST-22 |
| **F12** 403 solo con la contraseña correcta; el refresh tampoco emite | Comprobación tras `authenticate`; la contraseña mala sigue en 401 y cuenta para el bloqueo. `rotate_refresh_token` rechaza | ST-08, `test_refresh_refused_for_unverified_in_required_mode` |
| **F13** Migración y superusuario | `UPDATE users SET email_verified_at = created_at`. `createsuperuser` y las altas de admin nacen verificados | ST-45 |
| **F20–F25** Cambio de email | Contraseña actual (con rate limit de login), sin cambios hasta confirmar, 202 uniforme, avisos a la antigua, revocación. Los esquemas de PATCH no aceptan `email`/`email_verified_at` | ST-09, `test_email_change_flow`, `test_profile_updates_cannot_touch_email_fields` |
| **S01–S04, S06** Sesiones y bloqueo | `revoke_all_sessions` + `password_changed_at`. `forgot`/`reset` no tocan contadores | ST-18/19/20/21/23 |
| **R01** Límites por IP | `RATE_LIMIT_EMAIL_REQUEST` (vacío: `5/minute;20/hour` en producción) y `RATE_LIMIT_TOKEN_CONFIRM` (`10/minute;50/hour`); `/users/me/email` usa `RATE_LIMIT_LOGIN`. Validados con `_valid_limit` | ST-24 |
| **R02/R03** Cupo por cuenta en el worker | 60 s / 3 por hora / 10 al día (D3), con datos de `email_log`. Lo excedido termina `succeeded` y se audita `email.suppressed`. Forgot, resend y registro duplicado comparten cupo | ST-25 (6 peticiones desde 6 IP → 3 correos) |
| **R04** 429 auditado | `auth.rate_limited` también para `/users/me/email` | ST-24 |
| **R08** Nada a direcciones sin cuenta | El worker descarta con `unknown_email` | ST-27 y E2E |
| **L01–L05** Enlaces | Solo `FRONTEND_URL` + `EMAIL_LINK_*` (`{token}` exactamente una vez, URL-encoded, en el fragmento por defecto). Sin rutas GET. `Cache-Control: no-store` | ST-28/29 y E2E con `X-Forwarded-Host`/`Origin`/`Referer` maliciosos |
| **C01** Nada del freelancer | Valores por defecto vacíos o `example.com`. El escáner de `new_api.py` sobre **todos** los ficheros (también los nuevos sin versionar): 0 hallazgos | ST-39 |
| **C02/C03** Backends y arranque en producción | Por defecto `console` en development, `memory` en testing y ninguno en producción. En producción no arranca sin backend, con `console`/`file`/`memory` y flujos activos, sin `EMAIL_FROM` o con un dominio de ejemplo, con `FRONTEND_URL` http o localhost, con rutas sin `{token}` o con host, sin `SMTP_HOST` en el worker, ni con `SMTP_USER` sin contraseña | ST-34 (20 casos parametrizados) |
| **C04** `disabled` explícito | Endpoints → 403 con código. `disabled` con verificación o reset → error al arrancar (también fuera de producción) | ST-35 |
| **C05** `console` solo en desarrollo | En producción no escribe el cuerpo. `memory` está prohibido en producción | `test_console_backend_prints_in_development_only` |
| **C06** Validación de direcciones, nombres y URLs | Una sola dirección sin CR/LF. Nombre y marca sin control y ≤100. URLs https (http solo hacia localhost fuera de producción). Color `#rrggbb` | ST-31 |
| **C07** SMTP con TLS verificado | `ssl.create_default_context()`. `starttls` falla si el servidor no lo anuncia. `none` solo hacia loopback en producción | ST-36 (simulado y en Docker con certificado no confiable → `smtp_tls_certificate`) |
| **C09** Credenciales como `SecretStr` | `SMTP_PASSWORD: SecretStr`, que no aparece en `repr`. `SMTP_PASSWORD_FILE` como opción | `test_smtp_password_is_secret_and_can_come_from_a_file` |
| **C10** Mínimo privilegio | La API recibe `SMTP_*` vacíos en compose; las comprobaciones de credenciales solo se hacen en el rol worker | ST-38 (test y `docker compose config`) |
| **M01–M08** Plantillas y mensaje | Sandbox, autoescape en HTML y `StrictUndefined`. Nombre de plantilla y `lang` en lista blanca. Asunto de plantilla en una línea. Sin `full_name` hacia direcciones no probadas; en los avisos, escapado y ≤120 | ST-30/31/32/33 |
| **Q01** Trabajos de sistema | `owner_id=None` | ST-40 |
| **Q02/Q03** Payload sin secretos y vaciado | Sin tokens, contraseñas ni cuerpos. `scrub_payload=True` lo vacía al terminar (éxito o fallo definitivo) | ST-10 y en Docker, consulta a `jobs` (0 filas con token o con payload no vacío) |
| **Q04** Idempotencia | `email_log(job_id único, sent_at)`: un reintento con `sent_at` no reenvía. `Message-ID` = `<job_id@dominio>` | ST-41 |
| **Q05** Timeouts encadenados | `SMTP_TIMEOUT` ≤45 (20 por defecto) < timeout de la tarea (120) < arrendamiento (120 + `JOBS_LEASE_GRACE`) | — |
| **Q06/Q08** Clasificación de errores; `job.error` genérico | 5xx, autenticación, destinatario o TLS → `TaskError(retry=False)`. Red, 4xx o timeout → reintento. `max_attempts=5`. `job.error` = `Email delivery failed (transient|permanent)` | ST-42 |
| **Q07** Revalidación al enviar | Cuenta existente y activa, verificación pendiente, email libre en los cambios y petición no más antigua que la vida del token | ST-43 |
| **G01/G02** Qué no se registra | Sin tokens, enlaces, cuerpos, credenciales ni emails completos. `debuglevel=0`. Excepciones SMTP envueltas con `from None`. `httpx`/`httpcore`/`aiosqlite` ≥ WARNING | ST-37 (DEBUG) y en Docker, grep de 146 líneas de logs: 0 coincidencias |
| **G03/G04** Eventos de auditoría | `auth.register(.duplicate)`, `auth.email_verification.sent|verified|invalid_token|requested`, `auth.password_reset.requested|sent|completed|invalid_token`, `auth.email_change.requested|sent|completed|wrong_password`, `auth.login.unverified`, `email.suppressed` (`unknown_email|inactive|cooldown|quota|stale|already_verified|email_taken|circuit_open`), `email.send.failed`. Siempre sin la dirección | — |

**SHOULD implementados:**
- T12: como mucho 3 tokens vigentes por cuenta y propósito.
- T13: purga con `db prune`.
- F06/S05: la cuenta bloqueada completa el reset y queda desbloqueada y verificada.
- F15: las altas de admin nacen verificadas.
- R05: cortacircuitos global; al abrirse, reintenta con backoff y audita a nivel ERROR.
- C11: `SMTP_PASSWORD_FILE`.
- C12: bloque de correo en `init-env` y `email test`.
- C14: SPF/DKIM/DMARC en el README del cliente.
- M09: `Auto-Submitted` y ningún recurso remoto salvo el logo configurado.
- G06: nivel ERROR para errores permanentes y para el cortacircuitos.

**SHOULD pendientes:**
- F14: purgar cuentas sin verificar.
- R06: límite global con clave compartida (el cortacircuitos lo cubre en parte).
- C13: validar las plantillas al arrancar. Hoy se hace en `apigen check` y en los tests, no en el arranque.
- G06: alerta por picos de `invalid_token` desde una IP.

## 3. MUST del usuario (`fase2-plan-usuario.md` §6)

| MUST | Cumplimiento |
|---|---|
| 1. Endpoints `forgot`/`reset`/`verify`/`resend` con enlaces al frontend | Hechos, con las rutas del plan consolidado (`/auth/email/verify/resend`, con sesión y sin ella). Además, `reset/validate` y `GET /auth/features` (dos SHOULD) |
| 2. `EMAIL_VERIFICATION=off|optional|required` con `off` por defecto, 403 en login y `email_verified` | Hecho |
| 3. Usuarios existentes y altas de admin verificados | Hecho (migración, `POST /users` y `createsuperuser`) |
| 4. Backends `console` (defecto en development), `file`, `smtp`, sin correo y memoria para tests | Hecho (`disabled` equivale a "none"; `custom` como extensión) |
| 5. Marca e idioma por `.env`; plantillas es/en con texto, HTML y asunto aparte | Hecho: `EMAIL_FROM`, `EMAIL_FROM_NAME` y `MAIL_BRAND_*`/`MAIL_SUPPORT_EMAIL`/`MAIL_FOOTER`/`MAIL_DEFAULT_LANGUAGE`/`MAIL_LANGUAGES` |
| 6. Plantillas propias que apigen no toca, autoescape, modo estricto y errores detectados | `email_templates/` gana fichero a fichero. `apigen check` y los tests renderizan todas las plantillas en todos los idiomas |
| 7. Envío por la cola con reintentos (`inline` en development); el worker no necesita `SECRET_KEY` | Hecho. D10: el token se genera en el worker y solo hace falta sha256, sin secreto. `EMAIL_DELIVERY=inline` por defecto en development |
| 8. Producción no arranca con `console`/`file`/`none`, remitente de ejemplo o `FRONTEND_URL` http/localhost | Hecho |
| 9. `apigen email test` con errores traducidos; `check` e `init-env` con el bloque de correo | Hecho. En Docker muestra "✓ Enviado a … con smtp" y, con un certificado no confiable, "el certificado del servidor no es válido para mailpit…" |
| 10. `apigen docs`: sección de cuentas; README §6/§7 | Hecho (en/es) y README actualizado |
| 11. Postman: carpeta Account con variables y newman | Hecho (7 peticiones, verificadas con newman) |
| 12. Códigos estables: `invalid_or_expired_token`, `email_not_verified`, `password_reset_disabled` y 429 con `Retry-After` | Hecho (más `email_verification_disabled`, `email_change_disabled` y `same_email`) |

**SHOULD del usuario pendientes:**
- Admin: `PATCH email_verified` y `POST /users/{id}/send-password-reset`. No los hago porque REQ-F25 prohíbe `email_verified_at` en los esquemas de actualización, así que exigen una decisión conjunta.
- `User.locale`: el idioma sale de `Accept-Language` en cada petición.
- Permiso `verified` en el YAML: queda fuera por D8.

## 4. Desviaciones del plan y motivo

1. **Tabla auxiliar `email_log`.** El plan pone `sent_at` en `account_tokens`, pero el cupo por cuenta (R03), la idempotencia de avisos y de `email.send` (Q04) y el cortacircuitos (R05) necesitan un registro también para los correos **sin token** ("ya tienes cuenta", avisos, correos propios). Guarda solo `job_id`, `user_id`, tipo y fechas; no guarda direcciones ni contenido. `db prune` la purga a los 2 días.
2. **Dos grupos de cupo por cuenta.** Forgot, resend y registro duplicado comparten el cupo de D3, como exige ST-25. La confirmación de un **cambio de email**, que requiere sesión y contraseña, tiene su propio cupo con las mismas cifras. Si no, quien se registra, verifica y hace un reset en la misma hora no podía cambiar su email (lo detectó el E2E).
3. **Payload con dirección en dos trabajos.** `auth.email_change` lleva `new_email` y el aviso `email_changed` lleva `old_email`, porque tras el cambio la dirección antigua ya no está en la BD. REQ-Q02 solo contempla un email en forgot, resend y registro. Mitigación: `scrub_payload` los vacía al terminar y los trabajos son de sistema.
4. **`EMAIL_DELIVERY=inline`** (por defecto en development y prohibido en producción). Cubre el MUST 7 del usuario (F-01: "el correo no llega en local"): la API encola igual y, tras responder, ejecuta ese trabajo con el mismo código del worker (`run_now`). En testing y producción se usa la cola.
5. **SMTP sin TLS hacia loopback en producción sin opt-in.** REQ-C07 pedía además `EMAIL_SMTP_ALLOW_INSECURE`; el plan consolidado solo exige el error fuera de localhost, y así queda.
6. **Nombres de variables** según el plan §4 (`EMAIL_*`, `MAIL_*`, `SMTP_USER`, `TOKEN_TTL_*`, `EMAIL_PER_ACCOUNT_*`, `PASSWORD_RESET=on|off`). Donde REQ o usuario proponían otros (`EMAIL_VERIFICATION_REQUIRED`, `MAIL_BACKEND`, `apigen mail test`), prevalece el plan.
7. **El cortacircuitos reprograma en vez de descartar.** Con el límite superado, el trabajo se reintenta con backoff (y falla al agotar los intentos) en vez de terminar `suppressed`, para no perder correos de negocio. Se audita `email.suppressed` con `reason=circuit_open` a nivel ERROR.
8. **Cambios fuera del plan, necesarios:**
   - `APP_ENV_FILE`, para que los tests no lean el `.env` local.
   - `account`, `account_token` y `email_log` como nombres de recurso reservados en `apigen`, para que un recurso no pise `endpoints/account.py` ni los modelos.
   - `account.py` en `BASE_ENDPOINTS` de `new_api.py`.
   - Niveles de log de dependencias ruidosas.

## 5. Instrucciones para la validación

**Repo:**
```bash
.venv/bin/pytest -q -p no:cacheprovider        # 305 passed
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/pytest -q -p no:cacheprovider tests/test_account.py tests/test_email.py   # ST-xx
```
Correspondencia de casos ST con tests: los docstrings de `tests/test_account.py` y `tests/test_email.py` citan el ST que cubren.

**Casos ST que no son tests unitarios:**
- **ST-03 (tiempos).** Medido en proceso (ASGI) sin rate limit.
  - `forgot`: 200 + 200 peticiones alternadas; mediana 1,62 ms frente a 1,62 ms; Mann-Whitney p = 0,971.
  - `register`: 60 + 60 peticiones; 37,16 ms frente a 36,93 ms; p = 0,099.
  - Ambos cumplen el criterio (< 5 ms, p > 0,01).
- **ST-36/38/39** y la parte de ST-37 en Docker: ver el E2E de abajo.

**Laboratorio local sin Docker (lo que usé para newman):**
```bash
ENVIRONMENT=development EMAIL_BACKEND=file EMAIL_FILE_DIR=/tmp/mail \
EMAIL_VERIFICATION=optional PASSWORD_RESET=on FRONTEND_URL=http://localhost:3000 \
EMAIL_FROM=no-reply@example.com EMAIL_PER_ACCOUNT_COOLDOWN_SECONDS=0 \
uv run apigen run --port 8765
npx --yes newman@6 run docs/postman/API.postman_collection.json \
  --env-var baseUrl=http://127.0.0.1:8765 --folder Register --folder Login --folder Account
```
- Los tokens salen en los `.eml` (o en el log con `console`). Se pegan en las variables `resetToken` y `verifyToken` de la colección, en *Current value*.
- La carpeta Auth termina con logout-all: para Account, ejecuta `Login` antes.
- `EMAIL_PER_ACCOUNT_COOLDOWN_SECONDS=0` solo para encadenar pruebas rápidas contra la misma cuenta.

**E2E con Docker y Mailpit, en modo producción.** Lo hice en una copia del proyecto en el scratchpad:
1. `.env` de laboratorio:
   ```
   EMAIL_VERIFICATION=required
   PASSWORD_RESET=on
   EMAIL_BACKEND=smtp
   SMTP_HOST=mailpit
   SMTP_PORT=1025
   SMTP_SECURITY=starttls
   SMTP_USER=…
   SMTP_PASSWORD=…
   EMAIL_FROM=no-reply@<dominio de laboratorio>
   FRONTEND_URL=https://app.<dominio de laboratorio>
   ALLOWED_HOSTS=localhost,127.0.0.1
   ```
2. CA de laboratorio y certificado para `mailpit`.
3. Override con `MP_SMTP_TLS_CERT/KEY` y `MP_SMTP_REQUIRE_STARTTLS=true` en Mailpit, y `SSL_CERT_FILE=/certs/ca.pem` en el worker.
4. Arranque:
   ```
   docker compose -p apimail -f docker-compose.yml -f compose.mail.yml -f <override> up -d --build
   ```

Qué se comprobó:
- Todo `healthy`.
- `docker compose exec worker apigen email test …` envía el correo. Sin la CA de laboratorio (`-e SSL_CERT_FILE=/nonexistent`) falla con el mensaje de certificado: ST-36.
- **Registro y verificación:** 202 idéntico en los dos caminos, correo en español con la marca del cliente, `From` del cliente, HTML y `Auto-Submitted`. El enlace es `https://app.<dominio>/verify-email#token=ev_…`. El duplicado recibe "ya tienes cuenta" sin enlace. El login sin verificar da 403. `verify` da 204 con `no-store`, y 204 también la segunda vez.
- **Recuperación:** `forgot` con cabeceras maliciosas da un enlace limpio `…/reset-password#token=pr_…`. Además:
  - `validate` → 204;
  - contraseña débil → 422;
  - `reset` → 204, y reutilizar el token → 400;
  - el refresh anterior da 401, la contraseña antigua 401 y la nueva 200;
  - llega el aviso de "contraseña cambiada";
  - la dirección inexistente no recibe nada.
- **Cambio de email:** 202, enlace a la dirección nueva y aviso a la antigua. La confirmación da 204, la sesión anterior da 401, el login funciona con el email nuevo y llega el aviso final a la dirección antigua.
- **PostgreSQL:** los tokens son hex de 64 caracteres. 0 trabajos con tokens y 0 trabajos terminados con payload.
- **Logs de API y worker** (146 líneas): 0 tokens, enlaces, contraseñas o direcciones.
- **`docker compose config`:** la API recibe `SMTP_USER`/`SMTP_PASSWORD`/`SMTP_PASSWORD_FILE` vacíos.

Al terminar: `down -v --rmi local`.

**`scripts/new_api.py`.** Exige un árbol limpio y **nunca copia ficheros sin versionar**. Con `--allow-dirty`, el proyecto habría salido sin `app/email/`. Por eso lo probé desde una **copia del repo en el scratchpad con un commit en esa copia** (no en el repo real):
```bash
python3 scripts/new_api.py tienda-api --dir <scratch>/out --title "Tienda API" --lang es \
  --email-verification required --password-reset --frontend-url https://app.tienda.example
```
Resultado:
- uv sync, tests, grafo, escáner limpio y commit inicial del proyecto nuevo.
- El `.env` contiene `EMAIL_VERIFICATION=required`, `PASSWORD_RESET=on`, `FRONTEND_URL`, `MAIL_DEFAULT_LANGUAGE=es`, `MAIL_BRAND_NAME="Tienda API"` y `EMAIL_FROM=no-reply@example.com`. Este último es un marcador de desarrollo que en producción impide arrancar.
- `.env` no está versionado y sí lo están `email_templates/README.txt` y `compose.mail.yml`.
- El README del cliente trae la sección "Correos de cuenta" en español.
- `apigen check` muestra las filas de correo y avisa de que `FRONTEND_URL` no está en CORS.

## 6. Pendiente o para decidir

- SHOULD de seguridad: F14, R06, C13 en el arranque y alerta de picos de `invalid_token` (§2).
- SHOULD del usuario: operaciones de admin sobre la verificación (en conflicto con REQ-F25) y `User.locale` (§3).
- COULD (fuera por decisión del plan): proveedores HTTP (D5), "revertir cambio de email" (D6), permiso `verified` en el YAML (D8) y OTP (D9). El punto de extensión para un proveedor HTTP es `EMAIL_BACKEND=custom` + `EMAIL_BACKEND_CLASS=app.<módulo>:<Clase>`.
- Riesgo residual documentado en README §10: entrega "al menos una vez". Además, si una tarea vence por timeout mientras el hilo SMTP sigue enviando, un reintento podría duplicar el correo; los dos enlaces valdrían. `SMTP_TIMEOUT` está muy por debajo del timeout de la tarea para que no ocurra.
- `graphify update .` hecho. Los informes nuevos de `security/` necesitan `/graphify . --update` (extracción semántica) cuando el usuario quiera.

## 7. Ficheros

**Nuevos:**
- `alembic/versions/20260926_1800_5e2b7c9d1a34_account_tokens_email_verification.py`
- `apigen/docs_accounts.py`
- `app/api/v1/endpoints/account.py`
- `app/email/` (`__init__.py`, `message.py`, `links.py`, `render.py`, `backends/{__init__,base,console,file,memory,smtp}.py`, `templates/_layout.html`, `_button.html`, `_footer.txt`, `templates/{en,es}/*` con 8 plantillas × asunto, texto y HTML)
- `app/models/account_token.py`, `app/models/email_log.py`
- `app/schemas/account.py`
- `app/services/account_tokens.py`
- `app/tasks/mail.py`
- `compose.mail.yml`
- `email_templates/README.txt`
- `tests/test_account.py`, `tests/test_email.py`
- `security/reports/fase2-desarrollador.md`

**Modificados:**
- `.dockerignore`, `.env.example`, `.gitignore`, `Dockerfile`, `Makefile`, `docker-compose.yml`
- `README.txt`, `guia/README.txt`
- `apigen/cli.py`, `apigen/docs.py`, `apigen/spec.py`
- `app/api/deps.py`, `app/api/v1/endpoints/{auth,users}.py`, `app/api/v1/router.py`
- `app/core/{config,errors,logging}.py`
- `app/models/{__init__,user}.py`, `app/schemas/user.py`, `app/services/auth.py`
- `app/tasks/{__init__,queue,registry,worker}.py`
- `docs/postman/API.postman_collection.json`
- `scripts/new_api.py`
- `tests/{conftest,test_config,test_generator,test_new_api}.py`
- `security/reports/fase2-plan-desarrollador.md` (solo el formato de un bloque de código, para que `ruff format --check .` quede limpio)
- `graphify-out/*` (regenerado)
