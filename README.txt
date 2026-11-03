================================================================================
  API TEMPLATE  ·  Plantilla + generador de APIs con FastAPI
================================================================================

Base robusta, rápida y versionada para construir APIs REST en Python, con un
generador de código (`apigen`) que crea recursos CRUD completos y seguros a
partir de una línea de comandos o de un fichero YAML.

  FastAPI 0.141 · SQLModel (SQLAlchemy 2 async) · Alembic · PyJWT · Argon2id
  SlowAPI (rate limit, memoria o Redis) · Uvicorn (uvloop + httptools) · Locust


--------------------------------------------------------------------------------
1. CARACTERÍSTICAS
--------------------------------------------------------------------------------

  Generador
    - `apigen add` / `apigen generate`: modelo + esquemas + router versionado +
      tests + registro automático, desde CLI o YAML.
    - 13 tipos de campo: str, text, int, float, decimal, bool, date, datetime,
      uuid, email, json, enum y fk (clave foránea).
    - Permisos por acción (public | user | owner | admin), recursos con
      propietario, soft delete, filtros, búsqueda, ordenación y rate limit
      por recurso.
    - Las especificaciones se validan de forma estricta: un YAML malicioso no
      puede inyectar código en los ficheros generados.

  Base de datos
    - Async de extremo a extremo. Cambiar de motor = cambiar DATABASE_URL
      (SQLite para desarrollo, PostgreSQL para producción).
    - Migraciones con Alembic (`apigen db migrate`), UUIDv7 como clave
      primaria (ordenados, no enumerables) y fechas siempre en UTC.

  Seguridad
    - JWT de acceso de vida corta + refresh tokens opacos con rotación y
      detección de reutilización (si se reutiliza uno robado, se revoca la
      sesión completa).
    - Revocación instantánea (logout-all, cambio de contraseña o de rol).
    - Roles y scopes (tokens de solo lectura con `scope=read`).
    - Argon2id con concurrencia limitada, bloqueo de cuenta "inteligente"
      (tras 5 fallos se bloquea para orígenes desconocidos, con duración
      creciente, pero el titular sigue entrando desde una IP donde ya inició
      sesión), respuestas idénticas para "usuario no existe" y "contraseña
      incorrecta".
    - Registro de auditoría estructurado (logger app.audit): logins, bloqueos,
      reutilización de refresh tokens, cambios de contraseña y acciones de admin.
    - Rate limit global, por endpoint y específico en login/registro/refresh;
      por usuario autenticado o por IP (IPv6 agrupada por /64).
    - Aislamiento entre usuarios (404 para filas ajenas) incluso a través de
      claves foráneas; protección contra asignación masiva (extra="forbid").
    - Cabeceras de seguridad (también en los 500), límite de tamaño de body
      (también chunked), Content-Type estricto, errores sin detalles internos
      ni eco de datos, rechazo del carácter NUL y enteros acotados a 64 bits.
    - Validación de configuración: en producción la app no arranca si detecta
      valores inseguros (clave débil, CORS "*", hosts "*", DEBUG...).

  Cuentas y correo (desactivado por defecto; se activa por cliente en .env)
    - Verificación de email (off | optional | required) y recuperación de
      contraseña con tokens de un solo uso (solo su hash en BD), enlaces al
      frontend del cliente (FRONTEND_URL, token en el fragmento #) y
      respuestas que no revelan si una cuenta existe.
    - Correo por la cola del worker con backends intercambiables: console,
      file, smtp (cualquier proveedor), disabled y custom; plantillas es/en con
      la marca del cliente, sobrescribibles en email_templates/. Ver sección 15.

  Versionado
    - /api/v1, /api/v2... `apigen version add v2 --from v1` y
      `apigen version deprecate v1 --sunset AAAA-MM-DD` (cabeceras Deprecation
      y Sunset, y `deprecated` en OpenAPI).
    - Importante: las versiones comparten modelos (tablas) y esquemas; lo que
      se versiona son los routers. Un cambio incompatible en un esquema afecta
      a todas las versiones: para ello crea esquemas propios en la versión
      nueva (p. ej. app/schemas/v2/...) y edita sus endpoints a mano. Ojo:
      `generate --force` regenera los endpoints de TODAS las versiones del
      recurso y pisa los cambios manuales.

  Calidad
    - Tests con pytest (auth, seguridad, usuarios, generador) + tests
      generados automáticamente por cada recurso.
    - Pruebas de estrés con Locust (perfil de rendimiento y perfil con rate
      limit y tráfico hostil).


--------------------------------------------------------------------------------
2. REQUISITOS
--------------------------------------------------------------------------------

  - Python 3.12+ (se usa 3.13) y uv (https://docs.astral.sh/uv/)
  - Opcional: PostgreSQL y Redis para producción, Docker para desplegar.


--------------------------------------------------------------------------------
3. INICIO RÁPIDO
--------------------------------------------------------------------------------

  uv sync                          # instala dependencias
  uv run apigen init-env           # crea .env con una SECRET_KEY aleatoria
  uv run apigen db upgrade         # crea las tablas (users, refresh_tokens)
  uv run apigen createsuperuser    # crea un administrador
  uv run apigen run                # http://127.0.0.1:8000/docs

  Crear un recurso (pon cada -f entre comillas):

  uv run apigen add product \
      -f "name:str:max=120" -f "price:decimal:ge=0" -f "stock:int:default=0" \
      -f "status:enum=draft,published:default=draft" \
      --perm list=public --perm read=public --filter stock --search name
  uv run apigen db migrate -m "add product"
  uv run pytest

  Probar la autenticación con curl (el login es un FORMULARIO OAuth2, no JSON;
  usa --data-urlencode si la contraseña tiene caracteres especiales o acentos):

  curl -X POST localhost:8000/api/v1/auth/register -H 'Content-Type: application/json' \
       -d '{"email":"ana@example.com","password":"una frase larga de paso"}'
  curl -X POST localhost:8000/api/v1/auth/login \
       --data-urlencode username=ana@example.com \
       --data-urlencode 'password=una frase larga de paso'
  #  -> {"access_token", "refresh_token", "expires_in", "scope"}
  curl localhost:8000/api/v1/users/me -H "Authorization: Bearer <access_token>"
  curl -X POST localhost:8000/api/v1/auth/refresh -H 'Content-Type: application/json' \
       -d '{"refresh_token":"<refresh_token>"}'
  curl -X POST localhost:8000/api/v1/auth/logout -H 'Content-Type: application/json' \
       -d '{"refresh_token":"<refresh_token>"}'

  En desarrollo, GET / devuelve enlaces a /docs, /api/versions y /health, y
  CORS acepta cualquier http://localhost:<puerto> si CORS_ORIGINS está vacío.

  O desde YAML (ver examples/shop.yaml):

  uv run apigen generate examples/shop.yaml --migrate


--------------------------------------------------------------------------------
4. ESTRUCTURA
--------------------------------------------------------------------------------

  app/
    main.py              creación de la app, middlewares, versiones
    core/                config, seguridad (JWT/Argon2), permisos, rate limit,
                         middlewares, errores, logging
    db/                  motor async, sesiones, tipos (UTCDateTime, uuid7)
    models/              tablas SQLModel (+ registro para Alembic)
    schemas/             esquemas de entrada/salida (Pydantic)
    crud/base.py         repositorio genérico (filtros, búsqueda, orden,
                         propietario, soft delete)
    services/auth.py     login, bloqueo, emisión/rotación/revocación de tokens
    hooks/               lógica propia por recurso (apigen nunca la sobrescribe)
    tasks/               cola de trabajos, worker y tareas (@task)
    api/deps.py          dependencias: sesión, usuario actual, control de acceso
    api/versions.py      registro de versiones
    api/v1/              router y endpoints de la versión 1
  apigen/                CLI, especificación, generador y plantillas Jinja
  alembic/               migraciones
  resources/             specs YAML de los recursos generados (fuente de verdad)
  examples/              ejemplos de specs
  tests/                 tests (los de recursos se generan en tests/api/vN/)
  loadtests/             Locust: locustfile, modelos de prueba, runner, informes
  security/              laboratorio de auditoría, informes y revisión
  .claude/agents/        agentes de revisión: security-expert, developer, user


--------------------------------------------------------------------------------
5. COMANDOS DE apigen
--------------------------------------------------------------------------------

  apigen add NOMBRE -f campo:tipo[:opciones] ...   crear recurso desde CLI
                                                   (versión por defecto: la
                                                   más reciente no deprecada)
  apigen generate [ruta.yaml|dir] [--force]        generar desde YAML
                  [--no-tests] [--dry-run]
  apigen remove NOMBRE [-y]                        eliminar recurso
  apigen list                                      listar recursos (y avisos
                                                   de permisos arriesgados)
  apigen types                                     tipos y sintaxis de campos
  apigen version add v2 [--from v1]                nueva versión de la API
  apigen version deprecate v1 [--sunset FECHA]     deprecar versión
  apigen version list                              versiones y su estado
  apigen db migrate [-m "mensaje"] [--verbose]     autogenerar y aplicar migración
  apigen db upgrade | downgrade | current | history   (--verbose: log de Alembic)
  apigen db prune                                  política de retención (a
                                                   diario): refresh tokens e IPs,
                                                   tokens de cuenta, envíos,
                                                   trabajos, cuentas sin verificar
                                                   y filas con soft delete
  apigen init-env [--production]                   crear .env (con SECRET_KEY,
                                                   AUDIT_HMAC_KEY, clave de datos
                                                   y contraseñas de BD y Redis)
  apigen secret [--data-key]                       generar SECRET_KEY / clave de
                                                   cifrado de datos (AES-256)
  apigen createsuperuser [--email] [--promote]     crear administrador (sin
                                                   terminal: variable
                                                   APIGEN_SUPERUSER_PASSWORD)
  apigen check                                     validar configuración (y
                                                   las plantillas de correo)
  apigen email test DESTINO [--lang es]            envía YA un correo de prueba
                                                   (errores del proveedor
                                                   explicados)
  apigen email preview [PLANTILLA] [--lang]        HTML/texto en var/mail/preview
  apigen email eject [PLANTILLA|layout] [--lang]   copia plantillas de serie a
                                                   email_templates/ para editarlas
  apigen users verify --email X | --all-existing   marca emails como verificados
                  [--before AAAA-MM-DD] [-y]       (auditado; al pasar a required)
  apigen users review [--inactive-days 90] [--json] revisión de accesos (admins,
                                                   inactivos, bloqueados)
  apigen users export --email X [--out f.json]     exportar los datos de un
                                                   titular (solicitud de acceso)
  apigen users revoke-sessions --email X | --all   cerrar sesiones (incidentes)
  apigen audit verify [logs.json ...]              integridad de la cadena de
                                                   auditoría (logs JSON)
  apigen privacy inventory [--check]               inventario de datos personales
                                                   (docs/DATA_INVENTORY.md)
  apigen run                                       servidor de desarrollo
  apigen serve [--workers N]                       servidor de producción


--------------------------------------------------------------------------------
6. ENDPOINTS INCLUIDOS
--------------------------------------------------------------------------------

  GET    /health/live                 proceso vivo
  GET    /health/ready                base de datos accesible
  GET    /api/versions                versiones disponibles
  POST   /api/v1/auth/register        registro (JSON)
  POST   /api/v1/auth/login           login OAuth2 (form: username, password,
                                      scope opcional)
  POST   /api/v1/auth/refresh         rota el refresh token (JSON)
  POST   /api/v1/auth/logout          cierra una sesión (el access token sigue
                                      valiendo hasta caducar; logout-all no)
  POST   /api/v1/auth/logout-all      cierra todas las sesiones
  GET    /api/v1/auth/features        flujos de cuenta activos (para el frontend)
  POST   /api/v1/auth/password/forgot           pide enlace de recuperación (202
                                                siempre)          [PASSWORD_RESET]
  POST   /api/v1/auth/password/reset/validate   ¿sigue valiendo el token? (204/400)
  POST   /api/v1/auth/password/reset            contraseña nueva con el token (204)
  POST   /api/v1/auth/email/verify              verifica el email o confirma un
                                                cambio de email (204)
  POST   /api/v1/auth/email/verify/resend       reenvía la verificación (202
                                                siempre)      [EMAIL_VERIFICATION]
  GET    /api/v1/users/me             perfil
  PATCH  /api/v1/users/me             editar perfil
  POST   /api/v1/users/me/password    cambiar contraseña
  POST   /api/v1/users/me/email       pedir cambio de email (se confirma con el
                                      enlace enviado a la dirección nueva)
  GET    /api/v1/users                (admin) listar/buscar usuarios
  POST   /api/v1/users                (admin) crear usuario con rol
  GET    /api/v1/users/{id}           (admin)
  PATCH  /api/v1/users/{id}           (admin) rol, estado
  POST   /api/v1/users/{id}/unlock    (admin) desbloquear cuenta
  DELETE /api/v1/users/{id}           (admin)

  Cada recurso generado añade: GET (lista paginada), POST, GET /{id},
  PATCH /{id} y DELETE /{id} bajo /api/vN/<plural>.

  Formato de errores (todas las respuestas de error):
    {"detail": "...", "code": "..."}      detail: texto en inglés o, en los
                                          422, lista [{loc, msg, type}]
  `code` es estable y sirve para decidir qué hacer en el cliente:
    401 not_authenticated | invalid_token (-> login) | token_expired (-> refresh)
        invalid_credentials | invalid_refresh_token
    403 forbidden | insufficient_scope
    404 not_found
    400 invalid_host (cabecera Host fuera de ALLOWED_HOSTS)
        invalid_or_expired_token (enlace de recuperación/verificación malo,
        caducado o usado) | wrong_password | same_email
    403 email_not_verified (login con EMAIL_VERIFICATION=required y la
        contraseña correcta) | password_reset_disabled |
        email_verification_disabled | email_change_disabled
    409 unique_violation (+ "fields") | has_dependents | reference_violation
        email_taken | refresh_token_rotated (ver abajo) | last_admin | self_delete
    413 body_too_large     415 login_expects_form | expects_json
    422 validation_error: lista de errores, uno por problema, con `loc` en el
        campo (p. ej. ["body","password"]) y `type`: password_policy,
        immutable_field, null_not_allowed, null_character, reference_not_found,
        unknown_parameter...
    429 rate_limited (+ Retry-After)     500 internal_error (+ request_id)

  Refresh desde varias pestañas: si dos peticiones usan a la vez el mismo
  refresh token, una recibe el par nuevo y la otra 409 refresh_token_rotated
  (solo si viene de la misma IP y en REFRESH_REUSE_GRACE_SECONDS). Qué hacer
  ante ese 409:
    1. Relee el almacenamiento: si hay un refresh MÁS NUEVO que el que usaste,
       reintenta con él (otra pestaña ya refrescó).
    2. Si no lo hay, llama a POST /auth/logout con el refresh VIEJO y manda al
       usuario al login. Esto revoca la sesión entera: el refresh que se llevó
       quien ganó la carrera (podría ser un atacante en tu red) deja de valer
       al instante, pero su ACCESS token sigue valiendo hasta caducar (como
       mucho ACCESS_TOKEN_EXPIRE_MINUTES), igual que en cualquier logout. Si
       sospechas robo y aún tienes un access token válido, llama además a
       POST /auth/logout-all: invalida también todos los access tokens.
  Lo mejor es no provocarlo: serializa los refresh en el cliente (una sola
  petición de refresh en vuelo y el resto la espera). Ejemplo en la guía
  (guia/README.txt, sección 4).
  Reutilizar un refresh ya rotado fuera de ese caso revoca la sesión entera y
  los access tokens del usuario (se considera robo).

  Borrado y claves foráneas: `on_delete` (CASCADE | SET NULL | RESTRICT) se
  aplica igual con borrado físico que con soft delete. Al borrar lógicamente un
  padre, sus hijos VIVOS se borran lógicamente en cascada (o físicamente si el
  hijo no tiene soft delete), se ponen a NULL, o el DELETE responde 409
  has_dependents (RESTRICT). Detalle en guia/README.txt, sección 2.

  Parámetros de listado: limit, offset, order_by, q y los filtros declarados.
  Un parámetro que es un campo no filtrable, o page/size/sort, da 422 en vez de
  ignorarse; otros desconocidos (p. ej. _=123 anti-caché) se ignoran.


--------------------------------------------------------------------------------
7. CONFIGURACIÓN
--------------------------------------------------------------------------------

  Todo se configura por variables de entorno o .env (ver .env.example, que
  documenta cada variable). Las más importantes:

    ENVIRONMENT            development | testing | production
    SECRET_KEY             >= 32 caracteres (apigen secret)
    DATABASE_URL           sqlite+aiosqlite:///./app.db
                           postgresql+asyncpg://user:pass@host:5432/db
    RATE_LIMIT_STORAGE_URI memory://  |  redis://host:6379/0
    ALLOWED_HOSTS          dominios reales en producción
    CORS_ORIGINS           orígenes del frontend
    TRUSTED_PROXIES        IP/CIDR del proxy inverso (para X-Forwarded-For)
    EMAIL_VERIFICATION     off | optional | required (sección 15)
    PASSWORD_RESET         on | off
    EMAIL_BACKEND          console | file | smtp | disabled | custom
    FRONTEND_URL           URL del frontend del cliente (enlaces de los correos)

  `apigen check` muestra un resumen y avisa de configuraciones débiles.
  Una variable vacía en .env (VAR=) equivale a no definirla (valor por defecto).


--------------------------------------------------------------------------------
8. TESTS, CALIDAD Y PRUEBAS DE CARGA
--------------------------------------------------------------------------------

  uv run pytest                         tests
  make format && make lint              formato (ruff format + fix) y lint
  El código que escribe apigen (generate, add, version deprecate) ya sale
  formateado y limpio para `ruff check` si ruff está instalado (dependencia
  de desarrollo): no hace falta `make format` tras generar.
  ./loadtests/run_loadtest.sh throughput   rendimiento (rate limit off)
  ./loadtests/run_loadtest.sh ratelimit    rate limit + tráfico hostil
    Variables: USERS, SPAWN, DURATION, WORKERS, LOCUST_PROCESSES
    Informes HTML/CSV y log del servidor en loadtests/reports/
    BD: SQLite temporal (se borra al terminar). DATABASE_URL del entorno se
    IGNORA a propósito (la prueba migra, siembra un admin bench-admin@… y
    lanza tráfico hostil). Para otra BD: LOADTEST_DATABASE_URL=...; si su host
    no es local hace falta además LOADTEST_ALLOW_REMOTE_DB=1. Con una BD
    propia, las cuentas bench-* se borran al terminar (las tablas bench_* no).

  Resultados de referencia con el código final (MacBook de 8 núcleos,
  SQLite WAL, 4 workers, Locust en la misma máquina, 60 s):
    throughput: 102.772 peticiones, ~1.710 req/s, mediana 38 ms, p95 180 ms,
                0 fallos, 0 errores 5xx
    ratelimit : 79.970 peticiones, 0 fallos, 0 errores 5xx; todo el tráfico
                hostil rechazado (401/413/422) o frenado (429)
  Con PostgreSQL las escrituras concurrentes escalan bastante mejor.


--------------------------------------------------------------------------------
9. DESPLIEGUE
--------------------------------------------------------------------------------

  apigen init-env --production   # SECRET_KEY y POSTGRES_PASSWORD aleatorias
  # (sin apigen: cp .env.example .env y openssl rand -base64 48 / -hex 24)
  # edita .env: ALLOWED_HOSTS (obligatorio; añade localhost,127.0.0.1 para
  # probar en local), CORS_ORIGINS...
  docker compose up -d --build   API + worker + PostgreSQL + Redis (production)
  El healthcheck de la imagen envía como Host el primer dominio de
  ALLOWED_HOSTS. Sin orquestador, un contenedor unhealthy no se reinicia.
  o bien:
  ENVIRONMENT=production uv run apigen serve --workers 4

  Compose fuerza ENVIRONMENT=production (un .env de desarrollo no desactiva las
  validaciones) y la imagen se niega a arrancar en otro modo salvo
  ALLOW_NON_PRODUCTION=1. En producción SQLite es un error salvo
  ALLOW_SQLITE_IN_PRODUCTION=true.

  Proxy inverso y IP del cliente (importante: la IP decide el rate limit, el
  bloqueo de login y la gracia del refresh):
    - TRUSTED_PROXIES = la IP exacta del proxy. En producción se rechazan
      '*', 0.0.0.0/0, ::/0 y redes más amplias que /8 (y se avisa por encima
      de /16).
    - Compose crea la red `backend` con subred fija 172.30.57.0/24 y confía
      solo en su gateway (172.30.57.1), que es la IP con la que llega un proxy
      que corre en el HOST y conecta a 127.0.0.1:8000. Si el proxy es otro
      contenedor, dale una IP fija en `backend` (ipv4_address) y pon esa.
    - El proxy debe SOBRESCRIBIR X-Forwarded-For (no añadir lo que manda el
      cliente) y enviar X-Forwarded-Proto. nginx:
          proxy_set_header X-Forwarded-For   $remote_addr;
          proxy_set_header X-Forwarded-Proto $scheme;
          proxy_set_header Host              $host;
      Caddy (reverse_proxy) ya lo hace por defecto.
    - Sin TRUSTED_PROXIES detrás de un proxy, todos los clientes comparten la
      IP del proxy (rate limit y bloqueo globales) y no se envía HSTS.

  Lista de comprobación de producción:
    [ ] ENVIRONMENT=production y SECRET_KEY propia (apigen init-env --production)
    [ ] PostgreSQL en DATABASE_URL y `apigen db upgrade`
    [ ] Redis en RATE_LIMIT_STORAGE_URI si hay más de un worker/instancia
    [ ] ALLOWED_HOSTS, CORS_ORIGINS y TRUSTED_PROXIES con valores reales
    [ ] HTTPS terminado en el proxy, que envíe X-Forwarded-Proto (HSTS se
        envía si el esquema visto es https)
    [ ] ¿Registro abierto? (ALLOW_REGISTRATION). Si es público, activa la
        verificación de email (EMAIL_VERIFICATION=required) y añade una lista
        de contraseñas comprometidas (pendiente)
    [ ] Correo (si hay verificación o recuperación): EMAIL_BACKEND=smtp, SMTP_*,
        EMAIL_FROM del dominio del cliente con SPF, DKIM y DMARC, FRONTEND_URL
        https y en CORS_ORIGINS. Prueba: `docker compose exec worker apigen
        email test tu@example.com` (sección 15)
    [ ] `apigen check` sin avisos y `make audit` (dependencias) sin hallazgos,
        también en CI
    [ ] `apigen db prune` programado a diario (retención de IPs)
    [ ] Alerta sobre app.audit: event=auth.account.locked con nivel ERROR
        (admin bloqueado), picos de auth.login.failure / auth.register y los
        eventos de correo con nivel ERROR (email.send.failed: credenciales o
        TLS rechazados; email.suppressed con reason=circuit_open: cortacircuitos)

  Pendiente de verificar en un entorno real (no se pudo en la revisión: no
  había PostgreSQL, Redis ni Docker):
    - PostgreSQL: NUL en parámetros de query -> 422, índices únicos parciales,
      `constraint_name` en el 409, BIGINT.
    - Redis: fallback a memoria si cae y recuperación.
    - Docker/compose: arranque en producción, red `backend`, HSTS y
      X-Forwarded-For detrás del proxy real.


--------------------------------------------------------------------------------
10. SEGURIDAD
--------------------------------------------------------------------------------

  Hardening SOC 2 / ISO 27701 (controles, evidencias, procedimientos y lo que
  le toca al operador): docs/CUMPLIMIENTO_SOC2_ISO27701.md. En breve:
    - Auditoría encadenada con HMAC (AUDIT_HMAC_KEY) en los logs JSON;
      `apigen audit verify` detecta eventos alterados o borrados.
    - GET /users/me/export (acceso y portabilidad) y DELETE /users/me
      (supresión, con contraseña; ALLOW_SELF_DELETION).
    - Retención: `apigen db prune` borra también cuentas sin verificar
      (UNVERIFIED_ACCOUNT_RETENTION_DAYS) y filas con soft delete
      (SOFT_DELETE_RETENTION_DAYS). IP truncada en el log de acceso.
    - Specs: `pii: true` / `sensitive: true` por campo y `purpose:` por recurso.
      Un campo sensitive solo lo leen dueño/admin, no se filtra ni ordena por
      él y se cifra en reposo con AES-256-GCM (DATA_ENCRYPTION_KEY).
    - Inventario de datos: `apigen privacy inventory` (CI lo comprueba).
    - Revisión de accesos (`apigen users review`), respuesta a incidentes
      (`apigen users revoke-sessions`), Redis con contraseña en compose, CI y
      Dependabot (.github/).

  Resumen: security/REVISION_SEGURIDAD.md. Revisión en 4 rondas realizada por
  tres agentes (experto en ciberseguridad, desarrollador y usuario); los
  informes completos de cada ronda están en security/reports/. Para repetirla:
  `./security/lab.sh 8900` levanta un laboratorio aislado y los agentes están
  en .claude/agents/.

  Riesgos aceptados y documentados:
    - Con EMAIL_VERIFICATION=off (por defecto) el registro responde 409
      email_taken si el email existe (enumeración): sin correo no se puede
      avisar al dueño real y una respuesta uniforme empeoraría la UX sin
      ganar seguridad (bastaría con intentar el login). Con optional/required
      el registro responde 202 idéntico para cualquier email (cerrado).
    - Correo "al menos una vez": si el worker cae entre la aceptación del
      proveedor y el registro del envío, un reintento puede duplicar un correo
      (los dos enlaces valen: hasta 3 vigentes por cuenta y propósito).
    - Quien controla el buzón del usuario controla la cuenta (inherente a la
      recuperación por email). La protección del token en el frontend
      (fragmento, Referrer-Policy, sin scripts de terceros) depende del cliente.
    - /logout revoca solo el refresh token; el access token vive hasta que
      caduca (ACCESS_TOKEN_EXPIRE_MINUTES). /logout-all, el cambio de
      contraseña o de rol y la detección de robo sí lo invalidan al instante.
    - La API guarda la IP (o su /64) de cada sesión para el bloqueo
      inteligente y el periodo de gracia del refresh: es un dato personal
      (base legal: interés legítimo en la seguridad de las cuentas).
      Retención: mientras la sesión viva y, después, LOGIN_FAMILIAR_DAYS (30)
      días; `apigen db prune` borra el resto (y cada login purga las filas
      antiguas de ese usuario).
    - Un atacante que comparte IP con el titular (NAT de oficina, wifi) no
      queda afectado por el bloqueo: lo frena RATE_LIMIT_LOGIN por IP.

  Bloqueo de cuenta: tras LOGIN_MAX_ATTEMPTS fallos, la cuenta se bloquea
  LOGIN_LOCKOUT_MINUTES (el doble en cada bloqueo consecutivo, hasta
  LOGIN_LOCKOUT_MAX_MINUTES) para orígenes desconocidos. El mensaje es siempre
  el mismo 401 "Invalid credentials or account temporarily locked" (no revela
  si la cuenta existe). El titular puede seguir entrando desde una IP donde
  inició sesión con su contraseña actual en los últimos LOGIN_FAMILIAR_DAYS;
  eso NO levanta el bloqueo para los demás orígenes. Tras un cambio de
  contraseña, las IPs anteriores dejan de contar como conocidas. Un admin la
  desbloquea con POST /api/v1/users/{id}/unlock; los bloqueos quedan en el log
  app.audit (nivel ERROR si la cuenta es de un admin).


--------------------------------------------------------------------------------
11. GRAFO DE CONOCIMIENTO (graphify)
--------------------------------------------------------------------------------

  El repo incluye un grafo del código y la documentación (graphify-out/) para
  que los asistentes de IA (Claude Code) consulten solo lo relevante en vez de
  leer ficheros enteros: menos tokens y respuestas más precisas.

  uv tool install graphifyy==0.9.58  instalar la CLI (una vez; versión fijada:
                                     no está en uv.lock ni en `make audit`)
  graphify install                   instalar la skill /graphify en Claude Code
  graphify query "how is the refresh token rotated" --budget 1500
                                     consulta acotada (mejor en inglés o con
                                     nombres de símbolos)
  graphify explain "rotate_refresh_token()"        un símbolo y sus vecinos
  graphify path "refresh()" "rotate_refresh_token()"   relación entre dos
  graphify path "login()" "authenticate()"             nodos (llamadas)
  make graph  (= graphify update .)  actualizar tras cambiar código (sin coste)
  /graphify . --update               (en Claude Code) si cambian documentos

  - `path` sigue aristas dirigidas (A llama/importa a B). Si responde "No
    directed path", prueba con --undirected, pero desconfía de caminos que
    pasan por tipos genéricos (p. ej. UTCDateTime): no son relaciones reales.
  - Si un nombre existe en varios ficheros (p. ej. `_refresh_graph()`), explain
    avisa de ambigüedad o elige uno: usa el id completo que muestra el propio
    grafo (p. ej. apigen_project_refresh_graph).
  - El grafo sirve para NAVEGAR EL CÓDIGO (dónde está algo, quién lo llama);
    las recetas de uso están en guia/README.txt, no en el grafo.
  - Puntos ciegos: graphify no indexa apigen/templates/*.j2 (donde vive la
    autorización de los routers generados: require, owner_filter,
    ensure_reference), ni Dockerfile, alembic.ini, Makefile o .env.example.
    Léelos directamente. `ensure_reference()` aparece sin llamadores en el
    grafo porque la usan los routers generados: no es código muerto.
  - apigen add / generate / remove / version add / version deprecate y
    db migrate (si crea migración) actualizan el grafo solos (desactivable con
    APIGEN_NO_GRAPH=1; solo actúan si ya existe graphify-out/graph.json).
    Sin graphify instalado, apigen avisa y `make graph` falla con un mensaje.
  - Tras `apigen version add v2` cada símbolo de recurso aparece dos veces
    (v1 y v2): las consultas gastan más presupuesto.
  - graphify-out/graph.html: visualización interactiva en el navegador.
  - graphify-out/GRAPH_REPORT.md: nodos centrales, comunidades y conexiones.
  - Se versionan graph.json, GRAPH_REPORT.md, manifest.json y las etiquetas;
    la caché y los ficheros locales están en .gitignore. Lo que no debe
    entrar en el grafo se excluye en .graphifyignore. El grafo es un artefacto
    generado: revisa sus cambios en los PR y, si puedes, compruébalo en CI
    (`graphify update . && git diff --exit-code graphify-out/graph.json`).
  - CLAUDE.md y .claude/settings.json (hooks) hacen que Claude Code use el grafo
    automáticamente en este repo. Los hooks son opcionales; en otro equipo,
    regenéralos con `graphify claude install` (guía, sección 1).


--------------------------------------------------------------------------------
12. LÓGICA PERSONALIZADA Y TAREAS EN SEGUNDO PLANO
--------------------------------------------------------------------------------

  Hooks (lógica propia sin perderla al regenerar)
    Cada recurso tiene app/hooks/<recurso>.py con before_/after_ create,
    update y delete. apigen lo crea UNA vez y nunca lo sobrescribe (ni con
    --force); si añades acciones al YAML solo añade al final lo que falte.
    Los endpoints generados llaman a esos hooks.

  Acciones (endpoints extra) en el YAML del recurso:
    actions:
      - name: export_invoice       POST /orders/{id}/export_invoice
        background: true           202 + job_id; lo ejecuta el worker
        executor: async            async | thread | process (CPU intensiva)
        timeout: 600
        max_attempts: 3
        rate_limit: "10/minute"
        fields: {format: {type: str, max_length: 10, default: pdf}}
      - name: summary              síncrona: función en app/hooks/order.py
      - name: reindex              POST /products/reindex
        scope: collection

    Reglas de las acciones (se validan al generar):
    - Nombres reservados: list, read, create, update, delete, get (y los de
      hooks/tareas). Sus permisos usan alias propios (CanAction_<nombre>), que
      nunca pisan los del CRUD.
    - En un recurso owned, una acción de item con permission user/public es un
      error (BOLA) salvo con shared_read: true y read igual de abierto; por
      defecto hereda owner (el dueño; admins: cualquiera).
    - Toda acción valida su cuerpo (campos desconocidos -> 422). Sin campos
      obligatorios el cuerpo se puede omitir.
    - Acción síncrona: si cambia `obj` o la sesión, el endpoint hace el commit.
      No devuelvas obj.model_dump() (incluiría campos write_only).
    - Aviso si una acción en segundo plano no tiene rate_limit (salvo admin).

  Worker (proceso aparte: lo pesado nunca frena la API)
    apigen worker                  (o make worker; docker compose: servicio worker)
    - La cola vive en la base de datos (tabla jobs): sin Redis ni broker.
    - Varios workers a la vez sin duplicar trabajos (SKIP LOCKED en Postgres).
    - Reintentos con espera creciente, timeout por tarea, recuperación si un
      worker muere, límite de trabajos pendientes por usuario (429).
    - Estado: GET /api/v1/jobs/{id} (queued → running → succeeded | failed),
      GET /api/v1/jobs, POST /api/v1/jobs/{id}/cancel. Cada usuario ve solo
      los suyos; los errores internos nunca se muestran (TaskError sí).
    - Tareas propias: app/tasks/resources/<recurso>.py (tu código) o cualquier
      módulo con @task("nombre") importado en app/tasks/__init__.py.
    - Desde un hook: await ctx.enqueue("order.export_invoice", {...}).
    - Contexto: toda tarea puede recibir ctx (ctx.owner_id = quién la pidió,
      ctx.job_id, ctx.attempt); las thread/process lo reciben si declaran
      (ctx, payload). ctx.session() solo en las async: en thread/process pasa
      los datos en el payload.
    - Timeouts: async se cancela; process corre en un proceso por trabajo
      (como mucho JOBS_PROCESS_WORKERS a la vez) que se MATA al vencer y se
      reintenta; un hilo no se puede matar: falla sin reintento (hazla
      idempotente). El timeout cuenta desde que la tarea empieza.
    - Solo el worker que tiene el arrendamiento guarda el resultado.
    - El worker no recibe SECRET_KEY en docker compose (PROCESS_ROLE=worker).
      Su latido (JOBS_HEARTBEAT_FILE) solo se escribe si la BD responde.
    - Configuración: variables JOBS_* en .env.example. Limpieza: apigen db prune.

  Un recurso = un fichero en resources/
    Puedes usar un YAML por recurso o uno con varios (resources: [...]). apigen
    no escribe resources/<recurso>.yaml si el recurso ya está en otro fichero de
    resources/ (ese es su fuente); un recurso definido dos veces es un error, y
    `apigen add` con una definición distinta a la de ese fichero se rechaza.
    `apigen generate resources --force --only a,b` (comas o --only repetido).


--------------------------------------------------------------------------------
13. NUEVA API PARA UN CLIENTE Y DOCUMENTACIÓN DE ENTREGA
--------------------------------------------------------------------------------

  make new-api NAME=cursos-api [LANG=es]
  (= python3 scripts/new_api.py cursos-api --lang es --dir ~/Developer)

  Crea ~/Developer/cursos-api con solo lo necesario para desarrollar y
  entregar: sin informes internos de la plantilla, guía personal, grafo ni
  configuración local (.claude/settings.json). Renombra el proyecto, instala
  dependencias, crea .env (no versionado), pasa los tests, construye el grafo
  (graphify) e inicializa git con un commit inicial.

  Seguridad del script:
  - Exige la plantilla sin cambios sin commit (--allow-dirty para seguir: los
    ficheros nuevos no se copian nunca). Copia SOLO lo versionado.
  - Se niega si la plantilla tiene versionado código de recursos generados.
  - Justo antes del commit revisa TODOS los ficheros de texto a versionar
    (README y grafo incluidos): rutas de usuario, emails que no sean de
    ejemplo (example.com, .test...), claves privadas, sk_live_, AWS, tokens de
    GitHub/Slack/Google, secretos con valor y contraseñas en URLs. Si hay algo,
    no hace commit.
  - El proyecto trae docs/DESARROLLO.txt (referencia de apigen: YAML, hooks,
    acciones, worker, versiones, graphify) y `make deliver` (zip de lo
    versionado sin .claude/, graphify-out/, security/ ni loadtests/).

  Documentación para el cliente (README.md):
    uv run apigen docs [--lang en|es] [--base-url https://api.cliente.com]
  Se genera desde resources/*.yaml, las versiones y .env.example. Primero la
  guía de integración (primeros pasos con la respuesta del login, paginación,
  errores, cuentas y roles, un ejemplo curl por recurso, qué devuelve cada
  acción, trabajos con todos sus estados y el 409 de cancelación), después el
  despliegue (Docker paso a paso con SECRET_KEY, POSTGRES_PASSWORD y
  ALLOWED_HOSTS) y el desarrollo local. Los errores propios de los hooks
  (APIError(..., code="...")) y los mensajes de TaskError se extraen del
  código, así que se conservan al regenerar. Si la API tiene verificación de
  email o recuperación de contraseña (en .env.example o en el .env), añade la
  sección "Correos de cuenta": flujos, formato del enlace, qué debe hacer el
  frontend, errores y la configuración de correo (SPF/DKIM/DMARC). El idioma y la URL base quedan
  en el marcador <!-- apigen:docs:start lang=.. base_url=.. --> y se reutilizan
  si no pasas las opciones. Solo se regenera lo que está entre los
  marcadores; tu introducción y el contacto se conservan.

  Validado con Docker (API + 3 workers + PostgreSQL 17 + Redis 7): 24/24
  comprobaciones de extremo a extremo, 15 trabajos repartidos sin duplicados,
  Redis caído sin errores (fallback a memoria) y healthchecks correctos.


--------------------------------------------------------------------------------
14. PROBAR LA API DESDE POSTMAN
--------------------------------------------------------------------------------

  Importa docs/postman/API.postman_collection.json (File > Import).
  1. Variables de la colección: baseUrl, apiPrefix, email, password
     (escríbelos en "Current value": no se sincronizan con la nube).
  2. Auth > Login (x-www-form-urlencoded): guarda access y refresh token.
  3. Todas las peticiones heredan "Bearer {{accessToken}}"; un script de la
     colección renueva el token automáticamente 30 s antes de que caduque.
  Incluye registro, login de solo lectura (scope=read), refresh, logout,
  logout-all, jobs y health. Verificada con newman contra la API real. Los
  proyectos nuevos la incluyen y apigen docs la menciona en el README del cliente.

  Carpeta Account (recuperación, verificación y cambio de email): copia el token
  del enlace del correo (lo que va tras #token=) en las variables resetToken o
  verifyToken. En local sale en el log de la API (EMAIL_BACKEND=console) o en
  Mailpit (make mail); con EMAIL_BACKEND=file, en el .txt. Las variables se leen
  con pm.variables.get (valen en la colección o en un Environment) y newPassword
  trae un valor de ejemplo. Sin token, esas peticiones comprueban el rechazo
  (400/422). "Reset password" guarda newPassword como password (en el ámbito
  donde esté). Con newman: --env-var resetToken=... --env-var verifyToken=...
  Para newman, ejecuta por partes: --folder Register --folder Login
  --folder Account (la carpeta Auth termina con logout-all).


--------------------------------------------------------------------------------
15. CORREO, VERIFICACIÓN DE EMAIL Y RECUPERACIÓN DE CONTRASEÑA
--------------------------------------------------------------------------------

  Todo desactivado por defecto (EMAIL_VERIFICATION=off, PASSWORD_RESET=off):
  una API ya entregada se comporta igual. Se activa por cliente en su .env;
  nada del correo, dominio ni marca del freelancer queda en el código.

  Configurar un cliente (5-6 variables en .env):
    EMAIL_VERIFICATION=required        off | optional | required
    PASSWORD_RESET=on
    FRONTEND_URL=https://app.cliente.example   los enlaces van SOLO aquí
    EMAIL_BACKEND=smtp
    EMAIL_FROM=no-reply@...            dominio del CLIENTE (SPF, DKIM, DMARC)
    SMTP_HOST / SMTP_PORT / SMTP_SECURITY / SMTP_USER / SMTP_PASSWORD
    Marca: MAIL_BRAND_NAME, MAIL_BRAND_LOGO_URL, MAIL_BRAND_COLOR,
    MAIL_SUPPORT_EMAIL, MAIL_FOOTER; idioma: MAIL_DEFAULT_LANGUAGE, MAIL_LANGUAGES.
  `make new-api NAME=x` acepta --email-verification, --password-reset y
  --frontend-url: la configuración NO secreta (modos, idioma, marca y
  FRONTEND_URL) va a .env.example (versionado, lo recibe el cliente) y al .env;
  remitente y credenciales nunca. `apigen docs` avisa si .env y .env.example no
  coinciden en esos modos. En producción la app y el
  worker NO arrancan si falta el backend o es console/file/memory, si
  EMAIL_FROM falta o es de un dominio de ejemplo, si FRONTEND_URL no es https,
  si una ruta EMAIL_LINK_* no lleva {token} exactamente una vez o si el SMTP
  va sin TLS hacia fuera de localhost.

  Desarrollo:
    - Por defecto EMAIL_BACKEND=console: el correo (con el enlace en su línea)
      sale en el log de la API, y EMAIL_DELIVERY=inline lo envía la propia
      API tras responder (no hace falta el worker).
    - EMAIL_BACKEND=file: .eml, .html y .txt en EMAIL_FILE_DIR (var/mail/).
      Copia los tokens del .txt o del .html: el .eml usa quoted-printable y
      parte las líneas largas.
    - `make mail` levanta Mailpit (compose.mail.yml): bandeja en
      http://localhost:8025 y en .env EMAIL_BACKEND=smtp SMTP_HOST=localhost
      SMTP_PORT=1025 SMTP_SECURITY=none.

  Cómo funciona (seguridad):
    - La API solo ENCOLA un trabajo de sistema (tabla jobs, owner_id vacío):
      forgot/resend responden 202 con el mismo cuerpo y en el mismo tiempo
      exista o no la cuenta. El worker busca la cuenta, aplica el cupo por
      cuenta (60 s entre correos, 3/hora y 10/día, sea cual sea la IP), genera
      el token y envía. El payload del trabajo se vacía al terminar.
    - Tokens opacos de 256 bits con prefijo por propósito (pr_ reset, ev_
      verificación, ec_ cambio de email), solo su SHA-256 en la tabla
      account_tokens, un solo uso con consumo atómico, caducidad (30 min, 48 h,
      60 min) y ligados al email y a la contraseña vigentes.
    - Enlaces: FRONTEND_URL + EMAIL_LINK_RESET / EMAIL_LINK_VERIFY (por defecto
      "/reset-password#token={token}": el fragmento no llega a ningún
      servidor). Nunca desde Host/X-Forwarded-Host. La API solo consume
      tokens por POST (los escáneres de correo abren los enlaces con GET).
    - Reset: cierra todas las sesiones, desbloquea la cuenta, marca el email
      como verificado y envía un aviso de "contraseña cambiada". El cambio
      de contraseña normal también invalida los resets pendientes y avisa.
    - Registro con verificación: 202 idéntico para email nuevo o existente;
      el dueño de uno existente recibe "ya tienes cuenta" y su cuenta no cambia.
    - Cambio de email (POST /users/me/email con la contraseña actual): enlace
      a la dirección nueva, aviso a la antigua al pedirlo y al completarlo;
      al confirmar se cierran las sesiones y se invalidan los tokens.
    - Solo el worker recibe las credenciales SMTP (compose se las quita a la
      API); smtplib con TLS verificado y STARTTLS obligatorio con `starttls`.
    - Logs y auditoría sin tokens, enlaces, cuerpos, credenciales ni emails
      completos. Eventos: auth.password_reset.*, auth.email_verification.*,
      auth.email_change.*, auth.login.unverified, email.suppressed (motivo),
      email.send.failed.
    - Cupos: por cuenta (60 s / 3 por hora / 10 al día para forgot, resend y
      registro repetido; lo mismo para los enlaces de cambio de email), avisos
      de seguridad (EMAIL_NOTICES_PER_ACCOUNT_PER_HOUR) y enlaces de cambio de
      email a una misma dirección (EMAIL_PER_ADDRESS_PER_HOUR). Se serializan
      por cuenta: varios trabajos a la vez no los multiplican. En development
      son más holgados y lo descartado se avisa en el log.
    - Cortacircuitos global con dos presupuestos: EMAIL_MAX_PER_HOUR/DAY (altas,
      "ya tienes cuenta", cambios de email, correos propios) y
      EMAIL_MAX_SECURITY_PER_HOUR/DAY (reset y avisos): una inundación de altas
      no bloquea los resets.
    - Un error de configuración nunca imprime los valores del .env (secretos).
    - Los usuarios que ya existían quedan verificados en la migración;
      createsuperuser y las altas de admin nacen verificados. Si activas
      required más tarde, los registrados con off no lo están: `apigen users
      verify --all-existing [--before AAAA-MM-DD]` (auditado) y `apigen check`
      avisa de cuántos quedan. No hay endpoint de API para esto (REQ-F25).
    - Idioma: el de Accept-Language de cada petición y, si no viene, el guardado
      en users.locale (al registrarse o al usar un enlace); si no, el de
      MAIL_DEFAULT_LANGUAGE.

  Plantillas: de serie en app/email/templates/<lang>/ (es y en; asunto, texto
  y HTML). Las de email_templates/ ganan fichero a fichero (apigen nunca las
  toca): `apigen email eject` las copia, `apigen email preview` las muestra y
  `apigen check` las renderiza todas (una variable inexistente es un error).
  Jinja2 en sandbox con autoescape en HTML.

  Correos propios desde un hook (en una tarea: `async with ctx.session() as s`):
    from app.email import send_email
    await send_email(ctx.session, to=[cliente.email], template="pedido_enviado",
                     context={"codigo": pedido.codigo})   # sale si hay commit
  (plantilla en email_templates/<lang>/pedido_enviado.subject.txt/.txt/.html).
  En hooks/endpoints propios, la dependencia `VerifiedUser`
  (app.api.deps) exige email verificado cuando EMAIL_VERIFICATION no es off.

  Tests sin correos reales: la fixture `mail` activa los flujos con el backend
  memory; `process_pending()` ejecuta los trabajos y `mail` es la lista de
  mensajes "enviados".

  Proveedores: cualquiera con SMTP (SES, Brevo, Mailgun, SendGrid, Postmark,
  Resend, Zoho, Microsoft 365). Si el hosting bloquea 587/465, usa el 2525 del
  proveedor. `apigen email test destino@...` traduce los errores (credenciales,
  TLS, puerto, remitente no verificado). Otro proveedor por API HTTP:
  EMAIL_BACKEND=custom con EMAIL_BACKEND_CLASS=app.<módulo>:<Clase> (una clase
  con `async def send(message)`).

