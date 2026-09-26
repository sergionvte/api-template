# Ronda 1 — Informe del usuario (desarrollador nuevo)

**Perfil:** desarrollador que usa la plantilla por primera vez para montar su API. Quiere ir rápido y no es experto en seguridad.
**Fecha:** 2026-09-25
**Entorno:** copia en un directorio temporal (scratchpad `.../scratchpad/ux`), `.venv/bin/apigen` del repo, Python 3.13, SQLite. API arrancada con `uvicorn app.main:app --port 8902` (`ENVIRONMENT=development`, `ACCESS_TOKEN_EXPIRE_MINUTES=1` para probar la expiración). No he tocado el repositorio original.

**Qué he montado:**
- Con `apigen add`: `author` (list/read públicos, búsqueda y orden), `book` (10 campos de casi todos los tipos: str con pattern/unique/index, decimal, int, bool, enum, datetime, fk, json, uuid; filtros, búsqueda, orden y soft delete) y `note` (`--owned`, `write_only`, `immutable`, `--rate-write 5/minute`).
- Con un YAML propio: `review` (owned y lista pública, fk con `on_delete: CASCADE`) y `tag`.
- `db migrate`, `createsuperuser` con `APIGEN_SUPERUSER_PASSWORD`, `version add v2`, `version deprecate v1 --sunset`, `add -v v2`, `remove`, `list`, `check`, `db downgrade/upgrade` y la evolución de un recurso (añadir un campo al YAML, `generate --force` y `migrate`).
- Como cliente (curl/httpx): registro, login, refresh, `/users/me`, logout, logout-all, cambio de contraseña, CRUD, paginación, filtros, búsqueda, orden, errores de validación, expiración y revocación de tokens, bloqueo de cuenta, rate limit, CORS y `/docs` (Swagger se renderiza bien).
- Los tests generados pasan: 98 al principio y 130 tras añadir v2.

---

## Resumen de hallazgos

| ID | Prioridad | Título |
|----|-----------|--------|
| UX-01 | **Alta** | El `.env` que crea `apigen init-env` no arranca (booleanos vacíos) |
| UX-02 | **Alta** | Dos refresh concurrentes con el mismo token devuelven **500** |
| UX-03 | **Alta** | `apigen db migrate` sin cambios en los modelos acaba en traceback |
| UX-04 | **Alta** | No hay README ni guía de primeros pasos |
| UX-05 | Media | La sintaxis de enum `a\|b` que enseña `apigen types` choca con la shell y crea un recurso roto sin avisar |
| UX-06 | Media | Un YAML mal formado muestra un traceback de Python |
| UX-07 | Media | Errores de la CLI en dos idiomas, sin sugerencias y con nombres internos |
| UX-08 | Media | Un recurso nuevo va por defecto a v1 aunque exista v2 (y v1 esté deprecada) |
| UX-09 | Media | Las versiones comparten modelos y schemas: cambiar un recurso cambia también v1 |
| UX-10 | Media | El 409 es genérico: no dice qué campo ni qué restricción ha fallado |
| UX-11 | Media | Tras un soft delete, el valor único sigue ocupado (GET da 404 y POST da 409) |
| UX-12 | Media | Un token caducado y uno inválido dan el mismo error |
| UX-13 | Media | Login en form y refresh/logout en JSON; login con JSON da un error confuso |
| UX-14 | Media | Formato de error inconsistente (string o lista, con o sin `type`, español o inglés) |
| UX-15 | Media | Un PATCH a un campo `immutable` responde "Extra inputs are not permitted" |
| UX-16 | Media | Los parámetros de query desconocidos se ignoran sin avisar |
| UX-17 | Media | CORS vacío en desarrollo: el preflight da 405 sin ninguna pista |
| UX-18 | Media | OpenAPI incompleta: sin `deprecated`, sin 401/403/404/409/429, sin `description`/`example` |
| UX-19 | Media | Dos pestañas refrescando a la vez cierran la sesión (debate de seguridad) |
| UX-20 | Baja | `version list` no muestra el estado de deprecación y `--sunset` acepta fechas pasadas |
| UX-21 | Baja | Detalles de `remove` (cancelar, orden de las comprobaciones) |
| UX-22 | Baja | Detalles de la ayuda de la CLI |
| UX-23 | Baja | `check`, `init-env --production` y avisos duplicados |
| UX-24 | Baja | `db migrate` muy verboso y con mensajes que se contradicen |
| UX-25 | Baja | "No puede contener tu email" confunde |
| UX-26 | Baja | `/` da 404 y detalles de las cabeceras de rate limit |
| UX-27 | Baja | Un admin no puede crear usuarios por la API |
| UX-28 | Baja | `logout` no invalida el access token y `logout-all` sí |

---

## Prioridad Alta

### UX-01 — El `.env` que crea `init-env` no arranca
- **Qué intenté:** lo primero que haría cualquiera: `apigen init-env` y después `apigen check`.
- **Qué pasó:**
  ```
  ✗ 2 validation errors for Settings
  DOCS_ENABLED
    Input should be a valid boolean, unable to interpret input [type=bool_parsing, input_value='', input_type=str]
  LOG_JSON
    Input should be a valid boolean, ...
  ```
  `.env.example` trae `DOCS_ENABLED=` y `LOG_JSON=` vacíos ("Vacío = ..."), pero `Settings` no ignora los valores vacíos. Con ese `.env` falla todo lo que importa la configuración: `check`, el servidor y `db migrate`. `init-env --production` falla igual. Curiosamente, **sin** `.env`, `check` sí funciona.
- **Qué esperaba:** que el `.env` recién generado funcionase a la primera, como promete el propio fichero.
- **Sugerencia:** añadir `env_ignore_empty=True` al `SettingsConfigDict`, o comentar esas dos líneas en `.env.example`. Añadir un test que ejecute `init-env` seguido de `check`.
- **Workaround que usé:** comentar las dos líneas a mano.

### UX-02 — Refresh concurrente → 500 Internal Server Error
- **Qué intenté:** simular lo que hace un frontend con varias peticiones en paralelo: dos o tres llamadas a `POST /auth/refresh` con el mismo refresh token a la vez.
- **Qué pasó:** una devuelve 200 y **el resto 500** en cada intento (6 de 6 rondas: `[200, 500, 500]`). En el log aparece `sqlalchemy.exc.MissingGreenlet` en `app/services/auth.py` (`rotate_refresh_token` → `_revoke_family_for_reuse`). Tras el `session.rollback()`, acceder a `row.user_id` / `row.family_id` intenta recargar el objeto expirado fuera de await. Efecto secundario: la familia **no** se revoca, así que la detección de reutilización tampoco se aplica en este camino.
- **Qué esperaba:** 401 "Invalid refresh token" (o mejor aún, ver UX-19).
- **Sugerencia:** guardar `user_id` y `family_id` en variables locales antes del rollback, o hacer `refresh` de la fila. Añadir un test de concurrencia.

### UX-03 — `apigen db migrate` sin cambios → traceback
- **Qué intenté:** repetir `apigen db migrate -m "..."` "por si acaso", algo muy habitual.
- **Qué pasó:** `AttributeError: 'list' object has no attribute 'path'` (en `apigen/cli.py`, `db_migrate`). Con `skip_empty`, Alembic devuelve `[]` y no `None`, así que nunca se llega al mensaje previsto "Sin cambios en los modelos".
- **Qué esperaba:** "Sin cambios en los modelos: no se creó migración."
- **Sugerencia:** comprobar `if not script:` y, si es una lista, coger el primer elemento.

### UX-04 — Falta un README o guía de inicio
- **Qué pasó:** `README.txt` solo contiene "API Template". Tuve que deducir el flujo a partir de `--help`, `apigen types`, `.env.example`, `examples/shop.yaml` y el código. Cosas que no se pueden descubrir sin leer el código:
  - el login es un formulario OAuth2 (`username`, no `email`), pero refresh y logout son JSON;
  - `APIGEN_SUPERUSER_PASSWORD` no aparece en `createsuperuser --help`;
  - el orden de los pasos: `init-env` → `add`/`generate` → `db migrate` → `createsuperuser` → `run`;
  - el `Makefile` asume `uv`.
- **Sugerencia:** un README con un "quickstart en 5 comandos", un ejemplo de curl para cada endpoint de auth, una tabla de permisos y niveles, y una sección de "problemas comunes" (rate limit en desarrollo, CORS, bloqueo de cuenta).

---

## Prioridad Media

### UX-05 — Enum con `|` en la shell
- **Qué intenté:** copiar de `apigen types` la sintaxis `status:enum=draft|published:default=draft` (en la ayuda aparece sin comillas).
- **Qué pasó:** la shell interpreta `|` como una tubería. `apigen add book -f status:enum=a` se ejecutó **con éxito** y creó `book` con un enum de una sola opción (`choices: [a]`, `max_length: 1`). La salida se perdió en la tubería, así que no me enteré hasta que ejecuté `apigen list`.
- **Sugerencia:** poner comillas en los ejemplos de `types` (`'status:enum=draft|published'`) o aceptar también `,` o `/` como separador. Avisar si un enum tiene solo una opción.

### UX-06 — YAML mal formado → traceback
- **Qué intenté:** un YAML con una llave sin cerrar, y otro en el que añadí un campo en un sitio incorrecto.
- **Qué pasó:** unas 60 líneas de traceback de typer, click y yaml. La información útil (`line 4, column 14`) queda al final.
- **Sugerencia:** capturar `yaml.YAMLError` y mostrar `✗ specs/x.yaml:4:14: se esperaba ',' o '}'`, igual que los demás errores de la CLI.

### UX-07 — Errores de la CLI mejorables
- **Qué intenté:** errores típicos: `title:strng`, `title:string`, `max=abc`, `maxx=100`, `--perm list=everyone`, `--perm delete=owner` sin `--owned` y `--filter titel`.
- **Qué pasó:** todos se detectan (**bien**), pero:
  - Mezclan inglés de Pydantic ("Input should be 'str', 'text'…", "Extra inputs are not permitted") con español.
  - No sugieren nada: con `strng` o `string` no dice "¿quisiste decir `str`?", y con `titel` no dice "¿`title`?".
  - `max=abc` se reporta como `max_length: ...`, el nombre interno y no el que escribí.
  - Algunos mensajes salen con un prefijo `-:` sin sentido (`- -: filters: el campo 'titel' no existe`).
  - `permissions.delete=owner requiere owned: true` habla en términos de YAML cuando yo estaba usando la CLI (`--owned`).
  - En el YAML, un error que depende de otro (filtro `star` inexistente) solo aparece después de arreglar los demás.
- **Sugerencia:** traducir los mensajes de Pydantic más comunes, añadir sugerencias con `difflib.get_close_matches` y usar los nombres de opción de la CLI en los mensajes.

### UX-08 — Recursos nuevos van a v1 aunque exista v2
- **Qué intenté:** después de `version add v2` y `version deprecate v1`, ejecuté `apigen add coupon -f code:str` (en `--dry-run`).
- **Qué pasó:** el recurso se genera **solo en v1**, la versión deprecada. Para que vaya a v2 hay que acordarse de pasar `-v v2`.
- **Qué esperaba:** que por defecto fuese a la última versión (o a todas las no deprecadas), o al menos un aviso.
- **Sugerencia:** usar la última versión por defecto y mostrar "versión: v2" en el resumen de salida.

### UX-09 — Versiones que no aíslan cambios
- **Qué intenté:** añadir `country` a `author` en el YAML y ejecutar `generate --force --only author`.
- **Qué pasó:** se regeneran `v1` y `v2`, y ambas comparten `app/models/author.py` y `app/schemas/author.py`. El contrato de v1 (deprecada) cambia también. `version add` solo copia routers y tests, y además `--force` sobrescribe los endpoints de v2 que yo hubiera editado.
- **Qué esperaba:** entender qué garantiza "versionar". Tal y como está, un cambio incompatible rompe v1.
- **Sugerencia:** documentarlo claramente, o permitir schemas por versión (por ejemplo, `app/schemas/v2/author.py`).

### UX-10 — 409 genérico
- **Qué pasó:** autor duplicado, ISBN duplicado y borrar un autor que tiene libros dan todos el mismo mensaje: `{"detail":"Conflict: a unique or reference constraint was violated"}`.
- **Qué esperaba:** poder mostrar en el frontend "Ya existe un libro con ese ISBN" o "No se puede borrar: tiene libros asociados".
- **Sugerencia:** mapear las restricciones conocidas (las del generador) a `{"detail": ..., "code": "unique_violation", "field": "isbn"}` y `{"code": "has_dependents"}`. No hace falta exponer SQL.

### UX-11 — Soft delete y campos únicos
- **Qué pasó:** borré un libro (204). `GET` sobre él da 404, pero crear otro con el mismo ISBN da 409.
- **Sugerencia:** índices únicos parciales (`WHERE deleted_at IS NULL`) en Postgres, o al menos documentarlo y devolver un mensaje específico.

### UX-12 — Token caducado e inválido son indistinguibles
- **Qué pasó:** los dos casos responden `401 {"detail":"Could not validate credentials"}` con `WWW-Authenticate: Bearer`.
- **Qué esperaba:** saber si debo refrescar el token o mandar al usuario al login. Puedo refrescar de forma proactiva gracias a `expires_in` (bien), pero no tengo forma de reaccionar al error.
- **Sugerencia:** `WWW-Authenticate: Bearer error="invalid_token", error_description="token expired"` (RFC 6750) o un `code: "token_expired"`. No revela nada sensible.

### UX-13 — Formatos distintos en auth
- **Qué pasó:**
  - `POST /auth/login` con JSON devuelve 422 "username: Field required / password: Field required", un mensaje desconcertante cuando sí envías `password`.
  - `POST /auth/refresh` con form devuelve 422 "Input should be a valid dictionary…".
  - Con `curl -d 'password=Gato-Azul-Montaña-7'` (UTF-8 sin codificar) el login da **401**, y además **cuenta como intento fallido para el bloqueo**. Con `--data-urlencode` funciona.
- **Sugerencia:** que login acepte también JSON `{email, password}` (manteniendo el form para Swagger y OAuth2), o dar un error explícito del tipo "login espera application/x-www-form-urlencoded con `username` y `password`". Documentar el uso de `--data-urlencode`.

### UX-14 — Formato de errores inconsistente
- **Ejemplos:**
  - `detail` a veces es un string ("Not authenticated") y a veces una lista.
  - Los errores de la política de contraseñas y el de FK (`"Referenced resource not found"`) no traen `type`.
  - Idiomas mezclados: "debe tener al menos 12 caracteres" y "Estos campos no pueden ser null: name" frente a "Field required" y "Email already registered".
- **Sugerencia:** un único formato (por ejemplo RFC 9457 `application/problem+json`, o `{detail, code, errors[]}`) con códigos estables que el frontend pueda traducir, y un solo idioma para los mensajes de la API.

### UX-15 — PATCH a un campo `immutable`
- **Qué pasó:** `PATCH /notes/{id} {"created_for":"otro"}` devuelve `Extra inputs are not permitted`.
- **Sugerencia:** "created_for no se puede modificar después de crearse" (`type: immutable_field`).

### UX-16 — Parámetros desconocidos ignorados
- **Qué pasó:**
  - `GET /authors?page=2&size=2` devuelve la primera página con 20 elementos.
  - `GET /books?pages=387` (un campo que no es filtrable) devuelve todo.
  - En ambos casos la respuesta es 200 y parece que el filtro ha funcionado.
- **Sugerencia:** responder 422 ante parámetros desconocidos, o al menos documentar los filtros en la descripción de la operación. La paginación con `limit`/`offset` y `total` en la respuesta me parece bien.

### UX-17 — CORS en desarrollo
- **Qué intenté:** un preflight desde `http://localhost:3000`, lo primero que hará un frontend.
- **Qué pasó:** `OPTIONS` devuelve 405 "Method Not Allowed", sin cabeceras CORS y sin nada en el log que lo explique.
- **Sugerencia:** con `ENVIRONMENT=development`, permitir por defecto `http://localhost:*` y `127.0.0.1`, o registrar en el log "petición con Origin X rechazada: añade X a CORS_ORIGINS". Explicarlo en `.env.example`.

### UX-18 — OpenAPI y cabeceras de versión
- **Qué pasó:**
  - v1 está deprecada pero ninguna operación tiene `deprecated: true` en OpenAPI (Swagger no la tacha).
  - Solo se documentan las respuestas 200 y 422; faltan 401, 403, 404, 409 y 429, así que los clientes generados no las tipan.
  - La `description` del recurso ("Reseñas de libros") y el `example` de los campos (el ISBN) se guardan en el YAML pero no llegan a OpenAPI.
  - `info` no tiene descripción.
  - Hay una cabecera `Sunset: 2027-01-01` (RFC 8594 pide HTTP-date, `Fri, 01 Jan 2027 00:00:00 GMT`) y `Deprecation: true` (RFC 9745 usa `@<epoch>`).
- **Sugerencia:** propagar `deprecated`, `description` y `examples`; declarar `responses` comunes en el router generado; corregir el formato de las cabeceras.

### UX-19 — Carrera legítima al refrescar cierra la sesión (debate con seguridad)
- **Contexto:** cuando el refresh concurrente no da 500 (UX-02), la reutilización de un refresh token ya rotado revoca **toda la familia**. Lo comprobé: después de reutilizar el token viejo, el token nuevo tampoco sirve.
- **Problema para el usuario:** una SPA con dos pestañas, o una app móvil que reintenta tras un timeout, reutiliza el token viejo sin mala intención y el usuario queda deslogueado.
- **Sugerencia:** un periodo de gracia corto (por ejemplo 10–30 s), durante el cual el token anterior devuelve el mismo par ya emitido o un 409 sin revocar, o documentar que el cliente debe serializar los refresh.

---

## Prioridad Baja

- **UX-20:** `apigen version list` solo imprime `v1` y `v2`, sin indicar cuál está deprecada ni la fecha de sunset (`/api/versions` sí lo muestra). `--sunset 2020-01-01` (una fecha pasada) se acepta sin aviso. Si deprecas dos veces, la segunda sobrescribe la fecha sin decirlo.
- **UX-21:** `apigen remove book` y responder `n` sale con rc=1 sin ningún mensaje ("Cancelado" estaría bien). `remove author` pide confirmación **antes** de comprobar que `book.author_id` lo referencia; primero pregunta y luego falla.
- **UX-22:** en la ayuda de la CLI:
  - `--no-tests / --no-no-tests` es confuso;
  - `-v` significa versión y no verbose;
  - "Show this message and exit" está en inglés;
  - `createsuperuser --help` no menciona `APIGEN_SUPERUSER_PASSWORD`;
  - sin TTY, `createsuperuser` muestra un `GetPassWarning` y "Aborted." en lugar de sugerir la variable;
  - `add books` (en plural) genera `bookses` sin avisar (sugerencia: "¿'books' es plural? usa `book` o `--plural`").
- **UX-23:**
  - Sin `.env`, el aviso de SECRET_KEY efímera se imprime dos veces.
  - Con `ENVIRONMENT=production`, el error de `check` incluye ruido de Pydantic (`[type=value_error, input_value={'PROJECT_NAME': ...}]`).
  - `init-env --production` solo cambia `ENVIRONMENT`: luego `check` falla por `ALLOWED_HOSTS`. Estaría bien que avisara de lo que falta por rellenar (hosts, CORS, DATABASE_URL de Postgres, Redis).
- **UX-24:** `db migrate` vuelca unas 25 líneas de `INFO [alembic...]`. Dice "Revísala antes de aplicarla en producción" y acto seguido la aplica, lo cual es correcto en desarrollo pero choca. Tras `generate --force` de un recurso existente sugiere `-m "add author"` aunque sea una modificación. Sin `-m`, la migración falla; un mensaje por defecto (por ejemplo, con la fecha) sería cómodo.
- **UX-25:** `Admin-Pass-2026!xyz` para `admin@example.com`, o `Alice-...` para `alice@...`, se rechaza con "no puede contener tu email", pero lo que contiene es la parte local ("admin" o "alice"). Sería más claro "no puede contener tu nombre de usuario del email ('alice')".
- **UX-26:**
  - `GET /` devuelve 404; un JSON con enlaces a `/docs`, `/api/versions` y `/health` ayudaría en desarrollo.
  - `x-ratelimit-reset` es un epoch con decimales (`1790377561.0000029`).
  - `Retry-After` se envía también en respuestas 200.
  - `/authors/` (con barra final) redirige con 307.
- **UX-27:** no existe `POST /users` para el admin (da 405). Con `ALLOW_REGISTRATION=false`, la única forma de crear usuarios es la CLI.
- **UX-28:** `POST /auth/logout` revoca el refresh token pero el access token sigue siendo válido hasta que expira (lo comprobé: 200 en `/users/me`). En cambio, `logout-all` y el cambio de contraseña sí lo invalidan (gracias a `ver`). Es aceptable con JWT, pero conviene documentarlo porque parece inconsistente.

---

## Medidas de seguridad que me estorbaron (para debatir)

| # | Medida | Cómo me afectó | Propuesta |
|---|--------|----------------|-----------|
| S-1 | `RATE_LIMIT_REGISTER=5/hour` por IP, y cuenta también los registros rechazados por la política de contraseñas | En desarrollo me quedé **bloqueado una hora** tras 3 intentos con contraseña débil y 2 válidos. El 429 solo dice "5 per 1 hour". Con el almacenamiento en memoria, la única salida es reiniciar el servidor o cambiar la configuración | Límites más holgados con `ENVIRONMENT=development`, no contar los 422, o que el 429 mencione la variable a cambiar |
| S-2 | Bloqueo de cuenta (5 fallos → 15 min) con mensaje ambiguo "Invalid credentials or account temporarily locked" | Con la contraseña correcta seguía recibiendo 401 y no sabía que estaba bloqueado. Además, los 401 por UTF-8 mal codificado (UX-13) cuentan como fallos. Cualquiera que conozca un email puede bloquear esa cuenta | Entiendo la ambigüedad (no revelar si la cuenta existe). Al menos: avisar por email o log al usuario, documentar `POST /users/{id}/unlock` (que funciona bien) y valorar un bloqueo progresivo en lugar de fijo |
| S-3 | Revocación de toda la familia al reutilizar un refresh token | Riesgo de deslogueos "fantasma" en SPAs y apps móviles (UX-19) | Periodo de gracia |
| S-4 | Contraseña no puede contener la parte local del email | Rechazó "Alice-Clave-Larga-1" para alice. Razonable, pero el mensaje confunde (UX-25) | Mejorar el mensaje |
| S-5 | `extra="forbid"` en todos los schemas | Bien para seguridad (impide `role`/`owner_id` en el registro o en `/me`), pero produce el error confuso con campos inmutables (UX-15) | Mantenerlo y mejorar los mensajes |
| S-6 | CORS cerrado por defecto | Bloquea el primer frontend local sin ninguna explicación (UX-17) | Valores por defecto para desarrollo |
| — | Login 10/min, límite de 120/min por endpoint, 413 si el body supera 1 MB, CSP | **No me molestaron**: devuelven 429 con `Retry-After` y cabeceras `X-RateLimit-*`, y `/docs` funciona con la CSP | Mantener |

---

## Lo que me gustó

**CLI / generador**
- `apigen types` es una chuleta excelente: tipos, opciones y niveles de permiso en una pantalla.
- `--dry-run`, el "Siguiente paso: apigen db migrate …" tras cada comando, y que la spec se guarde en `resources/<nombre>.yaml` con un comentario que explica cómo regenerarla.
- La validación de la spec es muy completa: FK a recursos inexistentes, permiso `owner` sin `owned`, nombres reservados (`user`, `id`, `class`), filtros y búsqueda sobre campos que no existen, `decimal_places >= max_digits`, límites de rate mal escritos, versiones inexistentes (con el comando para crearlas).
- `apigen list` muestra las rutas, las versiones y los permisos efectivos de cada recurso: muy útil.
- `remove` protege las dependencias y dice cómo borrar la tabla después.
- `createsuperuser` acepta la contraseña por variable de entorno (sirve para CI), aplica la misma política de contraseñas y ofrece `--promote`.
- `check` muestra un resumen de seguridad legible. `init-env` crea el `.env` con permisos 600.
- Los tests se generan con cada recurso y pasan (130 en verde).
- `version add` / `deprecate` es sencillo, y el endpoint `/api/versions` es un buen detalle.

**API resultante**
- Paginación consistente (`{items, total, limit, offset}`) con límites claros (`limit<=100`, `offset<=10000`) y mensajes 422 comprensibles.
- `order_by` validado, con los valores permitidos en el propio error. Búsqueda `q` en varios campos. Los filtros por enum se validan.
- Los decimales se serializan como string (no se pierde precisión), los IDs son UUIDv7 (ordenables) y los timestamps van en UTC con `Z`.
- `owner_id` se asigna solo y no se puede falsificar; los campos `write_only` no se devuelven; 401 y 403 se usan correctamente; los 404 nombran el recurso ("Author not found").
- Tokens: `expires_in` en la respuesta, refresh con rotación, y `logout-all` y el cambio de contraseña invalidan también los access tokens ya emitidos.
- Admin: `unlock`, cambio de rol, y la protección "Cannot remove the last admin".
- Cabeceras `X-Request-ID`, `X-RateLimit-*` y `Retry-After`; 413 cuando el body es demasiado grande; cabeceras `Deprecation`/`Sunset` en v1.
- Swagger UI funciona y el botón Authorize usa el flujo password de OAuth2.

---

## Top 5 para la próxima ronda (según este usuario)
1. UX-01 (`init-env` roto): bloquea el primer minuto de uso.
2. UX-02 (500 en refresh concurrente) junto con UX-19 (periodo de gracia).
3. UX-03 (traceback en `db migrate` sin cambios) y UX-06 (traceback con YAML mal formado).
4. UX-04 (README) con los flujos de auth y la configuración para desarrollo (CORS y rate limits, UX-17 y S-1).
5. Errores de la API más útiles para el frontend: UX-10, UX-12, UX-14 y UX-15.
