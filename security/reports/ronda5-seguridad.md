# Revisión de seguridad — Ronda 5 (revisión completa guiada por el grafo de graphify)

- **Fecha:** 2026-09-25
- **Rol:** experto AppSec (defensivo), según `.claude/agents/security-expert.md`.
- **Entrada:** rondas 1–4 (`security/reports/`), `security/REVISION_SEGURIDAD.md` y el grafo `graphify-out/graph.json` (1004 nodos, 2189 aristas, generado a las 20:00:19; ningún `.py` de `app/`, `apigen/`, `tests/` ni `alembic/` es posterior).
- **Método:**
  1. Orientación con `graphify` (consultas en §2) y lectura dirigida por `source_location`.
  2. Revisión de los cambios no auditados: integración de graphify en `apigen`, hooks de `.claude/settings.json`, `.graphifyignore`, `.gitignore` y contenido versionado de `graphify-out/`.
  3. Laboratorio `./security/lab.sh 8901`: solo 127.0.0.1, modo producción, SQLite y rate limit en memoria.
- **Script nuevo:** `security/checks/ronda5_checks.py` (50 comprobaciones de extremo a extremo). Resultado: **49 OK, 0 FALLO, 1 INFO**. La INFO corresponde a SEC-30.
- **Tests:** `.venv/bin/pytest -q -p no:cacheprovider` → **133 passed**.
- **Estado final:** no he modificado `app/`, `apigen/` ni `tests/`. El servidor del laboratorio está detenido (`pkill -f "port 8901"`). En el log hay 0 `Traceback`, 0 `unhandled error` y 0 emails.
- **No verificable aquí** (igual que en rondas anteriores): PostgreSQL, Redis y Docker/compose.

---

## 1. Resumen ejecutivo

- **Nuevos hallazgos: 0 críticos, 0 altos, 0 medios, 3 bajos y 3 informativos.**
- **Controles críticos:** siguen funcionando de extremo a extremo tras las 4 rondas.
  - Autenticación, rotación de refresh y *scopes*.
  - BOLA en recursos *owned*.
  - Asignación masiva, incluidos los campos `immutable`.
  - FK hacia filas borradas lógicamente.
  - Borrado en cascada de las filas de un usuario eliminado.
  - Protección del último admin.
  - Rate limit de login.
  - Errores con `code` y cabeceras de seguridad, también en 4xx y 429.
  - `Host` no permitido y documentación oculta en producción.
- **Integración de graphify:** es segura en lo esencial.
  - El subproceso se lanza sin shell y con argumentos en lista.
  - `graphify update` solo hace extracción AST, sin LLM ni red (revisado en el código de graphify 0.9.58).
  - Los `.env` quedan excluidos por diseño de graphify.
  - Los artefactos versionados **no contienen secretos, rutas absolutas, emails, JWT ni hashes**.
- **Riesgos nuevos (de proceso y de entorno de desarrollo):**
  - Un hook versionado con una ruta absoluta del equipo del autor (SEC-25).
  - Una herramienta externa fuera del *lockfile* que `apigen` ejecuta automáticamente (SEC-26).
  - El grafo es un artefacto generado en el que el flujo de trabajo confía "primero", sin control de integridad (SEC-27).
  - **Puntos ciegos del grafo:** las plantillas Jinja, que contienen toda la autorización del código generado, y los ficheros de despliegue no están en el grafo (SEC-28).
- **Hallazgos inducidos por el grafo:**
  - El nodo central `User` llevó a revisar todas las rutas que escriben usuarios. De ahí sale **SEC-30**, reproducido: no se puede degradar ni borrar a un admin *ya desactivado* si solo queda un admin activo.
  - Siguiendo `seed.py → User`, apareció **SEC-29**: la prueba de carga respeta un `DATABASE_URL` heredado y crea un admin en esa base de datos.
- **Veredicto:** se mantiene **"Apta para producción con condiciones"** (§6). Ninguna condición nueva es bloqueante.

---

## 2. Uso de graphify: consultas y qué revelaron

| Consulta | Qué reveló | Valoración |
|---|---|---|
| Lectura de `GRAPH_REPORT.md` | Nodos centrales: `User` (48), `ResourceSpec` (44), `SpecError` (27), `Role` (26), `Settings` (21), `RefreshToken` (20). Tres hiperaristas de seguridad: IP del cliente, carrera de refresh y revisión en 4 rondas. | Útil para priorizar. Las hiperaristas coinciden con los temas de riesgo reales de las rondas 1–4. |
| `graphify path "UserRegister" "User"` | Sin camino dirigido. Con `--undirected`: `UserRegister ← endpoints/auth.py → User` (2 saltos). | El grafo modela *imports*, no flujo de datos. Para saber qué entrada llega a qué escritura hay que leer `register()` (`auth.py:45-61`). |
| `graphify explain "app_models_user_user"` | 48 conexiones. Quienes escriben `User`: `register()`, `create_user/update_user/unlock_user/delete_user`, `update_me`, `change_password`, `createsuperuser` (`apigen/cli.py:528`), **`loadtests/seed.py`** y `conftest`. | Revisé cada escritor. Salen **SEC-29** (seed) y **SEC-30** (`update_user`/`delete_user`). |
| `graphify query "which functions write or modify User role, password or is_active from HTTP input" --budget 1500` | 356 nodos (truncado a 59). Confirma `UserAdminUpdate`, `UserUpdateMe`, `PasswordChange` y `_admin_count`. | Correcto. `UserUpdateMe` solo admite `full_name` (verificado: `role` → 422). |
| `graphify path "update_user()" "_admin_count()" --undirected` | Llamada directa (1 salto). | Me llevó a revisar la condición `demoting` → SEC-30. |
| `graphify explain "app/crud/base.py"`, `explain "Repository"`, `explain "ensure_reference()"` | `Repository` solo lo importa `users.py`. **`ensure_reference()` no tiene ningún llamador en el grafo.** | **Falso "código muerto":** lo llaman los routers generados desde `apigen/templates/router.py.j2`, y el grafo no indexa `.j2` → SEC-28. |
| `graphify query "ensure_reference foreign key owner check" --budget 800` | Enlaza con `SEC-10`, `owner_filter()` y `_KeyRing`. | Mezcla nodos semánticos de los informes con código. Sirve para recordar el contexto, no como prueba. |
| `graphify path "router.py.j2" "Repository"` | Devuelve un camino desde **`app/api/v1/router.py`**. | **Coincidencia difusa silenciosa:** el nodo `.j2` no existe y graphify eligió otro sin avisar. Riesgo metodológico (SEC-28). |
| `graphify explain "app/core/config.py"` | 17 módulos importan `settings`. Ningún endpoint lo muta. | Revisé los consumidores que podrían filtrar `Settings`: `alembic/env.py:44,56` y `apigen check` (`cli.py:601,613`, que solo imprime el esquema de la URL). **Sin fugas.** |
| `graphify explain "RefreshToken"` | 20 conexiones, entre ellas `prune_refresh_tokens()` desde `start_session()`. | Revisé `auth.py:241-300`: la poda al iniciar sesión está acotada al `user_id` y conserva las familias vivas, así que no hay DoS por *flood* de login. Correcto. |
| `graphify explain "refresh_graph"` | Ambiguo (cli/project). Llamadores en `cli.py:194,227,310`. | Revisado en SEC-26. |
| "Conexiones sorprendentes" del informe | `bench_note ≈ order`, `bench_product ≈ product` (similitud semántica, INFERRED). `try_spec()`/tests → `SpecError`. | **Ruido** en lo que a seguridad respecta: son parecidos de diseño (*owned*, catálogo) y usos triviales de una excepción. No revelan acoplamientos peligrosos. |
| `manifest.json` frente a `find` | 84 ficheros indexados. **Fuera del grafo:** `apigen/templates/*.j2`, `Dockerfile`, `.dockerignore`, `alembic.ini`, `Makefile`, `.env.example`. Grafo al día (0 ficheros con *mtime* distinta). | Base de SEC-28. |

**Conclusión metodológica:**
- El grafo ahorra lectura en la capa de la app escrita a mano (auth, usuarios, configuración), donde la cobertura es completa y está al día.
- **No sirve como única guía para el código generado ni para el despliegue:** ahí están la mayor superficie de API (todos los recursos) y la autorización por objeto. Esas partes las he leído directamente (`router.py.j2` completo y `model.py.j2`).

---

## 3. Hallazgos nuevos

### SEC-25 — Hook versionado con una ruta absoluta del equipo del autor (`.claude/settings.json`)
- **Severidad:** Baja. **OWASP:** API8:2023 (configuración) / higiene de la cadena de suministro del entorno de desarrollo.
- **Evidencia:** `.claude/settings.json:9,18` → `"command": "/Users/sergionvte/.local/bin/graphify hook-guard search|read"`, en los `PreToolUse` de `Bash|Grep` y `Read|Glob`.
  - `.gitignore` no excluye `.claude/`, así que el fichero se versiona con la plantilla.
  - Es el **único** fichero del proyecto (fuera de `.venv`) que contiene el nombre de usuario local.
- **Impacto:**
  - **Divulgación menor:** nombre de la cuenta y estructura del *home*.
  - **Fallo en otros clones:** en cualquier otro equipo el hook no existe y falla en **cada** llamada a Bash, Read, Grep o Glob.
  - **Ejecución de código en cada llamada:** se ejecuta un binario externo al repositorio en cada llamada a esas herramientas. Quien controle esa ruta, o quien modifique este fichero en un PR, consigue ejecución de código en el equipo de cualquier desarrollador que use Claude Code sobre el repo (tras aceptar la confianza del *workspace*).
  - **Contexto inyectado en cada llamada:** el hook añade un texto "MANDATORY" a cada llamada. Es inocuo, pero condiciona el flujo del agente (ver SEC-27).
- **Recomendación:**
  - Mover los hooks a `.claude/settings.local.json` (no versionado; añadirlo a `.gitignore`), o invocar `graphify` por nombre (`graphify hook-guard …`) para que se resuelva por `PATH` sin rutas personales.
  - Documentar en el README que es opcional.
  - Revisar los cambios en `.claude/` como código en los PR.

### SEC-26 — `apigen` ejecuta automáticamente una herramienta externa fuera del *lockfile* (`refresh_graph`)
- **Severidad:** Info / Baja. **OWASP:** API8:2023 / A08 (integridad del software y de las dependencias).
- **Evidencia:** `apigen/project.py:305-325`, llamado desde `apigen/cli.py:53-58` tras `add`/`generate` (`:194`), `remove` (`:227`) y `version add` (`:310`).
  - El binario se resuelve con `shutil.which("graphify")` (el `PATH` del usuario) y se ejecuta con `[exe, "update", "."]`, `cwd=base` y `timeout=180`.
  - `graphifyy` no figura en `pyproject.toml` ni en `uv.lock`, así que **queda fuera de `make audit`/`pip-audit`** y de la fijación de versiones. Versión instalada: 0.9.58.
- **Controles positivos (verificados):**
  - Sin `shell=True` y con argumentos fijos.
  - Nunca rompe la CLI: captura `OSError` y `TimeoutExpired` y devuelve un mensaje.
  - Solo actúa si ya existe `graphify-out/graph.json`.
  - Se puede desactivar con `APIGEN_NO_GRAPH=1`, y `tests/conftest.py:11` lo desactiva en los tests.
  - En el código de graphify 0.9.58, `update` llama a `watch._rebuild_code` ("AST extraction … No LLM needed"): **sin LLM ni red**. Estático; no he interceptado tráfico.
  - La imagen Docker no incluye `graphify-out/` (`Dockerfile:7-12` copia de forma selectiva), así que en producción no hace nada.
- **Impacto:**
  - Un `graphify` malicioso o comprometido en el `PATH` se ejecuta en cada `apigen add` sin que el usuario lo pida explícitamente.
  - Una actualización de la herramienta con un fallo puede bloquear la CLI hasta 3 minutos.
- **Recomendación:**
  - Documentar e instalar una versión fijada: `uv tool install graphifyy==0.9.58`.
  - Opcional: incluirla como dependencia de desarrollo para que `pip-audit` la cubra.
  - Considerar que sea *opt-in* (`APIGEN_GRAPH=1` o una clave en `pyproject.toml`) en lugar de *opt-out*.
  - Reducir el `timeout` (p. ej. 60 s).

### SEC-27 — Artefactos del grafo versionados: sin secretos, pero sin control de integridad y con el mapa de riesgos aceptados
- **Severidad:** Info. **OWASP:** API8:2023 / A08.
- **Qué se versiona** (`.gitignore:32-43`): `graph.json`, `GRAPH_REPORT.md`, `manifest.json` y `.graphify_labels.json`. Se ignoran `cache/`, `graph.html`, `cost.json`, `.graphify_python` (ruta absoluta del intérprete), `.graphify_root` y la firma `.sig`.
- **Comprobación de fuga** (búsqueda con expresiones regulares sobre los 4 ficheros versionados):
  - 0 rutas absolutas (`/Users`, `/home`, `/private`), 0 JWT, 0 hashes Argon2, 0 emails y 0 `password=…`.
  - Las únicas IPs son `127.0.0.1`, `172.30.57.0` (subred fija de compose) y `172.16.0.0` (histórico de SEC-22). Son públicas en el propio repo.
  - Los *tokens* largos son identificadores de nodos.
  - `.env*` está excluido por diseño de graphify (`detect.py:_SENSITIVE_PATTERNS`, `.env`/`.pem`/`.key`/`id_rsa`/`.netrc`…), que además lee `.gitignore`.
  - `.graphifyignore` excluye `loadtests/reports/`, `graphify-out/`, `uv.lock` y `*.db`.
  - **Sin secretos.**
- **Riesgos residuales:**
  1. **Confidencialidad del diseño:** el grafo incluye nodos semánticos de los informes `security/` (SEC-01…24, T1–T6, riesgos aceptados como la enumeración en el registro o el NAT en el bloqueo inteligente). Si la plantilla se publica, el grafo y `security/` son un **catálogo de riesgos aceptados** aplicable a todos los proyectos generados. No es una vulnerabilidad en sí (transparencia), pero conviene decidirlo conscientemente.
  2. **Integridad:** `CLAUDE.md:7-11` y el hook (SEC-25) fijan "primero el grafo". Un `graph.json` desactualizado o manipulado en un PR (aristas ocultas, etiquetas engañosas) orienta mal a revisores y agentes. No hay regeneración ni comparación en CI.
- **Recomendación:**
  - En CI: `graphify update . && git diff --exit-code graphify-out/graph.json`, o dejar de versionar `graph.json` y regenerarlo en local.
  - Marcar `graphify-out/**` como `linguist-generated` y revisar sus diffs.
  - Decidir si `security/reports/` se publica con la plantilla. Si se publica, basta el resumen `REVISION_SEGURIDAD.md`.

### SEC-28 — Puntos ciegos del grafo: plantillas Jinja y ficheros de despliegue (riesgo metodológico)
- **Severidad:** Info (proceso de revisión). **OWASP:** — (ASVS V1, arquitectura y modelado de amenazas).
- **Evidencia:**
  - `manifest.json` no contiene `apigen/templates/{router,model,schemas,test}.py.j2`, `Dockerfile`, `.dockerignore`, `alembic.ini`, `Makefile` ni `.env.example`.
  - En el grafo, `ensure_reference()` tiene grado 6 y **ningún llamador**, y `Repository` solo lo importa `users.py`.
  - `graphify path "router.py.j2" "Repository"` resolvió en silencio a `app/api/v1/router.py` (coincidencia difusa). También hay avisos de "target match was ambiguous" con `User`.
- **Impacto:** toda la autorización por objeto del código generado está invisible para una revisión "primero el grafo" que siga las instrucciones de `CLAUDE.md` al pie de la letra. Esa autorización incluye `require(Access…, Scope…)`, `owner_filter()`, `_check_references`/`ensure_reference` y `scoped=` en get/patch/delete. Lo mismo pasa con el *hardening* del contenedor. Un revisor podría tomar `ensure_reference` por código muerto y "limpiarlo".
- **Recomendación:**
  - Añadir a `CLAUDE.md` una nota: "el grafo no cubre `apigen/templates/*.j2` ni Docker/Alembic; léelos directamente".
  - Opcional: indexar un proyecto generado de ejemplo (`examples/shop.yaml` generado en un directorio de muestra) para que el grafo contenga los routers reales.
  - En `path`/`explain`, usar IDs completos o rutas relativas (el grafo avisa de la ambigüedad, pero no de la sustitución difusa).
  - Añadir un comentario en `ensure_reference` indicando que lo usan los routers generados.

### SEC-29 — La prueba de carga respeta un `DATABASE_URL` heredado: migra y siembra un admin en esa base de datos
- **Severidad:** Baja (requiere un error del operador). **OWASP:** API8:2023.
- **Evidencia:**
  - `loadtests/run_loadtest.sh:44`: `export DATABASE_URL="${DATABASE_URL:-sqlite…}"`.
  - `:42`: fuerza `ENVIRONMENT=development`.
  - `:57-59`: `apigen generate loadtests/resources.loadtest.yaml`, `apigen db migrate -m loadtest` (*autogenerate* + *upgrade*) y `loadtests/seed.py`.
  - `seed.py:17-25`: crea `bench-admin@example.com` con **rol admin** y 200 usuarios con la misma contraseña (aleatoria, solo en el entorno del proceso), más 500 productos en tablas `bench_*`.
- **Impacto:** si el desarrollador tiene `DATABASE_URL` exportado (direnv, un `export` previo o una sesión conectada a *staging*), la prueba:
  - añade tablas `bench_*` y aplica una migración autogenerada contra esa base de datos, que podría incluir `drop_table` de tablas que la copia no conozca (**no verificado**, depende del estado);
  - deja un **admin persistente** con un email predecible;
  - lanza tráfico hostil (perfil `ratelimit`) contra la API local conectada a esa base de datos.
- **Recomendación:**
  - Usar una variable propia (`LOADTEST_DATABASE_URL`) y hacer `unset DATABASE_URL` por defecto.
  - Negarse si el host no es local o SQLite, salvo `LOADTEST_ALLOW_REMOTE_DB=1`.
  - Borrar las cuentas `bench-*` al terminar.

### SEC-30 — No se puede degradar ni borrar a un admin ya desactivado si solo queda un admin activo
- **Severidad:** Baja. **OWASP:** API5:2023 (autorización de funciones: gestión de privilegios). **Estado: reproducido.**
- **Evidencia:**
  - `app/api/v1/endpoints/users.py:153-155`: `demoting = …` y `if user.role == Role.admin and demoting and await _admin_count(session) <= 1: raise LAST_ADMIN`. `_admin_count` (`:142-144`) cuenta solo admins **activos**, pero la condición no comprueba si el objetivo está activo.
  - Lo mismo en `delete_user` (`:186-187`).
- **Laboratorio** (`ronda5_checks.py`):

```
POST  /api/v1/users {"email":"r5-admin2@…","role":"admin"}   -> 201
PATCH /api/v1/users/<admin2> {"is_active": false}             -> 200
PATCH /api/v1/users/<admin2> {"role": "user"}                 -> 409 {"detail":"Cannot remove the last admin","code":"last_admin"}
```

- **Impacto:** el caso típico es un admin comprometido que se desactiva. Después, el único admin activo no puede quitarle el rol ni borrarlo.
  - **Alternativa directa:** reactivarlo y luego degradarlo. Abre una ventana en la que la cuenta comprometida vuelve a ser admin activo, y la reactivación no revoca sesiones (`privilege_change` solo cuenta `is_active=False`, aunque las sesiones ya se revocaron al desactivar).
  - **Alternativa segura (no evidente):** crear antes otro admin.
  - Queda además una cuenta con rol admin latente que cualquier reactivación futura rehabilita.
- **Recomendación:**
  - Aplicar la protección solo si el objetivo **cuenta** para el mínimo: `if user.role == Role.admin and user.is_active and demoting and count <= 1`, y lo mismo en `delete_user`.
  - Añadir un test: degradar o borrar a un admin inactivo con un único admin activo → 200/204.

### Detalles menores (Info, sin ID)
- **`TrustedHostMiddleware`:** `Host` no permitido → `400 'Invalid host header'` en texto plano, sin `code`. Rompe el contrato T6 ("`code` estable en todos los errores"), aunque sin impacto de seguridad. Envolverlo o sustituirlo por una respuesta JSON `{"detail","code":"invalid_host"}`.
- **`apigen version add <new> --source <src>`:** solo valida `new` con `VERSION_NAME` (`cli.py`). `source` se usa en `api / source` (`project.py:257`) sin validar. Es una CLI local del propietario y sin impacto práctico, pero conviene aplicar el mismo patrón.
- **`.dockerignore`:** no excluye `graphify-out/`, `.claude/`, `security/` ni `tests/`. La imagen no los incluye (COPY selectivo), pero sí viajan en el *build context*. Añadirlos por higiene.
- **Auditoría:** las operaciones de administración rechazadas (409 `last_admin`, `self_delete`) y los 429 de login no generan evento `app.audit`. Conviene registrarlas: los intentos fallidos de escalada o de borrado son señal útil.

---

## 4. Controles re-verificados en el laboratorio (ronda 5)

`security/checks/ronda5_checks.py`, modo producción, 127.0.0.1:8901. Resultado: **49 OK, 0 FALLO, 1 INFO** (la INFO es SEC-30).

**Autenticación y sesiones (API2)**
- **Login fallido:** respuesta idéntica para email existente e inexistente (`401 invalid_credentials`).
- **Email en mayúsculas** (`ALICE@Example.COM`): el login funciona, porque el servidor lo normaliza (`auth.py:73`) y el registro lo pasa a minúsculas (`schemas/user.py:28-30`).
- **Refresh:**
  - Un refresh no sirve como access token (401).
  - La rotación funciona (200).
  - Reutilizar el token antiguo desde la misma IP dentro de la gracia da `409 refresh_token_rotated`, sin tokens.
- **Scopes:** un token `scope=read` no puede escribir (`403 insufficient_scope`).
- **Usuario borrado:** su access token → 401 y su refresh → `401 invalid_refresh_token`.

**Autorización por objeto y por función (API1, API3, API5)**
- **BOLA en `orders`:** bob recibe 404 en GET, PATCH y DELETE sobre el pedido de alice. Ni su listado ni el filtro `product_id` lo incluyen. El admin sí lo ve.
- **Asignación masiva:** `owner_id`, `id`, `created_at`, `deleted_at` y `role` (en `/users/me`) → 422 `extra_forbidden`.
- **Campo `immutable`** (`slug`) → 422 `immutable_field`.
- **FK obligatoria** a `null` → 422 `null_not_allowed`.
- **Campo `write_only`** (`internal_ref`): nunca se devuelve.
- **FK hacia un producto borrado lógicamente:** 422 `reference_not_found` en POST y en PATCH. El producto borrado da 404 incluso para el admin.
- **Borrado físico de una categoría con productos:** `409 has_dependents`, sin 500 ni huérfanos (`PRAGMA foreign_keys=ON`, `session.py:43`).
- **Borrado de un usuario:** sus pedidos *owned* se eliminan en cascada (`ondelete="CASCADE"`).
- **Último admin:** no se degrada ni se desactiva (409). El admin no se borra a sí mismo (409). Un usuario normal no lista usuarios (403).

**Errores y cabeceras (API8)**
- 404, 405, UUID inválido, JSON malformado y 401 sin token: todos con `code`, CSP, `nosniff`, `X-Frame-Options`, `X-Request-ID` y sin trazas.
- `Host` no permitido → 400 (ver detalle menor).
- `/docs`, `/redoc`, `/openapi.json` y `/api/v1/openapi.json` → 404 en producción.
- `/health/ready` → `{"status":"ok"}`, sin detalles internos. Sin cabecera `Server`.

**Rate limit (API4)**
- Login: `[401, 401, 401, 429, …]`. El 429 lleva `Retry-After` y las cabeceras de seguridad. El cupo llegó al límite antes por los logins previos del script, que suman 10/min por IP.

**Registros**
- Eventos `app.audit` observados: `auth.login.success/failure` (con `reason`, sin email), `auth.refresh.concurrent` y `admin.user.create/update/delete` (con `actor_id`/`target_user_id`).
- 0 emails en el log.

**Revisión estática sin cambios respecto a rondas anteriores (no repetida)**
- JWT (`alg=none`, `kid`, claves), bloqueo inteligente (T1, SEC-20), gracia desde otra IP (T2), `TRUSTED_PROXIES` (SEC-21/22), tamaño y profundidad de JSON, NUL y enteros, inyección en logs y generador (`generator_checks.py`).
- El código correspondiente no ha cambiado desde la ronda 4: 0 ficheros de `app/` posteriores al informe de la ronda 4, según `find -newer`.

---

## 5. No verificado en esta ronda
- PostgreSQL, Redis y Docker/compose (pendientes de `REVISION_SEGURIDAD.md`).
- Reutilización de refresh **desde otra IP** y bloqueo por IP desconocida. Requieren `TRUSTED_PROXIES=127.0.0.1`; verificados en la ronda 3 y sin cambios en el código.
- Si una migración autogenerada contra una base de datos ajena (SEC-29) emitiría `drop_table`: no lo he probado contra ninguna base de datos real.
- Ausencia de tráfico de red en `graphify update`: revisión estática del código de la herramienta, sin captura de red.
- El comportamiento del hook `graphify hook-guard` en otros equipos (SEC-25): deducido de la ruta absoluta, no ejecutado.

---

## 6. Veredicto actualizado

**Apta para producción con condiciones** (se mantiene). Las condiciones de las rondas 3 y 4 siguen vigentes:
- probar con PostgreSQL, Redis y Docker;
- `make audit` en CI;
- lista de contraseñas top-10k si el registro es público.

Se añaden recomendaciones **no bloqueantes**:

1. **SEC-30:** corregir la protección del último admin para que ignore a los admins inactivos. Es un cambio de una línea en dos sitios, con test.
2. **SEC-25:** sacar el hook con la ruta absoluta del fichero versionado (`.claude/settings.local.json` o `graphify` por `PATH`).
3. **SEC-29:** aislar la base de datos de la prueba de carga (`LOADTEST_DATABASE_URL`, rechazar hosts remotos).
4. **SEC-26/27/28:** fijar la versión de graphify, hacerla *opt-in* o auditable, verificar `graph.json` en CI y documentar los puntos ciegos del grafo (plantillas y despliegue) en `CLAUDE.md`.

Balance acumulado: **0 hallazgos críticos, altos o medios abiertos**. Los controles críticos se han vuelto a verificar de extremo a extremo tras las 4 rondas, sin regresiones.
