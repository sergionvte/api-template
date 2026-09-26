# Ronda 6 — Respuesta del desarrollador

- **Fecha:** 2026-09-26
- **Entrada:** `ronda5-seguridad.md` (SEC-25…SEC-30 y detalles menores) y `ronda5-usuario.md` (UX-38…UX-49).
- **Método:** orientación con `graphify query/explain/path` y lectura de las líneas indicadas. Las plantillas `.j2` se leyeron directamente porque no están en el grafo (SEC-28). Al terminar ejecuté `graphify update .`: 1102 nodos y 0 rutas absolutas en `graph.json`, `GRAPH_REPORT.md` y `manifest.json`.
- **Restricción:** no he modificado `.claude/` ni `CLAUDE.md` (SEC-25/UX-39 y la nota de SEC-28 para `CLAUDE.md` quedan como recomendación al propietario).

## Estado final

| Comprobación | Resultado |
|---|---|
| `.venv/bin/pytest -q -p no:cacheprovider` (repo) | **151 passed** (ronda 5: 133) |
| `.venv/bin/ruff check .` y `ruff format --check .` (repo) | limpios |
| Copia temporal + `generate examples/shop.yaml --migrate` | 174 passed, 1 skipped (el test de `loadtests/`, que la copia no incluye). `ruff check` limpio **sin** `make format`. No aparece la línea `Generating /ruta/absoluta`. El segundo `db migrate` responde "Sin cambios". |
| Misma copia + `version add v2` + `version deprecate v1` (dos veces) | **200 passed** (UX-38 resuelto con v2 activa). `versions.py` formateado y legible por `version list`. ruff limpio. |
| Misma copia + `add task` sin migrar + blog YAML (`post` y `comment` owned + `shared_read` + soft delete, `comment.post_id on_delete: cascade` en minúsculas, `bookmark.post_id on_delete: Restrict`) + `generate --migrate` | Aviso `! La migración incluye también: tasks`. **227 passed, 1 skipped**. ruff limpio. |
| E2E de UX-40 en la copia (httpx ASGI) | Ver la tabla de UX-40. |

No he creado `resources/` ni ficheros `*.db` en el repo, ni he lanzado pruebas de carga. Solo ejecuté `run_loadtest.sh` para comprobar que se niega ante una BD remota, y sale antes de generar nada.

---

## 1. Tabla de decisiones

| ID | Decisión | Cambio (ficheros) | Test |
|---|---|---|---|
| **SEC-30** Último admin frente a admins desactivados | **Aceptado** | `app/api/v1/endpoints/users.py`: nueva `_counts_as_admin(user)` (rol admin **y** activo). `update_user` y `delete_user` solo aplican la protección si el objetivo cuenta para el mínimo. | `test_inactive_admin_can_be_demoted_and_deleted` (con un único admin activo simulado: PATCH → 200, DELETE → 204); `test_last_active_admin_protected_and_audited` (sigue dando 409 `last_admin` en los 3 casos) |
| **UX-38** Test de `tokenUrl` con v2 activa | **Aceptado** | `tests/test_security.py`: el valor esperado se calcula a partir de `versions.VERSIONS` (la versión más alta no deprecada), no con el literal `/api/v1`. | El propio test. En la copia con v2 activa y v1 deprecada: 200 passed. |
| **UX-40** Soft delete del padre y `on_delete` | **Aceptado**: `on_delete` significa lo mismo con borrado físico y con soft delete. Ver §2. | `app/crud/base.py`: nueva `apply_on_delete()`, llamada desde `Repository.delete` cuando hay soft delete. Si falla, hace rollback. `guia/README.txt` §2.1.1 y `README.txt` §6. | `tests/test_soft_delete.py`: cascada lógica recursiva, hijo sin soft delete borrado físicamente, SET NULL, hijos ya borrados intactos, RESTRICT con 409 solo si hay hijos vivos, autorreferencia sin bucle. E2E en la copia. |
| **SEC-29** La prueba de carga heredaba `DATABASE_URL` | **Aceptado** | Nuevo `loadtests/resolve_db.py` (solo biblioteca estándar): ignora `DATABASE_URL`. El opt-in es `LOADTEST_DATABASE_URL`, y si el host no es local exige además `LOADTEST_ALLOW_REMOTE_DB=1`. Nunca imprime la contraseña. `run_loadtest.sh` lo usa y hace `unset DATABASE_URL`. `seed.py --cleanup` borra las cuentas `bench-*` al terminar cuando la BD no es la temporal. Documentado en README §8. | `tests/test_loadtest_db.py` (3 tests; se salta si no existe `loadtests/`). Manual: `LOADTEST_DATABASE_URL=postgresql://…@db.internal/x ./loadtests/run_loadtest.sh` termina con rc=2 y un mensaje claro. |
| **UX-45** Código generado sucio para ruff | **Aceptado** | `apigen/codegen.py`: `Imports.render(already=…)` quita los imports que la plantilla ya escribe, así que no hay F811 `import uuid` duplicados. `apigen/project.py`: `find_ruff()` busca ruff en el PATH, en `.venv/bin` y junto a `sys.executable` (el caso de `.venv/bin/apigen` sin activar el entorno, que era el del usuario). `format_files` aplica `check --fix --select I,F401,F811` y `format`, y ahora también a `versions.py` tras `version deprecate`. README §8: `make format && make lint`. | `test_generated_code_passes_ruff` (fk, owned, pattern largo, datetime y uuid; `ruff check` con la configuración del proyecto = 0 errores); `test_deprecate_survives_formatting`. En las copias, ruff limpio tras todos los comandos. |
| **UX-46** `on_delete` sensible a mayúsculas | **Aceptado** | `apigen/spec.py`: `field_validator("on_delete", mode="before")` normaliza `cascade`, `set null`, `Set_Null` y `restrict`. Cualquier otro valor sigue fallando con el mismo mensaje. | `test_on_delete_is_case_insensitive` (YAML y DSL de la CLI). En la copia, `cascade` y `Restrict` generan `ondelete="CASCADE"` y `"RESTRICT"`. |
| **UX-47** La migración incluye otros recursos / ruta absoluta en la salida | **Aceptado** | `apigen/cli.py`: `_migrate()` lista "Tablas afectadas" (tablas del `upgrade()`, vía `migration_tables()`). Desde `generate --migrate` avisa `! La migración incluye también: …`. `_alembic_config(quiet=True)` define `cmd_opts.quiet` y así Alembic deja de imprimir `Generating /ruta/absoluta … done`. | `test_migration_tables_lists_what_upgrade_touches`, `test_quiet_alembic_config_silences_status_messages`. En la copia, aviso con `tasks` y sin la ruta. |
| **UX-43** `db migrate` / `deprecate` no refrescaban el grafo | **Aceptado** (opción "refrescar", no excluir migraciones) | `apigen/cli.py`: `_migrate` llama a `_refresh_graph` si crea una migración, y `version deprecate` también. `generate --migrate` refresca una sola vez. | Manual en la copia ("grafo actualizado" tras migrate y deprecate). La lógica opcional de `refresh_graph` ya la cubre `test_refresh_graph_is_optional`. |
| **UX-49** Texto del logout tras el 409 | **Aceptado (documentación)** | README §6 y guía §4: el refresh del ganador deja de valer al instante, pero su access token vive hasta `ACCESS_TOKEN_EXPIRE_MINUTES`. Si se sospecha robo, se recomienda además `POST /auth/logout-all`, que sí invalida los access tokens. | Sin cambio de comportamiento. `test_logout_after_409_revokes_the_whole_family` sigue en verde. |
| **UX-48** Receta del blog: borradores y `unique` por autor | **Aceptado (documentación)** | Guía §3: advertencia y dos opciones, (a) forzar `published=True` en `list_posts` salvo para admin y 404 en `get_post` para borradores ajenos, o (b) `list/read=owner` más un endpoint público propio. También explica la unicidad por autor. | — (receta) |
| **UX-41** Ejemplos de `graphify path` que fallaban | **Aceptado** | README §11 y guía §13: `path "refresh()" "rotate_refresh_token()"`, `path "login()" "authenticate()"` y `path "delete_user()" "_admin_count()"`, los tres comprobados (1 salto). Nota sobre `--undirected` (desconfiar de caminos por `UTCDateTime`) y sobre ids en nombres ambiguos. | Ejecutados a mano. |
| **UX-42** `graphify install`, proyecto nuevo, `make graph` sin graphify | **Aceptado** | README §11: `graphify install` para `/graphify`. Guía §1: `graphify install`, `graphify claude install`, cómo excluir `security/reports/` y `loadtests/` en `.graphifyignore` y regenerar (`rm -rf graphify-out && graphify update .`, o `/graphify .`). `Makefile`: `GRAPHIFY_CHECK` con un mensaje claro y `make graph-query` sin `Q` muestra el uso. | `PATH=/usr/bin:/bin make graph` → `graphify no está instalado: uv tool install graphifyy==0.9.58 (ver README §11)`. |
| **UX-44** Para qué sirve el grafo | **Aceptado parcialmente** | Guía §13 "Para qué sirve (y para qué no)": sirve para navegar el código, no para aprender la plantilla. Mejor en inglés o con símbolos. **Pospuesto:** `/graphify . --update` (extracción semántica con LLM de README y guía). Lo ejecutará el propietario antes de publicar la plantilla; con `graphify update .` solo se actualiza el AST. | — |
| **UX-39 / SEC-25** Hook con ruta absoluta en `.claude/settings.json` | **Recomendación, sin tocar el fichero** (decisión del propietario) | Ver §3. README §11 y guía §1 ya explican que los hooks son opcionales y cómo regenerarlos con `graphify claude install`. | — |
| **SEC-26** `apigen` ejecuta una herramienta fuera del lockfile | **Aceptado parcialmente** | `apigen/project.py`: timeout de 180 s → 60 s. El mensaje de instalación usa la versión fijada (`graphifyy==0.9.58`), también en README, guía y Makefile. **Se mantiene** el comportamiento actual (solo actúa si ya existe `graphify-out/graph.json`, que en la práctica equivale a un opt-in, y `APIGEN_NO_GRAPH=1` lo desactiva). **No** la añado a `pyproject.toml`: cambiaría `uv.lock` y metería en el entorno de todos los usuarios una herramienta opcional. README §11 aclara que queda fuera de `make audit`. | La lógica opcional ya la cubre `test_refresh_graph_is_optional`. |
| **SEC-27** Integridad y alcance del grafo versionado | **Aceptado (documentación)** | README §11: el grafo es un artefacto generado, sus diffs se revisan en los PR y hay una receta para CI (`graphify update . && git diff --exit-code graphify-out/graph.json`). Guía §1: cómo sacar `security/reports/` del grafo en un proyecto nuevo. **No** cambio lo que se versiona: publicar o no `security/reports/` lo decide el propietario. | Comprobado tras `graphify update .`: 0 rutas absolutas en los artefactos versionados. |
| **SEC-28** Puntos ciegos del grafo | **Aceptado** (salvo `CLAUDE.md`, que no puedo tocar) | Docstring de `ensure_reference()`: la llaman los routers generados (`router.py.j2`), no es código muerto. README §11 y guía §13: `apigen/templates/*.j2`, Dockerfile, alembic.ini, Makefile y `.env.example` no están en el grafo y hay que leerlos directamente. **Recomendado al propietario:** la misma nota en `CLAUDE.md`. | — |
| Menor: 400 de `Host` sin `code` | **Aceptado** | `app/core/middleware.py`: `JSONTrustedHostMiddleware` hereda del de Starlette (misma validación y misma redirección www) y solo reescribe su 400 a `{"detail":"Invalid host header","code":"invalid_host"}`. Los 4xx de la aplicación no se tocan. `app/main.py`: se coloca dentro de `SecurityHeadersMiddleware`, así que el 400 también lleva CSP, `nosniff`, etc. README §6 documenta `invalid_host`. | `test_invalid_host_is_json_with_code` (JSON, cabeceras, host válido sin cambios, 4xx de la app sin reescribir, 307 www conservado) |
| Menor: `version add --from` sin validar | **Aceptado** | `apigen/cli.py` y `apigen/project.py::add_version`: `VERSION_NAME` también para el origen (defensa en la CLI y en la función). | `test_version_add_validates_source` (`--from ../app` → exit 1; `add_version(…, "../../etc")` → SpecError) |
| Menor: `.dockerignore` | **Aceptado** | Añadidos `graphify-out`, `.claude`, `security`, `tests`, `loadtests` y `guia`. El `COPY` selectivo del Dockerfile no usa ninguno. | Estático (no hay Docker aquí). |
| Menor: auditoría de 409 admin y 429 de login | **Aceptado** | `users.py`: evento `admin.user.rejected` (WARNING) con `actor_id`, `target_user_id`, `action` y `reason` (`last_admin` o `self_delete`). `app/core/errors.py`: `auth.rate_limited` (WARNING, con `path` y `client_ip`, sin email) **solo en rutas `/auth/`**, para que un flood contra otros endpoints no se convierta en un flood de logs de auditoría. | `test_last_active_admin_protected_and_audited`, `test_admin_cannot_delete_self` (ampliado), `test_login_rate_limited` (ampliado) |

---

## 2. UX-40: decisión sobre soft delete con hijos

**Opciones valoradas:**

| Opción | Problema |
|---|---|
| Filtrar hijos de padres borrados en cada listado | Un JOIN o subconsulta por cada FK en cada GET. Hay que tocar `list`, `get`, filtros y conteo, y aun así el hijo "existe" para PATCH y DELETE. Caro y fácil de olvidar en endpoints propios. |
| Solo un aviso en `generate` | No arregla la fuga pública de comentarios. |
| **Aplicar `on_delete` al borrado lógico** (elegida) | Una sola regla, coherente con el borrado físico, sin coste en las lecturas y solo al borrar. |

**Semántica implementada** (`app/crud/base.py::apply_on_delete`). Solo se consideran los hijos **vivos**:

| `on_delete` del hijo | Hijo con soft delete | Hijo sin soft delete |
|---|---|---|
| CASCADE | `deleted_at` (+ `updated_at`), recursivo sobre sus propios hijos | DELETE físico. La BD aplica sus propias FK: si un nieto lo impide → 409 `has_dependents` por el manejador existente. |
| SET NULL | columna a NULL (+ `updated_at`) | ídem |
| RESTRICT / NO ACTION | 409 `has_dependents` (mismo cuerpo que el borrado físico) | ídem |

**Detalles de implementación:**
- Las FK se leen de los metadatos de SQLAlchemy **en tiempo de ejecución**, no de las plantillas. Así funciona aunque el hijo se haya generado después que el padre, sin regenerar el router del padre, y también en recursos escritos a mano que usen `Repository`.
- Todo va en la transacción del DELETE. Ante cualquier error hay rollback y no se aplica nada a medias.
- La recursión termina también en ciclos y autorreferencias, porque solo se seleccionan hijos vivos (hay test).
- El 409 de RESTRICT revela que existen hijos, igual que el borrado físico. En recursos *owned*, CASCADE borra también hijos de otros usuarios (los comentarios de otros en mi post), igual que haría la BD. Es lo que significa CASCADE.

**E2E en la copia** (blog en `/api/v1`):

| Paso | Resultado |
|---|---|
| Comentarios del post antes de borrarlo | 1 |
| DELETE del post (CASCADE) | 204 |
| `GET /comments?post_id=…` anónimo después | total 0 |
| GET del comentario de Bob | 404 |
| DELETE de un post con bookmark (RESTRICT) | 409 `has_dependents`, el post sigue visible (200) |
| Bob borra su bookmark y se repite el DELETE | 204 |

**Cambio de comportamiento (documentado en la guía §2.1.1):**
- Borrar lógicamente un padre con hijos vivos RESTRICT, que es el valor por defecto de una FK no nullable, ahora da 409 donde antes daba 204.
- Ejemplo: en `shop.yaml`, un producto con pedidos. Para retirar algo con historial se recomienda un campo de estado (`active`/`status`), que el ejemplo ya tiene.
- Los datos anteriores (comentarios de posts ya borrados) no se corrigen solos. La guía sugiere una migración de datos.
- El script de laboratorio `ronda5_checks.py` no se ve afectado: borra un producto sin pedidos.

---

## 3. SEC-25 / UX-39: recomendación técnica (sin tocar `.claude/`)

El hook actual (`/Users/sergionvte/.local/bin/graphify hook-guard …`) no es portable, filtra el nombre de la cuenta y ejecuta un binario de fuera del repo en cada llamada a Bash, Read, Grep o Glob.

**Recomendación, en orden de preferencia:**

1. **Mover los hooks a `.claude/settings.local.json`** (añadirlo a `.gitignore`). Cada desarrollador los genera con `graphify claude install` (ya documentado en la guía §1) y `settings.json` versionado queda sin hooks. Es lo más seguro: un PR no puede introducir un comando que se ejecute en cada llamada de herramienta.
2. Si se quiere mantener el hook versionado: invocarlo **por nombre y tolerante a la ausencia**:

   ```sh
   command -v graphify >/dev/null 2>&1 && graphify hook-guard search || true
   ```

   Lo mismo para `read`. Así se resuelve por PATH, no rompe en equipos sin graphify y no contiene rutas personales.
3. En cualquier caso, revisar `.claude/` como código en los PR. Añadir a `CLAUDE.md` la nota de SEC-28: plantillas `.j2` y Docker/Alembic fuera del grafo.

---

## 4. Observaciones nuevas y pendientes

- **Pospuesto (UX-44):** `/graphify . --update` para reindexar semánticamente README, guía e informes. Necesita un LLM y lo ejecutará el propietario antes de publicar. Este informe y los cambios de documentación aún no están en la parte semántica del grafo.
- **Observado durante las pruebas (fuera de alcance, sin cambios):** un YAML sin `versions` genera el recurso en **v1**, mientras que `apigen add` usa la versión activa más reciente (v2 si v1 está deprecada). En la copia, `task` (por CLI) quedó en v2 y el blog (por YAML) en v1. Propongo unificarlo en la próxima ronda para que `load_specs` use `default_version()` cuando falte `versions`, y avisar en `generate`.
- **No verificado:** PostgreSQL, Redis y Docker (igual que en rondas anteriores). `apply_on_delete` usa SQL Core estándar (`UPDATE`/`DELETE … WHERE … IN`) y no depende del motor, pero no lo he probado contra PostgreSQL.

## 5. Ficheros modificados

**Código**
- `app/api/v1/endpoints/users.py`
- `app/core/middleware.py`
- `app/main.py`
- `app/core/errors.py`
- `app/crud/base.py`
- `apigen/spec.py`
- `apigen/codegen.py`
- `apigen/project.py`
- `apigen/cli.py`

**Pruebas de carga y configuración**
- `loadtests/run_loadtest.sh`
- `loadtests/seed.py`
- `loadtests/resolve_db.py` (nuevo)
- `Makefile`
- `.dockerignore`

**Tests**
- `tests/test_users.py`
- `tests/test_security.py`
- `tests/test_auth.py`
- `tests/test_generator.py`
- `tests/test_config.py`
- `tests/test_soft_delete.py` (nuevo)
- `tests/test_loadtest_db.py` (nuevo)

**Documentación y grafo**
- `README.txt` (§6, §8 y §11)
- `guia/README.txt` (§1, §2.1.1, §3, §4 y §13)
- `graphify-out/*` (regenerado con `graphify update .`)
- `security/reports/ronda6-desarrollador.md` (este informe)
