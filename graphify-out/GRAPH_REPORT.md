# Graph Report - api-template  (2026-09-26)

## Corpus Check
- 110 files · ~106,641 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1488 nodes · 3297 edges · 111 communities (71 shown, 25 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 336 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `08810358`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- services/auth.py
- cli.py
- test_config.py
- security.py
- codegen.py
- test_generator.py
- task
- test_auth.py
- main.py
- errors.py
- crud/base.py
- ResourceSpec
- endpoints/auth.py
- users.py
- APIError
- User
- Round 3 security verification report
- 3. Hallazgos nuevos
- Round 1 security audit report
- JSONTrustedHostMiddleware
- Round 1 user experience report
- main
- types.py
- ronda5_checks.py
- project.py
- run_loadtest.sh
- test_security.py
- Ronda 5: informe del usuario (revisión completa e integración con graphify)
- middleware.py
- logging.py
- Send
- Security and usability review summary (4 rounds)
- resolve_db.py
- lab.sh
- Round 4 developer closing response
- session.py
- render_resource
- Round 3 user verification report (8.5/10)
- 3. Hallazgos nuevos
- ronda3_checks.py
- T2 10 s refresh reuse grace (409 refresh_token_rotated)
- helpers.py
- new_api.py
- Pagination
- lab_checks_2.py
- SEC-05 email enumeration at registration
- test_loadtest_db.py
- test_swagger_token_url_uses_active_version
- Environment
- refresh_race.py
- ronda3_lock_reset.py
- Settings
- Worker
- test_new_api.py
- config.py
- login
- Ronda 7 – Informe de usuario (desarrollador que crea y entrega APIs a clientes)
- utcnow
- test_expired_token_is_distinguishable
- authenticate
- _claims
- ronda7_checks.py
- NullByteGuardMiddleware
- ronda7_docker_checks.py
- test_init_env_output_loads
- api-template
- refresh_graph
- api-template
- _clean
- test_jobs.py
- test_500_keeps_security_headers_and_request_id
- Job
- test_response_validation_errors_are_logged_without_values
- test_generic_overflow_error_is_still_a_500
- worker.py
- deps.py
- test_backend_recovery_check_does_not_block
- test_prune_removes_only_dead_old_sessions
- _stale_race
- fake_project
- Ronda 6 — Respuesta del desarrollador
- spec.py
- test_migration_tables_lists_what_upgrade_touches
- models/job.py
- test_nul_character_is_422_not_500
- test_integrity_errors_are_described_without_leaking
- test_unrouted_requests_are_rate_limited
- test_deprecation_headers_follow_rfcs
- test_rate_limit_header_cleanup
- test_partial_update_messages
- test_password_policy_errors_point_to_the_field
- resources/__init__.py
- test_non_json_body_gets_415
- test_invalid_host_is_json_with_code
- test_nul_in_query_or_path_is_422_not_500
- test_body_size_limit_chunked

## God Nodes (most connected - your core abstractions)
1. `ResourceSpec` - 63 edges
2. `User` - 53 edges
3. `task()` - 45 edges
4. `Job` - 36 edges
5. `SpecError` - 35 edges
6. `utcnow()` - 34 edges
7. `Role` - 29 edges
8. `_spec()` - 28 edges
9. `FieldSpec` - 27 edges
10. `APIError` - 27 edges

## Surprising Connections (you probably didn't know these)
- `bench_note (owned, write-heavy)` --semantically_similar_to--> `order resource (owned)`  [INFERRED] [semantically similar]
  loadtests/resources.loadtest.yaml → examples/shop.yaml
- `bench_product (read-heavy public catalog)` --semantically_similar_to--> `product resource (soft delete, rate limits)`  [INFERRED] [semantically similar]
  loadtests/resources.loadtest.yaml → examples/shop.yaml
- `try_spec()` --uses--> `SpecError`  [INFERRED]
  security/checks/generator_checks.py → apigen/spec.py
- `test_action_permission_aliases_cannot_override_crud()` --uses--> `SpecError`  [INFERRED]
  tests/test_generator.py → apigen/spec.py
- `test_cli_errors_are_translated_with_suggestions()` --uses--> `SpecError`  [INFERRED]
  tests/test_generator.py → apigen/spec.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Four-round multi-agent security and usability review** — _claude_agents_security_expert_security_expert_agent, _claude_agents_developer_developer_agent, _claude_agents_user_user_agent, security_revision_seguridad_review_summary [EXTRACTED 1.00]
- **Client IP authenticity as a security control (proxy trust, lockout, rate limit)** — security_reports_ronda1_seguridad_sec_04, security_reports_ronda3_seguridad_sec_21, security_reports_ronda3_seguridad_sec_22, readme_trusted_proxies, docker_compose_backend_network, security_reports_ronda4_desarrollador_proxy_validation, security_reports_ronda2_desarrollador_t1_smart_lockout [INFERRED 0.85]
- **Concurrent refresh race: detection, grace period and client serialization** — security_reports_ronda1_seguridad_sec_01, security_reports_ronda1_usuario_ux_02, security_reports_ronda1_usuario_ux_19, security_reports_ronda2_desarrollador_t2_refresh_grace_period, guia_readme_refreshaccess, readme_refresh_token_rotation [INFERRED 0.85]

## Communities (111 total, 25 thin omitted)

### Community 0 - "services/auth.py"
Cohesion: 0.17
Nodes (28): generate_refresh_token(), hash_token(), looks_like_refresh_token(), Devuelve (token_en_claro, hash). El token solo se entrega al cliente., Refresh token opaco. Solo se guarda su hash SHA-256. Todos los tokens de una…, RefreshToken, BaseModel, TokenPair (+20 more)

### Community 1 - "cli.py"
Cohesion: 0.07
Nodes (69): add(), _alembic_config(), check(), createsuperuser(), db_current(), db_downgrade(), db_history(), db_migrate() (+61 more)

### Community 2 - "test_config.py"
Cohesion: 0.11
Nodes (22): _is_sequence(), password_problems(), Política de contraseñas basada en NIST 800-63B: longitud y listas negras, sin…, _prod(), Configuración y CLI: el .env generado arranca, validaciones y utilidades., SEC-24: un DATABASE_URL ausente no puede acabar en SQLite en silencio., UX-34: 50/hour fuera de producción (cuentas de prueba), 5/hour en producción., UX-32: la CLI no mezcla idiomas. (+14 more)

### Community 3 - "security.py"
Cohesion: 0.06
Nodes (43): HealthStatus, live(), BaseModel, get, Request, Response, SessionDep, El proceso está vivo (para liveness probes). No toca la base de datos. (+35 more)

### Community 4 - "codegen.py"
Cohesion: 0.10
Nodes (38): build_context(), build_test_context(), make_parent(), _check_router_symbols(), create_field(), _default_expr(), enum_class(), enum_members() (+30 more)

### Community 5 - "test_generator.py"
Cohesion: 0.06
Nodes (58): hooks_module(), tasks_module(), pluralize(), parse_field_option(), Mini-DSL de la CLI: `nombre:tipo[:opción...]`. Ejemplos:…, _action_spec(), _files(), parametrize (+50 more)

### Community 6 - "task"
Cohesion: 0.05
Nodes (48): add_listener, echo(), prune(), Any, Tareas incluidas en la plantilla., Devuelve el payload recibido. Útil para comprobar que el worker funciona., Limpieza periódica: trabajos terminados antiguos., Registro de tareas en segundo plano. Importar este paquete registra todas las… (+40 more)

### Community 7 - "test_auth.py"
Cohesion: 0.10
Nodes (28): AsyncClient, client_from(), Cliente cuyas peticiones llegan desde otra IP (para simular otro origen)., _login(), Registro, login, bloqueo de cuenta, rotación y revocación de tokens., SEC-02: un anónimo que conoce el email ya no deja fuera al titular desde una IP…, Un refresh revocado por logout no es "reutilización": 401 sin tocar las demás…, SEC-20: el login del titular desde su IP no levanta el bloqueo ni reinicia el… (+20 more)

### Community 8 - "main.py"
Cohesion: 0.16
Nodes (12): APIVersion, Registro de versiones de la API. Cada versión se monta en…, Convierte excepciones no controladas en un 500 JSON *dentro* de la pila de…, UnhandledErrorMiddleware, create_app(), list_versions(), _deprecation_dependency(), lifespan() (+4 more)

### Community 9 - "errors.py"
Cohesion: 0.17
Nodes (24): _constraint_columns(), data_error_handler(), describe_integrity_error(), http_exception_handler(), integrity_handler(), Exception, FastAPI, Request (+16 more)

### Community 10 - "crud/base.py"
Cohesion: 0.10
Nodes (32): DatabaseValueError, Exception, Un valor que el esquema aceptó pero el driver de la BD no puede guardar (p. ej.…, apply_on_delete(), _commit(), ensure_reference(), escape_like(), Any (+24 more)

### Community 11 - "ResourceSpec"
Cohesion: 0.10
Nodes (32): _call_name(), custom_errors(), _example_value(), _examples(), _field_rules(), _field_type(), _literal_text(), Path (+24 more)

### Community 12 - "endpoints/auth.py"
Cohesion: 0.09
Nodes (30): RefreshRequest, check_json_size(), depth(), _has_nul(), Message, Page, PartialUpdate, Any (+22 more)

### Community 13 - "users.py"
Cohesion: 0.11
Nodes (37): AdminPrincipal, _admin_count(), change_password(), _counts_as_admin(), create_user(), delete_user(), get_user(), _get_user_or_404() (+29 more)

### Community 14 - "APIError"
Cohesion: 0.10
Nodes (26): HTTPException, query_guard(), dependency(), Dependencia de control de acceso para un nivel y (opcional) un scope., Dependencia para listados: rechaza (422) parámetros de query que parecen un…, require(), dependency(), _unauthorized() (+18 more)

### Community 15 - "User"
Cohesion: 0.11
Nodes (28): User, admin(), admin_headers(), client(), create_user(), _database(), db(), headers_for() (+20 more)

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

### Community 22 - "types.py"
Cohesion: 0.14
Nodes (13): datetime, UUID, Tipos de columna y generadores de IDs., UUID v7 (RFC 9562): ordenado en el tiempo, así los índices B-tree se mantienen…, DateTime siempre en UTC y con tzinfo, también en SQLite (que no guarda zona)., UTCDateTime, uuid7(), IDMixin (+5 more)

### Community 23 - "ronda5_checks.py"
Cohesion: 0.38
Nodes (5): bearer(), brief(), login(), Response, Ronda 5: re-verificación de extremo a extremo de los controles críticos y de…

### Community 24 - "project.py"
Cohesion: 0.10
Nodes (51): Lista las versiones existentes y su estado., version_list(), Rendered, add_version(), check_spec_sources(), default_version(), dependents(), deprecate_version() (+43 more)

### Community 25 - "run_loadtest.sh"
Cohesion: 0.15
Nodes (11): DATABASE_URL, DOCS_ENABLED, ENVIRONMENT, LOADTEST_PASSWORD, LOG_LEVEL, PASSWORD_HASH_CONCURRENCY, PYTHONPATH, SECRET_KEY (+3 more)

### Community 26 - "test_security.py"
Cohesion: 0.15
Nodes (3): Defensas transversales: tokens, cabeceras, tamaño de body, errores y rate limit., Regresión: SlowAPIMiddleware no ve los routers incluidos en FastAPI >= 0.140., test_default_rate_limit_applies_to_included_routers()

### Community 27 - "Ronda 5: informe del usuario (revisión completa e integración con graphify)"
Cohesion: 0.29
Nodes (6): 1. Lo ya resuelto sigue bien, 2. Puntos nuevos, 3. Valoración específica de graphify, 4. Lo que me ha gustado, 5. Valoración global, Ronda 5: informe del usuario (revisión completa e integración con graphify)

### Community 28 - "middleware.py"
Cohesion: 0.12
Nodes (13): internal_error_body(), log_unhandled(), BodySizeLimitMiddleware, RateLimitHeadersMiddleware, Middlewares ASGI puros (más rápidos que BaseHTTPMiddleware)., Rechaza cuerpos mayores que MAX_BODY_SIZE (también con chunked encoding)., Asigna un X-Request-ID, lo propaga a los logs y registra cada petición., Pule las cabeceras de SlowAPI: `X-RateLimit-Reset` como entero (epoch) y… (+5 more)

### Community 29 - "logging.py"
Cohesion: 0.13
Nodes (18): _configure(), do_run_migrations(), Entorno de Alembic (async). La URL sale de DATABASE_URL, nunca de alembic.ini., run_async_migrations(), run_migrations_offline(), _skip_empty(), _escape(), JSONFormatter (+10 more)

### Community 30 - "Send"
Cohesion: 0.22
Nodes (5): tracking_send(), send_wrapper(), _send_413(), Receive, Send

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
Cohesion: 0.13
Nodes (14): Crea una cuenta. La política de contraseñas se valida en el esquema (422),…, register(), hash_password(), create_engine(), _engine_kwargs(), get_session(), Any, AsyncSession (+6 more)

### Community 36 - "render_resource"
Cohesion: 0.14
Nodes (15): ensure_user_module(), Path, Crea el módulo si no existe o añade al final las funciones que falten. Devuelve…, render_resource(), compiles(), Comprobaciones de seguridad del generador `apigen` (ronda 1). No escribe en el…, spec(), try_spec() (+7 more)

### Community 37 - "Round 3 user verification report (8.5/10)"
Cohesion: 0.28
Nodes (9): Rate limiting (SlowAPI, memory or Redis), SEC-11 rate limiting gaps, S-1 register rate limit counts rejected attempts, T4 password-policy 422s do not consume register quota, Round 3 user verification report (8.5/10), UX-29 password policy errors without field loc, UX-34 register limit annoying in development, UX-35 owned-public warning cannot be acknowledged (+1 more)

### Community 38 - "3. Hallazgos nuevos"
Cohesion: 0.11
Nodes (17): 1. Resumen ejecutivo, 2. Uso de graphify: consultas y qué revelaron, 3.10 Detalles menores (Info, sin ID), 3. Hallazgos nuevos, 4. Controles verificados, 5. No verificado en esta ronda, 6. Veredicto actualizado, Revisión de seguridad — Ronda 7 (cola de trabajos, acciones generadas y herramientas para clientes) (+9 more)

### Community 39 - "ronda3_checks.py"
Cohesion: 0.36
Nodes (5): ip(), login(), main(), Ronda 3: verificación de las correcciones del desarrollador. Lanzar el…, trial()

### Community 40 - "T2 10 s refresh reuse grace (409 refresh_token_rotated)"
Cohesion: 0.29
Nodes (7): api() fetch wrapper with token_expired retry (TypeScript), refreshAccess() client refresh serialization (TypeScript), Refresh token rotation with reuse detection, SEC-01 refresh rotation race (500, family not revoked), UX-02 concurrent refresh returns 500, UX-19 legitimate concurrent refresh logs user out, T2 10 s refresh reuse grace (409 refresh_token_rotated)

### Community 41 - "helpers.py"
Cohesion: 0.20
Nodes (9): _future_date(), _future_datetime(), _like(), Utilidades para tests (también las usan los tests generados por apigen)., Valor aleatorio con la misma forma que `example` (a->letra, 9->dígito)., Fecha ISO dentro de un año (+offset días): válida para reglas tipo "no en el…, Fecha y hora ISO con zona, dentro de un año (+offset días), a las 10:00 UTC., _text() (+1 more)

### Community 42 - "new_api.py"
Cohesion: 0.15
Nodes (28): all_files(), check_clean(), claude_md(), default_title(), developer_docs(), dirty_files(), fail(), fix_references() (+20 more)

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
Cohesion: 0.29
Nodes (7): environment(), Environment, StrEnum, UX-17: en desarrollo, sin CORS_ORIGINS, se admite cualquier localhost., Ronda 7: el 422 del NUL iba por fuera de CORS (el navegador veía un error de…, test_dev_cors_allows_localhost_frontends(), test_nul_422_has_cors_headers_and_right_loc()

### Community 49 - "refresh_race.py"
Cohesion: 0.67
Nodes (3): main(), Carrera en /auth/refresh con DOS peticiones simultáneas (el caso realista: el…, trial()

### Community 53 - "Settings"
Cohesion: 0.16
Nodes (5): Any, field_validator, Settings, BaseSettings, test_weak_previous_jwt_keys_rejected_in_production()

### Community 54 - "Worker"
Cohesion: 0.17
Nodes (8): heartbeat_path(), Escribe el latido sin seguir enlaces simbólicos (SEC-36): fichero temporal…, Fichero de latido que comprueba el healthcheck (JOBS_HEARTBEAT_FILE)., Worker, SEC-36: el latido sustituye el fichero; nunca escribe a través de un enlace., SEC-39: con la BD caída no hay latido (el healthcheck pasa a unhealthy) y la…, test_heartbeat_does_not_follow_symlinks(), test_worker_heartbeat_only_while_database_answers()

### Community 55 - "test_new_api.py"
Cohesion: 0.25
Nodes (13): _git(), _load(), _new(), fixture, Path, scripts/new_api.py: solo copia lo versionado y no deja pasar secretos ni datos…, La plantilla versionada no debe disparar el escáner (falsos positivos)., Plantilla mínima en un repo git temporal (todo versionado y limpio). (+5 more)

### Community 56 - "config.py"
Cohesion: 0.22
Nodes (6): get_settings(), _proxy_problems(), model_validator, Configuración central de la aplicación. Todo se lee de variables de entorno (o…, Comprobaciones de producción que solo afectan a la API HTTP (no al worker)., SEC-21: la IP del cliente decide rate limits, bloqueo de login y gracia del…

### Community 57 - "login"
Cohesion: 0.16
Nodes (19): login(), logout(), logout_all(), Depends, limit, post, Request, Response (+11 more)

### Community 58 - "Ronda 7 – Informe de usuario (desarrollador que crea y entrega APIs a clientes)"
Cohesion: 0.22
Nodes (8): 0. Qué he hecho, 1. Puntos encontrados, 2. README para clientes (lo que recibe el cliente final), 3. Hooks y acciones: valoración, 4. Lo que me ha gustado, 5. Valoración, Mejoras concretas, Ronda 7 – Informe de usuario (desarrollador que crea y entrega APIs a clientes)

### Community 59 - "utcnow"
Cohesion: 0.17
Nodes (23): utcnow(), backoff_seconds(), claim(), complete(), fail(), _json_size(), _leased(), prune_jobs() (+15 more)

### Community 61 - "authenticate"
Cohesion: 0.25
Nodes (8): Devuelve (válida, nuevo_hash). `nuevo_hash` != None si hay que re-hashear…, verify_password(), authenticate(), lockout_minutes(), Duración del bloqueo: se dobla con cada bloqueo consecutivo, con tope., Verifica credenciales aplicando "smart lockout". Tras LOGIN_MAX_ATTEMPTS fallos…, _register_failure(), test_lockout_duration_escalates()

### Community 62 - "_claims"
Cohesion: 0.38
Nodes (7): _claims(), _forge(), Aunque el token (válido) diga role=admin, manda el rol en la base de datos., test_alg_none_rejected(), test_expired_and_wrong_audience_rejected(), test_forged_token_with_wrong_key(), test_role_claim_is_not_trusted()

### Community 63 - "ronda7_checks.py"
Cohesion: 0.33
Nodes (3): brief(), Response, Ronda 7: cola de trabajos, acciones generadas y NullByteGuard por HTTP.…

### Community 66 - "test_init_env_output_loads"
Cohesion: 0.40
Nodes (5): parametrize, SEC-21: confiar en XFF de cualquiera permite falsificar la IP del cliente., UX-01: el .env de `init-env` (con variables vacías) es válido tal cual., test_init_env_output_loads(), test_wildcard_trusted_proxies_rejected_in_production()

### Community 81 - "refresh_graph"
Cohesion: 0.50
Nodes (4): Actualiza el grafo de graphify tras cambiar código (solo AST: rápido y sin…, refresh_graph(), apigen solo toca graphify si el proyecto ya tiene grafo y no está desactivado., test_refresh_graph_is_optional()

### Community 82 - "api-template"
Cohesion: 0.50
Nodes (3): api-template, Cómo trabajar aquí, graphify

### Community 83 - "_clean"
Cohesion: 0.67
Nodes (3): _clean(), Exception, test_check_error_is_clean()

### Community 84 - "test_jobs.py"
Cohesion: 0.18
Nodes (28): JobStatus, StrEnum, process_pending(), Procesa los trabajos listos y vuelve (útil en tests y en `apigen worker…, _enqueue(), _job(), Cola de trabajos en segundo plano: ejecución, permisos, reintentos y límites., SEC-33: al vencer el timeout se mata el proceso de la tarea (no sigue corriendo… (+20 more)

### Community 86 - "Job"
Cohesion: 0.14
Nodes (22): alias, cancel_job(), get_job(), _get_or_404(), list_jobs(), get, max_length, PaginationDep (+14 more)

### Community 89 - "worker.py"
Cohesion: 0.13
Nodes (22): get_task(), TaskDef, _child_main(), _ChildError, _execute(), main(), _main(), _mp_context() (+14 more)

### Community 90 - "deps.py"
Cohesion: 0.11
Nodes (22): current_user(), error_responses(), ErrorBody, get_principal(), Principal, Any, BaseModel, Depends (+14 more)

### Community 93 - "_stale_race"
Cohesion: 0.22
Nodes (9): HTTPException, Reproduce de forma determinista la carrera de SEC-01: el "perdedor" leyó la…, SEC-01: el perdedor de la carrera recibe 401 (no 500) y la familia se revoca., UX-19: dos pestañas del mismo cliente -> 409 sin revocar; el token del ganador…, Condición T2: tras un 409 refresh_token_rotated, si el cliente no tiene un…, _stale_race(), test_logout_after_409_revokes_the_whole_family(), test_refresh_race_loser_revokes_family_without_grace() (+1 more)

### Community 95 - "Ronda 6 — Respuesta del desarrollador"
Cohesion: 0.25
Nodes (7): 1. Tabla de decisiones, 2. UX-40: decisión sobre soft delete con hijos, 3. SEC-25 / UX-39: recomendación técnica (sin tocar `.claude/`), 4. Observaciones nuevas y pendientes, 5. Ficheros modificados, Estado final, Ronda 6 — Respuesta del desarrollador

### Community 96 - "spec.py"
Cohesion: 0.11
Nodes (19): ActionSpec, coerce_value(), Permissions, Any, BaseModel, field_validator, model_validator, RateLimits (+11 more)

### Community 98 - "models/job.py"
Cohesion: 0.22
Nodes (7): HookContext, Any, UUID, Hooks de lógica personalizada para los recursos generados. Cada recurso tiene…, Lo que recibe cada hook: sesión de BD y quién hace la petición., Encola una tarea pesada para el worker (no bloquea la petición)., Cola de trabajos en segundo plano guardada en la propia base de datos. Así no…

## Knowledge Gaps
- **74 isolated node(s):** `run_loadtest.sh script`, `PYTHONPATH`, `ENVIRONMENT`, `DOCS_ENABLED`, `LOG_LEVEL` (+69 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 571 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **25 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `User` connect `User` to `services/auth.py`, `cli.py`, `session.py`, `test_security.py`, `test_integrity_errors_are_described_without_leaking`, `test_auth.py`, `endpoints/auth.py`, `users.py`, `APIError`, `types.py`, `deps.py`, `authenticate`?**
  _High betweenness centrality (0.090) - this node is a cross-community bridge._
- **Why does `ResourceSpec` connect `ResourceSpec` to `spec.py`, `cli.py`, `codegen.py`, `test_generator.py`, `render_resource`, `project.py`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **Why does `prune_jobs()` connect `utcnow` to `cli.py`, `task`, `crud/base.py`, `test_jobs.py`, `Job`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Are the 41 inferred relationships involving `ResourceSpec` (e.g. with `_warn_specs()` and `build_context()`) actually correct?**
  _`ResourceSpec` has 41 INFERRED edges - model-reasoned connections that need verification._
- **Are the 33 inferred relationships involving `User` (e.g. with `current_user()` and `get_principal()`) actually correct?**
  _`User` has 33 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `task()` (e.g. with `decorator()` and `ValueError`) actually correct?**
  _`task()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 24 inferred relationships involving `Job` (e.g. with `cancel_job()` and `get_job()`) actually correct?**
  _`Job` has 24 INFERRED edges - model-reasoned connections that need verification._