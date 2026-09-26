"""SEC-29: la prueba de carga nunca usa por error la BD del entorno."""

import importlib.util
from pathlib import Path

import pytest

_path = Path(__file__).resolve().parents[1] / "loadtests" / "resolve_db.py"
if not _path.exists():  # proyecto sin loadtests/ (se puede borrar)
    pytest.skip("sin loadtests/", allow_module_level=True)
_spec = importlib.util.spec_from_file_location("resolve_db", _path)
assert _spec and _spec.loader
resolve_db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(resolve_db)


WORK = "/work"


def test_inherited_database_url_is_ignored():
    url, messages = resolve_db.resolve(
        {"DATABASE_URL": "postgresql+asyncpg://app:x@staging.example.com/app"}, WORK
    )
    assert url == "sqlite+aiosqlite:////work/load.db"
    assert any("Ignorando DATABASE_URL" in m for m in messages)


def test_explicit_local_database_is_allowed():
    for candidate in (
        "postgresql+asyncpg://bench:x@localhost:5432/bench",
        "postgresql+asyncpg://bench:x@[::1]/bench",
        "sqlite+aiosqlite:///./bench.db",
    ):
        url, _ = resolve_db.resolve({"LOADTEST_DATABASE_URL": candidate}, WORK)
        assert url == candidate


def test_remote_database_needs_second_opt_in():
    remote = "postgresql+asyncpg://bench:secret@db.internal:5432/bench"
    url, messages = resolve_db.resolve({"LOADTEST_DATABASE_URL": remote}, WORK)
    assert url is None
    assert "LOADTEST_ALLOW_REMOTE_DB=1" in messages[-1]
    assert "secret" not in " ".join(messages)  # nunca se imprime la contraseña
    url, messages = resolve_db.resolve(
        {"LOADTEST_DATABASE_URL": remote, "LOADTEST_ALLOW_REMOTE_DB": "1"}, WORK
    )
    assert url == remote and "secret" not in " ".join(messages)
