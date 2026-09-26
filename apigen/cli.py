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
app.add_typer(db_app, name="db")


def _fail(message: str) -> None:
    typer.secho(f"✗ {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


def _refresh_graph(base) -> None:
    """Mantiene al día graphify-out/ tras cambiar código generado."""
    message = project.refresh_graph(base)
    if message:
        ok = message.startswith("grafo actualizado")
        typer.secho(f"  {message}", fg=None if ok else typer.colors.YELLOW)


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
    only: Annotated[list[str] | None, typer.Option(help="Generar solo estos recursos")] = None,
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
        specs = [s for s in specs if s.name in only]
        if not specs:
            _fail("Ningún recurso coincide con --only")
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
    """Borra refresh tokens de sesiones muertas con más de LOGIN_FAMILIAR_DAYS días
    (y con ellos la IP guardada) y trabajos terminados con más de JOBS_RETENTION_DAYS.
    Prográmalo a diario (cron, CronJob...)."""
    os.chdir(project.root())
    sys.path.insert(0, str(Path.cwd()))
    asyncio.run(_prune())


async def _prune() -> None:
    from app.core.config import settings
    from app.db.session import SessionFactory, engine
    from app.services.auth import prune_refresh_tokens
    from app.tasks.queue import prune_jobs

    async with SessionFactory() as session:
        removed = await prune_refresh_tokens(session)
    jobs_removed = await prune_jobs()
    await engine.dispose()
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


@db_app.command("history")
def db_history() -> None:
    """Muestra el historial de migraciones."""
    from alembic import command

    command.history(_alembic_config())


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
@app.command()
def secret(length: Annotated[int, typer.Option(min=32, max=256)] = 64) -> None:
    """Genera una SECRET_KEY aleatoria."""
    typer.echo(secrets.token_urlsafe(length))


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
    if production:
        text = re.sub(r"^ENVIRONMENT=.*$", "ENVIRONMENT=production", text, flags=re.M)
        text = re.sub(r"^DEBUG=.*$", "DEBUG=false", text, flags=re.M)
        # Obliga a rellenarlo: con "*" la app se niega a arrancar en producción.
        text = re.sub(r"^ALLOWED_HOSTS=.*$", "ALLOWED_HOSTS=", text, flags=re.M)
    target.write_text(text, encoding="utf-8")
    target.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600: solo tu usuario puede leerlo
    typer.secho("✓ .env creado con una SECRET_KEY nueva (permisos 600)", fg=typer.colors.GREEN)
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
            "Después: apigen check. Programa `apigen db prune` a diario (retención de IPs)."
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
    from app.models.user import User

    try:
        TypeAdapter(EmailStr).validate_python(email)
    except ValueError:
        _fail("Email no válido")
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
            user = User(email=email, hashed_password=await hash_password(password), role=Role.admin)
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
    ]
    for label, value, color in rows:
        typer.echo(f"  {label:<22}", nl=False)
        typer.secho(value, fg=color)
    typer.secho("✓ Configuración válida", fg=ok)


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
    raise typer.Exit(subprocess.call(cmd, cwd=base))  # noqa: S603


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
