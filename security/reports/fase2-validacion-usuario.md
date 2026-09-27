# Fase 2 · Validación del usuario (freelancer + cliente)

- **Fecha:** 2026-09-26
- **Autor:** agente `user`, con dos sombreros: freelancer que entrega la API y cliente/frontend que la recibe.
- **Referencias:**
  - `fase2-plan-usuario.md` (mis historias y MUST);
  - `fase2-plan.md` (las decisiones D1–D10 prevalecen);
  - `fase2-desarrollador.md`.
- **Entorno:**
  - Copia del working tree en el scratchpad (rsync sin `.venv`, `.env` ni `*.db`), con commit en esa copia. El repo de la plantilla no se ha tocado.
  - Proyecto `tienda-api` ("Tienda Luna") creado con `new_api.py`.
  - API en `127.0.0.1:8902` con backends `file` y `console`, `EMAIL_DELIVERY=inline` por defecto en development, y `apigen worker --once` para el modo cola.
  - newman 6.
  - Al terminar se paró todo (`pkill -f "port 8902"`, `pkill -f app.tasks.worker`; el puerto quedó libre).

---

## 1. Resumen

- Como freelancer puedo entregar esto hoy:
  - `new_api.py` con las flags de correo tarda unos 25 s;
  - con 6 o 7 variables de `.env` el cliente queda configurado;
  - `email test`, `preview`, `eject` y `check` funcionan y se entienden.
- Como cliente, los flujos son claros:
  - 202 uniformes, 403 `email_not_verified` y 400 único para tokens malos;
  - verificar dos veces cuenta como éxito;
  - las sesiones se cierran tras el reset y tras el cambio de email;
  - el README explica qué páginas debe construir el frontend.
- Hay cuatro problemas que sí afectan a una venta:
  1. **UX-67:** el zip entregado no lleva la configuración de correo elegida.
  2. **UX-68:** activar `required` más tarde deja fuera a quien se registró con `off`.
  3. **UX-69:** la colección de Postman falla con variables de entorno.
  4. **UX-70:** el cupo por cuenta compartido descarta en silencio el correo de recuperación.

## 2. MUST → cumplimiento

| # | MUST (plan usuario §6, ajustado por D1–D10) | Estado | Evidencia |
|---|---|---|---|
| 1 | Endpoints forgot / reset / verify / resend con enlaces al frontend | **Cumple** | `forgot` → 202 idéntico con email existente e inexistente. `reset/validate` → 204. `reset` → 204; reutilizar el token → 400. Enlace `http://localhost:5173/reset-password#token=pr_…` construido desde `FRONTEND_URL`. `verify/resend` con sesión (sin cuerpo) y anónimo (`{email}`) → 202; sin cuerpo ni sesión → 422 claro ("Field required when not authenticated") |
| 2 | `EMAIL_VERIFICATION=off\|optional\|required` (por defecto `off`), 403 en login, `email_verified` | **Cumple** | Con `required`: contraseña correcta sin verificar → 403 `email_not_verified`; contraseña mala → 401 `invalid_credentials` (no filtra). Con `optional`: login OK y `/users/me` con `"email_verified":false`. `GET /auth/features` refleja el modo |
| 3 | Usuarios existentes y altas de admin verificados | **Parcial** | `POST /users` (admin) → `email_verified:true`; `createsuperuser` → verificado. La migración rellena a los usuarios existentes (según el informe del desarrollador; no lo he reproducido con una BD previa). **Pero** los usuarios que se registran mientras el modo es `off` nacen `email_verified:false` y, al pasar a `required`, reciben 403 (probado con carol@…). Ver UX-68 |
| 4 | Backends `console` (defecto en dev), `file`, `smtp` y "sin correo", más memoria para tests | **Cumple** | `console`: el correo sale en stdout o en el log. `file`: `.eml` + `.html` en `var/mail/`. `smtp`: probado con errores reales. Con `off` los endpoints responden 403 `password_reset_disabled` / `email_verification_disabled` |
| 5 | Marca e idioma por `.env`; plantillas es/en con texto, HTML y asunto aparte | **Cumple** | `From: Tienda Luna <…>`, color y nombre en el HTML, `Auto-Submitted`. `Accept-Language: en` → "Reset your Tienda Luna password"; sin cabecera → `MAIL_DEFAULT_LANGUAGE=es` (fijado por `--lang es`) |
| 6 | Plantillas propias que apigen no toca; autoescape, modo estricto, errores detectados | **Cumple** | `apigen email eject password_reset --lang es` → 3 ficheros. Cambié el asunto (con emoji) y el texto, y el correo real salió con ellos. Una variable inexistente (`user_nombre`) → `apigen check` sale con código 1: `UndefinedError: 'user_nombre' is undefined`. Tras `apigen generate resources --force` y `apigen docs`, `shasum -c` → OK (nada pisado). Repetir `eject` no sobrescribe (`= … (ya existe)`) |
| 7 | Envío por cola con reintentos (`inline` en dev); el worker sin `SECRET_KEY` | **Cumple** | Sin worker en dev los correos salen igual (`inline`). Con `EMAIL_DELIVERY=queue` y sin worker no sale nada; `apigen worker --once` lo envía (`processed 1 jobs`). D10: el token lo genera el worker |
| 8 | Producción no arranca con `console`/`file`/`none`, remitente de ejemplo o `FRONTEND_URL` http/localhost | **Cumple** (matiz UX-73) | `apigen check` en producción lista: "EMAIL_BACKEND=console no envía correos reales", "EMAIL_FROM … usa un dominio de ejemplo", "FRONTEND_URL … debe ser https y no localhost", "EMAIL_LINK_RESET: debe contener {token} exactamente una vez" |
| 9 | `apigen email test` con errores traducidos; `check` e `init-env --production` con bloque de correo | **Cumple** (matices UX-72, UX-74) | "autenticación SMTP rechazada: revisa SMTP_USER y SMTP_PASSWORD (algunos proveedores usan 'apikey')", "el puerto 465 requiere SMTP_SECURITY=ssl y el 587, starttls", "no se pudo conectar a …:587 … prueba el 2525". `init-env --production` lista el bloque de correo y sugiere `apigen email test` |
| 10 | `apigen docs`: sección de cuentas y README actualizado | **Cumple** | README es/en con "Correos de cuenta": enlace, flujos, página del frontend con snippet JS, `features`, límites, SMTP/SPF/DKIM/DMARC y puerto 2525. Se adapta al modo: `required` añade el párrafo del 403; `off` quita la sección y el registro vuelve a 201 |
| 11 | Postman: carpeta Account con variables, verificada con newman | **Parcial** | Carpeta Account con 7 peticiones y variables `resetToken`, `verifyToken`, `newPassword` y `newEmail`. Resultados con newman: tal cual → 9/10 (el reset sin token da 422 porque `newPassword` viene vacío); con tokens pasados por `--env-var` → las 3 peticiones dan 204 pero las 3 aserciones **fallan**. Ver UX-69 |
| 12 | Códigos estables y 429 con `Retry-After` | **Cumple** | `invalid_or_expired_token`, `email_not_verified`, `password_reset_disabled`, `email_verification_disabled`, `same_email`, `wrong_password`. 429 `rate_limited` con `retry-after: 5` y una pista para ajustar `RATE_LIMIT_*` |

**Historias no MUST que también comprobé:**
- **Cambio de email** (SHOULD en mi plan, MUST en el plan consolidado):
  - `PATCH /users/me` con `email` → 422;
  - contraseña mala → `wrong_password`;
  - el mismo email → `same_email`;
  - dirección ocupada → 202 idéntico;
  - correcto → confirmación a la nueva y aviso a la antigua;
  - `verify` con `ec_` → 204, la sesión antigua da 401, el login con el email nuevo funciona y llega el aviso final. **Cumple.**
- **Reset y cuentas bloqueadas:** el reset desbloquea y verifica (D2), según el README y el informe del desarrollador. El aviso "contraseña cambiada" llegó.
- **`validate` y `features`** (SHOULD): hechos y útiles.

## 3. Puntos nuevos

### UX-67 · Alta · El zip entregado no lleva la configuración de correo elegida
- **Lo que hice:** `new_api.py … --lang es --email-verification optional --password-reset --frontend-url …`, luego `apigen docs` y revisar qué incluye `make deliver`.
- **Lo que pasó:**
  - Las flags solo escriben en `.env`, que no se versiona.
  - `.env.example`, lo que el cliente recibe y copia según el README (`cp .env.example .env`), sigue con `EMAIL_VERIFICATION=off`, `PASSWORD_RESET=off`, `MAIL_DEFAULT_LANGUAGE=en` y `MAIL_BRAND_NAME=` vacío.
  - El README del cliente, generado desde mi `.env`, dice "Esta API: verificación **optional** · recuperación **on**". El cliente despliega siguiendo el README y obtiene todo desactivado y en inglés. Su frontend recibe 403 `password_reset_disabled` y me escribe.
  - Lo mismo pasa con `apigen init-env --production --force`: regenera desde `.env.example` y pierde los valores (comprobado: `off/off/en`, marca vacía).
- **Lo que esperaba:** que las decisiones **no secretas** del proyecto (modos, idioma, marca, rutas de enlace) viajen con el código.
- **Sugerencia:** que `new_api.py` escriba también en `.env.example` los valores no secretos (`EMAIL_VERIFICATION`, `PASSWORD_RESET`, `MAIL_DEFAULT_LANGUAGE`, `MAIL_BRAND_NAME`). `FRONTEND_URL` y `EMAIL_FROM` pueden quedarse como marcador, porque producción los exige. Como mínimo:
  - `apigen docs` debería avisar si `.env` y `.env.example` difieren en esas variables;
  - el bloque "Edita .env" del README Docker debería listar las líneas de correo.

### UX-68 · Alta · Pasar de `off` a `required` deja fuera a los registrados en `off`
- **Lo que hice:** registrar a carol con `EMAIL_VERIFICATION=off` (201, `email_verified:false`), reiniciar con `required` e intentar el login.
- **Lo que pasó:** 403 `email_not_verified`. La migración solo protege a quienes existían al migrar. Es el caso típico: entrego con `off` (el valor por defecto), meses después el cliente activa `required` y todos los registrados en ese tiempo quedan fuera hasta que verifiquen.
  - El admin no tiene forma de marcarlos: `PATCH /users/{id}` con `email_verified_at` → 422 `extra_forbidden`, por REQ-F25.
  - Hay salida (`resend` + `verify`), pero es una sorpresa y nadie avisa.
- **Sugerencia**, en orden de preferencia:
  1. `apigen check` o el arranque avisan: "N usuarios sin verificar; con `required` no podrán entrar hasta verificar su email".
  2. Un comando de operador, `apigen users mark-verified --before <fecha>|--all`, que es CLI y no API, así que no choca con F25.
  3. Documentarlo en el README (§ verificación) y en `.env.example` junto a `EMAIL_VERIFICATION`.

### UX-69 · Media · Postman: las aserciones solo leen variables de colección y `newPassword` viene vacío
- **Lo que pasó:**
  - Tal cual, `Reset password` sin token responde **422** (la contraseña vacía se valida antes que el token) y el test espera 400 → 1 fallo.
  - Pasando `resetToken`, `verifyToken` y `newPassword` con `--env-var` (lo mismo que hace quien usa un *Environment* de Postman, muy habitual por cliente), las peticiones dan 204 pero los tests usan `pm.collectionVariables.get(...)`, creen que no hay token y fallan las 3 aserciones.
  - Tras el reset, el script guarda la contraseña nueva en la colección, pero si `password` viene del entorno, el siguiente Login sigue usando la vieja.
- **Sugerencia:**
  - usar `pm.variables.get()` (resuelve todos los ámbitos);
  - dar un valor por defecto a `newPassword` (o aceptar 400 o 422 en la rama sin token);
  - en la descripción de Account, decir qué hacer con un *Environment*.

### UX-70 · Media · El cupo por cuenta compartido descarta en silencio el correo de recuperación
- **Lo que hice:** registro, registro duplicado ("ya tienes cuenta") y un reenvío de verificación. Después, "olvidé mi contraseña".
- **Lo que pasó:**
  - El correo de reset **no se envió**: 202 al cliente y `email.suppressed reason=quota` en el log de auditoría (INFO).
  - Es D3 (3 por hora compartidos) y ST-25 lo exige, pero para el usuario final se traduce en "le di a olvidé y no me llega nada durante una hora", y el soporte del cliente no tiene pistas.
  - En desarrollo me pasó a los 5 minutos de probar: el informe del desarrollador solo menciona bajar `EMAIL_PER_ACCOUNT_COOLDOWN_SECONDS`, pero lo que me bloqueó fue `EMAIL_PER_ACCOUNT_PER_HOUR`.
- **Sugerencia:**
  1. En development, cupos por cuenta más permisivos por defecto (como ya se hace con `RATE_LIMIT_REGISTER`).
  2. Cuando se suprime un correo, en dev el log dice en claro "correo NO enviado: cupo por cuenta (3/h); sube EMAIL_PER_ACCOUNT_PER_HOUR para pruebas".
  3. El README del cliente ya dice "como mucho 3 correos por hora a la misma cuenta". Añadir una frase para su soporte: "si un usuario no recibe el correo, que espere una hora".

### UX-71 · Media · El `.eml` usa quoted-printable: copiar el token desde él falla
- **Lo que pasó:** en el `.eml` el enlace aparece como `#token=3Dev_X5bB…=` partido en dos líneas. Copiado o extraído con grep, da un token truncado y la API responde 400. Me pasó; al freelancer que siga la descripción de Postman ("copia el token del correo") le pasará. El `.html` de al lado sí trae el enlace limpio.
- **Sugerencia:** que el backend `file` escriba también un `.txt` decodificado (o registre en el log "enlace guardado en var/mail/xxx.txt"), y que la descripción de Postman y el README digan "abre el .html o el .txt, no el .eml".

### UX-72 · Baja · `apigen email test`: dos diagnósticos mejorables
- Puerto 465 con `SMTP_SECURITY=starttls` → "no se pudo conectar … (timeout o conexión rechazada)" tras esperar todo el timeout. Se puede detectar **antes** de conectar: "465 implica SMTP_SECURITY=ssl". La combinación inversa (587 + ssl) sí da el mensaje bueno.
- Un host que no resuelve (`smtp.noexiste.invalid`) da el mismo mensaje de "timeout". Mejor: "no se encuentra el servidor SMTP_HOST: revisa el nombre".
- `EMAIL_BACKEND=file` → "✓ Guardado en var/mail/". Mejor con el nombre del fichero.

### UX-73 · Baja · `apigen check` dice "válida" con SMTP sin TLS hacia un host remoto
- **Lo que pasó:** con `ENVIRONMENT=production`, `SMTP_HOST=smtp-relay.brevo.com` y `SMTP_SECURITY=none`, `apigen check` muestra "✓ Configuración válida". Solo con `PROCESS_ROLE=worker` aparece el error ("SMTP_SECURITY=none solo se admite hacia localhost").
- **Lo que esperaba:** `check` lo ejecuta el freelancer antes de entregar y no sabe que tiene que simular el rol worker. El worker no arrancará en producción y el fallo se descubre en el despliegue.
- **Sugerencia:** que `check` valide también las reglas del rol worker (en una sección "Worker") o que añada `--role worker|api|all`, con `all` por defecto.

### UX-74 · Baja · Falso aviso "(no está en CORS)" en desarrollo
`apigen check` en dev muestra `CORS: localhost:* (desarrollo)` y a la vez `Frontend (enlaces) http://localhost:5173 (no está en CORS)`. En desarrollo ese origen sí está permitido. Solo debería avisar si el origen realmente no pasaría el CORS efectivo.

### UX-75 · Baja · `apigen email preview` no usa mi `FRONTEND_URL`
La vista previa enlaza a `https://app.example.com/reset-password#token=pr_example`, mientras el pie usa mi `FRONTEND_URL` (`http://localhost:5173`). Justo quiero enseñarle al cliente el enlace real con su dominio y sus rutas (`EMAIL_LINK_*`). Sugerencia: construir el enlace de ejemplo con `FRONTEND_URL` y `EMAIL_LINK_*` (token ficticio).

### UX-76 · Baja · Un login rechazado por `email_not_verified` actualiza `last_login_at`
eva@… nunca ha entrado (solo recibió 403), pero el admin ve `last_login_at` con la hora del intento. Confunde al soporte ("dice que no puede entrar, pero entró hace 5 minutos"). Sugerencia: actualizarlo solo cuando se emiten tokens.

### UX-77 · Baja · Idioma inconsistente dentro de un mismo flujo
Pedí el reset con `Accept-Language: en` y recibí el enlace en inglés, pero el aviso "contraseña cambiada" (disparado por el `POST /reset`, sin cabecera) llegó en español (`MAIL_DEFAULT_LANGUAGE`). Es el SHOULD `User.locale` pendiente; con una columna `locale` guardada en la primera petición se arregla. Mientras tanto, el README podría pedir al frontend que envíe siempre `Accept-Language`.

### UX-78 · Baja · La página de verificación no distingue alta de cambio de email
El enlace de cambio de email usa la misma ruta (`/verify-email#token=ec_…`) y `verify` responde 204 sin cuerpo. Tras un cambio de email las sesiones se cierran, así que el frontend debería decir "email cambiado, vuelve a iniciar sesión", pero no sabe qué caso es salvo mirando el prefijo `ec_` (no documentado como contrato). Sugerencia: responder 200 `{"purpose":"verify"|"email_change","session_revoked":bool}` o documentar el prefijo como estable.

### UX-79 · Baja · `apigen docs` ignora las variables de entorno y solo lee `.env`
`EMAIL_VERIFICATION=required uv run apigen docs` siguió documentando `optional`; tuve que editar `.env`. Choca con "toda variable se puede sobrescribir con variables de entorno". Sugerencia: respetar el entorno o avisar de que `docs` lee `.env`.

### UX-80 · Baja · README del cliente: huecos menores
- La tabla de errores no incluye `wrong_password`, `same_email`, `email_change_disabled` ni el 409 al confirmar un email que otro ha ocupado mientras tanto.
- No hay una línea para apps móviles: `FRONTEND_URL` debe ser https, así que hacen falta *universal links / app links*.
- Por lo demás, el README es de lo mejor que he recibido: dice exactamente qué dos páginas hacer, con snippet, y explica por qué el token va en `#`.

## 4. Lo que me gustó

- `new_api.py` con las flags de correo: 25 s, tests en verde, escáner limpio, `.env` con marca e idioma.
- `.env.example` muy bien comentado ("Solo el worker necesita estas credenciales", "si bloquea 587/465…").
- `apigen email test` traduce de verdad los errores de SMTP (autenticación, TLS, puerto): me ahorra la parte más desesperante de una entrega.
- `eject` + overrides fichero a fichero + `check`, que atrapa variables inexistentes con código de salida 1. Es fácil de meter en CI.
- Plantillas HTML sobrias, con tablas, CSS en línea, versión en texto y el enlace "O copia este enlace". Se ven profesionales sin logo.
- Respuestas uniformes, verificar dos veces cuenta como éxito, `validate` antes del formulario, `GET /auth/features` para no fijar opciones en el frontend.
- El README se adapta al modo (201 o 202, párrafo de `required`, sección ausente con `off`).
- Mensajes de producción precisos y accionables.

## 5. Fricciones restantes (de mi plan, F-01..12)

| Fricción | Estado |
|---|---|
| F-01 El correo no llega en local | Resuelta (`inline` + `console`/`file`). Nueva variante: cupo por cuenta silencioso (UX-70) |
| F-02 Errores SMTP crípticos | Resuelta; quedan detalles (UX-72) |
| F-03 El escáner choca con las plantillas | Resuelta (marca y contacto en `.env`; escáner limpio) |
| F-04 Copiar todo para cambiar una frase | Resuelta (override por fichero; el asunto va aparte) |
| F-05 Usuarios existentes fuera | Parcial (UX-68: los registrados con `off`) |
| F-06 Producción con `console` | Resuelta |
| F-07 Muchos códigos de token | Resuelta (uno solo) |
| F-08 Verificar dos veces da error | Resuelta |
| F-09 Rate limit estricto en desarrollo | Resuelta por IP (30/min en dev); el cupo por cuenta sigue estricto (UX-70) |
| F-10 SDKs por proveedor | Resuelta (SMTP + `custom`) |
| F-11 Documentar a mano | Resuelta, salvo la desincronización `.env` / `.env.example` (UX-67) |
| F-12 Postman sin token | Parcial (UX-69, UX-71) |

## 6. Valoración para vender

**8,5 / 10.**

Esta fase convierte la plantilla en un producto con una línea de ficha que el comprador entiende: "recuperación de contraseña, verificación de email y cambio de email, con tu marca, tu dominio y cualquier proveedor SMTP". El README para el frontend y `email test` reducen el soporte postventa, que es donde pierdo dinero.

No le pongo un 9–10 por UX-67 (lo que entrego no arranca con lo que el README promete) y UX-68 (sorpresa al activar `required`): son exactamente el tipo de fallo que genera una reseña de 3 estrellas. Con UX-67, UX-68 y UX-69 arreglados, lo subiría a 9,5.
