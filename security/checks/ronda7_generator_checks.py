"""Ronda 7: acciones del generador (ActionSpec, router.py.j2, stubs de hooks/tareas).

    .venv/bin/python security/checks/ronda7_generator_checks.py

Solo renderiza en memoria (no escribe en el proyecto). Imprime OK/FALLO/INFO.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apigen.codegen import hooks_module, render_resource, tasks_module  # noqa: E402
from apigen.spec import ResourceSpec  # noqa: E402

results: list[str] = []


def check(label: str, ok: bool, detail: str = "", info: bool = False) -> None:
    status = "INFO" if info else ("OK" if ok else "FALLO")
    results.append(status)
    print(f"[{status}] {label} {('-> ' + detail) if detail else ''}", flush=True)


def spec(**kw) -> ResourceSpec:
    base = {"name": "note", "fields": {"title": {"type": "str", "max_length": 50}}}
    base.update(kw)
    return ResourceSpec.model_validate(base)


def accepted(**kw) -> tuple[bool, str]:
    try:
        return True, spec(**kw).model_dump_json()[:0]
    except Exception as exc:  # noqa: BLE001
        return False, str(exc).splitlines()[-1][:160] if str(exc) else type(exc).__name__


def router_src(s: ResourceSpec) -> str:
    files = render_resource(Path("/x"), s, {s.name: s}, with_tests=False)
    return next(f.content for f in files if "/endpoints/" in str(f.path))


# 1. Colisión del alias de permisos de una acción con los de CRUD ------------------
for action in ("read", "delete", "list", "update", "create"):
    ok, msg = accepted(
        permissions={"read": "admin", "list": "admin", "create": "admin",
                     "update": "admin", "delete": "admin"},
        actions=[{"name": action, "permission": "user"}],
    )
    if not ok:
        check(f"acción '{action}' rechazada (evita pisar Can{action.title()})", True, msg)
        continue
    s = spec(
        permissions={"read": "admin", "list": "admin", "create": "admin",
                     "update": "admin", "delete": "admin"},
        actions=[{"name": action, "permission": "user"}],
    )
    src = router_src(s)
    alias = f"Can{action.title()}"
    defs = re.findall(rf"^{alias} = .*$", src, flags=re.M)
    check(f"acción '{action}' (permission=user) NO redefine {alias} del CRUD (admin)",
          len(defs) == 1, " | ".join(defs))

# 2. Nombres de campo de entrada de una acción que chocan con Pydantic ----------------
for fname in ("model_config", "model_dump", "model_fields"):
    ok, msg = accepted(actions=[{"name": "go", "fields": {fname: {"type": "str"}}}])
    check(f"campo de acción '{fname}' rechazado", not ok, msg or "aceptado")

# 3. Permisos por defecto de las acciones ---------------------------------------------
s = spec(owned=True, actions=[{"name": "go"}, {"name": "bg", "background": True}])
perms = {a.name: a.permission for a in s.actions}
check("acción item en owned hereda update=owner (scoped)", perms == {"go": "owner", "bg": "owner"},
      str(perms))
ok, msg = accepted(owned=True, actions=[{"name": "go", "permission": "user"}])
warn = spec(owned=True, actions=[{"name": "go", "permission": "user"}]).warnings() if ok else []
check("owned + acción item con permission=user (BOLA) rechazada o avisada",
      (not ok) or any("go" in w for w in warn), f"aceptada={ok} avisos={warn}")
ok, msg = accepted(permissions={"create": "public", "list": "public", "read": "public"},
                   actions=[{"name": "bulk", "scope": "collection", "background": True}])
check("acción background que heredaría 'public' -> rechazada", not ok, msg)
ok, msg = accepted(permissions={"create": "public", "list": "public", "read": "public"},
                   actions=[{"name": "ping", "scope": "collection"}])
check("acción síncrona de colección hereda 'public' en silencio", True,
      f"aceptada={ok}", info=ok)

# 4. Inyección de código en los stubs vía description ---------------------------------
payloads = {
    "triple comilla + código": 'x"""\nimport os; os.system("id")\n"""',
    "barra final": "fin \\",
    "escape \\N": "ver \\N fin",
    "escape \\x": "hex \\x4 fin",
    "comillas mixtas": "a \"\"'\"\"\" b '''",
}
for label, desc in payloads.items():
    s = spec(actions=[{"name": "go", "background": True, "description": desc}])
    _, header, stubs = tasks_module(s)
    src = header + "\n\n" + "\n\n".join(stubs.values())
    try:
        tree = ast.parse(src)
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Import)
                 and any(a.name == "os" for a in n.names)]
        check(f"tasks stub, description '{label}': sin código inyectado", not calls,
              "compila")
    except SyntaxError as exc:
        check(f"tasks stub, description '{label}': sin código inyectado (pero no compila)",
              True, f"SyntaxError: {exc.msg}", info=True)
    rsrc = router_src(s)
    try:
        ast.parse(rsrc)
        check(f"router, description '{label}': compila (repr)", True)
    except SyntaxError as exc:
        check(f"router, description '{label}': compila (repr)", False, exc.msg)

# 5. Stubs de hooks: nombres controlados --------------------------------------------
s = spec(actions=[{"name": "go"}, {"name": "items", "scope": "collection"}])
_, header, stubs = hooks_module(s)
ast.parse(header + "\n\n" + "\n\n".join(stubs.values()))
check("hooks stub compila y solo usa nombres validados", set(stubs) >= {"go", "items"})
for bad in ("__init__", "Go", "os.system", "task", "before_create", "model_x", "import"):
    ok, msg = accepted(actions=[{"name": bad}])
    check(f"nombre de acción {bad!r} rechazado", not ok, msg)

print(f"\nResumen: {results.count('OK')} OK, {results.count('FALLO')} FALLO, "
      f"{results.count('INFO')} INFO")
