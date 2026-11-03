================================================================================
  GUÍA PERSONAL · Cómo usar el generador de APIs
================================================================================

Esta guía es para ti: recetas prácticas para crear, cambiar y desplegar APIs
con esta plantilla. El README.txt de la raíz es la documentación "del repo";
aquí va el "cómo lo hago".

Todos los comandos se ejecutan desde la raíz del proyecto. Si no quieres
escribir `uv run` delante de todo, activa el entorno: `source .venv/bin/activate`.


--------------------------------------------------------------------------------
0. LA IDEA EN 30 SEGUNDOS
--------------------------------------------------------------------------------

  1. Describes un recurso (campos, permisos, filtros) en YAML o por CLI.
  2. `apigen` escribe el código: modelo, esquemas, endpoints, tests.
  3. `apigen db migrate` crea la tabla.
  4. El código generado es TUYO: edítalo a mano si necesitas lógica propia.

  La "fuente de verdad" de cada recurso es resources/<nombre>.yaml. Si lo
  editas, regenera con `apigen generate --force --only <nombre>` (ojo: pisa
  los cambios manuales de ese recurso).


--------------------------------------------------------------------------------
1. PROYECTO NUEVO A PARTIR DE LA PLANTILLA
--------------------------------------------------------------------------------

  cp -R api-template mi-api && cd mi-api
  rm -rf .venv resources/*.yaml app.db
  uv sync
  uv run apigen init-env            # .env con SECRET_KEY aleatoria (permisos 600)
  # edita .env: PROJECT_NAME, JWT_ISSUER, JWT_AUDIENCE...
  uv run apigen db upgrade
  uv run apigen createsuperuser --email tu@correo.com
  uv run apigen run                 # abre http://127.0.0.1:8000/docs

  En /docs pulsa "Authorize", mete tu email como username y tu contraseña:
  a partir de ahí puedes probar todos los endpoints desde el navegador.

  Graphify (opcional, ver sección 13). El grafo heredado describe la
  PLANTILLA (incluidos security/reports/ y loadtests/). Para centrarlo en tu
  proyecto:
    uv tool install graphifyy==0.9.58 && graphify install
    graphify claude install           # hooks y sección de CLAUDE.md con tu PATH
    # opcional: añade a .graphifyignore lo que no quieras en el grafo, p. ej.
    #   security/reports/
    #   loadtests/
    rm -rf graphify-out && graphify update .     # solo código (AST, sin coste)
    # o, en Claude Code, /graphify .   (código + documentos, usa el LLM)
  Si no vas a usar graphify: rm -rf graphify-out (apigen deja de tocarlo) y
  quita los hooks de .claude/settings.json.


--------------------------------------------------------------------------------
2. CREAR RECURSOS
--------------------------------------------------------------------------------

  2.1 Desde la línea de comandos

  uv run apigen add task \
      -f "title:str:max=200" \
      -f "description:text:nullable" \
      -f "done:bool:default=false" \
      -f "priority:enum=low,medium,high:default=medium" \
      -f "due_date:date:nullable" \
      --owned --soft-delete \
      --filter done --filter priority --search title --order due_date
  uv run apigen db migrate -m "add task"

  Resultado: /api/vN/tasks (la versión más reciente no deprecada), donde cada
  usuario solo ve y toca SUS tareas.

  Sintaxis de campo:  nombre:tipo[:opción][:clave=valor]   (siempre entre comillas)
  (ver todas con `uv run apigen types`)

    str      title:str:max=200:unique        texto corto (255 por defecto)
    text     body:text:nullable              texto largo
    int      stock:int:ge=0:default=0         (siempre acotado a 64 bits)
    float    rating:float:ge=0:le=5
    decimal  price:decimal:ge=0:digits=10:places=2   (dinero: usa decimal)
    bool     active:bool:default=true
    date     birthday:date
    datetime starts_at:datetime              exige zona horaria (…Z o +02:00)
    uuid     external_id:uuid
    email    contact:email
    json     meta:json:nullable               (máx. 16 KiB, max= para cambiarlo)
    enum     "status:enum=draft,published:default=draft"  (o draft|published,
             pero entre comillas: en la shell | es una tubería)
    fk       category_id:fk=category         (fk=user para apuntar a usuarios)

    Opciones: nullable unique index immutable write_only
              min= max= ge= le= gt= lt= digits= places=
              default= example= pattern= on_delete= description=

    unique     = en recursos --owned es único POR USUARIO; con --soft-delete, un
                 valor borrado se puede reutilizar
    immutable  = se fija al crear y no se puede cambiar con PATCH (422
                 immutable_field)
    write_only = se acepta al escribir pero nunca se devuelve (p. ej. notas
                 internas o datos sensibles)
    pattern    = regex; exige también example= (para los tests)
    on_delete  = qué pasa con esta fila si se borra el padre: CASCADE,
                 SET NULL (exige nullable) o RESTRICT (por defecto si no es
                 nullable). Da igual mayúsculas o minúsculas (cascade, set_null).

  2.1.1 Borrado lógico (--soft-delete) y claves foráneas

  `on_delete` significa lo mismo con borrado físico y con soft delete. Al
  borrar lógicamente un padre (DELETE -> deleted_at), la API aplica a sus hijos
  VIVOS (los ya borrados se ignoran):
    CASCADE   el hijo se borra lógicamente si tiene soft delete (y así sus
              propios hijos), o físicamente si no lo tiene;
    SET NULL  la clave del hijo se pone a NULL;
    RESTRICT  409 has_dependents mientras quede algún hijo vivo (no se borra
              nada). Borra o reasigna antes los hijos.
  Ejemplo: comment.post_id con on_delete: cascade -> al borrar un post sus
  comentarios desaparecen de GET /comments (no quedan huérfanos públicos).
  Notas:
    - Todo ocurre en la misma transacción: o se aplica entero o nada.
    - Un hijo que apunta a un padre ya borrado da 422 reference_not_found.
    - Para "retirar" algo que tiene historial (un producto con pedidos, con
      RESTRICT) no lo borres: usa un campo de estado (active, status).
    - Los hijos borrados lógicamente siguen en la BD: con RESTRICT impiden el
      borrado FÍSICO del padre (409). Y los datos creados antes de este
      comportamiento (comentarios de posts ya borrados) no se corrigen solos:
      límpialos con una migración de datos si hace falta.

  2.2 Desde YAML (recomendado cuando hay varios recursos relacionados)

  Tour completo con TODAS las opciones: examples/cursos.yaml
    (plataforma de cursos: 13 tipos, owned, shared_read, on_delete, acciones...)

  Copia examples/shop.yaml, adáptalo y:
    uv run apigen generate mi_modelo.yaml --migrate

  Puedes simular antes sin escribir nada:
    uv run apigen generate mi_modelo.yaml --dry-run


--------------------------------------------------------------------------------
3. PERMISOS: QUÉ NIVEL ELEGIR
--------------------------------------------------------------------------------

  Cada acción (list, read, create, update, delete) tiene un nivel:

    public   cualquiera, sin login           (catálogos, blogs públicos)
    user     cualquier usuario logueado
    owner    solo el dueño de la fila; admin ve todo (requiere --owned)
    admin    solo administradores

  Valores por defecto (seguros):
    recurso normal : list/read = user,  create/update/delete = admin
    recurso --owned: todo = owner, create = user

  Ejemplos típicos:
    Catálogo público gestionado por admin:
      --perm list=public --perm read=public
    Blog: todos leen, cada autor edita lo suyo:
      --owned --shared-read --perm list=public --perm read=public
      (en YAML: `shared_read: true`; confirma que la lectura compartida es
      intencionada y silencia el aviso)
      OJO, borradores: list/read=public lo expone TODO, también los posts con
      published=false. Opciones:
        a) Filtra en el endpoint generado (app/api/vN/endpoints/posts.py,
           con `published` en filters): en list_posts fuerza los publicados
           salvo para un admin,
             filters={"published": published if principal.is_admin else True}
           y en get_post responde 404 si el post no está publicado y quien lo
           pide no es su dueño (obj.owner_id != principal.user_id) ni admin.
           Añade un test para cada caso (anónimo no ve el borrador).
        b) Deja posts con list/read=owner (cada autor ve sus borradores) y crea
           un endpoint público propio que solo liste published=true.
      Y `unique` en un recurso owned es POR AUTOR: dos autores pueden tener el
      slug "hola-mundo". Si necesitas slugs globales, quita owned del campo
      (unicidad global) o compón la URL con el autor.
    Datos privados por usuario (notas, pedidos):
      --owned

  El generador RECHAZA en un recurso --owned:
    - update/delete=public o user (cualquiera tocaría filas ajenas);
    - read más permisivo que list (p. ej. list=owner, read=user): el listado
      aísla pero GET /{id} no (BOLA). Si de verdad lo quieres, --shared-read.
  Y AVISA (sin bloquear) si list/read son public/user sin --shared-read.
  `apigen list` repite los avisos.

  Claves foráneas: la API comprueba que la fila apuntada existe y que el
  usuario puede verla (422 si no). Si solo un admin puede leer el destino, solo
  un admin puede apuntar a él. Un fk=user acepta cualquier usuario existente;
  si representa "el dueño", usa --owned (owner_id lo pone el servidor).


--------------------------------------------------------------------------------
4. CÓMO LO USA UN CLIENTE (FRONTEND / MÓVIL)
--------------------------------------------------------------------------------

  Registro:
    POST /api/v1/auth/register   {"email": "...", "password": "...(12+)"}
    -> 201 con el usuario; con EMAIL_VERIFICATION optional/required, 202
       {"detail": "Check your inbox to continue"} (igual para cualquier email)
       y el enlace de verificación llega por correo (sección 17).

  Login (formulario OAuth2, no JSON; con JSON responde 415):
    POST /api/v1/auth/login   username=<email>&password=<clave>
    (curl: --data-urlencode username=... --data-urlencode password=...)
    -> {access_token, refresh_token, expires_in, scope}

  Llamadas:  Authorization: Bearer <access_token>

  Cuando el access token caduque (401 con code "token_expired"; cada 15 min
  por defecto; con code "invalid_token" hay que volver al login):
    POST /api/v1/auth/refresh   {"refresh_token": "..."}
    -> devuelve un PAR NUEVO. Guarda siempre el refresh nuevo: el viejo deja
       de valer, y si alguien lo reutiliza se cierra toda la sesión.
    -> 409 "refresh_token_rotated": otra pestaña acaba de refrescar.
         1. Relee el almacenamiento: si hay un refresh más nuevo que el que
            enviaste, reintenta con él.
         2. Si no lo hay, llama a POST /auth/logout con el refresh VIEJO y
            manda al usuario al login. Revoca la sesión entera: el REFRESH de
            quien ganó la carrera (podría ser un atacante) deja de valer, pero
            su ACCESS token vive hasta caducar (ACCESS_TOKEN_EXPIRE_MINUTES).
            Si sospechas robo y tienes un access token válido, llama también
            a POST /auth/logout-all (invalida todos los access tokens).

  Serializa los refresh (una sola petición en vuelo; las demás la esperan).
  Ejemplo con fetch (TypeScript/JavaScript), válido para varias pestañas si
  guardas los tokens en localStorage:

    const API = "/api/v1";
    let refreshing: Promise<string> | null = null;   // refresh en vuelo

    async function refreshAccess(): Promise<string> {
      // Todas las peticiones que caducan a la vez esperan al MISMO refresh.
      refreshing ??= (async () => {
        const sent = localStorage.getItem("refresh_token")!;
        const r = await fetch(`${API}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: sent }),
        });
        if (r.ok) {
          const t = await r.json();
          localStorage.setItem("access_token", t.access_token);
          localStorage.setItem("refresh_token", t.refresh_token);
          return t.access_token;
        }
        const code = (await r.json().catch(() => ({}))).code;
        const latest = localStorage.getItem("refresh_token");
        if (code === "refresh_token_rotated" && latest && latest !== sent) {
          return localStorage.getItem("access_token")!;  // otra pestaña ganó
        }
        // Sin token más nuevo: cerramos la sesión en el servidor con el viejo.
        await fetch(`${API}/auth/logout`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: sent }),
        });
        localStorage.clear();
        throw new Error("login required");
      })().finally(() => { refreshing = null; });
      return refreshing;
    }

    async function api(path: string, init: RequestInit = {}): Promise<Response> {
      const call = (token: string | null) =>
        fetch(`${API}${path}`, {
          ...init,
          headers: { ...init.headers, Authorization: `Bearer ${token}` },
        });
      let r = await call(localStorage.getItem("access_token"));
      if (r.status === 401 && (await r.clone().json()).code === "token_expired") {
        r = await call(await refreshAccess());
      }
      return r;
    }

  (Si otra pestaña refresca justo a la vez, el 409 cae en el caso 1: esa
  pestaña ya guardó el par nuevo en localStorage. Para coordinar pestañas
  con más rigor, usa navigator.locks.request("refresh", ...) alrededor del
  refresh.)

  Logout: POST /auth/logout {"refresh_token": "..."}  (el access token sigue
          valiendo hasta caducar; bórralo en el cliente)
  Cerrar todas las sesiones: POST /auth/logout-all (con Bearer)

  Listas: ?limit=20&offset=0&order_by=-created_at&q=texto&<filtro>=valor
    -> {items, total, limit, offset}

  Token de solo lectura (para dashboards, integraciones):
    login con scope=read  -> ese token no puede crear/editar/borrar.

  Errores: {"detail": ..., "code": "..."}; usa `code` (estable) en el cliente.
  En los 422, `detail` es una lista con un error por problema y `loc` en el
  campo (["body","password"]): pinta cada `msg` junto a su campo.
    401 no autenticado / token inválido o caducado   403 sin permiso o scope
    404 no existe (o no es tuyo)
    409 conflicto: unique_violation (+ "fields": ["isbn"]), has_dependents
        (no se puede borrar: otros registros lo usan), email_taken...
    413 body demasiado grande             415 login sin formulario o cuerpo
                                              que no es JSON
    422 datos inválidos (lista con loc, msg y type por campo)
    429 rate limit (mira la cabecera Retry-After)
  Tabla completa de códigos en el README (sección 6).

  Admin: POST /api/v1/users crea usuarios con rol (útil con
  ALLOW_REGISTRATION=false); POST /api/v1/users/{id}/unlock desbloquea.


--------------------------------------------------------------------------------
5. CAMBIAR UN RECURSO EXISTENTE
--------------------------------------------------------------------------------

  Añadir un campo:
    1. Edita resources/task.yaml (añade el campo).
    2. uv run apigen generate --force --only task
    3. uv run apigen db migrate -m "task: add tags"
    Si el campo es obligatorio y la tabla ya tiene filas, dale un default o
    hazlo nullable, o edita la migración para rellenar datos.

  Lógica propia (validaciones, efectos secundarios):
    Edita app/api/v1/endpoints/tasks.py directamente. Después NO uses --force
    para ese recurso (o guarda tus cambios antes).

  Eliminar un recurso:
    uv run apigen remove task
    uv run apigen db migrate -m "drop task"


--------------------------------------------------------------------------------
6. VERSIONES DE LA API
--------------------------------------------------------------------------------

  Cuando necesites cambios incompatibles:
    uv run apigen version add v2              # copia v1 -> v2 (código y tests)
    # modifica app/api/v2/... lo que cambie
    uv run apigen version deprecate v1 --sunset 2027-06-30

  v1 sigue funcionando pero responde con cabeceras Deprecation y Sunset para
  avisar a los clientes. Cuando llegue la fecha, quítala de app/api/versions.py.

  `apigen add` crea los recursos nuevos en la versión más reciente no
  deprecada (usa -v para elegir). En YAML, sin `versions:`, van a v1.
  `apigen version list` muestra qué versiones están deprecadas.

  OJO: las versiones comparten modelos y esquemas; solo se copian los routers.
  Si cambias un esquema de forma incompatible, v1 también cambia. Para un
  contrato distinto en v2, crea esquemas propios (app/schemas/v2/...) y edita
  a mano los endpoints de v2 (y no uses generate --force sobre ese recurso).


--------------------------------------------------------------------------------
7. BASE DE DATOS
--------------------------------------------------------------------------------

  Desarrollo : DATABASE_URL=sqlite+aiosqlite:///./app.db
  Producción : DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db

  Solo cambias esa variable; el código es el mismo. Comandos:
    apigen db migrate -m "..."   detecta cambios en modelos, crea y aplica
                                 (sin -m usa un mensaje con la fecha; si no
                                 hay cambios lo dice y no crea nada)
    apigen db upgrade            aplica pendientes (hazlo en cada despliegue)
    apigen db downgrade          deshace la última
    apigen db current / history
    (--verbose en cualquiera de ellos muestra el log de Alembic)
    apigen db prune              purga refresh tokens de sesiones muertas con
                                 más de LOGIN_FAMILIAR_DAYS días (y sus IPs);
                                 prográmalo a diario (cron)

  Revisa siempre la migración generada (alembic/versions/) antes de aplicarla
  en producción: el autogenerado no detecta renombrados (los ve como borrar +
  crear columna).

  SQLite aguanta bien lecturas y escrituras moderadas; para muchas escrituras
  concurrentes o varios workers, usa PostgreSQL.


--------------------------------------------------------------------------------
8. RATE LIMIT
--------------------------------------------------------------------------------

  Por defecto: 120/min por endpoint y 1000/min en total por cliente (usuario
  logueado o IP). Login 10/min y 50/h por IP. Registro por IP: 5/h en
  producción y 50/h en desarrollo (RATE_LIMIT_REGISTER vacío; los intentos
  rechazados por contraseña débil NO cuentan). Las rutas inexistentes
  también cuentan (120/min por IP). En desarrollo, el 429 trae un "hint".

  Cambiar límites globales: variables RATE_LIMIT_* en .env.
  Límite propio de un recurso: en el YAML
    rate_limits: {read: "300/minute", write: "30/minute"}
  o en CLI --rate-read / --rate-write.

  Con más de un worker o servidor: RATE_LIMIT_STORAGE_URI=redis://... (si no,
  cada proceso cuenta por separado).

  Detrás de nginx / load balancer: pon su IP en TRUSTED_PROXIES; si no, todos
  los clientes parecerán la misma IP (la del proxy) y compartirán límite.


--------------------------------------------------------------------------------
9. SEGURIDAD: LO QUE YA ESTÁ Y LO QUE TE TOCA
--------------------------------------------------------------------------------

  Ya resuelto: hash Argon2id, JWT corto + refresh rotatorio, revocación,
  bloqueo inteligente por intentos (un tercero no puede dejarte fuera desde
  tu IP habitual), rate limit, aislamiento entre usuarios, validación
  estricta, cabeceras, límites de tamaño, errores sin filtrar información,
  log de auditoría (logger app.audit).

  Te toca a ti en cada despliegue:
    - HTTPS (en el proxy / plataforma).
    - SECRET_KEY propia y secreta (nunca en git; .env ya está en .gitignore).
    - ENVIRONMENT=production (la app se niega a arrancar si algo es inseguro).
    - `uv run apigen check` antes de desplegar.
    - Rotar la clave: pon la vieja en JWT_PREVIOUS_SECRET_KEYS, la nueva en
      SECRET_KEY, y quita la vieja pasado ACCESS_TOKEN_EXPIRE_MINUTES.
    - Si hay registro público: EMAIL_VERIFICATION=required y el correo del
      cliente configurado (sección 17), con SPF/DKIM/DMARC en su dominio.

  Cliente con requisitos SOC 2 / ISO 27701 (o simplemente datos personales):
    - En las specs marca los datos personales y su finalidad:
        purpose: Seguimiento de pacientes
        fields:
          phone: {type: str, pii: true}
          diagnosis: {type: text, sensitive: true}   # salud, ideología...
      sensitive = solo dueño/admin, sin filtros ni orden, cifrado en la BD.
      En la CLI: -f phone:str:pii  -f diagnosis:text:sensitive
    - `apigen privacy inventory` -> docs/DATA_INVENTORY.md; rellena la tabla
      «A completar» (responsable, base legal, encargados). Se actualiza solo al
      generar recursos y CI comprueba que está al día.
    - .env: AUDIT_HMAC_KEY y DATA_ENCRYPTION_KEY (init-env las crea). Guarda la
      de datos en un gestor de secretos: sin ella no se recupera lo cifrado.
    - Programa `apigen db prune` a diario y `apigen users review --json` cada
      trimestre (guárdalo como evidencia).
    - Envía los logs JSON a un SIEM y verifica la cadena con
      `apigen audit verify`.
    - Los usuarios ya pueden descargar sus datos (GET /users/me/export) y
      borrar su cuenta (DELETE /users/me). Si alguien no puede entrar:
      `apigen users export --email X`.
    - Todo el detalle (y lo que es responsabilidad organizativa):
      docs/CUMPLIMIENTO_SOC2_ISO27701.md.

  Revisión de seguridad con agentes (cuando hagas cambios grandes):
    En Claude Code, dentro del repo, pide por ejemplo:
      "usa el agente security-expert para auditar los cambios"
      "usa el agente user para probar la experiencia con el recurso X"
      "usa el agente developer para aplicar las recomendaciones"
    El laboratorio aislado se levanta con ./security/lab.sh 8900.


--------------------------------------------------------------------------------
10. RENDIMIENTO Y PRUEBAS DE ESTRÉS
--------------------------------------------------------------------------------

  ./loadtests/run_loadtest.sh throughput     rendimiento puro
  ./loadtests/run_loadtest.sh ratelimit      defensa bajo carga + ataques
  USERS=500 DURATION=120s WORKERS=8 ./loadtests/run_loadtest.sh throughput

  Abre el .html de loadtests/reports/ en el navegador. Mira:
    - "Failures": debe ser 0 (los 429 salen aparte como "[429]").
    - p95/p99 de cada endpoint.
    - El log *-server.log: "Errores 5xx" debe ser 0.

  El login es lento a propósito (Argon2 ≈ 35 ms por intento con los valores
  por defecto). Si necesitas más logins/s: ARGON2_MEMORY_COST_KIB y
  ARGON2_TIME_COST más bajos (sin bajar de 19456 KiB / 2), o más CPU.

  Consejos de velocidad:
    - apigen serve --workers <nº CPUs>
    - Indexa (index / unique) los campos por los que filtras u ordenas.
    - GZIP_MIN_SIZE=0 si tu proxy ya comprime.


--------------------------------------------------------------------------------
11. DESPLEGAR
--------------------------------------------------------------------------------

  Con Docker (API + Postgres + Redis):
    uv run apigen init-env --production   # genera SECRET_KEY y POSTGRES_PASSWORD
    # edita .env: ALLOWED_HOSTS (obligatorio), CORS_ORIGINS
    docker compose up --build -d
  Compose siempre arranca en producción, usa la red `backend` (172.30.57.0/24)
  y solo confía en X-Forwarded-For del gateway 172.30.57.1 (un proxy en el
  host que conecta a 127.0.0.1:8000). Pon delante nginx/Caddy con HTTPS que
  SOBRESCRIBA X-Forwarded-For y envíe X-Forwarded-Proto (ver README §9).
  Nunca TRUSTED_PROXIES='*' ni rangos amplios: en producción da error.
  Programa `apigen db prune` a diario.

  Sin Docker (SQLite en producción da error salvo ALLOW_SQLITE_IN_PRODUCTION):
    ENVIRONMENT=production uv run apigen db upgrade
    ENVIRONMENT=production uv run apigen serve --workers 4


--------------------------------------------------------------------------------
12. PROBLEMAS FRECUENTES
--------------------------------------------------------------------------------

  "SECRET_KEY no configurada o débil"   -> uv run apigen init-env
  401 con la contraseña correcta        -> cuenta bloqueada por intentos (el
                                           mensaje no lo dice a propósito):
                                           espera o un admin hace
                                           POST /users/{id}/unlock
  415 en el login                        -> envía formulario, no JSON
  CORS / preflight 405 con un frontend  -> en desarrollo localhost ya está
    que no es localhost                    permitido; si no, CORS_ORIGINS
  "Configuración insegura: ..."         -> estás en production; corrige lo
                                           que indica (no es un bug)
  "ya existen estos ficheros"           -> añade --force (pisa cambios manuales)
  "Target database is not up to date"   -> uv run apigen db upgrade
  401 justo tras cambiar contraseña/rol -> normal: se revocan los tokens
  429 en desarrollo                     -> sube RATE_LIMIT_* en .env o
                                           RATE_LIMIT_ENABLED=false (solo dev)
  400 "Host" / 400 Invalid host header  -> añade tu dominio a ALLOWED_HOSTS
  Todas las peticiones comparten límite -> configura TRUSTED_PROXIES


--------------------------------------------------------------------------------
13. GRAPHIFY: TRABAJAR CON CLAUDE GASTANDO MENOS TOKENS
--------------------------------------------------------------------------------

  El grafo (graphify-out/) es el "mapa" del proyecto. Claude Code lo consulta
  antes de leer código gracias a CLAUDE.md y a los hooks de .claude/settings.json.

  Día a día:
    - Cambias código a mano         -> make graph   (1-2 s, sin tokens; si
                                       graphify no está instalado, lo dice)
    - Usas apigen add/generate/remove/version/db migrate
                                    -> nada: se actualiza solo
    - Cambias README, guías o informes de security/
                                    -> en Claude Code: /graphify . --update
    - Proyecto nuevo desde la plantilla -> sección 1 (graphify install,
                                       graphify claude install, regenerar)

  Para qué sirve (y para qué no):
    - SÍ: navegar el código. "¿Dónde se rota el refresh?", "¿quién llama a
      _admin_count?": devuelve fichero y línea; luego lees solo esas líneas.
      Funciona mejor en inglés o con nombres de símbolos.
    - NO: aprender a usar la plantilla (las recetas están en esta guía) ni
      revisar el código generado por plantillas: apigen/templates/*.j2,
      Dockerfile y alembic.ini no están en el grafo; léelos directamente.

  Preguntas útiles (comprobadas):
    make graph-query Q="what happens when a refresh token is reused"
    graphify explain "authenticate()"
    graphify path "refresh()" "rotate_refresh_token()"
    graphify path "login()" "authenticate()"
    graphify path "delete_user()" "_admin_count()"
  `path` sigue aristas dirigidas (quién llama/importa a quién). Si no hay
  camino, --undirected encuentra uno, pero puede pasar por tipos genéricos
  sin relación real. Si un nombre es ambiguo, usa el id que muestra el grafo.

  Si algún día quieres quitarlo: `graphify claude uninstall` y borra graphify-out/.


--------------------------------------------------------------------------------
14. PERSONALIZAR UN ENDPOINT Y AÑADIR LÓGICA PROPIA
--------------------------------------------------------------------------------

  Regla de oro: tu lógica va en app/hooks/<recurso>.py, NO en el router
  generado. Así `apigen generate --force` nunca la borra.

    # app/hooks/order.py
    async def before_create(ctx, data):
        if data.quantity > 50:
            raise APIError(422, "Máximo 50 unidades", code="quantity_limit")
        return data.model_copy(update={"notes": (data.notes or "").strip()})

    async def after_create(ctx, obj):
        await ctx.enqueue("order.export_invoice", {"item_id": str(obj.id)})

  Hooks disponibles: before_create(data) · after_create(obj) ·
  before_update(obj, data) · after_update(obj) · before_delete(obj) ·
  after_delete(obj). ctx.session (BD), ctx.principal / ctx.user_id (quién).

  Errores de negocio: usa siempre APIError(status, "mensaje", code="codigo").
  `apigen docs` los lista solos en el README del cliente (se leen del código).

  Acción síncrona (sin background): función homónima en el mismo fichero.
  Si cambias `obj` el endpoint hace el commit por ti. Devuelve un dict; nunca
  obj.model_dump() (saldrían los campos write_only). Un cuerpo con campos
  desconocidos da 422; sin campos obligatorios, el cuerpo es opcional.

  Si tus hooks rechazan los datos de los tests generados (p. ej. "no puede ser
  en el pasado"), fija `example:` en el campo del YAML. Las fechas de los
  tests ya son futuras (dentro de un año).

  Cambiar campos, permisos o filtros -> edita el YAML donde esté definido el
  recurso (resources/<recurso>.yaml o tu YAML con varios recursos: apigen no
  crea copias, y un recurso definido dos veces es un error) y
    apigen generate resources --force --only <recurso>[,<otro>]   (hooks intactos)
    apigen db migrate -m "..."
  Añadir un endpoint nuevo -> una acción en el YAML (ver §15) o, si es muy
    particular, un router propio en app/api/v1/endpoints/ registrado en
    app/api/v1/router.py (ese fichero no lo pisa apigen).
  Cambiar el endpoint generado a mano -> posible, pero entonces no uses
    --force con ese recurso.


--------------------------------------------------------------------------------
15. PROCESOS PESADOS EN SEGUNDO PLANO (SIN FRENAR LA API)
--------------------------------------------------------------------------------

  1. Márcalo en el YAML:
       actions:
         - name: export_invoice
           background: true
           executor: async     # async (E/S), thread (librería bloqueante), process (CPU)
           timeout: 600
  2. apigen generate --force --only order   -> crea app/tasks/resources/order.py
  3. Escribe el proceso en esa función (es tu código, no se sobrescribe).
  4. Arranca el worker en otra terminal:  make worker   (o apigen worker)

  El cliente hace POST /api/v1/orders/{id}/export_invoice, recibe al instante
  202 {"job_id", "status": "queued", "status_url"} y consulta status_url hasta
  "succeeded" (con "result") o "failed" (con "error").

  - raise TaskError("mensaje") -> fallo visible para el cliente, sin reintento.
  - Cualquier otra excepción -> se reintenta (10 s, 20 s, 40 s...) y el
    cliente solo ve "Task failed" (la traza queda en el log con el job_id).
  - Quién lo pidió: ctx.owner_id (también ctx.job_id, ctx.attempt). Las
    tareas thread/process también reciben ctx, pero sin sesión de BD: lee los
    datos en el hook o en una tarea async y pásalos en el payload.
  - Timeout: una tarea process se mata al vencer (y se reintenta); un hilo no
    se puede matar, así que falla sin reintento: hazla idempotente.
  - Pon rate_limit a las acciones en segundo plano (apigen avisa si falta).
  - Más capacidad: más workers (docker compose up --scale worker=3) o
    JOBS_CONCURRENCY. CPU pesada: executor: process + JOBS_PROCESS_WORKERS.
  - En tests: from app.tasks.worker import process_pending; await process_pending()


--------------------------------------------------------------------------------
16. EMPEZAR LA API DE UN CLIENTE Y ENTREGARLA
--------------------------------------------------------------------------------

  1. make new-api NAME=<cliente>-api LANG=es      -> ~/Developer/<cliente>-api
     Con correo: python3 scripts/new_api.py <cliente>-api --lang es
       --email-verification required --password-reset --frontend-url https://...
     (los modos, idioma, marca y FRONTEND_URL van a .env.example, que se entrega;
     en producción faltará EMAIL_BACKEND=smtp, SMTP_* y EMAIL_FROM en el .env).
  2. En tu Second Brain: nuevo proyecto con la plantilla "Proyecto API para cliente".
  3. Recursos en resources/*.yaml -> uv run apigen generate resources --migrate
  4. Hooks, tareas, tests (uv run pytest) y revisión con los agentes.
  5. Al terminar: uv run apigen docs --lang es --base-url https://api.cliente.com
     -> README.md para el cliente (después basta `uv run apigen docs`: recuerda
     idioma y URL). Completa la introducción y el contacto (se conservan).
  6. Prueba el arranque del README tal cual: cp .env.example .env, rellena
     SECRET_KEY, POSTGRES_PASSWORD y ALLOWED_HOSTS, docker compose up -d --build.
  7. Entrega: `make deliver` -> ../<proyecto>-entrega.zip con lo versionado,
     sin .claude/, graphify-out/, security/, loadtests/ ni CLAUDE.md (o da
     acceso al repo si el cliente también va a desarrollar: docs/DESARROLLO.txt).

  new_api.py exige la plantilla sin cambios sin commit y copia solo lo
  versionado; antes del commit inicial revisa secretos y datos personales en
  todos los ficheros (si encuentra algo, no hace commit y te lo lista).


--------------------------------------------------------------------------------
17. CORREO: VERIFICACIÓN DE EMAIL Y RECUPERACIÓN DE CONTRASEÑA
--------------------------------------------------------------------------------

  Apagado por defecto. Para un cliente, en su .env (nunca en el código):
    EMAIL_VERIFICATION=required     (off | optional | required)
    PASSWORD_RESET=on
    FRONTEND_URL=https://app.cliente.example
    EMAIL_BACKEND=smtp + SMTP_HOST, SMTP_PORT, SMTP_SECURITY, SMTP_USER,
                  SMTP_PASSWORD
    EMAIL_FROM=no-reply@<dominio del cliente>   (con SPF, DKIM y DMARC)
    MAIL_BRAND_NAME / MAIL_BRAND_LOGO_URL / MAIL_BRAND_COLOR / MAIL_SUPPORT_EMAIL

  Probar en local sin proveedor:
    - Nada que hacer: en development el correo sale en el log de la API
      (EMAIL_BACKEND=console) y lo envía la propia API (EMAIL_DELIVERY=inline).
      Copia el token del enlace (lo que va tras #token=).
    - Para verlo como un correo real: make mail (Mailpit en
      http://localhost:8025) y en .env EMAIL_BACKEND=smtp SMTP_HOST=localhost
      SMTP_PORT=1025 SMTP_SECURITY=none.
    - Antes de entregar: uv run apigen email test tu@example.com (con el SMTP
      del cliente) y uv run apigen email preview para enseñarle los correos.

  Lo que tiene que hacer el frontend del cliente (va en su README.md):
    - Página /reset-password: lee el token de location.hash, lo quita con
      history.replaceState y envía POST /auth/password/reset
      {"token", "new_password"} (opcional antes: /auth/password/reset/validate).
    - Página /verify-email: POST /auth/email/verify {"token"} (también confirma
      los cambios de email). Dos clics = 204.
    - "¿Olvidaste tu contraseña?": POST /auth/password/forgot {"email"} y
      mensaje neutro (siempre 202). Reenviar verificación:
      POST /auth/email/verify/resend. GET /auth/features dice qué está activo.

  Personalizar textos: uv run apigen email eject password_reset --lang es y
  edita email_templates/es/password_reset.* (asunto, texto y HTML por
  separado). Correos propios: app.email.send_email(...) con una plantilla en
  email_templates/. En tests: fixture `mail` + process_pending().

  Límites que conviene conocer (todos configurables): por IP en forgot/resend
  (RATE_LIMIT_EMAIL_REQUEST) y por cuenta en el worker (60 s entre correos,
  3/hora, 10/día en producción; en development 0 s, 30/hora y 200/día). Lo
  excedido se descarta, se audita como email.suppressed y, en development,
  se avisa en el log ("correo NO enviado: cupo por cuenta").

  ¡Aviso al pasar a EMAIL_VERIFICATION=required! Los usuarios registrados
  mientras estaba en off no están verificados y recibirán 403 hasta verificar.
  Si ya eran de confianza:
    uv run apigen users verify --all-existing --before 2026-10-01
    uv run apigen users verify --email alguien@example.com
  (queda en el log de auditoría como admin.user.verify; `apigen check` avisa
  de cuántos usuarios faltan). Con EMAIL_BACKEND=file, copia el token del
  .txt (el .eml lo parte).
  Detalle técnico y de seguridad: README.txt, sección 15.
