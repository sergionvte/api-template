"""Configuración y CLI: el .env generado arranca, validaciones y utilidades."""

import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from apigen import cli, project
from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fake_project(tmp_path, monkeypatch):
    shutil.copy(ROOT / ".env.example", tmp_path / ".env.example")
    monkeypatch.setattr(project, "root", lambda: tmp_path)
    # Las variables de entorno de conftest tienen prioridad sobre el .env: fuera.
    for name in Settings.model_fields:
        monkeypatch.delenv(name, raising=False)
    return tmp_path


@pytest.mark.parametrize("production", [False, True])
def test_init_env_output_loads(fake_project, production):
    """UX-01: el .env de `init-env` (con variables vacías) es válido tal cual."""
    args = ["init-env", "--production"] if production else ["init-env"]
    result = CliRunner().invoke(cli.app, args)
    assert result.exit_code == 0, result.output
    env_file = fake_project / ".env"
    text = env_file.read_text()
    assert "DOCS_ENABLED=\n" in text and "LOG_JSON=\n" in text
    assert "POSTGRES_PASSWORD=\n" not in text  # se genera una aleatoria
    # Y también la de Redis y la clave de la cadena de auditoría (hardening SOC 2).
    assert "REDIS_PASSWORD=\n" not in text and "AUDIT_HMAC_KEY=\n" not in text
    assert "DATA_ENCRYPTION_KEY=\n" not in text
    if production:
        # En producción debe fallar SOLO por lo que el usuario tiene que rellenar.
        with pytest.raises(ValidationError) as exc:
            Settings(_env_file=env_file)
        assert "ALLOWED_HOSTS" in str(exc.value)
        assert "DOCS_ENABLED" not in str(exc.value)
        assert "ALLOWED_HOSTS" in result.output  # la CLI dice qué falta
    else:
        settings = Settings(_env_file=env_file)
        assert settings.DOCS_ENABLED is None and settings.LOG_JSON is None


def test_weak_previous_jwt_keys_rejected_in_production():
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="k" * 40,
            ALLOWED_HOSTS=["api.example.com"],
            JWT_PREVIOUS_SECRET_KEYS=["short"],
        )


def test_migrate_script_path_handles_all_alembic_results():
    """UX-03: con skip_empty Alembic devuelve [] en lugar de None."""

    class Script:
        path = "/x/alembic/versions/abc_add.py"

    assert cli._script_path(None) is None
    assert cli._script_path([]) is None
    assert cli._script_path([Script()]) == "abc_add.py"
    assert cli._script_path(Script()) == "abc_add.py"


def test_migration_tables_lists_what_upgrade_touches(tmp_path):
    """UX-47: generate --migrate avisa si la migración trae tablas de otros recursos."""
    script = tmp_path / "abc_add_post.py"
    script.write_text(
        "def upgrade():\n"
        "    op.create_table('posts', sa.Column('id', sa.Uuid()))\n"
        "    op.create_index(op.f('ix_posts_slug'), 'posts', ['slug'], unique=False)\n"
        "    op.create_table(\n        'tasks',\n        sa.Column('id', sa.Uuid()))\n"
        "    op.drop_index(op.f('ix_tags_name'), table_name='tags')\n"
        "    with op.batch_alter_table('comments') as batch_op:\n"
        "        batch_op.add_column(sa.Column('x', sa.Integer()))\n\n\n"
        "def downgrade():\n"
        "    op.drop_table('ignored')\n"
    )
    assert cli.migration_tables(script) == ["comments", "posts", "tags", "tasks"]


def test_quiet_alembic_config_silences_status_messages():
    """UX-47: sin la línea "Generating /ruta/absoluta ... done" de Alembic."""
    cfg = cli._alembic_config(quiet=True)
    assert cfg.messaging_opts["quiet"] is True
    assert cli._alembic_config(quiet=False).messaging_opts["quiet"] is False


def test_check_error_is_clean():
    try:
        Settings(ENVIRONMENT="production", SECRET_KEY="short")
    except ValidationError as exc:
        text = cli._clean(exc)
    assert "input_value" not in text and "validation error" not in text
    assert "SECRET_KEY" in text


def _prod(**overrides) -> Settings:
    values = {
        "ENVIRONMENT": "production",
        "SECRET_KEY": "k" * 40,
        "ALLOWED_HOSTS": ["api.example.com"],
        "DATABASE_URL": "postgresql+asyncpg://u:p@db:5432/api",
        "TRUSTED_PROXIES": ["172.30.57.1"],
        # Como en un despliegue real: sin backend de correo (conftest fija `memory`).
        "EMAIL_BACKEND": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_production_baseline_is_valid():
    assert _prod().RATE_LIMIT_REGISTER == "5/hour"


@pytest.mark.parametrize("proxies", [["*"], ["0.0.0.0/0"], ["::/0"], ["10.0.0.0/4"]])
def test_wildcard_trusted_proxies_rejected_in_production(proxies):
    """SEC-21: confiar en XFF de cualquiera permite falsificar la IP del cliente."""
    with pytest.raises(ValidationError, match="TRUSTED_PROXIES"):
        _prod(TRUSTED_PROXIES=proxies)


def test_trusted_proxies_must_be_ips():
    with pytest.raises(ValidationError, match="no es una IP"):
        _prod(TRUSTED_PROXIES=["proxy.local"])
    assert _prod(TRUSTED_PROXIES=["10.0.0.5", "fd00::/64"]).TRUSTED_PROXIES


def test_sqlite_in_production_needs_explicit_opt_in():
    """SEC-24: un DATABASE_URL ausente no puede acabar en SQLite en silencio."""
    with pytest.raises(ValidationError, match="SQLite"):
        _prod(DATABASE_URL="sqlite+aiosqlite:///./app.db")
    assert _prod(DATABASE_URL="sqlite+aiosqlite:///x.db", ALLOW_SQLITE_IN_PRODUCTION=True)


def test_register_limit_depends_on_environment(monkeypatch):
    """UX-34: 50/hour fuera de producción (cuentas de prueba), 5/hour en producción."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name, raising=False)
    assert Settings(_env_file=None, ENVIRONMENT="development").RATE_LIMIT_REGISTER == "50/hour"
    assert _prod().RATE_LIMIT_REGISTER == "5/hour"
    assert _prod(RATE_LIMIT_REGISTER="20/hour").RATE_LIMIT_REGISTER == "20/hour"


def test_cli_password_policy_in_spanish():
    """UX-32: la CLI no mezcla idiomas."""
    from app.core.security import password_problems

    assert password_problems("corta", lang="es")[0].startswith("debe tener al menos")


def test_keyboard_sequences_are_rejected():
    """UX-36."""
    from app.core.security import password_problems

    for weak in ("qwertyuiopas", "1qaz2wsx3edc", "abcdefghijklm", "lkjhgfdsapoiu"):
        assert password_problems(weak), weak
    assert password_problems("tren azul de medianoche") == []


def test_worker_does_not_need_the_jwt_secret():
    """SEC-38: el worker arranca en producción sin SECRET_KEY (no firma tokens); la API no."""
    worker = _prod(PROCESS_ROLE="worker", SECRET_KEY="", ALLOWED_HOSTS=["*"], TRUSTED_PROXIES=[])
    assert len(worker.SECRET_KEY.get_secret_value()) >= 32  # efímera, solo en memoria
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        _prod(SECRET_KEY="")
    with pytest.raises(ValidationError, match="DEBUG"):
        _prod(PROCESS_ROLE="worker", SECRET_KEY="", DEBUG=True)  # lo común sigue aplicando


async def test_createsuperuser_explains_invalid_email(capsys):
    """UX-65: el motivo del rechazo (dominio reservado) llega al usuario."""
    import typer

    from apigen.cli import _createsuperuser

    with pytest.raises(typer.Exit):
        await _createsuperuser("admin@gym.test", promote=False)
    assert "special-use or reserved" in capsys.readouterr().err
