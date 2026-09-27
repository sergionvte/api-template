# Fase 2 – Plan de seguridad: recuperación de contraseña, verificación de email y envío de correo por cliente

Autor: security-expert · Fecha: 2026-09-26 · Tipo: planificación (no auditoría de código)
Marco: OWASP ASVS 4.0.3 nivel 2 (V2 Autenticación, V3 Sesiones, V5, V7, V14) y OWASP API Security Top 10 (2023).

Convención: **MUST** = bloqueante para la validación final; **SHOULD** = esperado salvo
justificación escrita del desarrollador; **MAY** = opcional. Cada requisito tiene un ID
(`REQ-xxx`) al que remiten los casos de prueba (`ST-xx`) de la sección 5.

---

## 0. Punto de partida (lo que ya existe y condiciona el diseño)

Orientación con graphify (`query` sobre auth y cola) y lectura dirigida:

| Hecho | Evidencia | Consecuencia para el diseño |
|---|---|---|
| El registro responde 409 `email_taken` (riesgo aceptado T3/SEC-05 "hasta tener verificación") | `app/api/v1/endpoints/auth.py:22,57-60` | Con email ya disponible, la excusa desaparece: hay que cerrarlo (REQ-E01..E05). |
| El login ya tiene mensaje único y coste Argon2 igualado para usuario inexistente/bloqueado | `app/services/auth.py:31-37,77-115` | Mismo patrón para los flujos nuevos. |
| Cambiar contraseña revoca todas las sesiones (`token_version` + refresh) y actualiza `password_changed_at` | `app/api/v1/endpoints/users.py:81-86`, `services/auth.py:452-465` | El reset DEBE reutilizar exactamente esta ruta. |
| `_is_familiar` solo cuenta logins posteriores a `password_changed_at` | `services/auth.py:136-158` | Un reset "borra" las IPs conocidas: comportamiento deseado. |
| Refresh tokens: `secrets.token_urlsafe(48)` con prefijo, solo se guarda SHA-256 | `app/core/security.py:267-279` | Plantilla directa para los tokens de email. |
| El worker NO tiene `SECRET_KEY` (clave efímera, SEC-38) | `app/core/config.py` (`PROCESS_ROLE`), `docker-compose.yml:47-48` | Los tokens de email no pueden ser JWT/HMAC firmados con `SECRET_KEY`; deben ser opacos y guardados como hash. |
| `jobs.payload` se guarda en claro en BD y se retiene `JOBS_RETENTION_DAYS` (7) | `app/models/job.py:40`, `app/tasks/queue.py:88-95` | Prohibido poner tokens en claro en el payload (REQ-Q02). |
| `JobRead` no expone `payload`; un usuario ve y puede cancelar SUS trabajos | `app/schemas/job.py`, `app/api/v1/endpoints/jobs.py:29-33,66-77` | Los correos deben ser trabajos de sistema (`owner_id=None`) (REQ-Q01). |
| Reintentos con backoff y arrendamiento; un worker lento puede perder el lease y otro re-ejecutar | `queue.py:180-216`, `worker.py:138-180` | Envío "al menos una vez": hay que acotar duplicados (REQ-Q04..Q07). |
| El access log registra solo `path` (sin query string); `Referrer-Policy: no-referrer` en respuestas de la API | `app/core/middleware.py:58-70,95` | Bien, pero no protege el frontend del cliente, que es donde aterriza el enlace. |
| `audit()` nunca registra emails ni tokens, solo IDs | `app/core/audit.py:1-6` | Mantener el contrato en los eventos nuevos. |
| `ALLOWED_HOSTS="*"` por defecto; en producción se exige lista | `config.py:143,283-284` | Aun así, los enlaces NUNCA se construyen con `Host` (REQ-L01). |
| `UserUpdateMe`/`UserAdminUpdate` no permiten cambiar `email` | `app/schemas/user.py:64-74` | Correcto; el cambio de email será un flujo propio con verificación. |

Supuesto: **un despliegue = un cliente** (configuración por `.env`). Si en el futuro un
mismo despliegue sirve a varios clientes, la selección de configuración de correo debe
hacerse por tenant resuelto en servidor, nunca por cabecera `Host` (fuera de alcance).

---

## 1. Superficie nueva de referencia

Solo para dar nombres a los requisitos (el desarrollador decide rutas finales):

| Endpoint | Auth | Respuesta |
|---|---|---|
| `POST /auth/register` (modificado) | no | 202 uniforme |
| `POST /auth/verify-email` `{token}` | no | 204 / 400 `invalid_or_expired_token` |
| `POST /auth/verify-email/resend` `{email}` | no | 202 uniforme |
| `POST /auth/password/forgot` `{email}` | no | 202 uniforme |
| `POST /auth/password/reset` `{token, new_password}` | no | 204 / 400 / 422 |
| `POST /users/me/email` `{new_email, current_password}` | sí | 202 uniforme |
| `POST /users/me/email/confirm` `{token}` | no (el token prueba) | 204 / 400 |

Tabla nueva sugerida `account_tokens`: `id, user_id (FK CASCADE), purpose, token_hash
(UNIQUE), email (dirección destino snapshot), job_id, created_at, expires_at, used_at,
sent_at`. Columna nueva en `users`: `email_verified_at`.

---

## 2. Modelo de amenazas

| ID | Amenaza | Vector concreto en esta API | Ref. | Control (requisitos) |
|---|---|---|---|---|
| TM-01 | Enumeración de cuentas en registro | 409 `email_taken` vs 201; diferencia de tiempo (el camino "existe" se salta Argon2: `auth.py:59-64`) | ASVS 2.2.x/3.x (anti-enumeración), API2 | Respuesta 202 idéntica + Argon2 en ambos caminos + correo "ya tienes cuenta" (E01-E05) |
| TM-02 | Enumeración en forgot/resend | Distinto código/cuerpo/tiempo según exista el email; consulta a BD + inserción solo si existe | API2 | Siempre 202 idéntico; la API no consulta usuarios: el worker decide (E06-E08) |
| TM-03 | Enumeración en login de cuenta no verificada | 403 `email_not_verified` antes de verificar contraseña | ASVS 2.2.x | 403 solo tras contraseña correcta (F12) |
| TM-04 | Enumeración en cambio de email | 409 si el nuevo email ya existe | API2 | 202 uniforme; comprobación de unicidad al confirmar (F20-F22) |
| TM-05 | Fuerza bruta / adivinación de tokens | Tokens cortos, códigos numéricos, sin límite en `/reset` | ASVS 2.5.x, 2.7.6, API2/API4 | ≥256 bits, opacos, rate limit, sin OTP numérico por defecto (T01-T04, R04) |
| TM-06 | Reutilización del token | Carrera de dos peticiones con el mismo token; token válido tras usarse | ASVS 2.7.3 | `UPDATE ... WHERE used_at IS NULL` atómico; consumir invalida todos los del mismo propósito (T07-T09) |
| TM-07 | Confusión de tipos | Token de verificación usado para reset (o viceversa) | ASVS 2.5.x | Prefijo + columna `purpose` + filtro obligatorio (T05-T06) |
| TM-08 | Tokens predecibles o reversibles desde BD | JWT sin estado (no revocable), hash sin sal no aplica aquí; lectura de BD/backup revela token en claro | ASVS 2.5.1, 2.10 | Solo hash SHA-256 en BD; nunca en `jobs.payload` (T10-T11, Q02) |
| TM-09 | Fuga por URL / Referer / logs | Token en query string → logs de proxy/CDN, historial, `Referer` a analíticas del frontend | ASVS 3.1.1, 7.1.1 | Token en fragmento `#token=`, consumo solo por POST, guía de `Referrer-Policy` para el frontend (L02-L05) |
| TM-10 | Pre-carga por escáneres de correo | Safe Links/antivirus hacen GET del enlace y consumen el token de un solo uso | — | GET nunca consume; el frontend hace POST (L04) |
| TM-11 | Host header injection / enlace envenenado | Enlace construido con `request.base_url`, `Host` o `X-Forwarded-Host` → el atacante pide un reset para la víctima y recibe su token en su dominio | WSTG-INPV-17, API8 | Enlaces solo desde plantilla configurada y validada (L01, C06) |
| TM-12 | Envío a dirección controlada por el atacante | `{"email": ["victima@x","atacante@y"]}` (patrón CVE-2023-7028 de GitLab) o variante Unicode que colisiona al normalizar | API2 | Esquema estricto de un solo `EmailStr`; destinatario siempre `users.email` de BD (E09-E10) |
| TM-13 | Email bombing / spam relay / coste para el cliente | Bucle sobre forgot/resend/register para una víctima; miles de altas con emails ajenos; texto de phishing en `full_name` enviado desde el dominio del cliente | API4, API6 | Límites por IP, por cuenta (en BD) y globales con cortacircuitos; sin texto libre del usuario en correos pre-verificación (R01-R08, M08) |
| TM-14 | Llenado de la cola | Peticiones distribuidas que insertan un job cada una | API4 | Límite global del endpoint, trabajos de sistema con límites propios, depuración de payload (R06, Q01, Q08) |
| TM-15 | Toma previa de cuenta (pre-account takeover) | El atacante registra el email de la víctima con su contraseña; la víctima pulsa "verificar" o se registra después | ASVS 2.5.x | Re-registro NO reenvía verificación de la contraseña del atacante; la verificación no inicia sesión; reset revoca todo; purga de no verificadas (E03-E04, F05, F11, S01) |
| TM-16 | Sesiones que sobreviven al reset | El atacante con sesión robada sigue dentro tras el reset | ASVS 3.3.3 | Reset = `revoke_all_sessions` + `password_changed_at` (S01-S03) |
| TM-17 | Interacción con bloqueo inteligente y rate limit | El reset no puede usarse para medir bloqueo; un bloqueo no debe impedir recuperar la cuenta; contadores en memoria por proceso | ASVS 2.2.1 | Reset independiente del bloqueo y lo limpia al completarse; límites por cuenta en BD (S04-S06, R07) |
| TM-18 | Canal de tiempo | Diferencias medibles entre camino existe/no existe (Argon2, INSERT, envío síncrono) | ASVS 2.2.x | Rutas de igual trabajo; envío siempre asíncrono (E02, E07, ST-03/ST-07) |
| TM-19 | Cuentas no verificadas | Acceso completo con un email no probado; squatting de emails | ASVS 2.5.x | `EMAIL_VERIFICATION_REQUIRED` por defecto; migración marca verificados a los existentes (F10-F14) |
| TM-20 | Inyección en plantillas y cabeceras | `full_name` con HTML; CR/LF en asunto/From; SSTI si el cliente edita plantillas; `lang` usado como ruta | ASVS 5.2.5, 5.3.x | Autoescape, entorno sandbox, `EmailMessage` con política estricta, `lang` en lista blanca (M01-M09) |
| TM-21 | Secretos SMTP/API en `.env`, logs y trabajos | `smtplib.set_debuglevel`, logs de `httpx` con cabeceras, excepción del proveedor guardada en `job.error`, API con credenciales que no necesita | ASVS 2.10.4, 7.1.1, 14.1 | `SecretStr`, solo el worker recibe credenciales, lista de lo que no se loguea (C09-C12, G01-G06) |
| TM-22 | Transporte inseguro al proveedor | SMTP sin TLS o sin verificar certificado; redirecciones HTTP | ASVS 9.2.1, API10 | STARTTLS/TLS verificado, `none` prohibido en producción (C07-C08) |
| TM-23 | Duplicados y correos obsoletos por la cola | Reintento tras aceptación SMTP, lease perdido, backlog de horas que envía un reset caducado | — | Idempotencia por `job_id`, timeouts < timeout de tarea, clasificación de errores, frescura (Q03-Q07) |
| TM-24 | Cambio de email como vector de toma de cuenta | Sesión robada cambia el email y luego hace reset; confirmación sin reautenticación | ASVS 3.7.1, 2.2.3 | Contraseña actual, token al nuevo, aviso al antiguo, revocación de sesiones (F20-F26) |
| TM-25 | Configuración insegura por defecto / dependencia del freelancer | Remitente del freelancer embebido; backend `console` en producción imprimiendo enlaces | API8 | Sin valores del freelancer; fallo explícito al arrancar en producción (C01-C05) |

---

## 3. Decisiones de diseño recomendadas (resumen argumentado)

1. **Cerrar la enumeración del registro ahora.** `POST /auth/register` responde siempre
   `202 {"detail": "..."}` sin `id` ni datos del usuario. Si el email es nuevo: se crea la
   cuenta no verificada y se encola la verificación. Si ya existe: se calcula igualmente
   Argon2 (mismo coste), no se toca la cuenta y se encola un correo "ya existe una cuenta
   con este email; inicia sesión o recupera tu contraseña". Es un cambio incompatible
   (201 → 202): documentarlo en el changelog del generador.
2. **El token lo genera el worker, no la API.** El worker no tiene `SECRET_KEY` y
   `jobs.payload` persiste en claro 7 días. Payload del job = `{purpose, user_id | email,
   lang}`; el worker genera el token, guarda su hash, envía y marca `sent_at`. Así el token
   en claro solo existe en memoria del worker y en el buzón del usuario.
3. **La API no decide si el email existe en forgot/resend.** Siempre inserta un único job
   y devuelve 202; el worker resuelve el usuario y descarta en silencio (con auditoría) si no
   existe, está inactivo, ya está verificado o superó sus límites. Tiempo constante por
   construcción.
4. **Enlaces con el token en el fragmento** (`https://app.cliente.com/reset-password#token=...`):
   el fragmento no viaja en peticiones HTTP ni en `Referer`. El frontend lo lee, hace
   `history.replaceState` y lo envía por POST. La API nunca consume tokens por GET.
5. **Cuentas no verificadas:** con `EMAIL_VERIFICATION_REQUIRED=true` (por defecto), el
   login con contraseña correcta devuelve 403 `email_not_verified` sin emitir tokens; con
   contraseña incorrecta, el 401 habitual. La migración marca como verificados a los
   usuarios existentes (si no, se bloquea a toda la base instalada).
6. **Reset = cambio de contraseña completo:** reutiliza la ruta de `change_password`
   (hash, `password_changed_at`, `revoke_all_sessions`), invalida el resto de tokens,
   limpia el bloqueo, marca el email como verificado y notifica por correo.

---

## 4. Requisitos

### 4.1 Tokens (T)

- **REQ-T01 MUST** Tokens opacos generados con `secrets` (CSPRNG) con ≥256 bits de
  entropía: `prefijo + secrets.token_urlsafe(32)` (43 caracteres útiles). Prohibido JWT u
  otros tokens autocontenidos para estos flujos (no se pueden hacer de un solo uso).
- **REQ-T02 MUST** Prefijo distinto por propósito: `vt_` (verificación), `pr_` (reset),
  `ec_` (cambio de email). Validación de forma (prefijo + longitud 40–128) ANTES de hashear
  o consultar, como `looks_like_refresh_token`.
- **REQ-T03 MUST NOT** ofrecer por defecto códigos numéricos cortos (OTP de 6 dígitos). Si
  se añaden como opción para apps móviles: TTL ≤ 10 min, máximo 5 intentos por código con
  contador en BD y bloqueo del código al agotarse (ASVS 2.7.2, 2.7.6).
- **REQ-T04 MUST** Rechazar tokens sobredimensionados o con caracteres fuera de base64url
  con la misma respuesta 400 que un token inválido (sin 500 ni 422 que distinga).
- **REQ-T05 MUST** Columna `purpose` y filtro `purpose = :esperado` en TODA consulta de
  consumo; cada endpoint acepta solo su propósito.
- **REQ-T06 MUST** Un token de un propósito nunca sirve para otro, aunque se manipule el
  prefijo (el prefijo no sustituye al filtro por columna).
- **REQ-T07 MUST** Un solo uso: consumo con `UPDATE account_tokens SET used_at=now WHERE
  token_hash=:h AND purpose=:p AND used_at IS NULL AND expires_at > now` y comprobación de
  `rowcount == 1` (o `RETURNING`), en la misma transacción que el cambio que autoriza.
- **REQ-T08 MUST** Al consumir un token, invalidar todos los tokens pendientes del mismo
  usuario y propósito; al cambiar la contraseña (por cualquier vía) invalidar los de reset;
  al cambiar el email invalidar todos los pendientes del usuario.
- **REQ-T09 MUST** Caducidad fija en servidor: reset 30 min (configurable 10–60),
  verificación 48 h (configurable ≤ 7 días), cambio de email 60 min (configurable ≤ 24 h).
- **REQ-T10 MUST** En BD solo se guarda `SHA-256(token)` (hex, índice único). El token en
  claro no se guarda en ninguna tabla (tampoco `jobs.payload` ni `jobs.result`) ni se
  devuelve en ninguna respuesta de la API, tampoco en desarrollo.
- **REQ-T11 MUST** Vinculación: el token guarda `user_id` y la dirección destino (`email`).
  Se rechaza si `users.email` ya no coincide con el snapshot (verificación/reset) o si la
  cuenta está inactiva.
- **REQ-T12 SHOULD** Máximo 3 tokens activos por usuario y propósito (los más antiguos se
  invalidan al crear el cuarto) para tolerar reintentos de la cola sin dejar enlaces rotos.
- **REQ-T13 SHOULD** Purgar filas usadas/caducadas en `apigen db prune` (y oportunistamente),
  como se hace con refresh tokens.

### 4.2 Enumeración y respuesta uniforme (E)

- **REQ-E01 MUST** `POST /auth/register` devuelve el mismo código (202), cuerpo, cabeceras
  (sin `Location`) y forma para email nuevo, existente verificado y existente no verificado.
- **REQ-E02 MUST** Ambos caminos del registro ejecutan Argon2 (`hash_password`) y una única
  inserción de job; la diferencia de mediana entre caminos debe ser estadísticamente no
  significativa (ST-03).
- **REQ-E03 MUST** Registrar un email existente NO modifica la cuenta (ni contraseña, ni
  nombre) y NO reenvía un enlace de verificación que activaría la contraseña elegida por el
  primer registrante; envía el correo "ya tienes cuenta" (con enlace a login y a
  recuperación), sujeto a los límites por cuenta (REQ-R02).
- **REQ-E04 MUST** Una carrera de dos registros simultáneos con el mismo email (violación
  de `UNIQUE`) se mapea a la misma respuesta 202, nunca a 500/409.
- **REQ-E05 MUST** Eliminar el riesgo aceptado T3/SEC-05 de README y docstrings; si se
  mantiene un modo heredado con 409, que esté desactivado por defecto, solo con
  `EMAIL_VERIFICATION_REQUIRED=false` y documentado como riesgo aceptado del cliente.
- **REQ-E06 MUST** `forgot` y `verify-email/resend` devuelven siempre 202 con cuerpo
  idéntico, exista o no el email, esté bloqueado, inactivo, verificado o limitado.
- **REQ-E07 MUST** Esos endpoints no consultan al usuario en el camino de la petición:
  validan el esquema, insertan un job y responden. La decisión la toma el worker.
- **REQ-E08 MUST** Los errores de validación de esquema (422) dependen solo de la forma del
  input, nunca de la existencia de la cuenta.
- **REQ-E09 MUST** El campo `email` es un único `EmailStr` estricto (`StrictInput`,
  `extra="forbid"`); listas, objetos o campos duplicados → 422.
- **REQ-E10 MUST** El destinatario de cualquier correo de cuenta es `users.email` leído de
  BD (o el snapshot del token para el cambio de email), nunca la cadena recibida en la
  petición.

### 4.3 Flujos (F)

Recuperación de contraseña
- **REQ-F01 MUST** Consumo en orden: validar forma del token → buscar token vigente (sin
  consumir) → validar política de contraseña con `password_problems(new, user.email)`
  (422, NO consume el token) → Argon2 fuera de la transacción → transacción: consumo
  atómico (T07) + actualización de contraseña.
- **REQ-F02 MUST** Token inexistente, caducado, usado, de otro propósito o de cuenta
  inactiva → mismo 400 `invalid_or_expired_token` con el mismo cuerpo.
- **REQ-F03 MUST** La contraseña nueva cumple la misma política que registro/cambio.
- **REQ-F04 MUST** Tras el reset se envía una notificación "tu contraseña ha cambiado" a
  `users.email` (ASVS 2.2.3/2.5.5), sin token ni enlace de acción sensible; también tras
  `POST /users/me/password`.
- **REQ-F05 SHOULD** El reset no inicia sesión automáticamente (no devuelve tokens).
- **REQ-F06 SHOULD** Una cuenta bloqueada (`locked_until`) puede pedir y completar reset.

Verificación de email
- **REQ-F10 MUST** `EMAIL_VERIFICATION_REQUIRED` (por defecto `true` cuando hay backend de
  correo) controla si una cuenta no verificada puede autenticarse.
- **REQ-F11 MUST** Verificar el email no emite tokens ni inicia sesión, y es idempotente
  (una cuenta ya verificada con token usado → 400 genérico; sin cambios).
- **REQ-F12 MUST** Si la verificación es obligatoria, el login de una cuenta no verificada
  responde 403 `email_not_verified` SOLO tras verificar la contraseña con Argon2; con
  contraseña incorrecta sigue el 401 `invalid_credentials` y cuenta como fallo para el
  bloqueo. Ninguna otra vía (refresh, API keys si las hay) emite tokens a no verificados.
- **REQ-F13 MUST** La migración marca `email_verified_at` para los usuarios existentes, y
  el superusuario creado por `apigen` nace verificado.
- **REQ-F14 SHOULD** Purga de cuentas no verificadas tras `UNVERIFIED_ACCOUNT_TTL_DAYS`
  (p. ej. 7), con auditoría; libera emails "okupados".
- **REQ-F15 SHOULD** Usuarios creados por un admin: o bien nacen verificados por decisión
  explícita del admin, o reciben un token de invitación (propósito propio) para fijar su
  contraseña; nunca contraseñas enviadas por correo (ASVS 2.5.1).

Cambio de email
- **REQ-F20 MUST** Requiere sesión con scope de escritura y la contraseña actual
  (reautenticación, ASVS 3.7.1); el fallo de contraseña cuenta para el rate limit.
- **REQ-F21 MUST** El email no cambia hasta confirmar el token enviado a la NUEVA dirección.
- **REQ-F22 MUST** Respuesta 202 uniforme aunque la nueva dirección ya pertenezca a otra
  cuenta; la unicidad se re-comprueba al confirmar (y la restricción `UNIQUE` lo garantiza).
- **REQ-F23 MUST** Al solicitar Y al completar el cambio se notifica a la dirección
  ANTIGUA (sin tokens), indicando qué hacer si no fue el titular.
- **REQ-F24 MUST** Al completar: `email_verified_at = now`, invalidación de todos los
  tokens pendientes del usuario (T08) y revocación de sesiones (`revoke_all_sessions`).
- **REQ-F25 MUST** Ningún esquema de actualización de perfil (propio o admin) acepta
  `email` ni `email_verified_at` (mantener el estado actual; prueba de mass assignment).
- **REQ-F26 SHOULD** Si un admin cambia el email de un usuario, `email_verified_at` vuelve
  a `NULL` o se exige verificación.

### 4.4 Sesiones y bloqueo (S)

- **REQ-S01 MUST** Un reset completado incrementa `token_version`, revoca todos los refresh
  tokens (misma función `revoke_all_sessions`) y actualiza `password_changed_at`.
- **REQ-S02 MUST** Un access token emitido antes del reset es rechazado inmediatamente
  después (no espera a su caducidad).
- **REQ-S03 MUST** Tras el reset, una IP "conocida" anterior deja de estar exenta del
  bloqueo (consecuencia de `password_changed_at`; debe cubrirse con prueba).
- **REQ-S04 MUST** `forgot`, `resend` y `reset` no incrementan `failed_login_attempts` ni
  revelan el estado de bloqueo.
- **REQ-S05 SHOULD** Un reset completado pone `failed_login_attempts=0` y
  `locked_until=NULL` (el titular ha probado control del email) y marca el email verificado.
- **REQ-S06 MUST** Los tokens de reset inválidos no afectan a ninguna cuenta (no hay forma
  de bloquear a un tercero vía `/reset`).

### 4.5 Límites anti-abuso y coste (R)

- **REQ-R01 MUST** Límites SlowAPI por IP (`ip_key`, respetando `TRUSTED_PROXIES`):
  `forgot` y `resend` 5/minuto;20/hora; `reset`, `verify-email` y `email/confirm`
  10/minuto;50/hora; `users/me/email` como `RATE_LIMIT_LOGIN`. Configurables con variables
  `RATE_LIMIT_*` validadas por `_valid_limit`.
- **REQ-R02 MUST** Límite por cuenta y propósito aplicado en el worker con datos de BD
  (independiente de IP y del almacenamiento del limiter): enfriamiento ≥60 s entre correos
  y máximo 3/hora y 10/día. Excedido → no se envía, el job termina `succeeded` sin
  reintento y se audita `email.suppressed`.
- **REQ-R03 MUST** El correo "ya tienes cuenta" del registro comparte el cupo por cuenta de
  R02 (el registro no puede usarse para bombardear a un usuario existente).
- **REQ-R04 MUST** El 429 de los endpoints nuevos se audita como `auth.rate_limited`
  (ya ocurre para rutas con `/auth/`; comprobar que cubre `/users/me/email`).
- **REQ-R05 SHOULD** Cortacircuitos global de coste en el worker: `EMAIL_MAX_PER_HOUR` y
  `EMAIL_MAX_PER_DAY` (valores por defecto prudentes, p. ej. 200/1000); al superarse se
  suspende el envío, se audita a nivel ERROR y los jobs se reprograman o se descartan de
  forma documentada.
- **REQ-R06 SHOULD** Límite global (clave compartida) en `forgot`/`resend`/`register` para
  frenar la inundación distribuida de la cola.
- **REQ-R07 SHOULD** Documentar que con `memory://` y `WEB_CONCURRENCY>1` los límites por IP
  se multiplican por proceso; en producción recomendar Redis. R02 no depende de esto.
- **REQ-R08 MUST NOT** enviar correos a direcciones sin cuenta en `forgot`/`resend`
  (evita convertir la API en relé de spam hacia terceros).

### 4.6 Enlaces (L)

- **REQ-L01 MUST** Los enlaces se construyen exclusivamente desde plantillas de URL de
  configuración (`EMAIL_LINK_VERIFY`, `EMAIL_LINK_RESET`, `EMAIL_LINK_EMAIL_CHANGE`, o
  `FRONTEND_URL` + rutas); jamás desde `request.base_url`, `Host`, `X-Forwarded-Host`,
  `Origin`, `Referer` ni ningún parámetro de la petición (p. ej. `redirect_url`).
- **REQ-L02 MUST** Las plantillas contienen `{token}` exactamente una vez; el token se
  inserta URL-encoded.
- **REQ-L03 SHOULD** Por defecto el token va en el fragmento (`#token=`). Si el cliente
  necesita query string, arrancar con aviso y documentar en la guía del frontend:
  `Referrer-Policy: no-referrer`, sin scripts de terceros en esa página antes del consumo y
  `history.replaceState` para retirar el token.
- **REQ-L04 MUST** La API solo consume tokens por POST con el token en el cuerpo JSON; no
  existe endpoint GET que consuma o valide tokens.
- **REQ-L05 MUST** Respuestas de los endpoints de token con `Cache-Control: no-store`.

### 4.7 Configuración por cliente y valores seguros por defecto (C)

- **REQ-C01 MUST** Ningún valor del freelancer (email, dominio, nombre, claves) en código,
  plantillas, `.env.example` ni en lo que genera `apigen`. Ejemplos con `example.com`.
- **REQ-C02 MUST** `EMAIL_BACKEND` ∈ {`console`, `memory`, `smtp`, proveedores HTTP
  soportados, `disabled`}. Por defecto: `console` en development, `memory` en testing,
  **sin valor por defecto en production**.
- **REQ-C03 MUST** En producción la app y el worker se niegan a arrancar (`_check_security`)
  si: `EMAIL_BACKEND` falta o es `console`/`memory`; falta `EMAIL_FROM` o alguna plantilla de
  enlace; `EMAIL_FROM` usa `example.com/.org/.net`, `localhost` o `.test`; los enlaces no son
  `https`; falta la credencial del backend (comprobación en el proceso worker).
- **REQ-C04 MUST** `EMAIL_BACKEND=disabled` es una elección explícita: los endpoints de
  forgot/resend/cambio de email responden 404/403 documentado y
  `EMAIL_VERIFICATION_REQUIRED` debe ser `false` (combinación contradictoria → error al
  arrancar).
- **REQ-C05 MUST** El backend `console` solo imprime en desarrollo, con aviso visible de que
  el enlace contiene un token; `memory` solo en testing.
- **REQ-C06 MUST** Validación de configuración: `EMAIL_FROM`/`EMAIL_REPLY_TO` como direcciones
  únicas válidas sin CR/LF; `EMAIL_FROM_NAME`, marca y URLs sin CR/LF y con longitud acotada;
  URLs absolutas (https en producción; http solo a `localhost` fuera de ella).
- **REQ-C07 MUST** SMTP: `EMAIL_SMTP_SECURITY` ∈ {`starttls`, `ssl`, `none`} con verificación
  de certificado (`ssl.create_default_context()`); `none` prohibido en producción salvo
  destino loopback y opt-in explícito (`EMAIL_SMTP_ALLOW_INSECURE=true`). STARTTLS debe fallar
  si el servidor no lo anuncia (sin degradar a texto plano).
- **REQ-C08 MUST** Proveedores HTTP: endpoints fijos del proveedor en código (o, si se
  permite URL propia, solo `https` y validada al arrancar), TLS verificado, sin seguir
  redirecciones, timeout de conexión y total.
- **REQ-C09 MUST** Credenciales (`EMAIL_SMTP_PASSWORD`, `EMAIL_API_KEY`...) como `SecretStr`;
  nunca en `repr`, errores de validación ni en `/health`/`/docs`.
- **REQ-C10 MUST** Mínimo privilegio: solo el worker necesita las credenciales de envío;
  `docker-compose.yml` no se las pasa al servicio API (mismo criterio que `SECRET_KEY` en
  el worker, SEC-38). La API solo necesita saber qué backend y qué URLs hay.
- **REQ-C11 SHOULD** Soportar variantes `*_FILE` (Docker secrets) para las credenciales.
- **REQ-C12 SHOULD** `apigen init-env` genera las variables de email con marcadores vacíos y
  comentarios; `apigen` incluye un comando de prueba de envío (`apigen email test <dest>`)
  que no imprime credenciales.
- **REQ-C13 SHOULD** `EMAIL_DEFAULT_LANGUAGE` e `EMAIL_LANGUAGES` validados contra las
  plantillas presentes al arrancar.
- **REQ-C14 SHOULD** La documentación para el comprador exige SPF, DKIM y DMARC en su
  dominio remitente.

### 4.8 Plantillas y construcción del mensaje (M)

- **REQ-M01 MUST** Jinja2 con `autoescape` activado para HTML y `StrictUndefined`; parte de
  texto plano alternativa.
- **REQ-M02 MUST** `SandboxedEnvironment` si el cliente puede aportar plantillas propias
  (`EMAIL_TEMPLATES_DIR`); nombres de plantilla fijos en código, nunca derivados del input.
- **REQ-M03 MUST** `lang` validado contra la lista `EMAIL_LANGUAGES` (formato
  `^[a-z]{2}(-[A-Z]{2})?$`) antes de usarse; si no, idioma por defecto. Nunca se concatena
  el valor recibido a una ruta.
- **REQ-M04 MUST** Mensajes con `email.message.EmailMessage` y `policy=email.policy.default`
  (rechaza CR/LF en cabeceras); `To`/`From` con `formataddr`; el asunto proviene de
  catálogos de traducción, no del input del usuario.
- **REQ-M05 MUST** Ninguna cabecera ni el asunto contiene datos controlados por el usuario.
- **REQ-M06 MUST** Correos a direcciones aún no probadas (verificación, "ya tienes cuenta",
  confirmación de cambio de email) no incluyen texto libre del usuario (`full_name`, etc.):
  impide usar el dominio del cliente como relé de phishing.
- **REQ-M07 MUST** En notificaciones a usuarios verificados, `full_name` va escapado y
  truncado (≤120).
- **REQ-M08 MUST** Los enlaces del correo solo provienen de las plantillas de URL (L01) y de
  URLs de marca configuradas (logo/soporte, https).
- **REQ-M09 SHOULD** Sin píxeles de seguimiento ni recursos remotos por defecto; cabecera
  `Auto-Submitted: auto-generated`.

### 4.9 Cola de trabajos (Q)

- **REQ-Q01 MUST** Los jobs de correo son de sistema (`owner_id=None`): no aparecen en
  `/jobs` de usuarios, no se pueden cancelar desde la API ni consumen
  `JOBS_MAX_PENDING_PER_USER`.
- **REQ-Q02 MUST** `jobs.payload` y `jobs.result` no contienen tokens en claro, contraseñas,
  enlaces con token ni el cuerpo renderizado. Payload: `purpose`, `user_id` o email
  normalizado (solo en forgot/resend/register), `lang`, `requested_at`.
- **REQ-Q03 SHOULD** Tras terminar, el worker reduce el payload de los jobs de correo (p. ej.
  sustituir el email por `user_id` o eliminarlo) para no retener PII durante
  `JOBS_RETENTION_DAYS`.
- **REQ-Q04 MUST** Idempotencia por `job_id`: si ya existe un token con `job_id` y `sent_at`
  no nulo, el reintento no envía otra vez. Documentar la ventana residual "al menos una vez"
  (caída entre la aceptación del proveedor y el `UPDATE sent_at`).
- **REQ-Q05 MUST** Timeout de SMTP/HTTP (p. ej. 20–30 s) claramente menor que el `timeout`
  de la tarea, y este menor que el arrendamiento (`timeout + JOBS_LEASE_GRACE`), para que un
  envío lento no se re-reclame y duplique.
- **REQ-Q06 MUST** Clasificación de errores: permanentes (SMTP 5xx, HTTP 400/401/403/422 del
  proveedor, destinatario rechazado) → `TaskError(retry=False)`; transitorios (conexión,
  timeout, SMTP 4xx, HTTP 429/5xx) → reintento con el backoff existente;
  `max_attempts` ≤ 5.
- **REQ-Q07 MUST** Revalidación en el momento del envío: usuario existe y está activo, el
  email no ha cambiado, la verificación sigue pendiente (para `verify`), y el job no es más
  antiguo que la vida del token de su propósito (no enviar resets obsoletos tras un
  atasco de la cola).
- **REQ-Q08 MUST** `job.error` contiene solo mensajes genéricos (`"Email delivery failed
  (transient)"`), nunca la respuesta cruda del proveedor, direcciones ni credenciales
  (`job.error` es visible por API para admins).
- **REQ-Q09 SHOULD** Clave de idempotencia del proveedor = `job_id` cuando el proveedor la
  soporte.

### 4.10 Registros y auditoría (G)

- **REQ-G01 MUST NOT loguear**: tokens (en claro ni hash), enlaces con token, cuerpo
  renderizado, contraseñas, credenciales SMTP/API, cabecera `Authorization`, respuesta cruda
  del proveedor, direcciones de email completas.
- **REQ-G02 MUST** `smtplib` con `debuglevel=0` siempre; loggers `httpx`/`httpcore` a
  WARNING o superior en el worker; ninguna excepción con credenciales en su mensaje se
  propaga al log (envolverlas).
- **REQ-G03 MUST** Eventos de auditoría (vía `audit()`, solo IDs e IP):
  `auth.register` / `auth.register.duplicate`, `auth.email_verification.sent|verified|invalid_token`,
  `auth.password_reset.requested|sent|completed|invalid_token`,
  `auth.email_change.requested|completed`, `auth.login.unverified`,
  `email.suppressed` (motivo: `unknown_email|inactive|cooldown|quota|circuit_open`),
  `email.send.failed` (backend, clase de error, `job_id`).
- **REQ-G04 MUST** Para emails sin cuenta se audita `reason=unknown_email` sin la dirección.
- **REQ-G05 SHOULD** Emails enmascarados si hacen falta en logs operativos (`a***@d***.com`).
- **REQ-G06 SHOULD** Alerta (nivel ERROR) ante: fallo de autenticación con el proveedor,
  cortacircuitos abierto, pico de `invalid_token` desde una IP.

---

## 5. Casos de prueba de seguridad exigidos en la validación final

Se ejecutarán como tests (`tests/`) y, donde aplique, en el laboratorio local
(`./security/lab.sh`) con el backend `memory`/`console`. Todos son bloqueantes salvo que se
indique.

Enumeración y tiempo
- **ST-01** (E01) Registro con email nuevo, existente verificado y existente no verificado:
  mismo status, cuerpo byte a byte y cabeceras (ignorando `X-Request-ID`/rate limit).
- **ST-02** (E03) Registrar un email existente con otra contraseña: el hash y el nombre no
  cambian; se encola "ya tienes cuenta"; NO se encola verificación.
- **ST-03** (E02, E07) Tiempo: 200 peticiones alternadas por caso (registro existente/nuevo;
  forgot existente/inexistente); diferencia de medianas < 5 ms y test de Mann-Whitney sin
  significancia (p > 0,01).
- **ST-04** (E04) Dos registros concurrentes del mismo email → ambos 202, una sola fila.
- **ST-05** (E06) `forgot`/`resend` con email inexistente, inactivo, bloqueado, ya
  verificado y en cooldown → respuestas idénticas.
- **ST-06** (E09) `{"email": ["a@x.com","b@y.com"]}`, objeto, campo extra → 422 y ningún job.
- **ST-07** (E10) Usuario `Victim@Example.com` guardado en minúsculas; forgot con variantes de
  mayúsculas/Unicode → el correo sale a la dirección de BD, nunca a la tecleada.
- **ST-08** (F12) Cuenta no verificada: contraseña mala → 401 idéntico al resto y cuenta para
  bloqueo; contraseña buena → 403 `email_not_verified` sin tokens.
- **ST-09** (F22) Cambio de email a una dirección ocupada → 202 idéntico al caso libre.

Tokens
- **ST-10** (T01, T10) Inspección de BD tras cada flujo: solo hashes de 64 hex; ningún token
  en `jobs.payload`/`jobs.result`/`job.error`; tokens generados con prefijo y ≥43 caracteres
  aleatorios.
- **ST-11** (T07) Reutilizar un token de reset → 400; dos consumos concurrentes → exactamente
  uno 204.
- **ST-12** (T09) Token caducado (reloj adelantado) → 400 idéntico al token inexistente.
- **ST-13** (T05, T06) Token de verificación en `/reset`, de reset en `/verify-email`, y con
  prefijo cambiado → 400.
- **ST-14** (T08) Pedir 2 resets y usar uno → el otro queda inválido; cambiar contraseña por
  `/users/me/password` → resets pendientes inválidos; cambiar email → todo pendiente inválido.
- **ST-15** (T11) Token de verificación emitido para el email A; el usuario pasa a B → el
  token de A ya no verifica.
- **ST-16** (T04) Token de 10 KB, con NUL, con caracteres no base64url → 400 genérico, sin 500.
- **ST-17** (F01) Reset con contraseña débil → 422 y el token sigue siendo válido después.

Sesiones y bloqueo
- **ST-18** (S01, S02) Con access y refresh válidos, completar reset → access da 401 al
  instante y refresh da 401.
- **ST-19** (S03) IP conocida antes del reset deja de estar exenta del bloqueo tras él.
- **ST-20** (S04, S06) 50 `forgot`/`reset` inválidos no alteran `failed_login_attempts` ni
  `locked_until` de ninguna cuenta.
- **ST-21** (F06, S05) Cuenta bloqueada completa el reset y puede iniciar sesión.
- **ST-22** (F11) Verificar email no devuelve tokens; login posterior funciona.
- **ST-23** Toma previa: atacante registra el email de la víctima; la víctima hace reset →
  cualquier sesión del atacante queda revocada y su contraseña deja de valer.

Abuso y límites
- **ST-24** (R01) Superar el límite por IP en cada endpoint nuevo → 429 y evento
  `auth.rate_limited`.
- **ST-25** (R02, R03) Rotando IPs (X-Forwarded-For con `TRUSTED_PROXIES` de laboratorio):
  como máximo 3 correos/hora a la misma cuenta sumando forgot + resend + registro duplicado;
  el resto `email.suppressed`.
- **ST-26** (R05, SHOULD) Superar `EMAIL_MAX_PER_HOUR` abre el cortacircuitos y audita ERROR.
- **ST-27** (R08) `forgot` a email inexistente no produce ningún envío.

Enlaces y cabeceras
- **ST-28** (L01) `forgot` con `Host: evil.test`, `X-Forwarded-Host: evil.test`,
  `Origin`/`Referer` maliciosos → el enlace del correo usa solo el dominio configurado.
- **ST-29** (L02-L04) El token del correo va en el fragmento por defecto; GET a cualquier URL
  con el token no lo consume (no hay ruta GET); respuestas con `Cache-Control: no-store`.
- **ST-30** (M01, M07) `full_name = "<img src=x onerror=alert(1)><a href=//evil>"` → aparece
  escapado en notificaciones; (M06) no aparece en verificación ni "ya tienes cuenta".
- **ST-31** (M04, M05, C06) CR/LF en `EMAIL_FROM_NAME`, marca o cualquier campo que llegue a
  cabeceras → error al arrancar o excepción controlada; nunca cabecera inyectada.
- **ST-32** (M03) `lang=../../etc/passwd`, `lang=xx` → idioma por defecto, sin acceso a
  ficheros.
- **ST-33** (M02, si hay plantillas del cliente) Plantilla con `{{ ''.__class__.__mro__ }}`
  → `SecurityError` del sandbox.

Configuración y secretos
- **ST-34** (C03) `ENVIRONMENT=production` con `EMAIL_BACKEND` ausente, `console` o `memory`;
  sin `EMAIL_FROM`; remitente `@example.com`; enlaces `http://` → la app no arranca con
  mensaje claro.
- **ST-35** (C04) `EMAIL_BACKEND=disabled` + `EMAIL_VERIFICATION_REQUIRED=true` → error al
  arrancar.
- **ST-36** (C07) SMTP `none` en producción sin opt-in → error; servidor de laboratorio sin
  STARTTLS con `starttls` → fallo, no degradación; certificado autofirmado → fallo.
- **ST-37** (C09, G01, G02) Con `LOG_LEVEL=DEBUG` y JSON, ejecutar todos los flujos
  (incluido un fallo de autenticación SMTP y un 401 del proveedor HTTP): grep del log y de
  `jobs` sin tokens, enlaces, contraseña SMTP, API key ni emails completos.
- **ST-38** (C10) `docker compose config`: el servicio API no recibe credenciales de correo.
- **ST-39** (C01) Búsqueda en el repositorio y en un proyecto generado con `apigen`: ningún
  email/dominio del freelancer.

Cola
- **ST-40** (Q01) Un usuario no ve ni cancela los jobs de sus correos en `/jobs`.
- **ST-41** (Q04) Simular fallo tras envío aceptado y antes de `complete()` sin que exista
  `sent_at`, y con `sent_at` ya escrito → en el segundo caso el reintento no reenvía.
- **ST-42** (Q06) SMTP 550 → `failed` sin reintento; SMTP 421/timeout → reintento con backoff;
  `job.error` genérico.
- **ST-43** (Q07) Job de reset más antiguo que la vida del token, usuario desactivado o email
  cambiado entre encolado y envío → no se envía, se audita.
- **ST-44** (F04, F23) Tras reset, cambio de contraseña y cambio de email llegan las
  notificaciones (a la dirección antigua en el cambio de email) y no contienen tokens.
- **ST-45** (F13) Tras la migración, los usuarios existentes pueden iniciar sesión con
  `EMAIL_VERIFICATION_REQUIRED=true`.

---

## 6. Riesgos residuales a documentar para el comprador

- Entrega "al menos una vez": una caída entre la aceptación del proveedor y el registro de
  `sent_at` puede duplicar un correo (ambos enlaces válidos gracias a REQ-T12).
- Quien controle el buzón del usuario controla la cuenta (inherente a la recuperación por
  email); mitigable en el futuro con MFA.
- Un registrante malicioso puede ocupar temporalmente un email no verificado hasta la purga
  (REQ-F14); el titular real puede recuperarlo por reset.
- La protección del token en el frontend (fragmento, Referrer-Policy, sin terceros) depende
  del frontend del cliente: se entrega como guía, no se puede verificar desde la API.
