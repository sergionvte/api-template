# Graph Report - api-template  (2026-11-03)

## Corpus Check
- 151 files · ~183,489 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2328 nodes · 5455 edges · 140 communities (112 shown, 13 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 513 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `a766da31`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- ronda7_generator_checks.py
- cli.py
- _prod
- rate_limit.py
- codegen.py
- test_generator.py
- task
- test_auth.py
- Send
- errors.py
- crud/base.py
- docs.py
- schemas/user.py
- User
- list_jobs
- headers_for
- Round 3 security verification report
- 3. Hallazgos nuevos
- Round 1 security audit report
- create_user
- Round 1 user experience report
- main
- Worker
- ronda5_checks.py
- ResourceSpec
- run_loadtest.sh
- test_security.py
- Ronda 5: informe del usuario (revisión completa e integración con graphify)
- test_account.py
- .enqueue
- main.py
- Security and usability review summary (4 rounds)
- resolve_db.py
- lab.sh
- Round 4 developer closing response
- session.py
- fase2_docker_e2e.py
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
- 3. Puntos nuevos
- refresh_race.py
- ronda3_lock_reset.py
- Settings
- check
- test_new_api.py
- 3. Hallazgos nuevos
- endpoints/auth.py
- Ronda 7 – Informe de usuario (desarrollador que crea y entrega APIs a clientes)
- queue.py
- ronda7_worker_checks.py
- conftest.py
- Fase 2 — Plan técnico del desarrollador: correo, verificación de email y recuperación de contraseña
- ronda7_checks.py
- ready
- ronda7_docker_checks.py
- 2. Historias de usuario: CLIENTE / FRONTEND
- api-template
- test_email.py
- api-template
- render.py
- test_jobs.py
- endpoints/account.py
- backends/__init__.py
- _send_token_email
- services/auth.py
- worker.py
- deps.py
- mail.py
- EmailMessage
- env.py
- utcnow
- Ronda 6 — Respuesta del desarrollador
- ValueError
- call
- Ronda 8 — Respuesta del desarrollador a la ronda 7
- logging.py
- 4. Requisitos
- Fase 2: correcciones de la validación (SEC-40..45, UX-67..80)
- config.py
- FakeSMTP
- security.py
- audit
- resources/__init__.py
- _TextExtractor
- test_config.py
- Fase 2: plan consolidado (recuperación de contraseña, verificación de email y correo por cliente)
- test_forgot_payload_is_strict
- Fase 2: implementación del desarrollador (correo, verificación de email y recuperación de contraseña)
- docs_accounts.py
- test_user_cannot_see_email_jobs
- test_crypto.py
- test_profile_updates_cannot_touch_email_fields
- test_rate_limit_on_forgot_is_audited
- schemas/account.py
- test_privacy.py
- Job
- types.py
- enqueue_account_email
- test_bad_tokens_get_the_same_400
- FieldSpec
- JSONTrustedHostMiddleware
- resolve_language
- render_inventory
- file.py
- _docs_project
- Hardening SOC 2 e ISO/IEC 27701: controles, evidencias y responsabilidades
- json_log
- user_columns
- Inventario de datos personales
- test_init_env_output_loads
- refresh_graph
- _check_router_symbols
- naming.py
- error_responses
- ErrorBody
- .render

## God Nodes (most connected - your core abstractions)
1. `utcnow()` - 91 edges
2. `User` - 89 edges
3. `ResourceSpec` - 68 edges
4. `task()` - 52 edges
5. `process_pending()` - 49 edges
6. `Job` - 48 edges
7. `Settings` - 47 edges
8. `create_user()` - 46 edges
9. `audit()` - 44 edges
10. `SpecError` - 36 edges

## Surprising Connections (you probably didn't know these)
- `bench_note (owned, write-heavy)` --semantically_similar_to--> `order resource (owned)`  [INFERRED] [semantically similar]
  loadtests/resources.loadtest.yaml → examples/shop.yaml
- `bench_product (read-heavy public catalog)` --semantically_similar_to--> `product resource (soft delete, rate limits)`  [INFERRED] [semantically similar]
  loadtests/resources.loadtest.yaml → examples/shop.yaml
- `_count_unverified()` --uses--> `User`  [INFERRED]
  apigen/cli.py → app/models/user.py
- `_revoke_sessions()` --uses--> `RefreshToken`  [INFERRED]
  apigen/cli.py → app/models/refresh_token.py
- `_revoke_sessions()` --uses--> `User`  [INFERRED]
  apigen/cli.py → app/models/user.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Four-round multi-agent security and usability review** — _claude_agents_security_expert_security_expert_agent, _claude_agents_developer_developer_agent, _claude_agents_user_user_agent, security_revision_seguridad_review_summary [EXTRACTED 1.00]
- **Client IP authenticity as a security control (proxy trust, lockout, rate limit)** — security_reports_ronda1_seguridad_sec_04, security_reports_ronda3_seguridad_sec_21, security_reports_ronda3_seguridad_sec_22, readme_trusted_proxies, docker_compose_backend_network, security_reports_ronda4_desarrollador_proxy_validation, security_reports_ronda2_desarrollador_t1_smart_lockout [INFERRED 0.85]
- **Concurrent refresh race: detection, grace period and client serialization** — security_reports_ronda1_seguridad_sec_01, security_reports_ronda1_usuario_ux_02, security_reports_ronda1_usuario_ux_19, security_reports_ronda2_desarrollador_t2_refresh_grace_period, guia_readme_refreshaccess, readme_refresh_token_rotation [INFERRED 0.85]

## Communities (140 total, 13 thin omitted)

### Community 0 - "ronda7_generator_checks.py"
Cohesion: 0.40
Nodes (4): accepted(), Ronda 7: acciones del generador (ActionSpec, router.py.j2, stubs de…, router_src(), spec()

### Community 1 - "cli.py"
Cohesion: 0.06
Nodes (92): add(), _alembic_config(), audit_verify(), lines(), createsuperuser(), _data_key(), db_current(), db_downgrade() (+84 more)

### Community 2 - "_prod"
Cohesion: 0.12
Nodes (17): _prod(), SEC-24: un DATABASE_URL ausente no puede acabar en SQLite en silencio., UX-34: 50/hour fuera de producción (cuentas de prueba), 5/hour en producción., SEC-38: el worker arranca en producción sin SECRET_KEY (no firma tokens); la…, test_production_baseline_is_valid(), test_register_limit_depends_on_environment(), test_sqlite_in_production_needs_explicit_opt_in(), test_trusted_proxies_must_be_ips() (+9 more)

### Community 3 - "rate_limit.py"
Cohesion: 0.13
Nodes (22): check_unrouted_limit(), enforce_rate_limits(), _evaluate_with_fallback(), ip_key(), _maybe_recover_backend(), Request, Response, Rate limiting con SlowAPI. - Clave por usuario autenticado (`user:<id>`) o, si… (+14 more)

### Community 4 - "codegen.py"
Cohesion: 0.17
Nodes (26): build_context(), _classification_kwargs(), create_field(), _default_expr(), enum_class(), enum_members(), _examples_kwarg(), filter_param() (+18 more)

### Community 5 - "test_generator.py"
Cohesion: 0.05
Nodes (76): ensure_user_module(), Path, Crea el módulo si no existe o añade al final las funciones que falten. Devuelve…, render_resource(), pluralize(), parse_field_option(), Mini-DSL de la CLI: `nombre:tipo[:opción...]`. Ejemplos:…, _action_spec() (+68 more)

### Community 6 - "task"
Cohesion: 0.10
Nodes (35): echo(), prune(), Any, Tareas incluidas en la plantilla., Devuelve el payload recibido. Útil para comprobar que el worker funciona., Limpieza periódica: trabajos terminados antiguos., Any, BaseModel (+27 more)

### Community 7 - "test_auth.py"
Cohesion: 0.07
Nodes (37): lockout_minutes(), Duración del bloqueo: se dobla con cada bloqueo consecutivo, con tope., _login(), HTTPException, Registro, login, bloqueo de cuenta, rotación y revocación de tokens., SEC-02: un anónimo que conoce el email ya no deja fuera al titular desde una IP…, Reproduce de forma determinista la carrera de SEC-01: el "perdedor" leyó la…, SEC-01: el perdedor de la carrera recibe 401 (no 500) y la familia se revoca. (+29 more)

### Community 8 - "Send"
Cohesion: 0.16
Nodes (7): tracking_send(), NullByteGuardMiddleware, Rechaza NUL (``\\x00`` o ``%00``) en la ruta o la query con un 422. PostgreSQL…, send_wrapper(), _send_413(), Receive, Send

### Community 9 - "errors.py"
Cohesion: 0.14
Nodes (29): _constraint_columns(), data_error_handler(), describe_integrity_error(), http_exception_handler(), integrity_handler(), internal_error_body(), log_unhandled(), Exception (+21 more)

### Community 10 - "crud/base.py"
Cohesion: 0.09
Nodes (32): DatabaseValueError, Exception, Un valor que el esquema aceptó pero el driver de la BD no puede guardar (p. ej.…, apply_on_delete(), _commit(), ensure_reference(), escape_like(), Any (+24 more)

### Community 11 - "docs.py"
Cohesion: 0.16
Nodes (22): _call_name(), custom_errors(), _example_value(), _examples(), _field_rules(), _field_type(), _literal_text(), Path (+14 more)

### Community 12 - "schemas/user.py"
Cohesion: 0.10
Nodes (27): _has_nul(), Message, Page, PartialUpdate, Any, BaseModel, field_validator, model_validator (+19 more)

### Community 13 - "User"
Cohesion: 0.11
Nodes (45): AdminPrincipal, _admin_count(), change_email(), change_password(), _counts_as_admin(), create_user(), delete_me(), delete_user() (+37 more)

### Community 14 - "list_jobs"
Cohesion: 0.17
Nodes (16): alias, cancel_job(), get_job(), _get_or_404(), list_jobs(), get, max_length, PaginationDep (+8 more)

### Community 15 - "headers_for"
Cohesion: 0.08
Nodes (22): headers_for(), EMAIL_DELIVERY=inline (desarrollo): el correo sale sin worker., test_inline_delivery_runs_the_job_after_the_response(), UX-12: token caducado -> code token_expired (RFC 6750 error_description)., test_expired_token_is_distinguishable(), test_delete_me_can_be_disabled(), test_delete_me_requires_password(), test_export_requires_auth_and_is_rate_limited() (+14 more)

### Community 16 - "Round 3 security verification report"
Cohesion: 0.16
Nodes (19): api service (forced production, read-only, cap_drop ALL), backend network (fixed subnet 172.30.57.0/24), db service (PostgreSQL 17), redis service (Redis 7, rate-limit storage), Accepted and documented security risks, SEC-02 third-party account lockout DoS, SEC-03 compose could start in development, SEC-04 shared client IP behind proxy without TRUSTED_PROXIES (+11 more)

### Community 17 - "3. Hallazgos nuevos"
Cohesion: 0.13
Nodes (14): 1. Resumen ejecutivo, 2. Uso de graphify: consultas y qué revelaron, 3. Hallazgos nuevos, 4. Controles re-verificados en el laboratorio (ronda 5), 5. No verificado en esta ronda, 6. Veredicto actualizado, Detalles menores (Info, sin ID), Revisión de seguridad — Ronda 5 (revisión completa guiada por el grafo de graphify) (+6 more)

### Community 18 - "Round 1 security audit report"
Cohesion: 0.20
Nodes (14): OWASP ASVS Level 2, OWASP API Security Top 10 (2023), security-expert agent (defensive AppSec auditor), security/lab.sh local audit lab (127.0.0.1), user agent (first-time template developer), Field syntax name:type[:options] (13 field types), Permission levels (public / user / owner / admin), shared_read flag (--shared-read) (+6 more)

### Community 19 - "create_user"
Cohesion: 0.10
Nodes (36): Ejecuta un trabajo ya reclamado y registra el resultado. Nunca lanza. Con…, run_job(), AsyncClient, El worker ejecuta hasta JOBS_CONCURRENCY trabajos a la vez: el cupo (contar y…, Modo optional: alguien registra el email de la víctima con un full_name de…, Comprobaciones de seguridad de la fase 2 (validación independiente del…, Registro, verificación, reset, cambio de email y avisos con DEBUG en la raíz., Réplica pequeña de ST-03 (forgot) sin rate limit: la API solo encola. (+28 more)

### Community 20 - "Round 1 user experience report"
Cohesion: 0.22
Nodes (14): Resource spec YAML (resources/<name>.yaml source of truth), apigen CLI / CRUD code generator, Stable error `code` contract ({detail, code}), SEC-09 global uniqueness in owned resources (existence oracle), Round 1 user experience report, UX-01 generated .env does not start, UX-03 db migrate with no changes raises traceback, UX-10 generic 409 conflict (+6 more)

### Community 21 - "main"
Cohesion: 0.25
Nodes (11): b64(), bearer(), check(), login(), login_budget(), main(), Response, Verificación de controles de seguridad contra el laboratorio local (ronda 1).… (+3 more)

### Community 22 - "Worker"
Cohesion: 0.17
Nodes (8): heartbeat_path(), Escribe el latido sin seguir enlaces simbólicos (SEC-36): fichero temporal…, Fichero de latido que comprueba el healthcheck (JOBS_HEARTBEAT_FILE)., Worker, SEC-36: el latido sustituye el fichero; nunca escribe a través de un enlace., SEC-39: con la BD caída no hay latido (el healthcheck pasa a unhealthy) y la…, test_heartbeat_does_not_follow_symlinks(), test_worker_heartbeat_only_while_database_answers()

### Community 23 - "ronda5_checks.py"
Cohesion: 0.38
Nodes (5): bearer(), brief(), login(), Response, Ronda 5: re-verificación de extremo a extremo de los controles críticos y de…

### Community 24 - "ResourceSpec"
Cohesion: 0.07
Nodes (65): hooks_module(), Rendered, tasks_module(), add_version(), check_spec_sources(), default_version(), dependents(), deprecate_version() (+57 more)

### Community 25 - "run_loadtest.sh"
Cohesion: 0.15
Nodes (11): DATABASE_URL, DOCS_ENABLED, ENVIRONMENT, LOADTEST_PASSWORD, LOG_LEVEL, PASSWORD_HASH_CONCURRENCY, PYTHONPATH, SECRET_KEY (+3 more)

### Community 26 - "test_security.py"
Cohesion: 0.04
Nodes (47): Environment, StrEnum, check_json_size(), depth(), Validador para campos `json`: limita tamaño serializado y anidamiento (evita…, _claims(), _forge(), Defensas transversales: tokens, cabeceras, tamaño de body, errores y rate limit. (+39 more)

### Community 27 - "Ronda 5: informe del usuario (revisión completa e integración con graphify)"
Cohesion: 0.29
Nodes (6): 1. Lo ya resuelto sigue bien, 2. Puntos nuevos, 3. Valoración específica de graphify, 4. Lo que me ha gustado, 5. Valoración global, Ronda 5: informe del usuario (revisión completa e integración con graphify)

### Community 28 - "test_account.py"
Cohesion: 0.07
Nodes (65): process_pending(), Procesa los trabajos listos y vuelve (útil en tests y en `apigen worker…, _login(), Flujos de cuenta: recuperación de contraseña, verificación y cambio de email.…, ST-17: el 422 de política no consume el enlace., ST-11: dos consumos a la vez → exactamente un 204., ST-14: dos resets pedidos, uno usado → el otro no vale; cambiar la contraseña…, ST-21/19 y D2: una cuenta bloqueada completa el reset y entra; la IP conocida… (+57 more)

### Community 30 - "main.py"
Cohesion: 0.10
Nodes (22): APIVersion, Registro de versiones de la API. Cada versión se monta en…, BodySizeLimitMiddleware, RateLimitHeadersMiddleware, Middlewares ASGI puros (más rápidos que BaseHTTPMiddleware)., Cabeceras de seguridad en todas las respuestas., Rechaza cuerpos mayores que MAX_BODY_SIZE (también con chunked encoding)., Convierte excepciones no controladas en un 500 JSON *dentro* de la pila de… (+14 more)

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
Cohesion: 0.25
Nodes (7): create_engine(), _engine_kwargs(), get_session(), Any, AsyncSession, Motor async y sesiones. Cambiar de base de datos = cambiar DATABASE_URL., AsyncEngine

### Community 36 - "fase2_docker_e2e.py"
Cohesion: 0.19
Nodes (20): Client, compose(), drain(), login(), mails_to(), main(), mann_whitney_p(), message() (+12 more)

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
Nodes (8): _future_date(), _future_datetime(), _like(), Utilidades para tests (también las usan los tests generados por apigen)., Valor aleatorio con la misma forma que `example` (a->letra, 9->dígito)., Fecha ISO dentro de un año (+offset días): válida para reglas tipo "no en el…, Fecha y hora ISO con zona, dentro de un año (+offset días), a las 10:00 UTC., _text()

### Community 42 - "new_api.py"
Cohesion: 0.12
Nodes (33): all_files(), check_clean(), claude_md(), configure_email(), default_title(), developer_docs(), dirty_files(), _env_value() (+25 more)

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

### Community 48 - "3. Puntos nuevos"
Cohesion: 0.09
Nodes (21): 1. Resumen, 2. MUST → cumplimiento, 3. Puntos nuevos, 4. Lo que me gustó, 5. Fricciones restantes (de mi plan, F-01..12), 6. Valoración para vender, Fase 2 · Validación del usuario (freelancer + cliente), UX-67 · Alta · El zip entregado no lleva la configuración de correo elegida (+13 more)

### Community 49 - "refresh_race.py"
Cohesion: 0.67
Nodes (3): main(), Carrera en /auth/refresh con DOS peticiones simultáneas (el caso realista: el…, trial()

### Community 53 - "Settings"
Cohesion: 0.07
Nodes (14): Any, field_validator, Backend efectivo: el configurado o el de por defecto del entorno., ¿Hay algún flujo de cuenta por correo? (habilita el cambio de email)., Contraseña SMTP (de la variable o de SMTP_PASSWORD_FILE, p. ej. Docker secrets)., Settings, BaseSettings, check() (+6 more)

### Community 54 - "check"
Cohesion: 0.13
Nodes (16): check(), _clean(), _count_unverified(), _email_rows(), _privacy_rows(), Exception, Filas de auditoría, privacidad y retención de `apigen check` (SOC 2 / ISO…, Filas de correo de `apigen check` (sin credenciales). (+8 more)

### Community 55 - "test_new_api.py"
Cohesion: 0.22
Nodes (15): _git(), _load(), _new(), fixture, Path, scripts/new_api.py: solo copia lo versionado y no deja pasar secretos ni datos…, La plantilla versionada no debe disparar el escáner (falsos positivos)., UX-67: la configuración NO secreta de correo va también a `.env.example` (lo… (+7 more)

### Community 56 - "3. Hallazgos nuevos"
Cohesion: 0.12
Nodes (16): 0. Resumen, 1. Casos ST → estado → evidencia, 2. Requisitos MUST, 3. Hallazgos nuevos, 4. Veredicto, Controles verificados que funcionan (destacados), Cómo lo he verificado, Fase 2 – Validación de seguridad (correo, verificación de email y recuperación de contraseña) (+8 more)

### Community 57 - "endpoints/auth.py"
Cohesion: 0.15
Nodes (27): login(), logout(), logout_all(), BackgroundTasks, Depends, JSONResponse, limit, post (+19 more)

### Community 58 - "Ronda 7 – Informe de usuario (desarrollador que crea y entrega APIs a clientes)"
Cohesion: 0.22
Nodes (8): 0. Qué he hecho, 1. Puntos encontrados, 2. README para clientes (lo que recibe el cliente final), 3. Hooks y acciones: valoración, 4. Lo que me ha gustado, 5. Valoración, Mejoras concretas, Ronda 7 – Informe de usuario (desarrollador que crea y entrega APIs a clientes)

### Community 59 - "queue.py"
Cohesion: 0.17
Nodes (21): backoff_seconds(), cancel(), complete(), enqueue(), fail(), _json_size(), _leased(), Any (+13 more)

### Community 60 - "ronda7_worker_checks.py"
Cohesion: 0.27
Nodes (10): JobAccepted, JobRead, BaseModel, Respuesta 202 de un endpoint con proceso en segundo plano., check(), main(), put(), Ronda 7: comprobaciones del lado del worker contra la BD del laboratorio.… (+2 more)

### Community 61 - "conftest.py"
Cohesion: 0.24
Nodes (16): admin(), admin_headers(), client(), _database(), db(), mail(), other_headers(), other_user() (+8 more)

### Community 62 - "Fase 2 — Plan técnico del desarrollador: correo, verificación de email y recuperación de contraseña"
Cohesion: 0.06
Nodes (35): 0. Principios que condicionan el diseño, 1.1 Decisión: tabla de tokens de un solo uso (y no campos en `users`), 1.2 `app/models/account_token.py`, 1.3 Cambios en `users`, 1.4 Migración, 1.5 Limpieza, 1. Modelo de datos, 2.1 Tabla (+27 more)

### Community 63 - "ronda7_checks.py"
Cohesion: 0.33
Nodes (3): brief(), Response, Ronda 7: cola de trabajos, acciones generadas y NullByteGuard por HTTP.…

### Community 64 - "ready"
Cohesion: 0.21
Nodes (11): HealthStatus, live(), BaseModel, get, Request, Response, SessionDep, El proceso está vivo (para liveness probes). No toca la base de datos. (+3 more)

### Community 66 - "2. Historias de usuario: CLIENTE / FRONTEND"
Cohesion: 0.06
Nodes (32): 0. Lo que hay hoy y condiciona el diseño, 1. Historias de usuario: FREELANCER, 2. Historias de usuario: CLIENTE / FRONTEND, 3.1 Variables sugeridas (bloque nuevo en `.env.example`), 3.2 Proveedores: qué merece la pena, 3.3 Plantillas de email, 3.4 Envío y robustez (lo que el cliente nota), 3.5 Integración con `apigen` (+24 more)

### Community 81 - "test_email.py"
Cohesion: 0.07
Nodes (28): _email_hint(), reset_backend(), build_link(), Enlaces de los correos: SOLO desde FRONTEND_URL + EMAIL_LINK_* (REQ-L01/L02).…, fake_smtp(), fixture, Subsistema de correo: backends, SMTP, plantillas, enlaces y configuración., ST-36: sin STARTTLS anunciado se falla, no se degrada a texto plano. (+20 more)

### Community 82 - "api-template"
Cohesion: 0.50
Nodes (3): api-template, Cómo trabajar aquí, graphify

### Community 83 - "render.py"
Cohesion: 0.12
Nodes (29): environment(), base_context(), check_templates(), _environment(), _find(), _find_exact(), Any, Exception (+21 more)

### Community 84 - "test_jobs.py"
Cohesion: 0.17
Nodes (26): JobStatus, StrEnum, prune_jobs(), Borra trabajos terminados más antiguos que la retención configurada., _enqueue(), _job(), Cola de trabajos en segundo plano: ejecución, permisos, reintentos y límites., SEC-33: al vencer el timeout se mata el proceso de la tarea (no sigue corriendo… (+18 more)

### Community 85 - "endpoints/account.py"
Cohesion: 0.17
Nodes (26): _already_done(), forgot_password(), BackgroundTasks, limit, post, Request, Response, SessionDep (+18 more)

### Community 86 - "backends/__init__.py"
Cohesion: 0.17
Nodes (18): DisabledBackend, EmailBackend, EmailError, PermanentEmailError, Exception, Interfaz de los backends de correo y sus errores. Los mensajes de error son…, Fallo pasajero (red, timeout, SMTP 4xx): se reintenta con el backoff de la cola., Fallo definitivo (SMTP 5xx, autenticación, destinatario rechazado): no se… (+10 more)

### Community 87 - "_send_token_email"
Cohesion: 0.17
Nodes (26): mask_email(), n***@dominio.com: para mostrar en avisos sin exponer la dirección completa., timedelta, ttl(), account_exists(), _deliver(), email_change(), email_verification() (+18 more)

### Community 88 - "services/auth.py"
Cohesion: 0.13
Nodes (36): generate_refresh_token(), hash_token(), looks_like_refresh_token(), Devuelve (token_en_claro, hash). El token solo se entrega al cliente., Refresh token opaco. Solo se guarda su hash SHA-256. Todos los tokens de una…, RefreshToken, BaseModel, TokenPair (+28 more)

### Community 89 - "worker.py"
Cohesion: 0.16
Nodes (18): TaskDef, _child_main(), _ChildError, _execute(), main(), _main(), _mp_context(), _process_slots() (+10 more)

### Community 90 - "deps.py"
Cohesion: 0.08
Nodes (37): current_user(), get_principal(), Principal, Depends, HTTPException, Request, SessionDep, user (+29 more)

### Community 91 - "mail.py"
Cohesion: 0.11
Nodes (31): format_duration(), "30 minutes" / "30 minutos" / "48 hours" / "48 horas"., EmailLog, Registro de tareas en segundo plano. Importar este paquete registra todas las…, _circuit_open(), _count_since(), EmailChangePayload, EmailPayload (+23 more)

### Community 92 - "EmailMessage"
Cohesion: 0.15
Nodes (15): ConsoleBackend, Backend de desarrollo: escribe el correo en el log (con el enlace en su línea)., MemoryBackend, Backend en memoria para tests: los mensajes quedan en `outbox`., build_mime(), clean_subject(), EmailMessage, message_id_for() (+7 more)

### Community 93 - "env.py"
Cohesion: 0.39
Nodes (7): _configure(), do_run_migrations(), Entorno de Alembic (async). La URL sale de DATABASE_URL, nunca de alembic.ini., run_async_migrations(), run_migrations_offline(), _skip_empty(), Connection

### Community 94 - "utcnow"
Cohesion: 0.12
Nodes (31): _prune(), _revoke_sessions(), utcnow(), AccountToken, StrEnum, TokenPurpose, consume(), find_valid() (+23 more)

### Community 95 - "Ronda 6 — Respuesta del desarrollador"
Cohesion: 0.25
Nodes (7): 1. Tabla de decisiones, 2. UX-40: decisión sobre soft delete con hijos, 3. SEC-25 / UX-39: recomendación técnica (sin tocar `.claude/`), 4. Observaciones nuevas y pendientes, 5. Ficheros modificados, Estado final, Ronda 6 — Respuesta del desarrollador

### Community 96 - "ValueError"
Cohesion: 0.14
Nodes (12): ActionSpec, coerce_value(), Permissions, BaseModel, field_validator, model_validator, RateLimits, Valida que un default/example tenga el tipo correcto y lo normaliza. (+4 more)

### Community 97 - "call"
Cohesion: 0.11
Nodes (12): add_listener, FastHttpUser, Attacker, call(), _load_products(), Member, Pruebas de estrés con Locust. Usuarios virtuales (el peso indica la…, Tráfico hostil: aquí la respuesta "esperada" es un rechazo. (+4 more)

### Community 98 - "Ronda 8 — Respuesta del desarrollador a la ronda 7"
Cohesion: 0.25
Nodes (7): 1. Seguridad, 2. Usabilidad, 3. README para clientes (sección 2 del informe del usuario), 4. Pospuesto o rechazado (resumen), 5. Ficheros modificados, 6. Notas para la siguiente ronda, Ronda 8 — Respuesta del desarrollador a la ronda 7

### Community 99 - "logging.py"
Cohesion: 0.19
Nodes (11): _escape(), JSONFormatter, Logging estructurado con request-id propagado mediante contextvars., Escapa caracteres de control (CR/LF...): impide falsificar líneas de log con…, Formato legible para desarrollo: una línea por evento, con los campos `extra`…, _RequestIdFilter, setup_logging(), TextFormatter (+3 more)

### Community 100 - "4. Requisitos"
Cohesion: 0.11
Nodes (18): 0. Punto de partida (lo que ya existe y condiciona el diseño), 1. Superficie nueva de referencia, 2. Modelo de amenazas, 3. Decisiones de diseño recomendadas (resumen argumentado), 4.10 Registros y auditoría (G), 4.1 Tokens (T), 4.2 Enumeración y respuesta uniforme (E), 4.3 Flujos (F) (+10 more)

### Community 101 - "Fase 2: correcciones de la validación (SEC-40..45, UX-67..80)"
Cohesion: 0.25
Nodes (7): 1. Seguridad, 2. Usuario, 3. Verificación, 4. Cambios de comportamiento a tener en cuenta, 5. Pendiente o justificado, 6. Ficheros tocados en esta ronda, Fase 2: correcciones de la validación (SEC-40..45, UX-67..80)

### Community 102 - "config.py"
Cohesion: 0.14
Nodes (18): _address_problem(), _data_key_problems(), _email_problems(), get_settings(), _has_control(), _is_local_host(), _link_problem(), _proxy_problems() (+10 more)

### Community 104 - "security.py"
Cohesion: 0.17
Nodes (14): AccessToken, _build_keyring(), create_access_token(), hash_password(), _KeyRing, _kid(), _limiter(), UUID (+6 more)

### Community 105 - "audit"
Cohesion: 0.15
Nodes (23): audit(), _canonical(), _digest(), _key(), Any, Registro de auditoría: eventos de seguridad estructurados en el logger…, Comprueba la cadena de los eventos de auditoría de un log JSON (una línea por…, verify_lines() (+15 more)

### Community 107 - "_TextExtractor"
Cohesion: 0.25
Nodes (5): html_to_text(), Texto plano a partir del HTML (si una plantilla propia no trae el .txt)., _TextExtractor, HTMLParser, test_html_to_text()

### Community 108 - "test_config.py"
Cohesion: 0.12
Nodes (18): _is_sequence(), password_problems(), Política de contraseñas basada en NIST 800-63B: longitud y listas negras, sin…, fake_project(), fixture, Configuración y CLI: el .env generado arranca, validaciones y utilidades., UX-32: la CLI no mezcla idiomas., UX-65: el motivo del rechazo (dominio reservado) llega al usuario. (+10 more)

### Community 109 - "Fase 2: plan consolidado (recuperación de contraseña, verificación de email y correo por cliente)"
Cohesion: 0.22
Nodes (8): 1. Arquitectura acordada (los tres coinciden), 2. Endpoints, 3. Decisiones sobre los puntos en desacuerdo, 4. Configuración por cliente (resumen de variables), 5. Herramientas y entrega, 6. Orden de implementación, 7. Validación final, Fase 2: plan consolidado (recuperación de contraseña, verificación de email y correo por cliente)

### Community 111 - "Fase 2: implementación del desarrollador (correo, verificación de email y recuperación de contraseña)"
Cohesion: 0.22
Nodes (8): 1. Pasos del plan (§6): cambio → ficheros → tests, 2. Requisitos MUST de seguridad (`fase2-plan-seguridad.md` §4), 3. MUST del usuario (`fase2-plan-usuario.md` §6), 4. Desviaciones del plan y motivo, 5. Instrucciones para la validación, 6. Pendiente o para decidir, 7. Ficheros, Fase 2: implementación del desarrollador (correo, verificación de email y recuperación de contraseña)

### Community 112 - "docs_accounts.py"
Cohesion: 0.23
Nodes (12): account_section(), account_settings(), mismatches(), modes(), Path, Sección del README del cliente sobre los flujos de cuenta por correo (en/es).…, Sección "Correos de cuenta" (vacía si no hay flujos activos)., `.env.example` + `.env` + variables de entorno (UX-79), solo para las claves de… (+4 more)

### Community 114 - "test_crypto.py"
Cohesion: 0.18
Nodes (22): check_keys(), decrypt(), encrypt(), EncryptedText, EncryptionError, key_id(), _keys(), parse_key() (+14 more)

### Community 117 - "schemas/account.py"
Cohesion: 0.13
Nodes (17): features(), get, Flujos de cuenta que ofrece esta API: el frontend puede mostrar u ocultar…, AccountFeatures, EmailChangeRequest, EmailRequest, _no_nul(), PasswordResetRequest (+9 more)

### Community 118 - "test_privacy.py"
Cohesion: 0.20
Nodes (15): _add_note(), _note_exists(), _notes_table(), fixture, UUID, Derechos del interesado y retención (ISO 27701 7.3.6/7.3.8/7.4.7, SOC 2 P4-P5,…, test_delete_me_erases_account_and_cascades(), test_export_contains_account_sessions_and_owned_rows() (+7 more)

### Community 119 - "Job"
Cohesion: 0.23
Nodes (13): Job, claim(), Reclama hasta `limit` trabajos listos y los marca como `running`. Con `job_id`,…, Devuelve a la cola los trabajos de workers caídos (arrendamiento vencido)., reclaim_stale(), _scrubbed_names(), test_sec43_reclaimed_and_cancelled_jobs_keep_payload(), ST-42: un fallo pasajero se reintenta; uno definitivo falla sin reintento, con… (+5 more)

### Community 120 - "types.py"
Cohesion: 0.11
Nodes (17): datetime, UUID, Tipos de columna y generadores de IDs., UUID v7 (RFC 9562): ordenado en el tiempo, así los índices B-tree se mantienen…, DateTime siempre en UTC y con tzinfo, también en SQLite (que no guarda zona)., UTCDateTime, uuid7(), Tokens de un solo uso de los flujos de cuenta (reset, verificación, cambio de… (+9 more)

### Community 121 - "enqueue_account_email"
Cohesion: 0.22
Nodes (12): enqueue_account_email(), Any, AsyncSession, BackgroundTasks, UUID, Envío de correo: API pública para el código del proyecto. from app.email import…, Encola un correo con una plantilla (de serie o de EMAIL_TEMPLATES_DIR). Con…, Encola un correo de cuenta como trabajo de SISTEMA (owner_id=None, REQ-Q01).… (+4 more)

### Community 122 - "test_bad_tokens_get_the_same_400"
Cohesion: 0.67
Nodes (3): parametrize, ST-13/16: forma inválida, otro propósito o tamaño enorme → mismo 400, sin 500., test_bad_tokens_get_the_same_400()

### Community 123 - "FieldSpec"
Cohesion: 0.23
Nodes (9): build_test_context(), make_parent(), example_expr(), _model_value(), Expresión Python que produce un valor válido (distinto por `variant`)., Datos para el test generado: payload válido, padres a crear y campo a…, Igual que example_expr pero con tipos Python (para insertar vía ORM)., FieldSpec (+1 more)

### Community 124 - "JSONTrustedHostMiddleware"
Cohesion: 0.20
Nodes (7): BodyTooLarge, _HostRejectionSend, JSONTrustedHostMiddleware, HTTPException, `TrustedHostMiddleware` de Starlette con el 400 en JSON y con `code` (contrato…, `send` que convierte el 400 de texto plano de Starlette en JSON., TrustedHostMiddleware

### Community 125 - "resolve_language"
Cohesion: 0.18
Nodes (10): Idioma a usar: un código o una cabecera Accept-Language, SIEMPRE dentro de…, resolve_language(), parametrize, ST-32: el idioma nunca se concatena a una ruta., ST-34/35/31: la app no arranca, con un mensaje que dice qué variable cambiar., apigen docs: la sección de cuentas sale solo con los flujos activos., test_accept_language_negotiation(), test_client_readme_documents_account_flows() (+2 more)

### Community 126 - "render_inventory"
Cohesion: 0.31
Nodes (8): _defaults(), merge_inventory(), Any, Inventario de datos personales: `apigen privacy inventory` ->…, Bloque generado (entre marcadores) del inventario., Sustituye el bloque generado y conserva lo que el responsable haya completado., render_inventory(), _resource_rows()

### Community 127 - "file.py"
Cohesion: 0.36
Nodes (5): FileBackend, Path, Backend de desarrollo: guarda cada correo como .eml (y .html) en EMAIL_FILE_DIR., _write_new(), test_file_backend_writes_private_eml()

### Community 128 - "_docs_project"
Cohesion: 0.25
Nodes (8): _docs_project(), Path, `apigen docs`: README.md para el cliente desde los recursos; conserva lo manual., UX-52: `apigen docs` sin --lang conserva el idioma (y la URL base) elegidos., Informe del usuario (ronda 7): respuesta del login, paginación, un ejemplo por…, test_client_readme_documents_integration_details(), test_client_readme_is_generated_and_keeps_manual_text(), test_client_readme_remembers_language_and_base_url()

### Community 129 - "Hardening SOC 2 e ISO/IEC 27701: controles, evidencias y responsabilidades"
Cohesion: 0.29
Nodes (6): 1. Controles añadidos en este hardening, 2. Procedimientos operativos, 3. Riesgos residuales y decisiones, 4. Responsabilidad del operador (fuera del código), Controles que ya existían (relación con los criterios), Hardening SOC 2 e ISO/IEC 27701: controles, evidencias y responsabilidades

### Community 130 - "json_log"
Cohesion: 0.40
Nodes (4): _Chain, json_log(), fixture, Captura los eventos de `app.audit` tal como saldrían en el log JSON.

### Community 131 - "user_columns"
Cohesion: 0.40
Nodes (6): personal_tables(), Column, Table, Columnas de `table` que apuntan a un usuario (owner_id, autor...)., Tablas de recursos (no del núcleo) con filas asociadas a un usuario., user_columns()

### Community 132 - "Inventario de datos personales"
Cohesion: 0.33
Nodes (5): A completar por el responsable (fuera de los marcadores: apigen no lo toca), Derechos de los interesados, Inventario de datos personales, Recursos generados (`resources/*.yaml`), Tablas del núcleo (plantilla)

### Community 133 - "test_init_env_output_loads"
Cohesion: 0.40
Nodes (5): parametrize, SEC-21: confiar en XFF de cualquiera permite falsificar la IP del cliente., UX-01: el .env de `init-env` (con variables vacías) es válido tal cual., test_init_env_output_loads(), test_wildcard_trusted_proxies_rejected_in_production()

### Community 134 - "refresh_graph"
Cohesion: 0.50
Nodes (4): Actualiza el grafo de graphify tras cambiar código (solo AST: rápido y sin…, refresh_graph(), apigen solo toca graphify si el proyecto ya tiene grafo y no está desactivado., test_refresh_graph_is_optional()

### Community 135 - "_check_router_symbols"
Cohesion: 0.67
Nodes (3): _check_router_symbols(), Any, Defensa en profundidad (SEC-31): ningún nombre del router generado puede…

### Community 137 - "error_responses"
Cohesion: 0.67
Nodes (3): error_responses(), Any, Respuestas de error documentadas en OpenAPI para los endpoints generados.

### Community 138 - "ErrorBody"
Cohesion: 0.67
Nodes (3): ErrorBody, BaseModel, Forma de las respuestas de error (para OpenAPI y clientes generados).

## Knowledge Gaps
- **211 isolated node(s):** `run_loadtest.sh script`, `PYTHONPATH`, `ENVIRONMENT`, `DOCS_ENABLED`, `LOG_LEVEL` (+206 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 959 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `User` connect `User` to `cli.py`, `test_auth.py`, `errors.py`, `headers_for`, `create_user`, `test_security.py`, `test_account.py`, `check`, `endpoints/auth.py`, `ronda7_worker_checks.py`, `conftest.py`, `endpoints/account.py`, `_send_token_email`, `services/auth.py`, `deps.py`, `mail.py`, `utcnow`, `security.py`, `test_privacy.py`, `types.py`?**
  _High betweenness centrality (0.075) - this node is a cross-community bridge._
- **Why does `utcnow()` connect `utcnow` to `cli.py`, `queue.py`, `crud/base.py`, `mail.py`, `User`, `test_account.py`, `render.py`, `test_jobs.py`, `endpoints/account.py`, `_send_token_email`, `Job`, `types.py`, `enqueue_account_email`, `create_user`, `services/auth.py`, `EmailMessage`, `test_privacy.py`, `file.py`?**
  _High betweenness centrality (0.062) - this node is a cross-community bridge._
- **Why does `ResourceSpec` connect `ResourceSpec` to `ValueError`, `cli.py`, `ronda7_generator_checks.py`, `codegen.py`, `test_generator.py`, `_check_router_symbols`, `docs.py`, `FieldSpec`, `render_inventory`?**
  _High betweenness centrality (0.035) - this node is a cross-community bridge._
- **Are the 60 inferred relationships involving `User` (e.g. with `_count_unverified()` and `_revoke_sessions()`) actually correct?**
  _`User` has 60 INFERRED edges - model-reasoned connections that need verification._
- **Are the 45 inferred relationships involving `ResourceSpec` (e.g. with `_warn_specs()` and `build_context()`) actually correct?**
  _`ResourceSpec` has 45 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `task()` (e.g. with `decorator()` and `ValueError`) actually correct?**
  _`task()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `run_loadtest.sh script`, `PYTHONPATH`, `ENVIRONMENT` to the rest of the system?**
  _211 weakly-connected nodes found - possible documentation gaps or missing edges._