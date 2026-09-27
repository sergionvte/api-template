"""Sección del README del cliente sobre los flujos de cuenta por correo (en/es).

Solo aparece si la API tiene activada la verificación de email o la recuperación de
contraseña. Los valores salen de `.env.example` y, para las claves de esta lista
(ninguna es secreta), del `.env` del proyecto: ahí deja `make new-api` la configuración
del cliente.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

ACCOUNT_KEYS = (
    "EMAIL_VERIFICATION",
    "PASSWORD_RESET",
    "EMAIL_LINK_RESET",
    "EMAIL_LINK_VERIFY",
    "TOKEN_TTL_RESET_MINUTES",
    "TOKEN_TTL_VERIFY_HOURS",
    "TOKEN_TTL_EMAIL_CHANGE_MINUTES",
    "RATE_LIMIT_EMAIL_REQUEST",
    "RATE_LIMIT_TOKEN_CONFIRM",
    "EMAIL_PER_ACCOUNT_PER_HOUR",
    "MAIL_LANGUAGES",
)
_TRUE = {"1", "true", "on", "yes"}


def _read_local(base: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    local = base / ".env"
    if local.exists():
        for line in local.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", line.strip())
            if m and m.group(1) in ACCOUNT_KEYS and m.group(2).strip():
                values[m.group(1)] = m.group(2).strip().strip("\"'")
    return values


def account_settings(base: Path, env: dict[str, str]) -> dict[str, str]:
    """`.env.example` + `.env` + variables de entorno (UX-79), solo para las claves de
    ACCOUNT_KEYS (ninguna es secreta)."""
    values = {k: env.get(k, "") for k in ACCOUNT_KEYS}
    values.update(_read_local(base))
    values.update({k: os.environ[k] for k in ACCOUNT_KEYS if os.environ.get(k)})
    return values


def mismatches(base: Path, env: dict[str, str]) -> list[str]:
    """Claves que el README toma de .env (o del entorno) y que difieren de `.env.example`,
    que es lo que recibe el cliente (UX-67): el entregable no haría lo que dice el README."""
    effective = account_settings(base, env)
    return [
        f"{k}={effective[k]} (en .env.example: {env.get(k) or 'vacío'})"
        for k in ("EMAIL_VERIFICATION", "PASSWORD_RESET")
        if effective.get(k) and effective[k] != (env.get(k) or "")
    ]


def modes(values: dict[str, str]) -> tuple[str, bool]:
    mode = values.get("EMAIL_VERIFICATION") or "off"
    if mode not in {"off", "optional", "required"}:
        mode = "off"
    return mode, (values.get("PASSWORD_RESET") or "off").lower() in _TRUE


T = {
    "en": {
        "feature": "Email verification and password reset by email, with your brand and "
        "your own email provider (any SMTP)",
        "title": "Account emails: email verification and password reset",
        "status": "This API: email verification **{mode}** · password reset **{reset}**. "
        "`GET {p}/auth/features` returns the same information so your front-end can show or "
        "hide these options without hard-coding them.\n",
        "links": "The emails link to **your front-end**, never to the API: "
        "`FRONTEND_URL` + `{reset_path}` and `FRONTEND_URL` + `{verify_path}` (for example "
        "`https://app.example.com{reset_example}`). The token goes in the URL fragment "
        "(`#`), which browsers never send to any server.\n",
        "reset_title": "Password reset",
        "reset_body": (
            '1. `POST {p}/auth/password/forgot` with `{{"email": "…"}}` → **always `202`** '
            "with the same body, whether or not the account exists. Show a neutral message "
            '("if the email is registered, you will receive a link").\n'
            "2. The user opens the link (valid {reset_ttl} minutes, single use).\n"
            "3. Your page reads the token, optionally checks it with "
            '`POST {p}/auth/password/reset/validate` (`{{"token": "…"}}` → `204`, or `400` '
            "if expired) and sends `POST {p}/auth/password/reset` with "
            '`{{"token": "…", "new_password": "…"}}` → `204`.\n'
            "4. Every session is closed (log in again), a locked account is unlocked and the "
            'user receives a "your password was changed" email.\n\n'
            "`400 invalid_or_expired_token` → offer to request a new link. "
            "`422 password_policy` → same format as `POST {p}/users/me/password`; the link is "
            "still valid.\n"
        ),
        "verify_title": "Email verification",
        "verify_body": (
            "- `POST {p}/auth/register` answers **`202`** "
            '`{{"detail": "Check your inbox to continue"}}` for new **and** already registered '
            "emails (it does not reveal accounts). The owner of an existing account receives "
            '"you already have an account" instead; the account does not change.\n'
            "- The link (valid {verify_ttl} hours) opens your page, which calls "
            '`POST {p}/auth/email/verify` with `{{"token": "…"}}` → `204`. Clicking twice '
            "is also `204`. It does not log in.\n"
            "{mode_line}"
            "- Resend: `POST {p}/auth/email/verify/resend` without body (logged in) or with "
            '`{{"email": "…"}}` (not logged in) → always `202`.\n'
            "- `GET {p}/users/me` includes `email_verified`.\n"
            "- The token prefix is a stable contract: `ev_` = sign-up verification, `ec_` = "
            'email change (after an `ec_` confirmation every session is closed: show "email '
            'changed, log in again").\n'
            "- **Switching to `required` later?** Users who signed up while verification was "
            "`off` are not verified and would get `403` until they verify. The operator can mark "
            "them (they were already trusted): `apigen users verify --all-existing "
            "[--before YYYY-MM-DD]`; `apigen check` warns when there are unverified users.\n"
        ),
        "required_line": "- **Required** mode: until the email is verified, the login answers "
        '`403 email_not_verified` (only when the password is correct): show a "check your '
        'inbox" screen with a resend button.\n',
        "optional_line": "- **Optional** mode: the user can log in without verifying; use "
        "`email_verified` to show a reminder.\n",
        "change_title": "Changing the email",
        "change_body": (
            '`POST {p}/users/me/email` with `{{"new_email": "…", "current_password": "…"}}` '
            "→ `202` (also when the address is taken). Nothing changes until the user opens the "
            "link sent to the **new** address (same verification page, valid {change_ttl} "
            "minutes); the old address is notified. Confirming closes every session.\n"
        ),
        "front_title": "What your front-end must do",
        "front_body": (
            "Two pages (reset password and verify email) that:\n\n"
            "- read the token from the fragment and remove it from the address bar;\n"
            "- call the API with `POST` (never put the token in a `GET` to the API);\n"
            "- load no third-party scripts before using the token "
            "(and send `Referrer-Policy: no-referrer` if you move the token to `?token=`);\n"
            "- on `429`, wait for `Retry-After` before enabling the button again;\n"
            "- always send `Accept-Language` (the email language follows it, then the one "
            "saved for the user).\n\n"
            "Mobile apps: `FRONTEND_URL` must be `https`, so use *universal links* (iOS) / "
            "*app links* (Android) on that domain to open the app with the token.\n\n"
            "```js\n"
            'const token = new URLSearchParams(location.hash.slice(1)).get("token");\n'
            'history.replaceState(null, "", location.pathname); // hide the token\n'
            "const r = await fetch(`${{API}}{p}/auth/password/reset`, {{\n"
            '  method: "POST", headers: {{"Content-Type": "application/json"}},\n'
            "  body: JSON.stringify({{ token, new_password }}),\n"
            "}});\n"
            'if (r.status === 204) location.assign("/login?reset=ok");\n'
            "```\n\n"
            "Limits: {email_limit} per IP for forgot/resend, {confirm_limit} for the token "
            "endpoints, and at most {per_hour} emails per hour to the same account. For your "
            "support team: if a user does not receive the email after several attempts, the "
            "per-account limit may have been reached; ask them to wait an hour.\n"
        ),
        "err_rows": [
            ("400", "invalid_or_expired_token", "Reset/verification link wrong, expired or used"),
            (
                "400",
                "wrong_password / same_email",
                "Email change: wrong current password / same email",
            ),
            ("409", "email_taken", "Email change confirmed after someone else took that address"),
            (
                "403",
                "email_not_verified / password_reset_disabled / email_verification_disabled / "
                "email_change_disabled",
                "Email not verified yet, or the flow is not enabled in this API",
            ),
        ],
        "cfg_rows": [
            ("EMAIL_VERIFICATION", "`off` · `optional` · `required`"),
            ("PASSWORD_RESET", "`on` / `off`"),
            ("FRONTEND_URL", "**Required with the above.** `https://` URL of your front-end"),
            ("EMAIL_BACKEND", "**Required in production with the above:** `smtp`"),
            (
                "SMTP_HOST / SMTP_PORT / SMTP_SECURITY",
                "Your provider (`587` + `starttls` or `465` + `ssl`)",
            ),
            ("SMTP_USER / SMTP_PASSWORD", "Provider credentials (only the worker receives them)"),
            ("EMAIL_FROM", "Sender on **your** domain, e.g. `no-reply@<your-domain>`"),
            (
                "MAIL_BRAND_NAME / MAIL_BRAND_LOGO_URL / MAIL_BRAND_COLOR",
                "Your brand in the emails",
            ),
            (
                "MAIL_SUPPORT_EMAIL / MAIL_FOOTER / MAIL_DEFAULT_LANGUAGE",
                "Contact, legal footer, language",
            ),
        ],
        "deliver_title": "Email delivery",
        "deliver_body": (
            "Works with any SMTP provider (Amazon SES, Brevo, Mailgun, SendGrid, Postmark, "
            "Resend, Zoho, Microsoft 365...): change provider by editing `.env`.\n\n"
            "- Configure **SPF, DKIM and DMARC** for the sender domain (your provider explains "
            "how); without them the emails end up in spam.\n"
            "- Test it: `docker compose exec worker apigen email test you@<your-domain>` "
            "(provider errors are explained).\n"
            "- If your hosting blocks ports 587/465, use port `2525` of your provider.\n"
            "- Minimum lines to add to `.env` in production: `EMAIL_BACKEND=smtp`, `SMTP_HOST`, "
            "`SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM` and "
            "`FRONTEND_URL` (without them the API refuses to start and says which one is "
            "missing).\n"
            "- Your own texts: `apigen email eject` copies the templates to `email_templates/` "
            "(they win over the default ones); `apigen email preview` renders them.\n"
        ),
        "register_202": '   `202` → `{"detail": "Check your inbox to continue"}` (then verify the '
        "email: see *Account emails*)\n",
    },
    "es": {
        "feature": "Verificación de email y recuperación de contraseña por correo, con tu marca "
        "y tu propio proveedor de correo (cualquier SMTP)",
        "title": "Correos de cuenta: verificación de email y recuperación de contraseña",
        "status": "Esta API: verificación de email **{mode}** · recuperación de contraseña "
        "**{reset}**. `GET {p}/auth/features` devuelve lo mismo para que tu frontend muestre u "
        "oculte estas opciones sin fijarlas en el código.\n",
        "links": "Los correos enlazan a **tu frontend**, nunca a la API: `FRONTEND_URL` + "
        "`{reset_path}` y `FRONTEND_URL` + `{verify_path}` (por ejemplo "
        "`https://app.example.com{reset_example}`). El token va en el fragmento de la URL "
        "(`#`), que el navegador nunca envía a ningún servidor.\n",
        "reset_title": "Recuperar la contraseña",
        "reset_body": (
            '1. `POST {p}/auth/password/forgot` con `{{"email": "…"}}` → **siempre `202`** con '
            'el mismo cuerpo, exista o no la cuenta. Muestra un mensaje neutro ("si el email '
            'está registrado, recibirás un enlace").\n'
            "2. El usuario abre el enlace (vale {reset_ttl} minutos y un solo uso).\n"
            "3. Tu página lee el token, opcionalmente lo comprueba con "
            '`POST {p}/auth/password/reset/validate` (`{{"token": "…"}}` → `204`, o `400` si '
            "ha caducado) y envía `POST {p}/auth/password/reset` con "
            '`{{"token": "…", "new_password": "…"}}` → `204`.\n'
            "4. Se cierran todas las sesiones (hay que volver a entrar), se desbloquea la cuenta "
            'si estaba bloqueada y el usuario recibe un aviso de "contraseña cambiada".\n\n'
            "`400 invalid_or_expired_token` → ofrece pedir un enlace nuevo. "
            "`422 password_policy` → mismo formato que `POST {p}/users/me/password`; el enlace "
            "sigue valiendo.\n"
        ),
        "verify_title": "Verificación de email",
        "verify_body": (
            "- `POST {p}/auth/register` responde **`202`** "
            '`{{"detail": "Check your inbox to continue"}}` tanto a emails nuevos como a los ya '
            "registrados (no revela cuentas). El dueño de una cuenta existente recibe un aviso "
            '"ya tienes cuenta"; su cuenta no cambia.\n'
            "- El enlace (vale {verify_ttl} horas) abre tu página, que llama a "
            '`POST {p}/auth/email/verify` con `{{"token": "…"}}` → `204`. Pulsarlo dos veces '
            "también da `204`. No inicia sesión.\n"
            "{mode_line}"
            "- Reenviar: `POST {p}/auth/email/verify/resend` sin cuerpo (con sesión) o con "
            '`{{"email": "…"}}` (sin sesión) → siempre `202`.\n'
            "- `GET {p}/users/me` incluye `email_verified`.\n"
            "- El prefijo del token es un contrato estable: `ev_` = verificación del alta, "
            "`ec_` = cambio de email (tras confirmar un `ec_` se cierran todas las sesiones: "
            'muestra "email cambiado, vuelve a iniciar sesión").\n'
            "- **¿Vas a pasar a `required` más adelante?** Quien se registró con la verificación "
            "en `off` no está verificado y recibiría `403` hasta verificar. El operador puede "
            "marcarlos (ya eran de confianza): `apigen users verify --all-existing "
            "[--before AAAA-MM-DD]`; `apigen check` avisa si hay usuarios sin verificar.\n"
        ),
        "required_line": "- Modo **required**: hasta verificar el email, el login responde "
        "`403 email_not_verified` (solo si la contraseña es correcta): muestra una pantalla "
        '"revisa tu correo" con un botón de reenviar.\n',
        "optional_line": "- Modo **optional**: se puede entrar sin verificar; usa "
        "`email_verified` para mostrar un aviso.\n",
        "change_title": "Cambiar el email",
        "change_body": (
            '`POST {p}/users/me/email` con `{{"new_email": "…", "current_password": "…"}}` '
            "→ `202` (también si la dirección está ocupada). No cambia nada hasta que el usuario "
            "abre el enlace enviado a la dirección **nueva** (la misma página de verificación, "
            "vale {change_ttl} minutos); la antigua recibe un aviso. Al confirmar se cierran "
            "todas las sesiones.\n"
        ),
        "front_title": "Qué tiene que hacer tu frontend",
        "front_body": (
            "Dos páginas (restablecer contraseña y verificar email) que:\n\n"
            "- lean el token del fragmento y lo quiten de la barra de direcciones;\n"
            "- llamen a la API con `POST` (nunca pongas el token en un `GET` a la API);\n"
            "- no carguen scripts de terceros antes de usar el token (y envíen "
            "`Referrer-Policy: no-referrer` si mueves el token a `?token=`);\n"
            "- ante un `429`, esperen `Retry-After` antes de reactivar el botón;\n"
            "- envíen siempre `Accept-Language` (el idioma del correo lo sigue y, si no, el "
            "guardado para el usuario).\n\n"
            "Apps móviles: `FRONTEND_URL` debe ser `https`, así que usa *universal links* "
            "(iOS) / *app links* (Android) en ese dominio para abrir la app con el token.\n\n"
            "```js\n"
            'const token = new URLSearchParams(location.hash.slice(1)).get("token");\n'
            'history.replaceState(null, "", location.pathname); // oculta el token\n'
            "const r = await fetch(`${{API}}{p}/auth/password/reset`, {{\n"
            '  method: "POST", headers: {{"Content-Type": "application/json"}},\n'
            "  body: JSON.stringify({{ token, new_password }}),\n"
            "}});\n"
            'if (r.status === 204) location.assign("/login?reset=ok");\n'
            "```\n\n"
            "Límites: {email_limit} por IP en forgot/resend, {confirm_limit} en los endpoints "
            "con token y como mucho {per_hour} correos por hora a la misma cuenta. Para tu "
            "soporte: si a un usuario no le llega el correo tras varios intentos, puede haber "
            "alcanzado el límite por cuenta; que espere una hora.\n"
        ),
        "err_rows": [
            (
                "400",
                "invalid_or_expired_token",
                "Enlace de recuperación/verificación malo, caducado o usado",
            ),
            (
                "400",
                "wrong_password / same_email",
                "Cambio de email: contraseña actual mala / mismo email",
            ),
            (
                "409",
                "email_taken",
                "Cambio de email confirmado cuando otra cuenta ya usaba esa dirección",
            ),
            (
                "403",
                "email_not_verified / password_reset_disabled / email_verification_disabled / "
                "email_change_disabled",
                "Email aún sin verificar, o el flujo no está activado en esta API",
            ),
        ],
        "cfg_rows": [
            ("EMAIL_VERIFICATION", "`off` · `optional` · `required`"),
            ("PASSWORD_RESET", "`on` / `off`"),
            ("FRONTEND_URL", "**Obligatoria con lo anterior.** URL `https://` de tu frontend"),
            ("EMAIL_BACKEND", "**Obligatoria en producción con lo anterior:** `smtp`"),
            (
                "SMTP_HOST / SMTP_PORT / SMTP_SECURITY",
                "Tu proveedor (`587` + `starttls` o `465` + `ssl`)",
            ),
            ("SMTP_USER / SMTP_PASSWORD", "Credenciales del proveedor (solo las recibe el worker)"),
            ("EMAIL_FROM", "Remitente de **tu** dominio, p. ej. `no-reply@<tu-dominio>`"),
            ("MAIL_BRAND_NAME / MAIL_BRAND_LOGO_URL / MAIL_BRAND_COLOR", "Tu marca en los correos"),
            (
                "MAIL_SUPPORT_EMAIL / MAIL_FOOTER / MAIL_DEFAULT_LANGUAGE",
                "Contacto, pie legal, idioma",
            ),
        ],
        "deliver_title": "Envío de correo",
        "deliver_body": (
            "Funciona con cualquier proveedor SMTP (Amazon SES, Brevo, Mailgun, SendGrid, "
            "Postmark, Resend, Zoho, Microsoft 365...): cambia de proveedor editando `.env`.\n\n"
            "- Configura **SPF, DKIM y DMARC** del dominio remitente (tu proveedor explica "
            "cómo); sin ellos los correos acaban en spam.\n"
            "- Pruébalo: `docker compose exec worker apigen email test tu@<tu-dominio>` "
            "(explica los errores del proveedor).\n"
            "- Si tu hosting bloquea los puertos 587/465, usa el puerto `2525` de tu proveedor.\n"
            "- Líneas mínimas que añadir al `.env` en producción: `EMAIL_BACKEND=smtp`, "
            "`SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USER`, `SMTP_PASSWORD`, "
            "`EMAIL_FROM` y `FRONTEND_URL` (sin ellas la API no arranca y dice cuál falta).\n"
            "- Textos propios: `apigen email eject` copia las plantillas a `email_templates/` "
            "(ganan a las de serie); `apigen email preview` las muestra.\n"
        ),
        "register_202": '   `202` → `{"detail": "Check your inbox to continue"}` (después hay que '
        "verificar el email: ver *Correos de cuenta*)\n",
    },
}


def account_section(values: dict[str, str], lang: str, p: str) -> str:
    """Sección "Correos de cuenta" (vacía si no hay flujos activos)."""
    mode, reset = modes(values)
    if mode == "off" and not reset:
        return ""
    t = T[lang]
    reset_path = values.get("EMAIL_LINK_RESET") or "/reset-password#token={token}"
    verify_path = values.get("EMAIL_LINK_VERIFY") or "/verify-email#token={token}"
    out = [f"### {t['title']}\n"]
    out.append(t["status"].format(mode=mode, reset="on" if reset else "off", p=p))
    out.append(
        t["links"].format(
            reset_path=reset_path,
            verify_path=verify_path,
            reset_example=reset_path.replace("{token}", "pr_…"),
        )
    )
    if reset:
        out.append(
            f"#### {t['reset_title']}\n\n"
            + t["reset_body"].format(p=p, reset_ttl=values.get("TOKEN_TTL_RESET_MINUTES") or 30)
        )
    if mode != "off":
        mode_line = t["required_line"] if mode == "required" else t["optional_line"]
        out.append(
            f"#### {t['verify_title']}\n\n"
            + t["verify_body"].format(
                p=p, verify_ttl=values.get("TOKEN_TTL_VERIFY_HOURS") or 48, mode_line=mode_line
            )
        )
    out.append(
        f"#### {t['change_title']}\n\n"
        + t["change_body"].format(
            p=p, change_ttl=values.get("TOKEN_TTL_EMAIL_CHANGE_MINUTES") or 60
        )
    )
    out.append(
        f"#### {t['front_title']}\n\n"
        + t["front_body"].format(
            p=p,
            email_limit=values.get("RATE_LIMIT_EMAIL_REQUEST") or "5/minute;20/hour",
            confirm_limit=values.get("RATE_LIMIT_TOKEN_CONFIRM") or "10/minute;50/hour",
            per_hour=values.get("EMAIL_PER_ACCOUNT_PER_HOUR") or 3,
        )
    )
    return "\n".join(out)
