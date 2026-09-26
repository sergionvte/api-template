"""Convierte un ResourceSpec en código Python (modelo, esquemas, router y tests)."""

from __future__ import annotations

import ast
import keyword
import textwrap
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from apigen.naming import pascal
from apigen.spec import FieldSpec, ResourceSpec

# Nombres que no pueden ser miembros de un Enum (o que taparían métodos de str).
_ENUM_FORBIDDEN = {"mro", *dir(str)}

TEMPLATES = Path(__file__).parent / "templates"


def py(value: object) -> str:
    """Literal Python seguro (nunca interpolamos texto del YAML sin escapar)."""
    return repr(value)


def _num(value: float) -> str:
    return repr(int(value)) if float(value).is_integer() else repr(value)


@dataclass
class Imports:
    lines: set[str] = field(default_factory=set)

    def add(self, line: str) -> None:
        self.lines.add(line)

    def render(self, *, already: Iterable[str] = ()) -> str:
        """Líneas de import ordenadas, sin las que la plantilla ya escribe (UX-45)."""
        return "\n".join(sorted(self.lines - set(already)))


# --- tipos -------------------------------------------------------------------
def enum_members(choices: list[str]) -> list[tuple[str, str]]:
    members: list[tuple[str, str]] = []
    seen: set[str] = set()
    for value in choices:
        ident = value.lower().replace("-", "_")
        if (
            not ident.isidentifier()
            or keyword.iskeyword(ident)
            or ident.startswith("_")
            or ident in _ENUM_FORBIDDEN
        ):
            ident = f"v_{ident.lstrip('_')}"
        while ident in seen:
            ident += "_"
        seen.add(ident)
        members.append((ident, value))
    return members


def enum_class(spec: ResourceSpec, fname: str) -> str:
    return f"{spec.class_name}{pascal(fname)}"


def _py_type(
    spec: ResourceSpec, fname: str, f: FieldSpec, imports: Imports, *, schema: bool
) -> str:
    t = f.type
    if t in {"str", "text"}:
        return "str"
    if t == "email":
        if schema:
            imports.add("from pydantic import EmailStr")
            return "EmailStr"
        return "str"
    if t == "int":
        return "int"
    if t == "float":
        return "float"
    if t == "decimal":
        imports.add("from decimal import Decimal")
        return "Decimal"
    if t == "bool":
        return "bool"
    if t == "date":
        imports.add("from datetime import date")
        return "date"
    if t == "datetime":
        if schema:
            # Exige zona horaria: evita ambigüedades con fechas "naive".
            imports.add("from pydantic import AwareDatetime")
            return "AwareDatetime"
        imports.add("from datetime import datetime")
        return "datetime"
    if t in {"uuid", "fk"}:
        imports.add("import uuid")
        return "uuid.UUID"
    if t == "json":
        imports.add("from typing import Any")
        if schema:
            # Límite de tamaño y profundidad (SEC-14).
            imports.add("from typing import Annotated")
            imports.add("from pydantic import AfterValidator")
            imports.add("from app.schemas.common import check_json_size")
            return (
                "Annotated[dict[str, Any] | list[Any], "
                f"AfterValidator(lambda v: check_json_size(v, {f.max_length}))]"
            )
        return "dict[str, Any] | list[Any]"
    if t == "enum":
        return enum_class(spec, fname)
    raise AssertionError(t)


def _default_expr(f: FieldSpec, imports: Imports, enum_cls: str | None = None) -> tuple[str, str]:
    """Devuelve ('default'|'default_factory', expresión)."""
    v = f.default
    if f.type == "enum" and enum_cls:
        ident = dict((value, ident) for ident, value in enum_members(f.choices or []))[v]
        return "default", f"{enum_cls}.{ident}"
    if f.type == "decimal":
        imports.add("from decimal import Decimal")
        return "default", f"Decimal({py(v)})"
    if f.type == "date":
        imports.add("from datetime import date")
        return "default", f"date.fromisoformat({py(v)})"
    if f.type == "datetime":
        imports.add("from datetime import datetime")
        return "default", f"datetime.fromisoformat({py(v)})"
    if f.type == "json":
        return "default_factory", f"lambda: {py(v)}"
    return "default", py(v)


def _validation_kwargs(f: FieldSpec, *, include_length: bool = True) -> list[str]:
    kw: list[str] = []
    if f.type in {"str", "text", "email"} and include_length:
        if f.min_length:
            kw.append(f"min_length={f.min_length}")
        if f.max_length and f.type != "email":
            kw.append(f"max_length={f.max_length}")
        if f.pattern:
            kw.append(f"pattern={py(f.pattern)}")
    if f.type == "int":
        # Siempre acotado (a 64 bits como mínimo): un entero enorme daría un 500
        # por desbordamiento en la BD en vez de un 422 (SEC-07).
        low, high = f.int_bounds()
        kw += [f"ge={low}", f"le={high}"]
    else:
        for key in ("ge", "le", "gt", "lt"):
            value = getattr(f, key)
            if value is not None:
                kw.append(f"{key}={_num(value)}")
    if f.type == "decimal":
        kw.append(f"max_digits={f.max_digits}")
        kw.append(f"decimal_places={f.decimal_places}")
    if f.type == "float":
        kw.append("allow_inf_nan=False")
    if f.description:
        kw.append(f"description={py(f.description)}")
    return kw


def wrapped_literal(text: str, width: int = 70) -> list[str]:
    """Trocea un texto en literales Python cortos (concatenación implícita) para
    no superar el ancho de línea. Cada trozo se emite con repr()."""
    chunks: list[str] = []
    paragraphs = text.split("\n\n")
    for i, paragraph in enumerate(paragraphs):
        lines = textwrap.wrap(paragraph, width, break_long_words=True) or [""]
        for j, line in enumerate(lines):
            last_line = j == len(lines) - 1
            suffix = ("\n\n" if i < len(paragraphs) - 1 else "") if last_line else " "
            chunks.append(py(line + suffix))
    return chunks


def _examples_kwarg(f: FieldSpec) -> list[str]:
    return [f"examples=[{py(f.example)}]"] if f.example is not None else []


def unique_in_table(spec: ResourceSpec, f: FieldSpec) -> bool:
    """¿Se puede declarar `unique=True` en la columna? No en recursos owned (la
    unicidad es por propietario) ni con soft delete (índice parcial)."""
    return f.unique and not spec.owned and not spec.soft_delete


def table_args(spec: ResourceSpec, imports: Imports) -> list[str]:
    """Restricciones de unicidad compuestas o parciales para `__table_args__`.

    - owned: única por propietario (owner_id, campo). Con unicidad global, el
      409 revelaría a un usuario qué valores guardaron otros (SEC-09).
    - soft_delete: índice único parcial `WHERE deleted_at IS NULL`, para que un
      valor borrado se pueda reutilizar (UX-11). SQLite y PostgreSQL lo soportan.
    """
    args: list[str] = []
    for fname, f in spec.fields.items():
        if not f.unique or unique_in_table(spec, f):
            continue
        cols = ["owner_id", fname] if spec.owned else [fname]
        cols_py = ", ".join(py(c) for c in cols)
        if spec.soft_delete:
            imports.add("from sqlalchemy import Index, text")
            name = f"uq_{spec.table}_{'_'.join(cols)}"[:63]
            where = 'text("deleted_at IS NULL")'
            args.append(
                f"Index({py(name)}, {cols_py}, unique=True, "
                f"sqlite_where={where}, postgresql_where={where})"
            )
        else:
            imports.add("from sqlalchemy import UniqueConstraint")
            args.append(f"UniqueConstraint({cols_py})")
    return args


def table_field(
    spec: ResourceSpec, fname: str, f: FieldSpec, imports: Imports, tables: dict[str, str]
) -> str:
    ptype = _py_type(spec, fname, f, imports, schema=False)
    kw: list[str] = []
    if f.nullable:
        ptype = f"{ptype} | None"
    if f.default is not None:
        kind, expr = _default_expr(f, imports, enum_class(spec, fname))
        kw.append(f"{kind}={expr}")
    elif f.nullable:
        kw.append("default=None")

    if f.type in {"str", "email"}:
        kw.append(f"max_length={f.max_length}")
    elif f.type == "int" and not f.fits_int32():
        # INTEGER es de 32 bits en PostgreSQL: si el rango no cabe, BIGINT.
        imports.add("from sqlalchemy import BigInteger")
        kw.append("sa_type=BigInteger")
    elif f.type == "text":
        imports.add("from sqlalchemy import Text")
        kw.append("sa_type=Text")
    elif f.type == "decimal":
        kw += [f"max_digits={f.max_digits}", f"decimal_places={f.decimal_places}"]
    elif f.type == "datetime":
        imports.add("from app.db.types import UTCDateTime")
        kw.append("sa_type=UTCDateTime")
    elif f.type == "json":
        imports.add("from sqlalchemy import JSON")
        kw.append("sa_type=JSON")
    elif f.type == "enum":
        imports.add("from sqlalchemy import String")
        kw.append(f"sa_type=String({f.max_length})")
    elif f.type == "fk":
        kw.append(f"foreign_key={py(tables[f.to] + '.id')}")  # type: ignore[index]
        kw.append(f"ondelete={py(f.on_delete)}")

    if unique_in_table(spec, f):
        kw.append("unique=True")
    elif f.index:
        kw.append("index=True")
    if f.description:
        kw.append(f"description={py(f.description)}")
    return f"{fname}: {ptype} = Field({', '.join(kw)})"


def create_field(spec: ResourceSpec, fname: str, f: FieldSpec, imports: Imports) -> str:
    ptype = _py_type(spec, fname, f, imports, schema=True)
    kw = _validation_kwargs(f) + _examples_kwarg(f)
    if f.nullable:
        ptype = f"{ptype} | None"
    if f.default is not None:
        kind, expr = _default_expr(f, imports, enum_class(spec, fname))
        kw.insert(0, f"{kind}={expr}")
    elif f.nullable:
        kw.insert(0, "default=None")
    return f"{fname}: {ptype} = Field({', '.join(kw)})"


def update_field(spec: ResourceSpec, fname: str, f: FieldSpec, imports: Imports) -> str:
    ptype = _py_type(spec, fname, f, imports, schema=True)
    kw = ["default=None", *_validation_kwargs(f)]
    return f"{fname}: {ptype} | None = Field({', '.join(kw)})"


def read_field(spec: ResourceSpec, fname: str, f: FieldSpec, imports: Imports) -> str:
    ptype = _py_type(spec, fname, f, imports, schema=False)
    return f"{fname}: {ptype}{' | None' if f.nullable else ''}"


def filter_param(spec: ResourceSpec, fname: str, f: FieldSpec, imports: Imports) -> str:
    ptype = _py_type(spec, fname, f, imports, schema=False)
    if f.type in {"str", "email"}:
        return f"{fname}: Annotated[str | None, Query(max_length={f.max_length})] = None"
    if f.type == "int":
        low, high = f.int_bounds()
        return f"{fname}: Annotated[int | None, Query(ge={low}, le={high})] = None"
    return f"{fname}: {ptype} | None = None"


# --- valores de ejemplo para los tests -----------------------------------------
def example_expr(spec: ResourceSpec, fname: str, f: FieldSpec, *, variant: int = 0) -> str:
    """Expresión Python que produce un valor válido (distinto por `variant`)."""
    if f.example is not None and variant == 0:
        if f.unique and f.type in {"str", "text"}:
            # Misma "forma" que el ejemplo pero aleatorio: respeta patrones simples y la unicidad.
            return f"_like({py(f.example)})"
        return py(f.example)
    t = f.type
    if t in {"str", "text"}:
        if f.pattern:
            return f"_like({py(f.example)})" if f.unique else py(f.example)
        return f"_text({py(fname)}, {f.min_length or 0}, {f.max_length})"
    if t == "email":
        return f'f"{fname.replace("_", "-")}-{{_uid()}}@example.com"'
    if t in {"int", "float", "decimal"}:
        low = f.ge if f.ge is not None else (f.gt + 1 if f.gt is not None else 1)
        high = f.le if f.le is not None else (f.lt - 1 if f.lt is not None else low + 100)
        value = min(low + variant, high)
        if t == "int":
            return f"_rand_int({int(low)}, {int(high)})" if f.unique else repr(int(value))
        if t == "float":
            return repr(float(value))
        return py(f"{value:.{f.decimal_places}f}")
    if t == "bool":
        return "True" if variant == 0 else "False"
    if t == "date":
        return py(f"2026-01-{10 + variant:02d}")
    if t == "datetime":
        return py(f"2026-01-{10 + variant:02d}T10:00:00+00:00")
    if t == "uuid":
        return "str(uuid.uuid4())"
    if t == "json":
        return py({"key": f"value{variant}"})
    if t == "enum":
        choices = f.choices or []
        return py(choices[variant % len(choices)])
    raise AssertionError(t)


# --- renderizado ---------------------------------------------------------------
def environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        autoescape=False,  # noqa: S701 - generamos Python, no HTML
    )
    env.filters["py"] = py
    return env


@dataclass
class Rendered:
    path: Path
    content: str


def build_context(
    spec: ResourceSpec, all_specs: dict[str, ResourceSpec], version: str
) -> dict[str, object]:
    tables = {"user": "users", **{name: other.table for name, other in all_specs.items()}}
    model_imports, schema_imports, router_imports = Imports(), Imports(), Imports()
    fields = spec.fields
    enums = {
        fname: {"cls": enum_class(spec, fname), "members": enum_members(f.choices or [])}
        for fname, f in fields.items()
        if f.type == "enum"
    }
    table_fields = [table_field(spec, n, f, model_imports, tables) for n, f in fields.items()]
    model_table_args = table_args(spec, model_imports)
    create_fields = [create_field(spec, n, f, schema_imports) for n, f in fields.items()]
    update_fields = [
        update_field(spec, n, f, schema_imports) for n, f in fields.items() if not f.immutable
    ]
    read_fields = [
        read_field(spec, n, f, schema_imports) for n, f in fields.items() if not f.write_only
    ]
    non_nullable = sorted(n for n, f in fields.items() if not f.nullable and not f.immutable)
    immutable = sorted(n for n, f in fields.items() if f.immutable)
    # Parámetros de query válidos del listado y campos del recurso (para dar un 422
    # útil si se filtra por un campo no filtrable; UX-16).
    query_allowed = sorted(
        {"limit", "offset", "order_by", *spec.filters, *(["q"] if spec.search else [])}
    )
    query_fields = sorted(n for n, f in fields.items() if not f.write_only)
    filters = [filter_param(spec, n, fields[n], router_imports) for n in spec.filters]

    # FKs: hay que comprobar que la fila destino existe y que el usuario puede verla
    # (si no, podría enlazar/sondear filas ajenas; SEC-10). Respuesta uniforme 422.
    references = []
    for fname, f in fields.items():
        if f.type != "fk":
            continue
        if f.to == "user":
            references.append(
                {
                    "field": fname,
                    "model": "User",
                    "module": "user",
                    "scoped": False,
                    "admin_only": False,
                    "soft_delete": False,
                }
            )
            continue
        target = all_specs[f.to]  # type: ignore[index]
        references.append(
            {
                "field": fname,
                "model": target.class_name,
                "module": target.name,
                # Si solo el dueño puede leer el padre, solo el dueño puede referenciarlo.
                "scoped": target.owned and target.permissions.read == "owner",
                # Si solo un admin puede leer el padre, solo un admin puede referenciarlo.
                "admin_only": target.permissions.read == "admin",
                "soft_delete": target.soft_delete,
            }
        )

    ordering = sorted({"created_at", *spec.ordering})
    order_values = [v for o in ordering for v in (o, f"-{o}")]
    # Descripción del listado en OpenAPI: qué se puede filtrar, buscar y ordenar.
    doc = [spec.description] if spec.description else []
    if spec.filters:
        doc.append("Filters: " + ", ".join(spec.filters) + ".")
    if spec.search:
        doc.append("Text search (`q`) in: " + ", ".join(spec.search) + ".")
    doc.append("Ordering (`order_by`, prefix `-` for descending): " + ", ".join(ordering) + ".")
    actions = []
    for a in spec.actions:
        input_cls = f"{spec.class_name}{pascal(a.name)}Input" if a.fields else None
        actions.append(
            {
                "name": a.name,
                "scope": a.scope,
                "background": a.background,
                "perm": a.permission,
                "alias": f"Can{pascal(a.name)}",
                "func": f"{a.name}_{spec.name}",
                "path": f"/{{item_id}}/{a.name}" if a.scope == "item" else f"/{a.name}",
                "task": f"{spec.name}.{a.name}",
                "rate": a.rate_limit,
                "description": wrapped_literal(
                    a.description
                    or (
                        f"Runs `{a.name}` in the background worker: responds 202 with the job id."
                        if a.background
                        else f"Custom action `{a.name}` (app/hooks/{spec.name}.py)."
                    )
                ),
                "input_cls": input_cls,
                "input_fields": [
                    create_field(spec, n, f, schema_imports) for n, f in a.fields.items()
                ],
                "scoped": a.permission == "owner",
                "test_payload": {n: example_expr(spec, n, f) for n, f in a.fields.items()},
            }
        )

    p = spec.permissions
    return {
        "spec": spec,
        "actions": actions,
        "has_background": any(a["background"] for a in actions),
        "has_sync": any(not a["background"] for a in actions),
        "action_rates": any(a["rate"] for a in actions),
        "version": version,
        "cls": spec.class_name,
        "name": spec.name,
        "plural": spec.plural,
        "table": spec.table,
        "enums": enums,
        # Imports que las plantillas ya incluyen: sin duplicados (F811) en el código generado.
        "model_imports": model_imports.render(already=["import uuid"] if spec.owned else []),
        "schema_imports": schema_imports.render(
            already=["import uuid", "from datetime import datetime"]
        ),
        "router_imports": router_imports.render(already=["import uuid"]),
        "table_fields": table_fields,
        "table_args": model_table_args,
        "immutable": immutable,
        "query_allowed": query_allowed,
        "query_fields": query_fields,
        "create_fields": create_fields,
        "update_fields": update_fields,
        "read_fields": read_fields,
        "non_nullable": non_nullable,
        "filters": filters,
        "filter_names": list(spec.filters),
        "search_fields": list(spec.search),
        "ordering": ordering,
        "order_values": order_values,
        "list_description": wrapped_literal("\n\n".join(doc)),
        "description_chunks": wrapped_literal(spec.description or ""),
        "references": references,
        "perm": p,
        "rate_read": spec.rate_limits.read,
        "rate_write": spec.rate_limits.write,
        "test": build_test_context(spec, all_specs),
    }


def build_test_context(spec: ResourceSpec, all_specs: dict[str, ResourceSpec]) -> dict[str, object]:
    """Datos para el test generado: payload válido, padres a crear y campo a actualizar."""
    setup: list[dict[str, object]] = []
    counter = 0

    def make_parent(target_name: str, depth: int) -> str | None:
        nonlocal counter
        target = all_specs[target_name]
        values: dict[str, str] = {}
        for fname, f in target.fields.items():
            if f.type == "fk":
                if f.to == "user":
                    values[fname] = "owner_id"
                elif f.required and depth < 5 and f.to != target_name:
                    var = make_parent(f.to, depth + 1)  # type: ignore[arg-type]
                    if var is None:
                        return None
                    values[fname] = f"{var}.id"
                continue
            if f.required:
                values[fname] = _model_value(target, fname, f)
        if target.owned:
            values["owner_id"] = "owner_id"
        counter += 1
        var = f"{target.name}_{counter}"
        setup.append({"var": var, "cls": target.class_name, "module": target.name, "attrs": values})
        return var

    payload: dict[str, str] = {}
    supported = True
    for fname, f in spec.fields.items():
        if f.type == "fk":
            if f.to == "user":
                payload[fname] = "str(owner_id)"
            elif f.required:
                var = make_parent(f.to, 0)  # type: ignore[arg-type]
                if var is None:
                    supported = False
                    continue
                payload[fname] = f"str({var}.id)"
            continue
        payload[fname] = example_expr(spec, fname, f)

    update_target = None
    for fname, f in spec.fields.items():
        if f.immutable or f.write_only or f.unique or f.pattern:
            continue
        if f.type in {"str", "text", "int", "bool"} or (
            f.type == "enum" and len(f.choices or []) > 1
        ):
            update_target = (fname, example_expr(spec, fname, f, variant=1))
            break

    unique_field = next(
        (n for n, f in spec.fields.items() if f.unique and f.type in {"str", "email", "int"}), None
    )
    int_field = next(
        (n for n, f in spec.fields.items() if f.type == "int" and not f.write_only), None
    )
    immutable_field = next(
        (
            (n, example_expr(spec, n, f, variant=1))
            for n, f in spec.fields.items()
            if f.immutable and f.type in {"str", "text", "int", "bool", "enum"}
        ),
        None,
    )
    return {
        "int_field": int_field,
        "unique_fields": sorted(n for n, f in spec.fields.items() if f.unique),
        "immutable_field": immutable_field,
        "payload": payload,
        "setup": setup,
        "supported": supported,
        "update_field": update_target,
        "unique_field": unique_field,
        "write_only": [n for n, f in spec.fields.items() if f.write_only],
    }


def _model_value(spec: ResourceSpec, fname: str, f: FieldSpec) -> str:
    """Igual que example_expr pero con tipos Python (para insertar vía ORM)."""
    expr = example_expr(spec, fname, f)
    if f.type == "decimal":
        return f"Decimal({expr})"
    if f.type == "date":
        return f"date.fromisoformat({expr})"
    if f.type == "datetime":
        return f"datetime.fromisoformat({expr})"
    if f.type == "uuid":
        return "uuid.uuid4()"
    return expr


def render_resource(
    root: Path, spec: ResourceSpec, all_specs: dict[str, ResourceSpec], *, with_tests: bool = True
) -> list[Rendered]:
    env = environment()
    out: list[Rendered] = []
    base_ctx = build_context(spec, all_specs, spec.versions[0])
    out.append(
        Rendered(
            root / "app/models" / f"{spec.name}.py",
            env.get_template("model.py.j2").render(**base_ctx),
        )
    )
    out.append(
        Rendered(
            root / "app/schemas" / f"{spec.name}.py",
            env.get_template("schemas.py.j2").render(**base_ctx),
        )
    )
    for version in spec.versions:
        ctx = build_context(spec, all_specs, version)
        out.append(
            Rendered(
                root / "app/api" / version / "endpoints" / f"{spec.plural}.py",
                env.get_template("router.py.j2").render(**ctx),
            )
        )
        if with_tests:
            out.append(
                Rendered(
                    root / "tests/api" / version / f"test_{spec.plural}.py",
                    env.get_template("test.py.j2").render(**ctx),
                )
            )
    return out


# --- módulos del usuario (hooks y tareas): se crean una vez, nunca se pisan ------
_HOOK_DOCS = {
    "before_create": (
        "data: {cls}Create",
        "{cls}Create",
        "Antes de insertar: valida reglas de negocio, normaliza o rechaza con\n"
        '    `raise APIError(422, "...", code="...")`. Devuelve los datos (puedes\n'
        "    modificarlos con `data.model_copy(update={{...}})`).",
        "return data",
    ),
    "after_create": (
        "obj: {cls}",
        "None",
        "Tras insertar (ya guardado). Lo pesado, encólalo: `await ctx.enqueue(...)`.",
        "return None",
    ),
    "before_update": (
        "obj: {cls}, data: {cls}Update",
        "{cls}Update",
        "Antes de aplicar un PATCH. `obj` es la fila actual; `data` solo trae los campos\n"
        "    enviados (`data.model_fields_set`). Devuelve los datos a aplicar.",
        "return data",
    ),
    "after_update": ("obj: {cls}", "None", "Tras guardar los cambios.", "return None"),
    "before_delete": (
        "obj: {cls}",
        "None",
        "Antes de borrar: lanza APIError para impedirlo (p. ej. 409 si está en uso).",
        "return None",
    ),
    "after_delete": ("obj: {cls}", "None", "Tras borrar.", "return None"),
}


def hooks_module(spec: ResourceSpec) -> tuple[str, str, dict[str, str]]:
    cls = spec.class_name
    header = f'''"""Lógica personalizada de `{spec.name}`. ESTE FICHERO ES TUYO.

apigen lo crea una vez y nunca lo sobrescribe (ni con `generate --force`): si
añades acciones al YAML solo añade al final las funciones que falten. Los
endpoints de `app/api/vN/endpoints/{spec.plural}.py` llaman a estas funciones.

- before_*: valida/normaliza o rechaza con `raise APIError(...)`.
- after_*: efectos secundarios; lo pesado, encólalo con `await ctx.enqueue(...)`
  para que lo ejecute el worker sin ralentizar la API.
"""

from __future__ import annotations

from typing import Any  # noqa: F401

from app.core.exceptions import APIError  # noqa: F401
from app.hooks import HookContext
from app.models.{spec.name} import {cls}
from app.schemas.{spec.name} import {cls}Create, {cls}Update
'''
    stubs: dict[str, str] = {}
    for name, (params, returns, doc, body) in _HOOK_DOCS.items():
        stubs[name] = (
            f"async def {name}(ctx: HookContext, {params.format(cls=cls)}) -> "
            f"{returns.format(cls=cls)}:\n"
            f'    """{doc.format(cls=cls)}"""\n'
            f"    {body}\n"
        )
    for a in spec.actions:
        if a.background:
            continue
        item = "/{item_id}" if a.scope == "item" else ""
        where = f"/{spec.plural}{item}/{a.name}"
        obj_param = f"obj: {cls}, " if a.scope == "item" else ""
        result = '{"item_id": str(obj.id)}' if a.scope == "item" else '{"ok": True}'
        stubs[a.name] = (
            f"async def {a.name}(ctx: HookContext, {obj_param}data: dict[str, Any]) -> "
            "dict[str, Any]:\n"
            f'    """Acción `POST {where}`: devuelve un dict serializable a JSON.\n\n'
            "    Si tarda más de un par de segundos, márcala `background: true` en el YAML\n"
            '    para que la ejecute el worker."""\n'
            f"    return {result}\n"
        )
    return f"app/hooks/{spec.name}.py", header, stubs


def tasks_module(spec: ResourceSpec) -> tuple[str, str, dict[str, str]] | None:
    background = [a for a in spec.actions if a.background]
    if not background:
        return None
    cls = spec.class_name
    header = f'''"""Tareas en segundo plano de `{spec.name}`. ESTE FICHERO ES TUYO.

Se ejecutan en `apigen worker` (un proceso aparte), nunca dentro de la API.
apigen lo crea una vez y solo añade al final las tareas que falten.

- `raise TaskError("mensaje")`: fallo que el cliente puede ver (no se reintenta).
- Cualquier otra excepción se reintenta con espera creciente y el cliente solo
  ve "Task failed" (la traza queda en el log con el job_id).
"""

from __future__ import annotations

import uuid  # noqa: F401
from typing import Any

from app.models.{spec.name} import {cls}  # noqa: F401
from app.tasks.registry import TaskContext, TaskError, task  # noqa: F401
'''
    stubs: dict[str, str] = {}
    for a in background:
        keys = ('"item_id": "<uuid>"' if a.scope == "item" else "") + "".join(
            f', "{n}": ...' for n in a.fields
        )
        doc = (a.description or f"Proceso pesado `{a.name}`.").replace('"""', "'''")
        deco = (
            f'@task("{spec.name}.{a.name}", executor="{a.executor}", timeout={a.timeout}, '
            f"max_attempts={a.max_attempts})\n"
        )
        if a.executor == "async":
            if a.scope == "item":
                body = (
                    '    item_id = uuid.UUID(payload["item_id"])\n'
                    "    async with ctx.session() as session:\n"
                    f"        obj = await session.get({cls}, item_id)\n"
                    "        if obj is None:\n"
                    f'            raise TaskError("{cls} no longer exists")\n'
                    "        # Aquí va el proceso pesado (informes, llamadas externas...).\n"
                    '    return {"item_id": str(item_id)}\n'
                )
            else:
                body = '    return {"received": sorted(payload)}\n'
            stubs[a.name] = (
                deco
                + f"async def {a.name}(\n"
                + "    ctx: TaskContext, payload: dict[str, Any]\n"
                + ") -> dict[str, Any]:\n"
                + f'    """{doc}\n\n'
                + f"    payload: {{{keys.lstrip(', ')}}}.\n"
                + '    Sesión de BD propia: `async with ctx.session() as session`.\n    """\n'
                + body
            )
        else:
            result = '{"item_id": payload.get("item_id")}' if a.scope == "item" else "{}"
            stubs[a.name] = (
                deco
                + f"def {a.name}(payload: dict[str, Any]) -> dict[str, Any]:\n"
                + f'    """{doc}\n\n'
                + f"    Función síncrona ({a.executor}): recibe y devuelve datos JSON.\n"
                + '    """\n'
                + f"    return {result}\n"
            )
    return f"app/tasks/resources/{spec.name}.py", header, stubs


def ensure_user_module(path: Path, header: str, stubs: dict[str, str]) -> tuple[str, list[str]]:
    """Crea el módulo si no existe o añade al final las funciones que falten.

    Devuelve ("created" | "appended" | "unchanged" | "unparseable", nombres añadidos).
    Nunca modifica el código que ya existe.
    """
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(header + "\n\n" + "\n\n".join(stubs.values()), encoding="utf-8")
        return "created", list(stubs)
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return "unparseable", []
    existing = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    missing = [name for name in stubs if name not in existing]
    if not missing:
        return "unchanged", []
    addition = "\n\n".join(stubs[name] for name in missing)
    path.write_text(text.rstrip("\n") + "\n\n\n" + addition, encoding="utf-8")
    return "appended", missing
