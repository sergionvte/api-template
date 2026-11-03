"""CLI `apigen`: genera recursos, gestiona versiones, base de datos y utilidades.

Ejecuta `apigen --help` o `apigen <comando> --help` para ver todas las opciones.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import re
import secrets
import stat
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from apigen import project
from apigen.spec import (
    ACTIONS,
    VERSION_NAME,
    Permissions,
    RateLimits,
    ResourceSpec,
    SpecError,
    format_errors,
    load_specs,
    parse_field_option,
)

app = typer.Typer(
    help="Generador de APIs FastAPI + SQLModel. Crea recursos CRUD seguros y versionados.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)
version_app = typer.Typer(help="Gestiona versiones de la API (v1, v2...).", no_args_is_help=True)
db_app = typer.Typer(help="Migraciones de base de datos (Alembic).", no_args_is_help=True)
app.add_typer(version_app, name="version")
email_app = typer.Typer(
    help="Correo: prueba de envío, vista previa y copia de plantillas.", no_args_is_help=True
)
app.add_typer(db_app, name="db")
app.add_typer(email_app, name="email")
users_app = typer.Typer(
    help="Operaciones de operador sobre usuarios (quedan en el log de auditoría).",
    no_args_is_help=True,
)
app.add_typer(users_app, name="users")
audit_app = typer.Typer(
    help="Registro de auditoría (integridad de la cadena).", no_args_is_help=True
)
app.add_typer(audit_app, name="audit")
privacy_app = typer.Typer(
    help="Privacidad: inventario de datos personales (registro de actividades).",
    no_args_is_help=True,
)
app.add_typer(privacy_app, name="privacy")


def _fail(message: str) -> None:
    typer.secho(f"✗ {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


def _refresh_graph(base) -> None:
    """Mantiene al día graphify-out/ tras cambiar código generado."""
    message = project.refresh_graph(base)
    if message:
        ok = message.startswith("grafo actualizado")
        typer.secho(f"  {message}", fg=None if ok else typer.colors.YELLOW)


INVENTORY = Path("docs/DATA_INVENTORY.md")


def _inventory(base: Path, path: Path) -> tuple[str | None, str]:
    """(contenido actual, contenido al día) del inventario de datos personales."""
    from apigen.privacy import merge_inventory, render_inventory

    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    specs = list(project.load_all_specs(base).values())
    current = path.read_text(encoding="utf-8") if path.exists() else None
    return current, merge_inventory(current, render_inventory(specs))


def _refresh_inventory(base: Path) -> None:
    """Tras generar o quitar recursos, mantiene al día el inventario si el proyecto lo
    tiene (así `apigen privacy inventory --check` no falla en CI por un olvido)."""
    path = base / INVENTORY
    if not path.exists():
        return
    current, updated = _inventory(base, path)
    if updated != current:
        path.write_text(updated, encoding="utf-8")
        typer.echo(f"  inventario de datos actualizado ({INVENTORY})")


def _print_log(lines: list[str]) -> None:
    for line in lines:
        typer.echo(f"  {line}")


# ---------------------------------------------------------------------------
# Recursos
# ---------------------------------------------------------------------------
@app.command()
def add(
    name: Annotated[str, typer.Argument(help="Nombre en singular y snake_case, p. ej. 'product'")],
    field: Annotated[
        list[str],
        typer.Option(
            "--field", "-f", help="nombre:tipo[:opciones]. Repetible. Ver `apigen types`."
        ),
    ],
    plural: Annotated[str | None, typer.Option(help="Plural si no es regular")] = None,
    owned: Annotated[bool, typer.Option(help="Cada fila pertenece al usuario que la crea")] = False,
    soft_delete: Annotated[bool, typer.Option(help="Borrado lógico (deleted_at)")] = False,
    shared_read: Annotated[
        bool,
        typer.Option(help="Recurso owned que otros pueden leer a propósito (p. ej. un blog)"),
    ] = False,
    perm: Annotated[
        list[str] | None,
        typer.Option(help="accion=nivel, p. ej. list=public. Niveles: public|user|owner|admin"),
    ] = None,
    filter: Annotated[list[str] | None, typer.Option("--filter", help="Campo filtrable")] = None,
    search: Annotated[list[str] | None, typer.Option(help="Campo para búsqueda ?q=")] = None,
    order: Annotated[list[str] | None, typer.Option(help="Campo ordenable")] = None,
    rate_read: Annotated[str | None, typer.Option(help="Límite GET, p. ej. '300/minute'")] = None,
    rate_write: Annotated[
        str | None, typer.Option(help="Límite escrituras, p. ej. '30/minute'")
    ] = None,
    version: Annotated[
        list[str] | None,
        typer.Option(
            "--version",
            "-v",
            help="Versión(es) de la API (por defecto, la más reciente no deprecada)",
        ),
    ] = None,
    description: Annotated[str | None, typer.Option(help="Descripción")] = None,
    purpose: Annotated[
        str | None, typer.Option(help="Finalidad del tratamiento (inventario de datos)")
    ] = None,
    force: Annotated[bool, typer.Option(help="Sobrescribir ficheros existentes")] = False,
    dry_run: Annotated[bool, typer.Option(help="Mostrar qué se generaría sin escribir")] = False,
    tests: Annotated[bool, typer.Option("--tests/--no-tests", help="Generar tests")] = True,
    migrate: Annotated[bool, typer.Option(help="Crear y aplicar la migración al terminar")] = False,
) -> None:
    """Crea un recurso CRUD completo desde la línea de comandos."""
    if not plural and name.endswith("s") and not name.endswith("ss"):
        typer.secho(
            f"! '{name}' parece un plural: usa el singular (p. ej. '{name[:-1]}') o indica "
            "--plural. Se generará igualmente.",
            fg=typer.colors.YELLOW,
            err=True,
        )
    try:
        fields = dict(parse_field_option(raw) for raw in field)
        permissions: dict[str, str] = {}
        for item in perm or []:
            action, _, level = item.partition("=")
            if action not in ACTIONS:
                raise SpecError(f"--perm: acción desconocida {action!r} ({', '.join(ACTIONS)})")
            permissions[action] = level
        spec = ResourceSpec(
            name=name,
            plural=plural,
            description=description,
            purpose=purpose,
            owned=owned,
            soft_delete=soft_delete,
            shared_read=shared_read,
            versions=version or [project.default_version(project.root())],
            permissions=Permissions.model_validate(permissions),
            rate_limits=RateLimits(read=rate_read, write=rate_write),
            fields=fields,
            filters=filter or [],
            search=search or [],
            ordering=order or [],
        )
    except SpecError as exc:
        _fail(str(exc))
    except ValidationError as exc:
        _fail("Especificación no válida:\n" + format_errors(exc))
    _generate([spec], force=force, dry_run=dry_run, with_tests=tests, migrate=migrate)


@app.command()
def generate(
    path: Annotated[Path, typer.Argument(help="Fichero YAML o directorio")] = Path("resources"),
    only: Annotated[
        list[str] | None,
        typer.Option(help="Generar solo estos recursos (repetible o separados por comas)"),
    ] = None,
    force: Annotated[bool, typer.Option(help="Sobrescribir ficheros existentes")] = False,
    dry_run: Annotated[bool, typer.Option(help="Mostrar qué se generaría sin escribir")] = False,
    tests: Annotated[bool, typer.Option("--tests/--no-tests", help="Generar tests")] = True,
    migrate: Annotated[bool, typer.Option(help="Crear y aplicar la migración al terminar")] = False,
) -> None:
    """Genera recursos a partir de especificaciones YAML."""
    if not path.exists():
        _fail(f"No existe {path}")
    try:
        specs = load_specs(path)
    except SpecError as exc:
        _fail(str(exc))
    if only:
        # `--only a,b` o `--only a --only b` (UX-59).
        wanted = {name.strip() for item in only for name in item.split(",") if name.strip()}
        available = [s.name for s in specs]
        specs = [s for s in specs if s.name in wanted]
        unknown = sorted(wanted - set(available))
        if not specs or unknown:
            _fail(
                f"--only: no existe {', '.join(unknown) or ', '.join(sorted(wanted))} en {path}. "
                f"Recursos disponibles: {', '.join(available) or '(ninguno)'}"
            )
    _generate(specs, force=force, dry_run=dry_run, with_tests=tests, migrate=migrate)


def _warn_specs(specs: list[ResourceSpec]) -> None:
    for spec in specs:
        for warning in spec.warnings():
            typer.secho(f"! {warning}", fg=typer.colors.YELLOW, err=True)


def _generate(
    specs: list[ResourceSpec], *, force: bool, dry_run: bool, with_tests: bool, migrate: bool
) -> None:
    try:
        base = project.root()
        existed = {s.name for s in specs if (base / "app/models" / f"{s.name}.py").exists()}
        log = project.generate(base, specs, force=force, dry_run=dry_run, with_tests=with_tests)
    except SpecError as exc:
        _fail(str(exc))
    names = ", ".join(s.name for s in specs)
    typer.secho(f"✓ {'Simulado' if dry_run else 'Generado'}: {names}", fg=typer.colors.GREEN)
    for spec in specs:
        typer.echo(f"  {spec.name}: /{spec.plural} en {', '.join(spec.versions)}")
    _print_log(log)
    _warn_specs(specs)
    if dry_run:
        return
    _refresh_inventory(base)
    verb = "update" if existed else "add"
    if migrate:
        # _migrate actualiza el grafo si crea una migración; si no, se hace aquí.
        if not _migrate(f"{verb} {names}", expected_tables={s.table for s in specs}):
            _refresh_graph(base)
    else:
        _refresh_graph(base)
        typer.echo(f'\nSiguiente paso: apigen db migrate -m "{verb} {names}"')


@app.command()
def remove(
    name: Annotated[str, typer.Argument(help="Nombre del recurso")],
    keep_spec: Annotated[bool, typer.Option(help="Conservar resources/<nombre>.yaml")] = False,
    force: Annotated[bool, typer.Option(help="Aunque otros recursos lo referencien")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="No pedir confirmación")] = False,
) -> None:
    """Elimina un recurso generado (código, tests y registro). No toca la BD."""
    try:
        # Primero las comprobaciones, luego la confirmación (no preguntar para fallar).
        refs = project.dependents(project.root(), name)
    except SpecError as exc:
        _fail(str(exc))
    if refs and not force:
        _fail(f"Otros recursos apuntan a '{name}': {', '.join(refs)} (usa --force)")
    if not yes and not typer.confirm(f"¿Eliminar el recurso '{name}' y sus ficheros?"):
        typer.echo("Cancelado: no se ha borrado nada.")
        raise typer.Exit(1)
    try:
        base = project.root()
        log = project.remove(base, name, keep_spec=keep_spec, force=force)
    except SpecError as exc:
        _fail(str(exc))
    typer.secho(f"✓ Eliminado {name}", fg=typer.colors.GREEN)
    _print_log(log)
    _refresh_inventory(base)
    _refresh_graph(base)
    typer.echo(f'\nPara borrar la tabla: apigen db migrate -m "drop {name}"')


@app.command("list")
def list_resources() -> None:
    """Lista los recursos definidos en resources/."""
    try:
        specs = project.load_all_specs(project.root())
    except SpecError as exc:
        _fail(str(exc))
    if not specs:
        typer.echo("No hay recursos. Crea uno con `apigen add` o `apigen generate`.")
        return
    for spec in specs.values():
        p = spec.permissions
        flags = [
            f
            for f, on in (
                ("owned", spec.owned),
                ("soft-delete", spec.soft_delete),
                ("shared-read", spec.shared_read),
            )
            if on
        ]
        typer.secho(f"{spec.name}", bold=True, nl=False)
        typer.echo(
            f"  /{spec.plural}  versiones={','.join(spec.versions)}  campos={len(spec.fields)}"
            f"  {' '.join(flags)}"
        )
        typer.echo(
            f"    permisos: list={p.list} read={p.read} create={p.create} "
            f"update={p.update} delete={p.delete}"
        )
        for warning in spec.warnings():
            typer.secho(f"    ! {warning}", fg=typer.colors.YELLOW)


@app.command()
def docs(
    lang: Annotated[
        str | None,
        typer.Option(help="Idioma del README: en | es (por defecto, el que ya tiene; si no, en)"),
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option(help="URL pública para los ejemplos, p. ej. https://api.cliente.com"),
    ] = None,
) -> None:
    """Genera o actualiza README.md para el cliente (endpoints, campos, permisos...).

    Se regenera solo lo que hay entre los marcadores `apigen:docs`; la introducción y
    lo que escribas fuera de ellos se conserva. El idioma y la URL base se recuerdan
    (van en el marcador). Ejecútalo al terminar la API."""
    if lang is not None and lang not in {"en", "es"}:
        _fail("--lang debe ser 'en' o 'es'")
    if base_url is not None and not re.fullmatch(r"https?://[A-Za-z0-9.\-:\[\]/_~%]+", base_url):
        _fail("--base-url debe ser una URL http(s):// sin espacios, p. ej. https://api.cliente.com")
    from apigen.docs import write_readme

    try:
        path, created, lang = write_readme(project.root(), lang, base_url=base_url)
    except SpecError as exc:
        _fail(str(exc))
    verb = "creado" if created else "actualizado"
    typer.secho(f"✓ {path.name} {verb} ({lang})", fg=typer.colors.GREEN)
    from apigen import docs_accounts
    from apigen.docs import read_env_example

    base = project.root()
    differ = docs_accounts.mismatches(base, read_env_example(base))
    if differ:
        typer.secho(
            "  ! El README describe " + ", ".join(differ) + ": copia esos valores a "
            ".env.example (es lo que recibe el cliente) o el entregable no hará lo que dice.",
            fg=typer.colors.YELLOW,
        )
    if created:
        typer.echo("  Completa la introducción y el contacto (fuera de los marcadores).")


@app.command()
def types() -> None:
    """Muestra los tipos de campo y opciones disponibles."""
    typer.echo(
        """Tipos:  str text int float decimal bool date datetime uuid email json enum fk

Sintaxis CLI:  nombre:tipo[:opción][:clave=valor]...   (pon cada -f entre comillas)
  title:str:max=200:unique            texto corto, único
  body:text:nullable                  texto largo opcional
  price:decimal:ge=0:digits=10:places=2
  stock:int:ge=0:default=0
  published:bool:default=false
  'status:enum=draft,published:default=draft'   (también draft|published,
                                      pero entre comillas: | es una tubería)
  category_id:fk=category             clave foránea a otro recurso
  author_id:fk=user:nullable          clave foránea a usuarios
  'code:str:pattern=^[A-Z]{3}$:example=ABC'

Opciones:  nullable unique index immutable write_only
           max= min= ge= le= gt= lt= digits= places= default= example= pattern=
           on_delete=CASCADE|SET NULL|RESTRICT description=

Privacidad (SOC 2 / ISO 27701):
  phone:str:max=20:pii                dato personal (va al inventario y al OpenAPI)
  diagnosis:text:sensitive            categoría especial: solo dueño/admin lo leen,
                                      sin filtros/orden y cifrado en la BD (AES-256)
  --purpose "Seguimiento de pacientes"   finalidad del tratamiento del recurso

Niveles de permiso (--perm accion=nivel): public | user | owner | admin
  acciones: list read create update delete

Lógica propia y procesos pesados (en el YAML del recurso):
  app/hooks/<recurso>.py   before_/after_ create|update|delete (nunca se sobrescribe)
  actions:
    - name: export_pdf       POST /<plural>/{id}/export_pdf
      background: true       responde 202 + job_id; lo ejecuta `apigen worker`
      executor: process      async (E/S) | thread (bloqueante) | process (CPU)
      timeout: 600
    - name: stats            sin background: función homónima en app/hooks/<recurso>.py
      scope: collection      POST /<plural>/stats"""
    )


# ---------------------------------------------------------------------------
# Versiones
# ---------------------------------------------------------------------------
@version_app.command("add")
def version_add(
    name: Annotated[str, typer.Argument(help="Nueva versión, p. ej. v2")],
    source: Annotated[str, typer.Option("--from", help="Versión a copiar")] = "v1",
) -> None:
    """Crea una versión nueva copiando otra (endpoints y tests)."""
    if not VERSION_NAME.match(name) or not VERSION_NAME.match(source):
        _fail("Formato de versión (también en --from): v1, v2, ...")
    try:
        base = project.root()
        log = project.add_version(base, name, source)
    except SpecError as exc:
        _fail(str(exc))
    typer.secho(f"✓ Versión {name} creada a partir de {source}", fg=typer.colors.GREEN)
    _print_log(log)
    _refresh_graph(base)


@version_app.command("deprecate")
def version_deprecate(
    name: Annotated[str, typer.Argument(help="Versión a deprecar")],
    sunset: Annotated[str | None, typer.Option(help="Fecha de retirada YYYY-MM-DD")] = None,
) -> None:
    """Marca una versión como deprecada (cabeceras Deprecation y Sunset)."""
    today = date.today()
    if sunset:
        try:
            sunset_date = date.fromisoformat(sunset)
        except ValueError:
            _fail("--sunset debe ser una fecha válida YYYY-MM-DD")
        if sunset_date <= today:
            typer.secho(
                f"! La fecha de retirada {sunset} ya ha pasado o es hoy.",
                fg=typer.colors.YELLOW,
                err=True,
            )
    base = project.root()
    previous = project.version_info(base).get(name, {})
    since = previous.get("since") or today.isoformat()
    try:
        project.deprecate_version(base, name, sunset, str(since))
    except SpecError as exc:
        _fail(str(exc))
    if previous.get("deprecated"):
        typer.echo(f"  (ya estaba deprecada; sunset anterior: {previous.get('sunset') or '-'})")
    typer.secho(f"✓ {name} deprecada", fg=typer.colors.GREEN)
    _refresh_graph(base)


@version_app.command("list")
def version_list() -> None:
    """Lista las versiones existentes y su estado."""
    base = project.root()
    info = project.version_info(base)
    for v in project.existing_versions(base):
        state = info.get(v, {})
        if state.get("deprecated"):
            extra = f"  deprecada desde {state.get('since') or '?'}"
            if state.get("sunset"):
                extra += f", retirada {state['sunset']}"
            typer.echo(f"{v}{extra}")
        else:
            typer.echo(f"{v}  activa")


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------
def _alembic_config(*, quiet: bool = False):
    from alembic.config import Config

    base = project.root()
    os.chdir(base)
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    cfg = Config(str(base / "alembic.ini"))
    cfg.attributes["quiet"] = quiet  # alembic/env.py baja el log a WARNING
    if quiet:
        # Silencia también los mensajes de estado ("Generating /ruta/absoluta ... done").
        cfg.cmd_opts = argparse.Namespace(quiet=True, x=None)
    return cfg


_MIGRATION_TABLE = re.compile(
    r"op\.(?:create_table|drop_table|add_column|drop_column|alter_column|batch_alter_table"
    r"|create_foreign_key|drop_constraint|create_unique_constraint)\(\s*['\"](\w+)['\"]"
    r"|op\.create_index\(\s*[^,]+,\s*['\"](\w+)['\"]"
    r"|table_name=['\"](\w+)['\"]"
)


def migration_tables(script: Path) -> list[str]:
    """Tablas que toca el `upgrade()` de una migración autogenerada (UX-47)."""
    text = script.read_text(encoding="utf-8").split("def downgrade", 1)[0]
    found = {name for match in _MIGRATION_TABLE.finditer(text) for name in match.groups() if name}
    return sorted(found)


def _script_path(script: object) -> str | None:
    """`command.revision` devuelve None, un Script o (con skip_empty) una lista."""
    if isinstance(script, list):
        script = script[0] if script else None
    path = getattr(script, "path", None)
    return Path(path).name if path else None


@db_app.command("migrate")
def db_migrate(
    message: Annotated[
        str | None, typer.Option("--message", "-m", help="Descripción del cambio")
    ] = None,
    no_upgrade: Annotated[bool, typer.Option(help="Solo crear la migración")] = False,
    verbose: Annotated[bool, typer.Option(help="Mostrar el log de Alembic")] = False,
) -> None:
    """Detecta cambios en los modelos, crea la migración y la aplica."""
    _migrate(message, no_upgrade=no_upgrade, verbose=verbose)


def _migrate(
    message: str | None,
    *,
    no_upgrade: bool = False,
    verbose: bool = False,
    expected_tables: set[str] | None = None,
) -> bool:
    """`db migrate`. Con `expected_tables` (desde `generate --migrate`) avisa si la
    migración incluye tablas de otros recursos (UX-47). Devuelve si creó migración."""
    from alembic import command

    message = message or f"update models {date.today().isoformat()}"
    cfg = _alembic_config(quiet=not verbose)
    # Autogenerate compara contra la BD: primero hay que estar al día.
    command.upgrade(cfg, "head")
    cfg.attributes["skip_empty"] = True
    created = _script_path(command.revision(cfg, message=message, autogenerate=True))
    if created is None:
        typer.echo("Sin cambios en los modelos: no se creó migración.")
    else:
        typer.secho(f"✓ Migración creada: alembic/versions/{created}", fg=typer.colors.GREEN)
        tables = migration_tables(project.root() / "alembic" / "versions" / created)
        if tables:
            typer.echo(f"  Tablas afectadas: {', '.join(tables)}")
        others = sorted(set(tables) - expected_tables) if expected_tables is not None else []
        if others:
            typer.secho(
                f"! La migración incluye también: {', '.join(others)} (cambios pendientes de "
                "otros recursos). Revísala o sepárala antes de desplegarla.",
                fg=typer.colors.YELLOW,
                err=True,
            )
        typer.echo(
            "  Revísala (el autogenerado no detecta renombrados) antes de desplegarla."
            if no_upgrade
            else "  Ya aplicada en esta BD. Revísala antes de desplegarla en producción."
        )
        # Las migraciones también están en el grafo (UX-43).
        _refresh_graph(project.root())
    if not no_upgrade:
        command.upgrade(cfg, "head")
        typer.secho("✓ Base de datos actualizada", fg=typer.colors.GREEN)
    return created is not None


Verbose = Annotated[bool, typer.Option(help="Mostrar el log de Alembic")]


@db_app.command("upgrade")
def db_upgrade(
    revision: Annotated[str, typer.Argument()] = "head", verbose: Verbose = False
) -> None:
    """Aplica migraciones (por defecto hasta la última)."""
    from alembic import command

    command.upgrade(_alembic_config(quiet=not verbose), revision)
    typer.secho(f"✓ Base de datos en {revision}", fg=typer.colors.GREEN)


@db_app.command("downgrade")
def db_downgrade(
    revision: Annotated[str, typer.Argument()] = "-1", verbose: Verbose = False
) -> None:
    """Revierte migraciones (por defecto la última)."""
    from alembic import command

    command.downgrade(_alembic_config(quiet=not verbose), revision)
    typer.secho(f"✓ Revertido ({revision})", fg=typer.colors.GREEN)


@db_app.command("current")
def db_current(verbose: Verbose = False) -> None:
    """Muestra la revisión aplicada."""
    from alembic import command

    command.current(_alembic_config(quiet=not verbose), verbose=True)


@db_app.command("prune")
def db_prune() -> None:
    """Aplica la política de retención. Borra:
    refresh tokens de sesiones muertas con más de LOGIN_FAMILIAR_DAYS días (y con ellos
    la IP guardada), trabajos terminados con más de JOBS_RETENTION_DAYS, tokens de
    cuenta y registros de envío caducados, cuentas nunca verificadas
    (UNVERIFIED_ACCOUNT_RETENTION_DAYS, solo con EMAIL_VERIFICATION=required) y filas
    borradas lógicamente (SOFT_DELETE_RETENTION_DAYS).
    Prográmalo a diario (cron, CronJob...): queda en el log de auditoría."""
    os.chdir(project.root())
    sys.path.insert(0, str(Path.cwd()))
    asyncio.run(_prune())


async def _prune() -> None:
    from app.core.audit import audit
    from app.core.config import settings
    from app.core.logging import setup_logging
    from app.db.session import SessionFactory, engine
    from app.services.account_tokens import prune as prune_account_tokens
    from app.services.auth import prune_refresh_tokens
    from app.services.privacy import prune_soft_deleted, prune_unverified_users
    from app.tasks.queue import prune_jobs

    setup_logging()
    async with SessionFactory() as session:
        removed = await prune_refresh_tokens(session)
        tokens_removed, logs_removed = await prune_account_tokens(session)
        users_removed = await prune_unverified_users(session)
        soft_removed = await prune_soft_deleted(session)
    jobs_removed = await prune_jobs()
    await engine.dispose()
    # Evidencia de que la política de retención se ejecuta (SOC 2 C1.2, ISO 27701 7.4.7).
    audit(
        "retention.prune",
        actor="cli",
        refresh_tokens=removed,
        account_tokens=tokens_removed,
        email_log=logs_removed,
        jobs=jobs_removed,
        unverified_users=users_removed,
        soft_deleted_rows=soft_removed,
    )
    typer.secho(
        f"✓ {jobs_removed} trabajos terminados borrados "
        f"(retención: {settings.JOBS_RETENTION_DAYS} días)",
        fg=typer.colors.GREEN,
    )
    typer.secho(
        f"✓ {removed} refresh tokens borrados (retención: sesiones vivas y "
        f"{settings.LOGIN_FAMILIAR_DAYS} días)",
        fg=typer.colors.GREEN,
    )
    typer.secho(
        f"✓ {tokens_removed} tokens de cuenta y {logs_removed} registros de envío borrados",
        fg=typer.colors.GREEN,
    )
    typer.secho(
        f"✓ {users_removed} cuentas sin verificar y {soft_removed} filas borradas lógicamente "
        f"eliminadas (retención: {settings.UNVERIFIED_ACCOUNT_RETENTION_DAYS} / "
        f"{settings.SOFT_DELETE_RETENTION_DAYS} días; 0 = sin límite)",
        fg=typer.colors.GREEN,
    )


@db_app.command("history")
def db_history() -> None:
    """Muestra el historial de migraciones."""
    from alembic import command

    command.history(_alembic_config())


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
@app.command()
def secret(
    length: Annotated[int, typer.Option(min=32, max=256)] = 64,
    data_key: Annotated[
        bool, typer.Option("--data-key", help="Clave AES-256 para DATA_ENCRYPTION_KEY")
    ] = False,
) -> None:
    """Genera una SECRET_KEY (o AUDIT_HMAC_KEY) aleatoria; con --data-key, una clave de
    cifrado de datos (32 bytes en base64)."""
    typer.echo(_data_key() if data_key else secrets.token_urlsafe(length))


def _data_key() -> str:
    import base64

    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


@app.command("init-env")
def init_env(
    force: Annotated[bool, typer.Option(help="Sobrescribir .env existente")] = False,
    production: Annotated[bool, typer.Option(help="Plantilla con valores de producción")] = False,
) -> None:
    """Crea .env a partir de .env.example con una SECRET_KEY nueva."""
    base = project.root()
    target, example = base / ".env", base / ".env.example"
    if target.exists() and not force:
        _fail(".env ya existe (usa --force para regenerarlo)")
    text = example.read_text(encoding="utf-8")
    text = re.sub(r"^SECRET_KEY=.*$", f"SECRET_KEY={secrets.token_urlsafe(64)}", text, flags=re.M)
    text = re.sub(
        r"^POSTGRES_PASSWORD=.*$",
        f"POSTGRES_PASSWORD={secrets.token_urlsafe(24)}",
        text,
        flags=re.M,
    )
    # Hex: van dentro de una URL (redis://:clave@...) sin escapar nada.
    text = re.sub(
        r"^REDIS_PASSWORD=.*$", f"REDIS_PASSWORD={secrets.token_hex(24)}", text, flags=re.M
    )
    text = re.sub(
        r"^AUDIT_HMAC_KEY=.*$", f"AUDIT_HMAC_KEY={secrets.token_urlsafe(48)}", text, flags=re.M
    )
    text = re.sub(
        r"^DATA_ENCRYPTION_KEY=.*$", f"DATA_ENCRYPTION_KEY={_data_key()}", text, flags=re.M
    )
    if production:
        text = re.sub(r"^ENVIRONMENT=.*$", "ENVIRONMENT=production", text, flags=re.M)
        text = re.sub(r"^DEBUG=.*$", "DEBUG=false", text, flags=re.M)
        # Obliga a rellenarlo: con "*" la app se niega a arrancar en producción.
        text = re.sub(r"^ALLOWED_HOSTS=.*$", "ALLOWED_HOSTS=", text, flags=re.M)
    target.write_text(text, encoding="utf-8")
    target.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600: solo tu usuario puede leerlo
    typer.secho(
        "✓ .env creado con SECRET_KEY, AUDIT_HMAC_KEY y contraseñas nuevas (permisos 600)",
        fg=typer.colors.GREEN,
    )
    if production:
        typer.echo(
            "\nAntes de arrancar en producción, edita .env y rellena:\n"
            "  ALLOWED_HOSTS      tus dominios (p. ej. api.midominio.com)  [obligatorio]\n"
            "  CORS_ORIGINS       orígenes del frontend, si lo hay\n"
            "  TRUSTED_PROXIES    IP exacta del proxy inverso (docker compose usa el\n"
            "                     gateway de su red, 172.30.57.1); nunca '*' ni rangos amplios\n"
            "  DATABASE_URL       PostgreSQL, obligatorio (docker compose lo fija por ti)\n"
            "  RATE_LIMIT_STORAGE_URI  redis://... con varios workers (compose lo fija)\n"
            "  ALLOW_REGISTRATION ¿registro abierto al público? (por defecto true)\n"
            "  Correo (si usas verificación o recuperación de contraseña):\n"
            "    EMAIL_VERIFICATION / PASSWORD_RESET   off|optional|required / on|off\n"
            "    EMAIL_BACKEND=smtp, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD\n"
            "    EMAIL_FROM         remitente del dominio DEL CLIENTE (con SPF, DKIM y DMARC)\n"
            "    FRONTEND_URL       https://... del frontend (los enlaces van ahí)\n"
            "    MAIL_BRAND_*, MAIL_SUPPORT_EMAIL, MAIL_DEFAULT_LANGUAGE\n"
            "  Prueba el envío con: apigen email test tu@example.com\n"
            "Después: apigen check. Programa a diario `apigen db prune` (retención) y\n"
            "periódicamente `apigen users review` (revisión de accesos). Envía los logs JSON\n"
            "a un almacén externo y comprueba su integridad con `apigen audit verify`."
        )


@app.command()
def createsuperuser(
    email: Annotated[str | None, typer.Option(help="Email del administrador")] = None,
    promote: Annotated[bool, typer.Option(help="Si ya existe, convertirlo en admin")] = False,
) -> None:
    """Crea un usuario administrador (la contraseña se pide de forma oculta).

    Sin terminal interactiva (CI, scripts) pasa la contraseña en la variable de
    entorno APIGEN_SUPERUSER_PASSWORD.
    """
    if "APIGEN_SUPERUSER_PASSWORD" not in os.environ and not sys.stdin.isatty():
        _fail(
            "Sin terminal interactiva no puedo pedir la contraseña: define "
            "APIGEN_SUPERUSER_PASSWORD (y --email)."
        )
    os.chdir(project.root())
    sys.path.insert(0, str(Path.cwd()))
    email = (email or typer.prompt("Email")).strip().lower()
    asyncio.run(_createsuperuser(email, promote))


async def _createsuperuser(email: str, promote: bool) -> None:
    from pydantic import EmailStr, TypeAdapter
    from sqlmodel import select

    from app.core.permissions import Role
    from app.core.security import hash_password, password_problems
    from app.db.session import SessionFactory, engine
    from app.db.types import utcnow
    from app.models.user import User

    try:
        TypeAdapter(EmailStr).validate_python(email)
    except ValidationError as exc:
        # El motivo de email-validator (p. ej. dominio reservado como .test; UX-65).
        reason = exc.errors()[0].get("msg", "").removeprefix("value is not a valid email address: ")
        _fail(f"Email no válido: {reason}")
    async with SessionFactory() as session:
        user = (await session.exec(select(User).where(User.email == email))).first()
        if user and not promote:
            _fail("Ese usuario ya existe (usa --promote para hacerlo admin)")
        if user:
            user.role = Role.admin
            user.token_version += 1
        else:
            password = os.environ.get("APIGEN_SUPERUSER_PASSWORD") or getpass.getpass(
                "Contraseña: "
            )
            if "APIGEN_SUPERUSER_PASSWORD" not in os.environ and password != getpass.getpass(
                "Repite la contraseña: "
            ):
                _fail("Las contraseñas no coinciden")
            problems = password_problems(password, email, lang="es")
            if problems:
                _fail("Contraseña débil: " + "; ".join(problems))
            user = User(
                email=email,
                hashed_password=await hash_password(password),
                role=Role.admin,
                email_verified_at=utcnow(),  # nace verificado (REQ-F13)
            )
        session.add(user)
        await session.commit()
    await engine.dispose()
    typer.secho(f"✓ Administrador listo: {email}", fg=typer.colors.GREEN)


@app.command()
def check() -> None:
    """Valida la configuración y muestra un resumen de seguridad."""
    os.chdir(project.root())
    sys.path.insert(0, str(Path.cwd()))
    try:
        # La instancia del módulo: crear otra repetiría los avisos (p. ej. SECRET_KEY).
        from app.core.config import settings as s
    except Exception as exc:  # noqa: BLE001
        _fail(_clean(exc))
    ok, warn = typer.colors.GREEN, typer.colors.YELLOW
    rows = [
        ("Entorno", s.ENVIRONMENT.value, ok),
        (
            "Base de datos",
            s.DATABASE_URL.split("://", 1)[0],
            warn if s.is_sqlite and s.is_production else ok,
        ),
        (
            "JWT",
            f"{s.JWT_ALGORITHM}, access {s.ACCESS_TOKEN_EXPIRE_MINUTES} min, "
            f"refresh {s.REFRESH_TOKEN_EXPIRE_DAYS} d",
            ok,
        ),
        (
            "Rate limit",
            f"{'on' if s.RATE_LIMIT_ENABLED else 'OFF'} "
            f"({s.RATE_LIMIT_STORAGE_URI.split(':', 1)[0]}) default={s.RATE_LIMIT_DEFAULT}",
            ok if s.RATE_LIMIT_ENABLED else warn,
        ),
        (
            "Docs /docs",
            "activados" if s.docs_enabled else "desactivados",
            warn if s.docs_enabled and s.is_production else ok,
        ),
        (
            "CORS",
            ", ".join(s.CORS_ORIGINS)
            or ("localhost:* (desarrollo)" if s.ENVIRONMENT == "development" else "(ninguno)"),
            ok,
        ),
        ("Hosts", ", ".join(s.ALLOWED_HOSTS), warn if "*" in s.ALLOWED_HOSTS else ok),
        (
            "Proxies de confianza",
            ", ".join(s.TRUSTED_PROXIES) or "(ninguno)",
            warn if s.is_production and not s.TRUSTED_PROXIES else ok,
        ),
        ("Registro abierto", str(s.ALLOW_REGISTRATION), ok),
        *_email_rows(s, ok, warn),
        *_privacy_rows(s, ok, warn),
    ]
    for label, value, color in rows:
        typer.echo(f"  {label:<22}", nl=False)
        typer.secho(value, fg=color)
    worker_problems = _worker_problems()
    if worker_problems:
        _fail("Configuración del worker (el que envía los correos):\n  " + worker_problems)
    unverified = _unverified_warning(s)
    if unverified:
        typer.secho(f"  ! {unverified}", fg=warn)
    from app.email.render import check_templates

    errors, warnings = check_templates()
    for message in warnings:
        typer.secho(f"  ! plantillas: {message}", fg=warn)
    if errors:
        _fail("Plantillas de correo con errores:\n  " + "\n  ".join(errors))
    typer.secho("✓ Configuración válida", fg=ok)


def _worker_problems() -> str:
    """`check` valida también las reglas del rol worker (SMTP_HOST, TLS...): si no, el
    fallo aparecería al desplegar el worker (UX-73)."""
    from app.core.config import Settings

    try:
        Settings(PROCESS_ROLE="worker")
    except ValidationError as exc:
        return _clean(exc).replace("Configuración insegura:\n  - ", "").replace("\n  - ", "\n  ")
    return ""


def _unverified_warning(s) -> str:
    """Con EMAIL_VERIFICATION=required, avisa si hay usuarios sin verificar (UX-68)."""
    if s.email_verification != "required":
        return ""
    try:
        count = asyncio.run(_count_unverified())
    except Exception:  # noqa: BLE001  (sin BD accesible no se avisa)
        return ""
    if not count:
        return ""
    return (
        f"{count} usuario(s) sin verificar no podrán iniciar sesión con "
        "EMAIL_VERIFICATION=required hasta verificar su email. Si ya eran de confianza: "
        "apigen users verify --all-existing [--before AAAA-MM-DD]"
    )


async def _count_unverified() -> int:
    from sqlalchemy import func
    from sqlmodel import col, select

    from app.db.session import SessionFactory, engine
    from app.models.user import User

    try:
        async with SessionFactory() as session:
            query = select(func.count()).where(col(User.email_verified_at).is_(None))
            return (await session.exec(query)).one()
    finally:
        await engine.dispose()


@users_app.command("verify")
def users_verify(
    email: Annotated[str | None, typer.Option(help="Marcar un usuario concreto")] = None,
    all_existing: Annotated[
        bool, typer.Option("--all-existing", help="Marcar todos los que aún no lo están")
    ] = False,
    before: Annotated[
        str | None, typer.Option(help="Con --all-existing: solo los creados antes (AAAA-MM-DD)")
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="No pedir confirmación")] = False,
) -> None:
    """Marca emails como verificados (p. ej. al pasar de off/optional a required).

    Es un comando de operador (no hay endpoint de API para esto, REQ-F25) y queda en
    el log de auditoría (`admin.user.verify`)."""
    if bool(email) == all_existing:
        _fail("Indica --email o --all-existing (uno de los dos)")
    if before and not all_existing:
        _fail("--before solo se usa con --all-existing")
    cutoff = None
    if before:
        try:
            cutoff = date.fromisoformat(before)
        except ValueError:
            _fail("--before debe ser una fecha AAAA-MM-DD")
    _load_app_settings()
    target = email.strip().lower() if email else None
    if all_existing and not yes:
        scope = f"creados antes del {cutoff}" if cutoff else "todos los que faltan"
        typer.confirm(f"¿Marcar como verificados los usuarios sin verificar ({scope})?", abort=True)
    count = asyncio.run(_users_verify(target, cutoff))
    if target and not count:
        _fail(f"No hay ningún usuario sin verificar con el email {target}")
    typer.secho(f"✓ {count} usuario(s) marcados como verificados", fg=typer.colors.GREEN)


async def _users_verify(email: str | None, cutoff: date | None) -> int:
    from datetime import UTC, datetime

    from sqlalchemy import update
    from sqlmodel import col

    from app.core.audit import audit
    from app.core.logging import setup_logging
    from app.db.session import SessionFactory, engine
    from app.db.types import utcnow
    from app.models.user import User

    setup_logging()
    query = update(User).where(col(User.email_verified_at).is_(None))
    if email:
        query = query.where(col(User.email) == email)
    if cutoff:
        query = query.where(
            col(User.created_at) < datetime(cutoff.year, cutoff.month, cutoff.day, tzinfo=UTC)
        )
    try:
        async with SessionFactory() as session:
            result = await session.execute(query.values(email_verified_at=utcnow()))
            await session.commit()
    finally:
        await engine.dispose()
    audit(
        "admin.user.verify",
        actor="cli",
        scope="email" if email else "all_existing",
        before=cutoff.isoformat() if cutoff else None,
        count=result.rowcount,
    )
    return result.rowcount or 0


@users_app.command("review")
def users_review(
    inactive_days: Annotated[
        int, typer.Option(min=1, help="Días sin iniciar sesión para considerar inactiva")
    ] = 90,
    as_json: Annotated[bool, typer.Option("--json", help="Salida JSON (evidencia)")] = False,
) -> None:
    """Revisión periódica de accesos (SOC 2 CC6.2/CC6.3): administradores, cuentas
    inactivas, bloqueadas y sin verificar. Queda en el log de auditoría."""
    import json

    _load_app_settings()
    review = asyncio.run(_users_review(inactive_days))
    if as_json:
        typer.echo(json.dumps(review, indent=2, ensure_ascii=False, default=str))
        return
    typer.secho(f"Administradores ({len(review['admins'])})", bold=True)
    for admin in review["admins"]:
        state = "activo" if admin["is_active"] else "DESACTIVADO"
        last = admin["last_login_at"] or "nunca"
        typer.echo(f"  {admin['email']:<40} {state:<12} último login: {last}")
    typer.secho(f"\nInactivos más de {inactive_days} días ({len(review['inactive'])})", bold=True)
    for user in review["inactive"][:50]:
        typer.echo(f"  {user['email']:<40} {user['role']:<6} último login: {user['last_login_at']}")
    if len(review["inactive"]) > 50:
        typer.echo(f"  ... y {len(review['inactive']) - 50} más (usa --json)")
    typer.echo(f"\nBloqueados ahora: {review['locked']}  ·  sin verificar: {review['unverified']}")
    typer.echo(
        "Revisa que cada admin siga necesitando el rol; desactiva o degrada lo que sobre "
        "(PATCH /users/{id}) y conserva esta salida como evidencia."
    )


async def _users_review(inactive_days: int) -> dict:
    from datetime import timedelta

    from sqlalchemy import func, or_
    from sqlmodel import col, select

    from app.core.audit import audit
    from app.core.logging import setup_logging
    from app.core.permissions import Role
    from app.db.session import SessionFactory, engine
    from app.db.types import utcnow
    from app.models.user import User

    setup_logging()
    now = utcnow()
    cutoff = now - timedelta(days=inactive_days)
    fields = ("email", "role", "is_active", "created_at", "last_login_at")
    try:
        async with SessionFactory() as session:
            admins = (await session.exec(select(User).where(col(User.role) == Role.admin))).all()
            inactive = (
                await session.exec(
                    select(User)
                    .where(
                        col(User.is_active).is_(True),
                        or_(
                            col(User.last_login_at) < cutoff,
                            col(User.last_login_at).is_(None) & (col(User.created_at) < cutoff),
                        ),
                    )
                    .order_by(col(User.last_login_at))
                )
            ).all()
            locked = (
                await session.exec(select(func.count()).where(col(User.locked_until) > now))
            ).one()
            unverified = (
                await session.exec(
                    select(func.count()).where(col(User.email_verified_at).is_(None))
                )
            ).one()
    finally:
        await engine.dispose()
    review = {
        "generated_at": now.isoformat(),
        "inactive_days": inactive_days,
        "admins": [{f: getattr(u, f) for f in fields} for u in admins],
        "inactive": [{f: getattr(u, f) for f in fields} for u in inactive],
        "locked": locked,
        "unverified": unverified,
    }
    audit(
        "admin.access_review",
        actor="cli",
        admins=len(admins),
        inactive=len(inactive),
        inactive_days=inactive_days,
    )
    return review


@users_app.command("export")
def users_export(
    email: Annotated[str, typer.Option(help="Usuario cuyos datos se exportan")],
    out: Annotated[Path, typer.Option(help="Fichero JSON de salida")] = Path("export.json"),
) -> None:
    """Solicitud de acceso atendida por el operador (ISO 27701 7.3.9), p. ej. si el
    titular no puede iniciar sesión: el mismo JSON que GET /users/me/export. Verifica
    antes su identidad. Queda en el log de auditoría (`privacy.export`, actor=cli)."""
    import json

    _load_app_settings()
    data = asyncio.run(_users_export(email.strip().lower()))
    if data is None:
        _fail(f"No hay ningún usuario con el email {email}")
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    out.chmod(stat.S_IRUSR | stat.S_IWUSR)  # contiene datos personales: 600
    typer.secho(f"✓ Datos exportados en {out} (permisos 600)", fg=typer.colors.GREEN)


async def _users_export(email: str) -> dict | None:
    from sqlmodel import select

    from app.core.audit import audit
    from app.core.logging import setup_logging
    from app.db.session import SessionFactory, engine
    from app.models.user import User
    from app.services.privacy import export_user_data

    setup_logging()
    try:
        async with SessionFactory() as session:
            user = (await session.exec(select(User).where(User.email == email))).first()
            if user is None:
                return None
            data = await export_user_data(session, user)
    finally:
        await engine.dispose()
    audit("privacy.export", actor="cli", user_id=user.id)
    return data


@users_app.command("revoke-sessions")
def users_revoke_sessions(
    email: Annotated[str | None, typer.Option(help="Solo las de este usuario")] = None,
    all_users: Annotated[bool, typer.Option("--all", help="Las de TODOS los usuarios")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="No pedir confirmación")] = False,
) -> None:
    """Respuesta a incidentes (SOC 2 CC7.4): invalida al instante los access tokens y
    revoca los refresh tokens de un usuario o de todos (todos deberán iniciar sesión).
    Tras una filtración de SECRET_KEY, rótala además (JWT_PREVIOUS_SECRET_KEYS vacío)."""
    if bool(email) == all_users:
        _fail("Indica --email o --all (uno de los dos)")
    _load_app_settings()
    if all_users and not yes:
        typer.confirm("¿Cerrar las sesiones de TODOS los usuarios?", abort=True)
    count = asyncio.run(_revoke_sessions(email.strip().lower() if email else None))
    if email and not count:
        _fail(f"No hay ningún usuario con el email {email}")
    typer.secho(f"✓ Sesiones cerradas: {count} usuario(s)", fg=typer.colors.GREEN)


async def _revoke_sessions(email: str | None) -> int:
    from sqlalchemy import update
    from sqlmodel import col, select

    from app.core.audit import audit
    from app.core.logging import setup_logging
    from app.db.session import SessionFactory, engine
    from app.db.types import utcnow
    from app.models.refresh_token import RefreshToken
    from app.models.user import User

    setup_logging()
    try:
        async with SessionFactory() as session:
            # token_version + 1 invalida los access tokens ya emitidos al instante.
            query = update(User).values(token_version=col(User.token_version) + 1)
            tokens = update(RefreshToken).where(col(RefreshToken.revoked_at).is_(None))
            if email:
                user_id = (await session.exec(select(User.id).where(User.email == email))).first()
                if user_id is None:
                    return 0
                query = query.where(col(User.id) == user_id)
                tokens = tokens.where(col(RefreshToken.user_id) == user_id)
            count = (await session.execute(query)).rowcount or 0
            await session.execute(tokens.values(revoked_at=utcnow()))
            await session.commit()
    finally:
        await engine.dispose()
    audit("admin.sessions.revoke", actor="cli", scope="user" if email else "all", count=count)
    return count


@privacy_app.command("inventory")
def privacy_inventory(
    out: Annotated[Path, typer.Option(help="Fichero de salida")] = INVENTORY,
    check: Annotated[
        bool, typer.Option("--check", help="No escribe: falla si no está al día (CI)")
    ] = False,
) -> None:
    """Inventario de datos personales (registro de actividades, ISO 27701 7.2.8) a
    partir de los recursos y su clasificación `pii`/`sensitive`. Conserva lo que
    completes fuera de los marcadores (responsable, base legal, encargados...)."""
    base = project.root()
    os.chdir(base)
    path = out if out.is_absolute() else base / out
    try:
        current, updated = _inventory(base, path)
        specs = list(project.load_all_specs(base).values())
    except (SpecError, ValidationError) as exc:
        _fail(str(exc))
    if check:
        if current != updated:
            _fail(f"{out} no está al día: ejecuta `apigen privacy inventory`")
        typer.secho(f"✓ {out} al día", fg=typer.colors.GREEN)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8")
    verb = "actualizado" if current else "creado"
    typer.secho(f"✓ {out} {verb} ({len(specs)} recurso(s))", fg=typer.colors.GREEN)
    if current is None:
        typer.echo("  Completa la tabla «A completar» (responsable, base legal, encargados).")
    for spec in specs:
        for warning in spec.warnings():
            if "pii" in warning or "personales" in warning:
                typer.secho(f"! {warning}", fg=typer.colors.YELLOW, err=True)


@audit_app.command("verify")
def audit_verify(
    files: Annotated[
        list[Path] | None,
        typer.Argument(help="Logs JSON en orden (varios si están rotados); sin nada, stdin"),
    ] = None,
) -> None:
    """Comprueba la cadena del log de auditoría: detecta eventos alterados, insertados
    o borrados del medio (necesita los logs en JSON y la misma AUDIT_HMAC_KEY)."""
    _load_app_settings()
    from app.core.audit import verify_lines

    def lines():
        if not files:
            yield from sys.stdin
            return
        for path in files:
            if not path.is_file():
                _fail(f"no existe {path}")
            with path.open(encoding="utf-8", errors="replace") as handle:
                yield from handle

    report = verify_lines(lines())
    for note in report.notes[:20]:
        typer.secho(f"  · {note}", fg=typer.colors.YELLOW)
    for error in report.errors[:50]:
        typer.secho(f"  ✗ {error}", fg=typer.colors.RED, err=True)
    if not report.events:
        _fail("no hay eventos de auditoría encadenados (¿LOG_JSON=true?)")
    if not report.ok:
        _fail(f"cadena rota: {len(report.errors)} problema(s) en {report.events} eventos")
    typer.secho(
        f"✓ {report.events} eventos íntegros en {report.streams} flujo(s)", fg=typer.colors.GREEN
    )


def _privacy_rows(s, ok: str, warn: str) -> list[tuple[str, str, str]]:
    """Filas de auditoría, privacidad y retención de `apigen check` (SOC 2 / ISO 27701)."""
    keyed = bool(s.AUDIT_HMAC_KEY.get_secret_value())
    audit_text = ("HMAC" if keyed else "sin clave (AUDIT_HMAC_KEY)") + (
        ", JSON" if s.log_json else ", texto (no verificable)"
    )
    unverified = s.UNVERIFIED_ACCOUNT_RETENTION_DAYS if s.email_verification == "required" else 0
    return [
        ("Auditoría", audit_text, ok if (keyed and s.log_json) or not s.is_production else warn),
        ("IP en log de acceso", s.ACCESS_LOG_IP, ok),
        (
            "Derechos interesado",
            "exportar + borrar cuenta" if s.ALLOW_SELF_DELETION else "exportar (borrado: admin)",
            ok,
        ),
        (
            "Retención",
            f"sesiones {s.LOGIN_FAMILIAR_DAYS} d, trabajos {s.JOBS_RETENTION_DAYS} d, "
            f"soft delete {s.SOFT_DELETE_RETENTION_DAYS or '∞'} d, "
            f"sin verificar {unverified or '-'} d",
            warn if not s.SOFT_DELETE_RETENTION_DAYS else ok,
        ),
    ]


def _email_rows(s, ok: str, warn: str) -> list[tuple[str, str, str]]:
    """Filas de correo de `apigen check` (sin credenciales)."""
    from urllib.parse import urlsplit

    backend = s.email_backend or "(sin configurar)"
    detail = backend
    if backend == "smtp":
        detail = f"smtp ({s.SMTP_HOST or '?'}:{s.SMTP_PORT}, {s.SMTP_SECURITY.upper()})"
    elif backend == "file":
        detail = f"file ({s.EMAIL_FILE_DIR})"
    dev_backend = backend in {"console", "file", "memory", "(sin configurar)"}
    sender = f'"{s.EMAIL_FROM_NAME or s.mail_brand_name}" <{s.EMAIL_FROM}>' if s.EMAIL_FROM else "-"
    front = urlsplit(s.FRONTEND_URL) if s.FRONTEND_URL else None
    in_cors = front is not None and f"{front.scheme}://{front.netloc}" in s.CORS_ORIGINS
    if front is not None and not s.CORS_ORIGINS and s.ENVIRONMENT == "development":
        # En desarrollo, sin CORS_ORIGINS, se permite cualquier localhost (UX-74).
        in_cors = (front.hostname or "") in {"localhost", "127.0.0.1", "::1"}
    rows = [
        ("Correo", f"{detail} (envío: {s.email_delivery})", warn if dev_backend else ok),
        ("Remitente", sender, ok),
        ("Verificación email", s.email_verification, ok),
        ("Recuperar contraseña", "on" if s.password_reset_enabled else "off", ok),
        (
            "Frontend (enlaces)",
            (s.FRONTEND_URL or "-") + ("" if in_cors or not front else "  (no está en CORS)"),
            ok if in_cors or not front else warn,
        ),
    ]
    if s.email_verification == "required" and not s.ALLOW_REGISTRATION:
        rows.append(("", "verificación required con ALLOW_REGISTRATION=false", warn))
    return rows


@app.command()
def worker(
    concurrency: Annotated[
        int | None, typer.Option(help="Trabajos a la vez (JOBS_CONCURRENCY)")
    ] = None,
    once: Annotated[bool, typer.Option(help="Procesar lo pendiente y salir")] = False,
) -> None:
    """Worker de tareas en segundo plano (proceso aparte de la API)."""
    base = project.root()
    cmd = [sys.executable, "-m", "app.tasks.worker"]
    if concurrency:
        cmd += ["--concurrency", str(concurrency)]
    if once:
        cmd.append("--once")
    # El worker no necesita la clave de los JWT (SEC-38): no se le exige.
    env = {**os.environ, "PROCESS_ROLE": "worker"}
    raise typer.Exit(subprocess.call(cmd, cwd=base, env=env))  # noqa: S603


@app.command()
def run(
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option()] = 8000,
    reload: Annotated[bool, typer.Option(help="Recargar al cambiar código")] = True,
) -> None:
    """Servidor de desarrollo."""
    _uvicorn(["--host", host, "--port", str(port), *(["--reload"] if reload else [])])


@app.command()
def serve(
    host: Annotated[str, typer.Option()] = "0.0.0.0",  # noqa: S104
    port: Annotated[int, typer.Option()] = 8000,
    workers: Annotated[int, typer.Option(help="Procesos (≈ nº de CPUs)")] = os.cpu_count() or 2,
) -> None:
    """Servidor de producción (varios workers, uvloop + httptools)."""
    _uvicorn(
        [
            "--host",
            host,
            "--port",
            str(port),
            "--workers",
            str(workers),
            "--no-access-log",
            "--timeout-keep-alive",
            "5",
            "--timeout-graceful-shutdown",
            "20",
        ]
    )


# ---------------------------------------------------------------------------
# Correo
# ---------------------------------------------------------------------------
_EMAIL_HINTS = {
    "smtp_auth_failed": "autenticación SMTP rechazada: revisa SMTP_USER y SMTP_PASSWORD "
    "(algunos proveedores usan 'apikey' como usuario)",
    "smtp_connection": "no se pudo conectar a {host}:{port} (timeout o conexión rechazada): "
    "revisa SMTP_HOST/SMTP_PORT y que tu hosting permita salir por ese puerto "
    "(si bloquea 587/465, prueba el 2525 de tu proveedor)",
    "smtp_tls_error": "falló el TLS: el puerto 465 requiere SMTP_SECURITY=ssl y el 587, starttls",
    "smtp_tls_certificate": "el certificado del servidor no es válido para {host}: usa el host "
    "exacto que indica tu proveedor",
    "smtp_starttls_unavailable": "el servidor no ofrece STARTTLS: usa SMTP_SECURITY=ssl "
    "(puerto 465); `none` solo para Mailpit en local",
    "smtp_recipient_refused": "el servidor rechazó el destinatario (¿dirección válida? "
    "¿remitente verificado en el proveedor?)",
    "smtp_not_configured": "falta SMTP_HOST",
    "smtp_host_not_found": "no se encuentra el servidor {host}: revisa SMTP_HOST",
    "email_disabled": "no hay backend de correo (EMAIL_BACKEND vacío en producción o disabled)",
}


def _email_hint(code: str, s) -> str:
    if code in _EMAIL_HINTS:
        return _EMAIL_HINTS[code].format(host=s.SMTP_HOST, port=s.SMTP_PORT)
    if code.startswith("smtp_5"):
        return (
            f"el servidor rechazó el mensaje ({code[5:]}): suele ser un remitente (EMAIL_FROM) "
            "o dominio no verificado en tu proveedor"
        )
    if code.startswith("smtp_4"):
        return f"rechazo temporal del servidor ({code[5:]}): inténtalo más tarde"
    return code


def _load_app_settings():
    os.chdir(project.root())
    sys.path.insert(0, str(Path.cwd()))
    try:
        from app.core.config import settings as s
    except Exception as exc:  # noqa: BLE001
        _fail(_clean(exc))
    return s


@email_app.command("test")
def email_test(
    to: Annotated[str, typer.Argument(help="Destinatario de la prueba")],
    template: Annotated[str, typer.Option(help="Plantilla a enviar")] = "test",
    lang: Annotated[str | None, typer.Option(help="Idioma (defecto MAIL_DEFAULT_LANGUAGE)")] = None,
) -> None:
    """Envía YA un correo de prueba (sin la cola) con la configuración actual."""
    s = _load_app_settings()
    from pydantic import EmailStr, TypeAdapter

    try:
        TypeAdapter(EmailStr).validate_python(to)
    except ValidationError:
        _fail(f"{to!r} no es una dirección de correo válida")
    asyncio.run(_email_test(s, to, template, lang))


async def _email_test(s, to: str, template: str, lang: str | None) -> None:
    from app.email.backends import EmailError, get_backend
    from app.email.message import EmailMessage
    from app.email.render import TemplateError, render, resolve_language, sample_context

    backend = get_backend()
    if backend.name == "smtp" and s.SMTP_PORT == 465 and s.SMTP_SECURITY == "starttls":
        # Se sabe antes de conectar y esperar al timeout (UX-72).
        _fail("smtp: el puerto 465 usa TLS directo: pon SMTP_SECURITY=ssl (o usa el 587)")
    language = resolve_language(lang)
    try:
        rendered = render(template, language, sample_context(template, language))
        await backend.send(
            EmailMessage(to=(to,), subject=rendered.subject, text=rendered.text, html=rendered.html)
        )
    except TemplateError as exc:
        _fail(f"plantilla: {exc}")
    except EmailError as exc:
        _fail(f"{backend.name}: {_email_hint(exc.code, s)}")
    except ValueError:
        _fail("cabecera no válida: revisa EMAIL_FROM, EMAIL_FROM_NAME y EMAIL_REPLY_TO")
    if backend.name in {"console", "memory"}:
        typer.secho(
            f"✓ Con EMAIL_BACKEND={backend.name} no sale ningún correo: mira el log", fg="yellow"
        )
    elif backend.name == "file":
        path = getattr(backend, "last_path", None) or s.EMAIL_FILE_DIR
        typer.secho(f"✓ Guardado en {path} (y el .eml y .html al lado)", fg=typer.colors.GREEN)
    else:
        typer.secho(f"✓ Enviado a {to} con {backend.name}", fg=typer.colors.GREEN)


@email_app.command("preview")
def email_preview(
    template: Annotated[str | None, typer.Argument(help="Plantilla (defecto: todas)")] = None,
    lang: Annotated[str | None, typer.Option(help="Idioma (defecto: todos)")] = None,
    out: Annotated[Path, typer.Option(help="Carpeta de salida")] = Path("var/mail/preview"),
) -> None:
    """Genera el HTML y el texto de las plantillas con datos de ejemplo."""
    s = _load_app_settings()
    from app.email.render import BUILTIN, TemplateError, render, sample_context

    names = [template] if template else list(BUILTIN)
    languages = [lang] if lang else s.MAIL_LANGUAGES
    out.mkdir(parents=True, exist_ok=True)
    for name in names:
        for language in languages:
            try:
                rendered = render(name, language, sample_context(name, language))
            except TemplateError as exc:
                _fail(str(exc))
            stem = out / f"{name}.{rendered.language}"
            Path(f"{stem}.txt").write_text(
                f"Subject: {rendered.subject}\n\n{rendered.text}", encoding="utf-8"
            )
            if rendered.html:
                Path(f"{stem}.html").write_text(rendered.html, encoding="utf-8")
            typer.echo(f"  {stem}.html / .txt")
    typer.secho(f"✓ Vista previa en {out}/ (ábrela en el navegador)", fg=typer.colors.GREEN)


@email_app.command("eject")
def email_eject(
    template: Annotated[
        str | None, typer.Argument(help="Plantilla o 'layout' (defecto: todas)")
    ] = None,
    lang: Annotated[str | None, typer.Option(help="Idioma (defecto: todos los de serie)")] = None,
    force: Annotated[bool, typer.Option(help="Sobrescribir las que ya existan")] = False,
) -> None:
    """Copia plantillas de serie a EMAIL_TEMPLATES_DIR para personalizarlas."""
    import shutil

    _load_app_settings()
    from app.email.render import BUILTIN, BUILTIN_DIR, templates_dir

    target = templates_dir()
    files: list[Path] = []
    if template in (None, "layout"):
        files += [BUILTIN_DIR / n for n in ("_layout.html", "_button.html", "_footer.txt")]
    if template != "layout":
        if template is not None and template not in BUILTIN:
            _fail(f"plantilla desconocida: {template} (de serie: {', '.join(BUILTIN)})")
        for folder in sorted(p for p in BUILTIN_DIR.iterdir() if p.is_dir()):
            if lang and folder.name != lang:
                continue
            for name in [template] if template else BUILTIN:
                files += sorted(folder.glob(f"{name}.*"))
    for src in files:
        dst = target / src.relative_to(BUILTIN_DIR)
        if dst.exists() and not force:
            typer.echo(f"  = {dst} (ya existe)")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        typer.echo(f"  + {dst}")
    typer.secho(f"✓ Edita las copias en {target}/ (ganan a las de serie)", fg=typer.colors.GREEN)


def _uvicorn(args: list[str]) -> None:
    base = project.root()
    # --no-proxy-headers: X-Forwarded-For solo se acepta desde TRUSTED_PROXIES
    # (lo gestiona la app); uvicorn por defecto confía en 127.0.0.1.
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--no-server-header",
        "--no-proxy-headers",
        *args,
    ]
    raise typer.Exit(subprocess.call(cmd, cwd=base))  # noqa: S603


def _clean(exc: Exception) -> str:
    text = str(exc)
    text = re.sub(r"\n\s+For further information visit.*", "", text)
    # Quita el ruido de pydantic: "[type=value_error, input_value={...}, input_type=dict]".
    text = re.sub(r"\s*\[type=[^\]]*\]", "", text)
    text = re.sub(r"^\d+ validation errors? for \w+\n\s*", "", text)
    return text.replace("Value error, ", "")


if __name__ == "__main__":
    app()
