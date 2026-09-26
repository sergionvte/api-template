# Ronda 3 — Informe del usuario (verificación y respuesta al desarrollador)

- **Perfil:** desarrollador que usa la plantilla por primera vez. Esta vez he seguido **solo** `README.txt` y `guia/README.txt`.
- **Fecha:** 2026-09-25
- **Entorno:**
  - Copia nueva del repositorio en el scratchpad (`.../scratchpad/ux3`), sin tocar el original.
  - Herramientas del `.venv` del repositorio (`apigen`, `pytest`, `python`).
  - API en `127.0.0.1:8902` (`ENVIRONMENT=development`, `ACCESS_TOKEN_EXPIRE_MINUTES=1` para probar la caducidad). El servidor está detenido.
- **Entrada:** `ronda2-desarrollador.md` (decisiones UX-01…UX-28, S-1…S-6 y debate T1…T6).

**Recorrido realizado**

1. Seguí el inicio rápido: `init-env` → `check` → `db upgrade` → `createsuperuser` (sin TTY y con `APIGEN_SUPERUSER_PASSWORD`).
2. Generé cuatro recursos desde un YAML propio: `author`, `book` con soft delete, `note` (owned, unique, immutable, write_only, rate de escritura) y `review` (owned con lectura pública).
3. `db migrate` tres veces seguidas, `version add v2` / `deprecate` / `list`, `add tag` sin `-v`, `remove`, `init-env --production`, errores típicos de la CLI y de YAML.
4. `pytest` sobre la copia: **145 passed**.
5. Como cliente: registro, login, `/me`, refresh concurrente, gracia, logout, bloqueo, caducidad, CRUD con 409/422, parámetros desconocidos, CORS desde localhost, OpenAPI y cabeceras de versión.
6. En el log del servidor: **0 respuestas 5xx y 0 trazas**.

---

## 1. Estado de mis hallazgos de la ronda 1

| UX-ID | Estado | Evidencia |
|---|---|---|
| **UX-01** `.env` de `init-env` no arranca | **Resuelto** | `apigen init-env` seguido de `apigen check` → `✓ Configuración válida` a la primera. |
| **UX-02** Refresh concurrente → 500 | **Resuelto** | 3 refresh simultáneos → `[(200), (409 refresh_token_rotated), (409 refresh_token_rotated)]`. Cero 500 en el log. |
| **UX-03** `db migrate` sin cambios → traceback | **Resuelto** | El segundo y el tercer `migrate` responden `Sin cambios en los modelos: no se creó migración.` (rc=0). Sin `-m` también funciona ("update models 2026-09-25"). |
| **UX-04** Sin README | **Resuelto** | Con el README y la guía he podido hacer todo sin leer código: inicio rápido, curl de auth con `--data-urlencode`, tabla de `code`, pestañas y refresh, bloqueo, CORS, versionado, "Problemas frecuentes". *Matiz: el informe dice "el README ya existía". Cuando hice la ronda 1, `README.txt` solo contenía "API Template" y `guia/` no existía (se creó durante la ronda). No tiene importancia: ahora está muy bien.* |
| **UX-05** Enum con `\|` | **Resuelto** | `types` muestra los ejemplos entre comillas y acepta `enum=a,b`. `add book -f status:enum=a` avisa: `! book.status: el enum solo tiene una opción ('a'); ¿olvidaste las comillas?…` |
| **UX-06** YAML mal formado → traceback | **Resuelto** | `✗ specs/bad.yaml:5:1: YAML no válido: expected ',' or '}', but got '<stream end>'` |
| **UX-07** Errores de la CLI | **Mejorado** | `strng`/`string` → `¿quisiste decir 'str'?`; `titel` → `¿quisiste decir 'title'?`; `max=abc` → `max: debe ser un número entero (recibido 'abc')`; `--perm list=everyone` → `valor 'everyone' no válido (opciones: …)`; `delete=owner` menciona `--owned`; sin prefijo `-:`. **Pendiente:** `maxx=100` → `maxx: opción desconocida` sin sugerir `max`, y mezcla de idiomas en `createsuperuser` (ver UX-32). |
| **UX-08** Recurso nuevo en v1 con v2 activa | **Resuelto** | Tras `version add v2` y `deprecate v1`, `add tag` → `tag: /tags en v2`. En YAML sin `versions:` va a v1: **acepto** la decisión (compatibilidad), y la guía lo dice. |
| **UX-09** Versiones que no aíslan esquemas | **Acepto la decisión** | Queda documentado de forma clara en README §1, guía §6 y `versions.py`, incluido el aviso de que `--force` pisa los cambios de todas las versiones. Es lo que necesitaba saber. |
| **UX-10** 409 genérico | **Resuelto** | `409 {"detail":"A record with the same isbn already exists","code":"unique_violation","fields":["isbn"]}`; borrar un autor con libros → `409 has_dependents`. |
| **UX-11** Soft delete + único | **Resuelto** | Borrar el libro (204) y crear otro con el mismo ISBN → **201**. |
| **UX-12** Caducado frente a inválido | **Resuelto** | Caducado: `401 token_expired` + `WWW-Authenticate: Bearer error="invalid_token", error_description="The access token expired"`. Basura o refresh usado como access: `401 invalid_token`. Sin token: `401 not_authenticated`. |
| **UX-13** Formatos de auth | **Acepto la decisión** / Mejorado | Login con JSON → `415 login_expects_form` "Login expects application/x-www-form-urlencoded with the fields 'username' (your email) and 'password'". Es muy claro. Refresh con form sigue dando el 422 genérico "valid dictionary" (ver UX-37). |
| **UX-14** Formato de errores inconsistente | **Mejorado** | `code` en 401/403/404/405/409/415/422/429, y `type` en todos los 422. **Pendiente:** el 413 no lleva `code` (UX-30), y los errores de política o inmutabilidad perdieron el `loc` del campo (UX-29). |
| **UX-15** PATCH a campo inmutable | **Resuelto** | `422 immutable_field` "These fields cannot be modified after creation: created_for". Mismo patrón para `null_not_allowed`. |
| **UX-16** Parámetros desconocidos ignorados | **Resuelto** (con la decisión parcial aceptada) | `?page=2&size=5` → 422 "unknown parameter 'page': use limit/offset". `?price=5` → "field 'price' is not filterable (filters: author_id, genre)". `?_=123` se ignora: me parece un buen equilibrio. |
| **UX-17** CORS en desarrollo | **Resuelto** | Preflight desde `http://localhost:3000` → 200 con `access-control-allow-origin`. GET desde `localhost:5173` → OK, con `expose-headers` que incluye `Retry-After` y `X-RateLimit-*` (muy buen detalle). `https://evil.com` → 400. Pequeño detalle en UX-32. |
| **UX-18** OpenAPI y cabeceras de versión | **Mejorado** | Hay 34 operaciones de v1 con `deprecated: true`. Los listados y creaciones documentan 401/403/409/422/429. La `description` del recurso y la lista de filtros, búsqueda y orden aparecen en la operación. `examples` en ISBN. `Deprecation: @1790294400` y `Sunset: Wed, 30 Jun 2027 00:00:00 GMT`. **Pendiente:** `tokenUrl` de Swagger apunta a la v1 deprecada, y login/refresh no documentan 401/415/429 (UX-31). |
| **UX-19** Pestañas que cierran la sesión | **Resuelto** | Carrera desde la misma IP → 200 + 409 ×2, y el token del ganador sigue sirviendo. Reutilizar el viejo pasados 12 s (fuera de gracia) → `401 invalid_refresh_token` (revocación). Reutilizar un refresh cerrado con logout **no** afecta a la otra sesión (200). |
| **UX-20** `version list` y `--sunset` | **Resuelto** | `v1  deprecada desde 2026-09-25, retirada 2027-06-30` / `v2  activa`. Fecha pasada → `! La fecha de retirada 2020-01-01 ya ha pasado`. `2027-02-30` → error. Si ya estaba deprecada, lo indica y muestra el sunset anterior. |
| **UX-21** `remove` | **Resuelto** | Con `n` → `Cancelado: no se ha borrado nada.` |
| **UX-22** Ayuda de la CLI | **Mejorado** / acepto el rechazo | `createsuperuser` sin TTY → `✗ Sin terminal interactiva no puedo pedir la contraseña: define APIGEN_SUPERUSER_PASSWORD (y --email).` El `--help` la menciona. `add books` avisa del plural. "Show this message and exit" en inglés: **acepto** que no se traduzca. |
| **UX-23** `check` e `init-env --production` | **Resuelto** | `init-env --production` lista lo que hay que rellenar (ALLOWED_HOSTS obligatorio, CORS, proxies, BD, Redis, registro). `check` → un error limpio `ALLOWED_HOSTS debe enumerar…`, sin ruido de Pydantic, más el aviso de `TRUSTED_PROXIES`. |
| **UX-24** `db migrate` verboso | **Resuelto** (en `migrate`) | Salida de 3–4 líneas: "Ya aplicada en esta BD. Revísala antes de desplegarla en producción." `db upgrade/downgrade` siguen mostrando el INFO de Alembic (UX-33). |
| **UX-25** Mensaje "contiene tu email" | **Resuelto** | "Password must not contain the first part of your email ('alice')". |
| **UX-26** `/`, cabeceras y 307 | **Resuelto** / acepto el 307 | `GET /` → `{"name":…,"docs":"/docs","versions":…,"health":…}`. `x-ratelimit-reset: 1790379901` es un entero, y ya no hay `Retry-After` en los 200. |
| **UX-27** Admin crea usuarios | **Resuelto** | `POST /api/v2/users` (admin) → 201, y queda en `app.audit` (`admin.user.create`). |
| **UX-28** `logout` frente a `logout-all` | **Acepto la decisión** | Está documentado en la tabla de endpoints, la guía y los riesgos aceptados. |
| **S-1** Límite de registro | **Mejorado** | Los 422 de política ya no cuentan: con 4 contraseñas débiles seguidas pude registrarme después. El 429 trae un `hint` excelente. Pero ver UX-34. |
| **S-2** Bloqueo ambiguo | **Mejorado** / acepto la ambigüedad | 6 fallos de bob desde la misma IP y después su contraseña correcta → **200**. Con un usuario inexistente, el 401 es idéntico. La guía explica el 401 con contraseña correcta. No pude simular una IP desconocida en local (queda cubierto por tests del desarrollador). |
| **S-3** Revocación de familia | **Resuelto** | = UX-19. |
| **S-4** Parte local del email | **Resuelto** | = UX-25. |
| **S-5** `extra="forbid"` | **Acepto la decisión** | `PATCH /me {"role":"admin"}` → 422 `extra_forbidden`. Con el mensaje nuevo de inmutables ya no me molesta. |
| **S-6** CORS cerrado | **Resuelto** | = UX-17. |

**Resumen (34 entradas):** 24 resueltos, 6 mejorados, 4 con la decisión aceptada. Ninguno sigue igual.

---

## 2. Respuesta al debate (T1…T6) y a las decisiones rechazadas o pospuestas

### T1 — Bloqueo inteligente: **me convence**
- El dolor real que yo tenía era "me quedo fuera de mi propia cuenta". Desde mi IP habitual ya no pasa, y lo he comprobado.
- Acepto el 401 ambiguo, porque la guía (§12) lo explica y dice cómo desbloquear.
- **Me sigue preocupando** el titular que entra desde una IP nueva (móvil con datos, viaje, portátil en otra red) mientras alguien ataca su cuenta. El bloqueo escalonado de hasta 240 min es duro, y la única salida es que un admin lo desbloquee.
  - Cuando exista la verificación por email (pospuesta), un enlace de desbloqueo o login por email sería la solución natural. Lo dejaría anotado junto a SEC-05.
  - Mientras tanto, sugiero añadir en `.env.example` una línea sobre cómo bajar `LOGIN_LOCKOUT_MAX_MINUTES` para quien prefiera menos fricción.

### T2 — Gracia de 10 s en el refresh: **me convence**
- El 409 `refresh_token_rotated` es justo lo que un frontend necesita: un código claro que significa "relee y reintenta", y la sesión no se pierde.
- Entiendo que no se reenvíe el mismo par, porque solo se guardan hashes.
- **Petición:** un snippet de cliente en la guía (un interceptor tipo axios/fetch con un mutex o una promesa compartida de refresh, que ante 409 relea el almacenamiento). La mayoría de frontends lo harán mal la primera vez.

### T3 — 409 `email_taken` en el registro: **acepto (y lo prefiero)**
Como usuario prefiero saber que ya tengo cuenta. El argumento de que sin verificación de email la respuesta uniforme no protege me parece correcto.

### T4 — Los 422 no cuentan en el límite de registro: **resuelto a medias para desarrollo**
- Verificado que los 422 ya no cuentan.
- Pero en desarrollo sigue estorbando: con 5/h cuentan tanto los 409 como los registros correctos, y creando alice, bob y carol más dos 409 de prueba me quedé sin cupo. Ver UX-34.
- El `hint` del 429 ("Adjust the RATE_LIMIT_* variables… in-memory counters reset when the server restarts") me habría ahorrado 10 minutos en la ronda 1.

### T5 — 409 con `code` y `fields`: **muy bien**
- Es exactamente lo que pedía. `has_dependents` también.
- La unicidad por propietario en recursos owned tiene sentido: dos usuarios pueden tener una nota "compra" y el mismo usuario no puede repetirla. Comprobado.

### T6 — Formato, idioma y CORS
- **Sin RFC 9457:** acepto. `detail` + `code` es suficiente y no rompe Swagger.
- **API en inglés y cliente que traduce por `code`/`type`:** acepto, es lo coherente.
- **Pero hay un efecto secundario que para mí es un retroceso:** los errores de política de contraseña (y los de inmutable o null) ahora llegan con `loc: ["body"]` en lugar de `["body","password"]`. Mi formulario ya no sabe a qué campo pintar el error. Ver UX-29.
- **CORS de desarrollo:** perfecto.

### Otras decisiones rechazadas o pospuestas que me afectan

| Decisión | Mi postura |
|---|---|
| UX-09 esquemas por versión (pospuesto) | Acepto: con la documentación actual sé a qué atenerme. |
| UX-13 no aceptar JSON en el login | Acepto: el 415 explica exactamente qué enviar. |
| UX-22 no traducir los textos de click | Acepto. |
| UX-26 redirección 307 por barra final | Acepto. |
| UX-07 errores dependientes en una segunda pasada | Acepto: con las sugerencias nuevas casi no se nota. |
| SEC-15 lista de contraseñas filtradas (pospuesto) | Me da igual como usuario, pero anoto que `qwertyuiopas` se acepta (UX-36). |

---

## 3. Puntos nuevos

| ID | Prioridad | Qué intenté | Qué pasó | Qué esperaba / sugerencia |
|---|---|---|---|---|
| **UX-29** | **Media** | Registro con contraseña débil desde un formulario | `{"loc":["body"],"msg":"Password must be at least 12 characters long; is too repetitive","type":"password_policy"}`. Antes era `loc:["body","password"]`. Varios problemas quedan en un solo `msg` unidos por "; " y la segunda frase queda sin sujeto ("; is too repetitive"). Lo mismo pasa con `immutable_field` y `null_not_allowed` (`loc:["body"]`, con los campos solo dentro del texto). | Mantener `loc:["body","password"]` y generar **un error por problema**, porque un validador de modelo también puede construir `line_errors` con `loc` explícito. Para inmutables o null: un error por campo con `loc:["body","<campo>"]`. Así el frontend marca el campo sin tener que parsear texto. |
| **UX-30** | Baja | Body de 2 MB | `413 {"detail":"Request body too large"}` **sin `code`**. El README dice "todas las respuestas de error" y la tabla lista `body_too_large`. | Añadir `code: body_too_large` (probablemente lo emite el middleware de tamaño y no pasa por el handler). |
| **UX-31** | Baja | Botón Authorize de Swagger y cliente generado desde OpenAPI | `tokenUrl` = `/api/v1/auth/login`, la versión **deprecada**. `POST /auth/login` documenta solo 200/422 (faltan 401/415/429) y `/auth/refresh` solo 200/409/422 (falta 401). | Apuntar `tokenUrl` a la versión activa más reciente y declarar las respuestas de auth con `ErrorBody`. |
| **UX-32** | Baja | CLI y `check` en desarrollo | `createsuperuser` → `✗ Contraseña débil: password must not contain…` (español e inglés en la misma línea). `maxx=100` no sugiere `max`. `check` muestra `CORS (ninguno)` aunque en desarrollo se acepta localhost. | Traducir la política en la CLI (o usar el `type`). Pasar las opciones desconocidas por `difflib`. En `check`: `CORS  localhost:* (desarrollo)`. |
| **UX-33** | Baja | `apigen db upgrade` / `downgrade` | Siguen mostrando `INFO [alembic.runtime.migration] Context impl SQLiteImpl…` (solo `migrate` es silencioso). Detalle: la migración del repositorio se llama `20260925_1900_…`, así que en `alembic/versions/` aparece *después* de mis migraciones de las 17:44 aunque sea anterior en la cadena. | Aplicar el mismo modo silencioso a `upgrade`/`downgrade`/`current`. El nombre de fichero es un tema menor, quizá mejor sin hora futura. |
| **UX-34** | Media | Crear usuarios de prueba en desarrollo (alice, bob, carol, dave…) | Con `RATE_LIMIT_REGISTER=5/hour` cuentan los 201 y los 409. Tras 3 registros correctos y 2 duplicados → 429 durante 15 min (según `Retry-After`). | En `ENVIRONMENT=development`, un valor por defecto más holgado (p. ej. 50/hour) o que solo cuenten los 409. En producción, 5/h está bien. El `hint` ya ayuda a salir del paso. |
| **UX-35** | Baja | Blog tal y como recomienda la guía (`--owned --perm list=public --perm read=public`) | `generate` y `list` repiten siempre `! review: list=public en un recurso owned -> cualquiera ve las filas de todos los usuarios (incluido owner_id)`. Es correcto, pero es el patrón que la propia guía recomienda y no hay forma de marcarlo como intencionado. | Una opción en el YAML (`acknowledge: [owned_public]` o `public_owned: true`) que silencie el aviso, o mostrarlo solo al crear el recurso y no en cada `list`. |
| **UX-36** | Baja | Registro con `qwertyuiopas` | 201: se acepta, aunque `password1234` sí se rechaza por común. | Solo lo anoto para cuando se implemente la lista top-100k (SEC-15, pospuesto). No lo considero bloqueante. |
| **UX-37** | Baja | Enviar `text/plain` a un endpoint JSON, o form a `/auth/refresh` | `422 {"loc":["body"],"msg":"Input should be a valid dictionary or object to extract fields from","type":"model_attributes_type"}` | Por coherencia con el 415 del login: `415 expects_json` ("This endpoint expects application/json"). |

---

## 4. Lo que me ha gustado de esta ronda

- **Docs:** el README y la guía ahora son de verdad "copiar y pegar". La sección *Problemas frecuentes* responde a casi todo lo que me atascó en la ronda 1.
- **CLI:** los errores con sugerencias ("¿quisiste decir…?") y los avisos preventivos (enum de una opción, plural, permisos arriesgados) cambian mucho la experiencia.
- **Errores de la API:** `code` estable, `fields` en el 409, `token_expired` frente a `invalid_token` (con RFC 6750), 415 explícito en el login y 422 para `page`/`size` con la alternativa correcta. Un frontend puede reaccionar sin parsear textos.
- **Seguridad sin estorbar:** refresh concurrente sin 500 y sin deslogueos, bloqueo que no afecta al titular, y CORS de desarrollo que funciona a la primera con los headers de rate limit expuestos.
- **Versionado:** `version list` informativo y cabeceras según RFC.
- **Admin y auditoría:** `POST /users` para el admin y log de auditoría legible (`auth.login.success … client_ip=…`).
- **Calidad:** 145 tests en verde sobre mi copia y 0 errores 5xx en todo el recorrido.

---

## 5. Valoración final

**8,5 / 10** (en la ronda 1 le habría puesto un 5: se rompía en el primer minuto con `init-env` y no había documentación).

**Por qué no más:**
- La regresión del `loc` en los errores de contraseña (UX-29).
- El límite de registro sigue siendo incómodo en desarrollo (UX-34).
- Algunos flecos de coherencia: 413 sin `code`, `tokenUrl` en la versión deprecada, idiomas mezclados en la CLI.

Todo eso es menor y rápido de corregir. Con UX-29 y UX-34 resueltos le daría un 9. Hoy, como desarrollador nuevo, sí montaría mi API con esta plantilla.
