#!/usr/bin/env python3
"""Crea una API nueva a partir de esta plantilla, lista para desarrollar y entregar.

    python3 scripts/new_api.py cursos-api
    python3 scripts/new_api.py tienda-api --title "Tienda API" --lang es --dir ~/Developer
    python3 scripts/new_api.py tienda-api --email-verification required --password-reset \
        --frontend-url https://app.tienda.example

Qué hace:
1. Exige que la plantilla no tenga cambios sin commit (o `--allow-dirty`) y copia
   SOLO los ficheros versionados, sin lo personal ni lo interno: informes de
   seguridad, guía personal, grafo, `.claude/settings.json`, README de la
   plantilla y este script. Nunca copia ficheros sin versionar (SEC-35).
2. Renombra el proyecto (pyproject, uv.lock, PROJECT_NAME, JWT issuer/audience).
3. Genera README.md para el cliente (`apigen docs`), un CLAUDE.md y
   `docs/DESARROLLO.txt` (referencia de apigen para desarrollar sin la plantilla).
4. Instala dependencias, crea `.env` (no versionado) con la configuración de correo
   pedida (verificación de email, recuperación, FRONTEND_URL, idioma), pasa los tests
   y construye el grafo de graphify (si está instalado). Los valores reales del
   cliente solo van al `.env`, nunca a ficheros versionados.
5. Justo antes del commit inicial revisa TODOS los ficheros de texto que se van a
   versionar: datos personales (rutas de usuario, emails reales) y secretos
   (claves privadas, sk_live_, AWS, tokens...). Si encuentra algo, no hace commit.

Solo usa la librería estándar (funciona con cualquier Python 3.9+).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent
NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,50}$")
URL_RE = re.compile(r"^https?://[A-Za-z0-9.\-]+(:\d{1,5})?(/[A-Za-z0-9._~\-/]*)?$")

# Prefijos (rutas relativas) que NO van al proyecto nuevo.
EXCLUDE = (
    "security/reports/",  # revisión interna de la plantilla
    "security/checks/",
    "security/REVISION_SEGURIDAD.md",
    "guia/",  # guía de la plantilla (lo útil para desarrollar va a docs/DESARROLLO.txt)
    "graphify-out/",  # se reconstruye para el proyecto nuevo
    ".claude/settings.json",  # hooks locales con rutas de tu máquina
    ".claude/settings.local.json",
    "scripts/",  # herramientas de la plantilla
    "tests/test_new_api.py",  # test de este script (contiene secretos falsos a propósito)
    "README.txt",  # documentación de la plantilla: el proyecto lleva README.md para el cliente
    "README.md",  # presentación (portafolio) de la plantilla: `apigen docs` crea el del cliente
    "CLAUDE.md",  # se genera uno propio del proyecto
    "resources/",  # el proyecto empieza sin recursos
)
# Código de recursos generados: si la plantilla los tiene versionados, serían de otro
# cliente (modelos, hooks, migraciones...). La plantilla solo trae estos.
BASE_ENDPOINTS = {"__init__.py", "account.py", "auth.py", "jobs.py", "users.py"}

# --- datos personales y secretos -------------------------------------------------
_EMAIL = re.compile(r"(?<![\w.+:/-])[A-Za-z0-9_.+-]+@(?P<domain>[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
# Dominios de ejemplo o reservados (RFC 2606/6761): no son datos de nadie.
_SAFE_DOMAINS = re.compile(
    r"(^|\.)(example\.(com|org|net)|example|test|invalid|localhost|local|internal)$", re.I
)
PERSONAL = [
    ("ruta de usuario", re.compile(r"/Users/[A-Za-z0-9_.-]+")),
    ("ruta de usuario", re.compile(r"/home/[A-Za-z0-9_.-]+/")),
    ("ruta de usuario", re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9_.-]+")),
]
SECRETS = [
    ("clave privada", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY( BLOCK)?-----")),
    ("clave de Stripe", re.compile(r"\b[sr]k_live_[0-9A-Za-z]{8,}")),
    ("clave de AWS", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("token de GitHub", re.compile(r"\b(ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{30,}|github_pat_\w{20,}")),
    ("token de GitLab", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}")),
    ("token de Slack", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("clave de Google", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("clave de OpenAI/Anthropic", re.compile(r"\bsk-(ant-|proj-)?[A-Za-z0-9_-]{32,}")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    (
        "secreto con valor",
        re.compile(
            r"^[ \t]*[A-Z0-9_]*(SECRET|PASSWORD|TOKEN|API_KEY|PRIVATE_KEY)[A-Z0-9_]*"
            r"[ \t]*[=:][ \t]*"
            # Valor aleatorio (20+ caracteres con algún dígito): no "correct-horse-staple".
            r"[\"']?(?!change-me)(?=[A-Za-z0-9_+/=.-]*\d)[A-Za-z0-9_+/=.-]{20,}",
            re.M,
        ),
    ),
    ("contraseña en una URL", re.compile(r"://[^\s:@/]+:(?![^@\s]*[$<{])[^\s@/]{12,}@")),
]
# Ficheros que nunca deben versionarse, sean de texto o binarios.
FORBIDDEN_NAMES = re.compile(
    r"(^|/)(\.env(\.(?!example$)[^/]+)?|id_(rsa|dsa|ecdsa|ed25519)(\.pub)?|credentials[^/]*\.json)$"
    r"|\.(pem|key|p12|pfx|jks|kdbx|sqlite3?|db|dump|sql)$"
)
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules"}
LOCAL_ONLY = (
    "graphify-out/cache/", "graphify-out/.graphify_root", "graphify-out/.graphify_python",
    "graphify-out/cost.json", "graphify-out/graph.html", "loadtests/reports/",
)  # fmt: skip


def say(msg: str) -> None:
    print(f"==> {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"✗ {msg}", file=sys.stderr)
    raise SystemExit(1)


def run(cmd: list[str], cwd: Path, check: bool = True, quiet: bool = True) -> int:
    result = subprocess.run(cmd, cwd=cwd, capture_output=quiet, text=True)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-2000:] if quiet else ""
        fail(f"falló: {' '.join(cmd)}\n{detail}")
    return result.returncode


def git(template: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=template, capture_output=True, text=True, check=True
    ).stdout


def tracked_files(template: Path = TEMPLATE) -> list[str]:
    """Solo lo versionado (nunca ficheros nuevos sin commit: SEC-35)."""
    return [f for f in git(template, "ls-files", "-z", "--cached").split("\0") if f]


def dirty_files(template: Path = TEMPLATE) -> list[str]:
    """Cambios sin commit (modificados o nuevos) fuera de lo que no se copia."""
    entries = git(template, "status", "--porcelain", "-z", "--untracked-files=all").split("\0")
    paths: list[str] = []
    skip_next = False
    for entry in entries:
        if skip_next:  # origen de un renombrado
            skip_next = False
            continue
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        skip_next = "R" in status or "C" in status
        if not path.startswith(EXCLUDE):
            paths.append(path)
    return paths


def generated_resources(files: list[str]) -> list[str]:
    """Código de recursos generados entre los ficheros a copiar (de otro cliente)."""
    found = []
    for rel in files:
        parts = rel.split("/")
        name = parts[-1]
        if (
            (rel.startswith(("app/hooks/", "app/tasks/resources/")) and name != "__init__.py")
            or (rel.startswith("app/api/v") and "/endpoints/" in rel and name not in BASE_ENDPOINTS)
            or (rel.startswith("tests/api/v") and name.startswith("test_"))
        ):
            found.append(rel)
    return found


def scan_text(rel: str, text: str) -> list[str]:
    problems = []
    for label, pattern in PERSONAL + SECRETS:
        for match in pattern.finditer(text):
            value = match.group(0).strip()
            shown = value if label in {"ruta de usuario"} else value[:12] + "…"
            problems.append(f"{rel}: {label}: {shown}")
    for match in _EMAIL.finditer(text):
        if not _SAFE_DOMAINS.search(match.group("domain")):
            problems.append(f"{rel}: email: {match.group(0)}")
    return problems


def scan_files(root: Path, files: list[str]) -> list[str]:
    """Datos personales y secretos en los ficheros indicados (de texto: todos, sin
    filtrar por extensión) y ficheros que nunca deben versionarse."""
    problems: list[str] = []
    for rel in files:
        path = root / rel
        if not path.is_file():
            continue
        if FORBIDDEN_NAMES.search(rel):
            problems.append(f"{rel}: fichero que no debe versionarse (clave, credenciales o BD)")
            continue
        data = path.read_bytes()
        if b"\0" in data[:8192]:
            continue  # binario (imágenes...): lo cubre FORBIDDEN_NAMES por su nombre
        problems += scan_text(rel, data.decode("utf-8", errors="ignore"))
    return problems


def all_files(root: Path) -> list[str]:
    """Ficheros del proyecto (sin git): todo menos entornos, cachés y el .env local."""
    out = []
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if path.is_file() and not SKIP_DIRS.intersection(rel.parts) and rel.name != ".env":
            posix = rel.as_posix()
            # BD local de desarrollo y lo local de graphify (ignorados por .gitignore).
            if rel.suffix in {".db", ".db-shm", ".db-wal"} or posix.startswith(LOCAL_ONLY):
                continue
            out.append(posix)
    return sorted(out)


def check_clean(target: Path, files: list[str], when: str) -> None:
    problems = scan_files(target, files)
    if problems:
        shown = "\n  ".join(problems[:40]) + ("\n  ..." if len(problems) > 40 else "")
        fail(f"datos personales o secretos {when} (no se ha hecho commit):\n  {shown}")


def default_title(name: str) -> str:
    words = [w.upper() if w in {"api", "crm", "erp"} else w.capitalize() for w in name.split("-")]
    return " ".join(words)


def replace_in(path: Path, pairs: list[tuple[str, str]]) -> None:
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


def _sections(text: str) -> dict[int, tuple[str, str]]:
    """Secciones `N. TÍTULO` (entre líneas de guiones) de README.txt / guia/README.txt."""
    pattern = re.compile(r"^-{20,}\n(\d+)\. ([^\n]+)\n-{20,}\n", re.M)
    matches = list(pattern.finditer(text))
    out = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[int(m.group(1))] = (m.group(2).strip(), text[m.end() : end].rstrip() + "\n")
    return out


def developer_docs(template: Path) -> str:
    """docs/DESARROLLO.txt: lo necesario para desarrollar con apigen sin la plantilla
    (UX-62). Mantiene los números originales para que las referencias sigan valiendo."""
    parts = [
        "=" * 80,
        "  DESARROLLO CON apigen  ·  referencia copiada de la plantilla al crear el proyecto",
        "=" * 80,
        "",
        "Recursos en YAML, permisos, hooks, acciones, worker, versiones, base de datos y",
        "graphify. Las secciones conservan su número original (README §N / guía §N).",
        "",
    ]
    wanted = (
        ("README.txt", "README", (4, 5, 7, 8, 11, 12, 15)),
        ("guia/README.txt", "guía", (2, 3, 5, 6, 7, 12, 14, 15, 17)),
    )
    for rel, label, numbers in wanted:
        source = template / rel
        if not source.exists():
            continue
        sections = _sections(source.read_text(encoding="utf-8"))
        for n in numbers:
            if n in sections:
                title, body = sections[n]
                parts += ["-" * 80, f"{label} §{n}. {title}", "-" * 80, body]
    return "\n".join(parts)


def _env_value(value: str) -> str:
    """Valor seguro para .env/.env.example: sin saltos de línea, comillas, `\\` ni `$`
    (python-dotenv interpolaría `${...}`; Info-5), entre comillas si lleva espacios."""
    clean = re.sub(r"[\r\n'\"\\$]", "", value)
    return f'"{clean}"' if re.search(r"[\s#]", clean) else clean


def configure_email(target: Path, args: argparse.Namespace, title: str) -> None:
    """Configuración de correo NO secreta del cliente (modos, idioma, marca, FRONTEND_URL)
    en `.env.example`, que se versiona y recibe el cliente, y en `.env` si ya existe: así
    el entregable hace lo que dice su README (UX-67). Credenciales y remitente, nunca:
    solo en el `.env` de cada despliegue."""
    enabled = args.email_verification != "off" or args.password_reset
    values = {
        "EMAIL_VERIFICATION": args.email_verification,
        "PASSWORD_RESET": "on" if args.password_reset else "off",
        "MAIL_DEFAULT_LANGUAGE": args.lang,
        "MAIL_BRAND_NAME": title,
    }
    if args.frontend_url:
        values["FRONTEND_URL"] = args.frontend_url
    for name in (".env.example", ".env"):
        env_file = target / name
        if not env_file.exists():
            continue
        text = env_file.read_text(encoding="utf-8")
        for key, value in values.items():
            line = f"{key}={_env_value(value)}"
            text, count = re.subn(rf"^{key}=.*$", lambda _m, line=line: line, text, flags=re.M)
            if not count:
                text += f"\n{line}\n"
        env_file.write_text(text, encoding="utf-8")
    if enabled:
        say(
            f"Correo: verificación={args.email_verification}, recuperación="
            f"{values['PASSWORD_RESET']} (en .env.example; en desarrollo los correos salen "
            "en el log)"
        )


def fix_references(target: Path) -> None:
    """Referencias que en el proyecto nuevo apuntarían a ficheros de la plantilla (UX-63)."""
    makefile = target / "Makefile"
    if makefile.exists():
        text = makefile.read_text(encoding="utf-8")
        text = re.sub(r"\nnew-api:[^\n]*\n\t[^\n]*\n", "\n", text)  # el script no se copia
        text = text.replace(" new-api", "")
        text = text.replace("ver README §", "ver docs/DESARROLLO.txt, README §")
        makefile.write_text(text, encoding="utf-8")
    pyproject = target / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    text = re.sub(r'\n# Scripts de la plantilla[^\n]*\n"scripts/\*\*" = [^\n]*', "", text)
    pyproject.write_text(text, encoding="utf-8")


def claude_md(title: str, lang: str, template: Path) -> str:
    graphify_section = ""
    source = template / "CLAUDE.md"
    if source.exists():
        text = source.read_text(encoding="utf-8")
        if "## graphify" in text:
            graphify_section = "\n" + text[text.index("## graphify") :].strip() + "\n"
    return f"""# {title}

API construida con FastAPI + SQLModel async + JWT + SlowAPI y el generador `apigen`.
Referencia completa para desarrollar: `docs/DESARROLLO.txt` (YAML, hooks, acciones,
worker, versiones). README.md es para el cliente (lo genera `apigen docs`).

## Cómo trabajar aquí
- Recursos: `resources/*.yaml` → `apigen generate resources --migrate` (o `apigen add ...`).
  Un recurso se define en UN solo fichero: si usas un YAML con varios recursos,
  edítalo a él (apigen no crea copias por recurso). Tras editar:
  `apigen generate resources --force --only <recurso>`.
- Lógica de negocio: `app/hooks/<recurso>.py` (apigen nunca lo sobrescribe).
- Procesos pesados: acciones `background: true` en el YAML → `app/tasks/resources/`,
  ejecutadas por `apigen worker` (cola en la tabla `jobs`). En tests: `process_pending()`.
- Correo (verificación de email, recuperación de contraseña, `app.email.send_email`):
  configuración SOLO en `.env` (EMAIL_*, SMTP_*, MAIL_*, FRONTEND_URL); plantillas propias
  en `email_templates/` (`apigen email eject/preview/test`); en local, `make mail` (Mailpit).
  Tests sin correos reales: fixture `mail` (backend memory) + `process_pending()`.
- Datos personales: marca `pii`/`sensitive` por campo y `purpose:` por recurso (inventario en
  `docs/DATA_INVENTORY.md`, se actualiza solo; CI lo comprueba). `sensitive` = solo dueño/admin,
  cifrado en la BD (DATA_ENCRYPTION_KEY). Cumplimiento: `docs/CUMPLIMIENTO_SOC2_ISO27701.md`.
- Antes de dar algo por terminado: `uv run pytest` y `uv run ruff check .`.
- Al terminar (o al cambiar recursos): `uv run apigen docs` regenera README.md para el
  cliente (recuerda el idioma, `{lang}`; los errores `APIError(..., code=...)` de los hooks
  salen solos). Entrega: `make deliver` (zip sin herramientas internas).
- Comentarios en español, identificadores en inglés, ruff line-length 100.
- Agentes de revisión en `.claude/agents/`; laboratorio aislado: `./security/lab.sh <puerto>`.
- No usar `SlowAPIMiddleware`: con FastAPI >= 0.140 no aplica límites
  (se usan dependencias globales en `app/core/rate_limit.py`).
{graphify_section}"""


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Crea una API nueva desde la plantilla")
    parser.add_argument("name", help="nombre del proyecto en kebab-case, p. ej. cursos-api")
    parser.add_argument("--dir", default="~/Developer", help="carpeta padre (defecto ~/Developer)")
    parser.add_argument("--title", help="nombre visible (defecto: a partir del nombre)")
    parser.add_argument("--lang", choices=["en", "es"], default="en", help="idioma del README.md")
    parser.add_argument(
        "--email-verification",
        choices=["off", "optional", "required"],
        default="off",
        help="verificación de email al registrarse (defecto off)",
    )
    parser.add_argument(
        "--password-reset", action="store_true", help="activar la recuperación de contraseña"
    )
    parser.add_argument(
        "--frontend-url",
        help="URL del frontend del cliente para los enlaces de los correos (va al .env)",
    )
    parser.add_argument("--no-install", action="store_true", help="no ejecutar uv sync ni tests")
    parser.add_argument("--no-git", action="store_true", help="no inicializar el repo git")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="seguir aunque la plantilla tenga cambios sin commit (solo se copia lo versionado)",
    )
    parser.add_argument("--template", default=str(TEMPLATE), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    template = Path(args.template).resolve()

    if not NAME_RE.match(args.name):
        fail(
            "nombre inválido: de 2 a 51 caracteres, empieza por letra; minúsculas, números "
            "y guiones (p. ej. 'cursos-api')"
        )
    if args.frontend_url and not URL_RE.match(args.frontend_url):
        fail("--frontend-url debe ser una URL http(s):// sin espacios, query ni fragmento")
    target = Path(os.path.expanduser(args.dir)).resolve() / args.name
    if target.exists():
        fail(f"{target} ya existe")
    if not (template / ".git").exists():
        fail("la plantilla debe ser un repositorio git (se copian los ficheros versionados)")
    title = args.title or default_title(args.name)

    # 0. Plantilla sin cambios a medias: se copia lo versionado, y solo lo versionado.
    dirty = dirty_files(template)
    if dirty:
        shown = "\n  ".join(dirty[:20]) + ("\n  ..." if len(dirty) > 20 else "")
        if not args.allow_dirty:
            fail(
                "la plantilla tiene cambios sin commit (haz commit o descártalos; "
                f"--allow-dirty para seguir sin ellos):\n  {shown}"
            )
        print(
            "  ! cambios sin commit en la plantilla: los ficheros nuevos NO se copian y los "
            f"modificados se copian tal como están:\n  {shown}"
        )
    files = [f for f in tracked_files(template) if not f.startswith(EXCLUDE)]
    foreign = generated_resources(files)
    if foreign:
        fail(
            "la plantilla tiene versionado código de recursos generados (¿de otro cliente?): "
            "quítalo de la plantilla antes de crear el proyecto:\n  " + "\n  ".join(foreign)
        )
    check_clean(template, files, "en la plantilla")

    # 1. Copia
    say(f"Creando {target}")
    for rel in files:
        src, dst = template / rel, target / rel
        if not src.exists():  # borrado localmente pero aún versionado
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst, follow_symlinks=False)
    (target / "resources").mkdir(exist_ok=True)
    (target / "resources" / ".gitkeep").touch()

    # 2. Renombrado
    say(f"Renombrando proyecto: {args.name} ({title})")
    replace_in(
        target / "pyproject.toml",
        [
            ('name = "api-template"', f'name = "{args.name}"'),
            ('readme = "README.txt"', 'readme = "README.md"'),
        ],
    )
    pyproject = target / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    text = re.sub(r'^description = ".*"$', f'description = "{title}"', text, count=1, flags=re.M)
    pyproject.write_text(text, encoding="utf-8")
    # README.md provisional (hatchling lo exige para instalar); `apigen docs` lo rellena.
    (target / "README.md").write_text(f"# {title}\n", encoding="utf-8")
    if (target / "uv.lock").exists():
        replace_in(target / "uv.lock", [('name = "api-template"', f'name = "{args.name}"')])
    identity = [
        ('"API Template"', f'"{title}"'),
        ("api-template-clients", f"{args.name}-clients"),
        ("=api-template", f"={args.name}"),
        ('"api-template"', f'"{args.name}"'),
    ]
    for rel in ("app/core/config.py", ".env.example"):
        if (target / rel).exists():
            replace_in(target / rel, identity)
    configure_email(target, args, title)  # antes de init-env: el .env parte de aquí

    # 3. Documentación para desarrollar (el cliente recibe README.md)
    (target / "CLAUDE.md").write_text(claude_md(title, args.lang, template), encoding="utf-8")
    (target / "docs").mkdir(exist_ok=True)
    (target / "docs" / "DESARROLLO.txt").write_text(developer_docs(template), encoding="utf-8")
    fix_references(target)
    check_clean(target, all_files(target), "en el proyecto nuevo")

    # 4. Dependencias, .env, README y tests
    uv = shutil.which("uv")
    if args.no_install or uv is None:
        if uv is None:
            print("  (uv no está instalado: omito instalación y tests)")
        python = template / ".venv" / "bin" / "python"
        env = {**os.environ, "PYTHONPATH": str(target)}
        if python.exists():
            for command in (["init-env"], ["docs", "--lang", args.lang]):
                subprocess.run(
                    [str(python), "-m", "apigen.cli", *command],
                    cwd=target, env=env, capture_output=True, check=False,
                )  # fmt: skip
    else:
        say("Instalando dependencias (uv sync)")
        run([uv, "sync", "-q"], target)
        run([uv, "run", "apigen", "init-env"], target)
        say(f"Generando README.md para el cliente ({args.lang})")
        run([uv, "run", "apigen", "docs", "--lang", args.lang], target)
        say("Pasando los tests")
        run([uv, "run", "pytest", "-q", "-p", "no:cacheprovider"], target)

    # 5. Grafo (opcional)
    graphify = shutil.which("graphify")
    if graphify:
        say("Construyendo el grafo de código (graphify, sin coste de tokens)")
        if run([graphify, "update", "."], target, check=False) != 0:
            print("  (graphify no pudo construir el grafo: ejecuta /graphify . en Claude Code)")

    # 6. Revisión final (README y grafo incluidos) y commit
    say("Comprobando que no hay datos personales ni secretos")
    if args.no_git:
        check_clean(target, all_files(target), "en el proyecto nuevo")
    else:
        say("Inicializando git")
        run(["git", "init", "-b", "main", "-q"], target)
        for key in ("user.name", "user.email"):
            has = subprocess.run(
                ["git", "config", key], cwd=target, capture_output=True, text=True
            ).stdout.strip()
            if not has:
                value = subprocess.run(
                    ["git", "config", key], cwd=template, capture_output=True, text=True
                ).stdout.strip()
                if value:
                    run(["git", "config", key, value], target)
                    print(f"  (identidad del commit copiada de la plantilla: {key}={value})")
        run(["git", "add", "-A"], target)
        tracked = [f for f in git(target, "ls-files", "-z").split("\0") if f]
        if ".env" in tracked:
            fail(".env no debe versionarse (revisa .gitignore)")
        check_clean(target, tracked, "en los ficheros a versionar")
        if run(["git", "commit", "-q", "-m", f"{title}: proyecto inicial desde la plantilla"],
               target, check=False) != 0:  # fmt: skip
            print("  (git sin identidad: configura user.name/user.email y haz el primer commit)")

    print(
        f"""
✓ {title} creada en {target}

Siguientes pasos:
  cd {target}
  # 1. Define los recursos en resources/*.yaml (ver examples/ y docs/DESARROLLO.txt)
  uv run apigen generate resources --migrate
  # 2. Lógica en app/hooks/ · procesos pesados en app/tasks/resources/
  uv run pytest
  make dev            # API     ·  make worker  # tareas en segundo plano
  # 3. Al terminar: documentación para el cliente (recuerda el idioma: {args.lang})
  uv run apigen docs
"""
    )


if __name__ == "__main__":
    main()
