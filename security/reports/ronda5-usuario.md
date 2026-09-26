# Ronda 5: informe del usuario (revisión completa e integración con graphify)

- **Perfil:** desarrollador que usa la plantilla por primera vez. He seguido **solo** `README.txt` y `guia/README.txt`, incluidas las secciones nuevas de graphify (README §11 y guía §13).
- **Fecha:** 2026-09-25
- **Entorno:**
  - Copia nueva en el scratchpad (`.../scratchpad/ux5`), hecha con rsync sin `.venv`, `__pycache__`, `*.db`, `loadtests/` ni `security/reports/`. No he tocado el repositorio original.
  - `apigen` y `pytest` del `.venv` del repositorio, con `PYTHONPATH` apuntando a la copia.
  - graphify 0.9.58 en el PATH.
  - API en `127.0.0.1:8902` (development). El servidor está detenido.
- **Orientación en el código:** antes de leer nada he usado `graphify query/explain/path`. Así llegué a `_refresh_graph()` (`apigen/cli.py` L53) y a `refresh_graph()` (`apigen/project.py` L305) y leí solo esas líneas.

**Recorrido realizado**

1. **Preparación:** `init-env` → `check` → `db upgrade` → `createsuperuser` (sin TTY, con `APIGEN_SUPERUSER_PASSWORD`). Todo a la primera.
2. **`add task`** con la receta de la guía §2.1 (`--owned --soft-delete`, filtros, búsqueda y orden).
3. **Blog por YAML** (`post` y `comment`, ambos `owned: true` y `shared_read: true`, `list/read: public`, `fk` con `on_delete`) → `generate --dry-run` → `generate --migrate`.
4. **Resto de la CLI:**
   - `db migrate` sin cambios, `version add v2`, `version deprecate v1`;
   - `add tag` → `remove tag` (sin `-y` y con `-y`) → `migrate "drop tag"`;
   - receta de la guía §5 (editar `resources/post.yaml` → `generate --force --only post` → `migrate`);
   - `check`, `make graph` y `make graph-query`;
   - `apigen` y `make graph` sin graphify en el PATH, y con `APIGEN_NO_GRAPH=1`.
5. **Graphify:** después de cada comando comprobé el grafo (número de nodos, nodos del recurso nuevo o borrado, ficheros inexistentes). También ejecuté los ejemplos de README §11 y guía §13 tal cual.
6. **Cliente real:**
   - registro, login (form y JSON), `/me`;
   - refresh normal y en gracia, 3 refresh concurrentes, procedimiento del 409 (logout con el refresh viejo), logout;
   - CRUD de `tasks`, `posts` y `comments`, aislamiento entre usuarios, lectura pública;
   - filtros, `q`, `order_by`, paginación y parámetros desconocidos;
   - errores 404/405/409/413/415/422;
   - rate limit de login, registro y endpoint;
   - CORS de localhost, OpenAPI y cabeceras Deprecation/Sunset.
7. **Calidad:** `pytest` sobre la copia da **174 passed, 1 failed** (ver UX-38). `ruff check .` da 78 errores en el código generado (ver UX-45). El cliente no vio ninguna respuesta 5xx y el log no tiene trazas.

---

## 1. Lo ya resuelto sigue bien

| ID | Estado en ronda 5 | Evidencia |
|---|---|---|
| UX-01 `init-env` | OK | `init-env` + `check` → `✓ Configuración válida` a la primera; `.env` con permisos 600. |
| UX-02 / T2 refresh concurrente | OK | 3 simultáneos → `[200, 409 refresh_token_rotated, 409 refresh_token_rotated]`. Reutilizar dentro de la gracia → 409. Logout con el refresh viejo → el refresh del ganador pasa a 401 (ver matiz UX-50). |
| UX-03 migrate sin cambios | OK | `Sin cambios en los modelos: no se creó migración.` (rc=0). |
| UX-10 409 con `fields` | OK | `409 unique_violation, fields:["slug"]`. |
| UX-11 soft delete + unique | OK | Borrar el post y volver a crear el mismo `slug` → 201. |
| UX-12 / UX-13 códigos de auth | OK | Sin token → `not_authenticated`; basura → `invalid_token`; login con JSON → `415 login_expects_form`. |
| UX-29 `loc` por campo | OK | `password_policy` con `loc:["body","password"]` (longitud y contraseña común); `null_not_allowed` e `immutable_field` con `loc` en su campo. |
| UX-30 413 | OK | `413 {"detail":"Request body too large","code":"body_too_large"}`. |
| UX-31 `tokenUrl` | OK | Con v2 activa: `tokenUrl=/api/v2/auth/login`; login documenta 200/401/415/422/429. *El test del repositorio no lo contempla: UX-38.* |
| UX-32 CLI | OK | `maxx=10` → `¿quisiste decir 'max'?`; `createsuperuser` → `Contraseña débil: es una secuencia de teclado o del alfabeto`; `check` → `CORS localhost:* (desarrollo)`. |
| UX-33 Alembic silencioso | OK, con un matiz | `db upgrade`, `db migrate` y `db current` son limpios. `generate --migrate` todavía muestra la línea `Generating /ruta/absoluta/… done` (UX-47). |
| UX-34 límite de registro | OK | 10 registros seguidos desde la misma IP → todos 201. |
| UX-35 / SEC-08 blog | OK | Con `shared_read: true`, ni `generate` ni `list` avisan; `apigen list` muestra `owned shared-read`. |
| UX-36 teclado | OK | `qwertyuiopas` se rechaza (CLI). |
| UX-37 415 JSON | OK | `text/plain` a `/tasks` y form a `/auth/refresh` → `415 expects_json`. |
| Paginación y filtros | OK | `{items,total,limit,offset}`. `page/size` → 422 con la alternativa. Un campo no filtrable → `field 'title' is not filterable (filters: done, priority)`. `_=123` se ignora. `limit=1000` → 422. |
| Aislamiento | OK | Bob no puede leer, modificar ni borrar la tarea de Ana (404), ni editar ni borrar su post público (404). Sí puede comentar en él. |
| Rate limit | OK | `429 rate_limited` + `Retry-After` + `hint` claro. Endpoint: 119×200 y luego 429. |
| Versionado | OK | Tras `deprecate v1` (y reiniciar el servidor): `Deprecation: @…` y `Sunset: Wed, 30 Jun 2027`. |
| CORS de desarrollo | OK | Preflight desde `http://localhost:5173` → 200 con los headers esperados. |

---

## 2. Puntos nuevos

| ID | Prioridad | Qué intenté | Qué pasó | Qué esperaba | Sugerencia |
|---|---|---|---|---|---|
| **UX-38** | **Media** | Seguir la guía §6 (`apigen version add v2`) y ejecutar `uv run pytest`, como pide el README. | **1 failed**: `tests/test_security.py::test_swagger_token_url_uses_active_version` espera `"/api/v1/auth/login"` literal. Con v2 activa, `tokenUrl` es `/api/v2/auth/login`, que es justo el comportamiento correcto de UX-31. | Que un flujo documentado no deje la suite en rojo. Un usuario nuevo pensará que ha roto algo. | Calcular el valor esperado con `deps._login_version()` o `versions`, o fijar las versiones con `monkeypatch`. Conviene revisar si hay otros tests de la plantilla que den por hecho que solo existe v1. |
| **UX-39** | **Media** | Revisar cómo "Claude Code usa el grafo automáticamente" (README §11). | `.claude/settings.json` llama a los hooks con una **ruta absoluta de este equipo**: `/Users/sergionvte/.local/bin/graphify hook-guard …`. Es el único fichero versionado con esa ruta (graph.json, manifest y CLAUDE.md están limpios). | Que la plantilla sea portable. En otro equipo o usuario, el hook falla en cada llamada a Bash, Read, Grep o Glob, o no hace nada. | Usar `graphify hook-guard search` (resuelto por el PATH), con una salida silenciosa si no está instalado: `command -v graphify >/dev/null && graphify hook-guard search \|\| true`. En la guía §1 (proyecto nuevo), indicar `graphify claude install` para regenerarlo. |
| **UX-40** | **Media** | Blog: `comment.post_id` con `on_delete: CASCADE` hacia `post` (soft delete). Borrar el post y listar `GET /comments?post_id=<post borrado>` sin autenticación. | El post desaparece (404), pero **sus comentarios se siguen listando públicamente** y apuntan a un post inexistente. `CASCADE` no actúa con soft delete. Con el `RESTRICT` por defecto tampoco habría 409 `has_dependents`. Crear un comentario nuevo sobre ese post sí da `422 reference_not_found` (bien). Ni el generador ni la guía lo avisan. | Que `on_delete` signifique algo también con soft delete o, al menos, que me avisen. | Opciones: (a) aviso en `generate`, del tipo "fk hacia un recurso con soft_delete: on_delete no se aplica al borrado lógico"; (b) propagar el soft delete a los hijos `CASCADE` y responder 409 `has_dependents` para `RESTRICT`; (c) documentarlo en la guía §2 junto a `--soft-delete`. |
| **UX-41** | Baja | Ejecutar tal cual los ejemplos de `graphify path`: README §11 `path "User" "RefreshToken"` y guía §13 `path "ResourceSpec" "render_resource"`. | Los dos responden `No directed path found … Re-run with --undirected`. Con `--undirected`, User→RefreshToken sale **a través de `UTCDateTime`**, una relación engañosa (la real es la FK `user_id`). | Que el ejemplo de la documentación funcione y enseñe algo. | Usar pares con relación directa, que he comprobado: `graphify path "refresh()" "rotate_refresh_token()"` y `graphify path "login()" "authenticate()"`. Añadir una línea sobre `--undirected` y sobre `explain` con símbolos ambiguos (`_refresh_graph()` existe en dos ficheros y exige el id `apigen_project_refresh_graph`). |
| **UX-42** | Baja | Instalar y usar graphify solo con el README §11 y la guía §1/§13. | (1) `uv tool install graphifyy` instala la CLI, pero **`/graphify` en Claude Code necesita la skill** (`graphify install`), y eso no se menciona. (2) La guía §1 (proyecto nuevo) no habla de graphify: el grafo heredado describe la plantilla e incluye `security/reports/` y `loadtests/`, y esos nodos aparecen en consultas del día a día (en "dos pestañas hacen refresh" salen `SEC-02 lockout DoS` y `T1 Smart lockout`). (3) `make graph` sin graphify da un seco `make: graphify: No such file or directory`. En cambio, `apigen` sin graphify avisa muy bien: `graphify no está instalado: el grafo queda desactualizado (uv tool install graphifyy)`. | Pasos completos y un grafo centrado en *mi* proyecto. | Añadir `graphify install` al README §11. En la guía §1, añadir "`graphify claude install` y `/graphify .`". Valorar `security/reports/` y `loadtests/` en `.graphifyignore` (o documentarlo). En el Makefile: `@command -v graphify >/dev/null \|\| { echo "instala graphify: uv tool install graphifyy"; exit 1; }`. |
| **UX-43** | Baja | `apigen db migrate -m "drop tag"` y luego buscar la migración en el grafo. | `db migrate` (y `version deprecate`, que edita `versions.py`) **no actualizan el grafo**, pero las migraciones sí forman parte de él: `drop_tag` no está y `add_tag` sí. El README lo cumple a la letra (solo promete add, generate, remove y version add), pero el grafo queda desfasado. | Todo lo que hace `apigen` y cambia código deja el grafo al día. | Lo más sencillo: añadir `alembic/versions/` a `.graphifyignore` (solo aportan ruido: `upgrade()` y `downgrade()` por fichero). Si no, llamar a `refresh_graph()` también tras `migrate` y `deprecate`. |
| **UX-44** | Baja | Preguntar al grafo cosas "de uso": `graphify query "cómo añado un campo a un recurso existente"`. | Devuelve `dependents()`, `list_resources()` y un test de pestañas (UX-19), pero no la receta de la guía §5. Además, el grafo versionado **no incluye README §11 ni guía §13**: en `manifest.json`, README, guía y CLAUDE.md tienen `semantic_hash: ""`, y de la guía solo hay 7 nodos. El `--budget 700` devolvió unos 2.000 tokens ("Complete answer over budget"). | Saber para qué sirve el grafo. | Ejecutar `/graphify . --update` antes de publicar la plantilla, como pide el propio CLAUDE.md. En la guía §13, decir que el grafo sirve para **navegar el código** y que las recetas están en la guía. Las consultas en inglés o con nombres de símbolos funcionan mejor. |
| **UX-45** | Baja | README §8: `uv run ruff check . && ruff format .` tras generar task, post, comment y v2. | **78 errores** en el código generado: 52 F401 (imports sin usar), 12 I001, 10 E501 (líneas con `pattern` en modelos y esquemas, y `versions.py` tras `deprecate`) y 4 F811 (`import uuid` duplicado en los recursos con `fk`). `ruff format` + `ruff check --fix` (= `make format`) los corrige todos. | Que el código generado pase el lint que recomienda el propio README. | Pasar `ruff format` y `ruff check --fix` a los ficheros escritos (si ruff está disponible) o limpiar las plantillas. En el README, poner primero `format` y después `check`. |
| **UX-46** | Baja | `on_delete: cascade` en YAML. | `✗ fields.post_id.on_delete: valor 'cascade' no válido (opciones: CASCADE, SET NULL, RESTRICT)` | Que lo acepte en minúsculas: el mensaje es claro, pero es fricción gratuita. | Normalizar a mayúsculas antes de validar. |
| **UX-47** | Baja | `apigen add task` (olvidé el migrate) y después `generate blog.yaml --migrate`. | La migración se llamó `add post, comment` pero **también crea la tabla `tasks`**, sin ningún aviso. `generate --migrate` imprime además `Generating /ruta/absoluta/alembic/versions/… ... done` de Alembic (no pasa con `db migrate`). | Un aviso cuando la migración incluye tablas de otros recursos, y el mismo modo silencioso que `db migrate`. | Tras el autogenerate, comparar las tablas tocadas con los recursos del comando y avisar (`! la migración incluye también: tasks`). Aplicar el mismo modo silencioso a `generate --migrate`. |
| **UX-48** | Baja (docs) | Receta "Blog" de la guía §3 y un post de Bob con `published: false`. | El borrador de Bob aparece en `GET /posts` para anónimos, porque `list/read=public` lo expone todo. `slug` es único **por usuario**, así que dos autores pueden tener `hola-mundo` (documentado, pero sorprende en un blog). | Una advertencia en la receta, porque es el ejemplo que cualquiera copia. | En la receta: "los borradores también se ven: filtra `published` en el endpoint o crea uno propio para publicados. `unique` es por autor". |
| **UX-49** | Baja (docs) | Procedimiento del 409, paso 2 (README §6 y guía §4): logout con el refresh viejo "revoca la sesión entera, incluido el token del ganador". | El **refresh** del ganador queda revocado (401), pero su **access token sigue valiendo** (`/users/me` → 200) hasta que caduca, como en cualquier logout. | Que el texto no dé a entender que el atacante queda fuera al instante. | Precisarlo ("su refresh deja de valer; su access token dura como máximo ACCESS_TOKEN_EXPIRE_MINUTES") o, mejor, que el logout con un token rotado dentro de la gracia invalide también los access tokens (igual que la detección de robo). |

---

## 3. Valoración específica de graphify

**Nota: 7/10.** La integración con `apigen` está muy bien. Los ejemplos de la documentación, la portabilidad y la utilidad para preguntas de uso flojean.

**Lo que funciona bien**

- **`apigen` mantiene el grafo como promete.** Comprobado con número de nodos y nodos concretos:
  - `add task`: aparecen `app_models_task_task`, los endpoints y los tests, en unos 2 s;
  - `generate` del blog y `version add v2`: 1.216 nodos, 58 de ellos de `app/api/v2`;
  - `generate --force --only post` también lo actualiza;
  - `remove tag`: desaparecen los 27 nodos de código de `tag` y no queda **ningún nodo apuntando a un fichero inexistente**.
- **Degradación elegante.** Sin graphify en el PATH, `apigen` sigue funcionando y avisa con el comando de instalación. `APIGEN_NO_GRAPH=1` lo desactiva. Solo se ejecuta si ya existe `graphify-out/graph.json`.
- **`make graph` es rápido** (~1 s, sin tokens) y dice cuándo no hay cambios.
- **Para preguntas de código ahorra de verdad.** `query "cómo se rota el refresh token"` y `explain "rotate_refresh_token"` me dieron fichero y línea exactos (`app/services/auth.py L314`) y quién la llama. Con `sed -n` sobre esas líneas me bastó, sin abrir ficheros enteros. `make graph-query Q="quién puede borrar un post…"` me llevó a `Principal.owner_filter` y `_get_or_404`.
- El `.gitignore` y el README coinciden en qué se versiona: la caché, `graph.html` y las copias fechadas `graphify-out/2026-09-25/` quedan fuera.

**Lo que no**

- Los dos ejemplos de `graphify path` de la documentación fallan (UX-41).
- El hook con ruta absoluta (UX-39) y la falta del paso `graphify install` (UX-42).
- `db migrate` desfasa el grafo (UX-43).
- El grafo versionado no refleja la documentación actual y no ayuda con preguntas de uso (UX-44).
- Tras `version add v2`, cada símbolo de recurso aparece dos veces (v1 y v2) y gasta el doble de presupuesto en las consultas. No es un error, pero conviene saberlo.
- Ruido del propio graphify: `Tip: set GEMINI_API_KEY…` en cada `update`, el aviso "MANDATORY…" del hook en casi cada `ls`, `grep` o `cat`, y un `--budget` que no siempre se respeta.

**¿Se entiende?** Sí. La guía §13 ("Día a día") es clara y concisa. Solo falta explicar qué preguntas contesta bien el grafo y cuáles no.

**¿Me ayuda a entender el proyecto?** Para localizar código, mucho. Para aprender a usar la plantilla, no: para eso sigue siendo mejor la guía.

---

## 4. Lo que me ha gustado

- **El recorrido completo se hace sin leer código:** init-env, upgrade, superusuario, un recurso por CLI, un blog por YAML, v2, remove y la receta de "añadir campo". Todo funciona tal como lo cuenta la guía.
- **Los errores de la API son de diez:** `code` estable, `loc` en el campo, sugerencias como `field 'title' is not filterable (filters: done, priority)` o `unknown parameter 'page': use limit/offset`, 415 explícitos, y 413 y 429 con `code` y `hint`.
- **`shared_read`** resuelve el blog sin avisos molestos y sin abrir BOLA.
- **La CLI** sugiere alternativas ("¿quisiste decir 'max'?"), explica la contraseña débil en español y `--dry-run` muestra exactamente qué ficheros va a escribir.
- **Estabilidad:** 0 respuestas 5xx y 0 trazas en todo el recorrido.

---

## 5. Valoración global

**9 / 10** (ronda 1: 5; ronda 3: 8,5).

- En la ronda 3 dije que con UX-29 y UX-34 resueltos le pondría un 9. Están resueltos, y el resto de puntos de esa ronda también.
- Lo nuevo es de prioridad media o baja. Lo que más me importa como usuario:
  - **UX-38:** `pytest` en rojo tras seguir la guía de versiones.
  - **UX-40:** comentarios huérfanos visibles tras el soft delete del padre.
  - **UX-39:** el hook de graphify ligado a este equipo.
- Graphify suma como herramienta para trabajar con Claude sobre el código. Hoy le resta algo de pulido (ejemplos que no funcionan y portabilidad).
- Con UX-38, UX-39 y UX-40 corregidos, le pondría un 9,5 sin dudarlo.
