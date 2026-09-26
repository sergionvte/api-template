"""scripts/new_api.py: solo copia lo versionado y no deja pasar secretos ni datos
personales al repositorio del cliente (SEC-35)."""

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git no está instalado")


def _load():
    spec = importlib.util.spec_from_file_location("new_api", ROOT / "scripts/new_api.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)  # noqa: S603, S607


@pytest.fixture
def template(tmp_path) -> Path:
    """Plantilla mínima en un repo git temporal (todo versionado y limpio)."""
    repo = tmp_path / "template"
    repo.mkdir()
    for rel in ("pyproject.toml", "uv.lock", ".env.example", "Makefile", ".gitignore"):
        shutil.copy(ROOT / rel, repo / rel)
    (repo / "app/core").mkdir(parents=True)
    shutil.copy(ROOT / "app/core/config.py", repo / "app/core/config.py")
    (repo / "README.txt").write_text("plantilla\n")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "init")
    return repo


def _new(module, template: Path, tmp_path: Path, *extra: str) -> Path:
    module.main(
        ["demo-api", "--dir", str(tmp_path / "out"), "--no-install", "--no-git",
         "--template", str(template), *extra]
    )  # fmt: skip
    return tmp_path / "out" / "demo-api"


def test_dirty_template_is_rejected_and_untracked_files_never_copied(template, tmp_path):
    module = _load()
    (template / "deploy_key").write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n")
    (template / "notas-cliente.txt").write_text("STRIPE_KEY=sk_" + "live_abcdefghijkl1234\n")
    with pytest.raises(SystemExit):
        _new(module, template, tmp_path)
    assert not (tmp_path / "out" / "demo-api").exists()

    project = _new(module, template, tmp_path, "--allow-dirty")
    assert (project / "pyproject.toml").exists() and (project / "docs/DESARROLLO.txt").exists()
    assert not (project / "deploy_key").exists()
    assert not (project / "notas-cliente.txt").exists()
    assert not (project / "README.txt").exists()
    assert 'name = "demo-api"' in (project / "pyproject.toml").read_text()
    assert "new-api" not in (project / "Makefile").read_text()  # UX-63: el script no va


def test_versioned_secrets_and_personal_data_abort(template, tmp_path):
    module = _load()
    (template / ".env.example").write_text(
        (template / ".env.example").read_text() + "# contacto: juan.perez@acme-cliente.es\n"
    )
    _git(template, "add", "-A")
    _git(template, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x")
    with pytest.raises(SystemExit):
        _new(module, template, tmp_path)


def test_scanner_patterns():
    module = _load()
    bad = {
        "a.txt": "-----BEGIN RSA PRIVATE KEY-----",
        "b": "key = 'sk_" + "live_4eC39HqLyjWDarjtT1zdp7dc'",
        "c.md": "AKIAIOSFODNN7EXAMPLE",
        "d.example": "API_TOKEN=abcdefghijklmnopqrstuvwxyz0123",
        "e.cfg": "path /Users/somebody/Developer/x",
        "f.py": "email = 'maria@gmail.com'",
        "g.yml": "url: postgresql://app:VeryRealPassw0rd@prod-db:5432/app",
    }
    for rel, text in bad.items():
        assert module.scan_text(rel, text), rel
    good = (
        "user@example.com x@staging.example.com admin@gym.test "
        "postgresql+asyncpg://bench:secret@db.internal/x SECRET_KEY=change-me "
        "DATABASE_URL=postgresql+asyncpg://api:${POSTGRES_PASSWORD:?x}@db:5432/api"
    )
    assert module.scan_text("ok.txt", good) == []
    assert module.FORBIDDEN_NAMES.search("backup.sqlite3")
    assert module.FORBIDDEN_NAMES.search("keys/deploy.key")
    assert not module.FORBIDDEN_NAMES.search(".env.example")
    generated = module.generated_resources(
        ["app/hooks/__init__.py", "app/hooks/invoice.py", "app/api/v1/endpoints/users.py",
         "app/api/v1/endpoints/documents.py", "tests/api/v1/test_documents.py"]
    )  # fmt: skip
    assert generated == [
        "app/hooks/invoice.py",
        "app/api/v1/endpoints/documents.py",
        "tests/api/v1/test_documents.py",
    ]


def test_real_template_passes_the_scanner():
    """La plantilla versionada no debe disparar el escáner (falsos positivos)."""
    module = _load()
    if not (ROOT / ".git").exists():
        pytest.skip("sin repositorio git")
    files = [f for f in module.tracked_files(ROOT) if not f.startswith(module.EXCLUDE)]
    assert module.scan_files(ROOT, files) == []
