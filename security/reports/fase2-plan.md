# Fase 2: plan consolidado (recuperación de contraseña, verificación de email y correo por cliente)

**Fecha:** 2026-09-26

**Entradas** (detalle en cada documento):

| Documento | Autor | Contenido |
|---|---|---|
| `fase2-plan-seguridad.md` | Experto en ciberseguridad | TM-01..25 amenazas · REQ-xxx requisitos · ST-01..45 casos de prueba |
| `fase2-plan-usuario.md` | Usuario (freelancer + cliente) | Historias, MUST/SHOULD/COULD, fricciones F-01..12, variables propuestas |
| `fase2-plan-desarrollador.md` | Desarrollador | Diseño técnico, endpoints, subsistema de correo, 11 pasos, ~36 h |

**Principio:** el software se vende. Nada está ligado al correo ni a los datos del freelancer. Cada cliente configura su proveedor, remitente, marca, enlaces de su frontend e idioma con **variables de entorno** y **plantillas propias** que el generador nunca sobrescribe. Todo queda **desactivado por defecto**, así que las APIs ya entregadas se comportan igual.

---

## 1. Arquitectura acordada (los tres coinciden)

- **La API solo encola** trabajos de sistema (`owner_id=None`). El **worker** hace el resto: buscar al usuario, generar el token, renderizar la plantilla y enviar el correo.
  - Respuesta y tiempo idénticos exista o no la cuenta.
  - Las credenciales SMTP solo las recibe el worker.
  - El token en claro nunca se guarda: ni en BD, ni en `jobs.payload`/`result`/`error`, ni en logs, ni en respuestas.
- **Tokens:**
  - Opacos, `secrets.token_urlsafe`, de 256 bits como mínimo, con prefijo por tipo (`pr_` reset, `ev_` verificación, `ec_` cambio de email).
  - Tabla `account_tokens` con `sha256`, `purpose` (siempre filtrado), `user_id`, email de destino, `expires_at`, `used_at` y `created_at`.
  - Consumo atómico (`UPDATE … WHERE used_at IS NULL … RETURNING`). Al usar uno se invalidan los demás del mismo propósito.
  - Un token deja de valer si la contraseña cambió después de emitirlo o si el email ya no coincide.
- **Enlaces:** solo desde `FRONTEND_URL` + `EMAIL_LINK_RESET` / `EMAIL_LINK_VERIFY` (rutas con `{token}` exactamente una vez; por defecto en el fragmento `#token=`). Nunca desde `Host`, `X-Forwarded-Host` ni `Origin`.
- **Consumo solo por POST** desde el frontend del cliente: los escáneres de correo abren los enlaces con GET. Las respuestas llevan `Cache-Control: no-store`.
- **Subsistema `app/email/`:**
  - Interfaz `EmailBackend.send()` que distingue errores transitorios (se reintentan) de permanentes (no).
  - Backends: `console` (desarrollo), `file` (`.eml`), `memory` (tests), `smtp` (`smtplib` en un hilo, STARTTLS/SSL con certificado verificado), `disabled` y `custom` (clase propia del proyecto).
- **Plantillas:**
  - Jinja en sandbox, con autoescape HTML y `StrictUndefined`.
  - Texto + HTML + asunto, en **es/en**, con la marca del cliente tomada del `.env`.
  - Se pueden sobrescribir en `email_templates/` del proyecto, que apigen no toca.
  - Idioma: `Accept-Language` validado contra una lista blanca, con `MAIL_DEFAULT_LANGUAGE` como respaldo.
- **Cola:**
  - Idempotencia con `Message-ID` estable y `sent_at`.
  - Timeouts encadenados: SMTP < tarea < arrendamiento.
  - Opción `scrub_payload` para no dejar emails en `jobs`.
  - Revalidación antes de enviar: usuario activo, email sin cambios y trabajo más reciente que la vida del token.
- **Cero dependencias nuevas.**

## 2. Endpoints

| Endpoint | Respuesta | Notas |
|---|---|---|
| `POST /auth/password/forgot` `{email}` | **202** genérico siempre | Rate limit por IP; el cupo por cuenta lo aplica el worker |
| `POST /auth/password/reset` `{token, new_password}` | **204** | 422 con contraseña débil **sin consumir el token**. Además: revoca todas las sesiones, fija `password_changed_at` y envía un aviso de "contraseña cambiada" |
| `POST /auth/email/verify` `{token}` | **204** | Sirve para el alta y para el cambio de email; verificar dos veces cuenta como éxito; no inicia sesión |
| `POST /auth/email/verify/resend` `{email}` o con sesión | **202** genérico | Mismo rate limit y cupo que `forgot` |
| `POST /users/me/email` `{new_email, current_password}` | **202** | Envía el enlace a la dirección nueva y un aviso a la antigua; también 202 si la nueva está ocupada; revoca sesiones al confirmar |
| `GET /users/me` | + `email_verified` | — |

**`EMAIL_VERIFICATION=off|optional|required`** (por defecto `off`):
- Con `required`, el login responde **403 `email_not_verified` solo después de comprobar que la contraseña es correcta**, y el refresh también rechaza a los no verificados.
- Con `optional`, los hooks pueden exigirlo con la dependencia `VerifiedUser`.

**`PASSWORD_RESET=on|off`** (por defecto `off`).

**Migración:** `users.email_verified_at` se rellena para todos los usuarios existentes. `createsuperuser` y las altas hechas por un admin nacen verificados.

## 3. Decisiones sobre los puntos en desacuerdo

| # | Punto | Decisión | Motivo |
|---|---|---|---|
| D1 | Registro y enumeración (409 `email_taken`) | Con `EMAIL_VERIFICATION` distinto de `off`: **202 idéntico siempre, con Argon2 en los dos caminos**. Si el email ya existe, no se toca la cuenta y se envía el correo "ya tienes cuenta" (con el mismo cupo por cuenta). Con `off` se mantiene el 201/409 actual (riesgo aceptado y documentado) | Solo cuando hay correo se puede avisar al dueño real; con `off` un 202 sin aviso rompería la UX sin ganar seguridad real. Cierra por fin SEC-05 |
| D2 | ¿El reset desbloquea la cuenta? | **Sí, en silencio**: el reset pone a cero `failed_login_attempts`/`locked_until`, y la respuesta es 204 igual, estuviera bloqueada o no | Completar el reset demuestra que se controla el email; quien lo controla ya podía cambiar la contraseña. No se revela el estado de bloqueo |
| D3 | Límites por cuenta | 60 s entre correos, **3/hora y 10/día** por cuenta (configurables) + rate limit por IP | Se adopta la cifra más prudente (seguridad) |
| D4 | Caducidad de los tokens | Reset **30 min** · verificación **48 h** · cambio de email **60 min** (configurables) | Requisito de seguridad |
| D5 | Proveedores HTTP (Resend, Postmark…) | **Fuera de esta fase** (COULD / extra de pago). SMTP genérico + backend `custom` | Todos ofrecen SMTP; cero dependencias |
| D6 | Enlace "no fui yo, revertir" en el cambio de email | **Fuera** (COULD). El aviso a la dirección antigua incluye el contacto de soporte del cliente | Complejidad y superficie extra |
| D7 | Mailpit | Fichero aparte **`compose.mail.yml`** + `make mail` | El compose de producción queda limpio |
| D8 | Nivel `verified` en el YAML | **Fuera** (COULD). En esta fase, la dependencia `VerifiedUser` para hooks y endpoints propios | Con `required` todos los usuarios autenticados ya están verificados |
| D9 | Código OTP de 6 dígitos para móvil | **Fuera** (COULD). Las apps usan deep links con el mismo token | Seguridad desaconseja códigos cortos por defecto |
| D10 | Dónde se genera el token | **En el worker** | Para que el token no quede en `jobs.payload` (consenso de seguridad y desarrollo) |

## 4. Configuración por cliente (resumen de variables)

| Grupo | Variables |
|---|---|
| Funciones | `EMAIL_VERIFICATION` · `PASSWORD_RESET` |
| Enlaces | `FRONTEND_URL` · `EMAIL_LINK_RESET` · `EMAIL_LINK_VERIFY` |
| Remitente y marca | `EMAIL_FROM` · `EMAIL_FROM_NAME` · `MAIL_BRAND_NAME` · `MAIL_BRAND_URL` · `MAIL_BRAND_LOGO_URL` · `MAIL_BRAND_COLOR` · `MAIL_SUPPORT_EMAIL` · `MAIL_FOOTER` · `MAIL_DEFAULT_LANGUAGE` |
| Backend | `EMAIL_BACKEND=console\|file\|memory\|smtp\|disabled\|custom` · `SMTP_HOST` · `SMTP_PORT` · `SMTP_USER` · `SMTP_PASSWORD` (`SecretStr`) · `SMTP_SECURITY=starttls\|ssl\|none` · `SMTP_TIMEOUT` · `EMAIL_BACKEND_CLASS` (para `custom`) |
| Límites y vida de tokens | `RATE_LIMIT_EMAIL_REQUEST` · `EMAIL_PER_ACCOUNT_*` · `TOKEN_TTL_*` |

**En producción la API y el worker no arrancan si:**
- falta el backend o es `console`, `file` o `memory` con alguna función activa;
- `disabled` se combina con `required`;
- `EMAIL_FROM` falta o es de `example.*`;
- `FRONTEND_URL` no es https o es localhost;
- las rutas de enlace no llevan exactamente un `{token}`;
- se usa SMTP sin TLS fuera de localhost.

Los valores reales van solo al `.env`, que no se versiona. El escáner de secretos de `new_api.py` sigue como red de seguridad.

## 5. Herramientas y entrega

- **CLI:**
  - `apigen email test <dirección>`: envía una prueba con mensajes claros si el proveedor falla.
  - `apigen email preview <plantilla> [--lang]` (SHOULD).
  - `apigen check` e `init-env --production` con el bloque de correo.
  - `apigen db prune` limpia los tokens caducados.
- **`make new-api`:** flags `--email-verification`, `--password-reset` y `--frontend-url`; los valores reales van solo al `.env`.
- **`apigen docs`:** secciones de flujos de cuenta, qué debe implementar el frontend, formato del enlace, errores nuevos (`invalid_or_expired_token`, `email_not_verified`, `password_reset_disabled`) y configuración SMTP/SPF/DKIM/DMARC.
- **Postman:** carpeta **Account** con `resetToken`/`verifyToken`, verificada con newman.
- **Tests:** unos 40, con el backend `memory` y `process_pending()`, SMTP simulado, y E2E opcional contra Mailpit.
- **Seguridad y logs:**
  - Nunca se registran tokens, enlaces, cuerpos, credenciales, respuestas crudas del proveedor ni emails completos.
  - `smtplib` con `debuglevel=0`.
  - Eventos `audit()` solo con IDs.

## 6. Orden de implementación

1. Subsistema `app/email/` (backends, plantillas, configuración y validación) + tests.
2. Modelo `account_tokens` + `users.email_verified_at` + migración.
3. Tareas del worker (`auth.*`, `email.send`) con cupos por cuenta, idempotencia y `scrub_payload`.
4. Recuperación de contraseña.
5. Verificación de email, modos y registro uniforme (D1).
6. Cambio de email.
7. CLI (`email test`/`preview`, `check`, `init-env`, `prune`).
8. `apigen docs`, Postman y `make new-api`.
9. `compose.mail.yml` + E2E con Mailpit + Docker.
10. Documentación (README, guía) y `graphify update`.

## 7. Validación final

- **Experto en ciberseguridad:** los casos **ST-01..45** de `fase2-plan-seguridad.md`.
- **Usuario:** los criterios de aceptación de `fase2-plan-usuario.md` (freelancer y cliente) y el README/Postman para el cliente.
