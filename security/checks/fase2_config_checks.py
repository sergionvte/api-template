# ruff: noqa: E501
"""ST-34/35/36 (configuración): la app no arranca con configuración de correo insegura.

    .venv/bin/python security/checks/fase2_config_checks.py

Instancia `Settings` sin .env (APP_ENV_FILE inexistente) con distintas variables.
"""

from __future__ import annotations

import os
import secrets
import sys
import tempfile

os.environ["APP_ENV_FILE"] = os.path.join(tempfile.mkdtemp(), "none.env")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.config import Settings  # noqa: E402

BASE = {
    "ENVIRONMENT": "production",
    "SECRET_KEY": secrets.token_urlsafe(48),
    "DATABASE_URL": "postgresql+asyncpg://u:p@db/api",
    "ALLOWED_HOSTS": ["api.cliente.dev"],
    "TRUSTED_PROXIES": ["10.0.0.1"],
    "EMAIL_VERIFICATION": "required",
    "PASSWORD_RESET": True,
    "EMAIL_BACKEND": "smtp",
    "EMAIL_FROM": "no-reply@cliente.dev",
    "FRONTEND_URL": "https://app.cliente.dev",
    "CORS_ORIGINS": ["https://app.cliente.dev"],
    "SMTP_HOST": "smtp.proveedor.dev",
}


def check(name: str, overrides: dict, expect_error: bool, role: str = "api") -> bool:
    values = {**BASE, "PROCESS_ROLE": role, **overrides}
    values = {k: v for k, v in values.items() if v is not None}
    try:
        Settings(**values)
        error = None
    except Exception as exc:  # noqa: BLE001
        error = str(exc).splitlines()[1:3]
    ok = (error is not None) == expect_error
    verdict = "OK   " if ok else "FALLO"
    print(f"[{verdict}] {name}: {'rechazada' if error else 'aceptada'} {error or ''}")
    return ok


CASES = [
    ("base válida", {}, False),
    ("sin EMAIL_BACKEND", {"EMAIL_BACKEND": None}, True),
    ("backend console", {"EMAIL_BACKEND": "console"}, True),
    ("backend file", {"EMAIL_BACKEND": "file"}, True),
    ("backend memory", {"EMAIL_BACKEND": "memory"}, True),
    ("disabled + required", {"EMAIL_BACKEND": "disabled"}, True),
    ("sin EMAIL_FROM", {"EMAIL_FROM": ""}, True),
    ("EMAIL_FROM @example.com", {"EMAIL_FROM": "no-reply@example.com"}, True),
    ("EMAIL_FROM con CRLF", {"EMAIL_FROM": "a@cliente.dev\r\nBcc: x@evil.dev"}, True),
    ("EMAIL_FROM_NAME con LF", {"EMAIL_FROM_NAME": "Cliente\nBcc: x@evil.dev"}, True),
    ("EMAIL_FROM con nombre", {"EMAIL_FROM": "Cliente <a@cliente.dev>"}, True),
    ("FRONTEND_URL http", {"FRONTEND_URL": "http://app.cliente.dev"}, True),
    ("FRONTEND_URL localhost", {"FRONTEND_URL": "https://localhost:3000"}, True),
    ("FRONTEND_URL con usuario", {"FRONTEND_URL": "https://app.cliente.dev@evil.dev"}, True),
    ("FRONTEND_URL con fragmento", {"FRONTEND_URL": "https://app.cliente.dev/#x"}, True),
    ("EMAIL_LINK_RESET sin {token}", {"EMAIL_LINK_RESET": "/reset"}, True),
    ("EMAIL_LINK_RESET {token}x2", {"EMAIL_LINK_RESET": "/r#t={token}&u={token}"}, True),
    ("EMAIL_LINK_RESET protocol-relative", {"EMAIL_LINK_RESET": "//evil.dev/#token={token}"}, True),
    ("EMAIL_DELIVERY inline", {"EMAIL_DELIVERY": "inline"}, True),
    (
        "custom fuera de app.*",
        {"EMAIL_BACKEND": "custom", "EMAIL_BACKEND_CLASS": "os:system"},
        True,
    ),
    ("MAIL_BRAND_COLOR inyectado", {"MAIL_BRAND_COLOR": "red;background:url(x)"}, True),
    ("MAIL_LANGUAGES con ruta", {"MAIL_LANGUAGES": ["en", "../x"]}, True),
    ("worker smtp none a host remoto", {"SMTP_SECURITY": "none"}, True, "worker"),
    ("worker SMTP_USER sin contraseña", {"SMTP_USER": "u"}, True, "worker"),
    ("worker sin SMTP_HOST", {"SMTP_HOST": ""}, True, "worker"),
    # Observaciones (no bloqueantes): se documentan como Info.
    # Info-2 corregido en fase2-correcciones: ya no se aceptan.
    (
        "worker smtp none a *.localhost (Info-2 corregido)",
        {"SMTP_SECURITY": "none", "SMTP_HOST": "relay.localhost"},
        True,
        "worker",
    ),
    (
        "FRONTEND_URL IP de loopback no canónica (corregido)",
        {"FRONTEND_URL": "https://127.0.0.2"},
        True,
    ),
    ("[info] EMAIL_FROM example.co.uk", {"EMAIL_FROM": "no-reply@example.co.uk"}, False),
    (
        "[info] features off: console en producción",
        {"EMAIL_VERIFICATION": "off", "PASSWORD_RESET": False, "EMAIL_BACKEND": "console"},
        False,
    ),
]

if __name__ == "__main__":
    results = [check(*case) for case in CASES]
    print(f"\n{sum(results)}/{len(results)} como se esperaba")
    sys.exit(0 if all(results) else 1)
