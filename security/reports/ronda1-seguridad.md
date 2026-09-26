# Revisión de seguridad — Ronda 1

- **Proyecto:** api-template (plantilla FastAPI + generador `apigen`)
- **Fecha:** 2026-09-25
- **Rol:** experto AppSec (enfoque defensivo)
- **Marco:** OWASP API Security Top 10 (2023) y ASVS 4.0 nivel 2
- **Alcance:** `app/`, `apigen/` (spec, codegen, plantillas, CLI), `Dockerfile`, `docker-compose.yml`, `.env.example`, `examples/shop.yaml`, Alembic.
- **Método:** revisión manual del código y verificación dinámica en el laboratorio (`./security/lab.sh 8901`, 127.0.0.1, modo producción, SQLite, rate limit en memoria, recursos de `examples/shop.yaml`).
- **Scripts de verificación** (en `security/checks/`):
  - `lab_checks.py`: batería general, 101 comprobaciones.
  - `lab_checks_2.py`: bloqueo de cuenta, enumeración, carrera en refresh y respuesta 500.
  - `refresh_race.py`: carrera con dos peticiones simultáneas.
  - `generator_checks.py`: inyección y permisos en `apigen`. Se ejecuta en memoria y no escribe en el proyecto.
- **Estado del código:** no se ha modificado `app/`, `apigen/` ni `tests/`. Los 66 tests siguen pasando.

> Nota del laboratorio: `lab.sh` crea los usuarios con el dominio `@lab.test`. `EmailStr` rechaza ese TLD al serializar la respuesta, así que `/users/me` devolvía 500. Antes de las pruebas cambié el dominio en la BD del laboratorio a `@example.com` con `sqlite3 ... update users ...`. El efecto se documenta en SEC-12.

---

## 1. Resumen ejecutivo

La base es sólida. Estos controles están bien diseñados y los he confirmado en el laboratorio:

- JWT con algoritmo fijado, `kid`, `aud`, `iss` y claims obligatorios.
- Revocación inmediata mediante `token_version`.
- Refresh tokens opacos, guardados como hash y con rotación.
- Scopes.
- Aislamiento entre usuarios con 404 en recursos *owned*.
- Protección contra asignación masiva (`extra="forbid"`).
- Listas blancas para ordenar y filtrar, y escape de `LIKE`.
- Límites de paginación y de tamaño del cuerpo, también con *chunked*.
- Cabeceras de seguridad.
- Errores 422 que no devuelven la entrada.
- Validación estricta de la configuración de producción.
- Generador que no admite inyección de código desde YAML: identificadores validados con regex y literales emitidos con `repr()`.

No hay hallazgos críticos ni altos. Los más relevantes son:

1. **SEC-01 (Media):** con dos peticiones simultáneas de `/auth/refresh` con el mismo token, una recibe **500** y **la familia de sesión no se revoca**. Esto anula la detección de robo de refresh tokens justo en el caso para el que existe. Reproducido 2 de 2 veces.
2. **SEC-02 (Media):** el bloqueo de cuenta lo puede provocar cualquier anónimo con 5 intentos, **también contra el administrador**, y repetirlo cada 15 minutos (DoS de cuenta). Reproducido.
3. **SEC-03 / SEC-04 (Media, teóricos por configuración):** si se siguen las instrucciones de `docker-compose.yml`, el contenedor arranca en `development`, porque el `.env` sobrescribe el `ENVIRONMENT=production` de la imagen. Además, detrás del proxy previsto y sin `TRUSTED_PROXIES`, todos los clientes comparten una IP: el límite de login (10/min) pasa a ser global y HSTS no se envía nunca.

El resto son hallazgos bajos o informativos:

- respuestas 500 sin cabeceras de seguridad;
- enteros sin límite que provocan 500;
- enumeración de emails en el registro;
- configuraciones inseguras que el generador acepta sin aviso;
- unicidad global en recursos *owned*;
- FKs sin control de visibilidad;
- huecos del rate limiting;
- registro de auditoría insuficiente;
- *hardening* del despliegue.

| Severidad | Nº | IDs |
|---|---|---|
| Crítica | 0 | — |
| Alta | 0 | — |
| Media | 4 | SEC-01, SEC-02, SEC-03, SEC-04 |
| Baja | 10 | SEC-05 … SEC-14 |
| Info | 5 | SEC-15 … SEC-19 |

---

## 2. Hallazgos

### SEC-01 — Condición de carrera en la rotación de refresh tokens: 500 y familia no revocada
- **Severidad:** Media. **OWASP:** API2:2023 Broken Authentication. **ASVS:** 3.5.x / 2.x (gestión de sesión).
- **Estado:** reproducido.
- **Evidencia (código):** `app/services/auth.py:197-205`. Si el `UPDATE ... WHERE revoked_at IS NULL` no afecta a ninguna fila (`rowcount != 1`), el código hace `await session.rollback()` y después llama a `_revoke_family_for_reuse(session, row)`.
  - El `rollback()` **expira** todas las instancias ORM, aunque `expire_on_commit=False`.
  - Después, `auth.py:230-233` lee `row.user_id` / `row.family_id`. Eso fuerza una carga perezosa síncrona que falla con `sqlalchemy.exc.MissingGreenlet`.
  - La excepción sale antes de `revoke_family()`.
- **Evidencia (laboratorio)** con `security/checks/refresh_race.py`:
  ```
  códigos=[200, 500]  refresh con el token del ganador después -> 200  (familia NO revocada)
  códigos=[200, 500]  refresh con el token del ganador después -> 200  (familia NO revocada)
  ```
  - Con 5 peticiones simultáneas: `[200, 401, 500, 500, 500]`.
  - En el log del servidor: `sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called ... auth.py line 232, in _revoke_family_for_reuse`.
  - Cuando alguna petición entra por la rama secuencial (`revoked_at` ya fijado), la familia sí se revoca. El fallo aparece en la carrera pura, que es el caso habitual de "cliente legítimo contra atacante con el token robado".
- **Impacto:** si el atacante gana la carrera, el cliente legítimo recibe un 500 (no un 401) y la sesión robada sigue viva. Solo muere si el cliente reintenta con el mismo token. Además hay errores 500 no controlados.
- **Recomendación:**
  1. Guardar `family_id` y `user_id` en variables locales antes de cualquier `rollback()`, o evitar el `rollback()` y hacer la revocación en la misma transacción. Por ejemplo, `UPDATE refresh_tokens SET revoked_at=now WHERE family_id=:fid`, con `fid` capturado al leer la fila.
  2. Cambiar `_revoke_family_for_reuse(session, row)` para que reciba `family_id` y `user_id` como valores, no como objeto ORM.
  3. Añadir un test de concurrencia (`asyncio.gather` de dos refresh) que exija `[200, 401]` y que el token del ganador quede revocado.

### SEC-02 — Bloqueo de cuenta explotable por terceros (DoS de cuenta, incluido admin)
- **Severidad:** Media. **OWASP:** API2:2023 / API4:2023. **ASVS:** 2.2.1 (anti-automatización sin permitir DoS de cuenta).
- **Estado:** reproducido.
- **Evidencia (código):**
  - `app/services/auth.py:64-66`: una cuenta bloqueada rechaza incluso la contraseña correcta.
  - `auth.py:92-111`: el bloqueo se aplica tras `LOGIN_MAX_ATTEMPTS=5` fallos desde cualquier origen, y `failed_login_attempts` vuelve a 0 al bloquear (`auth.py:107`). Así se puede volver a bloquear cada `LOGIN_LOCKOUT_MINUTES=15`.
- **Evidencia (laboratorio):**
  ```
  login legítimo antes del ataque: 200
  login legítimo tras 5 fallos de un tercero: 401 "Invalid credentials or account temporarily locked"
  cuenta admin bloqueable por un anónimo -> login correcto -> 401
  ```
- **Impacto:** para mantener bloqueada una cuenta bastan unas 20 peticiones por hora. Con el límite de 50/hora por IP, una sola IP (o un /64 IPv6) puede tener 2 o 3 cuentas bloqueadas de forma permanente, más cuentas con varias IPs. Afecta al administrador. Conocer el email de la víctima es suficiente (ver SEC-05).
- **Recomendación:**
  - Sustituir el bloqueo duro por *throttling* progresivo por cuenta: retraso exponencial o CAPTCHA/prueba adicional tras N fallos.
  - Contar los fallos por la pareja (cuenta, IP o /64) en lugar de solo por cuenta, o permitir el login con la contraseña correcta desde orígenes que no han fallado.
  - No reiniciar el contador al bloquear; conviene escalarlo.
  - Registrar y alertar los bloqueos de cuentas admin.
  - Documentar `POST /users/{id}/unlock` como procedimiento de recuperación.

### SEC-03 — `docker-compose` puede arrancar en modo development (se saltan las validaciones de producción)
- **Severidad:** Media. **OWASP:** API8:2023 Security Misconfiguration. **ASVS:** 14.1.x.
- **Estado:** teórico. No hay Docker en el entorno. El comportamiento se deduce de la precedencia de Compose: `environment` > `env_file` > `ENV` de la imagen.
- **Evidencia:**
  - `docker-compose.yml:2`: indica `cp .env.example .env`.
  - `docker-compose.yml:7`: `env_file: .env`.
  - `.env.example:10`: `ENVIRONMENT=development`, que sobrescribe `Dockerfile:21` (`ENVIRONMENT=production`).
  - `.env.example:70`: `ALLOWED_HOSTS=*`.
  - `apigen init-env` sin `--production` (`apigen/cli.py:363-364`) también deja `development`.
- **Impacto:** con `development`, `Settings._check_security` (`app/core/config.py:198-211`) no se aplica:
  - `/docs`, `/redoc` y `/openapi.json` quedan expuestos;
  - se aceptan `ALLOWED_HOSTS=*` y `CORS_ORIGINS=*`;
  - `DEBUG=true` no se rechaza.

  Si además `SECRET_KEY` es débil, cada worker genera su propia clave efímera (`config.py:183-188`). La autenticación falla de forma intermitente y el equipo puede "arreglarlo" relajando la configuración.
- **Recomendación:**
  - Fijar `ENVIRONMENT: production` en el bloque `environment:` del servicio `api`, que tiene precedencia sobre `env_file`.
  - Que la imagen se niegue a arrancar si no hay `ENVIRONMENT=production`, salvo que se indique explícitamente lo contrario, por ejemplo con `ALLOW_NON_PRODUCTION=1`.
  - Cambiar el comentario de compose a `apigen init-env --production`.

### SEC-04 — Detrás del proxy inverso sin `TRUSTED_PROXIES`, el rate limit por IP se vuelve global y HSTS no se envía
- **Severidad:** Media. **OWASP:** API4:2023 / API8:2023. **ASVS:** 14.4.5, 2.2.1.
- **Estado:** teórico en despliegue. En el laboratorio se confirmó la mecánica: los límites son por IP del socket y `X-Forwarded-For` se ignora sin `TRUSTED_PROXIES`.
  ```
  X-Forwarded-For no evade el límite (sin TRUSTED_PROXIES) -> 429
  login limitado por IP -> [401, 401, 401, 401, 429, ...]
  ```
- **Evidencia:**
  - `docker-compose.yml:11-12` publica solo en `127.0.0.1:8000`, lo que implica un proxy delante.
  - `.env.example:72` deja `TRUSTED_PROXIES=` vacío.
  - `app/main.py:122-123` solo añade `ProxyHeadersMiddleware` si hay proxies de confianza.
  - `app/core/rate_limit.py:25-41`: la clave es `request.client.host`.
  - `app/core/middleware.py:109,119`: HSTS solo se envía si `scope["scheme"] == "https"`.
  - `config.py:198-211` no avisa de esta combinación en producción.
- **Impacto:** todas las peticiones llegan con la IP del proxy o de la pasarela del bridge de Docker. `RATE_LIMIT_LOGIN` (10/min, 50/h), `RATE_LIMIT_REGISTER` (5/h) y `RATE_LIMIT_REFRESH` pasan a ser cupos compartidos por todos los usuarios, así que un único cliente puede impedir el login y el refresh de todos (DoS trivial). Como el esquema visto es siempre `http`, HSTS no se emite nunca aunque el proxy termine TLS.
- **Recomendación:**
  - En producción, avisar o fallar si `TRUSTED_PROXIES` está vacío y la app no escucha directamente en Internet, o añadir un ajuste explícito `BEHIND_PROXY`.
  - Documentar el CIDR del bridge de compose (p. ej. `172.16.0.0/12`) y enviar `X-Forwarded-Proto`.
  - Permitir forzar HSTS por configuración (`HSTS_FORCE=true`) cuando se sabe que el borde es HTTPS.
  - Pasar `forwarded_allow_ips` de uvicorn de forma coherente.

### SEC-05 — Enumeración de emails en el registro
- **Severidad:** Baja. **OWASP:** API2:2023. **ASVS:** 2.2.x / 3.x (no revelar existencia de cuentas).
- **Estado:** reproducido.
- **Evidencia:** `app/api/v1/endpoints/auth.py:34-37`.
  ```
  registro con email existente: 409 {"detail":"Email already registered"}
  registro con email nuevo:     201
  ```
  El login está bien protegido: mensaje idéntico y tiempo equivalente (mediana 38,6 ms frente a 40,2 ms, sin diferencia apreciable). El registro, en cambio, revela qué emails existen. El límite de 5/h por IP lo frena, pero no lo impide, sobre todo con varias IPs (ver también SEC-04).
- **Impacto:** facilita escoger objetivos para SEC-02 y para *credential stuffing*.
- **Recomendación:** responder siempre igual (202 Accepted con "revisa tu correo") y completar el alta con un email de verificación. Si no se quiere verificación, aceptar el riesgo de forma explícita y documentada.

### SEC-06 — Las respuestas 500 no llevan cabeceras de seguridad ni `X-Request-ID`
- **Severidad:** Baja. **OWASP:** API8:2023. **ASVS:** 14.4.x.
- **Estado:** reproducido.
- **Evidencia:** `app/core/errors.py:51-57,64` registra el handler de `Exception`. Starlette lo instala en `ServerErrorMiddleware`, la capa más externa, fuera de `SecurityHeadersMiddleware` y `RequestContextMiddleware` (`app/main.py:118-123`).
  ```
  cabeceras de la respuesta 500: {'date': ..., 'content-length': '82', 'content-type': 'application/json'}
  (faltan content-security-policy, x-content-type-options, cache-control, x-frame-options, x-request-id)
  ```
- **Impacto:** sin `nosniff`, CSP ni `no-store` en esas respuestas. El `request_id` va en el cuerpo, pero no en la cabecera, lo que complica la correlación en proxies.
- **Recomendación:** capturar las excepciones en un middleware ASGI propio situado dentro de `SecurityHeadersMiddleware`, que convierta `Exception` en un JSON 500. Otra opción es añadir las cabeceras estáticas en `unhandled_handler`. Añadir un test.

### SEC-07 — El código generado no acota los enteros (500 por desbordamiento en BD); NUL en cadenas con PostgreSQL
- **Severidad:** Baja. **OWASP:** API8:2023 (validación de entrada) / API4. **ASVS:** 5.1.3, 5.1.4.
- **Estado:**
  - Enteros: reproducido con SQLite.
  - PostgreSQL (int4 y `\x00`): teórico, no hay PostgreSQL en el entorno.
- **Evidencia:** `apigen/codegen.py:126-129` solo emite `ge/le` si el YAML los define. `table_field` usa `int`, que en PostgreSQL es `INTEGER` (int4).
  ```
  POST /api/v1/products {"stock": 9223372036854775808} -> 500
  log: OverflowError: Python int too large to convert to SQLite INTEGER
  ```
  - En PostgreSQL bastaría con pasar de 2^31-1.
  - Además, PostgreSQL rechaza `\u0000` en `text/varchar` (`DataError`). Ningún esquema lo filtra, incluidos `UserRegister.full_name` y el `username` de `/auth/login`, que llega a `WHERE email = ...`. Eso daría 500 **sin autenticación**.
- **Impacto:** 500 controlables por el cliente y ruido en logs. En shop solo se alcanza como admin (`stock`), pero cualquier recurso generado con `int` sin `le` y escritura `user` o `public` queda expuesto.
- **Recomendación:**
  - En `apigen`, aplicar por defecto `ge=-2**31` y `le=2**31-1` a `int`, o usar `BigInteger` con `±2**63`.
  - Rechazar `\x00` en todos los `str`, con un validador en `StrictInput` o un tipo `SafeStr`.
  - Mapear `sqlalchemy.exc.DataError` a 422 en `errors.py`.

### SEC-08 — El generador acepta sin aviso combinaciones de permisos inseguras
- **Severidad:** Baja. Impacto potencial alto si se usa por error. **OWASP:** API1:2023 BOLA / API5:2023 BFLA.
- **Estado:** reproducido con `generator_checks.py`.
- **Evidencia:** `apigen/spec.py:292-310` solo rechaza `owner` sin `owned`, `create=owner|public` en recursos *owned* y `update/delete=public`. Acepta:
  ```
  owned + update=user, delete=user       -> cualquier usuario modifica/borra filas ajenas
  owned + list/read=public               -> expone filas y owner_id de todos
  owned + list=owner pero read=user      -> el listado aísla, pero GET /{id} no (BOLA por ID)
  no owned + create=public / update=user
  ```
- **Impacto:** los valores por defecto son seguros (owner/admin). Aun así, un error tipográfico o un cambio parcial en el YAML produce BOLA o BFLA sin aviso, y los tests generados pasan igualmente porque ejercitan la configuración elegida.
- **Recomendación:**
  - En recursos `owned`, exigir `allow_shared: true` (o un flag similar) para usar `user` o `public` en read/update/delete.
  - Rechazar que `read` sea más permisivo que `list`.
  - Mostrar un aviso visible en `apigen add/generate` y en `apigen list`.
  - Generar un test que documente la exposición intencionada.

### SEC-09 — Unicidad global en recursos *owned*: oráculo de existencia entre usuarios
- **Severidad:** Baja. **OWASP:** API1:2023 / API3:2023.
- **Estado:** teórico, por análisis de código. En shop no hay campos únicos en recursos *owned*.
- **Evidencia:**
  - `apigen/codegen.py:173-174` emite `unique=True` a nivel de tabla, sin tener en cuenta `owner_id`.
  - `app/core/errors.py:43-48` convierte `IntegrityError` en 409.
- **Impacto:** si un recurso *owned* declara, por ejemplo, `email: {unique: true}`, el usuario B puede averiguar si otro usuario ya guardó ese valor (409 frente a 201). Además, no puede crear el suyo.
- **Recomendación:** en recursos `owned`, generar `UniqueConstraint("owner_id", campo)` en lugar de `unique=True`, y ofrecer `unique: global` como opción explícita. Con `soft_delete`, considerar índices parciales (`WHERE deleted_at IS NULL`).

### SEC-10 — Claves foráneas sin control de visibilidad hacia `user` y hacia recursos de lectura restringida
- **Severidad:** Baja. **OWASP:** API1:2023.
- **Estado:** reproducido con `generator_checks.py` (código generado).
- **Evidencia:** `apigen/codegen.py:296-311`.
  - Las FK con `to: user` se omiten sin más (`continue` en la línea 298).
  - Hacia recursos no *owned*, `ensure_reference` se genera con `owner_id=None`, sin tener en cuenta que el padre pueda tener `read: admin`.
  ```
  FK a recurso solo-admin -> ensure_reference owner_id=None (usuario puede enlazar/sondear): True
  FK a 'user' sin comprobación de referencia: True
  ```
- **Impacto:**
  - Un usuario puede enlazar su fila a cualquier usuario (p. ej. `assignee_id`).
  - La diferencia entre 409 (FK inexistente, a través de `IntegrityError`) y 201 revela si existe un ID de usuario.
  - Un usuario puede referenciar y sondear filas que solo el admin puede leer (422 frente a 201).
- **Recomendación:**
  - Generar el control según el nivel `read` del recurso destino: si es `admin`, solo un admin puede referenciarlo.
  - Para `to: user`, limitar por defecto a `principal.user_id` (o solo admin) o, como mínimo, validar la existencia con `ensure_reference(User, ...)` y responder 422 de forma uniforme.

### SEC-11 — Huecos del rate limiting: rutas inexistentes, fallo abierto con Redis y semántica de los límites
- **Severidad:** Baja. **OWASP:** API4:2023. **ASVS:** 11.1.4 / 13.x.
- **Estado:** parcialmente reproducido.
- **Evidencia:**
  - `app/core/rate_limit.py:89-91`: si no hay endpoint resuelto (404), no se aplica ningún límite.
    ```
    rutas inexistentes también limitadas (200 peticiones anónimas) -> 200x404 0x429
    ```
  - `rate_limit.py:103-107`: si falla el backend (Redis), `enforce_rate_limits` registra el error y **deja pasar la petición**. El *fallback* en memoria de SlowAPI solo se activa desde el decorador (`_check_request_limit`), así que los endpoints sin decorador pueden quedar sin límite por defecto mientras Redis esté caído. Teórico: no hay Redis en el entorno.
  - `rate_limit.py:60-71`:
    - `application_limits` usa la misma `key_func`, así que `RATE_LIMIT_GLOBAL` es un límite por cliente, no global.
    - Con `key_style="endpoint"`, el límite por defecto de 120/min es por endpoint. Confirmado: tras el 429 en `/users/me`, `/orders` seguía respondiendo 200.
  - `rate_limit.py:75,93-98` depende de atributos privados de SlowAPI (`_Limiter__evaluate_limits`, `_route_limits`, ...). Una actualización menor podría desactivar los límites en silencio. El test `test_default_rate_limit_applies_to_included_routers` lo cubre en parte.
- **Impacto:** tráfico anónimo ilimitado contra rutas inexistentes (escaneo, ruido de logs), límites laxos en incidentes de Redis y expectativas de capacidad equivocadas.
- **Recomendación:**
  - Aplicar un límite por IP también a peticiones sin endpoint, en un middleware ASGI o en un handler 404/405.
  - Marcar el storage como caído y usar el limitador en memoria también desde `enforce_rate_limits`.
  - Renombrar o documentar `RATE_LIMIT_GLOBAL` como "por cliente, todos los endpoints".
  - Fijar la versión de `slowapi` con un límite superior y mantener el test de regresión.

### SEC-12 — Serializar `email` como `EmailStr` puede romper `/users/me` y el listado de usuarios
- **Severidad:** Baja. **OWASP:** API8:2023 / API4 (disponibilidad).
- **Estado:** reproducido (artefacto del laboratorio).
- **Evidencia:** `app/schemas/user.py:27` (`UserRead.email: EmailStr`) valida también en la salida. Usuarios con `@lab.test`, creados fuera de la API:
  ```
  GET /api/v1/users/me -> 500
  log: ResponseValidationError ... 'input': 'alice@lab.test' ... special-use or reserved name
  ```
- **Impacto:**
  - Un solo email almacenado que no supere la validación actual (alta por script o migración, o reglas más estrictas en una nueva versión de `email_validator`) provoca 500 en `/me` para ese usuario y en **todo** `GET /users` para el admin.
  - El log incluye el email (`input`), es decir, datos personales en los registros.
- **Recomendación:**
  - Usar `str` en los esquemas de salida y validar solo en la entrada.
  - En `unhandled_handler`, no registrar `ResponseValidationError` con sus valores, o sanearlos.
  - Que `lab.sh` y `createsuperuser` usen dominios válidos (`example.com`).

### SEC-13 — Registro de auditoría insuficiente e inyección de líneas en el formato de texto
- **Severidad:** Baja. **OWASP:** relacionado con API8/API9. **ASVS:** 7.1.3, 7.1.4, 7.2.1, 7.2.2, 7.3.1.
- **Estado:** reproducido.
- **Evidencia:**
  - **Autenticación:** solo se registran el bloqueo (`app/services/auth.py:110`) y la reutilización de refresh (`auth.py:230`). No se registran los logins fallidos ni los correctos (con IP, `user_id` y `request_id`), los cambios de contraseña ni `logout-all`.
  - **Administración:** tampoco se registran las acciones de admin: cambio de rol, desactivación, borrado y desbloqueo (`app/api/v1/endpoints/users.py:116-148`).
  - **Inyección en logs:** el formato de texto (`app/core/logging.py:48-50`, por defecto fuera de producción y en el laboratorio) escribe `scope["path"]` ya decodificado (`app/core/middleware.py:56-60`). Una petición a `/api/v1/x%0aFAKE%20LOG%20admin%20login%20ok` generó:
    ```
    2026-09-25 17:10:17,002 INFO [583f...] app.access: GET /api/v1/x
    FAKE LOG admin login ok 404 0.13ms
    ```
  - En texto, los `extra` (`user_id`, `family_id`) no se imprimen, así que los eventos de seguridad pierden contexto.
- **Impacto:** poca capacidad de detección y de análisis forense, y posibilidad de falsificar líneas en logs de texto. El formato JSON de producción escapa los saltos de línea.
- **Recomendación:**
  - Añadir un logger `app.audit` con eventos estructurados (`auth.login.success/failure`, `auth.password.change`, `admin.user.update/delete/unlock`, `auth.refresh.reuse`) que incluya el actor, el objetivo, la IP y el `request_id`, y nunca secretos.
  - Escapar `\r\n` (con `repr` o `%r`) en el formato de texto.

### SEC-14 — Campos `json` sin límite de tamaño ni profundidad (amplificación de respuesta)
- **Severidad:** Baja. **OWASP:** API4:2023.
- **Estado:** teórico, no medido.
- **Evidencia:** `apigen/codegen.py:89-91` (`dict[str, Any] | list[Any]`) no tiene más límite que `MAX_BODY_SIZE` (1 MiB). Un JSON anidado 100.000 niveles se rechazó correctamente con 400 (verificado), pero una fila puede guardar casi 1 MiB.
- **Impacto:** en un recurso con escritura `user`, un listado con `limit=100` puede serializar unos 100 MiB por petición (CPU, memoria y ancho de banda), hasta 120 veces por minuto por usuario.
- **Recomendación:** añadir `max_bytes` y `max_depth` para `json` en la spec, con un valor por defecto prudente (p. ej. 16 KiB y profundidad 10), validados en el esquema. Estudiar excluir los campos `json` y `text` de los listados o hacerlos opcionales.

### SEC-15 — Política de contraseñas y alta de cuentas (Info)
- **ASVS:** 2.1.7, 2.1.x, 1.x.
- **Evidencia:**
  - `app/core/security.py:64-83`: la lista de contraseñas comunes tiene 16 entradas y no se comprueba contra contraseñas filtradas.
  - El registro está abierto por defecto (`ALLOW_REGISTRATION=true`) y no verifica la propiedad del email: se pueden "ocupar" emails ajenos.
  - Lo positivo: longitud mínima de 12, sin reglas de composición, bloqueo de contraseñas que contienen el email y límite de longitud frente a DoS con Argon2.
- **Recomendación:** usar una lista amplia (top 100k) o k-anonimato con HIBP (opcional y configurable), añadir verificación de email y valorar dejar `ALLOW_REGISTRATION=false` por defecto en la plantilla de producción.

### SEC-16 — El access token sobrevive a `/logout` y a la detección de reutilización (Info)
- **Evidencia:** `app/services/auth.py:237-253`: `revoke_family` / `revoke_by_token` no incrementan `token_version`.
  ```
  access token sigue válido tras /logout hasta expirar -> 200
  ```
  Es aceptable por diseño (TTL de 15 minutos), y `logout-all`, el cambio de contraseña y el cambio de rol sí invalidan al instante.
- **Recomendación:** al detectar reutilización de un refresh token, incrementar también `token_version`, porque indica compromiso. Documentar que `/logout` solo cierra la sesión de refresh.

### SEC-17 — Detalles de JWT y de administración (Info)
- **`kid` derivado del secreto:** `app/core/security.py:115-125` usa `sha256(secret)[:16]` y lo publica en cada token. No es explotable con un secreto de 32 caracteres o más, pero el identificador no debería derivarse del secreto. Mejor un `kid` aleatorio o configurable.
- **Claves antiguas sin validar:** `JWT_PREVIOUS_SECRET_KEYS` (`config.py:70`, `security.py:123-124`) no pasa la validación de longitud ni de valores inseguros.
- **Algoritmos asimétricos:** no hay anillo de claves anteriores para RS/ES/EdDSA, es decir, no se puede rotar sin cortar sesiones.
- **"Último admin" con TOCTOU:** `app/api/v1/endpoints/users.py:122-124,146-147`. Dos admins que se degradan a la vez pueden dejar el sistema sin administradores. Se recupera con `apigen createsuperuser --promote`.

### SEC-18 — *Hardening* del despliegue (Info)
- `Dockerfile:3,4,16`: imágenes por etiqueta (`python:3.13-slim`, `uv:0.12`), sin *digest*.
- `Dockerfile:27`: las migraciones se ejecutan al arrancar con el mismo usuario de BD de la aplicación, que por tanto tiene privilegios DDL. Mejor un usuario de migración separado.
- `docker-compose.yml:9,26`: contraseña de PostgreSQL por defecto (`api-dev-password`) si no se define. Redis sin autenticación. Ninguno de los dos publica puertos (bien), pero conviene exigir `POSTGRES_PASSWORD` con `${POSTGRES_PASSWORD:?}` y usar `requirepass` o ACL en Redis.
- Por lo demás, bien: usuario no root, `read_only`, `cap_drop: ALL`, `no-new-privileges`, puerto solo en 127.0.0.1, `--no-server-header`, `--no-proxy-headers`, `.dockerignore` excluye `.env` y `keys`, y `uv.lock --frozen`.
- No se ha podido ejecutar una auditoría de dependencias: no hay `pip-audit` y no descargué herramientas. Recomiendo añadir `pip-audit` o `uv pip audit` en CI.

### SEC-19 — Robustez del generador (Info)
Estado: reproducido con `generator_checks.py`. No son vulnerabilidades, pero producen código que no arranca:

- Un campo filtrable llamado `session`, `principal` o `page` genera `SyntaxError: duplicate argument` (`apigen/codegen.py:206-210`, plantilla del router).
- Un valor de enum `mro` hace fallar la importación (`ValueError invalid enum member name(s) 'mro'`). `_missing_` y similares también son problemáticos (`codegen.py:38-49`).
- `pattern` con *look-around*: `spec.py:146-150` lo valida con `re` de Python, pero pydantic usa el motor Rust, que no lo soporta, y el esquema falla al importar. Contrapartida positiva: no hay riesgo de ReDoS.
- **Recomendación:** añadir esos nombres a `RESERVED_FIELDS`, validar los miembros de enum contra los nombres reservados de `Enum` y validar `pattern` compilándolo con pydantic.

---

## 3. Controles verificados que funcionan correctamente

Verificado en el laboratorio (`lab_checks.py`: 88 OK, 7 FALLO, 6 INFO). Los fallos corresponden a SEC-02, SEC-05, SEC-07 y SEC-11. Hubo además dos falsos negativos de mi script, que ya están corregidos.

**Autenticación y JWT (API2)**
- Payload modificado (`role` o `scope` admin) → 401. `alg=none` → 401. `kid` desconocido, no string, lista, dict o con *path traversal* → 401 sin 500. Token de más de 4096 bytes → 401.
- Un token presente pero inválido se rechaza incluso en endpoints públicos (401).
- Un refresh token no sirve como access token, ni al revés (401/422).
- Claims `aud, exp, iat, iss, jti, nbf, sub, typ, ver`. `typ=access` obligatorio. El rol se toma de la BD, no del token.
- Login: mensaje único y sin diferencia temporal medible entre email existente e inexistente (38,6 ms frente a 40,2 ms). Un login correcto reinicia el contador de fallos.
- Rotación de refresh; la reutilización secuencial revoca toda la familia (el token nuevo también muere); `/logout` revoca el refresh; el límite de sesiones por usuario está en el código.
- Desactivar un usuario invalida su access token al instante (401). Cambio de rol y `logout-all` usan `token_version`.
- El cambio de contraseña exige la actual y revoca todas las sesiones.
- Contraseñas: se rechazan las comunes y las de menos de 12 caracteres. Argon2id con concurrencia limitada.

**Autorización (API1, API3, API5)**
- `orders` (*owned*): bob recibe 404 al leer, modificar o borrar el pedido de alice, y su listado y filtros no incluyen pedidos ajenos. El admin sí los ve.
- `owner_id` lo fija el servidor. `owner_id`, `id` y `role` extra → 422 (`extra="forbid"`), también en PATCH y en `/users/me`.
- Un usuario normal no lista ni modifica usuarios (403) y no crea categorías ni productos (403). Un anónimo recibe 401.
- Scopes: el token `read` no puede escribir (403); un usuario no obtiene el scope `admin` (400).
- Campo `write_only` (`internal_ref`) nunca devuelto. PATCH con `null` en un campo obligatorio → 422.
- FK: producto inexistente o borrado lógicamente → 422 (no 409/500).
- No se puede degradar al último admin (409). El admin no puede borrarse a sí mismo (código).

**Validación de entrada, recursos y errores (API4, API8)**
- Paginación: `limit` entre 1 y 100, `offset` hasta 10000, `order_by` con lista blanca (`Literal`), `q` hasta 100 caracteres → 422 fuera de rango.
- `LIKE`: `%` escapado. Búsqueda con `' OR 1=1 --` sin efecto (consultas parametrizadas).
- Decimal con escala y precisión, precio negativo, `NaN`, datetime sin zona → 422.
- Cuerpo de más de 1 MiB → 413, también con *chunked*. JSON malformado → 422. JSON profundamente anidado → 400. `Content-Type` no JSON → 422.
- Los 422 no reflejan la entrada (`input` eliminado). 404, 405 y UUID inválido responden con mensajes genéricos. Los 500 no filtran detalles, solo el `request_id`.

**Rate limiting**
- Login limitado por IP (10/min, con `Retry-After`) y registro (5/h).
- Límite por defecto de 120/min por usuario autenticado (primer 429 en la petición 121).
- `X-Forwarded-For` ignorado sin proxies de confianza.

**Cabeceras y configuración**
- CSP `default-src 'none'`, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, COOP, CORP, `Permissions-Policy`, `Cache-Control: no-store`, sin `Server`, `X-Request-ID` saneado.
- `Host` no permitido → 400.
- `/docs`, `/redoc` y `/openapi.json` → 404 en producción.
- La app no arranca en producción con `SECRET_KEY` débil, `CORS *`, `hosts *` o `DEBUG` (código). CORS sin credenciales por defecto.

**Generador (`generator_checks.py`)**
- Descripciones, *patterns*, enums y *defaults* JSON con comillas, `"""` y saltos de línea no inyectan código: solo aparecen dentro de literales `repr()` y el resultado compila.
- Se rechazan nombres de campo y de recurso fuera de `^[a-z][a-z0-9_]*$`, palabras clave, `model_*`, `id`, `owner_id`, `../`, y enums con espacios o comillas.
- Permisos por defecto seguros: *owned* → owner; resto → lectura `user` y escritura `admin`. `update/delete=public` prohibidos.
- Las FK hacia recursos *owner-only* se comprueban con el filtro del propietario (evita IDOR a través de FK).
- `yaml.safe_load` y escritura de ficheros solo en rutas derivadas de nombres validados.

---

## 4. Recomendaciones priorizadas

| Prioridad | ID | Acción | Esfuerzo |
|---|---|---|---|
| 1 | SEC-01 | Capturar `family_id`/`user_id` antes del `rollback()` (o eliminarlo) en `rotate_refresh_token`. Añadir test de concurrencia que exija revocación de la familia. | Bajo |
| 2 | SEC-02 | Sustituir el bloqueo duro por *throttling* progresivo por cuenta e IP. No reiniciar el contador al bloquear. Alertar en cuentas admin. | Medio |
| 3 | SEC-03 | `ENVIRONMENT: production` en `environment:` de compose. La imagen falla si no es producción. Corregir el comentario (`init-env --production`). | Bajo |
| 4 | SEC-04 | Validar `TRUSTED_PROXIES` en producción, documentar el CIDR del bridge y la opción para forzar HSTS. | Bajo |
| 5 | SEC-08, SEC-10, SEC-09 | Endurecer `apigen`: rechazar o avisar de permisos incoherentes en *owned*, respetar el nivel `read` del destino en FKs (incluido `user`), unicidad por propietario. | Medio |
| 6 | SEC-07, SEC-14 | Límites por defecto en `int` y `json`, rechazar `\x00`, mapear `DataError` a 422. | Bajo |
| 7 | SEC-06, SEC-12 | Cabeceras de seguridad también en los 500; `str` en esquemas de salida; no registrar datos personales en errores de respuesta. | Bajo |
| 8 | SEC-05, SEC-15 | Registro con respuesta uniforme y verificación de email; lista de contraseñas comprometidas. | Medio |
| 9 | SEC-13 | Logger de auditoría estructurado para eventos de autenticación y administración; escapar CR/LF en el formato de texto. | Bajo |
| 10 | SEC-11 | Límite para rutas sin endpoint, *fallback* de Redis en la dependencia global, documentar la semántica de los límites, fijar la versión de `slowapi`. | Bajo |
| 11 | SEC-16…SEC-19 | Mejoras informativas: `token_version` en reutilización, `kid` no derivado, validación de claves antiguas, digest de imágenes, usuario de migración, `pip-audit` en CI, robustez del generador. | Bajo |

**Pendiente para la ronda 2:**
- Repetir SEC-01, SEC-02 y SEC-06 tras las correcciones con los scripts de `security/checks/`.
- Verificar SEC-03, SEC-04 y SEC-07 (PostgreSQL y NUL) en un entorno con Docker, PostgreSQL y Redis.
- Ejecutar una auditoría de dependencias.
