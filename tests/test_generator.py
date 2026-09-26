"""Tests del generador: validación de specs y seguridad del código generado."""

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from apigen.codegen import render_resource
from apigen.naming import pluralize
from apigen.spec import (
    ResourceSpec,
    SpecError,
    load_specs,
    parse_field_option,
    validate_references,
)

ROOT = Path(__file__).resolve().parents[1]


def _spec(**overrides) -> ResourceSpec:
    data = {"name": "widget", "fields": {"title": {"type": "str"}}}
    data.update(overrides)
    return ResourceSpec.model_validate(data)


@pytest.mark.parametrize(
    ("singular", "plural"),
    [
        ("product", "products"),
        ("category", "categories"),
        ("box", "boxes"),
        ("blog_post", "blog_posts"),
        ("person", "people"),
    ],
)
def test_pluralize(singular, plural):
    assert pluralize(singular) == plural


@pytest.mark.parametrize(
    "fields",
    [
        {"id": {"type": "str"}},
        {"owner_id": {"type": "uuid"}},
        {"class": {"type": "str"}},
        {"Bad-Name": {"type": "str"}},
        {"model_config": {"type": "str"}},
        {"x": {"type": "str", "pattern": "[a-"}},
        {"x": {"type": "int", "default": "abc"}},
        {"x": {"type": "enum", "choices": ["ok", "no'pe"]}},
        {"x": {"type": "fk"}},
        {"x": {"type": "text", "unique": True}},
    ],
)
def test_invalid_fields_rejected(fields):
    with pytest.raises(ValidationError):
        _spec(fields=fields)


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "users"},
        {"name": "x; import os"},
        {"permissions": {"update": "public"}},
        {"permissions": {"read": "owner"}},  # owner sin owned
        {"owned": True, "permissions": {"create": "public"}},
        {"filters": ["missing"]},
        {"versions": ["2"]},
        {"rate_limits": {"read": "lots"}},
    ],
)
def test_invalid_resources_rejected(overrides):
    with pytest.raises(ValidationError):
        _spec(**overrides)


def test_secure_default_permissions():
    public = _spec()
    assert (public.permissions.create, public.permissions.delete) == ("admin", "admin")
    owned = _spec(owned=True)
    assert owned.permissions.read == "owner" and owned.permissions.create == "user"


def test_unknown_reference_rejected():
    spec = _spec(fields={"parent_id": {"type": "fk", "to": "ghost"}})
    with pytest.raises(SpecError):
        validate_references([spec])


def test_cli_field_dsl():
    name, f = parse_field_option("price:decimal:ge=0:digits=10:places=2:default=9.99")
    assert (name, f.type, f.max_digits, f.decimal_places, f.default) == (
        "price",
        "decimal",
        10,
        2,
        "9.99",
    )
    _, e = parse_field_option("status:enum=a|b:default=b")
    assert e.choices == ["a", "b"] and e.default == "b"
    with pytest.raises(SpecError):
        parse_field_option("x:str:bogus")


def test_generated_code_cannot_be_injected(tmp_path):
    """Textos hostiles del YAML acaban como literales, nunca como código."""
    payload = '"""\nimport os; os.system("echo pwned")\n"""'
    spec = _spec(
        description=payload[:300],
        fields={
            "title": {"type": "str", "description": payload, "default": "')\nimport os #"},
            "kind": {"type": "enum", "choices": ["a", "b"]},
        },
    )
    for rendered in render_resource(tmp_path, spec, {"widget": spec}):
        tree = ast.parse(rendered.content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import | ast.ImportFrom):
                names = [a.name for a in node.names]
                assert "os" not in names and getattr(node, "module", "") != "os"
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr != "system"


def test_generated_code_compiles_for_all_types(tmp_path):
    spec = ResourceSpec.model_validate(
        {
            "name": "thing",
            "owned": True,
            "soft_delete": True,
            "rate_limits": {"read": "100/minute", "write": "10/minute"},
            "fields": {
                "a": {"type": "str", "unique": True},
                "b": {"type": "text", "nullable": True},
                "c": {"type": "int", "ge": 0, "default": 1},
                "d": {"type": "float", "nullable": True},
                "e": {"type": "decimal", "default": "1.50"},
                "f": {"type": "bool", "default": False},
                "g": {"type": "date", "nullable": True},
                "h": {"type": "datetime", "nullable": True},
                "i": {"type": "uuid", "nullable": True},
                "j": {"type": "email"},
                "k": {"type": "json", "default": {"x": 1}},
                "l": {
                    "type": "enum",
                    "choices": ["in-progress", "1st", "class"],
                    "default": "class",
                },
                "m": {"type": "fk", "to": "user", "nullable": True},
            },
            "filters": ["a", "c", "f", "l", "m"],
            "search": ["a", "b"],
            "ordering": ["c", "e"],
        }
    )
    for rendered in render_resource(tmp_path, spec, {"thing": spec}):
        compile(rendered.content, str(rendered.path), "exec")


def _render(spec: ResourceSpec, tmp_path, others: dict | None = None) -> dict[str, str]:
    specs = {spec.name: spec, **(others or {})}
    return {str(r.path): r.content for r in render_resource(tmp_path, spec, specs)}


def test_int_fields_are_bounded_and_use_bigint_when_needed(tmp_path):
    """SEC-07: todo int queda acotado a 64 bits; BIGINT si no cabe en 32."""
    spec = _spec(
        fields={
            "small": {"type": "int", "ge": 1, "le": 100},
            "big": {"type": "int"},
            "huge_le": {"type": "int", "le": 2**70},
        },
        filters=["big"],
    )
    files = _render(spec, tmp_path)
    schemas = next(c for n, c in files.items() if "WidgetCreate" in c)
    model = next(c for n, c in files.items() if "table=True" in c)
    assert "small: int = Field(ge=1, le=100)" in schemas
    assert f"big: int = Field(ge={-(2**63)}, le={2**63 - 1})" in schemas
    assert f"le={2**63 - 1}" in schemas.split("huge_le")[1].splitlines()[0]
    assert "small: int = Field()" in model
    assert "big: int = Field(sa_type=BigInteger)" in model


def test_owned_unique_is_per_owner_and_soft_delete_uses_partial_index(tmp_path):
    """SEC-09 / UX-11."""
    owned = _spec(owned=True, fields={"code": {"type": "str", "unique": True}})
    model = next(c for c in _render(owned, tmp_path).values() if "table=True" in c)
    assert 'UniqueConstraint("owner_id", "code")' in model.replace("'", '"')
    assert "unique=True" not in model

    soft = _spec(soft_delete=True, fields={"code": {"type": "str", "unique": True}})
    model = next(c for c in _render(soft, tmp_path).values() if "table=True" in c)
    assert 'sqlite_where=text("deleted_at IS NULL")' in model


def test_fk_references_are_checked_for_users_and_admin_only_targets(tmp_path):
    """SEC-10: fk a user comprueba existencia; destino solo-admin exige admin."""
    secret = _spec(name="secret", permissions={"read": "admin", "list": "admin"})
    spec = _spec(
        name="note",
        owned=True,
        fields={
            "assignee_id": {"type": "fk", "to": "user", "nullable": True},
            "secret_id": {"type": "fk", "to": "secret", "nullable": True},
        },
    )
    router = next(
        c for c in _render(spec, tmp_path, {"secret": secret}).values() if "APIRouter" in c
    )
    assert "from app.models.user import User" in router
    assert "allowed=principal.is_admin" in router


@pytest.mark.parametrize("name", ["session", "principal", "page", "request", "response"])
def test_filter_names_that_clash_with_endpoint_params_rejected(name):
    """SEC-19: evitaría un "duplicate argument" en el router generado."""
    with pytest.raises(ValidationError):
        _spec(fields={name: {"type": "str"}})


def test_enum_members_that_break_enum_are_renamed(tmp_path):
    spec = _spec(fields={"kind": {"type": "enum", "choices": ["mro", "upper", "_x", "ok"]}})
    for rendered in render_resource(tmp_path, spec, {"widget": spec}):
        compile(rendered.content, str(rendered.path), "exec")
    model = next(c for c in _render(spec, tmp_path).values() if "table=True" in c)
    assert "v_mro = " in model and "v_upper = " in model and "ok = " in model


def test_pattern_unsupported_by_pydantic_rejected():
    with pytest.raises(ValidationError):
        _spec(fields={"x": {"type": "str", "pattern": "^(?=a)b$", "example": "b"}})


def test_insecure_permission_combinations():
    """SEC-08: error si cualquier usuario puede modificar filas ajenas o leer por ID
    filas que el listado oculta (salvo `shared_read`); aviso si se exponen filas de
    todos (silenciable con `shared_read`, UX-35)."""
    with pytest.raises(ValidationError):
        _spec(owned=True, permissions={"update": "user"})
    for read in ("user", "public"):
        with pytest.raises(ValidationError, match="shared_read"):
            _spec(owned=True, permissions={"list": "owner", "read": read})
    by_id = _spec(owned=True, shared_read=True, permissions={"list": "owner", "read": "user"})
    assert by_id.permissions.read == "user"
    blog = {"list": "public", "read": "public"}
    assert any("ve las filas de todos" in w for w in _spec(owned=True, permissions=blog).warnings())
    assert _spec(owned=True, shared_read=True, permissions=blog).warnings() == []
    assert _spec(owned=True).warnings() == []
    with pytest.raises(ValidationError):
        _spec(shared_read=True)  # solo para recursos owned


def test_yaml_syntax_error_is_reported_with_position(tmp_path):
    """UX-06: sin traceback; fichero:línea:columna."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: x\nfields: {a: {type: str}\n")
    with pytest.raises(SpecError, match=r"bad\.yaml:\d+:\d+: YAML no válido"):
        load_specs(bad)


def test_cli_enum_accepts_commas_and_warns_single_choice():
    """UX-05: `enum=a,b` no necesita comillas; un enum de una opción avisa."""
    _, f = parse_field_option("status:enum=draft,published:default=draft")
    assert f.choices == ["draft", "published"]
    single = _spec(fields={"status": {"type": "enum", "choices": ["a"]}})
    assert any("una opción" in w for w in single.warnings())


def test_cli_errors_are_translated_with_suggestions():
    """UX-07: sugerencia para tipos mal escritos y nombre de opción de la CLI."""
    with pytest.raises(SpecError, match="quisiste decir 'str'"):
        parse_field_option("title:strng")
    with pytest.raises(SpecError, match=r"- max: debe ser un número entero"):
        parse_field_option("title:str:max=abc")
    with pytest.raises(SpecError, match="quisiste decir 'max'"):
        parse_field_option("title:str:maxx=100")
    with pytest.raises(ValidationError, match="quisiste decir 'title'"):
        _spec(fields={"title": {"type": "str"}}, filters=["titel"])


def test_json_fields_have_size_limit(tmp_path):
    spec = _spec(fields={"meta": {"type": "json", "nullable": True}})
    schemas = next(c for c in _render(spec, tmp_path).values() if "WidgetCreate" in c)
    assert "check_json_size(v, 16384)" in schemas


def test_refresh_graph_is_optional(tmp_path, monkeypatch):
    """apigen solo toca graphify si el proyecto ya tiene grafo y no está desactivado."""
    from apigen.project import refresh_graph

    monkeypatch.delenv("APIGEN_NO_GRAPH", raising=False)
    assert refresh_graph(tmp_path) is None  # sin graphify-out/graph.json
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "graph.json").write_text("{}")
    monkeypatch.setenv("APIGEN_NO_GRAPH", "1")
    assert refresh_graph(tmp_path) is None
    monkeypatch.delenv("APIGEN_NO_GRAPH")
    monkeypatch.setattr("shutil.which", lambda _: None)
    assert "no está instalado" in refresh_graph(tmp_path)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("cascade", "CASCADE"),
        ("set null", "SET NULL"),
        ("Set_Null", "SET NULL"),
        ("restrict", "RESTRICT"),
    ],
)
def test_on_delete_is_case_insensitive(value, expected):
    """UX-46: on_delete se normaliza antes de validar (YAML y CLI)."""
    spec = _spec(fields={"p": {"type": "fk", "to": "widget", "nullable": True, "on_delete": value}})
    assert spec.fields["p"].on_delete == expected
    _, f = parse_field_option(f"p:fk=widget:nullable:on_delete={value}")
    assert f.on_delete == expected
    with pytest.raises(ValidationError):
        _spec(fields={"p": {"type": "fk", "to": "widget", "on_delete": "cascada"}})


def test_generated_code_passes_ruff(tmp_path):
    """UX-45: lo que escribe apigen pasa `ruff check` sin tener que hacer `make format`."""
    import shutil
    import subprocess

    from apigen.project import find_ruff, format_files

    ruff = find_ruff(ROOT)
    if ruff is None:
        pytest.skip("ruff no está instalado")
    shutil.copy(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    parent = _spec(soft_delete=True)
    spec = ResourceSpec.model_validate(
        {
            "name": "gadget",
            "owned": True,
            "fields": {
                "code": {
                    "type": "str",
                    "pattern": "^[A-Z]{3}-[0-9]{4}-[a-z]{2,8}$",
                    "example": "ABC-1234-abc",
                    "unique": True,
                },
                "widget_id": {"type": "fk", "to": "widget", "on_delete": "cascade"},
                "user_id": {"type": "fk", "to": "user", "nullable": True},
                "when": {"type": "datetime", "nullable": True},
                "ref": {"type": "uuid", "nullable": True},
            },
            "filters": ["widget_id", "user_id", "ref"],
        }
    )
    files = render_resource(tmp_path, spec, {"widget": parent, "gadget": spec})
    for rendered in files:
        assert rendered.content.count("\nimport uuid\n") <= 1
        rendered.path.parent.mkdir(parents=True, exist_ok=True)
        rendered.path.write_text(rendered.content, encoding="utf-8")
    assert format_files(tmp_path, [f.path for f in files])
    result = subprocess.run(  # noqa: S603
        [str(ruff), "check", "--no-cache", "."], cwd=tmp_path, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout


def test_deprecate_survives_formatting(tmp_path):
    """versions.py sigue siendo legible por apigen después de `ruff format`."""
    from apigen.project import deprecate_version, version_info

    api = tmp_path / "app" / "api"
    api.mkdir(parents=True)
    (api / "versions.py").write_text(
        "VERSIONS = [\n"
        '    APIVersion(name="v1", module="app.api.v1.router"),\n'
        '    APIVersion(name="v2", module="app.api.v2.router"),\n'
        "    # [apigen:versions]\n"
        "]\n"
    )
    deprecate_version(tmp_path, "v1", "2027-06-30", "2026-09-25")
    deprecate_version(tmp_path, "v1", "2027-12-31", "2026-09-25")  # segunda vez: actualiza
    info = version_info(tmp_path)
    assert info["v1"] == {"deprecated": True, "sunset": "2027-12-31", "since": "2026-09-25"}
    assert info["v2"]["deprecated"] is False
    text = (api / "versions.py").read_text()
    assert max(len(line) for line in text.splitlines()) <= 100


def test_version_add_validates_source(tmp_path):
    """--from también se valida: nada de rutas como `../x` (ronda 5, detalle menor)."""
    from typer.testing import CliRunner

    from apigen import cli
    from apigen.project import add_version

    result = CliRunner().invoke(cli.app, ["version", "add", "v3", "--from", "../app"])
    assert result.exit_code == 1 and "--from" in result.output
    with pytest.raises(SpecError):
        add_version(tmp_path, "v3", "../../etc")


def _action_spec(**overrides) -> ResourceSpec:
    data = {
        "name": "report",
        "owned": True,
        "fields": {"title": {"type": "str"}},
        "actions": [
            {"name": "export_pdf", "background": True, "fields": {"fmt": {"type": "str"}}},
            {"name": "preview"},
            {"name": "crunch", "scope": "collection", "background": True, "executor": "process"},
        ],
    }
    data.update(overrides)
    return ResourceSpec.model_validate(data)


def test_actions_get_secure_defaults():
    spec = _action_spec()
    perms = {a.name: a.permission for a in spec.actions}
    assert perms == {"export_pdf": "owner", "preview": "owner", "crunch": "user"}


@pytest.mark.parametrize(
    "action",
    [
        {"name": "task"},  # chocaría con el decorador importado
        {"name": "before_create"},
        {"name": "x", "background": True, "permission": "public"},  # llenar la cola
        {"name": "x", "scope": "collection", "permission": "owner"},
        {"name": "x", "fields": {"ref": {"type": "fk", "to": "user"}}},  # IDOR
        {"name": "x", "rate_limit": "lots"},
    ],
)
def test_invalid_actions_rejected(action):
    with pytest.raises(ValidationError):
        _spec(owned=True, actions=[action])


def test_duplicate_actions_rejected():
    with pytest.raises(ValidationError):
        _spec(actions=[{"name": "a"}, {"name": "a"}])


def test_actions_generate_endpoints_hooks_and_tasks(tmp_path):
    from apigen.codegen import hooks_module, tasks_module

    spec = _action_spec()
    router = next(
        r.content
        for r in render_resource(tmp_path, spec, {"report": spec})
        if "endpoints" in str(r.path)
    )
    assert '"/{item_id}/export_pdf"' in router and "HTTP_202_ACCEPTED" in router
    assert 'enqueue(\n        session,\n        "report.export_pdf"' in router
    assert "hooks.preview(" in router and "hooks.before_create(ctx, payload)" in router
    _, hooks_header, hooks = hooks_module(spec)
    assert "preview" in hooks and "export_pdf" not in hooks  # las de fondo van al worker
    _, tasks_header, tasks = tasks_module(spec)
    assert set(tasks) == {"export_pdf", "crunch"}
    assert 'executor="process"' in tasks["crunch"] and "def crunch(payload" in tasks["crunch"]
    for header, stubs in ((hooks_header, hooks), (tasks_header, tasks)):
        compile(header + "\n\n" + "\n\n".join(stubs.values()), "<stub>", "exec")


def test_user_modules_are_never_overwritten(tmp_path):
    from apigen.codegen import ensure_user_module, hooks_module

    spec = _action_spec()
    _, header, stubs = hooks_module(spec)
    path = tmp_path / "hooks.py"
    assert ensure_user_module(path, header, stubs)[0] == "created"
    custom = path.read_text().replace("    return data\n", "    raise ValueError('mine')\n", 1)
    path.write_text(custom)

    assert ensure_user_module(path, header, stubs) == ("unchanged", [])
    stubs["new_action"] = "async def new_action(ctx, obj, data):\n    return {}\n"
    state, added = ensure_user_module(path, header, stubs)
    assert (state, added) == ("appended", ["new_action"])
    assert path.read_text().startswith(custom.rstrip("\n"))  # tu código intacto

    path.write_text("def broken(:\n")
    assert ensure_user_module(path, header, stubs)[0] == "unparseable"
    assert path.read_text() == "def broken(:\n"
