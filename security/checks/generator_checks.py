"""Comprobaciones de seguridad del generador `apigen` (ronda 1).

No escribe en el proyecto: renderiza en memoria y compila/importa en un
directorio temporal. Uso:

    .venv/bin/python security/checks/generator_checks.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from apigen.codegen import render_resource  # noqa: E402
from apigen.spec import ResourceSpec, SpecError  # noqa: E402


def spec(**kw) -> ResourceSpec:
    return ResourceSpec.model_validate(kw)


def try_spec(desc: str, **kw) -> ResourceSpec | None:
    try:
        s = spec(**kw)
        print(f"[ACEPTA ] {desc}  -> permisos {s.permissions.model_dump()}")
        return s
    except (ValueError, SpecError) as exc:
        first = str(exc).splitlines()[1:3]
        print(f"[RECHAZA] {desc}  -> {' '.join(x.strip() for x in first)}")
        return None


def compiles(s: ResourceSpec, others: dict[str, ResourceSpec] | None = None) -> str:
    specs = {s.name: s, **(others or {})}
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        for f in render_resource(Path(tmp), s, specs, with_tests=False):
            try:
                compile(f.content, str(f.path), "exec")
            except SyntaxError as exc:
                problems.append(f"{f.path.name}: SyntaxError {exc.msg}")
    return "; ".join(problems) or "compila"


print("== 1. Inyección de código vía YAML (literales) ==")
evil = 'x"""\n__import__("os").system("id")\n"""'
s = try_spec(
    "description/pattern/enum con comillas y saltos de línea",
    name="evil",
    description=evil[:300],
    fields={
        "title": {"type": "str", "description": evil, "pattern": "^'''\"\"\"$", "example": "'''\"\"\""},
        "kind": {"type": "enum", "choices": ["a-b", "class", "None"]},
        "meta": {"type": "json", "default": {"k": "'); import os; ('"}},
    },
)
if s:
    out = render_resource(Path("/tmp/x"), s, {"evil": s}, with_tests=False)
    joined = "\n".join(f.content for f in out)
    print("   system(...) aparece solo dentro de literales:",
          all(("'" in line or '"' in line) for line in joined.splitlines() if "system" in line))
    print("  ", compiles(s))
for bad in ("x; import os", "a\nb", "__class__", "model_config", "id", "owner_id"):
    try_spec(f"nombre de campo {bad!r}", name="t1", fields={bad: {"type": "str"}})
try_spec("nombre de recurso con '../'", name="../etc", fields={"a": {"type": "str"}})
try_spec("enum con espacio/comillas", name="t2", fields={"k": {"type": "enum", "choices": ["a b", "x'"]}})

print("\n== 2. Nombres que colisionan (robustez del código generado) ==")
for fname in ("session", "principal", "page", "order_by", "request", "status", "uuid", "json", "copy"):
    s = try_spec(f"campo filtrable {fname!r}", name="t3", fields={fname: {"type": "str"}}, filters=[fname])
    if s:
        print("  ", compiles(s))
s = try_spec("enum con miembros especiales", name="t4",
             fields={"k": {"type": "enum", "choices": ["_missing_", "mro", "__init__"]}})
if s:
    print("  ", compiles(s))
    with tempfile.TemporaryDirectory() as tmp:
        model = render_resource(Path(tmp), s, {"t4": s}, with_tests=False)[0].content
        ns: dict = {}
        try:
            exec(compile(model.split("class T4(")[0], "m", "exec"), ns)  # noqa: S102
            print("   enum importa; miembros:", list(ns["T4K"].__members__))
        except Exception as exc:  # noqa: BLE001
            print("   enum falla al importar:", type(exc).__name__, exc)
try_spec("pattern con look-around (válido en Python, no en el motor Rust de pydantic)",
         name="t5", fields={"c": {"type": "str", "pattern": "^(?=A)[A-Z]{3}$", "example": "ABC"}})

print("\n== 3. Permisos inseguros que el validador acepta ==")
f = {"title": {"type": "str"}}
try_spec("owned + update=user (cualquier usuario modifica filas ajenas)", name="p1", owned=True,
         fields=f, permissions={"update": "user", "delete": "user"})
try_spec("owned + list/read=public (expone filas y owner_id de todos)", name="p2", owned=True,
         fields=f, permissions={"list": "public", "read": "public"})
try_spec("owned + list=owner pero read=user (incoherente: BOLA por ID)", name="p3", owned=True,
         fields=f, permissions={"read": "user"})
try_spec("no owned + create=public (alta anónima)", name="p4", fields=f,
         permissions={"create": "public"})
try_spec("no owned + update=user (cualquier usuario edita todo)", name="p5", fields=f,
         permissions={"update": "user"})

print("\n== 4. Claves foráneas ==")
parent_admin = spec(name="secret_doc", fields=f, permissions={"list": "admin", "read": "admin"})
child = spec(name="note", owned=True, fields={"doc_id": {"type": "fk", "to": "secret_doc"},
                                              "assignee_id": {"type": "fk", "to": "user", "nullable": True}})
out = render_resource(Path("/tmp/x"), child, {"note": child, "secret_doc": parent_admin}, with_tests=False)
router = next(x.content for x in out if "endpoints" in str(x.path))
print("   FK a recurso solo-admin -> ensure_reference owner_id=None (usuario puede enlazar/sondear):",
      "owner_id=None" in router)
print("   FK a 'user' sin comprobación de referencia:", "assignee_id" not in router.split("_check_references")[1]
      if "_check_references" in router else True)
