# Ronda 2 — Respuesta del desarrollador

- **Proyecto:** api-template (plantilla FastAPI + generador `apigen`)
- **Fecha:** 2026-09-25
- **Rol:** desarrollador backend senior (`.claude/agents/developer.md`)
- **Entrada:** `ronda1-seguridad.md` (SEC-01…SEC-19) y `ronda1-usuario.md` (UX-01…UX-28, S-1…S-6)

**Estado final**

| Comprobación | Resultado |
|---|---|
| `.venv/bin/pytest -q -p no:cacheprovider` (repo) | **112 passed** (antes 66) |
| `.venv/bin/ruff check .` (repo) | limpio |
| Copia temporal + `apigen generate examples/shop.yaml` + `db migrate` (dos veces) + pytest | **138 passed**, ruff limpio; el segundo `migrate` responde "Sin cambios" |
| Copia con un YAML de casos límite (owned + unique + soft delete, fk→user, fk→recurso solo-admin, enum `mro`/`upper`, json con límite, campo inmutable) | 91 generados + 2 pruebas ad hoc, todo en verde |
| Laboratorio `security/lab.sh` (sin carga) | ver §4 |

`resources/` del repo no existe (no he generado nada dentro del repo real).

---

## 1. Debate: las seis tensiones

### T1. Bloqueo de cuenta (SEC-02) frente a UX y fuerza bruta distribuida

**Decisión: "smart lockout" con orígenes conocidos y bloqueo escalonado.** Es el modelo de Azure AD Smart Lockout adaptado a la plantilla.

- El contador de fallos sigue siendo **por cuenta**. Así, un atacante distribuido sigue limitado a N intentos por ventana en total, no N por IP.
- Al llegar a `LOGIN_MAX_ATTEMPTS`, la cuenta queda bloqueada **para orígenes desconocidos**.
- Una IP (o /64) desde la que el titular **inició sesión con contraseña** en los últimos `LOGIN_FAMILIAR_DAYS` (30) puede seguir entrando.
  - Solo cuentan los tokens emitidos por login (`id == family_id`), no los obtenidos por rotación: quien robe un refresh token no convierte su IP en "conocida".
- El contador **ya no se reinicia al bloquear**. Cada bloqueo consecutivo dobla la duración (15 → 30 → 60 … hasta `LOGIN_LOCKOUT_MAX_MINUTES`=240).
- El contador solo se reinicia con un login correcto o con `POST /users/{id}/unlock`.
- Los intentos durante el bloqueo desde orígenes desconocidos se rechazan sin evaluar la contraseña (hash señuelo para igualar el tiempo) y sin contar.

**Por qué no las alternativas:**

- **Contar por pareja (cuenta, IP):** multiplica por el número de IPs los intentos de una botnet contra una cuenta.
- **Retraso progresivo sin bloqueo:** mantiene conexiones abiertas y no frena a un atacante paciente.
- **CAPTCHA:** fuera del alcance de una API genérica.

**Mensaje:** se mantiene el 401 ambiguo, porque decir "bloqueada" confirma que la cuenta existe. La queja del usuario (S-2) se resuelve de otra forma:

- el titular apenas sufre ya el bloqueo;
- el desbloqueo por admin queda documentado en README y guía;
- el bloqueo se registra en `app.audit`, con nivel ERROR si la cuenta es de un admin.

**Riesgo residual (documentado):** un atacante que comparta IP con la víctima (NAT de oficina o wifi pública) no queda afectado por el bloqueo. Sigue limitado por `RATE_LIMIT_LOGIN` (10/min y 50/h por IP) y por la política de 12+ caracteres. Además, guardamos la IP de cada sesión (dato personal), lo que se indica en el README.

### T2. Detección de reutilización de refresh frente a gracia para pestañas concurrentes

**Decisión: gracia de 10 s (`REFRESH_REUSE_GRACE_SECONDS`, 0 = desactivada), muy acotada.** Solo se aplica si se cumplen todas estas condiciones:

1. el token presentado **fue rotado** (tiene `replaced_by_id`), es decir, no se revocó por logout;
2. el sucesor se emitió hace ≤ 10 s;
3. el sucesor se emitió **a la misma IP** que hace esta petición;
4. el sucesor sigue vivo.

En ese caso se responde **409 `refresh_token_rotated`** y **no se emite nada ni se revoca nada**. La pestaña relee el token guardado y reintenta. En cualquier otro caso se revoca la familia y además se incrementa `token_version` (SEC-16).

**Por qué no debilita la detección de robo:**

- El atacante no obtiene tokens durante la gracia: solo un 409. Desde otra IP, la reutilización dispara la revocación en el acto.
- El caso peligroso sería que el atacante gane la carrera y el cliente legítimo llegue segundo, desde la misma IP y en menos de 10 s.
  - Eso exige compartir IP con la víctima y adivinar el instante de su refresh (cada ~15 min). La probabilidad es de ~1 %, y además en ese caso el atacante ya estaba en la red de la víctima.
  - En cuanto el legítimo reintente con su token viejo pasada la gracia, la familia se revoca.
- No reenvío "el mismo par" (lo que pedía UX-19) porque solo guardamos hashes: habría que guardar el token en claro.
- Tampoco emito un token hermano, porque eso sí regalaría una sesión a quien tuviera el token robado.

### T3. Enumeración en el registro (SEC-05) frente a UX

**Decisión: se mantiene el 409, ahora `code: "email_taken"`. Riesgo aceptado y documentado en el README.**

- Una respuesta uniforme **sin verificación de email** no evita la enumeración: basta con registrar el email con una contraseña conocida e intentar el login. Además empeora la UX (el usuario no sabe si ya tenía cuenta).
- La solución real es la verificación por email con respuesta 202 uniforme. Necesita SMTP o una cola de correo, así que queda **pospuesta**.
- Mitigaciones actuales:
  - el límite de 5/h por IP;
  - el impacto principal que citaba el experto (elegir víctimas para SEC-02) desaparece con T1.

### T4. El límite de registro cuenta intentos rechazados por la política (S-1) frente a anti-abuso

**Decisión: los 422 de política ya no consumen cupo; los 409 y los registros correctos sí.**

- La política de contraseñas pasa del endpoint al esquema `UserRegister` (`PydanticCustomError` de tipo `password_policy`). FastAPI valida el body antes de llamar al endpoint decorado, así que el decorador de SlowAPI no llega a contar.
- **Anti-abuso:**
  - el 422 no crea nada ni calcula Argon2 (es barato de servir);
  - sigue sujeto al límite global por cliente (`RATE_LIMIT_GLOBAL`), que la dependencia global aplica antes;
  - el 409 sigue contando (frena la enumeración).
- Además, fuera de producción el 429 incluye un `hint` con las variables a ajustar.

### T5. 409 genéricos (UX-10) frente a no filtrar información (SEC-09)

**Decisión: el 409 lleva `code` y `fields` (solo nombres de columna, nunca valores ni SQL), y la causa raíz de SEC-09 se corrige en el generador.**

- `code` distingue:
  - `unique_violation` (+ `fields: ["isbn"]`);
  - `has_dependents` (DELETE de una fila referenciada);
  - `reference_violation`;
  - `not_null_violation`.
- Los nombres de campo ya son públicos en OpenAPI.
- En recursos `owned`, la unicidad pasa a ser **por propietario** (`UniqueConstraint("owner_id", campo)`). Así, el 409 solo informa sobre datos del propio usuario y deja de ser un oráculo entre usuarios.
- Con `soft_delete`, se usa un índice único parcial `WHERE deleted_at IS NULL`, lo que también resuelve UX-11.
- La detección funciona en SQLite (texto del error) y en PostgreSQL (`sqlstate` y `constraint_name`, que se resuelven contra `SQLModel.metadata`). PostgreSQL no se ha podido probar en este entorno.

### T6. Formato e idioma de los errores y CORS en desarrollo

- **Formato: sin RFC 9457.** Se mantiene `detail` compatible con FastAPI (texto, o lista `{loc,msg,type}` en los 422), porque cambiarlo rompería clientes y la convención de Swagger.
  - Se **añade** `code` estable en **todas** las respuestas de error (401/403/404/409/413/415/422/429/500), mediante un handler de `HTTPException` y la clase `APIError`.
  - Todos los errores de validación propios llevan ya `type`: `password_policy`, `immutable_field`, `null_not_allowed`, `null_character`, `reference_not_found`, `unknown_parameter`, `json_too_large`, `json_too_deep`.
  - Es un cambio aditivo: no rompe la API pública.
- **Idioma:** los mensajes de la API pasan a **inglés**, igual que los de FastAPI y Pydantic que ya salían en inglés, y el cliente traduce a partir de `code`/`type`. La **CLI sigue en español**, con los mensajes de Pydantic más comunes traducidos.
  - Cambio visible: los textos de la política de contraseñas y de `null` ahora están en inglés. Nadie debería depender de esos textos, porque para eso está `type`.
- **CORS en desarrollo:** con `ENVIRONMENT=development` y `CORS_ORIGINS` vacío, se aceptan `http(s)://localhost|127.0.0.1|[::1]:<puerto>` (regex) sin credenciales.
  - En `testing` y `production` no cambia nada: vacío significa CORS desactivado.
  - El riesgo es nulo fuera de desarrollo; dentro, solo afecta a orígenes locales.

---

## 2. Respuesta punto por punto: seguridad

Leyenda: **A** aceptado, **P** parcial, **R** rechazado, **Pos** pospuesto.

| ID | Decisión | Justificación | Cambio (ficheros) | Test |
|---|---|---|---|---|
| **SEC-01** Carrera en refresh → 500 y familia viva | **A** (obligatorio) | Bug confirmado: `row.user_id` tras `rollback()` produce `MissingGreenlet`. | `app/services/auth.py`: se copian `token_id/family_id/user_id/expires_at/scope` antes de cualquier rollback; la rama "perdí la carrera" y la de "ya revocado" comparten `_handle_revoked()`, que relee el estado fresco de la BD. Con gracia 0 o desde otra IP → 401 y la familia revocada. | `test_refresh_race_loser_revokes_family_without_grace` (reproducción determinista de la carrera: sesión con fila obsoleta en el identity map; comprobado que entra en la rama del rollback), `test_concurrent_refresh_never_returns_500` (`asyncio.gather` real por HTTP), `test_refresh_rotation_and_reuse_detection`. Laboratorio: `[200, 401]` con el token del ganador revocado (con gracia 0) y 0 trazas. |
| **SEC-02** Bloqueo explotable por terceros | **A** | Ver T1. | `app/services/auth.py` (`authenticate`, `_is_familiar`, `lockout_minutes`, `_register_failure`), `app/core/config.py` (`LOGIN_LOCKOUT_MAX_MINUTES`, `LOGIN_FAMILIAR_DAYS`), `app/models/refresh_token.py` (`client_ip`) + migración `alembic/versions/20260925_1900_a7d3c2e1b4f0_refresh_token_client_ip.py`, auditoría (`app/core/audit.py`), documentación (README, guía, `.env.example`). | `test_lockout_by_third_party_does_not_lock_out_owner`, `test_account_lockout`, `test_lockout_duration_escalates`, `test_admin_unlock_resets_lockout` |
| **SEC-03** Compose arranca en development | **A** | Precedencia de Compose: `environment` > `env_file`. | `docker-compose.yml`: `ENVIRONMENT: production` en `environment:` y comentario `apigen init-env --production`. `Dockerfile`: el CMD se niega a arrancar si `ENVIRONMENT != production`, salvo `ALLOW_NON_PRODUCTION=1`. `apigen init-env --production` deja `ALLOWED_HOSTS=` para obligar a rellenarlo y enumera lo que falta. | `test_init_env_output_loads[True]` (en producción solo falla por `ALLOWED_HOSTS`). No hay Docker en el entorno: verificación estática. |
| **SEC-04** Sin `TRUSTED_PROXIES` detrás del proxy | **A** (parcial en HSTS) | Hay que confiar en el proxy, no forzar HSTS a ciegas. | Compose: `TRUSTED_PROXIES=${TRUSTED_PROXIES:-172.16.0.0/12}` (red bridge; el puerto solo se publica en 127.0.0.1; comprobado que el `ProxyHeadersMiddleware` de uvicorn acepta CIDR). Aviso al arrancar en producción con `TRUSTED_PROXIES` vacío (`config.py`), en amarillo en `apigen check`. Con el proxy de confianza, `X-Forwarded-Proto` fija `scheme=https` y HSTS se envía. **`HSTS_FORCE` rechazado:** tapa la mala configuración en lugar de corregirla, y las IP seguirían siendo globales. | Aviso verificado en el laboratorio (log de arranque). |
| **SEC-05** Enumeración en el registro | **R/Pos** | Ver T3. Riesgo aceptado; la verificación de email queda pospuesta. | `code: email_taken`; README (§10, riesgos aceptados). | `test_duplicate_email` |
| **SEC-06** 500 sin cabeceras ni X-Request-ID | **A** (obligatorio) | — | `app/core/middleware.py`: `UnhandledErrorMiddleware`, el middleware más interno, convierte la excepción en un JSON 500 que después recibe CORS, cabeceras de seguridad y X-Request-ID. Con `DEBUG=true` deja pasar la traza. `app/core/errors.py`: `log_unhandled`, `internal_error_body`. `app/main.py`: orden de middlewares. | `test_500_keeps_security_headers_and_request_id` |
| **SEC-07** Enteros sin límite → 500; NUL en PostgreSQL | **A** (obligatorio) | — | Generador: todo `int` sale con `ge/le` acotados a 64 bits (los límites del YAML se recortan a ese rango). Columna `BigInteger` si el rango no cabe en int4 (así PostgreSQL no desborda con 2^31); `Integer` si cabe (p. ej. `quantity 1..100`). Filtros `int` también acotados (`apigen/spec.py` `int_bounds/fits_int32`, `apigen/codegen.py`). NUL: `StrictInput` rechaza `\x00` en cualquier texto, también dentro de JSON (`null_character`), y el login lo trata como credencial inválida. Red de seguridad: `DataError` y `OverflowError` → 422 `invalid_value` (`errors.py`). | `test_int_fields_are_bounded_and_use_bigint_when_needed`, `test_nul_character_is_422_not_500`; plantilla: `test_int_out_of_range_is_422` en cada recurso con `int`. Laboratorio: el POST con `stock=2^63` ya no llega a la BD. PostgreSQL no probado (no disponible). |
| **SEC-08** Permisos inseguros aceptados | **P** | Algunos casos son legítimos (blog: owned + lectura pública). Se bloquea solo lo que nunca tiene sentido. | `apigen/spec.py`: **error** para owned + `update/delete=user`. **Aviso** (no bloquea) para owned + `list/read` public/user y para `read` más permisivo que `list`. Los avisos se muestran en `add/generate` y en `apigen list` (`apigen/cli.py`). No se genera un "test que documente la exposición": el aviso cumple ese papel con menos ruido. | `test_insecure_permission_combinations` |
| **SEC-09** Unicidad global en owned | **A** | Ver T5. | `apigen/codegen.py` (`table_args`, `unique_in_table`), `model.py.j2` (`__table_args__`). `unique: global` como opción: **pospuesto**; quien lo necesite puede editar el modelo generado. | `test_owned_unique_is_per_owner_and_soft_delete_uses_partial_index`; ad hoc en la copia: dos usuarios crean la misma `label` (201/201) y el mismo usuario la repite (409 `fields=["label"]`). |
| **SEC-10** FK sin control de visibilidad | **P** | La existencia de un usuario por UUIDv7 no es enumerable en la práctica. Aun así, el 409 frente al 201 y el enlace a destinos solo-admin se corrigen. | fk→`user`: `ensure_reference(User, …)` → 422 uniforme `reference_not_found`. Destino con `read: admin`: `allowed=principal.is_admin` → 422 sin consultar la BD (`app/crud/base.py`, `router.py.j2`, `codegen.py`). **No** se restringe fk→user a `principal.user_id`: rompería casos legítimos (`assignee_id`); se deja a criterio del autor. | `test_fk_references_are_checked_for_users_and_admin_only_targets`; ad hoc en la copia: usuario → 422 contra `secret_doc`, admin → 201, `assignee_id` inexistente → 422. |
| **SEC-11** Huecos del rate limiting | **A** | — | Rutas inexistentes: el handler de 404/405 sin endpoint aplica los límites por defecto y global (`check_unrouted_limit`). Redis caído: `_evaluate_with_fallback` pasa a memoria (antes dejaba pasar sin límite) y reintenta el backend cada 30 s. Semántica documentada ("por cliente") en `rate_limit.py`, `.env.example` y README. `slowapi>=0.1.10,<0.2` en `pyproject.toml` (y `uv.lock` actualizado offline). | `test_unrouted_requests_are_rate_limited`, `test_default_rate_limit_applies_to_included_routers` (antes era inestable al cruzar el minuto con la ventana deslizante; ahora es robusto). Laboratorio: 120×404 y después 429. Fallback de Redis no probado (no hay Redis). |
| **SEC-12** `EmailStr` en respuestas → 500; PII en el log | **A** (obligatorio) | — | `UserRead.email: str` (la entrada sigue con `EmailStr`). Los esquemas generados ya usaban `str` en la salida. `log_unhandled` registra `ResponseValidationError` solo con `loc/type`. `security/lab.sh` crea `@example.com`. | `test_me_works_with_special_use_email_domain`, `test_response_validation_errors_are_logged_without_values` |
| **SEC-13** Auditoría insuficiente; inyección en logs | **A** | — | Nuevo `app/core/audit.py` (logger `app.audit`). Eventos: `auth.login.success/failure/blocked`, `auth.account.locked` (ERROR si es admin), `auth.refresh.reuse/concurrent`, `auth.register`, `auth.password.change`, `auth.logout_all`, `admin.user.create/update/unlock/delete`. Registran IDs e IP, nunca emails ni secretos. `app/core/logging.py`: `TextFormatter` escapa los caracteres de control y añade los campos `extra`. | `test_text_logs_escape_control_characters`. Laboratorio: `GET /api/v1/x\x0aFAKE LOG` en una sola línea; eventos `auth.refresh.reuse` visibles en texto. |
| **SEC-14** JSON sin límite | **P** | Tamaño y profundidad: sí. Excluir json/text de los listados: pospuesto (cambia el contrato de los listados). | `json` con `max_length` por defecto de 16 KiB serializados (configurable con `max=`) y profundidad ≤ 10 (`app/schemas/common.py` `check_json_size`, `codegen.py`). | `test_json_size_and_depth_limits`, `test_json_fields_have_size_limit`; ad hoc: `json_too_large`. |
| **SEC-15** Política de contraseñas y alta | **Pos** | Lista top-100k o HIBP: dependencia de datos o de red; mejor como opción futura (`PASSWORD_BREACH_CHECK`). La verificación de email va con T3. | Aviso sobre `ALLOW_REGISTRATION` en la salida de `init-env --production` y en el checklist del README. | — |
| **SEC-16** El access token sobrevive a logout y a la reutilización | **P** | Reutilización (compromiso): se invalida también el access token. `/logout`: por diseño (TTL de 15 min); para cortar al instante está `/logout-all`. Un refresh revocado por logout ya **no** dispara la revocación de familia ni `token_version` (evita efectos colaterales por bugs del cliente). | `auth.py` (`_handle_revoked` → `token_version + 1`); docstrings de `/logout` y README. | `test_refresh_rotation_and_reuse_detection` (el access token cae), `test_logged_out_token_reuse_has_no_side_effects` |
| **SEC-17** Detalles JWT/admin | **P** | Claves antiguas: se validan (≥ 32 caracteres en producción). `kid` derivado: **R**. Son 64 bits de SHA-256 de un secreto de ≥ 256 bits: atacar el `kid` sin conexión cuesta lo mismo que atacar la firma y no aporta nada. Anillo asimétrico: **Pos**. TOCTOU del último admin: **Pos** (baja probabilidad y se recupera con `createsuperuser --promote`; un bloqueo correcto requiere `SELECT … FOR UPDATE`, que SQLite no tiene). | `config.py` | `test_weak_previous_jwt_keys_rejected_in_production` |
| **SEC-18** *Hardening* del despliegue | **P** | `POSTGRES_PASSWORD` obligatorio (`${…:?}`) y generado por `init-env`: sí. Auditoría de dependencias: target `make audit` (`uv export \| uvx pip-audit`); no se ha ejecutado por falta de red. Digests de imagen, usuario de migración separado y `requirepass` en Redis: **Pos** (coste de mantenimiento; Redis no publica puertos). | `docker-compose.yml`, `.env.example`, `Makefile`, `apigen/cli.py` | `test_init_env_output_loads` (genera `POSTGRES_PASSWORD`) |
| **SEC-19** Robustez del generador | **A** | — | Se reservan `session`, `principal`, `page`, `request` y `response`. Los miembros de enum `mro`, `_x` o que tapan métodos de `str` se renombran a `v_*` (el valor no cambia). `pattern` se valida también con el motor de Pydantic (Rust): se rechazan look-around y backreferences. | `test_filter_names_that_clash_with_endpoint_params_rejected`, `test_enum_members_that_break_enum_are_renamed`, `test_pattern_unsupported_by_pydantic_rejected` |

---

## 3. Respuesta punto por punto: usuario

| ID | Decisión | Justificación / cambio (ficheros) | Test |
|---|---|---|---|
| **UX-01** `.env` de `init-env` no arranca | **A** (obligatorio) | `env_ignore_empty=True` en `Settings` (`config.py`): `VAR=` equivale a no definirla. Documentado en `.env.example`. | `test_init_env_output_loads[False/True]` (ejecuta `init-env` con `CliRunner` y carga el `.env`) |
| **UX-02** Refresh concurrente → 500 | **A** (obligatorio) | = SEC-01. | ídem SEC-01 |
| **UX-03** `db migrate` sin cambios → traceback | **A** (obligatorio) | `apigen/cli.py`: `_script_path()` acepta `None`, `[]`, `[Script]` y `Script`. | `test_migrate_script_path_handles_all_alembic_results`; en la copia, el segundo `migrate` responde "Sin cambios en los modelos". |
| **UX-04** Sin README | **Ya resuelto** / ampliado | El README ya existía. Añadidos: ejemplos curl de auth (con `--data-urlencode`), tabla de `code` de error, refresh con pestañas, bloqueo y desbloqueo, CORS de desarrollo, versionado, despliegue detrás de proxy y riesgos aceptados. La guía se ha actualizado igual. | — |
| **UX-05** Enum con `\|` en la shell | **A** | Se acepta también `,` como separador (`enum=a,b`). `apigen types` y la guía muestran los ejemplos entre comillas. Aviso si un enum tiene una sola opción. | `test_cli_enum_accepts_commas_and_warns_single_choice` |
| **UX-06** YAML mal formado → traceback | **A** | `load_specs` captura `yaml.YAMLError` y muestra `fichero:línea:col: YAML no válido: …`. También valida que la raíz sea un recurso o `resources: [...]`. | `test_yaml_syntax_error_is_reported_with_position` |
| **UX-07** Errores de la CLI | **P** | Traducidos los mensajes de Pydantic más comunes (literal, extra, int, float, bool, missing). Sugerencias con `difflib` para tipos y campos de filters/search/ordering. Nombres de la CLI (`max`, `min`, `digits`, `places`). Sin prefijo `-:`. El mensaje de `owner` menciona `--owned`. No se ha cambiado que un error dependiente aparezca en una segunda pasada (validación por capas de Pydantic). | `test_cli_errors_are_translated_with_suggestions` |
| **UX-08** Recurso nuevo en v1 con v2 activa | **A** (en `add`) | Por defecto, la versión más reciente no deprecada (`project.default_version`). El resumen muestra "`recurso: /plural en v2`". En YAML sin `versions:` sigue siendo v1 (compatibilidad de las specs existentes). | Verificado en la copia (`add coupon` → v2). |
| **UX-09** Versiones que no aíslan esquemas | **P** (docs) / **Pos** (esquemas por versión) | Esquemas por versión es un cambio grande del generador. Se documenta con claridad en README, guía y `app/api/versions.py`, incluido el riesgo de `--force` sobre endpoints editados. | — |
| **UX-10** 409 genérico | **A** | Ver T5: `errors.py` (`describe_integrity_error`). | `test_integrity_errors_are_described_without_leaking`; plantilla `test_unique_*` (comprueba `code` y `fields`). |
| **UX-11** Soft delete + único | **A** | Índice único parcial `WHERE deleted_at IS NULL` (SQLite y PostgreSQL). Alembic lo autogenera, y un segundo `migrate` no produce diferencias. | Plantilla `test_unique_*`: borrar y volver a crear → 201. |
| **UX-12** Caducado frente a inválido | **A** | `TokenExpired` (solo si la firma es válida). `code: token_expired` / `invalid_token` / `not_authenticated`, y `WWW-Authenticate: Bearer error="invalid_token", error_description=…` (RFC 6750). | `test_expired_token_is_distinguishable` |
| **UX-13** Formatos de auth | **P** | Se mantiene el login por formulario (flujo password de OAuth2 y botón Authorize de Swagger). Con JSON → **415** `login_expects_form` con un mensaje explícito. Documentado `--data-urlencode`. No acepto JSON en paralelo: duplicaría la superficie y la documentación del endpoint. | `test_login_with_json_gets_explicit_error` |
| **UX-14** Formato inconsistente | **P** | Ver T6: `code` en todas las respuestas, `type` en todos los 422 y API en inglés. No se adopta RFC 9457, para no romper clientes. | `test_error_bodies_have_stable_codes`, `test_partial_update_messages` |
| **UX-15** PATCH a campo inmutable | **A** | `PartialUpdate.__immutable__` → 422 `immutable_field` ("These fields cannot be modified after creation: …"). La plantilla lo rellena. | `test_partial_update_messages`; plantilla `test_immutable_field_rejected_on_patch`. |
| **UX-16** Parámetros desconocidos ignorados | **P** | 422 `unknown_parameter` solo cuando el parámetro es un **campo del recurso no filtrable** (lista los filtros válidos) o un nombre típico de otras APIs (`page`, `size`, `per_page`, `page_size`, `sort`, `order`, `search`). El resto se ignora, como marca HTTP, para no romper cachés con `_=123`. `deps.query_guard` + plantilla. La descripción del listado en OpenAPI enumera filtros, búsqueda y orden. | Plantilla `test_unknown_pagination_param_is_rejected`; ad hoc: `?counter=3` → "not filterable". |
| **UX-17** CORS en desarrollo | **A** | Ver T6 (`main.py`, `.env.example`). | `test_dev_cors_allows_localhost_frontends` |
| **UX-18** OpenAPI incompleta y cabeceras de versión | **A** | `deprecated=True` en las operaciones de versiones deprecadas. `responses` 401/403/404/409/429 con modelo `ErrorBody` en los routers generados. `description` del recurso en create/list y `examples` de los campos en `Create`. `PROJECT_DESCRIPTION` → `info.description`. `Deprecation: @epoch` (RFC 9745, con `deprecated_since` que guarda `version deprecate`) y `Sunset` como HTTP-date (RFC 8594). | `test_deprecation_headers_follow_rfcs` |
| **UX-19** Pestañas que cierran la sesión | **A** (acotado) | Ver T2. | `test_refresh_race_same_client_within_grace_keeps_session`, `test_reuse_after_grace_period_revokes` |
| **UX-20** `version list` y `--sunset` | **A** | `version list` muestra activa/deprecada, desde cuándo y la retirada. Aviso si el sunset ya pasó; informa si ya estaba deprecada (y conserva la fecha original de deprecación). Validación real de la fecha. | Verificado en la copia. |
| **UX-21** `remove` | **A** | Primero comprueba dependencias y después pregunta. Con `n` imprime "Cancelado: no se ha borrado nada." (`project.dependents`). | Verificado en la copia. |
| **UX-22** Ayuda de la CLI | **P** | `--tests/--no-tests`. `-v` se mantiene (ya publicado; la ayuda dice "Versión(es)…"). `createsuperuser` documenta `APIGEN_SUPERUSER_PASSWORD` y, sin TTY, falla con esa sugerencia. Aviso de plural en `add books`. "Show this message and exit" en inglés: **R** (texto interno de click/typer; traducirlo exige parches frágiles). | Verificado en la copia. |
| **UX-23** `check` e `init-env --production` | **A** | `check` usa la instancia del módulo (sin aviso duplicado) y limpia el ruido de Pydantic. `init-env --production` fija `DEBUG=false`, vacía `ALLOWED_HOSTS` para obligar a rellenarlo, genera `POSTGRES_PASSWORD` y lista qué rellenar. | `test_check_error_is_clean`, `test_init_env_output_loads[True]` |
| **UX-24** `db migrate` verboso | **A** | Log de Alembic a WARNING salvo con `--verbose` (`alembic/env.py`). `-m` opcional ("update models AAAA-MM-DD"). Tras `generate --force` sugiere `update …` en lugar de `add …`. Mensaje coherente: "Ya aplicada en esta BD. Revísala antes de desplegarla en producción." | Verificado en la copia. |
| **UX-25** "No puede contener tu email" | **A** | "must not contain the first part of your email ('alice')". | `test_password_policy_message_names_email_part` |
| **UX-26** `/`, cabeceras de rate limit y 307 | **P** | `GET /` con enlaces solo si los docs están activos (en producción sigue en 404). `X-RateLimit-Reset` entero y `Retry-After` solo en 429 (`RateLimitHeadersMiddleware`). Redirección 307 por barra final: **R** (comportamiento estándar de Starlette, inocuo, y `TrustedHost` protege el `Host`). | `test_rate_limit_header_cleanup` |
| **UX-27** Admin no puede crear usuarios | **A** | `POST /api/v1/users` (admin; rol opcional; misma política de contraseñas; 409 `email_taken`; auditado). | `test_admin_can_create_users` |
| **UX-28** `logout` frente a `logout-all` | **A** (docs) | Por diseño (JWT sin estado). Documentado en el docstring de `/logout`, en el README y en la guía. | — |
| **S-1** Límite de registro | **A** | Ver T4. | `test_weak_passwords_do_not_consume_register_quota` |
| **S-2** Bloqueo ambiguo | **P** | Ver T1: el mensaje sigue siendo ambiguo, pero el titular ya no queda fuera desde su IP; desbloqueo documentado. | ver SEC-02 |
| **S-3** Revocación de familia | **P** | Ver T2. | ver UX-19 |
| **S-4** Parte local del email | **A** | = UX-25. | — |
| **S-5** `extra="forbid"` | Se mantiene | Solo mejora el mensaje de inmutables (UX-15). | — |
| **S-6** CORS cerrado | **A** (solo desarrollo) | = UX-17. | — |

---

## 4. Verificación en el laboratorio (sin pruebas de carga)

`./security/lab.sh` (producción, SQLite, rate limit en memoria) sobre una copia:

- **SEC-01, con gracia por defecto** (`refresh_race.py` adaptado a `@example.com`): `códigos=[200, 409]` ×3.
  - El script lo marca como "familia NO revocada", pero es el comportamiento buscado: las dos peticiones salen del mismo cliente (127.0.0.1), así que es el caso "dos pestañas".
- **SEC-01, con `REFRESH_REUSE_GRACE_SECONDS=0`**, que emula a un atacante desde otra IP: `códigos=[200, 401]` ×3 y el token del ganador → **401 (familia revocada)**. 3 eventos `auth.refresh.reuse` y **0 trazas / 0 `MissingGreenlet`** en el log.
- **5 refresh concurrentes:** `[200, 409, 409, 409, 409]` (antes `[200, 401, 500, 500, 500]`).
- **SEC-05:** `409 {"detail":"Email already registered","code":"email_taken"}`.
- **SEC-11:** 125 peticiones a `/nope` → 120×404 + 5×429.
- **SEC-13:** `GET /api/v1/x%0aFAKE%20LOG` → una sola línea con `\x0a`.
- **SEC-02:** el laboratorio no permite simular varias IP sin `TRUSTED_PROXIES`, así que se cubre con tests (`client_from(ip)` en `tests/conftest.py`).

**Nota para el experto:** `security/lab.sh` crea ahora `admin|alice|bob@example.com`. `refresh_race.py` usa la clave `alice@lab.test` en `credentials.json` y habrá que cambiarla; `lab_checks_2.py` funciona tal cual. No he modificado sus scripts. Los he excluido de ruff (`extend-exclude`), porque son scripts de laboratorio que no forman parte del producto.

**Pendiente de entorno** (no disponible aquí): PostgreSQL (NUL, int4/int8, `constraint_name` en el 409, índice parcial), Redis (fallback) y Docker (SEC-03/SEC-04), además de `pip-audit` (`make audit`).

---

## 5. Cambios que afectan a la API pública (documentados)

- Todas las respuestas de error añaden `code`. Es aditivo: `detail` se mantiene.
- Los mensajes de la política de contraseñas y de `null` pasan al inglés. Los errores de política llegan como 422 de validación (`type: password_policy`, `loc: ["body"]`) en lugar de `loc: ["body","password"]`.
- `/auth/login` con JSON responde 415 (antes, un 422 confuso).
- `/auth/refresh` puede responder 409 `refresh_token_rotated`.
- Listados generados: 422 con `page/size/sort/...` o con campos no filtrables.
- Nuevo `POST /api/v1/users` (admin).
- Código generado:
  - unicidad por propietario en recursos owned;
  - índice parcial con soft delete;
  - `int` acotados y BIGINT;
  - límite de 16 KiB en `json`;
  - comprobación de fk→user.

  Afectan a recursos **regenerados**; requieren `apigen db migrate`.
- Nueva migración `a7d3c2e1b4f0` (`refresh_tokens.client_ip`).

## 6. Pospuesto (mejora futura)

- Verificación de email con registro 202 uniforme (SEC-05 y SEC-15).
- Comprobación de contraseñas filtradas (HIBP con k-anonimato o lista top-100k) (SEC-15).
- Esquemas por versión en el generador (UX-09).
- Anillo de claves asimétricas y bloqueo del último admin con `FOR UPDATE` (SEC-17).
- Digests de imagen, usuario de BD para migraciones y `requirepass` en Redis (SEC-18).
- `unique: global` en recursos owned (SEC-09).
- Excluir `json/text` de los listados (SEC-14).

## 7. Ficheros modificados

**Aplicación**
- `app/core/config.py`: `env_ignore_empty`; nuevos ajustes de lockout, gracia y `PROJECT_DESCRIPTION`; avisos y validaciones de producción.
- `app/core/exceptions.py` **(nuevo)**: `APIError` y códigos por defecto.
- `app/core/audit.py` **(nuevo)**: logger `app.audit`.
- `app/core/errors.py`: handler de `HTTPException` con `code` y límite para rutas inexistentes; 409 descriptivo; `DataError`/`OverflowError` → 422; log sin PII; hint en el 429.
- `app/core/middleware.py`: `UnhandledErrorMiddleware` y `RateLimitHeadersMiddleware`.
- `app/core/rate_limit.py`: fallback a memoria, `check_unrouted_limit` y documentación de la semántica.
- `app/core/logging.py`: `TextFormatter` con escape de caracteres de control y campos `extra`.
- `app/core/security.py`: `TokenExpired` y mensajes de la política en inglés.
- `app/services/auth.py`: SEC-01, SEC-02, SEC-16, UX-19 y auditoría.
- `app/api/deps.py`: 401 con `code` y RFC 6750; `query_guard`; `error_responses`/`ErrorBody`.
- `app/api/v1/endpoints/auth.py`: política en el esquema, 415 en el login, IP del cliente y auditoría.
- `app/api/v1/endpoints/users.py`: `POST /users` (admin), códigos y auditoría.
- `app/api/versions.py`: `deprecated_since` y cabeceras RFC 9745/8594.
- `app/main.py`: middlewares, CORS de desarrollo, `deprecated` en OpenAPI, `GET /` en desarrollo y `description`.
- `app/schemas/common.py`: rechazo de NUL, `__immutable__`, errores tipados y `check_json_size`.
- `app/schemas/user.py`: `email: str` en la salida, validador de política y `UserAdminCreate`.
- `app/models/refresh_token.py`: `client_ip`.
- `app/crud/base.py`: `ensure_reference(allowed=…)` y `type` en el 422.

**Migraciones**
- `alembic/env.py`: modo silencioso.
- `alembic/versions/20260925_1900_a7d3c2e1b4f0_refresh_token_client_ip.py` **(nueva)**.

**Generador**
- `apigen/spec.py`: nombres reservados, `int_bounds`, `json` de 16 KiB, `pattern` compatible con Pydantic, error y avisos de permisos, errores de YAML, mensajes traducidos con sugerencias, enum con `,`.
- `apigen/codegen.py`: `int` acotado + BIGINT, límite de `json`, `__table_args__` (unicidad por propietario o parcial), referencias a user y destinos solo-admin, enums seguros, descripciones y datos para los tests nuevos.
- `apigen/project.py`: `version_info`, `default_version`, `dependents`, `deprecated_since`.
- `apigen/cli.py`: `db migrate` (UX-03/24), `remove`, `version list/deprecate`, `init-env --production`, `createsuperuser` sin TTY, `check`, `--tests/--no-tests`, avisos, `types`.
- `apigen/templates/model.py.j2`, `schemas.py.j2`, `router.py.j2`, `test.py.j2`.

**Tests**
- `tests/conftest.py`: `client_from(ip)` y `create_user(email=…)`.
- `tests/test_auth.py`, `tests/test_users.py`, `tests/test_security.py`, `tests/test_generator.py`.
- `tests/test_config.py` **(nuevo)**.

**Despliegue, configuración y documentación**
- `.env.example`, `docker-compose.yml`, `Dockerfile`, `Makefile` (`audit`).
- `pyproject.toml`: `slowapi<0.2`, per-file-ignores de los ficheros de registro y `extend-exclude` de `security/checks`.
- `uv.lock`: solo el especificador de slowapi.
- `security/lab.sh`: `@example.com`.
- `README.txt`, `guia/README.txt`.
- `security/reports/ronda2-desarrollador.md` (este informe).
