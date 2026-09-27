# Fase 2 – Validación de seguridad (correo, verificación de email y recuperación de contraseña)

Autor: security-expert · Fecha: 2026-09-26 · Tipo: validación final contra `fase2-plan-seguridad.md`
Entradas: `fase2-plan.md` (decisiones D1–D10, que prevalecen), `fase2-desarrollador.md`.
Marco: OWASP ASVS 4.0.3 N2 y OWASP API Security Top 10 (2023).

## 0. Resumen

- **Veredicto: APTO CON CONDICIONES.** No hay hallazgos críticos ni altos. El diseño acordado
  está bien implementado y 43 de los 45 casos ST quedan verificados; los otros 2 son parciales
  y no hay ningún caso que falle.
- **Antes de entregar a clientes** hay que corregir dos hallazgos de severidad media:
  - **SEC-40:** los avisos de seguridad no tienen cupo por cuenta, y el cortacircuitos global
    funciona como interruptor de denegación de servicio para todo el correo.
  - **SEC-44:** si la configuración es inválida, el error de arranque puede imprimir en claro el
    final del `.env`, incluida `SMTP_PASSWORD`.
- **Recomendado, severidad baja:**
  - **SEC-41:** carrera en el cupo por cuenta.
  - **SEC-42:** `full_name` llega a una dirección no probada a través del aviso `email_changed`.
  - **SEC-43:** los trabajos recuperados tras la caída de un worker o cancelados no vacían el payload.
  - **SEC-45:** canal de tiempo residual en el registro, de alrededor de 1 ms en PostgreSQL.
- **Suite del repositorio:** 305 tests en verde; `ruff check .` y `ruff format --check .` limpios,
  también con mis scripts.

### Cómo lo he verificado

1. **Revisión de código** (tras orientarme con `graphify query`/`explain`):
   - `app/services/account_tokens.py`, `app/api/v1/endpoints/account.py`, `auth.py` y `users.py`;
   - `app/tasks/mail.py`, `queue.py` y `worker.py`;
   - `app/email/*` (backends, `render`, `message`, `links`) y las plantillas;
   - `app/core/config.py`, `apigen/cli.py` (`email test|preview|eject`), `scripts/new_api.py`,
     `docker-compose.yml`, `compose.mail.yml` y la migración.
2. **Scripts propios** en `security/checks/`:
   - `fase2_checks.py`: 12 tests con las fixtures de `tests/conftest.py`. Se ejecuta con
     `.venv/bin/pytest -q -p no:cacheprovider -p tests.conftest security/checks/fase2_checks.py -s`.
     Los tests `test_sec4x_*` pasan cuando el defecto **se reproduce**: al corregirlo hay que
     invertirlos.
   - `fase2_config_checks.py`: 29 configuraciones de producción (`.venv/bin/python security/checks/fase2_config_checks.py`).
   - `fase2_docker_e2e.py`: E2E contra el laboratorio Docker.
3. **Laboratorio Docker `-p apisec2`**, en modo **producción**:
   - Componentes: API en 127.0.0.1:8901, worker, PostgreSQL 17, Redis y Mailpit (web en
     127.0.0.1:8925, porque el 8902 estaba ocupado por otro proceso).
   - SMTP con **STARTTLS obligatorio** y un certificado firmado por una CA de laboratorio.
   - El proyecto se copió al scratchpad, así que no se ha creado ningún `.env` en el repositorio.
   - Al terminar: `down -v --rmi local`. No queda ningún contenedor, volumen ni imagen.

---

## 1. Casos ST → estado → evidencia

| ST | Estado | Evidencia |
|---|---|---|
| ST-01 | Verificado | `test_account.py:453`. `fase2_checks.py::test_st01_*`: cuerpo y cabeceras idénticos byte a byte en los 3 casos, sin `id`. Docker: 120 registros alternados en PostgreSQL → **1** sola forma de respuesta (202) |
| ST-02 | Verificado | `test_account.py:453`. Docker: la cuenta existente recibe "ya tienes cuenta" sin enlace y su contraseña no cambia; el login con la contraseña nueva da 401 |
| ST-03 | **Parcial** | **forgot:** en proceso, dif. de medianas −0,002 ms; en Docker/PG +0,01, −0,01 y +0,03 ms con p = 0,49, 0,81 y 0,43 → cumple. **register:** en Docker/PG el camino "existente" es consistentemente **0,84–1,20 ms más lento**, con p = 0,124, **0,001** y **0,0005** (la última con 200+200 muestras y el worker en reposo). Cumple < 5 ms pero no p > 0,01 → SEC-45 |
| ST-04 | Verificado | `test_account.py:478` (dos registros a la vez → dos 202 y una fila) y `auth.py` (`IntegrityError` → 202) |
| ST-05 | Verificado | `test_account.py:129`. `fase2_checks.py::test_st05_*`: cuenta activa, inactiva, bloqueada, verificada e inexistente → mismo 202 y mismo cuerpo |
| ST-06 | Verificado | `test_account.py:143`. `EmailRequest(StrictInput)` en `app/schemas/account.py:12` |
| ST-07 | Verificado | `test_account.py:129`. El destinatario sale de la BD (`mail.py:306`, `to=user.email`) |
| ST-08 | Verificado | `test_account.py:490`. Docker: contraseña mala → 401; buena → 403 `email_not_verified`, sin tokens. El refresh también se rechaza (`services/auth.py:350`) |
| ST-09 | Verificado | `test_account.py:629`. El worker descarta con `email_taken` (`mail.py:423-426`) |
| ST-10 | Verificado | `test_account.py:312`. En PostgreSQL: 0 hashes que no sean hex de 64, 0 trabajos con tokens en `payload`/`result`/`error`, 0 trabajos terminados con payload |
| ST-11 | Verificado | `test_account.py:117,204`. Docker: reutilizar el token → 400 |
| ST-12 | Verificado | `test_account.py:190` |
| ST-13 | Verificado | `test_account.py:164`. `fase2_checks.py::test_st16_st13_*`: prefijo cambiado y token de reset en `/email/verify` → 400 |
| ST-14 | Verificado | `test_account.py:213`. `invalidate()` en reset, verify, `/users/me/password` y cambio de email |
| ST-15 | Verificado | `test_account.py:560` y `account_tokens.py:116` |
| ST-16 | Verificado | `fase2_checks.py`: 10 KB, NUL, `!$` y cadena vacía en `/reset`, `/validate` y `/verify` → siempre `(400, invalid_or_expired_token)`, y el token real sigue valiendo |
| ST-17 | Verificado | `test_account.py:181`. Docker: contraseña débil → 422, y después `validate` → 204 |
| ST-18 | Verificado | `test_account.py:111`. Docker: tras el reset, el access token → 401 y el refresh → 401 |
| ST-19 | Verificado | `test_account.py:240` (`password_changed_at` corta las IP conocidas) |
| ST-20 | Verificado | `test_account.py:260` |
| ST-21 | Verificado | `test_account.py:240` y `account.py:196-201` (D2) |
| ST-22 | Verificado | `test_account.py:490`. Docker: 204 sin cuerpo, repetido → 204 (D: idempotente), `Cache-Control: no-store` |
| ST-23 | Verificado | `test_account.py:269` |
| ST-24 | Verificado | `test_account.py:660`. En el laboratorio los límites estaban relajados a propósito para medir tiempos, así que no se repitió allí |
| ST-25 | **Parcial** | En secuencia se cumple (`test_account.py:337`). Con trabajos **simultáneos** se supera: en SQLite, `[6, 6, 6, 6, 5]` correos de 6; en PG, 8 `forgot` simultáneos → **4 resets** (lo esperado era 1), y 6 cambios de email → 4 enlaces pese a los 60 s de enfriamiento → SEC-41 |
| ST-26 | Verificado | `test_account.py:436`. Ver además SEC-40: el cortacircuitos lo puede disparar un tercero |
| ST-27 | Verificado | `test_account.py:129` y `mail.py:293` |
| ST-28 | Verificado | `test_account.py:294`. Docker con `X-Forwarded-Host`, `Origin`, `Referer` y `Forwarded` maliciosos → enlace `https://app.lab-cliente.dev/reset-password#token=pr_…`; `Host: evil.example` → 400 (`ALLOWED_HOSTS`) |
| ST-29 | Verificado | Token en el fragmento (Docker). `fase2_checks.py::test_st29_*`: ninguna ruta GET consume tokens. `no-store` presente |
| ST-30 | Verificado | `test_email.py:197`. Docker: `full_name` con `<script>` no aparece en la verificación y sale escapado (`&lt;script&gt;`) en el aviso. El caso `email_changed` es un hallazgo aparte (SEC-42) |
| ST-31 | Verificado | `test_email.py:53`. `fase2_config_checks.py`: CR/LF en `EMAIL_FROM` y en `EMAIL_FROM_NAME` → no arranca |
| ST-32 | Verificado | `test_email.py:211`. `resolve_language` solo devuelve valores de `MAIL_LANGUAGES` (`render.py:95-118`); `MAIL_LANGUAGES=../x` → no arranca |
| ST-33 | Verificado | `test_email.py:247` (`SandboxedEnvironment`, `render.py:72`) |
| ST-34 | Verificado | `test_email.py:319` (20 casos). `fase2_config_checks.py`: 29/29 según lo esperado (backend ausente, console, file o memory; remitente de ejemplo; `FRONTEND_URL` http, localhost, con usuario o fragmento; enlaces sin `{token}` o protocol-relative; `inline`; `custom` fuera de `app.*`; color o idioma inyectados) |
| ST-35 | Verificado | `disabled` + `required` → error al arrancar (también fuera de producción) |
| ST-36 | Verificado | `test_email.py:154` (sin STARTTLS anunciado → fallo). Docker: sin la CA → "el certificado del servidor no es válido"; `ssl` contra un puerto STARTTLS → error TLS; `SMTP_SECURITY=none` hacia `mailpit` → el worker no arranca |
| ST-37 | Verificado | `test_account.py:701`. `fase2_checks.py::test_st37_*`: todos los flujos con DEBUG, 0 tokens, 0 `#token=`, 0 direcciones. Docker: 2307 líneas de API + worker con DEBUG → 0 tokens, 0 enlaces, 0 direcciones y 0 veces la contraseña SMTP. Salvedad: el error de arranque, SEC-44 |
| ST-38 | Verificado | `docker compose config`: la API recibe `SMTP_PASSWORD: ""` y el worker la contraseña. `apigen email test` desde la API no puede autenticarse |
| ST-39 | Verificado | `grep` en `app/`, `apigen/`, `scripts/`, `email_templates/`, `docs/`, `.env.example`, compose, Dockerfile, Makefile y guías: ningún dato del freelancer |
| ST-40 | Verificado | `test_account.py:330`. En PostgreSQL: 0 trabajos `auth.*` con `owner_id` |
| ST-41 | Verificado | `test_account.py:392` (con `sent_at` no se reenvía). La carrera entre trabajos **distintos** es SEC-41 |
| ST-42 | Verificado | `test_account.py:408` y `smtp.py:25-102` (4xx/red → transitorio; 5xx/autenticación/TLS → permanente; `from None`) |
| ST-43 | Verificado | `test_account.py:368` y `mail.py:117-118` (`requested_at` lo pone la API, `email/__init__.py:82`) |
| ST-44 | Verificado | `test_account.py:120`. Docker: aviso "Se ha cambiado tu contraseña de Cliente Lab" sin tokens |
| ST-45 | Verificado | `test_account.py:527` y la migración (`UPDATE users SET email_verified_at = created_at`, línea 31) |

**Totales:** 43 verificados · 2 parciales (ST-03 en el registro, ST-25 con concurrencia) · 0 fallan · 0 sin verificar.

---

## 2. Requisitos MUST

| Grupo | Estado | Comentario |
|---|---|---|
| **T01–T11** (tokens) | Cumple | `pr_/ev_/ec_` + `token_urlsafe(32)`; forma validada antes del hash; `purpose` en todas las consultas; consumo atómico en la misma transacción que el cambio; invalidación; TTL con rangos; solo SHA-256; vinculación a email, estado activo y `password_changed_at`. T03: sin OTP (D9) |
| **E01–E04** (registro uniforme) | Cumple, con matiz | Respuesta idéntica; Argon2 en los dos caminos; carrera → 202. E02 (tiempo) queda **parcial**: ~1 ms de diferencia en PG (SEC-45) |
| **E05** | Cumple según D1 | El 409 solo sigue con `EMAIL_VERIFICATION=off` y está documentado como riesgo aceptado. Aceptable |
| **E06–E10** | Cumple | La API solo encola; `StrictInput`; el destinatario sale de la BD |
| **F01–F04, F11–F13, F20–F25** | Cumple | Orden correcto del reset; 403 solo con la contraseña correcta; migración; cambio de email con contraseña, avisos y revocación. F23 cumple, pero sin cupo (SEC-40) |
| **S01–S04, S06** | Cumple | Nota: la revocación de sesiones va en una transacción posterior al cambio de contraseña (`account.py:204-208`); ver Info-1 |
| **R01, R04, R08** | Cumple | — |
| **R02/R03** (cupo por cuenta) | **Parcial** | Correcto en secuencia; se supera con concurrencia (SEC-41). Los avisos (`auth.notice`) están exentos de cupo (SEC-40) |
| **L01–L05** | Cumple | — |
| **C01–C06** | Cumple | 29/29 configuraciones como se esperaba |
| **C07** | Cumple, con desviación aceptada | `none` solo hacia loopback, sin opt-in (desviación 5). Ver Info-2 sobre `*.localhost` |
| **C08** | N/A (D5) | Sin proveedores HTTP; con `custom` la responsabilidad es del proyecto. Conviene documentar TLS/timeout/sin redirecciones en la guía de `custom` |
| **C09** | **Parcial** | `SecretStr` correcto, pero la validación fallida vuelca parte de la entrada (SEC-44) |
| **C10** | Cumple | Verificado en compose |
| **M01–M05, M07, M08** | Cumple | — |
| **M06** | **Parcial** | Se cumple en la verificación y en "ya tienes cuenta"; `email_changed` lo incumple (SEC-42) |
| **Q01, Q04–Q08** | Cumple | Timeouts: `SMTP_TIMEOUT` 20 s < tarea 120 s < arrendamiento 180 s |
| **Q02** | Cumple, con desviación aceptada | Dos trabajos llevan una dirección (desviación 3), mitigado por `scrub_payload`; ver SEC-43 |
| **G01–G04** | Cumple | Verificado con DEBUG en proceso y en Docker. Excepción: SEC-44 (fuera del logging de la app) |

### Valoración de las desviaciones del desarrollador (§4 de su informe)

| # | Desviación | Valoración |
|---|---|---|
| 1 | Tabla `email_log` | **Aceptable.** Sin direcciones ni contenido y purgada a 2 días |
| 2 | Dos grupos de cupo | **Aceptable**, pero `email_change_confirm` va a direcciones **de terceros** elegidas por el usuario y hoy solo tiene cupo por cuenta (ver SEC-40, recomendación c) |
| 3 | Dirección en el payload de `auth.email_change`/`notice` | **Aceptable** con `scrub_payload`, si se corrige SEC-43 |
| 4 | `EMAIL_DELIVERY=inline` | **Aceptable.** Está prohibido en producción (verificado) y la tarea en segundo plano corre después de enviar la respuesta |
| 5 | `none` hacia loopback sin opt-in | **Aceptable** (lo decide el plan consolidado); Info-2 |
| 6 | Nombres de variables | **Aceptable** |
| 7 | El cortacircuitos reprograma en vez de descartar | **Aceptable en sí**, pero combinado con SEC-40 convierte el límite global en una palanca de DoS |
| 8 | `APP_ENV_FILE`, nombres reservados, niveles de log | **Aceptable.** Los niveles de log de dependencias mejoran G01 |

---

## 3. Hallazgos nuevos

### SEC-40 · Media · API4/API6 (consumo de recursos y flujos de negocio sensibles), ASVS 2.2.1
**Los avisos de seguridad no tienen cupo por cuenta, y el cortacircuitos global se puede disparar desde fuera, lo que para todo el correo del cliente.**

**Evidencia:**
- `mail.py:462`: `auth.notice` llama a `_gate(..., quota=False)`.
- `fase2_checks.py::test_sec40_notices_bypass_per_account_quota`: 8 peticiones a
  `POST /users/me/email` → **8 avisos** a la dirección antigua (el cupo es 3/hora con 60 s de
  enfriamiento). Docker: 6 peticiones → 5 avisos (el sexto aún estaba en cola).
- Solo frena el límite por IP de `RATE_LIMIT_LOGIN` (10/min, 50/h), que se esquiva rotando IP.
  Lo mismo ocurre con `password_changed`.
- `test_sec40_notices_consume_global_breaker_and_block_resets`: con `EMAIL_MAX_PER_HOUR` a 5 por
  encima de lo ya enviado, **una sola cuenta** agota el presupuesto con avisos. Después, el
  `forgot` de **otro** usuario queda `queued` con el error "Email sending paused". Ese reset
  fallará cuando agote los reintentos.
- En el laboratorio (con el límite por defecto de 200/h) el cortacircuitos también se abrió solo
  con altas nuevas: cada alta envía una verificación a una dirección arbitraria.
- En modo `off` + `PASSWORD_RESET=on`, u `optional`, cualquiera puede registrar la dirección de
  la víctima, iniciar sesión y usar `/users/me/email` para enviarle avisos sin límite por cuenta.

**Impacto:**
- Bombardeo de correo a terceros desde el dominio del cliente, con coste y reputación del remitente.
- Denegación de servicio de **todo** el correo transaccional (resets incluidos) durante una hora.

**Recomendación:**
- a) Aplicar a los avisos un cupo propio por cuenta, p. ej. 5/hora; si se supera, se descartan
  con auditoría.
- b) Reservar capacidad en el cortacircuitos para los correos de seguridad (reset, verificación
  y avisos), con presupuestos por tipo o prioridad. Contar aparte, o no contar, los correos que
  un anónimo puede provocar hacia direcciones no verificadas.
- c) Añadir un cupo por **dirección de destino** (hash del email) para `email_change_confirm` y
  los avisos.
- d) Alerta cuando se abra el cortacircuitos (ya se audita con nivel ERROR).

### SEC-41 · Baja · API4, ASVS 2.2.1
**El cupo por cuenta tiene una carrera cuando varios trabajos de la misma cuenta se ejecutan a la vez.**

**Evidencia:**
- `mail.py:142-179`: `_quota_reason` cuenta y después `_gate` inserta en `email_log`, sin
  serializar por cuenta. El worker ejecuta hasta `JOBS_CONCURRENCY` trabajos simultáneos
  (`worker.py`, `create_task`).
- `fase2_checks.py::test_sec41_*` (SQLite): `[6, 6, 6, 6, 5]` correos de 6 trabajos, cuando lo
  esperado era 1.
- Docker/PostgreSQL: 8 `forgot` simultáneos → 4 correos de reset; 6 cambios de email → 4 enlaces
  de confirmación. En otra pasada, la verificación y el "ya tienes cuenta" salieron en el mismo
  segundo pese al enfriamiento.

**Impacto:** el enfriamiento y el tope 3/hora se multiplican por concurrencia × workers
(`--scale worker=N`). Amplía el bombardeo, aunque de forma acotada.

**Recomendación:** serializar por cuenta dentro de `_gate`:
- en PostgreSQL, `pg_advisory_xact_lock(hashtext('email-quota:'||user_id))`, igual que ya se hace
  en `enqueue` (SEC-34);
- o bien `SELECT ... FOR UPDATE` sobre la fila del usuario antes de contar;
- en SQLite basta con la serialización de escritura, si se abre la transacción de escritura
  antes de contar.

Añadir un test concurrente, invirtiendo `test_sec41`.

### SEC-42 · Baja · API6, ASVS 5.2 (REQ-M06)
**Texto libre del usuario (`full_name`) enviado a una dirección nunca probada, a través del aviso `email_changed`.**

**Evidencia:**
- `mail.py:234-236`: `_user_name` comprueba `user.email_verified_at`, pero en `email_changed`
  el destinatario es `old_email` (`mail.py:460`), y al confirmar el cambio el usuario pasa a estar
  verificado **con la dirección nueva** (`account.py:295`).
- `fase2_checks.py::test_sec42_*` (modo `optional`): se registra la dirección de la víctima con
  `full_name="URGENTE visita http://evil.example/claim"`, se entra, se cambia el email a uno propio
  y se confirma → la víctima recibe "The email of your … account was changed" **con el señuelo**.
  Los correos anteriores lo omitían correctamente.

**Impacto:** usar el dominio del cliente para enviar un mensaje de phishing, uno por cuenta.

**Recomendación:** para `email_changed` (y en general para los avisos dirigidos a
`old_email`), decidir si se incluye el nombre según si la dirección **de destino** estaba
verificada. Guardar en el payload `old_email_verified: bool`, o no incluir nunca `user_name`
cuando el destino no es `users.email`.

### SEC-43 · Baja · ASVS 8.3 (datos personales retenidos), REQ-Q03
**Los trabajos que terminan fuera de `run_job` no vacían el payload.**

**Evidencia:**
- `queue.py:236-262` (`reclaim_stale`, que los marca `failed` con "Worker lost") y `queue.py:265`
  (`cancel`) no aplican `scrub_payload`.
- `fase2_checks.py::test_sec43_*`: un trabajo `auth.password_reset` recuperado tras la caída del
  worker y otro cancelado por un admin conservan `{"email": …}`.

**Impacto:** direcciones (y `old_email`/`new_email`) retenidas `JOBS_RETENTION_DAYS` en estos
casos poco frecuentes.

**Recomendación:** en `reclaim_stale` (rama de fallo definitivo) y en `cancel`, vaciar el payload
cuando `get_task(name).scrub_payload` sea verdadero; o hacer que `prune_jobs` vacíe antes los
payload de las tareas con `scrub_payload`.

### SEC-44 · Media · API8 (configuración insegura), ASVS 7.1.1 / 2.10.4
**Un fallo de validación al arrancar imprime la cola del diccionario de entrada, que puede incluir `SMTP_PASSWORD` (u otro secreto) en claro.**

**Evidencia:**
- `app/core/config.py:50`: `SettingsConfigDict` no fija `hide_input_in_errors=True`.
  `_check_security` lanza `ValueError` y pydantic añade `input_value={...}`, recortado por el
  medio pero **con los últimos caracteres**.
- Reproducido con un `.env` de producción cuyo último valor es `SMTP_PASSWORD` y un `EMAIL_FROM`
  de ejemplo:
  `input_value={'ENVIRONMENT': 'producti...WORD': 'SENTINELpw5555'}` → la contraseña completa
  aparece en la salida de `python -c "import app.core.config"`, y por tanto en `uvicorn`/`alembic`
  al arrancar y en los logs del contenedor o del journal.
- `apigen check` sí la oculta (0 coincidencias). En el contenedor del laboratorio el último valor
  era `LOG_LEVEL`, así que ahí no se filtró. Depende del orden.
- Es un **mecanismo previo** (también afectaba a `SECRET_KEY`), pero esta fase lo agrava:
  - añade secretos nuevos;
  - añade una decena de comprobaciones que hacen más probable un arranque fallido (el propio
    `EMAIL_FROM=no-reply@example.com` que deja `new_api.py`);
  - `new_api.py` añade las variables **al final** del `.env`.

**Impacto:** credenciales SMTP (o la clave JWT) en logs que suelen leer terceros (hosting,
agregadores).

**Recomendación:**
- `hide_input_in_errors=True` en `SettingsConfigDict`;
- como defensa adicional, capturar la excepción en `app/core/config.py` y relanzar solo el texto
  de "Configuración insegura" (como ya hace `apigen`);
- test que compruebe que un secreto centinela no aparece en `str(exc)`.

### SEC-45 · Baja · API2, ASVS 2.2 (REQ-E02)
**Canal de tiempo residual en `POST /auth/register` con verificación activa: alrededor de 1 ms en PostgreSQL.**

**Evidencia:**
- Tres mediciones en Docker/PG (`fase2_docker_e2e.py`, también el modo `timing`): el camino
  "existente" tarda **+0,84 / +1,20 / +0,86 ms**, con p = 0,124 / 0,001 / 0,0005.
- Causa probable: `auth.py:127` encola `account_exists` con `commit=True`, y `enqueue` hace
  `commit()` + `refresh(job)` (`queue.py:95-97`). El camino nuevo usa `commit=False` y un único
  `commit()`.

**Impacto:** bajo en la práctica. Con `RATE_LIMIT_REGISTER=5/hour` por IP y el ruido de Internet
hacen falta muchas IP y muchas muestras; cada sonda sobre una cuenta existente envía un aviso a su
dueño; y cada sonda sobre una inexistente **crea** la cuenta. Aun así, incumple el criterio de ST-03.

**Recomendación:** igualar las operaciones de BD de los dos caminos (`enqueue(..., commit=False)`
+ `session.commit()` en ambos, sin `refresh`) y repetir la medición con
`fase2_docker_e2e.py <dir> timing`.

### Informativos (sin acción obligatoria)

- **Info-1:** en `reset_password`, el cambio de contraseña y la revocación de sesiones van en
  transacciones separadas (`account.py:204-208`). Si el proceso muere entre ambas, las sesiones
  sobreviven al reset. Sugerencia: incrementar `token_version` y revocar los refresh tokens en la
  misma transacción que el consumo del token.
- **Info-2:** `_is_local_host` acepta `*.localhost` (`config.py`). `SMTP_SECURITY=none` hacia
  `relay.localhost` se admite en producción, y en Docker o con un DNS propio ese nombre puede
  resolver a un host remoto (credenciales en claro). Solo lo puede configurar el operador.
- **Info-3:** la confirmación del cambio de email responde 409 `email_taken` si la dirección se
  ocupó entretanto (`account.py:300-302`). Solo lo ve quien controla ese buzón, así que no es
  una enumeración útil.
- **Info-4:** una ráfaga de `forgot`/`register` llena la cola: 400–570 trabajos tardaron 100–150 s
  en vaciarse con `JOBS_CONCURRENCY=4`, y los correos legítimos esperan detrás (mismo
  `ACCOUNT_PRIORITY`). Esto refuerza el SHOULD pendiente R06 (límite global compartido).
- **Info-5:** `scripts/new_api.py` escribe `--title` en `MAIL_BRAND_NAME` sin escapar comillas,
  `$` ni saltos de línea. Con un título con `${…}` o `"`, python-dotenv interpola o corta el
  valor. Solo lo introduce el freelancer; basta con validar o escapar.
- **Info-6:** los valores de `compose.mail.yml` (`MP_SMTP_AUTH_ACCEPT_ANY`, `AUTH_ALLOW_INSECURE`)
  son adecuados solo para desarrollo, y los puertos están ligados a 127.0.0.1. Hay que recordar
  que la bandeja web de Mailpit muestra los enlaces con token sin autenticación.

### Controles verificados que funcionan (destacados)

- **Tokens:** opacos de 256 bits, solo el hash en BD, un solo uso atómico, separación estricta
  de propósitos y respuesta 400 uniforme.
- **Enumeración:** `forgot`/`resend` uniformes en contenido y tiempo; login y refresh bloqueados
  para no verificados en `required`, sin revelar nada sin la contraseña.
- **Reset:** revoca todo al instante; desbloqueo silencioso (D2).
- **Enlaces:** solo desde la configuración, con el token en el fragmento, sin GET y con `no-store`.
- **Correo:** STARTTLS o SSL con certificado verificado, sin degradar a texto plano; errores del
  proveedor clasificados y genéricos; cabeceras protegidas con `policy.default`.
- **Plantillas:** en sandbox, con autoescape y el idioma en lista blanca.
- **Datos y logs:** trabajos de sistema con payload vaciado; logs sin tokens ni direcciones,
  incluso en DEBUG.
- **Credenciales y configuración:** solo el worker recibe las credenciales SMTP; la app no
  arranca con configuración de correo insegura.

---

## 4. Veredicto

**APTO CON CONDICIONES** para vender la plantilla con estos flujos:

1. **Bloqueante antes de entregar:**
   - **SEC-40**: cupo en los avisos y presupuesto reservado para los correos de seguridad en el
     cortacircuitos.
   - **SEC-44**: `hide_input_in_errors=True` y un test con un centinela.
2. **Recomendado en esta misma iteración, con poco esfuerzo:** SEC-41 (lock por cuenta), SEC-42,
   SEC-43 y SEC-45.
3. **Re-validación:**
   - invertir los tests `test_sec4x_*` de `security/checks/fase2_checks.py`;
   - repetir `fase2_docker_e2e.py` (incluido el modo `timing`);
   - añadir los tests equivalentes a `tests/`.

No hay hallazgos críticos ni altos, y el riesgo aceptado T3/SEC-05 queda cerrado cuando la
verificación está activa (D1).
