# Graph Report - api-template  (2026-09-26)

## Corpus Check
- 143 files · ~172,184 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2174 nodes · 5004 edges · 120 communities (94 shown, 10 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 472 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `27c0c38d`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- ResourceSpec
- command
- test_config.py
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
- project.py
- run_loadtest.sh
- test_security.py
- Ronda 5: informe del usuario (revisión completa e integración con graphify)
- test_account.py
- hooks/__init__.py
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
- cli.py
- test_new_api.py
- 3. Hallazgos nuevos
- endpoints/auth.py
- Ronda 7 – Informe de usuario (desarrollador que crea y entrega APIs a clientes)
- queue.py
- Job
- conftest.py
- Fase 2 — Plan técnico del desarrollador: correo, verificación de email y recuperación de contraseña
- ronda7_checks.py
- ready
- ronda7_docker_checks.py
- 2. Historias de usuario: CLIENTE / FRONTEND
- api-template
- test_email.py
- api-template
- render
- test_jobs.py
- endpoints/account.py
- backends/__init__.py
- _send_token_email
- utcnow
- worker.py
- deps.py
- mail.py
- EmailMessage
- env.py
- secret
- Ronda 6 — Respuesta del desarrollador
- spec.py
- call
- Ronda 8 — Respuesta del desarrollador a la ronda 7
- logging.py
- 4. Requisitos
- Fase 2: correcciones de la validación (SEC-40..45, UX-67..80)
- config.py
- FakeSMTP
- security.py
- Environment
- resources/__init__.py
- render.py
- generate
- Fase 2: plan consolidado (recuperación de contraseña, verificación de email y correo por cliente)
- test_forgot_payload_is_strict
- Fase 2: implementación del desarrollador (correo, verificación de email y recuperación de contraseña)
- docs_accounts.py
- test_user_cannot_see_email_jobs
- _alembic_config
- test_profile_updates_cannot_touch_email_fields
- test_rate_limit_on_forgot_is_audited
- add
- test_bad_tokens_get_the_same_400

## God Nodes (most connected - your core abstractions)
1. `User` - 81 edges
2. `utcnow()` - 80 edges
3. `ResourceSpec` - 63 edges
4. `task()` - 52 edges
5. `process_pending()` - 49 edges
6. `Job` - 46 edges
7. `create_user()` - 43 edges
8. `Settings` - 40 edges
9. `SpecError` - 35 edges
10. `audit()` - 33 edges

## Surprising Connections (you probably didn't know these)
- `bench_note (owned, write-heavy)` --semantically_similar_to--> `order resource (owned)`  [INFERRED] [semantically similar]
  loadtests/resources.loadtest.yaml → examples/shop.yaml
- `bench_product (read-heavy public catalog)` --semantically_similar_to--> `product resource (soft delete, rate limits)`  [INFERRED] [semantically similar]
  loadtests/resources.loadtest.yaml → examples/shop.yaml
- `_count_unverified()` --uses--> `User`  [INFERRED]
  apigen/cli.py → app/models/user.py
- `email_preview()` --uses--> `TemplateError`  [INFERRED]
  apigen/cli.py → app/email/render.py
- `environment()` --calls--> `Environment`  [INFERRED]
  apigen/codegen.py → app/core/config.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Four-round multi-agent security and usability review** — _claude_agents_security_expert_security_expert_agent, _claude_agents_developer_developer_agent, _claude_agents_user_user_agent, security_revision_seguridad_review_summary [EXTRACTED 1.00]
- **Client IP authenticity as a security control (proxy trust, lockout, rate limit)** — security_reports_ronda1_seguridad_sec_04, security_reports_ronda3_seguridad_sec_21, security_reports_ronda3_seguridad_sec_22, readme_trusted_proxies, docker_compose_backend_network, security_reports_ronda4_desarrollador_proxy_validation, security_reports_ronda2_desarrollador_t1_smart_lockout [INFERRED 0.85]
- **Concurrent refresh race: detection, grace period and client serialization** — security_reports_ronda1_seguridad_sec_01, security_reports_ronda1_usuario_ux_02, security_reports_ronda1_usuario_ux_19, security_reports_ronda2_desarrollador_t2_refresh_grace_period, guia_readme_refreshaccess, readme_refresh_token_rotation [INFERRED 0.85]

## Communities (120 total, 10 thin omitted)

### Community 0 - "ResourceSpec"
Cohesion: 0.12
Nodes (23): ensure_user_module(), hooks_module(), Path, Crea el módulo si no existe o añade al final las funciones que falten. Devuelve…, render_resource(), tasks_module(), Combinaciones válidas pero que merecen confirmación (SEC-08)., ResourceSpec (+15 more)

### Community 1 - "command"
Cohesion: 0.12
Nodes (41): createsuperuser(), db_migrate(), docs(), email_eject(), email_preview(), email_test(), _fail(), init_env() (+33 more)

### Community 2 - "test_config.py"
Cohesion: 0.09
Nodes (28): fake_project(), _prod(), fixture, parametrize, Configuración y CLI: el .env generado arranca, validaciones y utilidades., SEC-21: confiar en XFF de cualquiera permite falsificar la IP del cliente., SEC-24: un DATABASE_URL ausente no puede acabar en SQLite en silencio., UX-34: 50/hour fuera de producción (cuentas de prueba), 5/hour en producción. (+20 more)

### Community 3 - "rate_limit.py"
Cohesion: 0.13
Nodes (22): check_unrouted_limit(), enforce_rate_limits(), _evaluate_with_fallback(), ip_key(), _maybe_recover_backend(), Request, Response, Rate limiting con SlowAPI. - Clave por usuario autenticado (`user:<id>`) o, si… (+14 more)

### Community 4 - "codegen.py"
Cohesion: 0.11
Nodes (37): build_context(), build_test_context(), make_parent(), _check_router_symbols(), create_field(), _default_expr(), enum_class(), enum_members() (+29 more)

### Community 5 - "test_generator.py"
Cohesion: 0.06
Nodes (59): pluralize(), parse_field_option(), Mini-DSL de la CLI: `nombre:tipo[:opción...]`. Ejemplos:…, _action_spec(), parametrize, Tests del generador: validación de specs y seguridad del código generado., Textos hostiles del YAML acaban como literales, nunca como código., SEC-07: todo int queda acotado a 64 bits; BIGINT si no cabe en 32. (+51 more)

### Community 6 - "task"
Cohesion: 0.10
Nodes (34): echo(), prune(), Any, Tareas incluidas en la plantilla., Devuelve el payload recibido. Útil para comprobar que el worker funciona., Limpieza periódica: trabajos terminados antiguos., Any, BaseModel (+26 more)

### Community 7 - "test_auth.py"
Cohesion: 0.07
Nodes (39): lockout_minutes(), Duración del bloqueo: se dobla con cada bloqueo consecutivo, con tope., AsyncClient, client_from(), Cliente cuyas peticiones llegan desde otra IP (para simular otro origen)., SEC-41: con varios trabajos a la vez de la misma cuenta, el cupo se serializa., test_concurrent_jobs_respect_per_account_quota(), _login() (+31 more)

### Community 8 - "Send"
Cohesion: 0.13
Nodes (10): tracking_send(), _HostRejectionSend, JSONTrustedHostMiddleware, `TrustedHostMiddleware` de Starlette con el 400 en JSON y con `code` (contrato…, `send` que convierte el 400 de texto plano de Starlette en JSON., send_wrapper(), _send_413(), Receive (+2 more)

### Community 9 - "errors.py"
Cohesion: 0.13
Nodes (30): _constraint_columns(), data_error_handler(), describe_integrity_error(), http_exception_handler(), integrity_handler(), internal_error_body(), log_unhandled(), Exception (+22 more)

### Community 10 - "crud/base.py"
Cohesion: 0.10
Nodes (29): apply_on_delete(), _commit(), ensure_reference(), escape_like(), Any, AsyncSession, BaseModel, datetime (+21 more)

### Community 11 - "docs.py"
Cohesion: 0.11
Nodes (30): _call_name(), custom_errors(), _example_value(), _examples(), _field_rules(), _field_type(), _literal_text(), Path (+22 more)

### Community 12 - "schemas/user.py"
Cohesion: 0.06
Nodes (39): features(), get, Flujos de cuenta que ofrece esta API: el frontend puede mostrar u ocultar…, AccountFeatures, EmailChangeRequest, EmailRequest, _no_nul(), PasswordResetRequest (+31 more)

### Community 13 - "User"
Cohesion: 0.12
Nodes (37): AdminPrincipal, _admin_count(), _counts_as_admin(), create_user(), delete_user(), get_user(), _get_user_or_404(), list_users() (+29 more)

### Community 14 - "list_jobs"
Cohesion: 0.17
Nodes (16): alias, cancel_job(), get_job(), _get_or_404(), list_jobs(), get, max_length, PaginationDep (+8 more)

### Community 15 - "headers_for"
Cohesion: 0.09
Nodes (18): headers_for(), EMAIL_DELIVERY=inline (desarrollo): el correo sale sin worker., test_inline_delivery_runs_the_job_after_the_response(), UX-12: token caducado -> code token_expired (RFC 6750 error_description)., test_expired_token_is_distinguishable(), _only_one_active_admin(), Gestión de usuarios y control de acceso de administración., SEC-30: un admin desactivado no cuenta para el mínimo; se puede degradar y… (+10 more)

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
Nodes (35): El worker ejecuta hasta JOBS_CONCURRENCY trabajos a la vez: el cupo (contar y…, Modo optional: alguien registra el email de la víctima con un full_name de…, Comprobaciones de seguridad de la fase 2 (validación independiente del…, Registro, verificación, reset, cambio de email y avisos con DEBUG en la raíz., Réplica pequeña de ST-03 (forgot) sin rate limit: la API solo encola., Sanidad: la BD de pruebas es accesible (evita falsos positivos por fixtures)., Una cuenta pide N cambios de email: la dirección ANTIGUA recibe N avisos…, Con EMAIL_MAX_PER_HOUR=5, una sola cuenta agota el presupuesto global con… (+27 more)

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

### Community 24 - "project.py"
Cohesion: 0.11
Nodes (43): Rendered, add_version(), check_spec_sources(), default_version(), dependents(), deprecate_version(), existing_versions(), find_ruff() (+35 more)

### Community 25 - "run_loadtest.sh"
Cohesion: 0.15
Nodes (11): DATABASE_URL, DOCS_ENABLED, ENVIRONMENT, LOADTEST_PASSWORD, LOG_LEVEL, PASSWORD_HASH_CONCURRENCY, PYTHONPATH, SECRET_KEY (+3 more)

### Community 26 - "test_security.py"
Cohesion: 0.04
Nodes (40): check_json_size(), depth(), Validador para campos `json`: limita tamaño serializado y anidamiento (evita…, _claims(), _forge(), Defensas transversales: tokens, cabeceras, tamaño de body, errores y rate limit., Regresión: SlowAPIMiddleware no ve los routers incluidos en FastAPI >= 0.140., SEC-06: el 500 se genera dentro de la pila de middlewares. (+32 more)

### Community 27 - "Ronda 5: informe del usuario (revisión completa e integración con graphify)"
Cohesion: 0.29
Nodes (6): 1. Lo ya resuelto sigue bien, 2. Puntos nuevos, 3. Valoración específica de graphify, 4. Lo que me ha gustado, 5. Valoración global, Ronda 5: informe del usuario (revisión completa e integración con graphify)

### Community 28 - "test_account.py"
Cohesion: 0.07
Nodes (61): process_pending(), Procesa los trabajos listos y vuelve (útil en tests y en `apigen worker…, _login(), Flujos de cuenta: recuperación de contraseña, verificación y cambio de email.…, ST-17: el 422 de política no consume el enlace., ST-12: caducado → mismo 400 que inexistente., ST-11: dos consumos a la vez → exactamente un 204., ST-14: dos resets pedidos, uno usado → el otro no vale; cambiar la contraseña… (+53 more)

### Community 29 - "hooks/__init__.py"
Cohesion: 0.28
Nodes (6): HookContext, Any, UUID, Hooks de lógica personalizada para los recursos generados. Cada recurso tiene…, Lo que recibe cada hook: sesión de BD y quién hace la petición., Encola una tarea pesada para el worker (no bloquea la petición).

### Community 30 - "main.py"
Cohesion: 0.07
Nodes (30): APIVersion, Registro de versiones de la API. Cada versión se monta en…, BodySizeLimitMiddleware, BodyTooLarge, NullByteGuardMiddleware, HTTPException, RateLimitHeadersMiddleware, Middlewares ASGI puros (más rápidos que BaseHTTPMiddleware). (+22 more)

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

### Community 54 - "cli.py"
Cohesion: 0.12
Nodes (21): check(), _clean(), _count_unverified(), db_prune(), _email_rows(), _prune(), Exception, CLI `apigen`: genera recursos, gestiona versiones, base de datos y utilidades.… (+13 more)

### Community 55 - "test_new_api.py"
Cohesion: 0.22
Nodes (15): _git(), _load(), _new(), fixture, Path, scripts/new_api.py: solo copia lo versionado y no deja pasar secretos ni datos…, La plantilla versionada no debe disparar el escáner (falsos positivos)., UX-67: la configuración NO secreta de correo va también a `.env.example` (lo… (+7 more)

### Community 56 - "3. Hallazgos nuevos"
Cohesion: 0.12
Nodes (16): 0. Resumen, 1. Casos ST → estado → evidencia, 2. Requisitos MUST, 3. Hallazgos nuevos, 4. Veredicto, Controles verificados que funcionan (destacados), Cómo lo he verificado, Fase 2 – Validación de seguridad (correo, verificación de email y recuperación de contraseña) (+8 more)

### Community 57 - "endpoints/auth.py"
Cohesion: 0.11
Nodes (34): ErrorBody, BaseModel, Forma de las respuestas de error (para OpenAPI y clientes generados)., login(), logout(), logout_all(), BackgroundTasks, Depends (+26 more)

### Community 58 - "Ronda 7 – Informe de usuario (desarrollador que crea y entrega APIs a clientes)"
Cohesion: 0.22
Nodes (8): 0. Qué he hecho, 1. Puntos encontrados, 2. README para clientes (lo que recibe el cliente final), 3. Hooks y acciones: valoración, 4. Lo que me ha gustado, 5. Valoración, Mejoras concretas, Ronda 7 – Informe de usuario (desarrollador que crea y entrega APIs a clientes)

### Community 59 - "queue.py"
Cohesion: 0.17
Nodes (21): backoff_seconds(), cancel(), complete(), enqueue(), fail(), _json_size(), _leased(), Any (+13 more)

### Community 60 - "Job"
Cohesion: 0.18
Nodes (16): Job, JobAccepted, JobRead, BaseModel, Respuesta 202 de un endpoint con proceso en segundo plano., Devuelve a la cola los trabajos de workers caídos (arrendamiento vencido)., reclaim_stale(), _scrubbed_names() (+8 more)

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
Nodes (30): _email_hint(), reset_backend(), fake_smtp(), fixture, parametrize, Subsistema de correo: backends, SMTP, plantillas, enlaces y configuración., ST-36: sin STARTTLS anunciado se falla, no se degrada a texto plano., ST-37/42: 5xx y autenticación → permanente; 4xx y red → transitorio. Ni la… (+22 more)

### Community 82 - "api-template"
Cohesion: 0.50
Nodes (3): api-template, Cómo trabajar aquí, graphify

### Community 83 - "render"
Cohesion: 0.08
Nodes (35): environment(), base_context(), check_templates(), _environment(), _find(), _find_exact(), Any, Exception (+27 more)

### Community 84 - "test_jobs.py"
Cohesion: 0.14
Nodes (32): JobStatus, StrEnum, claim(), prune_jobs(), Reclama hasta `limit` trabajos listos y los marca como `running`. Con `job_id`,…, Borra trabajos terminados más antiguos que la retención configurada., _enqueue(), _job() (+24 more)

### Community 85 - "endpoints/account.py"
Cohesion: 0.10
Nodes (48): _already_done(), forgot_password(), BackgroundTasks, limit, post, Request, Response, SessionDep (+40 more)

### Community 86 - "backends/__init__.py"
Cohesion: 0.13
Nodes (21): DisabledBackend, EmailBackend, EmailError, PermanentEmailError, Exception, Interfaz de los backends de correo y sus errores. Los mensajes de error son…, Fallo pasajero (red, timeout, SMTP 4xx): se reintenta con el backoff de la cola., Fallo definitivo (SMTP 5xx, autenticación, destinatario rechazado): no se… (+13 more)

### Community 87 - "_send_token_email"
Cohesion: 0.18
Nodes (25): mask_email(), n***@dominio.com: para mostrar en avisos sin exponer la dirección completa., ttl(), account_exists(), _deliver(), email_change(), email_verification(), _mark_sent() (+17 more)

### Community 88 - "utcnow"
Cohesion: 0.08
Nodes (54): generate_refresh_token(), looks_like_refresh_token(), Devuelve (token_en_claro, hash). El token solo se entrega al cliente., datetime, UUID, Tipos de columna y generadores de IDs., UUID v7 (RFC 9562): ordenado en el tiempo, así los índices B-tree se mantienen…, DateTime siempre en UTC y con tzinfo, también en SQLite (que no guarda zona). (+46 more)

### Community 89 - "worker.py"
Cohesion: 0.09
Nodes (30): Any, AsyncSession, UUID, Envío de correo: API pública para el código del proyecto. from app.email import…, Encola un correo con una plantilla (de serie o de EMAIL_TEMPLATES_DIR). Con…, send_email(), decorator(), TaskDef (+22 more)

### Community 90 - "deps.py"
Cohesion: 0.08
Nodes (35): current_user(), error_responses(), get_principal(), Principal, Any, Depends, HTTPException, Request (+27 more)

### Community 91 - "mail.py"
Cohesion: 0.12
Nodes (29): EmailLog, Registro de tareas en segundo plano. Importar este paquete registra todas las…, _circuit_open(), _count_since(), EmailChangePayload, EmailPayload, _gate(), _limits() (+21 more)

### Community 92 - "EmailMessage"
Cohesion: 0.11
Nodes (22): ConsoleBackend, Backend de desarrollo: escribe el correo en el log (con el enlace en su línea)., FileBackend, Path, Backend de desarrollo: guarda cada correo como .eml (y .html) en EMAIL_FILE_DIR., _write_new(), MemoryBackend, Backend en memoria para tests: los mensajes quedan en `outbox`. (+14 more)

### Community 93 - "env.py"
Cohesion: 0.39
Nodes (7): _configure(), do_run_migrations(), Entorno de Alembic (async). La URL sale de DATABASE_URL, nunca de alembic.ini., run_async_migrations(), run_migrations_offline(), _skip_empty(), Connection

### Community 94 - "secret"
Cohesion: 0.50
Nodes (4): Genera una SECRET_KEY aleatoria., secret(), max, min

### Community 95 - "Ronda 6 — Respuesta del desarrollador"
Cohesion: 0.25
Nodes (7): 1. Tabla de decisiones, 2. UX-40: decisión sobre soft delete con hijos, 3. SEC-25 / UX-39: recomendación técnica (sin tocar `.claude/`), 4. Observaciones nuevas y pendientes, 5. Ficheros modificados, Estado final, Ronda 6 — Respuesta del desarrollador

### Community 96 - "spec.py"
Cohesion: 0.09
Nodes (23): Utilidades de nombres (singular/plural, snake_case/PascalCase)., ActionSpec, coerce_value(), load_specs(), load_specs_with_sources(), Any, field_validator, model_validator (+15 more)

### Community 97 - "call"
Cohesion: 0.11
Nodes (12): add_listener, FastHttpUser, Attacker, call(), _load_products(), Member, Pruebas de estrés con Locust. Usuarios virtuales (el peso indica la…, Tráfico hostil: aquí la respuesta "esperada" es un rechazo. (+4 more)

### Community 98 - "Ronda 8 — Respuesta del desarrollador a la ronda 7"
Cohesion: 0.25
Nodes (7): 1. Seguridad, 2. Usabilidad, 3. README para clientes (sección 2 del informe del usuario), 4. Pospuesto o rechazado (resumen), 5. Ficheros modificados, 6. Notas para la siguiente ronda, Ronda 8 — Respuesta del desarrollador a la ronda 7

### Community 99 - "logging.py"
Cohesion: 0.23
Nodes (9): _escape(), JSONFormatter, Logging estructurado con request-id propagado mediante contextvars., Escapa caracteres de control (CR/LF...): impide falsificar líneas de log con…, Formato legible para desarrollo: una línea por evento, con los campos `extra`…, _RequestIdFilter, setup_logging(), TextFormatter (+1 more)

### Community 100 - "4. Requisitos"
Cohesion: 0.11
Nodes (18): 0. Punto de partida (lo que ya existe y condiciona el diseño), 1. Superficie nueva de referencia, 2. Modelo de amenazas, 3. Decisiones de diseño recomendadas (resumen argumentado), 4.10 Registros y auditoría (G), 4.1 Tokens (T), 4.2 Enumeración y respuesta uniforme (E), 4.3 Flujos (F) (+10 more)

### Community 101 - "Fase 2: correcciones de la validación (SEC-40..45, UX-67..80)"
Cohesion: 0.25
Nodes (7): 1. Seguridad, 2. Usuario, 3. Verificación, 4. Cambios de comportamiento a tener en cuenta, 5. Pendiente o justificado, 6. Ficheros tocados en esta ronda, Fase 2: correcciones de la validación (SEC-40..45, UX-67..80)

### Community 102 - "config.py"
Cohesion: 0.15
Nodes (16): _address_problem(), _email_problems(), get_settings(), _has_control(), _is_local_host(), _link_problem(), _proxy_problems(), model_validator (+8 more)

### Community 104 - "security.py"
Cohesion: 0.12
Nodes (24): change_email(), change_password(), BackgroundTasks, limit, post, Request, Response, Pide cambiar el email. No cambia nada hasta que se confirme con el enlace que… (+16 more)

### Community 105 - "Environment"
Cohesion: 0.33
Nodes (6): Environment, StrEnum, UX-17: en desarrollo, sin CORS_ORIGINS, se admite cualquier localhost., Ronda 7: el 422 del NUL iba por fuera de CORS (el navegador veía un error de…, test_dev_cors_allows_localhost_frontends(), test_nul_422_has_cors_headers_and_right_loc()

### Community 107 - "render.py"
Cohesion: 0.14
Nodes (10): build_link(), Enlaces de los correos: SOLO desde FRONTEND_URL + EMAIL_LINK_* (REQ-L01/L02).…, format_duration(), html_to_text(), Plantillas de correo (Jinja2 en sandbox, autoescape en HTML, modo estricto).…, "30 minutes" / "30 minutos" / "48 hours" / "48 horas"., Texto plano a partir del HTML (si una plantilla propia no trae el .txt)., _TextExtractor (+2 more)

### Community 108 - "generate"
Cohesion: 0.15
Nodes (16): generate(), _migrate(), migration_tables(), Path, Genera recursos a partir de especificaciones YAML., Tablas que toca el `upgrade()` de una migración autogenerada (UX-47)., `command.revision` devuelve None, un Script o (con skip_empty) una lista., `db migrate`. Con `expected_tables` (desde `generate --migrate`) avisa si la… (+8 more)

### Community 109 - "Fase 2: plan consolidado (recuperación de contraseña, verificación de email y correo por cliente)"
Cohesion: 0.22
Nodes (8): 1. Arquitectura acordada (los tres coinciden), 2. Endpoints, 3. Decisiones sobre los puntos en desacuerdo, 4. Configuración por cliente (resumen de variables), 5. Herramientas y entrega, 6. Orden de implementación, 7. Validación final, Fase 2: plan consolidado (recuperación de contraseña, verificación de email y correo por cliente)

### Community 111 - "Fase 2: implementación del desarrollador (correo, verificación de email y recuperación de contraseña)"
Cohesion: 0.22
Nodes (8): 1. Pasos del plan (§6): cambio → ficheros → tests, 2. Requisitos MUST de seguridad (`fase2-plan-seguridad.md` §4), 3. MUST del usuario (`fase2-plan-usuario.md` §6), 4. Desviaciones del plan y motivo, 5. Instrucciones para la validación, 6. Pendiente o para decidir, 7. Ficheros, Fase 2: implementación del desarrollador (correo, verificación de email y recuperación de contraseña)

### Community 112 - "docs_accounts.py"
Cohesion: 0.23
Nodes (12): account_section(), account_settings(), mismatches(), modes(), Path, Sección del README del cliente sobre los flujos de cuenta por correo (en/es).…, Sección "Correos de cuenta" (vacía si no hay flujos activos)., `.env.example` + `.env` + variables de entorno (UX-79), solo para las claves de… (+4 more)

### Community 114 - "_alembic_config"
Cohesion: 0.20
Nodes (12): _alembic_config(), db_current(), db_downgrade(), db_history(), db_upgrade(), Aplica migraciones (por defecto hasta la última)., Revierte migraciones (por defecto la última)., Muestra la revisión aplicada. (+4 more)

### Community 118 - "add"
Cohesion: 0.33
Nodes (7): add(), Crea un recurso CRUD completo desde la línea de comandos., format_errors(), Permissions, BaseModel, RateLimits, ValidationError

### Community 122 - "test_bad_tokens_get_the_same_400"
Cohesion: 0.67
Nodes (3): parametrize, ST-13/16: forma inválida, otro propósito o tamaño enorme → mismo 400, sin 500., test_bad_tokens_get_the_same_400()

## Knowledge Gaps
- **203 isolated node(s):** `run_loadtest.sh script`, `PYTHONPATH`, `ENVIRONMENT`, `DOCS_ENABLED`, `LOG_LEVEL` (+198 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 911 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `User` connect `User` to `command`, `test_security.py`, `test_auth.py`, `test_account.py`, `headers_for`, `create_user`, `endpoints/account.py`, `cli.py`, `_send_token_email`, `utcnow`, `endpoints/auth.py`, `deps.py`, `mail.py`, `Job`, `conftest.py`?**
  _High betweenness centrality (0.078) - this node is a cross-community bridge._
- **Why does `utcnow()` connect `utcnow` to `command`, `security.py`, `queue.py`, `crud/base.py`, `render.py`, `User`, `Job`, `test_account.py`, `render`, `test_jobs.py`, `endpoints/account.py`, `cli.py`, `_send_token_email`, `create_user`, `worker.py`, `backends/__init__.py`, `mail.py`, `EmailMessage`?**
  _High betweenness centrality (0.066) - this node is a cross-community bridge._
- **Why does `task()` connect `task` to `spec.py`, `call`, `_send_token_email`, `worker.py`, `mail.py`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Are the 54 inferred relationships involving `User` (e.g. with `_count_unverified()` and `current_user()`) actually correct?**
  _`User` has 54 INFERRED edges - model-reasoned connections that need verification._
- **Are the 41 inferred relationships involving `ResourceSpec` (e.g. with `_warn_specs()` and `build_context()`) actually correct?**
  _`ResourceSpec` has 41 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `task()` (e.g. with `decorator()` and `ValueError`) actually correct?**
  _`task()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `run_loadtest.sh script`, `PYTHONPATH`, `ENVIRONMENT` to the rest of the system?**
  _203 weakly-connected nodes found - possible documentation gaps or missing edges._