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
    assert 'executor="process"' in tasks["crunch"]
    assert "def crunch(ctx: TaskContext, payload" in tasks["crunch"]  # UX-53: recibe ctx
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


def _docs_project(tmp_path) -> Path:
    import shutil

    (tmp_path / "app/api").mkdir(parents=True)
    shutil.copy(ROOT / "app/api/versions.py", tmp_path / "app/api/versions.py")
    shutil.copy(ROOT / ".env.example", tmp_path / ".env.example")
    (tmp_path / "resources").mkdir()
    shutil.copy(ROOT / "examples/cursos.yaml", tmp_path / "resources/cursos.yaml")
    return tmp_path


def test_client_readme_is_generated_and_keeps_manual_text(tmp_path):
    """`apigen docs`: README.md para el cliente desde los recursos; conserva lo manual."""
    from apigen.docs import END, write_readme

    base = _docs_project(tmp_path)
    path, created, lang = write_readme(base, "en")
    text = path.read_text()
    assert created and lang == "en" and "<!-- apigen:docs:start lang=en" in text and END in text
    assert "`/api/v1/enrollments/{id}/certificate`" in text and "background (202)" in text
    assert "never returned" in text  # write_only
    assert "### Background jobs" in text

    custom = text.replace("Describe here what this API does", "Our custom intro")
    path.write_text(custom + "\nManual notes at the end.\n")
    _, created_again, _ = write_readme(base, "es")
    updated = path.read_text()
    assert not created_again
    assert "Our custom intro" in updated and "Manual notes at the end." in updated
    assert "### Autenticación" in updated  # sección regenerada en español
    assert updated.count("apigen:docs:start") == 1


def test_client_readme_remembers_language_and_base_url(tmp_path):
    """UX-52: `apigen docs` sin --lang conserva el idioma (y la URL base) elegidos."""
    from apigen.docs import write_readme

    base = _docs_project(tmp_path)
    write_readme(base, "es", base_url="https://api.cliente.com")
    path, _, lang = write_readme(base)
    text = path.read_text()
    assert lang == "es" and "## Guía de integración" in text
    assert "curl -X POST https://api.cliente.com/api/v1/auth/login" in text
    # README antiguo (marcador sin atributos, en español): se deduce el idioma.
    path.write_text("# X\n<!-- apigen:docs:start -->\n## Autenticación\n<!-- apigen:docs:end -->\n")
    assert write_readme(base)[2] == "es"


def test_client_readme_documents_integration_details(tmp_path):
    """Informe del usuario (ronda 7): respuesta del login, paginación, un ejemplo por
    recurso, qué devuelven las acciones, trabajos (cancelled, 409), arranque Docker
    completo y errores propios de los hooks (se extraen del código)."""
    from apigen.docs import write_readme

    base = _docs_project(tmp_path)
    (base / "app/hooks").mkdir(parents=True)
    (base / "app/hooks/course.py").write_text(
        "from app.core.exceptions import APIError\n"
        "async def before_create(ctx, data):\n"
        "    raise APIError(409, 'The course is full', code='course_full')\n"
    )
    text = write_readme(base, "en")[0].read_text()
    for expected in (
        '"token_type": "bearer"',  # respuesta del login
        '{"items": [...], "total": 42',  # forma de la paginación
        "curl -X POST http://127.0.0.1:8000/api/v1/courses",  # ejemplo por recurso
        "`200` → a JSON object",  # acción síncrona
        '"status_url"',  # acción en segundo plano
        "`cancelled`",
        "job_not_cancellable",
        "POSTGRES_PASSWORD",
        "openssl rand",
        "ALLOWED_HOSTS=",
        "| 409 | `course_full` | The course is full |",  # error propio, conservado
    ):
        assert expected in text, expected


def _files(spec: ResourceSpec, tmp_path) -> dict[str, str]:
    """Router y esquemas generados, por tipo."""
    out = {}
    for r in render_resource(tmp_path, spec, {spec.name: spec}):
        kind = r.path.parent.name
        out[{"endpoints": "router", "schemas": "schemas", "models": "model"}.get(kind, kind)] = (
            r.content
        )
    return out


@pytest.mark.parametrize("name", ["list", "read", "create", "update", "delete", "get"])
def test_actions_named_like_crud_operations_rejected(name):
    """SEC-31: una acción `read` redefinía `CanRead` y abría GET /{id} a su permiso."""
    with pytest.raises(ValidationError):
        _spec(actions=[{"name": name}])


def test_action_permission_aliases_cannot_override_crud(tmp_path):
    """SEC-31: los alias de las acciones tienen prefijo propio y se definen una vez."""
    spec = _spec(
        permissions={"read": "admin", "list": "admin"},
        actions=[{"name": "mark_read", "permission": "user"}, {"name": "archive"}],
    )
    router = _files(spec, tmp_path)["router"]
    assert router.count("CanRead = ") == 1
    assert "CanRead = Annotated[Principal, Depends(require(Access.admin, Scope.read))]" in router
    assert "CanAction_mark_read = Annotated[Principal, Depends(require(Access.user" in router
    # Nombres que PascalCase confundiría (a_1 / a1 -> A1) se detectan antes de generar.
    clash = _spec(actions=[{"name": "a_1"}, {"name": "a1"}])
    with pytest.raises(SpecError, match="nombres repetidos"):
        render_resource(tmp_path, clash, {"widget": clash})


def test_owned_item_actions_open_to_any_user_are_rejected(tmp_path):
    """SEC-32: en un recurso owned, una acción de item con permission=user cargaba filas
    ajenas (BOLA). Solo se admite con shared_read y lectura abierta."""
    for level in ("user", "public"):
        with pytest.raises(ValidationError, match="BOLA"):
            _spec(owned=True, actions=[{"name": "export", "permission": level}])
    shared = _spec(
        owned=True,
        shared_read=True,
        permissions={"read": "user"},
        actions=[
            {"name": "export", "permission": "user"},
            {"name": "audit", "permission": "admin"},
        ],
    )
    assert any("shared_read" in w for w in shared.warnings())

    def body(router: str, func: str) -> str:
        return router.split(f"async def {func}(")[1].split("\n@router")[0]

    router = _files(shared, tmp_path)["router"]
    assert "scoped=False" in body(router, "export_widget")  # shared_read: a propósito
    assert "scoped=False" in body(router, "audit_widget")  # admin: cualquiera
    owned = _files(_action_spec(), tmp_path)["router"]
    assert "scoped=True" in body(owned, "preview_report")  # owner: solo lo suyo


def test_action_input_fields_and_descriptions_are_validated():
    """SEC-38: nombres de pydantic en la entrada de una acción y `\\` en la descripción."""
    from apigen.codegen import tasks_module

    for fname in ("model_config", "model_dump", "json", "copy"):
        with pytest.raises(ValidationError):
            _spec(actions=[{"name": "x", "fields": {fname: {"type": "str"}}}])
    spec = _action_spec(
        actions=[{"name": "export", "background": True, "description": r"Ruta C:\Nuevo \x4 \N"}]
    )
    _, header, stubs = tasks_module(spec)
    compile(header + "\n\n" + "\n\n".join(stubs.values()), "<stub>", "exec")


def test_sync_actions_commit_reject_unknown_body_and_allow_empty_body(tmp_path):
    """UX-54/56/57: la acción síncrona guarda sus cambios; un cuerpo con campos
    desconocidos da 422 y, sin campos obligatorios, el cuerpo es opcional."""
    spec = _action_spec(
        actions=[
            {"name": "check_in"},
            {"name": "remind", "fields": {"channel": {"type": "str", "nullable": True}}},
            {"name": "rename", "fields": {"title": {"type": "str"}}},
        ]
    )
    files = _files(spec, tmp_path)
    router, schemas = files["router"], files["schemas"]
    assert "await session.commit()" in router
    assert "payload: Annotated[ReportCheckInInput, Body(default_factory=ReportCheckInInput)]" in (
        router
    )
    assert "payload: ReportRenameInput," in router
    assert "class ReportCheckInInput(StrictInput):" in schemas


def test_background_actions_without_rate_limit_warn():
    spec = _action_spec()
    assert any("sin rate_limit" in w for w in spec.warnings())


def test_each_resource_has_a_single_spec_file(tmp_path):
    """UX-50: un YAML con varios recursos en resources/ es la fuente de esos recursos:
    no se escriben copias por recurso, los duplicados son un error y una definición
    distinta (p. ej. desde `apigen add`) se rechaza en vez de pisar a la otra."""
    import yaml

    from apigen.project import check_spec_sources, save_spec

    resources = tmp_path / "resources"
    resources.mkdir()
    gym = {
        "resources": [
            {"name": "gym_class", "fields": {"title": {"type": "str"}}},
            {"name": "booking", "owned": True, "fields": {"notes": {"type": "text"}}},
        ]
    }
    (resources / "gym.yaml").write_text("# mis comentarios\n" + yaml.safe_dump(gym))
    specs = load_specs(resources)
    sources = check_spec_sources(tmp_path, specs)  # generar desde gym.yaml: válido
    for spec in specs:
        assert "gym.yaml (fuente de" in save_spec(tmp_path, spec, sources)
    assert sorted(p.name for p in resources.iterdir()) == ["gym.yaml"]

    changed = _spec(name="booking", owned=True, fields={"notes": {"type": "str"}})
    with pytest.raises(SpecError, match="ya está definido en resources/gym.yaml"):
        check_spec_sources(tmp_path, [changed])

    (resources / "booking.yaml").write_text(yaml.safe_dump(gym["resources"][1]))
    with pytest.raises(SpecError, match="booking.* en booking.yaml y en gym.yaml"):
        load_specs(resources)


def test_saving_an_unchanged_spec_keeps_comments(tmp_path):
    """UX-66: si el YAML ya tiene esa definición no se reescribe (conserva tu formato)."""
    from apigen.project import save_spec

    resources = tmp_path / "resources"
    resources.mkdir()
    text = "# Mi recurso\nname: widget\nfields: {title: {type: str}}  # corto\n"
    (resources / "widget.yaml").write_text(text)
    assert save_spec(tmp_path, _spec()).endswith("(sin cambios)")
    assert (resources / "widget.yaml").read_text() == text
    assert "unique: false" not in _spec_yaml_for_action()


def _spec_yaml_for_action() -> str:
    from apigen.spec import spec_to_yaml

    return spec_to_yaml(_spec(actions=[{"name": "go", "fields": {"channel": {"type": "str"}}}]))


def test_only_accepts_commas_and_lists_available_resources(tmp_path, monkeypatch):
    """UX-59: `--only a,b` funciona y, si no coincide, dice qué recursos hay."""
    from typer.testing import CliRunner

    from apigen import cli

    captured = {}
    monkeypatch.setattr(cli, "_generate", lambda specs, **kw: captured.setdefault("s", specs))
    runner = CliRunner()
    shop = str(ROOT / "examples/shop.yaml")
    result = runner.invoke(cli.app, ["generate", shop, "--only", "category,product"])
    assert result.exit_code == 0, result.output
    assert [s.name for s in captured["s"]] == ["category", "product"]
    missing = runner.invoke(cli.app, ["generate", shop, "--only", "nope"])
    assert missing.exit_code == 1 and "Recursos disponibles: category" in missing.output


async def test_ordering_parameter_gets_a_hint():
    """UX-60: `?ordering=` (la clave del YAML) da 422 con la pista de `order_by`."""
    from fastapi import HTTPException
    from starlette.requests import Request

    from app.api.deps import query_guard

    guard = query_guard(frozenset({"limit", "offset", "order_by"}), frozenset({"title"}))
    request = Request({"type": "http", "query_string": b"ordering=-title", "headers": []})
    with pytest.raises(HTTPException) as exc:
        await guard(request)
    assert "use order_by" in exc.value.detail[0]["msg"]
