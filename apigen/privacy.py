"""Inventario de datos personales: `apigen privacy inventory` -> docs/DATA_INVENTORY.md.

Es la base del registro de actividades de tratamiento (ISO 27701 7.2.8, RGPD art. 30)
y de la identificación de información confidencial (SOC 2 C1.1). Se construye con
las specs de `resources/` (clasificación `pii`/`sensitive`, `purpose`, permisos) y
con las tablas del núcleo, así que se regenera igual en cualquier máquina: CI puede
comprobar con `--check` que está al día. Los plazos se citan por su variable de
entorno y su valor por defecto, no por el `.env` local.

Lo que el código no sabe (responsable, base legal, encargados, transferencias
internacionales) queda como campos «a completar» fuera de los marcadores.
"""

from __future__ import annotations

from typing import Any

from apigen.spec import ResourceSpec

BEGIN = "<!-- apigen:inventory:begin -->"
END = "<!-- apigen:inventory:end -->"

_HEADER = """# Inventario de datos personales

Registro de actividades de tratamiento de esta API (ISO/IEC 27701 7.2.8, RGPD art. 30)
e identificación de información confidencial (SOC 2 C1.1).

## A completar por el responsable (fuera de los marcadores: apigen no lo toca)

| Campo | Valor |
|---|---|
| Responsable del tratamiento | _(empresa, CIF, dirección)_ |
| Delegado de protección de datos / contacto de privacidad | _(email)_ |
| Base legal de cada finalidad | _(contrato, consentimiento, interés legítimo...)_ |
| Encargados (hosting, base de datos, proveedor SMTP...) y sus contratos (DPA) | _(lista)_ |
| Transferencias internacionales y garantías | _(ninguna / cláusulas tipo...)_ |
| Plazo de conservación de los logs (auditoría y acceso) en el SIEM | _(recomendado: 1 año)_ |

"""

# (tabla, datos personales, finalidad, retención)
_CORE = [
    (
        "users",
        "email, full_name, hashed_password (Argon2id), role, locale, last_login_at, "
        "email_verified_at, intentos fallidos y bloqueo",
        "Cuenta y autenticación",
        "Hasta la supresión (DELETE /users/me o un admin). Cuentas nunca verificadas con "
        "EMAIL_VERIFICATION=required: {UNVERIFIED_ACCOUNT_RETENTION_DAYS} días "
        "(UNVERIFIED_ACCOUNT_RETENTION_DAYS)",
    ),
    (
        "refresh_tokens",
        "client_ip (o prefijo /64), user_agent, hash del token",
        "Sesiones, detección de robo de tokens y bloqueo inteligente",
        "Mientras la sesión viva + {LOGIN_FAMILIAR_DAYS} días (LOGIN_FAMILIAR_DAYS)",
    ),
    (
        "account_tokens",
        "email de destino, hash del token",
        "Recuperación de contraseña, verificación y cambio de email",
        "1 día tras caducar o usarse",
    ),
    (
        "email_log",
        "user_id, hash del destinatario, tipo de correo (sin dirección ni contenido)",
        "Cupos antiabuso e idempotencia de envíos",
        "2 días",
    ),
    (
        "jobs",
        "owner_id; el payload puede incluir datos de la petición (p. ej. el email nuevo)",
        "Cola de trabajos en segundo plano",
        "{JOBS_RETENTION_DAYS} días tras terminar (JOBS_RETENTION_DAYS)",
    ),
    (
        "log de auditoría",
        "user_id, client_ip completa, request_id (nunca emails, contraseñas ni tokens)",
        "Seguridad y trazabilidad (SOC 2 CC7.2)",
        "Fuera de la API (SIEM): ver «A completar»",
    ),
    (
        "log de acceso",
        "client_ip según ACCESS_LOG_IP (por defecto truncada: /24 o /48), ruta, estado",
        "Operación y diagnóstico",
        "Fuera de la API (SIEM): ver «A completar»",
    ),
]

_RIGHTS = """
## Derechos de los interesados

| Derecho | Cómo se ejerce |
|---|---|
| Acceso y portabilidad (ISO 27701 7.3.8) | `GET /api/<versión>/users/me/export`: JSON con la cuenta, sesiones, correos, trabajos y filas de los recursos del usuario (sin campos `write_only` ni hashes) |
| Rectificación (7.3.6) | `PATCH /api/<versión>/users/me` y el `PATCH` de cada recurso propio; email: `POST /users/me/email` |
| Supresión (7.3.6) | `DELETE /api/<versión>/users/me` con la contraseña (si ALLOW_SELF_DELETION=true) o `DELETE /users/{id}` (admin). Borra en cascada lo que le pertenece |
| Evidencias | Eventos `privacy.export`, `privacy.erasure`, `retention.prune` en el log de auditoría |
"""


def _defaults() -> dict[str, Any]:
    import logging

    # Importar la configuración la instancia: sus avisos (SECRET_KEY...) aquí son ruido.
    logging.getLogger("app.core.config").setLevel(logging.ERROR)
    from app.core.config import Settings

    return {name: field.default for name, field in Settings.model_fields.items()}


def _resource_rows(specs: list[ResourceSpec], defaults: dict[str, Any]) -> list[str]:
    rows = []
    for spec in sorted(specs, key=lambda s: s.name):
        p = spec.permissions
        personal = [n for n, f in spec.fields.items() if f.pii and not f.sensitive]
        sensitive = [n for n, f in spec.fields.items() if f.sensitive]
        people = [n for n, f in spec.fields.items() if f.type == "fk" and f.to == "user"]
        if spec.owned:
            people.insert(0, "owner_id")
        if spec.owned:
            retention = "Hasta borrarla o suprimir la cuenta del dueño (CASCADE)"
        else:
            retention = "Hasta borrarla (sin plazo automático)"
        if spec.soft_delete:
            days = defaults["SOFT_DELETE_RETENTION_DAYS"]
            retention += f"; tras el borrado lógico, {days} días (SOFT_DELETE_RETENTION_DAYS)"
        missing = (
            "_(a completar: `purpose:` en la spec)_" if people or personal or sensitive else "-"
        )
        rows.append(
            f"| `{spec.table}` | {spec.purpose or missing} "
            f"| {', '.join(people) or '-'} | {', '.join(personal) or '-'} "
            f"| {', '.join(sensitive) or '-'} | list={p.list}, read={p.read} | {retention} |"
        )
    return rows


def render_inventory(specs: list[ResourceSpec]) -> str:
    """Bloque generado (entre marcadores) del inventario."""
    defaults = _defaults()
    out = [BEGIN, "## Tablas del núcleo (plantilla)", ""]
    out += ["| Tabla | Datos personales | Finalidad | Conservación |", "|---|---|---|---|"]
    for table, data, purpose, retention in _CORE:
        out.append(f"| `{table}` | {data} | {purpose} | {retention.format(**defaults)} |")
    out += ["", "## Recursos generados (`resources/*.yaml`)", ""]
    if specs:
        out += [
            "| Tabla | Finalidad | Vínculo con personas | pii | sensitive | Acceso | Conservación |",
            "|---|---|---|---|---|---|---|",
            *_resource_rows(specs, defaults),
        ]
        unclassified = sorted(
            spec.name
            for spec in specs
            if not any(f.pii for f in spec.fields.values())
            and (spec.owned or any(f.type == "fk" and f.to == "user" for f in spec.fields.values()))
        )
        if unclassified:
            out += [
                "",
                "> Recursos ligados a usuarios sin ningún campo `pii`: "
                + ", ".join(unclassified)
                + ". Revisa si guardan datos personales y márcalos en la spec.",
            ]
    else:
        out.append("_(ninguno todavía)_")
    out += [_RIGHTS.rstrip(), "", END]
    return "\n".join(out) + "\n"


def merge_inventory(existing: str | None, block: str) -> str:
    """Sustituye el bloque generado y conserva lo que el responsable haya completado."""
    if existing and BEGIN in existing and END in existing:
        head, rest = existing.split(BEGIN, 1)
        tail = rest.split(END, 1)[1].lstrip("\n")
        return head + block + (("\n" + tail) if tail else "")
    return _HEADER + block
