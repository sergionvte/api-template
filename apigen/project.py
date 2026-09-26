"""Operaciones sobre el proyecto: escribir ficheros, registrar/desregistrar recursos."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from apigen.codegen import (
    Rendered,
    ensure_user_module,
    hooks_module,
    render_resource,
    tasks_module,
)
from apigen.spec import (
    VERSION_NAME,
    ResourceSpec,
    SpecError,
    load_specs,
    spec_to_yaml,
    validate_references,
)

RESOURCES_DIR = "resources"
GRAPH_FILE = Path("graphify-out") / "graph.json"


def root() -> Path:
    """Raíz del proyecto (el directorio que contiene app/ y pyproject.toml)."""
    here = Path.cwd()
    for candidate in (here, *here.parents):
        if (candidate / "app" / "main.py").exists() and (candidate / "pyproject.toml").exists():
            return candidate
    raise SpecError(
        "No encuentro la raíz del proyecto (app/main.py). Ejecuta apigen desde el repo."
    )


# --- marcadores ----------------------------------------------------------------
def insert_before_marker(path: Path, marker: str, line: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if line in text.splitlines():
        return False
    token = f"# [apigen:{marker}]"
    if token not in text:
        raise SpecError(f"{path}: falta el marcador '{token}'")
    lines = text.splitlines(keepends=True)
    for i, current in enumerate(lines):
        if current.strip() == token:
            lines.insert(i, line + "\n")
            break
    path.write_text("".join(lines), encoding="utf-8")
    return True


def remove_line(path: Path, line: str) -> bool:
    if not path.exists():
        return False
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [current for current in lines if current.rstrip("\n") != line]
    if len(kept) != len(lines):
        path.write_text("".join(kept), encoding="utf-8")
        return True
    return False


def model_import(spec: ResourceSpec) -> str:
    return f"from app.models.{spec.name} import {spec.class_name}  # noqa: F401"


def router_lines(spec: ResourceSpec, version: str) -> tuple[str, str]:
    return (
        f"from app.api.{version}.endpoints import {spec.plural}",
        f"api_router.include_router({spec.plural}.router)",
    )


# --- specs ---------------------------------------------------------------------
def specs_dir(base: Path) -> Path:
    return base / RESOURCES_DIR


def load_all_specs(base: Path) -> dict[str, ResourceSpec]:
    directory = specs_dir(base)
    if not directory.exists():
        return {}
    return {s.name: s for s in load_specs(directory)}


def save_spec(base: Path, spec: ResourceSpec) -> Path:
    directory = specs_dir(base)
    directory.mkdir(exist_ok=True)
    path = directory / f"{spec.name}.yaml"
    path.write_text(
        f"# Especificación de '{spec.name}'. Tras editarla ejecuta:\n"
        f"#   apigen generate --force --only {spec.name}\n" + spec_to_yaml(spec),
        encoding="utf-8",
    )
    return path


def existing_versions(base: Path) -> list[str]:
    api = base / "app" / "api"
    return sorted(
        (p.name for p in api.iterdir() if p.is_dir() and re.fullmatch(r"v\d+", p.name)),
        key=lambda v: int(v[1:]),
    )


_VERSION_CALL = re.compile(r'APIVersion\(\s*name="(v\d+)"[^)]*\)')


def version_info(base: Path) -> dict[str, dict[str, str | bool | None]]:
    """Estado de cada versión registrada en app/api/versions.py."""
    text = (base / "app/api/versions.py").read_text(encoding="utf-8")
    info: dict[str, dict[str, str | bool | None]] = {}
    # Una llamada por versión, en una línea o repartida en varias (tras `ruff format`).
    for call in _VERSION_CALL.finditer(text):
        line = call.group(0)
        sunset = re.search(r'sunset="([^"]+)"', line)
        since = re.search(r'deprecated_since="([^"]+)"', line)
        info[call.group(1)] = {
            "deprecated": "deprecated=True" in line,
            "sunset": sunset.group(1) if sunset else None,
            "since": since.group(1) if since else None,
        }
    return info


def default_version(base: Path) -> str:
    """Versión para recursos nuevos: la más alta que no esté deprecada."""
    versions = existing_versions(base)
    info = version_info(base)
    active = [v for v in versions if not info.get(v, {}).get("deprecated")]
    return (active or versions or ["v1"])[-1]


# --- generación -------------------------------------------------------------------
def generate(
    base: Path,
    specs: list[ResourceSpec],
    *,
    force: bool = False,
    dry_run: bool = False,
    with_tests: bool = True,
    save_specs: bool = True,
) -> list[str]:
    """Genera y registra recursos. Devuelve un log de acciones."""
    known = load_all_specs(base)
    for spec in specs:
        known[spec.name] = spec
    validate_references(list(known.values()))
    versions = set(existing_versions(base))
    log: list[str] = []

    rendered: list[Rendered] = []
    for spec in specs:
        missing = [v for v in spec.versions if v not in versions]
        if missing:
            raise SpecError(
                f"{spec.name}: la(s) versión(es) {', '.join(missing)} no existen. "
                f"Créalas con: apigen version add {missing[0]}"
            )
        files = render_resource(base, spec, known, with_tests=with_tests)
        if not force:
            existing = [f.path for f in files if f.path.exists()]
            if existing:
                rel = "\n  ".join(str(p.relative_to(base)) for p in existing)
                raise SpecError(
                    f"{spec.name}: ya existen estos ficheros (usa --force para sobrescribir, "
                    f"perderás cambios manuales):\n  {rel}"
                )
        rendered.extend(files)

    if dry_run:
        preview = [f"[dry-run] escribiría {f.path.relative_to(base)}" for f in rendered]
        for spec in specs:
            for module in (hooks_module(spec), tasks_module(spec)):
                if module and not (base / module[0]).exists():
                    preview.append(f"[dry-run] crearía {module[0]} (tu código)")
        return preview

    for file in rendered:
        file.path.parent.mkdir(parents=True, exist_ok=True)
        init = file.path.parent / "__init__.py"
        if not init.exists():
            init.touch()
        file.path.write_text(file.content, encoding="utf-8")
        log.append(f"escrito    {file.path.relative_to(base)}")

    for spec in specs:
        if insert_before_marker(base / "app/models/__init__.py", "models", model_import(spec)):
            log.append(f"registrado modelo {spec.class_name}")
        for version in spec.versions:
            router_file = base / "app/api" / version / "router.py"
            imp, inc = router_lines(spec, version)
            insert_before_marker(router_file, "imports", imp)
            if insert_before_marker(router_file, "routers", inc):
                log.append(f"registrado router /{version}/{spec.plural}")
        if save_specs:
            path = save_spec(base, spec)
            log.append(f"spec       {path.relative_to(base)}")

    # Módulos del usuario: se crean una vez y NUNCA se sobrescriben (ni con --force).
    created: list[Path] = []
    for spec in specs:
        for module in (hooks_module(spec), tasks_module(spec)):
            if module is None:
                continue
            rel, header, stubs = module
            state, added = ensure_user_module(base / rel, header, stubs)
            if state == "created":
                created.append(base / rel)
                log.append(f"creado     {rel} (tu código: apigen no lo sobrescribe)")
            elif state == "appended":
                log.append(f"añadido    {rel}: {', '.join(added)} (tu código queda intacto)")
            elif state == "unparseable":
                log.append(f"AVISO      {rel} tiene errores de sintaxis: no se ha tocado")
        if tasks_module(spec) is not None and insert_before_marker(
            base / "app/tasks/__init__.py", "tasks", task_import(spec)
        ):
            log.append(f"registradas tareas de {spec.name} (apigen worker)")

    format_files(base, [f.path for f in rendered] + created)
    return log


def task_import(spec: ResourceSpec) -> str:
    return f"from app.tasks.resources import {spec.name}  # noqa: F401"


def dependents(base: Path, name: str) -> list[str]:
    """Campos de otros recursos que apuntan (fk) a `name`. Falla si no existe."""
    known = load_all_specs(base)
    if name not in known:
        raise SpecError(f"No existe resources/{name}.yaml")
    return [
        f"{other.name}.{fname}"
        for other in known.values()
        if other.name != name
        for fname, f in other.fields.items()
        if f.type == "fk" and f.to == name
    ]


def remove(base: Path, name: str, *, keep_spec: bool = False, force: bool = False) -> list[str]:
    known = load_all_specs(base)
    spec = known.get(name)
    if spec is None:
        raise SpecError(f"No existe resources/{name}.yaml")
    refs = dependents(base, name)
    if refs and not force:
        raise SpecError(f"Otros recursos apuntan a '{name}': {', '.join(refs)} (usa --force)")

    log: list[str] = []
    paths = [base / "app/models" / f"{spec.name}.py", base / "app/schemas" / f"{spec.name}.py"]
    for version in existing_versions(base):
        paths.append(base / "app/api" / version / "endpoints" / f"{spec.plural}.py")
        paths.append(base / "tests/api" / version / f"test_{spec.plural}.py")
        imp, inc = router_lines(spec, version)
        router_file = base / "app/api" / version / "router.py"
        remove_line(router_file, imp)
        if remove_line(router_file, inc):
            log.append(f"desregistrado router /{version}/{spec.plural}")
    if remove_line(base / "app/models/__init__.py", model_import(spec)):
        log.append(f"desregistrado modelo {spec.class_name}")
    # El worker deja de importar sus tareas (su modelo ya no existe).
    if remove_line(base / "app/tasks/__init__.py", task_import(spec)):
        log.append(f"desregistradas tareas de {spec.name}")
    for rel in (f"app/hooks/{spec.name}.py", f"app/tasks/resources/{spec.name}.py"):
        if (base / rel).exists():
            log.append(f"conservado {rel} (tu código; bórralo a mano si ya no lo quieres)")
    if not keep_spec:
        paths.append(specs_dir(base) / f"{spec.name}.yaml")
    for path in paths:
        if path.exists():
            path.unlink()
            log.append(f"borrado    {path.relative_to(base)}")
    return log


def find_ruff(base: Path) -> Path | None:
    """ruff del PATH, del .venv del proyecto o junto al intérprete que ejecuta apigen
    (p. ej. `.venv/bin/apigen` sin activar el entorno: UX-45)."""
    candidates = (
        shutil.which("ruff"),
        base / ".venv" / "bin" / "ruff",
        Path(sys.executable).parent / "ruff",
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def format_files(base: Path, paths: list[Path]) -> bool:
    """Deja el código generado limpio para `ruff check` (UX-45): quita imports sin uso
    o duplicados, los ordena y formatea (parte las líneas largas). ruff no es
    obligatorio: sin él no se hace nada y devuelve False."""
    ruff = find_ruff(base)
    targets = [str(p) for p in paths if p.suffix == ".py" and p.exists()]
    if ruff is None or not targets:
        return False
    for args in (
        ["check", "--fix", "--quiet", "--select", "I,F401,F811", "--exit-zero"],
        ["format", "--quiet"],
    ):
        subprocess.run(  # noqa: S603
            [str(ruff), *args, *targets], cwd=base, check=False, capture_output=True, timeout=60
        )
    return True


# --- versiones ------------------------------------------------------------------
def add_version(base: Path, new: str, source: str) -> list[str]:
    # Ambos nombres acaban en rutas y en reemplazos de texto: solo `v<n>`.
    for value in (new, source):
        if not VERSION_NAME.match(value):
            raise SpecError(f"Versión no válida: {value!r} (formato v1, v2, ...)")
    api = base / "app" / "api"
    src, dst = api / source, api / new
    if not src.exists():
        raise SpecError(f"La versión origen {source} no existe")
    if dst.exists():
        raise SpecError(f"La versión {new} ya existe")
    log: list[str] = []
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    for py_file in dst.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        py_file.write_text(text.replace(f"app.api.{source}.", f"app.api.{new}."), encoding="utf-8")
    log.append(f"copiado    app/api/{source} -> app/api/{new}")

    tests_src, tests_dst = base / "tests/api" / source, base / "tests/api" / new
    if tests_src.exists() and not tests_dst.exists():
        shutil.copytree(tests_src, tests_dst, ignore=shutil.ignore_patterns("__pycache__"))
        for py_file in tests_dst.rglob("*.py"):
            text = py_file.read_text(encoding="utf-8")
            py_file.write_text(text.replace(f"/api/{source}/", f"/api/{new}/"), encoding="utf-8")
        log.append(f"copiado    tests/api/{source} -> tests/api/{new}")

    versions_file = api / "versions.py"
    line = f'    APIVersion(name="{new}", module="app.api.{new}.router"),'
    insert_before_marker(versions_file, "versions", line)
    log.append(f"registrada versión {new}")

    for spec in load_all_specs(base).values():
        if source in spec.versions and new not in spec.versions:
            spec.versions.append(new)
            save_spec(base, spec)
    log.append(f"specs actualizadas: los recursos de {source} ahora también están en {new}")
    return log


def deprecate_version(base: Path, version: str, sunset: str | None, since: str) -> None:
    path = base / "app/api/versions.py"
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf'APIVersion\(\s*name="{re.escape(version)}"[^)]*\)')
    if not pattern.search(text):
        raise SpecError(f"La versión {version} no está registrada en app/api/versions.py")
    sunset_part = f', sunset="{sunset}"' if sunset else ""
    replacement = (
        f'APIVersion(name="{version}", module="app.api.{version}.router", '
        f'deprecated=True, deprecated_since="{since}"{sunset_part})'
    )
    path.write_text(pattern.sub(lambda _: replacement, text, count=1), encoding="utf-8")
    format_files(base, [path])  # la línea pasa de 100 caracteres (UX-45)


# --- graphify --------------------------------------------------------------------
def refresh_graph(base: Path) -> str | None:
    """Actualiza el grafo de graphify tras cambiar código (solo AST: rápido y sin
    coste de tokens). No hace nada si el proyecto no usa graphify o si se define
    APIGEN_NO_GRAPH=1. Nunca falla: devuelve un mensaje para mostrar o None."""
    if os.environ.get("APIGEN_NO_GRAPH") or not (base / GRAPH_FILE).exists():
        return None
    exe = shutil.which("graphify")
    if exe is None:
        return (
            "graphify no está instalado: el grafo queda desactualizado "
            "(uv tool install graphifyy==0.9.58)"
        )
    try:
        result = subprocess.run(  # noqa: S603
            [exe, "update", "."], cwd=base, capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"no se pudo actualizar el grafo: {exc}"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:] or ["error desconocido"]
        return f"no se pudo actualizar el grafo: {detail[0]} (ejecuta `graphify update .`)"
    return "grafo actualizado (graphify update .)"
