# Fase 2 · Plan desde el punto de vista del usuario

Recuperación de contraseña, verificación de email y envío de correo configurable por cliente.

Autor: agente `user` (dos sombreros: **freelancer** que vende y entrega APIs hechas con la
plantilla, y **cliente** que las recibe con su frontend/app móvil).
Fecha: 2026-09-26. Documento de planificación: no hay código.

---

## 0. Lo que hay hoy y condiciona el diseño

Me he orientado con graphify y he leído README.txt §6, §7, §12, §13 y §14, `.env.example`,
`app/api/v1/endpoints/auth.py`, `users.py` (`change_password`), `app/models/user.py` y
`apigen check` / `apigen init-env`.

- **Auth**: `register` (201 `UserRead`, 409 `email_taken`, 403 `registration_disabled`),
  `login` (form OAuth2, 401 `invalid_credentials`), `refresh`, `logout`, `logout-all`,
  `POST /users/me/password` (cambia la contraseña y **revoca todas las sesiones**:
  `revoke_all_sessions`, sube `token_version`). La recuperación debería hacer lo mismo.
- **User**: no tiene `email_verified`/`email_verified_at`. Hará falta una migración, y hay que
  decidir qué pasa con las filas que ya existen (ver H-C6).
- **Errores**: `{"detail", "code"}` con `code` estable. Es lo que más aprecia un frontend y
  los nuevos flujos deben seguir la misma convención.
- **Worker**: la cola vive en la BD (`apigen worker`) con reintentos. Es el sitio natural para
  enviar correo sin frenar la petición. Ojo: **en docker compose el worker no recibe
  `SECRET_KEY`** (`PROCESS_ROLE=worker`). El worker no puede firmar tokens: el enlace tiene que
  generarse en la API y el worker solo lo envía.
- **Config**: todo va por `.env`, que documenta `.env.example`. `apigen init-env [--production]`
  imprime qué rellenar y `apigen check` muestra un resumen con avisos. El correo tiene que
  entrar en los tres sitios.
- **Entrega**: `make new-api NAME=... LANG=es`, `apigen docs --lang --base-url` (README.md del
  cliente, conserva lo que está fuera de los marcadores), `make deliver` (zip) y la colección
  Postman estática en `docs/postman/`.
- **Escáner de secretos de `new_api.py`**: bloquea el commit si hay **emails que no sean de
  ejemplo** en ficheros versionados. Si las plantillas de email llevan escrito
  `soporte@cliente.com`, el freelancer choca con el escáner. Los datos de marca y contacto
  tienen que ir en `.env`, no en ficheros versionados (ver F-03).

---

## 1. Historias de usuario: FREELANCER

### H-F1 · Configurar el correo de un cliente nuevo en minutos (MUST)
> Como freelancer, quiero dejar el correo de un cliente listo cambiando solo variables de
> `.env`, sin tocar código, para entregar el mismo día.

Criterios de aceptación:
- Todas las opciones están en un bloque `# --- Correo ---` de `.env.example`, cada una con su
  comentario (como el resto del fichero).
- Para un cliente con SMTP basta con 5 o 6 variables: `MAIL_BACKEND=smtp`, `SMTP_HOST`,
  `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `MAIL_FROM`, más `FRONTEND_URL`.
- `apigen init-env --production` lista las variables de correo en su mensaje de "rellena
  esto".
- `apigen check` añade filas: `Correo: smtp (smtp.cliente.com:587, STARTTLS)`,
  `Remitente: "Tienda" <no-reply@tienda.com>`, `Verificación email: required`,
  `Frontend: https://app.tienda.com`, con avisos en amarillo (ver §3.6).
- **No queda nada del freelancer**: sin remitente, dominio, logo ni firma por defecto que
  apunten a mí. Los valores por defecto son neutros (`PROJECT_NAME`, `no-reply@example.com`)
  y en producción un valor de ejemplo impide arrancar.

### H-F2 · Probar en local sin proveedor real (MUST)
> Como freelancer, quiero registrarme, recuperar la contraseña y verificar el email en local
> sin cuenta de proveedor, copiando el enlace desde la terminal.

Criterios:
- `MAIL_BACKEND=console` es el **valor por defecto en development**: el correo (asunto, texto y
  enlace) se imprime en el log de la API o del worker, con el enlace en una línea propia fácil
  de copiar.
- `MAIL_BACKEND=file` escribe cada correo como `.eml` (y opcionalmente `.html`) en
  `MAIL_FILE_DIR` (por defecto `./var/mail/`, ignorado por git). Así se revisa el HTML en el
  navegador y los tests pueden leerlo.
- Si en development no hay worker en marcha, el correo **sale igual**: envío en línea o un
  aviso claro en el log ("correo encolado; arranca `apigen worker`"). No quiero perder media
  hora buscando por qué no llega nada.
- Con SMTP local (Mailpit/MailHog en `localhost:1025`) funciona sin TLS ni credenciales. Un
  servicio `mailpit` opcional en docker compose (perfil `dev`) sería un buen extra (COULD).
- En `production`, `console` y `file` **dan error al arrancar**, salvo confirmación explícita
  (`ALLOW_DEV_MAIL_IN_PRODUCTION=true`, igual que `ALLOW_SQLITE_IN_PRODUCTION`).

### H-F3 · Cambiar de proveedor sin tocar código (MUST para SMTP, SHOULD para API HTTP)
> Como freelancer, quiero pasar de Gmail/Zoho SMTP a Brevo/SES/Resend solo con `.env`.

Criterios:
- Cambiar `MAIL_BACKEND` y sus credenciales basta. Las plantillas y las URLs no cambian.
- Todos los proveedores serios (SES, Brevo, Mailgun, SendGrid, Postmark, Resend, Zoho, M365)
  ofrecen SMTP. Con **SMTP genérico** bien hecho (STARTTLS/SSL, timeout, reintentos del worker)
  cubro el 95 % de los clientes.
- Hay un comando de prueba: `apigen mail test destino@cliente.com [--template reset]`, que
  envía un correo real con la configuración actual y **muestra el error del proveedor
  traducido** ("autenticación SMTP rechazada: revisa SMTP_USERNAME/SMTP_PASSWORD", "puerto 465
  requiere SMTP_SECURITY=ssl", "timeout conectando a smtp.x:587"). Es lo que más tiempo me
  ahorra en la entrega.

### H-F4 · Personalizar marca, textos e idioma sin tocar código (MUST marca+idioma, SHOULD plantillas propias)
> Como freelancer, quiero que el correo lleve el nombre, logo, color y tono del cliente, y en
> su idioma, sin editar Python.

Criterios:
- Marca por `.env`: `MAIL_BRAND_NAME` (por defecto `PROJECT_NAME`), `MAIL_BRAND_LOGO_URL`,
  `MAIL_BRAND_COLOR`, `MAIL_SUPPORT_EMAIL`, `MAIL_FOOTER` (texto legal / dirección postal).
- Plantillas por defecto en **es y en** (los mismos idiomas que `apigen docs`), limpias y
  sobrias, que se vean bien sin logo.
- Para personalizar más: copio las plantillas a una carpeta de **overrides** del proyecto que
  la plantilla nunca sobrescribe (como los hooks). Una plantilla con override gana a la de
  serie, y si solo cambio el asunto no tengo que copiar el HTML.
- `apigen mail preview reset --lang es` genera el HTML y el texto con datos ficticios en
  `var/mail/preview/` para enseñárselo al cliente antes de entregar (SHOULD).
- Un error en una plantilla (variable inexistente, sintaxis) **se detecta en `apigen check`
  o en los tests**, no con el primer usuario real que pide un reset.

### H-F5 · Entregar al cliente (MUST)
> Como freelancer, quiero que el zip y el README del cliente expliquen el correo sin que yo
> escriba nada a mano.

Criterios:
- `apigen docs` añade al README.md del cliente una sección **"Cuentas: verificación de email y
  recuperación de contraseña"** con: los endpoints, el flujo paso a paso, el formato exacto
  del enlace que recibirá su frontend (`{FRONTEND_URL}{RESET_PATH}?token=...`), lo que debe
  hacer la página del frontend, los `code` de error, el modo de verificación configurado y las
  variables de correo para desplegar.
- La sección de despliegue del README lista las variables de correo con las obligatorias
  marcadas, y recuerda configurar **SPF/DKIM/DMARC del dominio del remitente** (sin eso el
  correo acaba en spam y el cliente me escribe a mí).
- `make deliver` incluye las plantillas por defecto y los overrides, y excluye `var/mail/`.
- El escáner de `new_api.py` no bloquea por culpa de las plantillas de serie (solo usan
  variables y `example.com`).

### H-F6 · Postman (MUST)
- La colección añade una carpeta **Account** con: `Request password reset`, `Reset password`,
  `Verify email`, `Resend verification`.
- Nuevas variables de colección `resetToken` y `verifyToken` (en "Current value"), con una nota
  en la descripción: "en local, copia el token del log de la API (MAIL_BACKEND=console)".
- Verificada con newman como el resto. Con `MAIL_BACKEND=file` un script de prueba podría leer
  el token del `.eml` (COULD).

---

## 2. Historias de usuario: CLIENTE / FRONTEND

### H-C1 · Pedir recuperación de contraseña (MUST)
`POST /api/v1/auth/password/forgot`, JSON `{"email": "..."}`
- Responde **siempre 202** con `{"detail": "If the email exists, we have sent instructions"}`,
  exista o no la cuenta (así no se enumeran cuentas; al frontend le da igual, solo necesita un
  mensaje fijo).
- 422 si el email tiene mal formato, 429 `rate_limited` con `Retry-After`.
- El frontend muestra "Si el email está registrado, recibirás un correo" y un contador para
  "reenviar" basado en `Retry-After`.

### H-C2 · Página "nueva contraseña" del frontend (MUST)
El correo lleva el enlace `{FRONTEND_URL}{MAIL_RESET_PATH}?token=<token>`
(por defecto `https://app.cliente.com/reset-password?token=...`).
- El frontend lee `token` de la URL y muestra el formulario.
- **Opcional, pero lo agradecería (SHOULD)**: `POST /auth/password/reset/validate` `{"token"}`
  → 204 si vale, o 400 `invalid_or_expired_token`. Así la página dice "el enlace ha caducado"
  **antes** de que el usuario escriba su nueva contraseña dos veces.
- `POST /api/v1/auth/password/reset`, JSON `{"token": "...", "new_password": "..."}`
  - 204 si todo va bien. **Cierra todas las sesiones** (como `/users/me/password`) y el frontend
    redirige al login con "contraseña cambiada". SHOULD: opción `PASSWORD_RESET_AUTO_LOGIN` que
    devuelva `TokenPair`, por defecto desactivada.
  - 400 `invalid_or_expired_token` (un solo código para caducado, usado o manipulado; el
    frontend no necesita distinguirlos).
  - 422 `password_policy` con el mismo formato que `/users/me/password` (el frontend reutiliza
    el mismo componente).
  - El token es **de un solo uso**. Pedir un reset nuevo invalida los anteriores, y cambiar la
    contraseña por otra vía también.
- El reset también **desbloquea la cuenta** si estaba bloqueada por intentos fallidos (si no,
  el usuario recupera la contraseña y sigue sin poder entrar: frustrante). A decidir con
  seguridad.
- El reset marca el email como verificado: si recibió el enlace, controla el buzón (SHOULD).

### H-C3 · Registro con verificación (MUST)
- `POST /auth/register` sigue devolviendo 201 `UserRead`, que ahora incluye
  `email_verified: bool`. Con verificación activa se envía el correo al registrarse.
- El enlace es `{FRONTEND_URL}{MAIL_VERIFY_PATH}?token=...` (por defecto `/verify-email`).
- **La página "email verificado" la construye el frontend**: lee el token, llama a
  `POST /api/v1/auth/email/verify` `{"token"}` y muestra el resultado.
  - 200 con `{"email": "...", "email_verified": true}` o 204.
  - Si ya estaba verificado: **también éxito**, no error. El usuario pulsa dos veces el enlace,
    el cliente de correo lo precarga (Outlook Safe Links) o lo abre en otro dispositivo; si
    respondemos error, el cliente recibe tickets de soporte.
  - 400 `invalid_or_expired_token` → la página ofrece "reenviar enlace".
- **Por qué `POST` y no `GET` directo a la API**: los escáneres de enlaces de los clientes de
  correo hacen GET automáticamente. Que el enlace apunte al frontend y este haga el POST evita
  verificaciones fantasma y deja la experiencia en la marca del cliente.
- COULD, para clientes **sin frontend web** (solo app móvil o solo API):
  `MAIL_VERIFY_MODE=api_page`, donde el enlace apunta a una página mínima servida por la propia
  API que confirma con un botón (POST) y muestra "Email verificado" con la marca. Para móvil lo
  normal es un deep link / universal link (`FRONTEND_URL=miapp://`); el README debe decir que
  vale cualquier esquema, validado contra una lista.

### H-C4 · Reenviar verificación (MUST)
- `POST /api/v1/auth/email/resend-verification`
  - **Autenticado** (usuario con sesión pero sin verificar, en modo `optional`): sin cuerpo,
    202.
  - **Sin autenticar** (modo `required`, el usuario no puede hacer login): JSON `{"email"}` →
    siempre 202 con mensaje neutro, igual que forgot.
  - 429 con `Retry-After` si pide demasiados. El frontend deshabilita el botón con cuenta atrás.
- Cada reenvío invalida el token anterior (o ambos siguen valiendo hasta caducar; a decidir,
  pero documentado).

### H-C5 · Login con verificación obligatoria (MUST)
- Contraseña correcta y email sin verificar en modo `required`: **403 `email_not_verified`**
  con un `detail` claro. Solo se devuelve si la contraseña es correcta, así que no enumera
  cuentas. El frontend muestra "Revisa tu correo" y el botón de reenviar.
- En modo `optional`: el login funciona, `GET /users/me` devuelve `email_verified: false` y el
  frontend muestra un aviso. SHOULD: permiso `verified_user` para que un recurso del YAML pueda
  exigir email verificado en ciertas acciones (`permission: verified`), y 403
  `email_not_verified` si no lo está.

### H-C6 · Usuarios ya existentes (MUST)
Al actualizar una API ya entregada, nadie debe quedarse fuera por sorpresa.
- La migración marca a **todos los usuarios existentes como verificados**
  (`email_verified_at = created_at` o `now`). El por defecto es este, documentado.
- Alternativa explícita: `apigen users mark-unverified --all` o una opción de migración para
  quien quiera forzar la verificación (COULD).
- Los usuarios creados por un admin (`POST /users`) y por `apigen createsuperuser` nacen
  **verificados** por defecto. SHOULD: opción `send_verification: true` en el alta de admin.
- Admin: `PATCH /users/{id}` permite `email_verified: true/false` (soporte manual) y
  `POST /users/{id}/send-password-reset` para que soporte envíe un enlace sin conocer la
  contraseña (SHOULD).

### H-C7 · Cambio de email (SHOULD, se puede posponer)
Si `PATCH /users/me` permite cambiar el email, con verificación activa el email nuevo debe
quedar sin verificar (o pendiente hasta confirmarlo) y conviene avisar al email antiguo. Si
esto no entra en la fase 2, **que se documente como limitación** y que cambiar el email ponga
`email_verified=false` como mínimo.

### H-C8 · Errores comprensibles (MUST)
Códigos nuevos, añadidos a la tabla de README §6 y al README del cliente:

| HTTP | code | Cuándo | Qué hace el frontend |
|---|---|---|---|
| 202 | — | forgot / resend (siempre) | mensaje neutro |
| 400 | `invalid_or_expired_token` | reset/verify con token malo, caducado o usado | ofrecer pedir otro |
| 403 | `email_not_verified` | login o acción con verificación requerida | pantalla "revisa tu correo" + reenviar |
| 403 | `password_reset_disabled` | la API del cliente no lo usa (sin correo configurado) | ocultar "olvidé mi contraseña" |
| 422 | `password_policy` | nueva contraseña débil | igual que hoy |
| 429 | `rate_limited` + `Retry-After` | demasiadas peticiones | cuenta atrás |
| 503 | `mail_unavailable` | **solo** si el envío es síncrono y falla | "inténtalo más tarde" |

Además, un endpoint público (o un campo en `/api/versions`) con las capacidades de la API,
`{"registration": true, "email_verification": "required", "password_reset": true}`, para que el
frontend muestre u oculte opciones sin hardcodearlas (SHOULD).

---

## 3. Configuración que espero

### 3.1 Variables sugeridas (bloque nuevo en `.env.example`)

```dotenv
# --- Correo ---------------------------------------------------------------------
# console (log; por defecto en development) | file (./var/mail) | smtp | none
# none = no se envía nada: recuperación y verificación quedan desactivadas (403).
MAIL_BACKEND=
# Remitente. Debe ser de un dominio del CLIENTE con SPF/DKIM configurados.
MAIL_FROM=no-reply@example.com
# Vacío = PROJECT_NAME
MAIL_FROM_NAME=
MAIL_REPLY_TO=
# Idioma de los correos: es | en (vacío = en)
MAIL_DEFAULT_LANGUAGE=en
# Idiomas con plantilla; se usa el del usuario (Accept-Language al registrarse
# o User.locale) si está en la lista, si no MAIL_DEFAULT_LANGUAGE.
MAIL_LANGUAGES=en,es

# Marca (en los correos). Vacío = sin logo, color neutro.
MAIL_BRAND_NAME=
MAIL_BRAND_LOGO_URL=
MAIL_BRAND_COLOR=#2563eb
MAIL_SUPPORT_EMAIL=
MAIL_FOOTER=

# SMTP (MAIL_BACKEND=smtp)
SMTP_HOST=
SMTP_PORT=587
# starttls (587) | ssl (465) | none (solo localhost / Mailpit)
SMTP_SECURITY=starttls
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_TIMEOUT=10

# Fichero (MAIL_BACKEND=file)
MAIL_FILE_DIR=./var/mail

# --- Frontend (enlaces de los correos) --------------------------------------------
# URL base de la web/app del cliente. Obligatoria si MAIL_BACKEND no es none.
# Acepta https://... o un esquema de app (miapp://) listado en FRONTEND_URL_SCHEMES.
FRONTEND_URL=http://localhost:3000
MAIL_RESET_PATH=/reset-password
MAIL_VERIFY_PATH=/verify-email

# --- Verificación de email y recuperación -----------------------------------------
# off | optional | required
EMAIL_VERIFICATION=off
EMAIL_VERIFICATION_TOKEN_HOURS=48
PASSWORD_RESET_ENABLED=true
PASSWORD_RESET_TOKEN_MINUTES=30
RATE_LIMIT_PASSWORD_FORGOT=5/hour
RATE_LIMIT_VERIFY_RESEND=5/hour
```

Notas para el equipo:
- **Una sola variable de URL** (`FRONTEND_URL`) más dos rutas. Nada de plantillas de URL con
  `{token}`: es propenso a errores. El README explica qué recibe el frontend.
- `EMAIL_VERIFICATION=off` por defecto: una API recién generada no debe dejar a nadie fuera por
  no tener correo configurado. `required` o `optional` se activan a conciencia. En producción,
  `EMAIL_VERIFICATION!=off` o `PASSWORD_RESET_ENABLED=true` con `MAIL_BACKEND=none|console|file`
  → **error al arrancar** con un mensaje que diga qué variable cambiar.
- Si `MAIL_BACKEND` está vacío: `console` en development/testing (en testing, mejor un backend
  en memoria para los tests) y **error** en producción si la recuperación está activa. Nada de
  "falla en silencio".
- `SMTP_PASSWORD` es un secreto y tiene que funcionar como variable de entorno real
  (Docker/Render). SHOULD: `SMTP_PASSWORD_FILE` para secretos de Docker, como
  `JWT_PRIVATE_KEY_FILE`.

### 3.2 Proveedores: qué merece la pena

| Backend | Prioridad | Por qué |
|---|---|---|
| `console` | MUST | desarrollo sin nada; enlace copiable |
| `file` (.eml + .html) | MUST | revisar el HTML, tests, demos al cliente |
| `smtp` genérico | MUST | cubre SES, Brevo, Mailgun, SendGrid, Postmark, Resend, Zoho, Gmail/Workspace, M365, Mailpit |
| `none` | MUST | cliente sin correo: los endpoints responden 403 claro |
| memoria (tests) | MUST (interno) | los tests leen el token sin tocar disco |
| API HTTP (Resend / Postmark / Brevo / SES API) | COULD | útil en PaaS que bloquean el puerto SMTP saliente (algunos planes de Render/Railway/DigitalOcean lo hacen). Si se añade, **solo uno o dos** con interfaz común (`MAIL_BACKEND=resend`, `MAIL_API_KEY`), sin SDKs pesados (httpx ya está) |
| Webhook genérico (`MAIL_BACKEND=webhook`, POST JSON a una URL del cliente) | COULD | el cliente enruta por su n8n/Zapier; cómodo para mí, pero hay que firmarlo (HMAC) |

Mi opinión como vendedor: **con SMTP genérico y un buen `apigen mail test` basta para
vender**. Los adaptadores HTTP dan para un upsell ("integración con tu proveedor") y no deben
retrasar la fase 2. Lo único que sí documentaría ya: "si tu hosting bloquea el puerto 587/465,
usa el puerto 2525 de tu proveedor (Brevo, Mailgun, SendGrid y Postmark lo ofrecen)".

### 3.3 Plantillas de email

- **Dónde viven**
  - De serie: dentro de la app (p. ej. `app/mail/templates/<lang>/<nombre>.{subject.txt,txt,html}`),
    versionadas, que se actualizan con la plantilla.
  - Overrides del proyecto: `mail_templates/<lang>/...` en la raíz (o la ruta de
    `MAIL_TEMPLATES_DIR`). **Nunca las toca apigen**, igual que los hooks. Se resuelve por
    orden override → serie, fichero a fichero.
  - `apigen mail eject [reset|verify|all] [--lang es]` copia las de serie a overrides para
    empezar a editar (SHOULD).
- **Formato**: siempre **texto plano y HTML** (multipart/alternative). El texto es obligatorio
  por entregabilidad y accesibilidad. Si solo existe el HTML, el texto se genera a partir de él
  (SHOULD). HTML con CSS en línea y tablas, sin JS ni recursos externos salvo el logo.
- **Motor**: Jinja2 (probablemente ya disponible por FastAPI/apigen) con **autoescape en
  HTML** y **modo estricto** (una variable indefinida es un error en `check`/tests, no un hueco
  vacío en producción).
- **Variables disponibles** (documentadas en el README y en la cabecera de cada plantilla):
  - Comunes: `brand_name`, `brand_logo_url`, `brand_color`, `support_email`, `footer`,
    `frontend_url`, `project_name`, `language`, `year`.
  - Usuario: `user_name` (`full_name` o la parte local del email), `user_email`.
  - Reset: `action_url` (enlace completo), `expires_in` ya formateado según el idioma ("30
    minutos" / "30 minutes"), `request_ip` y `request_time` (opcionales, "si no fuiste tú...").
  - Verify: `action_url`, `expires_in`.
  - Aviso "tu contraseña ha cambiado" (SHOULD): `changed_at`, `support_email`.
- **Plantillas de serie**: `verify_email`, `password_reset`, `password_changed` (aviso de
  seguridad tras el reset o el cambio; SHOULD) y `welcome` (COULD, apagado por defecto).
- **Idiomas**: es y en de serie. Idioma del usuario → `MAIL_DEFAULT_LANGUAGE` → en. Guardar
  `User.locale` al registrarse (campo opcional `locale` en el registro, o `Accept-Language`) es
  SHOULD. Sin él, todos los correos van en `MAIL_DEFAULT_LANGUAGE`, que para la mayoría de mis
  clientes (un solo país) es suficiente. Añadir un idioma = crear la carpeta `mail_templates/fr/`
  y ponerlo en `MAIL_LANGUAGES`, sin tocar código.
- **Asuntos** en fichero propio (`*.subject.txt`) para poder traducirlos sin tocar el HTML.
- **Nada del freelancer**: ni "Powered by", ni mi email, ni enlaces a mi web. Como mucho un
  `MAIL_FOOTER` vacío por defecto.

### 3.4 Envío y robustez (lo que el cliente nota)
- El envío va **por la cola del worker** (reintentos con espera creciente) cuando hay worker.
  La petición HTTP responde 202 al instante, y un proveedor lento no hace que forgot tarde 10 s
  (eso además revelaría si la cuenta existe).
- El token/enlace lo genera la API. **El worker no necesita `SECRET_KEY`** (hoy no la recibe
  en compose): recibe el enlace ya construido en el payload (o solo el id del token), sin
  secretos en claro que se queden en la tabla `jobs` más de lo necesario. A validar con
  seguridad.
- `MAIL_SEND_MODE=queue|inline` (por defecto `queue` si se detecta worker; en development,
  `inline` para no depender del worker). Documentar que en producción hace falta el servicio
  `worker` (compose ya lo levanta).
- Un fallo definitivo de envío queda en el log con un `code` legible (`smtp_auth_failed`,
  `smtp_timeout`) y en `GET /jobs` solo para el admin. Nunca se filtra al usuario final.

### 3.5 Integración con `apigen`
- `apigen check`: filas de correo, frontend y verificación (ver §3.6).
- `apigen mail test <email> [--template ...] [--lang ...]` (MUST).
- `apigen mail preview [plantilla] [--lang]` (SHOULD).
- `apigen mail eject` (SHOULD).
- `apigen init-env --production`: añade `MAIL_*`, `SMTP_*` y `FRONTEND_URL` a la lista de
  "rellena" (MUST).
- `make new-api ... LANG=es` → `MAIL_DEFAULT_LANGUAGE=es` en el `.env` generado (SHOULD, cero
  esfuerzo y queda profesional).
- `apigen docs`: sección de cuentas y variables de correo en el README del cliente (MUST).

### 3.6 Avisos de `apigen check` que espero
- `MAIL_FROM` en `example.com` con producción → error.
- `FRONTEND_URL` en `localhost` o `http://` con producción → error (o aviso si es un esquema de
  app).
- `FRONTEND_URL` cuyo origen no está en `CORS_ORIGINS` → aviso ("tu frontend no podrá llamar a
  la API").
- `EMAIL_VERIFICATION=required` con `ALLOW_REGISTRATION=false` → aviso informativo.
- `SMTP_SECURITY=none` con un host que no es local → aviso.
- Plantillas override con errores de sintaxis o variables inexistentes → error.
- Override que existe para un idioma y no para otro de `MAIL_LANGUAGES` → aviso ("en `en` se
  usará la plantilla de serie").

---

## 4. Fricción (lo que me molestaría)

| ID | Fricción | Prioridad | Sugerencia |
|---|---|---|---|
| F-01 | Correo que "no llega" en local sin saber por qué (worker parado, backend mal escrito) | Alta | console/inline por defecto en development; log explícito "correo encolado / enviado / fallido" |
| F-02 | Errores SMTP crípticos (`SMTPAuthenticationError (535, b'5.7.8 ...')`) | Alta | `apigen mail test` con diagnóstico traducido |
| F-03 | El escáner de `new_api.py` bloquea el commit porque metí el email de soporte del cliente en una plantilla | Alta | marca y contacto por `.env`, las plantillas solo con variables; o que el escáner permita emails del dominio de `MAIL_FROM` si el freelancer lo confirma |
| F-04 | Tener que copiar el HTML entero para cambiar una frase o el asunto | Media | overrides fichero a fichero (asunto, texto y HTML por separado) |
| F-05 | Que activar la verificación deje fuera a los usuarios existentes | Alta | la migración los marca como verificados |
| F-06 | Que la API arranque en producción con `console` y los correos se pierdan en el log | Alta | error al arrancar en producción |
| F-07 | Que el frontend tenga que distinguir 5 códigos de token inválido | Media | un solo `invalid_or_expired_token` |
| F-08 | Que "verificar dos veces" dé error | Media | idempotente: éxito |
| F-09 | Rate limit de forgot/resend demasiado estricto en desarrollo (5/hour me bloquea probando) | Media | como `RATE_LIMIT_REGISTER`: vacío = más permisivo fuera de producción |
| F-10 | Depender de un SDK por proveedor (más dependencias, más CVE, más mantenimiento) | Baja | SMTP primero; HTTP solo con httpx |
| F-11 | Tener que escribir la documentación del flujo a mano para cada cliente | Alta | `apigen docs` la genera según la configuración (modo de verificación, rutas) |
| F-12 | Postman sin forma de obtener el token | Media | nota en la colección y lectura del `.eml` en modo file (COULD) |

---

## 5. Valor percibido (lo que hace que un cliente lo compre)

1. **"Recuperación de contraseña y verificación de email incluidas, con tu marca y tu
   dominio"**: es una línea de la ficha de Fiverr/Gumroad que el comprador entiende y sabe que
   le costaría días. Hoy es lo primero que me preguntan después de "¿tiene login?".
2. **Sin dependencia de mí ni de un SaaS concreto**: "funciona con cualquier proveedor SMTP;
   cambia de proveedor editando el .env". Para el cliente, eso le quita miedo a comprar.
3. **Documentación para su frontend**: el README trae el flujo con ejemplos (`fetch`/curl) de
   las dos páginas que tiene que construir. Su desarrollador frontend lo integra sin
   preguntarme, y eso me ahorra horas de soporte en cada venta.
4. **Correos bonitos en su idioma desde el minuto uno** (es/en) y vista previa HTML para
   enseñársela antes de entregar.
5. **Seguro por defecto y explicado** (tokens de un solo uso, caducidad, no revela si el email
   existe, cierra sesiones tras el reset): argumento de venta frente a plantillas baratas.
6. Upsells posibles: plantillas a medida, adaptador HTTP de su proveedor, página de
   verificación servida por la API para quien no tiene web.

---

## 6. Priorización

### MUST
1. Endpoints `password/forgot` (202 neutro), `password/reset` (un solo uso, revoca sesiones,
   `password_policy` como hoy), `email/verify` (POST, idempotente), `email/resend-verification`
   (autenticado y anónimo, 202 neutro). Enlaces al **frontend del cliente**
   (`FRONTEND_URL` + `MAIL_RESET_PATH`/`MAIL_VERIFY_PATH`).
2. `EMAIL_VERIFICATION=off|optional|required` (por defecto `off`); `403 email_not_verified` en
   login con `required`; `email_verified` en `UserRead`/`/users/me`.
3. Migración: **usuarios existentes verificados**; los creados por un admin o `createsuperuser`
   nacen verificados.
4. Backends `console` (por defecto en development), `file`, `smtp` genérico (starttls/ssl/none,
   timeout) y `none`, más uno en memoria para tests. Todo por `.env`, **nada del freelancer**
   por defecto.
5. Marca e idioma por `.env` (`MAIL_FROM`, `MAIL_FROM_NAME`, `MAIL_BRAND_*`,
   `MAIL_SUPPORT_EMAIL`, `MAIL_FOOTER`, `MAIL_DEFAULT_LANGUAGE`). Plantillas de serie
   `verify_email` y `password_reset` en **es/en**, texto y HTML, asunto aparte.
6. Overrides de plantillas en una carpeta del proyecto que apigen nunca sobrescribe; Jinja2 con
   autoescape y modo estricto; errores detectados en `check`/tests.
7. Envío por la cola del worker con reintentos (`inline` en development); la API genera el
   enlace y el worker no necesita `SECRET_KEY`.
8. En producción: error al arrancar con `console`/`file`/`none` si hay reset o verificación
   activos, con `MAIL_FROM` de ejemplo o con `FRONTEND_URL` localhost/http.
9. `apigen mail test <email>` con errores de proveedor traducidos; `apigen check` e
   `init-env --production` con el bloque de correo.
10. `apigen docs` genera la sección "Cuentas: verificación y recuperación" (endpoints, flujo,
    formato del enlace, códigos de error, variables, SPF/DKIM) y README §6/§7 se actualizan.
11. Postman: carpeta Account con las 4 peticiones y las variables `resetToken`/`verifyToken`,
    verificada con newman.
12. Códigos de error nuevos y estables: `invalid_or_expired_token`, `email_not_verified`,
    `password_reset_disabled` y 429 con `Retry-After` en forgot/resend.

### SHOULD
- `POST /auth/password/reset/validate` para que la página del frontend avise antes de que el
  token ha caducado.
- El reset desbloquea la cuenta y marca el email como verificado.
- Correo `password_changed` (aviso de seguridad).
- `apigen mail preview` y `apigen mail eject`.
- `User.locale` (campo en el registro o `Accept-Language`) y `MAIL_LANGUAGES`.
- Endpoint o campo de capacidades (`email_verification`, `password_reset`) para el frontend.
- Admin: `PATCH email_verified`, `POST /users/{id}/send-password-reset`,
  `send_verification` en el alta.
- Permiso `verified` en el YAML de recursos.
- Cambio de email → deja el email sin verificar (mínimo) o flujo de confirmación.
- `SMTP_PASSWORD_FILE`; `MAIL_DEFAULT_LANGUAGE` tomado de `make new-api LANG=`.
- Rate limits de forgot/resend más permisivos fuera de producción.
- Generar el texto plano a partir del HTML si falta.

### COULD
- Adaptadores HTTP (Resend/Postmark/Brevo/SES API) con httpx y una interfaz común, y
  `MAIL_BACKEND=webhook` firmado.
- Página de verificación servida por la API (`MAIL_VERIFY_MODE=api_page`) para clientes sin
  web; guía de deep links para móvil.
- Servicio `mailpit` opcional en docker compose.
- Correo `welcome`.
- Postman/newman leyendo el token del `.eml` en modo file.
- `apigen users mark-unverified` para forzar la verificación de usuarios antiguos.

---

## 7. Preguntas abiertas para seguridad y desarrollo

1. ¿El token del enlace es aleatorio (guardado como hash en BD, revocable, de un solo uso) o un
   JWT firmado? Desde el punto de vista del usuario prefiero el primero: permite "un solo uso",
   invalidar al pedir otro y no depende de `SECRET_KEY` en el worker.
2. ¿Guardamos el enlace completo en `jobs.payload` o solo el id y la API regenera el correo?
   (retención de `jobs`: `JOBS_RETENTION_DAYS=7`).
3. ¿El reset desbloquea la cuenta (`locked_until`)? Lo pido como usuario, pero es una decisión
   de seguridad.
4. `register` hoy revela `email_taken` (riesgo aceptado). Con la verificación, ¿mantenemos el
   409 o lo cambiamos? Si cambia, el frontend lo tiene que saber (es un cambio incompatible y
   debe ir en el README).
5. Validar `FRONTEND_URL` contra una lista (esquemas permitidos) para que nadie pueda inyectar
   un dominio en el enlace, por ejemplo vía cabecera `Host`: el enlace **nunca** se construye a
   partir de la petición.
