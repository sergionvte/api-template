# Fase 2: correcciones de la validación (SEC-40..45, UX-67..80)

- **Fecha:** 2026-09-26
- **Entradas:** `fase2-validacion-seguridad.md` (SEC-40..45 e Info-1..6, con sus pruebas en `security/checks/fase2_*.py`) y `fase2-validacion-usuario.md` (UX-67..80).
- **Estado final:**
  - **Repo:** 322 tests en verde (antes 305); `ruff check` y `ruff format --check` limpios.
  - **Pruebas del experto en seguridad:** `security/checks/fase2_checks.py` 12/12, con los `test_sec4x_*` **invertidos** (ahora comprueban la corrección). `fase2_config_checks.py` 29/29, con los dos casos Info corregidos y su expectativa actualizada.
  - **Generador:** en copias temporales, `examples/shop.yaml` da 348 tests en verde y `examples/cursos.yaml` 353, con ruff limpio. En cada copia se omite 1 test porque la copia no es un repositorio git.
  - **Migración:** `alembic upgrade head`, `alembic check` ("No new upgrade operations") y `downgrade`.
  - **Docker `-p apifix`** (modo producción, PostgreSQL, Mailpit con STARTTLS y certificado verificado):
    - `fase2_docker_e2e.py`: 18 comprobaciones y 0 fallos;
    - modo `timing`: resultados en SEC-45;
    - terminado con `down -v --rmi local`.
  - **newman:** la colección tal cual está en verde (§3).
  - **`new_api.py`:** probado con las flags nuevas en el scratchpad (§3).
- **Sin commits.** No se han tocado `.claude/` ni el `CLAUDE.md` del repo. `graphify update .` ejecutado.

## 1. Seguridad

| ID | Decisión | Cambio (ficheros) | Test |
|---|---|---|---|
| **SEC-40** (bloqueante) | **Aceptado, con las cuatro recomendaciones.** **a)** Los avisos (`auth.notice`) tienen cupo por cuenta: `EMAIL_NOTICES_PER_ACCOUNT_PER_HOUR` (5/h, ×4 al día); lo excedido se descarta y se audita. **b)** El cortacircuitos tiene **dos presupuestos**: seguridad (reset y avisos, `EMAIL_MAX_SECURITY_PER_HOUR/DAY` = 300/2000) y el resto (altas, "ya tienes cuenta", enlaces de cambio de email y correos propios, `EMAIL_MAX_PER_HOUR/DAY`). Un tercero que provoca correos masivos ya no bloquea los resets. **c)** Cupo **por dirección de destino** para los enlaces de cambio de email (`EMAIL_PER_ADDRESS_PER_HOUR`=3): nueva columna `email_log.recipient_hash` (sha256, purgada a los 2 días). **d)** La alerta ya existía (`email.suppressed reason=circuit_open`, nivel ERROR) | `app/tasks/mail.py` (`SECURITY_KINDS`, `_circuit_open(kind)`, `_limits`, `_quota_reason`, `recipient_hash`), `app/models/email_log.py`, migración (misma revisión, aún no publicada), `app/core/config.py`, `.env.example` | `test_circuit_breaker_pauses_sending` (el general agotado pausa la verificación pero el reset sale; con el de seguridad agotado también se pausa), `test_notices_have_per_account_quota`, `test_email_change_links_have_per_address_quota`; `fase2_checks.py::test_sec40_*` invertidos. Docker: 6 cambios de email → 4 avisos (cupo de 5 con el aviso de contraseña ya contado) y 1 enlace |
| **SEC-44** (bloqueante) | **Aceptado.** `hide_input_in_errors=True` en `SettingsConfigDict`: ni los errores de campo ni los de `_check_security` muestran valores recibidos. Siguen diciendo qué variable está mal | `app/core/config.py` | `test_startup_error_never_shows_secrets`: centinela en `SMTP_PASSWORD` al final del `.env`, con error de campo y con error de modelo. Comprobado que **falla** con `hide_input_in_errors=False`. Docker: `import app.core.config` con `EMAIL_FROM` de ejemplo y el centinela → 0 apariciones |
| **SEC-41** | **Aceptado.** `_lock_account()`: antes de contar, un `UPDATE users SET updated_at=updated_at WHERE id=…` bloquea la fila en PostgreSQL y toma el bloqueo de escritura en SQLite hasta el commit, que ocurre antes de enviar. Es portable y no cambia `updated_at` | `app/tasks/mail.py` | `test_concurrent_jobs_respect_per_account_quota`: 3 cuentas × 6 trabajos simultáneos → 1 correo por cuenta. Comprobado que **falla** sin el bloqueo. `test_sec41` invertido. Docker/PG: 8 `forgot` simultáneos → **1** reset (antes 4) |
| **SEC-42** | **Aceptado.** El aviso `email_changed` solo incluye el nombre si la dirección **antigua** estaba verificada (`old_verified` en el payload, calculado al confirmar) | `app/api/v1/endpoints/account.py`, `app/tasks/mail.py` | `test_email_changed_notice_has_no_free_text_for_unproven_address`; `test_sec42` invertido |
| **SEC-43** | **Aceptado.** `reclaim_stale` (rama de fallo definitivo) y `cancel` vacían el payload de las tareas con `scrub_payload` | `app/tasks/queue.py` | `test_reclaimed_and_cancelled_email_jobs_are_scrubbed`; `test_sec43` invertido; Docker: 0 trabajos terminados con payload |
| **SEC-45** | **Aceptado.** El registro con verificación ya no hace SELECT previo. Los dos caminos **intentan el INSERT** dentro de un `SAVEPOINT` (el existente lo rechaza `UNIQUE`, que también cubre la carrera de REQ-E04), después encolan con `commit=False` y hacen un único commit sin refresh | `app/api/v1/endpoints/auth.py` | Tests de registro uniforme y de carrera. Docker/PG con reposo, 200+200 muestras: diferencia de medianas **−0,02 / −0,15 / −0,11 ms** con p = 0,063 / 0,002 / 0,013 (antes, +0,84 a +1,20 ms con p ≤ 0,001). En la suite completa, +0,04 ms con p = 0,49. **Residual:** unos 0,1 ms, a veces significativo con 400 muestras en reposo. Con `RATE_LIMIT_REGISTER=5/hour`, sin poder encadenar sondas y con cada sonda avisando al dueño o creando una cuenta, lo considero inexplotable. Queda documentado |
| Info-1 | **Aceptado.** El reset y la confirmación del cambio de email revocan sesiones (`token_version` + refresh) y encolan el aviso **en la misma transacción** que el consumo del token (`auth_service.revoke_sessions`, sin commit) | `app/services/auth.py`, `account.py` | Tests de reset y cambio de email (ST-18) |
| Info-2 | **Aceptado.** `SMTP_SECURITY=none` solo hacia loopback **exacto**, sin `*.localhost`. Además, `_is_local_host` trata cualquier IP de loopback como local, así que `FRONTEND_URL=https://127.0.0.2` se rechaza en producción | `app/core/config.py` | `test_smtp_without_tls_only_to_exact_loopback`; `fase2_config_checks.py` (2 casos Info → rechazados) |
| Info-3 | Sin cambios: el 409 al confirmar solo lo ve quien controla ese buzón. Queda documentado en el README del cliente (UX-80) | — | — |
| Info-4 | **Pospuesto** (SHOULD R06, límite global compartido). Mitigado por SEC-40b: una ráfaga ya no puede bloquear los correos de seguridad | — | Docker: 401–698 trabajos se vaciaron en 103–180 s |
| Info-5 | **Aceptado.** `new_api.py` quita `$`, comillas, `\` y saltos de línea de los valores que escribe en `.env`/`.env.example`, y los entrecomilla si llevan espacios | `scripts/new_api.py` | `test_email_flags_go_to_env_example_without_secrets` (título con `${HOME}` y comillas) |
| Info-6 | **Documentado** en `compose.mail.yml`: la bandeja de Mailpit no pide contraseña y muestra enlaces con token; solo escucha en 127.0.0.1 | `compose.mail.yml` | — |

## 2. Usuario

| ID | Decisión | Cambio (ficheros) | Test |
|---|---|---|---|
| **UX-67** (alta) | **Aceptado.** Las flags de `new_api.py` escriben la configuración **no secreta** (`EMAIL_VERIFICATION`, `PASSWORD_RESET`, `FRONTEND_URL` si se pasa, `MAIL_DEFAULT_LANGUAGE`, `MAIL_BRAND_NAME`) en `.env.example` (versionado) **antes** de `init-env`, así que el `.env` parte de ahí. `init-env --production --force` conserva esos valores. `EMAIL_FROM` y las credenciales quedan vacíos. Para que el `.env` de desarrollo arranque con los flujos activos, fuera de producción `FRONTEND_URL` y `EMAIL_FROM` vacíos usan marcadores (`http://localhost:3000`, `no-reply@example.com`) con aviso; en producción siguen siendo obligatorios. `apigen docs` avisa si `.env` y `.env.example` difieren en los modos. El README del cliente lista las líneas de `.env` que hay que añadir en producción | `scripts/new_api.py`, `app/core/config.py`, `apigen/docs_accounts.py`, `apigen/cli.py` | `test_email_flags_go_to_env_example_without_secrets`, `test_development_defaults_are_forgiving`, `test_docs_follow_environment_and_warn_about_env_example`. En el laboratorio, el proyecto nuevo tiene `.env.example` versionado con `optional/on/es/Tienda Luna/FRONTEND_URL`, `EMAIL_FROM=` vacío y README "optional · on"; tras `init-env --production --force` conserva los valores |
| **UX-68** (alta) | **Aceptado, según la decisión:** sin bypass en la API (REQ-F25). Comando de operador `apigen users verify --email X` / `--all-existing [--before AAAA-MM-DD] [-y]`, con confirmación y auditado (`admin.user.verify`, `actor=cli`, alcance y número). `apigen check` avisa: "N usuario(s) sin verificar no podrán iniciar sesión con required… apigen users verify --all-existing". Documentado en el README del cliente (verificación), en `.env.example`, en README §5/§15 y en la guía §17 (aviso al pasar a `required`) | `apigen/cli.py`, `apigen/docs_accounts.py`, `.env.example`, `README.txt`, `guia/README.txt` | `test_cli_users_verify`. Docker: `check` avisó de 1389 sin verificar; `users verify --all-existing -y` → evento de auditoría con `count: 1389`, y después `check` ya no avisa |
| **UX-69** | **Aceptado.** Los tests de la colección leen con `pm.variables.get` (Environment o colección). `newPassword` trae un valor de ejemplo válido. Sin token se acepta 400 o 422 (y si es 400, `invalid_or_expired_token`). Tras el reset, `password` se actualiza en el ámbito donde esté y los tokens se limpian en ambos. La descripción de Account explica el uso con un Environment y con newman | `docs/postman/API.postman_collection.json`, `README.txt` §14, `apigen/docs.py` | newman §3 |
| **UX-70** | **Aceptado.** Los cupos por cuenta vacíos son 60 s / 3 por hora / 10 al día en producción y en tests (D3) y **0 s / 30 / 200 en development**. Fuera de producción, un descarte por cupo escribe en el log "correo NO enviado (…): cupo por cuenta… sube EMAIL_PER_ACCOUNT_PER_HOUR". El README del cliente incluye una frase para el soporte ("que espere una hora") | `app/core/config.py`, `app/tasks/mail.py`, `apigen/docs_accounts.py`, `.env.example`, guía §17 | `test_development_defaults_are_forgiving`, `test_quota_suppression_is_visible_outside_production` |
| **UX-71** | **Aceptado.** El backend `file` escribe también un `.txt` **decodificado** (To, Subject y texto) y lo anuncia en el log. `apigen email test` indica el fichero. El `.eml` sigue en quoted-printable, que es lo correcto para SMTP. Postman, README y guía dicen "copia el token del `.txt`" | `app/email/backends/file.py`, `apigen/cli.py`, textos | `test_file_backend_writes_private_eml`; newman leyó los tokens de los `.txt` |
| UX-72 | **Aceptado.** 465 + `starttls` se detecta **sin conectar** ("el puerto 465 usa TLS directo: pon SMTP_SECURITY=ssl"). Un host que no resuelve devuelve `smtp_host_not_found` ("no se encuentra el servidor …"). Con `file`, se muestra la ruta del fichero | `apigen/cli.py`, `app/email/backends/smtp.py` | `test_cli_email_test_detects_port_465_with_starttls`, `test_smtp_unknown_host_is_explained` |
| UX-73 | **Aceptado.** `apigen check` valida también las reglas del rol worker (`Settings(PROCESS_ROLE="worker")`) y falla con "Configuración del worker…" | `apigen/cli.py` | `test_check_validates_worker_rules` |
| UX-74 | **Aceptado.** En development, sin `CORS_ORIGINS`, un `FRONTEND_URL` en localhost ya no se marca como "(no está en CORS)" | `apigen/cli.py` | — (visual) |
| UX-75 | **Aceptado.** La vista previa usa `FRONTEND_URL` + `EMAIL_LINK_*` con un token ficticio si `FRONTEND_URL` está configurado | `app/email/render.py` | `test_preview_uses_client_links` |
| UX-76 | **Aceptado.** `authenticate(require_verified=…)` lanza `email_not_verified` después de comprobar la contraseña pero **antes** de tocar `last_login_at` y los contadores. `EMAIL_NOT_VERIFIED` pasa a `app/core/exceptions.py` | `app/services/auth.py`, `auth.py`, `app/core/exceptions.py`, `app/api/deps.py` | `test_unverified_login_does_not_touch_last_login` |
| UX-77 | **Aceptado (el SHOULD `User.locale`).** Nueva columna `users.locale`, en la misma migración aún no publicada, que se guarda al registrarse y al usar un enlace (reset o verify) si la petición trae `Accept-Language`. Los correos usan el idioma de la petición; si no viene, `users.locale`; y si no, `MAIL_DEFAULT_LANGUAGE`. `request_language()` devuelve `None` sin cabecera. El README del cliente pide enviar siempre `Accept-Language` | `app/models/user.py`, migración, `app/email/__init__.py`, `auth.py`, `account.py`, `app/tasks/mail.py` | `test_email_language_follows_user_locale`: registro en `es`, y después forgot y reset **sin cabecera** → todo en español |
| UX-78 | **Documentado, sin cambiar la respuesta.** Mantengo el 204 ya validado (REQ-F11) y documento el prefijo como **contrato estable**: `ev_` = alta y `ec_` = cambio de email, tras el cual se cierran las sesiones. El frontend lo sabe antes de llamar y no hay que romper el 204 que ya usan tests, colección y README | `apigen/docs_accounts.py` | Test del README del cliente |
| UX-79 | **Aceptado.** `apigen docs` superpone las variables de entorno a `.env` y `.env.example` para las claves de cuentas (ninguna es secreta) | `apigen/docs_accounts.py` | `test_docs_follow_environment_and_warn_about_env_example` |
| UX-80 | **Aceptado.** La tabla de errores del README del cliente añade `wrong_password`, `same_email`, `email_change_disabled` y el 409 `email_taken` al confirmar. Nueva línea para apps móviles (*universal links / app links*) | `apigen/docs_accounts.py` | — |

## 3. Verificación

**newman.** La colección, sin tocarla, contra una API local en development (backend `file`, `optional` y reset activados, cupos por defecto de desarrollo):
1. **Tal cual**, sin tokens, con `--env-var baseUrl/email/password` (`--folder Register --folder Login --folder Account`): 9 peticiones y **10/10 aserciones**. Las peticiones con token esperan el rechazo.
2. **Con tokens por `--env-var`**, leídos del `.txt` del backend `file` (`--folder Login --folder Account`): 8 peticiones y **9/9**. `Verify email`, `Validate reset token` y `Reset password` → 204.
3. **Con la contraseña nueva** (el valor por defecto de `newPassword`):
   - `--folder Auth`: 7/7;
   - `--folder Login --folder Jobs --folder Health`: 5/5.
   - Nota: `Auth` termina con logout-all. Si después se ejecuta `Jobs` en la misma pasada, da 401. Esto es anterior a esta fase y está documentado en README §14.

**Docker `-p apifix`.** Copia del proyecto en el scratchpad con un override del laboratorio:
- CA propia; Mailpit con `MP_SMTP_REQUIRE_STARTTLS`; el worker con `SSL_CERT_FILE`.
- `.env` de producción con `EMAIL_VERIFICATION=required`, `PASSWORD_RESET=on`, `LOG_LEVEL=DEBUG`.
- Límites por IP y cortacircuitos relajados solo para poder medir tiempos.
- He parametrizado `security/checks/fase2_docker_e2e.py` (`E2E_PROJECT`, `E2E_API_PORT`, `E2E_MAILPIT_PORT`). Uso:
  ```
  E2E_PROJECT=apifix E2E_API_PORT=8000 E2E_MAILPIT_PORT=8025 \
    .venv/bin/python security/checks/fase2_docker_e2e.py <compose-dir> [timing]
  ```

Resultado:
- **Pasada completa:** 18 comprobaciones y 0 fallos. Destacado:
  - ST-01: una sola forma de respuesta en 120 registros;
  - ST-03 register: +0,04 ms (p = 0,49); ST-03 forgot: +0,00 ms (p = 0,65);
  - ST-02, ST-08, ST-22, ST-28, ST-17/11/18, ST-44 y ST-10/Q01/Q03 correctos;
  - ST-37: 8782 líneas de log en DEBUG sin tokens, enlaces, direcciones ni la contraseña SMTP;
  - SEC-40: 6 cambios de email → 4 avisos (cupo) y 1 enlace;
  - SEC-41: 8 forgot simultáneos → 1 reset.
- **Ajuste del script en ST-02:** ahora espera 61 s entre el alta y el registro repetido. Con el cupo serializado (SEC-41), un segundo correo a la misma cuenta antes de 60 s se descarta (D3). Antes salían los dos "en el mismo segundo" precisamente por la carrera.
- **Modo `timing`:** ver SEC-45.
- **Además, en el contenedor:**
  - SEC-44 → 0 centinelas en la salida del error;
  - `apigen check` → aviso de usuarios sin verificar;
  - `apigen users verify --all-existing -y` → evento de auditoría;
  - `apigen email test` por STARTTLS verificado → enviado.
- Terminado con `down -v --rmi local`: 0 contenedores.

**`new_api.py`.** Desde una copia del repo con un commit en esa copia, no en el repo real, con `--email-verification optional --password-reset --frontend-url https://app.tienda.example --lang es --title "Tienda Luna"`:
- uv, tests, escáner y commit correctos;
- `.env.example` versionado con los modos, el idioma, la marca y `FRONTEND_URL`; sin remitente ni credenciales;
- el README del cliente describe "optional · on";
- `init-env --production --force` conserva `optional/on/es`.

## 4. Cambios de comportamiento a tener en cuenta

- **Cupos:** los avisos de seguridad y los enlaces a una misma dirección tienen cupo, y el cupo por cuenta ya no se puede superar con trabajos simultáneos. Un registro repetido **en menos de 60 s** tras el alta ya no envía "ya tienes cuenta" (D3; se audita `cooldown`).
- **`request_language()` devuelve `None` sin `Accept-Language`:** el worker decide el idioma (`users.locale` o `MAIL_DEFAULT_LANGUAGE`).
- **Migración:** `users.locale` y `email_log.recipient_hash` se añaden a la **misma** revisión `5e2b7c9d1a34`. No se ha publicado ni comiteado; si alguien la hubiera aplicado ya en local, necesita `apigen db downgrade` + `upgrade`.
- **`.env.example` de la plantilla:** los cupos por cuenta quedan **vacíos**, con los valores por defecto según el entorno, y aparecen 4 variables nuevas: `EMAIL_NOTICES_PER_ACCOUNT_PER_HOUR`, `EMAIL_PER_ADDRESS_PER_HOUR` y `EMAIL_MAX_SECURITY_PER_HOUR/DAY`.
- **Archivos del experto que he modificado:**
  - `security/checks/fase2_checks.py`: tests `test_sec4x_*` invertidos;
  - `security/checks/fase2_config_checks.py`: dos casos Info ahora esperan rechazo;
  - `security/checks/fase2_docker_e2e.py`: parámetros por variables de entorno y espera de 61 s en ST-02.

## 5. Pendiente o justificado

- **R06 / Info-4** (límite global con clave compartida para `forgot`/`resend`/`register`): pospuesto. Los dos presupuestos del cortacircuitos protegen ya los correos de seguridad.
- **SEC-45 residual** de unos 0,1 ms: documentado como aceptable (ver tabla).
- **UX-78:** documentado en vez de cambiar la respuesta.
- Siguen pendientes los SHOULD de la fase anterior: F14 (purga de no verificados), C13 al arrancar, alerta por picos de `invalid_token` y las operaciones de admin por API (descartadas por REQ-F25; sustituidas por la CLI de UX-68).

## 6. Ficheros tocados en esta ronda

**Código:**
- `app/core/{config,exceptions}.py`
- `app/api/deps.py`, `app/api/v1/endpoints/{auth,account}.py`
- `app/services/auth.py`
- `app/tasks/{mail,queue}.py`
- `app/models/{user,email_log}.py`
- `app/email/{__init__,render}.py`, `app/email/backends/{file,smtp}.py`
- `alembic/versions/20260926_1800_5e2b7c9d1a34_account_tokens_email_verification.py`
- `apigen/{cli,docs_accounts,docs}.py`
- `scripts/new_api.py`

**Configuración y documentación:**
- `.env.example`, `compose.mail.yml`
- `docs/postman/API.postman_collection.json`
- `README.txt` (§5, §14, §15), `guia/README.txt` (§16, §17)

**Tests:**
- `tests/{conftest,test_account,test_email,test_new_api}.py`
- `security/checks/fase2_{checks,config_checks,docker_e2e}.py`
- `security/reports/fase2-correcciones.md`
