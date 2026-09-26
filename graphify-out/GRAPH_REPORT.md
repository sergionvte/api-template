# Graph Report - api-template  (2026-09-26)

## Corpus Check
- 99 files · ~82,341 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1258 nodes · 2804 edges · 110 communities (73 shown, 22 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 293 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- services/auth.py
- cli.py
- test_config.py
- rate_limit.py
- ResourceSpec
- test_generator.py
- task
- test_auth.py
- middleware.py
- errors.py
- crud/base.py
- main.py
- schemas/user.py
- users.py
- deps.py
- test_users.py
- Round 3 security verification report
- 3. Hallazgos nuevos
- Round 1 security audit report
- JSONTrustedHostMiddleware
- Round 1 user experience report
- main
- conftest.py
- ronda5_checks.py
- project.py
- run_loadtest.sh
- test_security.py
- Ronda 5: informe del usuario (revisión completa e integración con graphify)
- ready
- logging.py
- .__call__
- Security and usability review summary (4 rounds)
- resolve_db.py
- lab.sh
- Round 4 developer closing response
- session.py
- client_from
- Round 3 user verification report (8.5/10)
- list_users
- ronda3_checks.py
- T2 10 s refresh reuse grace (409 refresh_token_rotated)
- helpers.py
- _claims
- Pagination
- lab_checks_2.py
- SEC-05 email enumeration at registration
- test_loadtest_db.py
- test_swagger_token_url_uses_active_version
- Environment
- refresh_race.py
- ronda3_lock_reset.py
- test_500_keeps_security_headers_and_request_id
- test_response_validation_errors_are_logged_without_values
- test_generic_overflow_error_is_still_a_500
- Role
- endpoints/auth.py
- test_nul_character_is_422_not_500
- utcnow
- test_deprecation_headers_follow_rfcs
- test_rate_limit_header_cleanup
- test_partial_update_messages
- test_password_policy_errors_point_to_the_field
- test_non_json_body_gets_415
- types.py
- test_default_rate_limit_applies_to_included_routers
- api-template
- test_invalid_host_is_json_with_code
- api-template
- test_ipv6_grouped_by_prefix
- test_jobs.py
- _migrate
- list_jobs
- Settings
- test_unrouted_requests_are_rate_limited
- worker.py
- Principal
- authenticate
- security.py
- _stale_race
- env.py
- Ronda 6 — Respuesta del desarrollador
- load_specs
- config.py
- HookContext
- password_problems
- schemas/job.py
- refresh_graph
- _clean
- ErrorBody
- test_init_env_output_loads
- test_backend_recovery_check_does_not_block
- resources/__init__.py
- fake_project
- test_integrity_errors_are_described_without_leaking
- test_text_logs_escape_control_characters

## God Nodes (most connected - your core abstractions)
1. `User` - 51 edges
2. `ResourceSpec` - 49 edges
3. `task()` - 34 edges
4. `utcnow()` - 33 edges
5. `Role` - 29 edges
6. `Job` - 29 edges
7. `SpecError` - 28 edges
8. `APIError` - 25 edges
9. `FieldSpec` - 23 edges
10. `Settings` - 21 edges

## Surprising Connections (you probably didn't know these)
- `bench_note (owned, write-heavy)` --semantically_similar_to--> `order resource (owned)`  [INFERRED] [semantically similar]
  loadtests/resources.loadtest.yaml → examples/shop.yaml
- `bench_product (read-heavy public catalog)` --semantically_similar_to--> `product resource (soft delete, rate limits)`  [INFERRED] [semantically similar]
  loadtests/resources.loadtest.yaml → examples/shop.yaml
- `environment()` --calls--> `Environment`  [INFERRED]
  apigen/codegen.py → app/core/config.py
- `try_spec()` --uses--> `SpecError`  [INFERRED]
  security/checks/generator_checks.py → apigen/spec.py
- `test_cli_errors_are_translated_with_suggestions()` --uses--> `SpecError`  [INFERRED]
  tests/test_generator.py → apigen/spec.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Four-round multi-agent security and usability review** — _claude_agents_security_expert_security_expert_agent, _claude_agents_developer_developer_agent, _claude_agents_user_user_agent, security_revision_seguridad_review_summary [EXTRACTED 1.00]
- **Client IP authenticity as a security control (proxy trust, lockout, rate limit)** — security_reports_ronda1_seguridad_sec_04, security_reports_ronda3_seguridad_sec_21, security_reports_ronda3_seguridad_sec_22, readme_trusted_proxies, docker_compose_backend_network, security_reports_ronda4_desarrollador_proxy_validation, security_reports_ronda2_desarrollador_t1_smart_lockout [INFERRED 0.85]
- **Concurrent refresh race: detection, grace period and client serialization** — security_reports_ronda1_seguridad_sec_01, security_reports_ronda1_usuario_ux_02, security_reports_ronda1_usuario_ux_19, security_reports_ronda2_desarrollador_t2_refresh_grace_period, guia_readme_refreshaccess, readme_refresh_token_rotation [INFERRED 0.85]

## Communities (110 total, 22 thin omitted)

### Community 0 - "services/auth.py"
Cohesion: 0.16
Nodes (29): generate_refresh_token(), hash_token(), looks_like_refresh_token(), Devuelve (token_en_claro, hash). El token solo se entrega al cliente., Refresh token opaco. Solo se guarda su hash SHA-256. Todos los tokens de una…, RefreshToken, _enforce_session_limit(), _handle_revoked() (+21 more)

### Community 1 - "cli.py"
Cohesion: 0.09
Nodes (51): add(), check(), createsuperuser(), db_migrate(), db_prune(), _fail(), generate(), init_env() (+43 more)

### Community 2 - "test_config.py"
Cohesion: 0.15
Nodes (16): _prod(), Configuración y CLI: el .env generado arranca, validaciones y utilidades., SEC-21: confiar en XFF de cualquiera permite falsificar la IP del cliente., SEC-24: un DATABASE_URL ausente no puede acabar en SQLite en silencio., UX-34: 50/hour fuera de producción (cuentas de prueba), 5/hour en producción., UX-03: con skip_empty Alembic devuelve [] en lugar de None., UX-47: generate --migrate avisa si la migración trae tablas de otros recursos., UX-47: sin la línea "Generating /ruta/absoluta ... done" de Alembic. (+8 more)

### Community 3 - "rate_limit.py"
Cohesion: 0.14
Nodes (22): check_unrouted_limit(), client_ip(), enforce_rate_limits(), _evaluate_with_fallback(), ip_key(), _maybe_recover_backend(), Request, Response (+14 more)

### Community 4 - "ResourceSpec"
Cohesion: 0.06
Nodes (64): build_context(), build_test_context(), make_parent(), create_field(), _default_expr(), enum_class(), enum_members(), environment() (+56 more)

### Community 5 - "test_generator.py"
Cohesion: 0.09
Nodes (43): ensure_user_module(), hooks_module(), Path, Crea el módulo si no existe o añade al final las funciones que falten. Devuelve…, tasks_module(), parse_field_option(), Mini-DSL de la CLI: `nombre:tipo[:opción...]`. Ejemplos:…, _action_spec() (+35 more)

### Community 6 - "task"
Cohesion: 0.06
Nodes (39): add_listener, echo(), prune(), Any, Tareas incluidas en la plantilla., Devuelve el payload recibido. Útil para comprobar que el worker funciona., Limpieza periódica: trabajos terminados antiguos., Registro de tareas en segundo plano. Importar este paquete registra todas las… (+31 more)

### Community 7 - "test_auth.py"
Cohesion: 0.13
Nodes (19): _login(), Registro, login, bloqueo de cuenta, rotación y revocación de tokens., Un refresh revocado por logout no es "reutilización": 401 sin tocar las demás…, S-1/UX: la política se valida en el esquema, antes del límite de registro., test_account_lockout(), test_cannot_request_scopes_beyond_role(), test_change_password_revokes_sessions(), test_concurrent_refresh_never_returns_500() (+11 more)

### Community 8 - "middleware.py"
Cohesion: 0.14
Nodes (12): BodySizeLimitMiddleware, RateLimitHeadersMiddleware, Middlewares ASGI puros (más rápidos que BaseHTTPMiddleware)., Rechaza cuerpos mayores que MAX_BODY_SIZE (también con chunked encoding)., Convierte excepciones no controladas en un 500 JSON *dentro* de la pila de…, Asigna un X-Request-ID, lo propaga a los logs y registra cada petición., Pule las cabeceras de SlowAPI: `X-RateLimit-Reset` como entero (epoch) y…, Cabeceras de seguridad en todas las respuestas. (+4 more)

### Community 9 - "errors.py"
Cohesion: 0.16
Nodes (26): _constraint_columns(), data_error_handler(), describe_integrity_error(), http_exception_handler(), integrity_handler(), log_unhandled(), Exception, FastAPI (+18 more)

### Community 10 - "crud/base.py"
Cohesion: 0.10
Nodes (32): DatabaseValueError, Exception, Un valor que el esquema aceptó pero el driver de la BD no puede guardar (p. ej.…, apply_on_delete(), _commit(), ensure_reference(), escape_like(), Any (+24 more)

### Community 11 - "main.py"
Cohesion: 0.20
Nodes (10): APIVersion, Registro de versiones de la API. Cada versión se monta en…, create_app(), list_versions(), _deprecation_dependency(), lifespan(), BaseModel, FastAPI (+2 more)

### Community 12 - "schemas/user.py"
Cohesion: 0.09
Nodes (30): check_json_size(), depth(), _has_nul(), Message, Page, PartialUpdate, Any, BaseModel (+22 more)

### Community 13 - "users.py"
Cohesion: 0.17
Nodes (29): AdminPrincipal, _admin_count(), change_password(), _counts_as_admin(), create_user(), delete_user(), get_user(), _get_user_or_404() (+21 more)

### Community 14 - "deps.py"
Cohesion: 0.11
Nodes (25): current_user(), error_responses(), Any, HTTPException, query_guard(), dependency(), Dependencias compartidas: sesión de BD, usuario actual y control de acceso., Dependencia de control de acceso para un nivel y (opcional) un scope. (+17 more)

### Community 15 - "test_users.py"
Cohesion: 0.10
Nodes (17): create_user(), headers_for(), UX-12: token caducado -> code token_expired (RFC 6750 error_description)., test_expired_token_is_distinguishable(), _only_one_active_admin(), Gestión de usuarios y control de acceso de administración., SEC-30: un admin desactivado no cuenta para el mínimo; se puede degradar y…, El último admin activo sigue protegido; el intento queda en app.audit. (+9 more)

### Community 16 - "Round 3 security verification report"
Cohesion: 0.16
Nodes (19): api service (forced production, read-only, cap_drop ALL), backend network (fixed subnet 172.30.57.0/24), db service (PostgreSQL 17), redis service (Redis 7, rate-limit storage), Accepted and documented security risks, SEC-02 third-party account lockout DoS, SEC-03 compose could start in development, SEC-04 shared client IP behind proxy without TRUSTED_PROXIES (+11 more)

### Community 17 - "3. Hallazgos nuevos"
Cohesion: 0.13
Nodes (14): 1. Resumen ejecutivo, 2. Uso de graphify: consultas y qué revelaron, 3. Hallazgos nuevos, 4. Controles re-verificados en el laboratorio (ronda 5), 5. No verificado en esta ronda, 6. Veredicto actualizado, Detalles menores (Info, sin ID), Revisión de seguridad — Ronda 5 (revisión completa guiada por el grafo de graphify) (+6 more)

### Community 18 - "Round 1 security audit report"
Cohesion: 0.20
Nodes (14): OWASP ASVS Level 2, OWASP API Security Top 10 (2023), security-expert agent (defensive AppSec auditor), security/lab.sh local audit lab (127.0.0.1), user agent (first-time template developer), Field syntax name:type[:options] (13 field types), Permission levels (public / user / owner / admin), shared_read flag (--shared-read) (+6 more)

### Community 19 - "JSONTrustedHostMiddleware"
Cohesion: 0.20
Nodes (7): BodyTooLarge, _HostRejectionSend, JSONTrustedHostMiddleware, HTTPException, `TrustedHostMiddleware` de Starlette con el 400 en JSON y con `code` (contrato…, `send` que convierte el 400 de texto plano de Starlette en JSON., TrustedHostMiddleware

### Community 20 - "Round 1 user experience report"
Cohesion: 0.22
Nodes (14): Resource spec YAML (resources/<name>.yaml source of truth), apigen CLI / CRUD code generator, Stable error `code` contract ({detail, code}), SEC-09 global uniqueness in owned resources (existence oracle), Round 1 user experience report, UX-01 generated .env does not start, UX-03 db migrate with no changes raises traceback, UX-10 generic 409 conflict (+6 more)

### Community 21 - "main"
Cohesion: 0.25
Nodes (11): b64(), bearer(), check(), login(), login_budget(), main(), Response, Verificación de controles de seguridad contra el laboratorio local (ronda 1).… (+3 more)

### Community 22 - "conftest.py"
Cohesion: 0.33
Nodes (12): admin(), admin_headers(), client(), _database(), db(), other_headers(), other_user(), fixture (+4 more)

### Community 23 - "ronda5_checks.py"
Cohesion: 0.38
Nodes (5): bearer(), brief(), login(), Response, Ronda 5: re-verificación de extremo a extremo de los controles críticos y de…

### Community 24 - "project.py"
Cohesion: 0.17
Nodes (30): add_version(), default_version(), dependents(), deprecate_version(), existing_versions(), find_ruff(), format_files(), generate() (+22 more)

### Community 25 - "run_loadtest.sh"
Cohesion: 0.15
Nodes (11): DATABASE_URL, DOCS_ENABLED, ENVIRONMENT, LOADTEST_PASSWORD, LOG_LEVEL, PASSWORD_HASH_CONCURRENCY, PYTHONPATH, SECRET_KEY (+3 more)

### Community 27 - "Ronda 5: informe del usuario (revisión completa e integración con graphify)"
Cohesion: 0.29
Nodes (6): 1. Lo ya resuelto sigue bien, 2. Puntos nuevos, 3. Valoración específica de graphify, 4. Lo que me ha gustado, 5. Valoración global, Ronda 5: informe del usuario (revisión completa e integración con graphify)

### Community 28 - "ready"
Cohesion: 0.21
Nodes (11): HealthStatus, live(), BaseModel, get, Request, Response, SessionDep, El proceso está vivo (para liveness probes). No toca la base de datos. (+3 more)

### Community 29 - "logging.py"
Cohesion: 0.23
Nodes (9): _escape(), JSONFormatter, Logging estructurado con request-id propagado mediante contextvars., Escapa caracteres de control (CR/LF...): impide falsificar líneas de log con…, Formato legible para desarrollo: una línea por evento, con los campos `extra`…, _RequestIdFilter, setup_logging(), TextFormatter (+1 more)

### Community 30 - ".__call__"
Cohesion: 0.20
Nodes (6): internal_error_body(), tracking_send(), send_wrapper(), _send_413(), Receive, Send

### Community 31 - "Security and usability review summary (4 rounds)"
Cohesion: 0.24
Nodes (11): category resource (public catalog), order resource (owned), product resource (soft delete, rate limits), Personal guide for using the API generator, bench_note (owned, write-heavy), bench_product (read-heavy public catalog), API Template (FastAPI + apigen generator), Locust load tests (throughput / ratelimit profiles) (+3 more)

### Community 32 - "resolve_db.py"
Cohesion: 0.50
Nodes (4): main(), Elige la base de datos de la prueba de carga (SEC-29). Solo usa la biblioteca…, (url o None si se niega, mensajes para el usuario)., resolve()

### Community 33 - "lab.sh"
Cohesion: 0.20
Nodes (9): ALLOW_SQLITE_IN_PRODUCTION, ALLOWED_HOSTS, DATABASE_URL, ENVIRONMENT, LOG_JSON, LOG_LEVEL, PYTHONPATH, SECRET_KEY (+1 more)

### Community 34 - "Round 4 developer closing response"
Cohesion: 0.28
Nodes (9): developer agent (senior backend developer), app.audit structured audit log, Production deployment checklist, TRUSTED_PROXIES / X-Forwarded-For client IP, SEC-13 insufficient audit logging / log line injection, apigen db prune (refresh token / IP retention purge), make audit (pip-audit over uv export), TRUSTED_PROXIES production validation (_valid_proxies / _proxy_problems) (+1 more)

### Community 35 - "session.py"
Cohesion: 0.33
Nodes (5): create_engine(), _engine_kwargs(), Any, Motor async y sesiones. Cambiar de base de datos = cambiar DATABASE_URL., AsyncEngine

### Community 36 - "client_from"
Cohesion: 0.22
Nodes (9): AsyncClient, client_from(), Cliente cuyas peticiones llegan desde otra IP (para simular otro origen)., SEC-02: un anónimo que conoce el email ya no deja fuera al titular desde una IP…, SEC-20: el login del titular desde su IP no levanta el bloqueo ni reinicia el…, Condición T1: tras cambiar la contraseña, las IPs de logins anteriores dejan de…, test_lockout_by_third_party_does_not_lock_out_owner(), test_owner_login_during_lockout_keeps_lock_for_others() (+1 more)

### Community 37 - "Round 3 user verification report (8.5/10)"
Cohesion: 0.28
Nodes (9): Rate limiting (SlowAPI, memory or Redis), SEC-11 rate limiting gaps, S-1 register rate limit counts rejected attempts, T4 password-policy 422s do not consume register quota, Round 3 user verification report (8.5/10), UX-29 password policy errors without field loc, UX-34 register limit annoying in development, UX-35 owned-public warning cannot be acknowledged (+1 more)

### Community 38 - "list_users"
Cohesion: 0.25
Nodes (8): list_users(), get, max_length, PaginationDep, Query, read_me(), pattern, ReadMe

### Community 39 - "ronda3_checks.py"
Cohesion: 0.36
Nodes (5): ip(), login(), main(), Ronda 3: verificación de las correcciones del desarrollador. Lanzar el…, trial()

### Community 40 - "T2 10 s refresh reuse grace (409 refresh_token_rotated)"
Cohesion: 0.29
Nodes (7): api() fetch wrapper with token_expired retry (TypeScript), refreshAccess() client refresh serialization (TypeScript), Refresh token rotation with reuse detection, SEC-01 refresh rotation race (500, family not revoked), UX-02 concurrent refresh returns 500, UX-19 legitimate concurrent refresh logs user out, T2 10 s refresh reuse grace (409 refresh_token_rotated)

### Community 41 - "helpers.py"
Cohesion: 0.33
Nodes (5): _like(), Utilidades para tests (también las usan los tests generados por apigen)., Valor aleatorio con la misma forma que `example` (a->letra, 9->dígito)., _text(), _uid()

### Community 42 - "_claims"
Cohesion: 0.38
Nodes (7): _claims(), _forge(), Aunque el token (válido) diga role=admin, manda el rol en la base de datos., test_alg_none_rejected(), test_expired_and_wrong_audience_rejected(), test_forged_token_with_wrong_key(), test_role_claim_is_not_trusted()

### Community 43 - "Pagination"
Cohesion: 0.40
Nodes (6): Pagination, Query, ge, le, MAX_OFFSET, PAGE_SIZE_MAX

### Community 44 - "lab_checks_2.py"
Cohesion: 0.47
Nodes (5): login(), Response, race(), Verificaciones dirigidas (ronda 1, segunda pasada) sobre un laboratorio NUEVO.…, show()

### Community 45 - "SEC-05 email enumeration at registration"
Cohesion: 0.40
Nodes (5): API versioning (routers versioned, models/schemas shared), SEC-05 email enumeration at registration, UX-09 versions share models and schemas, T3 keep 409 email_taken (accepted risk), Deferred improvements (email verification, HIBP, per-version schemas)

### Community 47 - "test_swagger_token_url_uses_active_version"
Cohesion: 0.50
Nodes (4): _login_version(), Versión para el botón Authorize de Swagger: la más reciente no deprecada., UX-31: tokenUrl apunta a la versión activa más reciente; login documenta…, test_swagger_token_url_uses_active_version()

### Community 48 - "Environment"
Cohesion: 0.50
Nodes (4): Environment, StrEnum, UX-17: en desarrollo, sin CORS_ORIGINS, se admite cualquier localhost., test_dev_cors_allows_localhost_frontends()

### Community 49 - "refresh_race.py"
Cohesion: 0.67
Nodes (3): main(), Carrera en /auth/refresh con DOS peticiones simultáneas (el caso realista: el…, trial()

### Community 56 - "Role"
Cohesion: 0.38
Nodes (6): Role, hash_password(), cleanup(), main(), Siembra datos para la prueba de carga (se ejecuta dentro de la copia temporal)., Borra las cuentas de la prueba (con LOADTEST_DATABASE_URL la BD no es temporal).

### Community 57 - "endpoints/auth.py"
Cohesion: 0.16
Nodes (23): login(), logout(), logout_all(), Depends, limit, post, Request, Response (+15 more)

### Community 59 - "utcnow"
Cohesion: 0.16
Nodes (26): utcnow(), Hooks de lógica personalizada para los recursos generados. Cada recurso tiene…, Job, backoff_seconds(), cancel(), claim(), complete(), enqueue() (+18 more)

### Community 65 - "types.py"
Cohesion: 0.13
Nodes (14): datetime, UUID, Tipos de columna y generadores de IDs., UUID v7 (RFC 9562): ordenado en el tiempo, así los índices B-tree se mantienen…, DateTime siempre en UTC y con tzinfo, también en SQLite (que no guarda zona)., UTCDateTime, uuid7(), IDMixin (+6 more)

### Community 82 - "api-template"
Cohesion: 0.50
Nodes (3): api-template, Cómo trabajar aquí, graphify

### Community 84 - "test_jobs.py"
Cohesion: 0.24
Nodes (20): JobStatus, StrEnum, process_pending(), Procesa los trabajos listos y vuelve (útil en tests y en `apigen worker…, _enqueue(), _job(), Cola de trabajos en segundo plano: ejecución, permisos, reintentos y límites., test_a_job_is_claimed_only_once() (+12 more)

### Community 85 - "_migrate"
Cohesion: 0.14
Nodes (18): _alembic_config(), db_current(), db_downgrade(), db_history(), db_upgrade(), _migrate(), migration_tables(), Path (+10 more)

### Community 86 - "list_jobs"
Cohesion: 0.17
Nodes (16): alias, cancel_job(), get_job(), _get_or_404(), list_jobs(), get, max_length, PaginationDep (+8 more)

### Community 87 - "Settings"
Cohesion: 0.16
Nodes (5): Any, field_validator, Settings, BaseSettings, test_weak_previous_jwt_keys_rejected_in_production()

### Community 89 - "worker.py"
Cohesion: 0.19
Nodes (10): main(), _main(), _pool(), UUID, Worker de tareas en segundo plano: `apigen worker` (o `python -m…, Ejecuta un trabajo ya reclamado y registra el resultado. Nunca lanza., run_job(), Worker (+2 more)

### Community 90 - "Principal"
Cohesion: 0.18
Nodes (9): get_principal(), Principal, Depends, Request, SessionDep, UUID, Quién hace la petición (o nadie, en endpoints públicos)., ID por el que filtrar filas en recursos con propietario (None = todas). (+1 more)

### Community 91 - "authenticate"
Cohesion: 0.20
Nodes (10): _limiter(), Devuelve (válida, nuevo_hash). `nuevo_hash` != None si hay que re-hashear…, verify_password(), authenticate(), lockout_minutes(), Duración del bloqueo: se dobla con cada bloqueo consecutivo, con tope., Verifica credenciales aplicando "smart lockout". Tras LOGIN_MAX_ATTEMPTS fallos…, _register_failure() (+2 more)

### Community 92 - "security.py"
Cohesion: 0.33
Nodes (7): AccessToken, _build_keyring(), create_access_token(), _KeyRing, _kid(), UUID, Primitivas criptográficas: contraseñas (Argon2id), JWT de acceso y refresh…

### Community 93 - "_stale_race"
Cohesion: 0.22
Nodes (9): HTTPException, Reproduce de forma determinista la carrera de SEC-01: el "perdedor" leyó la…, SEC-01: el perdedor de la carrera recibe 401 (no 500) y la familia se revoca., UX-19: dos pestañas del mismo cliente -> 409 sin revocar; el token del ganador…, Condición T2: tras un 409 refresh_token_rotated, si el cliente no tiene un…, _stale_race(), test_logout_after_409_revokes_the_whole_family(), test_refresh_race_loser_revokes_family_without_grace() (+1 more)

### Community 94 - "env.py"
Cohesion: 0.39
Nodes (7): _configure(), do_run_migrations(), Entorno de Alembic (async). La URL sale de DATABASE_URL, nunca de alembic.ini., run_async_migrations(), run_migrations_offline(), _skip_empty(), Connection

### Community 95 - "Ronda 6 — Respuesta del desarrollador"
Cohesion: 0.25
Nodes (7): 1. Tabla de decisiones, 2. UX-40: decisión sobre soft delete con hijos, 3. SEC-25 / UX-39: recomendación técnica (sin tocar `.claude/`), 4. Observaciones nuevas y pendientes, 5. Ficheros modificados, Estado final, Ronda 6 — Respuesta del desarrollador

### Community 96 - "load_specs"
Cohesion: 0.29
Nodes (7): format_errors(), load_specs(), Path, Carga un fichero YAML (un recurso o `resources: [...]`) o un directorio., UX-06: sin traceback; fichero:línea:columna., test_yaml_syntax_error_is_reported_with_position(), ValidationError

### Community 97 - "config.py"
Cohesion: 0.29
Nodes (5): get_settings(), _proxy_problems(), model_validator, Configuración central de la aplicación. Todo se lee de variables de entorno (o…, SEC-21: la IP del cliente decide rate limits, bloqueo de login y gracia del…

### Community 98 - "HookContext"
Cohesion: 0.33
Nodes (5): HookContext, Any, UUID, Lo que recibe cada hook: sesión de BD y quién hace la petición., Encola una tarea pesada para el worker (no bloquea la petición).

### Community 99 - "password_problems"
Cohesion: 0.33
Nodes (6): _is_sequence(), password_problems(), Política de contraseñas basada en NIST 800-63B: longitud y listas negras, sin…, UX-32: la CLI no mezcla idiomas., test_cli_password_policy_in_spanish(), test_keyboard_sequences_are_rejected()

### Community 100 - "schemas/job.py"
Cohesion: 0.50
Nodes (4): JobAccepted, JobRead, BaseModel, Respuesta 202 de un endpoint con proceso en segundo plano.

### Community 101 - "refresh_graph"
Cohesion: 0.50
Nodes (4): Actualiza el grafo de graphify tras cambiar código (solo AST: rápido y sin…, refresh_graph(), apigen solo toca graphify si el proyecto ya tiene grafo y no está desactivado., test_refresh_graph_is_optional()

### Community 102 - "_clean"
Cohesion: 0.67
Nodes (3): _clean(), Exception, test_check_error_is_clean()

### Community 103 - "ErrorBody"
Cohesion: 0.67
Nodes (3): ErrorBody, BaseModel, Forma de las respuestas de error (para OpenAPI y clientes generados).

### Community 104 - "test_init_env_output_loads"
Cohesion: 0.67
Nodes (3): parametrize, UX-01: el .env de `init-env` (con variables vacías) es válido tal cual., test_init_env_output_loads()

## Knowledge Gaps
- **53 isolated node(s):** `run_loadtest.sh script`, `PYTHONPATH`, `ENVIRONMENT`, `DOCS_ENABLED`, `LOG_LEVEL` (+48 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 470 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **22 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `User` connect `users.py` to `services/auth.py`, `cli.py`, `types.py`, `test_security.py`, `client_from`, `list_users`, `test_auth.py`, `test_integrity_errors_are_described_without_leaking`, `deps.py`, `test_users.py`, `conftest.py`, `Role`, `endpoints/auth.py`, `Principal`, `authenticate`?**
  _High betweenness centrality (0.098) - this node is a cross-community bridge._
- **Why does `task()` connect `task` to `ResourceSpec`?**
  _High betweenness centrality (0.067) - this node is a cross-community bridge._
- **Why does `ResourceSpec` connect `ResourceSpec` to `project.py`, `cli.py`, `load_specs`, `test_generator.py`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Are the 32 inferred relationships involving `User` (e.g. with `current_user()` and `get_principal()`) actually correct?**
  _`User` has 32 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `ResourceSpec` (e.g. with `_warn_specs()` and `build_context()`) actually correct?**
  _`ResourceSpec` has 31 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `task()` (e.g. with `decorator()` and `ValueError`) actually correct?**
  _`task()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `Role` (e.g. with `Principal` and `_admin_count()`) actually correct?**
  _`Role` has 15 INFERRED edges - model-reasoned connections that need verification._