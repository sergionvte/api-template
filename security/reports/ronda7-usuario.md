# Ronda 7 – Informe de usuario (desarrollador que crea y entrega APIs a clientes)

Fecha: 2026-09-26 · Rol: `.claude/agents/user.md` · Valoración anterior: 9/10 (ronda 5)

## 0. Qué he hecho

He seguido solo README.txt §12–13 y guia/README.txt §14–16, trabajando en el scratchpad y no en `~/Developer`.

1. **Proyectos nuevos:**
   - `new_api.py gimnasio-api --lang es`;
   - `new_api.py tienda-api --lang en --title "Tienda Ñandú & Co"`;
   - casos de error: ya existe, `Tienda_API`, `x`, `--no-install --no-git` con una carpeta padre que no existía.
2. **Dominio propio, un gimnasio:**
   - `gym_class`: clases públicas que gestiona el admin. Tiene la acción `occupancy_report` (colección, `background`, `executor: process`, solo admin).
   - `booking`: reservas `owned`. Tiene la acción síncrona `check_in` y la acción `send_reminder` (`background`, `executor: async`, `max_attempts: 2`, `rate_limit`, campo `channel`).
   - Después añadí `cancel` (síncrona) y `export_history` (colección, `executor: thread`).
   - Lógica en los hooks:
     - la clase no puede empezar en el pasado;
     - aforo completo → 409 `class_full`;
     - reserva duplicada → 409;
     - no se puede cambiar de clase en un PATCH;
     - un socio no puede crear una reserva ya asistida;
     - `check_in` sobre una reserva cancelada → 409.
   - Lógica en las tareas:
     - `TaskError` si el canal no es válido;
     - excepción genérica para probar los reintentos;
     - tarea lenta de 20 s para probar la cancelación;
     - informe de ocupación leyendo la BD desde un proceso.
3. **Tests y servidores:** `pytest` (195 en verde), `ruff check` y `ruff format --check` limpios. API con uvicorn en el **8902**, worker con `python -m app.tasks.worker` y después con `make worker`.
4. **Uso como cliente real:** unas 60 peticiones con httpx y curl (202 + `Location`, `status_url`, `/jobs`, cancelación, reintentos, 429, aislamiento entre usuarios). **Ninguna respuesta 5xx ni trazas** en el log de la API.
5. **Documentación:** `apigen docs --lang es` y `--lang en`, con la introducción y el contacto personalizados. Comprobé que se conservan y que la regeneración es idempotente.
6. **Limpieza:** API y worker detenidos; el puerto 8902 queda libre. El repositorio de la plantilla no se ha tocado, salvo este informe.

---

## 1. Puntos encontrados

| ID | Prioridad | Qué intenté | Qué pasó | Qué esperaba | Sugerencia |
|---|---|---|---|---|---|
| **UX-50** | **Alta** | Seguí la guía §16.3, "Recursos en resources/*.yaml → `generate resources --migrate`": un solo `resources/gym.yaml` con los dos recursos, como en `examples/`. | `apigen` escribe además `resources/gym_class.yaml` y `resources/booking.yaml`, así que **cada recurso queda definido dos veces**:<br>• `generate resources --force` genera cada uno dos veces;<br>• el mensaje sale duplicado: `db migrate -m "update booking, booking"`;<br>• **gana el fichero que va último por orden alfabético, sin ningún aviso**.<br>Edité `resources/booking.yaml` (su cabecera dice "Tras editarla ejecuta: generate --force --only booking") y subí `notes` a 700: **mi cambio se perdió**. El esquema se generó con el valor de `gym.yaml` y `booking.yaml` volvió a reescribirse con 500. | Una única fuente de verdad por recurso, o como mínimo un error si hay dos definiciones del mismo recurso. | 1) Si dos ficheros definen el mismo `name`: error `✗ booking definido en gym.yaml y booking.yaml`.<br>2) Si la fuente es un YAML con varios recursos dentro de `resources/`, no escribir los specs por recurso (o separarlo y avisar: "gym.yaml dividido en … y movido a …").<br>3) Decir en la guía §16 qué formato usar en `resources/`. |
| **UX-51** | Media | Arranque rápido (Docker) del README.md del cliente, al pie de la letra: `cp .env.example .env` → `docker compose up -d --build`. | No tenía Docker, así que lo simulé con los valores de `.env.example` y `ENVIRONMENT=production` en `apigen check`:<br>• `SECRET_KEY debe tener al menos 32 caracteres aleatorios`;<br>• `ALLOWED_HOSTS debe enumerar los dominios reales`;<br>• compose exige `POSTGRES_PASSWORD` (`:?define POSTGRES_PASSWORD en .env`), que no aparece en la tabla de Configuración.<br>Además, el README propone `apigen secret`, que un cliente que solo usa Docker no tiene instalado. | Que el arranque rápido que recibe el cliente funcione tal como está escrito. | Cambiar el paso a `docker compose run --rm --no-deps api apigen init-env --production` (o `uv run apigen init-env --production`) y añadir `POSTGRES_PASSWORD` a la tabla. Decir explícitamente que en producción hay que rellenar `ALLOWED_HOSTS`/`CORS_ORIGINS` o la API no arranca. |
| **UX-52** | Media | Proyecto creado con `--lang es`, y después `uv run apigen docs` y `make docs` sin `--lang`, como indica el CLAUDE.md del proyecto. | El README.md del cliente **pasa a inglés** (`--lang` vale `en` por defecto). | Que el proyecto recuerde el idioma elegido al crearlo. | Guardar el idioma (en `pyproject.toml` `[tool.apigen] docs_lang`, o deducirlo del README.md actual) y usarlo cuando no se pase `--lang`. En el CLAUDE.md generado, escribir el comando con el idioma. |
| **UX-53** | Media | Acción `export_history` ("Exporta **tu** historial": colección, `executor: thread`) e informe de ocupación con `executor: process`. | Las tareas `thread` y `process` reciben solo `payload`: sin `ctx`, sin `owner_id`, sin `job_id` y sin sesión de BD. En una acción de colección el payload es `{}`, así que **la tarea no puede saber quién la pidió**. Para leer la BD desde `process` tuve que improvisar `asyncio.run()` + `SessionFactory()` dentro del proceso. Funciona con SQLite, pero no sé si es seguro con asyncpg y el pool. | Poder hacer "exporta lo mío" con cualquier executor, y una forma documentada de leer datos. | Incluir `owner_id` (y `job_id`) en el payload, o pasar un contexto ligero serializable a las tareas síncronas. Que el stub de `process`/`thread` explique cómo leer datos: "carga los datos en el endpoint/hook y pásalos en el payload" o un helper `run_db(...)`. |
| **UX-54** | Media | Acción síncrona `check_in` que cambia `obj.status`. | Funciona **solo porque añadí `await ctx.session.commit()`**. La sesión de la petición no se confirma sola, y el stub no lo menciona: sin ese commit, la acción devuelve 200 y el cambio se pierde en silencio. | Que el stub avise o que el endpoint confirme la transacción. | Añadir al docstring del stub: "si modificas `obj`, `ctx.session.add(obj); await ctx.session.commit()`". O hacer el commit en el router después de la acción si la sesión tiene cambios pendientes. |
| **UX-55** | Media (docs) | Leer el README.md como cliente final (detalle en la sección 2). | Faltan:<br>• la forma de las respuestas: login, paginación y job;<br>• los parámetros de `/jobs` (`status`, `name`);<br>• el estado `cancelled` y el 409 `job_not_cancellable`;<br>• la respuesta de las acciones síncronas y el `result` de las de segundo plano;<br>• los códigos de negocio de mis hooks (`class_full`, `already_booked`…);<br>• ejemplos de petición por recurso. | Poder integrar sin abrir `/docs`. | Ver la sección 2. |
| **UX-56** | Baja | `POST /bookings/{id}/send_reminder` sin cuerpo. El README dice "Cuerpo: `channel` (texto, opt.)". | 422 `loc: ["body"]`, `Field required`: hay que enviar `{}`. | Que, si todos los campos tienen valor por defecto, se pueda omitir el cuerpo. | En el router, `payload: X = Body(default_factory=X)` cuando no haya campos obligatorios. Si no, que el README diga "cuerpo JSON obligatorio (puede ser `{}`)". |
| **UX-57** | Baja | `check_in` (acción sin `fields`) con cuerpo `{"x": 1}`. | 200: el cuerpo se ignora sin avisar. El resto de la API rechaza los campos extra con 422. | Coherencia con `StrictInput`. | Si la acción no declara `fields`, rechazar un cuerpo no vacío (o validar contra un modelo vacío estricto). |
| **UX-58** | Baja | Hook "la clase no puede empezar en el pasado". | **Rompe 2 tests generados**: usan la fecha fija `2026-01-10T10:00:00+00:00`, que ya es pasado. Se arregla con `example: '2030-01-10T10:00:00+00:00'` en el YAML (funciona bien y `--force` respeta los hooks), pero la guía solo menciona `example=` para `pattern`. | Tests generados robustos ante reglas de negocio habituales. | Usar por defecto una fecha futura (p. ej. dentro de un año) para `date`/`datetime`. Añadir a la guía §14: "si tus hooks rechazan el payload de los tests generados, fija `example:` en el campo". |
| **UX-59** | Baja | `apigen generate --force --only gym_class,booking` | `✗ Ningún recurso coincide con --only`, sin decir cuáles hay ni que la opción se repite (`--only a --only b`). | Que acepte comas, o que el error lo explique. | Aceptar la lista separada por comas y, si no coincide ninguno, listar los recursos disponibles. |
| **UX-60** | Baja | `GET /gym_classes?ordering=-starts_at` (la clave del YAML es `ordering`). | 200: el parámetro se ignora en silencio. `sort=` sí responde "unknown parameter 'sort': use order_by". | La misma pista para `ordering`. | Añadir `ordering` (y `order`) a la lista de alias con pista. |
| **UX-61** | Baja | README.md en `es` y en `en`, con el proyecto vacío y con recursos. | • La versión en español dice `Requisitos: Python 3.12+ and [uv]`.<br>• Con el proyecto vacío, "Recursos" muestra solo `—`.<br>• En la versión inglesa, descripciones y acciones salen en español porque vienen del YAML (`Marca la reserva como asistida`). El encabezado `## Soporte` queda en el idioma inicial. | Un texto sin mezclas de idioma. | Traducir "and" → "y". Con el proyecto vacío: "Aún no hay recursos". Admitir `description: {es: …, en: …}` o avisar en `apigen docs` si el idioma del YAML no coincide con el del README. |
| **UX-62** | Media | Desarrollar dentro del proyecto nuevo sin volver a la plantilla. | El proyecto **no trae documentación para el desarrollador**: README.txt y guia/ no se copian. Solo hay CLAUDE.md (resumen de 10 líneas) y `examples/`. La sintaxis del YAML, las acciones, los hooks y el worker solo están en la plantilla. Si la plantilla evoluciona, el proyecto se queda sin su referencia. | Una referencia de `apigen` (YAML, hooks, acciones, worker, versiones) dentro del proyecto. | Copiar un `docs/DESARROLLO.md` (o `apigen help yaml` en la CLI) con las secciones 4–9 y 12 del README y las 14–15 de la guía. CLAUDE.md puede apuntar a ese fichero. |
| **UX-63** | Baja | Revisar el proyecto generado. | Referencias rotas:<br>• el objetivo `make new-api` llama a `scripts/new_api.py`, que no se copia;<br>• `make graph` dice "ver README §11" (README.txt no existe en el proyecto);<br>• `make loadtest` dice "ver loadtests/README", que no existe;<br>• `pyproject.toml` ignora `scripts/**`.<br>Los comentarios del código citan IDs internos (UX-45, SEC-12, …) de informes que no se entregan. | Un proyecto coherente consigo mismo. | En `new_api.py`: quitar el objetivo `new-api` y reescribir esas referencias. Opcionalmente, eliminar los IDs de informe de los comentarios. |
| **UX-64** | Baja | Preparar la entrega del repositorio al cliente (guía §16.6: "…y entrega"). | El repositorio incluye:<br>• `.claude/agents/*.md`: prompts de revisión internos ("usa esta plantilla por primera vez");<br>• `security/lab.sh` y `loadtests/`;<br>• `graphify-out/` (1,5 MB), que cambia en cada `generate`, así que hay diffs ruidosos en todos los commits.<br>No hay una lista de qué entregar. | Saber qué se entrega y qué es herramienta mía. | Una sección "Entrega" en la guía, o `make deliver` / `apigen package` (`git archive` excluyendo `.claude/`, `graphify-out/`, `security/` y `loadtests/`), según lo que el cliente necesite. |
| **UX-65** | Baja | `createsuperuser --email admin@gym.test` · `new_api.py x`. | `✗ Email no válido`, sin decir por qué (dominio reservado). `✗ nombre inválido: minúsculas, números y guiones`, pero `x` cumple eso: falta decir que el mínimo son 2 caracteres. | Mensajes que expliquen la causa. | Propagar el motivo de email-validator ("dominio reservado/no entregable") y mencionar la longitud mínima. |
| **UX-66** | Baja | Leer `resources/booking.yaml` después de `generate`. | Formato muy verboso: `nullable: false`, `unique: false` también en los campos de entrada de las acciones, donde `unique` no tiene sentido. Además se pierden el estilo `{...}` y los comentarios. | Un spec legible, parecido a lo que escribí. | Omitir los valores por defecto al serializar (`exclude_defaults`), y en las acciones no emitir las claves que no aplican. |

---

## 2. README para clientes (lo que recibe el cliente final)

He leído el README.md generado como si fuera el equipo de frontend del gimnasio. **Se entiende bien.**

- **Bien resuelto:**
  - tabla por recurso con quién puede hacer cada cosa ("El dueño (admins: cualquiera)", "Cualquiera");
  - campos con tipo, reglas y valores por defecto;
  - parámetros del listado y `q` con los campos en los que busca;
  - aviso de que las fechas llevan zona (coincide con el 422 real `timezone_aware`);
  - flujo de refresh con "guarda el par nuevo";
  - tabla de errores con `code`;
  - 404 "(o no es tuyo)".
- **Coincide con el comportamiento real:**
  - `order_by`, filtros y `q`;
  - 409 `has_dependents` al borrar una clase con reservas;
  - "Cancela un trabajo que aún no ha empezado": un trabajo en `running` → 409;
  - admins ven todos los trabajos (27 frente a 5);
  - 429 con `Retry-After`, también en `too_many_pending_jobs`.
- **Se conserva lo mío:** la introducción y el contacto se mantienen al regenerar en `es`→`en`→`es`, y la regeneración es idempotente (`diff` vacío).

### Mejoras concretas

1. **Arranque Docker que funcione tal como está escrito (UX-51).** Proponer `init-env --production` a través de Docker y listar `POSTGRES_PASSWORD`, `ALLOWED_HOSTS` y `CORS_ORIGINS` como obligatorios en producción.
2. **"Primeros pasos" en 4 peticiones, con la respuesta de ejemplo:**
   - registro;
   - login, mostrando `{"access_token", "refresh_token", "token_type": "bearer", "expires_in": 900, "scope": "read write"}`;
   - una llamada autenticada;
   - refresh.

   Hoy solo hay un `curl` de login y el cliente no sabe qué campos va a recibir.
3. **Un ejemplo por recurso**, generado con los `example`/valores por defecto del YAML: `curl` de crear (cuerpo JSON) y de listar con filtro, más la forma de la página `{"items", "total", "limit", "offset"}`. Hoy la forma de la paginación no aparece en ningún sitio.
4. **Acciones síncronas:** decir qué devuelven (hoy solo "Marca la reserva como asistida"). Por ejemplo, con un `returns:`/`response_description:` opcional en el YAML, o al menos "devuelve un objeto JSON". Indicar también si llevan cuerpo (`check_in` no lo lleva).
5. **Acciones en segundo plano:**
   - qué contiene `result` (un `result_description:` en el YAML);
   - que el cuerpo es obligatorio aunque sea `{}` (UX-56);
   - su `rate_limit` propio: `send_reminder` tiene 5/minute y no aparece en ningún sitio.
6. **Sección de trabajos más completa:**
   - campos del job (`status`, `attempts`/`max_attempts`, `result`, `error`, `run_after`, `started_at`, `finished_at`);
   - el estado `cancelled`;
   - parámetros de `GET /jobs` (`status`, `name`, `limit`, `offset`);
   - 409 `job_not_cancellable`;
   - un intervalo de consulta recomendado (1–2 s, o respetar `Location`);
   - que `error` solo muestra mensajes de negocio y el resto sale como "Task failed" tras los reintentos.
7. **Errores de negocio propios.** Mis hooks devuelven `class_full`, `already_booked`, `immutable_class`, `booking_cancelled`, `starts_in_past` y `class_not_found`, pero la tabla de errores está dentro de los marcadores y no puedo añadirlos sin perderlos al regenerar. Propuesta: una clave `errors:` por recurso/acción en el YAML, o un bloque preservado `<!-- apigen:docs:errors -->`, o que `apigen docs` extraiga los `code="…"` de `app/hooks/`.
8. **Separar audiencias.** Hoy se mezclan operación (Docker, `.env`, `pytest`, `db prune`) e integración (auth, endpoints). Propuesta: "Para integrar (frontend/móvil)" primero y "Para desplegar" después. `uv run pytest` sobra en un README de cliente, o debería ir en "Para desarrollar".
9. **URL base y `/docs` en producción.** Un marcador fuera de la zona generada tipo `Base URL: https://api.cliente.com` que `apigen docs` reutilice en los ejemplos en lugar de `http://127.0.0.1:8000`.
10. **Cuentas y roles.** Explicar que el registro crea usuarios con rol `user`, que el primer admin se crea con `createsuperuser` y que se promueve con `PATCH /users/{id}` (`role`). Hoy hay que deducirlo de la tabla.
11. **Idioma (UX-52 y UX-61):** "and" en la versión española, descripciones del YAML en español dentro del README inglés, y `apigen docs` sin `--lang` cambia el idioma.

---

## 3. Hooks y acciones: valoración

- **Meter lógica propia es fácil.** En unos 15 minutos tenía aforo, duplicados, inmutabilidad y check-in sin tocar ni un router. `HookContext` con `session`, `principal` y `user_id`, más `APIError(status, msg, code=)`, cubre el 90 % de los casos. Los errores salen en el formato estándar de la API.
- **Los stubs ayudan de verdad:**
  - cada firma lleva tipos concretos (`BookingCreate`, `Booking`);
  - el docstring dice qué devolver (`data.model_copy(update=…)`, `data.model_fields_set`);
  - la tarea async ya viene con el patrón `ctx.session()` + "no longer exists" → `TaskError`.

  Faltan dos avisos: el `commit` en las acciones síncronas (UX-54) y cómo acceder a datos en `thread`/`process` (UX-53).
- **`generate --force` respeta mi código.** Lo comprobé con el md5 de `app/hooks/booking.py` y `app/tasks/resources/booking.py` antes y después, y es idéntico. Al añadir `cancel` y `export_history` al YAML, `--force` **solo añadió al final** los stubs nuevos ("añadido … (tu código queda intacto)") y registró la tarea. `db migrate` detecta que no hay cambios de modelo y no crea migraciones vacías.
- **El worker se comporta como promete:**
  - 202 inmediato con `Location` y `status_url`;
  - otro usuario → 404;
  - `TaskError` visible sin reintentos;
  - excepción genérica → 2 intentos (10 s de espera) y "Task failed", con la traza solo en el log;
  - 21.º trabajo pendiente → 429 `too_many_pending_jobs` con `Retry-After: 30`;
  - cancelar uno en cola → `cancelled`, y cancelarlo otra vez → 409;
  - `SIGTERM` → "finishing running jobs" y parada limpia;
  - al rearrancarlo con `make worker`, vació 20 informes `process` en unos 12 s.

---

## 4. Lo que me ha gustado

- **`new_api.py` es rápido y limpio:**
  - unos 15 s con `uv sync`, tests, grafo y commit;
  - sin datos personales (`git grep` de sergio, icloud, `/Users/` y "Second Brain" vacío);
  - `.env` con permisos 600 y fuera de git;
  - `JWT_ISSUER`/`JWT_AUDIENCE` y `PROJECT_NAME` renombrados, también con `--title` con acentos y `&`;
  - commit inicial con mi identidad de git;
  - errores claros ("ya existe", nombre inválido);
  - `--dir` crea las carpetas intermedias.
- **Los "siguientes pasos" que imprime el script** son exactamente el flujo de la guía §16.
- **UX-45 resuelto:** el código generado pasa `ruff check` y `ruff format --check` a la primera.
- **La API sigue siendo muy agradable para el cliente:**
  - pistas como `unknown parameter 'search': use q` y `sort … use order_by`;
  - enums y literales listados en el 422;
  - `Input should have timezone info`;
  - la pista de configuración del 429 solo aparece en desarrollo.
- **Estabilidad:** 0 respuestas 5xx y 0 trazas en la API durante todo el recorrido.

---

## 5. Valoración

- **Global: 9 / 10** (igual que en la ronda 5). La plantilla ha ganado mucho con los hooks, las acciones, el worker y `apigen docs`, y todo funciona de principio a fin. No subo la nota por UX-50: un flujo tan natural como "un YAML con varios recursos en `resources/`" acaba con ediciones perdidas en silencio.
- **Flujo "crear API para cliente": 8 / 10.**
  - Crear el proyecto, meter lógica y montar tareas en segundo plano merece un 9,5.
  - Resta:
    - la doble fuente de specs (UX-50);
    - un arranque Docker del README del cliente que no funciona tal como está escrito (UX-51);
    - la falta de documentación para el desarrollador dentro del proyecto (UX-62);
    - lo que le falta al README para que el cliente integre sin abrir `/docs` (sección 2).
  - Con UX-50, UX-51, UX-52 y los puntos 2, 3 y 6 de la sección 2 resueltos, le pondría un 9,5.
