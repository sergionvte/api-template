# Revisión de seguridad — Ronda 7 (cola de trabajos, acciones generadas y herramientas para clientes)

- **Fecha:** 2026-09-26
- **Alcance:** lo nuevo desde la ronda 6. Incluye la cola de trabajos (`app/models/job.py`, `app/tasks/*`, `app/api/v1/endpoints/jobs.py`), los hooks y las acciones generadas (`app/hooks/__init__.py`, `apigen/templates/router.py.j2`, `apigen/spec.py::ActionSpec`, `apigen/codegen.py::{hooks_module,tasks_module,ensure_user_module}`), `NullByteGuardMiddleware`, `scripts/new_api.py`, `apigen/docs.py`, `docker-compose.yml` y el `Dockerfile`.
- **Restricción:** no he modificado `app/`, `apigen/`, `scripts/` ni `tests/`, y no he hecho commits. Las pruebas que alteran código (PoC de generación, tareas del laboratorio, `new_api.py` con ficheros plantados) se hicieron en copias temporales del *scratchpad*.
- **Scripts nuevos** (en `security/checks/`):

| Script | Qué comprueba | Resultado |
|---|---|---|
| `ronda7_checks.py` | HTTP contra el laboratorio | **31 OK, 0 FALLO, 1 INFO**. Con worker (`WAIT_WORKER=1`), además, `export_invoice` y `reindex` terminan en `succeeded` (visto en el log del worker). |
| `ronda7_worker_checks.py` + `ronda7_worker.py` + `ronda7_lab_tasks.py` | El lado del worker, con tareas de laboratorio | **6 OK, 2 FALLO, 3 INFO** → SEC-33, SEC-34 y SEC-36 |
| `ronda7_generator_checks.py` | Generador, solo en memoria | **18 OK, 9 FALLO, 3 INFO** → SEC-31, SEC-32 y SEC-38 |
| `ronda7_docker_checks.py` | `docker compose -p apisec` (PostgreSQL + Redis + worker) | **12 OK, 0 FALLO** |

---

## 1. Resumen ejecutivo

**Lo que funciona bien:**
- **Aislamiento de `/jobs`:** los trabajos ajenos devuelven 404 en lectura y cancelación, y el admin ve todos. `JobRead` no expone `payload`, `owner_id` ni `locked_by`.
- **Límites y mensajes de error:** están el límite de payload (413) y el truncado del resultado. Los errores internos se muestran como `"Task failed"`, sin el mensaje: se probó con una excepción que contenía una cadena de conexión con contraseña.
- **Acciones generadas con la configuración por defecto:** son correctas. La acción *item* de un recurso *owned* hereda `owner`, el `item_id` del cuerpo se rechaza, rigen `extra=forbid` y el NUL en el JSON, un token `scope=read` recibe 403 y el rate limit por acción funciona.
- **Tareas en segundo plano públicas:** se rechazan también cuando el `public` es heredado.
- **Stubs de hooks y tareas:** no admiten inyección de código desde el YAML. El `"""` en la descripción se neutraliza y los nombres pasan por `IDENT`.
- **`NullByteGuardMiddleware`:** devuelve 422 en query y ruta, también con PostgreSQL, conserva las cabeceras de seguridad y el 400 de `Host` sigue teniendo prioridad.
- **`apigen/docs.py`:** solo lee `.env.example` y no expone secretos.

**Lo nuevo y relevante:**

| ID | Severidad | Resumen |
|---|---|---|
| **SEC-31** | Media | Una acción llamada `read`, `list`, `create`, `update` o `delete` **redefine el alias de permisos del CRUD** (`CanRead`…). Así se abre, por ejemplo, `GET /documents/{id}` (`read: admin`) a cualquier usuario. Reproducido de extremo a extremo, y los tests generados siguen en verde. |
| **SEC-32** | Media | En un recurso *owned*, una acción *item* con `permission: user` se genera con `scoped=False` (BOLA). El generador rechaza `update/delete=user` en *owned*, pero esto lo acepta sin aviso. Reproducido: Bob exporta la factura de Alice y ve el resultado. |
| **SEC-33** | Media | Los executors `process` y `thread` **no detienen la tarea al vencer el timeout**. Los procesos y hilos siguen corriendo, el reintento duplica la ejecución y el pool de procesos queda ocupado: una tarea trivial falla con `Timed out`. Reproducido. |
| **SEC-35** | Media | `scripts/new_api.py` copia al repo del cliente los ficheros **no versionados y no ignorados**, y hace commit. Reproducido con una clave SSH, un dump `.sqlite3`, notas con una clave `sk_live` y el código y las migraciones de otro cliente. El control de datos personales no revisa `.env.example`, no busca secretos y se ejecuta antes de generar el README y el grafo. |
| SEC-34 | Baja | Carrera en `JOBS_MAX_PENDING_PER_USER`: 40 encolados concurrentes → 31 aceptados en SQLite y 30 en PostgreSQL (límite 20). |
| SEC-36 | Baja | El latido del worker usa un nombre fijo en el directorio temporal y **sigue enlaces simbólicos**: sobrescribió el destino de un symlink. |
| SEC-37 | Baja | `complete()` y `fail()` no comprueban el arrendamiento (`locked_by`/`running`). Solo revisión de código. |
| SEC-38 | Baja | El worker exige y recibe `SECRET_KEY`, la clave que firma los JWT, aunque no la necesita. Tampoco se validan los nombres de campo de las acciones (`model_*`). |
| SEC-39 | Info | El healthcheck del worker da "healthy" con la BD caída (reproducido en Docker) y el worker escribe una traza por segundo. |
| — | Info | Otros detalles (§3.10): el Dockerfile de los proyectos creados con `new_api.py` no construye, el 422 de NUL no lleva CORS, etc. |

**Veredicto:** **"Apta para producción con condiciones"** (§6), con condiciones nuevas:
- corregir SEC-31 y SEC-32 **antes de generar APIs de clientes con acciones**;
- corregir SEC-33 antes de usar `executor: process/thread` con entradas de usuario;
- corregir SEC-35 antes de usar `new_api.py` para entregas.

---

## 2. Uso de graphify: consultas y qué revelaron

| Consulta | Resultado | Uso |
|---|---|---|
| `graphify query "background job queue claim lease worker retry cancel owner" --budget 1500` | `claim()` L93, `cancel()` L205, `Worker` L100, `run_job()` L43, `reclaim_stale()` L176, `complete()`/`fail()`, `_get_or_404()` de jobs, `HookContext.enqueue()`… | Mapa de la cola. Leí completos `queue.py`, `worker.py`, `jobs.py`, `job.py` y `registry.py` (son cortos). |
| `graphify explain "claim_next"` | Sin nodo | El nombre real es `claim()`. |
| `graphify query "ActionSpec action validation background executor permission rate input fields" --budget 800` | `ActionSpec` en `spec.py` L302, `._rate()`, `StrictInput` | Lectura de `spec.py:302-356` y de los valores por defecto en `ResourceSpec._check` (`spec.py:470-482`). |
| `graphify query "codegen hooks_module tasks_module ensure_user_module action context scoped task name" --budget 800` | `hooks_module()` L668, `tasks_module()` L716, `ensure_user_module()` L785 | Lectura de `codegen.py:430-460` y `660-808`. Salen **SEC-31/32** (el alias y `scoped` se deciden aquí y en la plantilla). |
| `graphify explain "NullByteGuardMiddleware"` | `middleware.py` L203; usado en `create_app()` `main.py` L151 | Posición en la pila (§3.10). |
| `graphify query "apigen docs README generation client settings environment variables" --budget 600` | `write_readme()` `docs.py` L573 | Revisión de `read_env_example()` y `render_docs()`. |
| `graphify query "jobs router included in api version router" --budget 400` | `app/api/v1/router.py` | `/jobs` solo se monta en los routers de versión (§3.10). |
| `graphify explain "test_scoped_read_only_token()"` | `tests/test_auth.py` L316 | Cómo pedir `scope=read` para probar 403 en acciones y cancelación. |
| `graphify explain "prune_jobs()"` | La llaman `apigen db prune` (`cli.py:540-544`) y `system.prune` | La retención de `jobs` (payload con datos de usuario) entra en la limpieza diaria documentada. |

**Puntos ciegos (SEC-28, siguen vigentes):**
- `router.py.j2`, `Dockerfile` y `docker-compose.yml` no están en el grafo: los leí directamente.
- **SEC-31 solo se ve en la plantilla.** El grafo no puede relacionar el nombre de una acción con `CanRead`.

---

## 3. Hallazgos nuevos

### SEC-31 — Una acción con nombre de operación CRUD redefine el alias de permisos (escalada de privilegios en el código generado)

- **Severidad:** Media · **OWASP:** API5:2023 *Broken Function Level Authorization*.
- **Descripción:**
  - `router.py.j2:60-64` define `CanList`, `CanRead`, `CanCreate`, `CanUpdate` y `CanDelete`. Después, `router.py.j2:65-67` define un alias por acción, `{{ a.alias }}`, con `alias = f"Can{pascal(a.name)}"` (`codegen.py:438`).
  - `ActionSpec._name` (`spec.py:326-334`) no reserva `list`, `read`, `create`, `update` ni `delete` (`RESERVED_ACTIONS`, `spec.py:293-296`).
  - Así, una acción `read` genera una **segunda** asignación, `CanRead = …require(Access.<permiso de la acción>, Scope.write)`. Esa asignación se ejecuta antes de declarar los endpoints, así que `GET /{id}` usa el permiso de la acción.
  - `read` es un nombre natural para "marcar como leído".
- **Evidencia:**
  - `ronda7_generator_checks.py`: FALLO en las 5 variantes. Por ejemplo:
    `CanRead = …require(Access.admin, Scope.read)` | `CanRead = …require(Access.user, Scope.write)`.
  - De extremo a extremo, en una copia temporal con `document` (`list/read/create/update/delete: admin`) y la acción `read` con `permission: user`: `GET /api/v1/documents` como usuario → **403**, pero `GET /api/v1/documents/{id}` → **200** con `"Plan confidencial"`.
  - Los 17 tests generados para esos recursos **pasan**: no lo detectan.
- **Impacto:**
  - Cualquier usuario lee, crea, modifica o borra en recursos restringidos, según el nombre de la acción.
  - Con permisos más estrictos en la acción, el efecto es el contrario: el CRUD queda roto o exige `Scope.write` para leer.
- **Recomendación:**
  1. Añadir `list`, `read`, `create`, `update`, `delete` y `get` a `RESERVED_ACTIONS`, o mejor:
  2. Generar alias sin colisión posible, por ejemplo `CanAction{Pascal}` o `_perm_<accion>`, y comprobar en `build_context` que no hay alias duplicados.
  3. Añadir un test del generador que renderice una acción `read` y compruebe que `CanRead` se define una sola vez.

### SEC-32 — Acción *item* con `permission: user` en un recurso *owned*: BOLA aceptado sin aviso

- **Severidad:** Media · **OWASP:** API1:2023 *Broken Object Level Authorization*.
- **Descripción:**
  - En la plantilla, `scoped` es `a.permission == "owner"` (`codegen.py:456`, `router.py.j2:295`).
  - Con `permission: user`, `_get_or_404(..., scoped=False)` carga la fila de cualquier propietario.
  - `ResourceSpec._check` rechaza `update/delete='user'` en *owned* precisamente por esto (`spec.py:438-442`). Para las acciones no hay ni error ni aviso en `warnings()` (`spec.py:470-482`).
  - En las acciones en segundo plano el resultado es peor:
    - el trabajo queda a nombre del **atacante** (`owner_id=principal.user_id`, `router.py.j2:310`), que puede consultarlo;
    - el stub de la tarea hace `session.get(Model, item_id)` sin comprobar el dueño (`codegen.py:748-756`).
- **Evidencia (de extremo a extremo, copia temporal, `invoice` owned + `export` background `permission: user`):**
  - Bob hace `GET /invoices/{id de Alice}` → 404.
  - `POST /invoices/{id de Alice}/export` → **202**.
  - Tras `process_pending()`, Bob hace `GET status_url` → `succeeded` con el `result` de la factura de Alice.
  - `ronda7_generator_checks.py`: "owned + acción item con permission=user … aceptada=True avisos=[]".
- **Recomendación:**
  - En un recurso *owned*, que las acciones *item* con `user` sean error, igual que `update/delete`, o que exijan un flag explícito (`shared: true`) acompañado de aviso.
  - Además, que `scoped` sea `True` salvo para `admin`.
  - En el stub de la tarea: filtrar por `ctx.owner_id` cuando el modelo tiene `owner_id` (y respetar `deleted_at`), como defensa en profundidad.

### SEC-33 — Los executors `process`/`thread` no se detienen al vencer el timeout: procesos fuera de control, ejecución duplicada y agotamiento del pool

- **Severidad:** Media · **OWASP:** API4:2023 *Unrestricted Resource Consumption*.
- **Descripción:**
  - `worker.py:60-67`: `asyncio.wait_for` cancela la espera, pero:
    - `loop.run_in_executor(_pool(), …)` no puede interrumpir un proceso del `ProcessPoolExecutor`;
    - `anyio.to_thread.run_sync(..., abandon_on_cancel=True)` abandona el hilo, que sigue ejecutándose.
  - `TimeoutError` se reintenta siempre (`worker.py:69-71`), así que el reintento corre **a la vez** que la ejecución anterior.
  - El pool tiene `JOBS_PROCESS_WORKERS=2` y la concurrencia es 4. El timeout cuenta también el tiempo de espera en la cola del pool.
- **Evidencia (`ronda7_worker_checks.py`, laboratorio en macOS con `spawn`):**
  - Dos `lab7.slowproc` (sleep 12 s, timeout 2 s) → `failed 'Timed out after 2s'`. **Aun así, los dos procesos escribieron su marca al terminar** (`slowproc-a.done`, `slowproc-b.done`).
  - `lab7.fastproc` (devuelve al instante, timeout 5 s), encolado después → **`failed 'Timed out after 5s'`**: el pool estaba ocupado por procesos "vencidos".
  - `lab7.slowthread` (timeout 2 s, `max_attempts=2`, sleep 14 s) → `failed`, intentos=2, **2 marcas**: los dos intentos se ejecutaron hasta el final.
- **Impacto:**
  - Una entrada que haga colgar una tarea de CPU (PDF o imagen maliciosos, *regex* catastrófica…), que es justo el caso de uso de `process`, inutiliza **todas** las tareas `process` del worker hasta reiniciarlo.
  - Mientras tanto el latido sigue diciendo "healthy" (SEC-39).
  - En `thread` se acumulan hilos y los efectos secundarios se duplican (emails, cobros externos).
- **Recomendación:**
  1. Para `process`, un proceso por trabajo (`multiprocessing.Process`/`spawn`, con `terminate()`/`kill()` al vencer), o reciclar el pool (`shutdown(cancel_futures=True)` y recrearlo) cuando un trabajo vence.
  2. Contar el timeout desde que la tarea empieza a ejecutarse, o limitar los `process` reclamados al tamaño del pool.
  3. Para `thread`, documentar que no se puede interrumpir, no reintentar por timeout por defecto (`retry` configurable por tarea) y exigir idempotencia.
  4. Test: tarea `process` que duerme más que su timeout, seguida de una rápida que debe terminar en `succeeded`.

### SEC-34 — Carrera en el límite de trabajos pendientes por usuario

- **Severidad:** Baja · **OWASP:** API4:2023.
- **Descripción:** `enqueue()` cuenta los pendientes y después inserta (`queue.py:59-89`), sin bloqueo ni restricción en la BD (TOCTOU).
- **Evidencia:** 40 `enqueue` concurrentes para un usuario sin pendientes:
  - **SQLite:** 31 aceptados y 9 con 429;
  - **PostgreSQL (Docker, dentro del contenedor del worker):** **30 aceptados** y 10 con 429.
  - El límite es 20. En secuencia, el 429 funciona.
- **Impacto:** limitado. Por HTTP lo frena el rate limit de la acción (`export_invoice` 10/min: se observó 429 en la petición 10), pero una acción *sin* `rate_limit` solo tiene el límite por defecto (120/min) y admite ráfagas.
- **Recomendación:**
  - En PostgreSQL, `pg_advisory_xact_lock(hash(owner_id))` o `SELECT … FOR UPDATE` sobre la fila del usuario antes de contar.
  - En SQLite, `BEGIN IMMEDIATE`.
  - Alternativa: aceptar el exceso y documentarlo. Recomendar también `rate_limit` en toda acción `background` (aviso en `warnings()` si falta).

### SEC-35 — `scripts/new_api.py` puede filtrar secretos y código de otros clientes al repo del cliente

- **Severidad:** Media · **OWASP:** API8:2023 *Security Misconfiguration* (ASVS V14.1, V8.3).
- **Descripción:**
  - `tracked_files()` usa `git ls-files --cached --others --exclude-standard` (`new_api.py:75-84`), así que copia cualquier fichero no versionado y no ignorado del directorio de la plantilla. Después hace `git add -A` y commit (`new_api.py:239-245`).
  - `.gitignore` no cubre `*.key`, `*_key`, `*.sqlite*`, `*.sql`, `*.p12`, `credentials*.json` ni notas sueltas.
  - Copia también el estado de trabajo de los ficheros versionados, por ejemplo `app/api/v1/router.py` con los routers de otro cliente registrados.
  - El control de datos personales (`new_api.py:186-195`):
    1. no revisa `.env.example`: su sufijo `.example` no está en `TEXT_SUFFIXES` (`new_api.py:52-55`);
    2. solo reconoce `/Users/…`, `/home/…` y 5 dominios de email personales;
    3. no busca secretos;
    4. se ejecuta **antes** de `init-env`, `apigen docs` y `graphify update`, cuyos resultados también se versionan.
  - Además, copia `user.name`/`user.email` de la plantilla como identidad del commit (`new_api.py:229-238`). Probablemente es intencionado, pero no se avisa.
- **Evidencia:** copia temporal de la plantilla con ficheros plantados, `python3 scripts/new_api.py demo-api --no-install --no-git`:
  - Terminó con éxito y el proyecto nuevo contiene **`deploy_key`** (clave OpenSSH), **`backup.sqlite3`**, **`notas-cliente-acme.txt`** (`STRIPE_KEY=sk_live_…`), `r7.yaml`, `app/models/document.py`, `app/hooks/invoice.py`, la migración `…_add_document_invoice.py`, `tests/api/v1/test_documents.py` y `app/api/v1/router.py` con `documents`/`invoices` registrados.
  - `.env.example:132-133` conserva `juan.perez@acme-cliente.es` y **`/Users/sergionvte/Developer/x`**. El control no lo detectó.
  - Hoy el directorio real de la plantilla está limpio: solo `apigen/docs.py`, `scripts/` y los scripts de `security/checks/`, que están excluidos. El riesgo aparece cuando se experimenta en la plantilla (por ejemplo, `apigen generate examples/shop.yaml`).
- **Recomendación:**
  1. Copiar solo `git ls-files --cached` y exigir un árbol limpio (`git status --porcelain` vacío salvo `--allow-dirty`). O usar una lista blanca de rutas.
  2. Revisar **todos** los ficheros de texto (sin filtrar por sufijo) **después** de generar README, `.env` (excluido) y grafo, justo antes del commit. Añadir patrones de secretos (`-----BEGIN .* PRIVATE KEY-----`, `sk_live_`, `AKIA…`, `SECRET_KEY=` con valor…) y cualquier email que no sea `@example.com`.
  3. Negarse si en `resources/`, `app/models/` o `alembic/versions/` hay ficheros distintos de los de la plantilla.
  4. Añadir a `.gitignore`: `*.key`, `*.sqlite*`, `*.sql`, `*.dump`, `*.p12`, `credentials*.json`.

### SEC-36 — Latido del worker con nombre predecible en el directorio temporal y siguiendo enlaces simbólicos

- **Severidad:** Baja · **OWASP:** API8:2023 (CWE-59/CWE-377).
- **Descripción:**
  - `HEARTBEAT_FILE = os.path.join(tempfile.gettempdir(), "apigen-worker.heartbeat")` (`worker.py:33`).
  - Se escribe con `open(..., "w")` (`worker.py:151-156`), que sigue enlaces simbólicos y trunca el destino.
  - En un Linux con `/tmp` compartido (worker fuera de Docker), otro usuario local puede:
    - preparar un symlink hacia un fichero que el usuario del worker pueda escribir, aunque `fs.protected_symlinks=1`, habitual en las distribuciones, lo mitiga;
    - crear el fichero antes para falsear o romper el healthcheck.
  - Varios workers en el mismo host comparten el fichero.
- **Evidencia:** con `TMPDIR` apuntando a un directorio del laboratorio y `apigen-worker.heartbeat → victim.txt` (contenido `CONTENIDO-ORIGINAL`), el worker dejó en `victim.txt` su PID (`'8385'`).
- **Contexto que lo mitiga:**
  - en Docker, `/tmp` es un tmpfs privado (`rw,nosuid,nodev,noexec`, fichero `app:app`, verificado);
  - en macOS, `TMPDIR` es por usuario.
- **Recomendación:**
  - Ruta configurable (`JOBS_HEARTBEAT_FILE`) dentro de un directorio propio del proceso, `0700`, por ejemplo `$XDG_RUNTIME_DIR` o `/app/run` en la imagen.
  - Escribir con `os.open(path, O_WRONLY|O_CREAT|O_TRUNC|O_NOFOLLOW, 0o600)` o sustituir con `os.replace` sobre un temporal creado con `mkstemp`.
  - Incluir `worker_id` en el nombre si hay varios workers.

### SEC-37 — `complete()`/`fail()` no verifican que el worker siga siendo dueño del arrendamiento

- **Severidad:** Baja · **OWASP:** API4:2023 / integridad de estado. **No reproducido; solo revisión de código.**
- **Descripción:**
  - `complete()` hace `UPDATE … WHERE id=:id` (`queue.py:136-147`) y `fail()` igual (`queue.py:171`), sin `AND status='running' AND locked_by=:worker_id`.
  - Si `reclaim_stale()` (de otro worker) devuelve a la cola un trabajo cuyo worker original sigue vivo (bucle de eventos bloqueado por una tarea `async` que hace CPU, pausa larga de la VM…), los dos lo ejecutan. El último en terminar sobrescribe el estado.
  - Además, un `fail(retry=True)` tardío puede volver a poner en `queued` un trabajo que otro worker ya completó.
- **Recomendación:**
  - Pasar `worker_id` a `complete`/`fail` y condicionar el `UPDATE`. Si no afecta a ninguna fila, registrar un aviso "lease lost".
  - Opcional: renovar `locked_until` periódicamente en trabajos largos.

### SEC-38 — Mínimo privilegio del worker y validación incompleta de `ActionSpec`

- **Severidad:** Baja · **OWASP:** API8:2023.
- **Worker con `SECRET_KEY`:**
  - Sin `SECRET_KEY`, el worker no arranca en producción: `Configuración insegura: SECRET_KEY debe tener al menos 32 caracteres` (reproducido en el laboratorio; `config.py:223-231`).
  - En compose recibe todo el `.env` (`docker-compose.yml:39`). Dentro del contenedor hay 2 variables `SECRET_KEY*`.
  - Es justo el proceso que procesa entradas de usuario de riesgo (PDFs, imágenes). Si se compromete, se pueden **forjar JWT de admin**.
  - **Recomendación:** un perfil de configuración `worker` que no exija ni cargue `SECRET_KEY`/`JWT_PREVIOUS_SECRET_KEYS`, y en compose un `env_file` o `environment` mínimo para el worker (BD y `JOBS_*`). Sobran también `TRUSTED_PROXIES` y `RATE_LIMIT_STORAGE_URI`.
- **Campos de acción:**
  - `ActionSpec._check` (`spec.py:343-345`) no aplica `RESERVED_FIELDS` ni el prefijo `model_`, a diferencia de `ResourceSpec` (`spec.py:408-415`).
  - `model_config`, `model_dump` y `model_fields` se aceptan (FALLO en `ronda7_generator_checks.py`). El resultado es un esquema que no importa o que rompe `payload.model_dump(mode="json")` con un 500.
  - **Recomendación:** reutilizar la misma validación que en los campos del recurso.
- **Descripción con escapes:**
  - `\N` o `\x4` en la `description` de una acción en segundo plano generan un stub de tareas **que no compila** (`SyntaxError: malformed \N character escape`, `codegen.py:733`).
  - No es inyección: `"""` se neutraliza y el router usa `repr`.
  - **Recomendación:** docstring *raw* (`r"""`), o escapar `\` además de `"""`.

### SEC-39 — El healthcheck del worker no refleja si procesa trabajos (Info)

- **Severidad:** Info · **OWASP:** API8/API9 (observabilidad).
- **Evidencia (Docker):**
  - `docker compose stop db` y 75 s después: `apisec-worker-1 healthy fails=0`.
  - La API da `/health/ready` → 503, como corresponde.
  - En 80 s, el worker escribió **77** `worker loop error` con traza completa (`worker.py:159-165`, una por `JOBS_POLL_INTERVAL`).
  - Al volver la BD, se recupera solo (verificado).
- **Contexto:**
  - El latido solo prueba que el bucle de eventos vive. Tampoco refleja SEC-33 (pool agotado).
  - En compose sin orquestador, `unhealthy` no reinicia el contenedor.
- **Recomendación:**
  - Escribir el latido solo tras un `claim()` o un `SELECT 1` correctos, y marcar el worker como no sano tras N errores seguidos.
  - Limitar la frecuencia de las trazas repetidas (espera exponencial en el bucle ante errores de BD).
  - Documentar que el healthcheck no reinicia el contenedor.

### 3.10 Detalles menores (Info, sin ID)

- **Proyectos creados con `new_api.py` y el Dockerfile:**
  - `new_api.py` excluye `README.txt`, pero el `Dockerfile:7` hace `COPY pyproject.toml uv.lock README.txt ./`, así que `docker compose up --build` fallará en el proyecto del cliente.
  - Tampoco se copia `README.md`, que `pyproject` exige como `readme` para instalar el proyecto.
  - Afecta a la disponibilidad del despliegue del cliente. Verificado estáticamente en el proyecto `demo-api` generado.
- **NullByteGuard:**
  - Está *fuera* de `CORSMiddleware` (`main.py:150-151`): su 422 no lleva cabeceras CORS y el navegador lo verá como un error de red opaco.
  - El 422 dice `loc: ["query"]` también cuando el NUL está en la ruta.
  - Por lo demás, bien situado: dentro de `SecurityHeaders` y `TrustedHost`.
- **Acciones síncronas:**
  - Devuelven `dict[str, Any]` sin `response_model` (`router.py.j2:293`). Si el desarrollador devuelve `obj.model_dump()`, se filtran los campos `write_only`, como `internal_ref` o `private_notes`.
  - Recomendado: documentarlo en el stub, o `response_model` opcional por acción.
- **Acción síncrona de colección sin permiso explícito:** hereda `public` de `create: public` sin aviso (INFO en el script). Añadirlo a `warnings()`.
- **`HookContext.enqueue(..., owner_id=None)`** (`hooks/__init__.py:35`): encolar sin dueño se salta el límite de pendientes. Documentarlo.
- **Stub de tarea:** usa `session.get()`, que ignora `deleted_at`, así que un trabajo encolado antes del borrado lógico se procesa igualmente.
- **`status_url`** usa la versión del router del recurso (`router.py.j2:312`). Es correcto mientras `/jobs` exista en todas las versiones activas (`add_version` copia el router de v1).
- **`JobRead.error`:** los `TaskError` muestran su mensaje al cliente, que es lo documentado. El `logger.info("job failed: %s", exc)` va por el formateador de logs ya verificado frente a inyección en rondas previas.

---

## 4. Controles verificados

**Laboratorio** (producción, SQLite, 127.0.0.1:8901, `ronda7_checks.py` + worker):

| Control | Resultado |
|---|---|
| `export_invoice` propio: 202, `Location: /api/v1/jobs/{id}` y `status_url` | OK |
| `export_invoice` y `summary` sobre un pedido ajeno | 404 (sin revelar que existe) |
| `item_id` en el cuerpo de la acción | 422 `extra_forbidden` (`spec.py:344` reserva el nombre) |
| `max_length` y NUL en el JSON de la acción | 422 |
| Token `scope=read` al lanzar una acción o cancelar | 403 `insufficient_scope`. Sin token: 401 |
| `reindex` (admin) como usuario / como admin | 403 / 202 |
| `/jobs/{ajeno}` (GET y cancel) | 404. El listado de un usuario solo contiene lo suyo; el admin ve todo |
| Campos de `JobRead` | Solo `id, name, status, attempts, max_attempts, result, error, created_at, run_after, started_at, finished_at` |
| Filtros de `/jobs` | `status` inválido → 422; `limit=10000` → 422; `name` > 100 → 422 |
| Cancelación | Trabajo en cola → 200 `cancelled`; segunda vez → 409 `job_not_cancellable` |
| Rate limit por acción (10/minute) | 429 con `Retry-After` y `code=rate_limited`. Los 422 de validación no consumen cupo; el 404 sí |
| Errores de tareas | Excepción interna → `"Task failed"`, sin el secreto del mensaje. `TaskError` → mensaje visible, 1 intento |
| Límites de tamaño | Resultado > 256 KB → `{"truncated": true}`; payload > 64 KB → 413 `job_payload_too_large`; límite secuencial de pendientes → 429 `too_many_pending_jobs` |
| Borrado de usuario | Sus trabajos se borran en cascada (40 → 0, SQLite con FK activas) |
| NullByteGuard | 422 con CSP, `nosniff` y `X-Request-ID` para `?q=%00`, `?status=%00draft`, `/products/%00` y `/jobs/%00`; `%2500` → 200; `Host` no permitido + NUL → 400 `invalid_host` |

**Generador** (`ronda7_generator_checks.py`):
- La acción *item* de un recurso *owned* hereda `owner`.
- Una acción en segundo plano que heredaría `public` se rechaza.
- Nombres de acción peligrosos (`__init__`, `os.system`, `task`, `before_create`, `model_x`, `import`, mayúsculas) → rechazados.
- Descripción con `"""` + código, comillas mixtas o barra final → sin inyección en los stubs. El router usa `repr` y compila siempre.
- `ensure_user_module` nunca reescribe el código existente y devuelve `unparseable` sin tocar nada.

**Docker** (`docker compose -p apisec`, PostgreSQL 17, Redis, `ronda7_docker_checks.py`):

| Control | Resultado |
|---|---|
| Arranque | `worker` con `depends_on: api healthy` y healthcheck por latido en `healthy` |
| Contenedor del worker | Usuario `app` (uid 999), `/tmp` en tmpfs `noexec` |
| `certificate` (async) y `reindex` (process, Linux `fork`, Python 3.13) | `succeeded`, sin avisos de *fork* en el log |
| Aislamiento de trabajos | Trabajo ajeno → 404 |
| NUL con PostgreSQL | 422 en query, ruta y `/jobs?name=%00` (antes daba 500 con PostgreSQL) |
| Recuperación | El worker se recupera tras reiniciar `db` |
| Limpieza | `docker compose -p apisec down -v` e imágenes eliminadas |

**Sin regresiones observadas** en autenticación, rate limit, cabeceras ni `TrustedHost` durante las pruebas.

## 5. No verificado en esta ronda

- SEC-37 (arrendamiento perdido y doble `complete`): solo revisión de código.
- Reclamo con varios workers a la vez en PostgreSQL (`--scale worker=3`, `SKIP LOCKED`).
- Parada con `SIGTERM` dentro de `JOBS_SHUTDOWN_GRACE` y devolución a la cola al vencer el arrendamiento de un worker matado.
- Seguridad de `fork` con asyncpg bajo carga: solo se probó una tarea `process` trivial.
- Límites por acción compartidos en Redis entre varias réplicas de la API.
- `TRUSTED_PROXIES` del compose: no se ha vuelto a probar (verificado en rondas 3 y 4). Al worker no le afecta.
- El comportamiento de SEC-36 en un Linux con `/tmp` compartido: se reprodujo con un `TMPDIR` de laboratorio en macOS.
- `new_api.py` con `uv` y tests (`--no-install` en la prueba) y el `docker build` real del proyecto generado (§3.10): comprobado solo de forma estática.

## 6. Veredicto actualizado

**Apta para producción con condiciones.**
- **Siguen vigentes** las condiciones anteriores: probar Redis y réplicas, `make audit` en CI y la lista de contraseñas top-10k si el registro es público. PostgreSQL y Docker quedan cubiertos en parte con esta ronda.
- **Nuevas condiciones:**
  1. **SEC-31 y SEC-32** (generador): corregirlas **antes de generar APIs de clientes con `actions`**. Son cambios pequeños en `spec.py`/`codegen.py`/`router.py.j2`, más tests del generador. Mientras tanto, evitar las acciones llamadas como operaciones CRUD y `permission: user` en acciones de recursos *owned*.
  2. **SEC-33:** antes de usar `executor: process` o `thread` con entradas de usuario, poder matar el proceso al vencer, o reciclar el pool, y no reintentar por timeout las tareas no idempotentes.
  3. **SEC-35:** antes de usar `scripts/new_api.py` para una entrega, copiar solo lo versionado (o exigir un árbol limpio) y revisar secretos y datos personales justo antes del commit, sin filtrar por sufijo.
- **Recomendadas, no bloqueantes:** SEC-34, 36, 37, 38 y 39 y los detalles de §3.10. Sobre todo el Dockerfile de los proyectos nuevos, que hoy no construye.

**Balance:** 0 hallazgos críticos o altos; **4 medios nuevos** (SEC-31, 32, 33 y 35), 4 bajos y 1 informativo. Los controles de la cola en tiempo de ejecución (aislamiento por dueño, límites y mensajes de error) están bien. El riesgo está en **lo que el generador permite configurar** y en **cómo se interrumpen las tareas**.
