# Revisión de seguridad — Ronda 3 (verificación de correcciones)

- **Fecha:** 2026-09-25
- **Rol:** experto AppSec (defensivo)
- **Entrada:** `ronda2-desarrollador.md`, que incluye la sección "Debate".
- **Método:** revisión del código modificado y laboratorio `./security/lab.sh 8901` (127.0.0.1, modo producción, SQLite, rate limit en memoria), en tres arranques:
  1. `TRUSTED_PROXIES=127.0.0.1`: permite simular varias IPs de cliente con `X-Forwarded-For` desde 127.0.0.1.
  2. `REFRESH_REUSE_GRACE_SECONDS=0`.
  3. Configuración por defecto, para comprobar el aviso de `TRUSTED_PROXIES`.
- **Scripts nuevos o actualizados** en `security/checks/`:
  - `ronda3_checks.py` (secciones general / lockout / race);
  - `ronda3_lock_reset.py`;
  - `refresh_race.py`, adaptado a `@example.com`;
  - `generator_checks.py`, vuelto a ejecutar.
- **Tests:** `.venv/bin/pytest -q -p no:cacheprovider` → **112 passed**.
- **Estado final:** no he modificado `app/`, `apigen/` ni `tests/`. No queda ningún servidor en marcha.
- **No verificable aquí:** Docker, PostgreSQL y Redis. Lo que depende de ellos está marcado como *estático* o *no verificado*.

---

## 1. Estado de los hallazgos SEC-01 … SEC-19

Leyenda:
- **Verificado:** corregido y comprobado.
- **Parcial:** mejora real con un hueco pendiente.
- **No resuelto.**
- **Riesgo aceptado:** decisión del desarrollador que acepto, con las condiciones indicadas.

| ID | Decisión dev | Estado | Evidencia (laboratorio / código) |
|---|---|---|---|
| SEC-01 Carrera en refresh | A | **Verificado** | Ver detalle debajo de la tabla. |
| SEC-02 Bloqueo por terceros | A | **Parcial** (riesgo residual aceptado + SEC-20) | Ver detalle debajo de la tabla. |
| SEC-03 Compose en development | A | **Verificado (estático)** | `docker-compose.yml:13` fija `ENVIRONMENT: production` en `environment:`, que prevalece sobre `env_file`. `Dockerfile:28` se niega a arrancar si `ENVIRONMENT != production` salvo `ALLOW_NON_PRODUCTION=1`. Con `env_ignore_empty`, `ALLOWED_HOSTS=` vacío vuelve a `*`, así que la app no arranca en producción hasta que se rellene. Correcto. Sin Docker no se ha ejecutado. |
| SEC-04 Proxy sin `TRUSTED_PROXIES` | A (parcial HSTS) | **Parcial** (ver SEC-21/22) | El aviso sale en el arranque: `TRUSTED_PROXIES vacío: si la API está detrás de un proxy inverso…`. Con proxy de confianza, `X-Forwarded-Proto: https` → `strict-transport-security: max-age=63072000; includeSubDomains`. Acepto el rechazo de `HSTS_FORCE`. Pero `TRUSTED_PROXIES='*'`/`0.0.0.0/0` se aceptan en producción (SEC-21) y el CIDR por defecto de compose es demasiado amplio (SEC-22). |
| SEC-05 Enumeración en registro | R/Pos | **Riesgo aceptado** | `409 {"detail":"Email already registered","code":"email_taken"}`. Condiciones en §2 (T3). |
| SEC-06 500 sin cabeceras | A | **Verificado (código + test)** | `UnhandledErrorMiddleware` es la capa más interna (`app/main.py:124`, `middleware.py:200-235`) y `test_500_keeps_security_headers_and_request_id` pasa. En el laboratorio ya no he conseguido provocar ningún 500: los vectores de la ronda 1 están cerrados. El 413 (*chunked*) y el 429 de rutas inexistentes llevan CSP, `nosniff` y `X-Request-ID`. |
| SEC-07 Enteros / NUL | A | **Verificado** (PostgreSQL no) | `stock=2**63` → 422 `less_than_equal`. `stock=2**31` → 201 (BIGINT). NUL en `full_name` → 422 `null_character`. NUL en el `username` del login → 401. NUL dentro de JSON → 422. NUL en query params (`q`, filtros) depende de la red `DataError → 422`, no verificado en PostgreSQL. |
| SEC-08 Permisos inseguros | P | **Parcial** | `generator_checks.py`: owned + `update/delete=user` → **rechazado**. Siguen aceptándose (con aviso): owned + `list/read=public` y owned + `list=owner, read=user`. En no-owned, `update=user` y `create=public` se aceptan; no he verificado si emiten aviso. Ver T-SEC-08 en §3. |
| SEC-09 Unicidad global en owned | A | **Verificado (código generado)** | Modelo generado: `__table_args__ = (UniqueConstraint('owner_id', 'label'),)`. El 409 excluye `owner_id` de `fields` (`errors.py:117`). `shop.yaml` no tiene campos únicos en recursos owned, así que en el laboratorio no se ejercita; hay test del desarrollador. |
| SEC-10 FK sin visibilidad | P | **Verificado / riesgo residual aceptado** | Router generado: destino con `read: admin` → `ensure_reference(..., allowed=principal.is_admin)`, que devuelve 422 sin consultar la BD. fk→`user` → `ensure_reference(User, …)`, con 422 uniforme en lugar de 409. En el laboratorio: FK a categoría inexistente → 422 `reference_not_found`. Residual: fk→user puede apuntar a cualquier usuario existente (ver §3). |
| SEC-11 Huecos del rate limit | A | **Verificado** (Redis no) | 125 × `GET /nope` desde una IP → **120×404 + 5×429**, y el 429 lleva `retry-after`, `x-ratelimit-*` y cabeceras de seguridad. `slowapi<0.2` fijado. El *fallback* de Redis (`rate_limit.py:85-110`) es correcto en código; ver SEC-24 sobre la llamada síncrona. |
| SEC-12 `EmailStr` en salida | A | **Verificado** | El laboratorio crea `@example.com`. `/users/me` y los logins funcionan. `UserRead.email: str`. `log_unhandled` registra `ResponseValidationError` solo con `loc/type`. Hay test con dominio especial. |
| SEC-13 Auditoría / inyección en logs | A | **Verificado** | `GET /api/v1/x%0aFAKE…` → una sola línea `…GET /api/v1/x\x0aFAKE LOG line 404`. Eventos `auth.login.success/failure/blocked`, `auth.account.locked` (nivel **ERROR** con `admin=True`), `auth.refresh.reuse/concurrent`, con `user_id` e IP. **0 emails** en las líneas `app.audit`. |
| SEC-14 JSON sin límite | P | **Verificado / residual aceptado** | JSON de 20 KB → 422 `json_too_large`. Profundidad 13 → 422 `json_too_deep`. Queda pospuesto excluir campos de los listados: acepto (16 KiB × 100 filas ≈ 1,6 MB por página). |
| SEC-15 Contraseñas / alta | Pos | **Riesgo aceptado con condición** | Ver §2 (T3/T4) y el veredicto: con registro abierto al público exijo al menos la lista top-10k antes del lanzamiento. |
| SEC-16 Access tras logout / reutilización | P | **Verificado** | Reutilización desde otra IP → el access token cae: `GET /users/me → 401 invalid_token`. `/logout` sin invalidar el access token es por diseño (TTL de 15 min) y está documentado. Acepto. |
| SEC-17 JWT / admin | P | **Verificado / riesgo aceptado** | Claves antiguas de menos de 32 caracteres rechazadas en producción (`config.py`, test). Acepto el argumento sobre `kid`: 64 bits de SHA-256 de un secreto de ≥ 256 bits no aportan ventaja offline. Anillo asimétrico y TOCTOU del último admin: pospuestos, aceptado. |
| SEC-18 *Hardening* despliegue | P | **Parcial / riesgo aceptado con condición** | `POSTGRES_PASSWORD` obligatorio con `${…:?}` (estático). `make audit` existe pero **no se ha ejecutado**: es condición de producción. Digests, usuario de migración y `requirepass`: aceptado como pospuesto (Redis sin puertos publicados). |
| SEC-19 Robustez del generador | A | **Verificado** | `session`, `principal`, `page`, `request` y `order_by` rechazados. Enum `mro/_missing_/__init__` → `v_mro…`, que importa correctamente. `pattern` con look-around → rechazado en la validación. |

### Detalle SEC-01 — Verificado

Laboratorio, con dos refresh simultáneos:

| Escenario | Códigos | Token del ganador después |
|---|---|---|
| Misma IP, gracia 10 s (×3) | `[200, 409]` | 200 (comportamiento "dos pestañas" buscado) |
| IPs distintas, gracia 10 s (×3) | `[200, 401]` | **401** |
| `REFRESH_REUSE_GRACE_SECONDS=0`, `refresh_race.py` (×3) | `[200, 401]` | **401** |
| 5 peticiones concurrentes, gracia 0 | `[200, 401, 401, 401, 401]` | — |

- **Trazas en el servidor:** 0 `Traceback` y 0 `MissingGreenlet`, con 7 eventos `auth.refresh.reuse`.
- **Código:** `auth.py:284-285` copia `token_id`, `family_id`, `user_id`, `expires_at` y `scope` antes del `rollback()`. `_handle_revoked` relee el estado de la BD.

### Detalle SEC-02 — Parcial (riesgo residual aceptado + SEC-20)

Laboratorio con XFF:

| Prueba | Resultado |
|---|---|
| Titular desde su IP conocida tras 5 fallos de un tercero | 200 |
| Titular desde IP **nueva** | **401** (bloqueado) |
| Admin desde IP nueva tras 5 fallos anónimos | 401 (auditoría `auth.account.locked` a nivel ERROR con `admin=True`) |
| Admin desde IP conocida | 200 |
| Escalado del bloqueo | `attempts=10 minutes=30` |

Nuevo hallazgo **SEC-20**: el login del titular levanta el bloqueo para todos.

---

## 2. Respuesta al Debate

### T1. Smart lockout — **Acepto con riesgo residual**

El diseño es correcto:
- el contador es por cuenta, y la botnet no gana intentos;
- solo los logins con contraseña hacen conocida una IP, y la rotación de refresh no;
- el hash señuelo durante el bloqueo iguala el tiempo;
- el bloqueo de un admin sale como alerta.

Lo he comprobado en el laboratorio.

Riesgo residual que acepto:
- Un atacante que comparte IP con la víctima (NAT) sigue sin bloqueo, limitado solo por 10/min y 50/h por IP. Laboratorio: 6 intentos seguidos evaluados desde la "IP conocida" de bob.
- Los usuarios sin IP conocida (móvil con CGNAT, viajes, dispositivo nuevo) sufren el bloqueo, y ahora con escalado hasta 240 min.

Mitigación mínima que exijo:
1. Corregir **SEC-20**.
2. Invalidar la "familiaridad" tras un cambio de contraseña: contar solo los logins con `created_at > password_changed_at`. Así, un atacante que conoció la contraseña antigua no conserva una IP exenta del bloqueo para atacar la nueva.
3. Que la documentación indique al operador el procedimiento `unlock` y la alerta a vigilar.

Como mejora opcional, no bloqueante: una prueba de dispositivo, es decir, una cookie o token de dispositivo firmado en lugar de solo la IP.

### T2. Gracia de refresh — **Acepto con riesgo residual**

He verificado que la gracia no entrega tokens: solo responde 409.
- Desde otra IP, la reutilización revoca la familia y los access tokens.
- Pasada la gracia, la reutilización revoca.

El único caso en que la detección se debilita es este: el atacante comparte IP con la víctima, gana la carrera y el cliente legítimo recibe 409 y **no vuelve a presentar** el token viejo. El README indica "relee el token más reciente y reintenta". Si no hay uno más reciente en el almacenamiento, un cliente que se limite a cerrar la sesión en local deja viva la familia del atacante hasta 7 días.

Mitigación mínima que exijo, solo de documentación:
- En el README y la guía: *"si tras un 409 `refresh_token_rotated` tu almacenamiento no contiene un refresh más nuevo, llama a `POST /auth/logout` con el token viejo"*. Esa llamada revoca toda la familia (`revoke_by_token`), incluida la del atacante.
- Añadir un test que cubra ese flujo.

Nota: sin `TRUSTED_PROXIES` detrás de un proxy, todos los clientes comparten IP y la gracia se aplica a cualquiera. Sigue sin entregar tokens, así que es aceptable.

### T3. Enumeración en el registro — **Acepto (riesgo aceptado)**

El argumento es correcto: sin verificación de email, una respuesta uniforme no evita la enumeración, porque basta con registrarse y probar el login. Además, con T1 la enumeración ya no sirve para dejar fuera a la víctima.

Condiciones:
- el 409 sigue consumiendo cupo (verificado en el código);
- vigilar picos de `auth.register` en la auditoría;
- implementar la verificación de email antes de cualquier despliegue en el que la pertenencia al servicio sea sensible (salud, finanzas, etc.).

### T4. Los 422 de política no consumen cupo — **Acepto**

El 422 es barato (sin Argon2, sin escritura) y sigue sujeto a `RATE_LIMIT_GLOBAL` por cliente. El 409, que es el oráculo, sí cuenta. No abre ninguna vía nueva de abuso.

### T5. 409 con `code` y `fields` — **Acepto**

- Solo se exponen nombres de columna, que ya son públicos en OpenAPI; nunca valores.
- La causa del oráculo entre usuarios se corrige con `UniqueConstraint(owner_id, campo)`.
- `has_dependents` sí revela que existen filas que referencian a una propia. Solo es posible si otro usuario puede referenciarla (destino compartido); lo considero aceptable.

### T6. Formato, idioma y CORS de desarrollo — **Acepto**

- `code` aditivo sin RFC 9457: sin impacto en seguridad.
- CORS de desarrollo:
  - Verificado que en producción no se activa: preflight desde `http://localhost:3000` → sin `Access-Control-Allow-Origin`.
  - En desarrollo permite `localhost:*` **sin credenciales**. Como la autenticación va en la cabecera `Authorization` (no en cookies), una página local maliciosa no puede usar la sesión de nadie.
  - Starlette compara el origen con la regex mediante `fullmatch`.

---

## 3. Decisiones rechazadas o pospuestas (fuera del Debate)

- **SEC-08 (parcial):** acepto que *owned + lectura pública* sea legítimo (blog) y que se quede en aviso. **No acepto** que *owned + `read` más permisivo que `list`* (p. ej. `list: owner`, `read: user`) sea solo un aviso. Es exactamente un BOLA por ID: el listado aísla, el detalle no, y los tests generados pasan igualmente. Mitigación mínima: convertirlo en **error**, salvo un flag explícito (`allow_shared_read: true`) que el autor tenga que escribir.
- **SEC-10 (fk→user sin limitar a `principal.user_id`):** acepto con riesgo residual. Los UUIDv7 no son enumerables y ahora la respuesta es un 422 uniforme. Documentar en la plantilla que un campo fk→user permite enlazar a cualquier usuario y que, si representa "el propietario", hay que usar `owned`.
- **SEC-14, SEC-15, SEC-17 y SEC-18 (pospuestos):** aceptados con las condiciones del veredicto.

---

## 4. Revisión de los cambios nuevos

| Cambio | Resultado |
|---|---|
| Log de auditoría (`app/core/audit.py`) | Correcto: sin emails, contraseñas ni tokens (0 emails en las líneas `app.audit`). Registra IPs (dato personal, documentado); ver SEC-23 sobre retención. |
| `client_ip` en `refresh_tokens` | Funciona. Sin purga ni índice (SEC-23). Ahora la IP es una **decisión de seguridad** (bloqueo y gracia), así que la confianza en `X-Forwarded-For` pasa a ser crítica (SEC-21/22). Con proxy de confianza, uvicorn toma la IP más a la derecha no confiable (comprobado en el código de `ProxyHeadersMiddleware`). |
| Unicidad por propietario / índice parcial | Correcto (SEC-09). |
| 415 en el login | Verificado: `415 login_expects_form`. La dependencia se evalúa antes del decorador, así que no consume cupo de login, pero sí el global por cliente. Sin riesgo. |
| CORS en desarrollo | Correcto (T6). |
| Docker / compose | Correcto en lo estático (SEC-03). Nuevo: SEC-22. |
| `env_ignore_empty=True` | Positivo para `ALLOWED_HOSTS`. Pero `DATABASE_URL=` vacío hace que producción use SQLite local en silencio (solo un aviso); ver SEC-24. |
| Handler global de `OverflowError` → 422 | Ver SEC-24. |

---

## 5. Hallazgos nuevos

### SEC-20 — El login del titular levanta el bloqueo para todos y reinicia el escalado
- **Severidad:** Baja. **OWASP:** API2:2023 (anti-automatización). **Estado:** reproducido.
- **Evidencia:** `app/services/auth.py:115-123`. Un login correcto, aunque se haga con `locked` desde una IP conocida, pone `failed_login_attempts=0` y `locked_until=None`. Con `security/checks/ronda3_lock_reset.py`:
  ```
  fallos del atacante: [401 ×5]              -> auth.account.locked attempts=5 minutes=15
  titular desde IP nueva (bloqueada): 401
  titular desde IP conocida: 200             -> bloqueo levantado
  atacante tras el login del titular: [401 ×6] -> 5 contraseñas evaluadas de nuevo;
                                               se vuelve a bloquear con attempts=5 minutes=15 (sin escalado)
  ```
- **Impacto:** el atacante recupera 5 intentos reales cada vez que el titular inicia sesión, y el escalado (15 → 240 min) nunca llega a actuar contra una víctima activa. Con la política de 12 o más caracteres el impacto es bajo, pero anula en parte el objetivo de T1.
- **Recomendación:** si el login correcto ocurre **durante un bloqueo** desde una IP conocida, dejar entrar al titular **sin** borrar `locked_until` ni el contador para el resto de orígenes. Reiniciar el contador solo con un login correcto fuera de bloqueo o con `unlock`. Añadir un test.
- **Relacionado (Baja, teórico):** `_is_familiar` no tiene en cuenta `password_changed_at`. Una IP desde la que se inició sesión con la contraseña anterior (quizá la de un atacante) sigue exenta del bloqueo durante 30 días tras el cambio de contraseña. Recomendación: `created_at >= max(since, user.password_changed_at)`.

### SEC-21 — `TRUSTED_PROXIES='*'` o `0.0.0.0/0` aceptados en producción
- **Severidad:** Media, por configuración. **OWASP:** API8:2023 / API2 / API4. **Estado:** reproducido.
- **Evidencia:**
  ```
  ENVIRONMENT=production … TRUSTED_PROXIES='*'      -> Settings() OK: ['*']
  ENVIRONMENT=production … TRUSTED_PROXIES=0.0.0.0/0 -> Settings() OK
  ```
  Con `*`, `ProxyHeadersMiddleware` usa la IP **más a la izquierda** de `X-Forwarded-For`, que controla el cliente. `config.py:89-94` solo avisa si la lista está vacía.
- **Impacto:** tras SEC-02, la IP decide la exención del bloqueo (IP conocida) y la gracia de refresh, además de todos los límites por IP. Con esa configuración, un atacante puede:
  - saltarse `RATE_LIMIT_LOGIN`/`REGISTER`/`REFRESH` cambiando el XFF en cada petición (credential stuffing masivo, a 5 intentos por cuenta y ventana);
  - si conoce la IP de salida de la víctima (p. ej. la de una empresa), saltarse el bloqueo por completo.
- **Recomendación:**
  - En producción, **rechazar** `*`, `0.0.0.0/0` y `::/0`, y avisar ante redes más amplias que /16.
  - Documentar que el proxy debe **sobrescribir** XFF (`proxy_set_header X-Forwarded-For $remote_addr`) en lugar de añadir a lo que envía el cliente.

### SEC-22 — El CIDR por defecto de compose (`172.16.0.0/12`) es demasiado amplio
- **Severidad:** Baja. **Estado:** teórico (sin Docker).
- **Evidencia:** `docker-compose.yml:17`. uvicorn recorre XFF de derecha a izquierda y descarta las IPs confiables. Si el cliente real tiene una IP dentro de 172.16.0.0/12 (redes corporativas que usan ese rango, clientes en el mismo host, otros contenedores), su IP se considera "proxy" y se toma la entrada anterior, que pone el atacante. Además, cualquier contenedor de esas redes (incluidos `db` o `redis` si se ven comprometidos) puede falsificar XFF.
- **Recomendación:** declarar en compose una red con `ipam.subnet` fija y confiar solo en la IP de su gateway (`/32`), o en la IP concreta del contenedor del proxy si también está en compose.

### SEC-23 — `client_ip` sin retención ni índice (dato personal)
- **Severidad:** Info / Baja (privacidad, RGPD). **Estado:** código.
- **Evidencia:**
  - `app/models/refresh_token.py:29` y la migración `a7d3c2e1b4f0`: la columna no tiene índice.
  - No hay ninguna purga de `refresh_tokens` (búsqueda de `delete(RefreshToken)` sin resultados), así que las IPs se guardan indefinidamente, aunque solo se necesitan `LOGIN_FAMILIAR_DAYS` (30).
- **Recomendación:** tarea o comando `apigen db purge-tokens` que borre filas expiradas o revocadas con más de `max(REFRESH_TOKEN_EXPIRE_DAYS, LOGIN_FAMILIAR_DAYS)` días. Índice `(user_id, client_ip)`. Documentar la base legal y el plazo.

### SEC-24 — Detalles menores de los cambios (Info)
- **`OverflowError` global** (`errors.py:185`): cualquier `OverflowError` que no venga de la BD (un bug de cálculo) se presentaría como 422 `invalid_value` en lugar de 500, lo que oculta errores. Convertir solo el que envuelve el driver (capturarlo en el repositorio) o comprobar el origen.
- **Llamada síncrona a Redis:** `_evaluate_with_fallback` llama a `limiter._storage.check()`, que es síncrona, dentro del *event loop*. Con Redis caído, bloquea el loop hasta el *timeout* del socket cada 30 s. Conviene un *timeout* corto en la URI de Redis (`socket_timeout`). No verificado: no hay Redis.
- **`DATABASE_URL=` vacío:** en producción cae en `sqlite+aiosqlite:///./app.db` con solo un aviso. Con la imagen `read_only`, fallaría en la escritura, pero fuera de Docker arrancaría con una BD local vacía. Convertirlo en error en producción cuando `DATABASE_URL` no está definida.

---

## 6. Veredicto final

**Apto para producción con condiciones.** No quedan hallazgos críticos ni altos. Los dos medios de la ronda 1 que eran bugs (SEC-01, SEC-02) están corregidos y verificados, y los de configuración (SEC-03, SEC-04) están mitigados.

**Condiciones bloqueantes (antes del primer despliegue):**
1. **SEC-21:** rechazar `TRUSTED_PROXIES` comodín en producción y configurar el proxy para que sobrescriba `X-Forwarded-For`. Con el bloqueo inteligente, la autenticidad de la IP es ahora un control de seguridad.
2. **SEC-22:** acotar `TRUSTED_PROXIES` en compose a la IP del gateway o del proxy.
3. **SEC-20:** no levantar el bloqueo global con el login del titular (cambio pequeño con test).
4. **SEC-08:** convertir *owned + `read` más permisivo que `list`* en error salvo un flag explícito.
5. **SEC-18:** ejecutar `make audit` (pip-audit) en CI con resultado limpio.
6. Probar en un entorno real con **PostgreSQL + Redis + Docker**:
   - NUL en query params → 422;
   - índices parciales y `constraint_name` del 409;
   - *fallback* de Redis;
   - HSTS y XFF detrás del proxy real.

**Condiciones no bloqueantes (siguiente iteración):**
- Documentar el flujo del 409 `refresh_token_rotated` → `logout` con el token viejo (T2).
- Familiaridad posterior a `password_changed_at` (SEC-20, relacionado).
- Purga de `refresh_tokens` e índice (SEC-23).
- Detalles de SEC-24.
- Si el registro es público: lista de contraseñas comprometidas (top-10k como mínimo) y, cuando haya SMTP, verificación de email (SEC-05/SEC-15).
