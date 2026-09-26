"""Elige la base de datos de la prueba de carga (SEC-29). Solo usa la biblioteca estándar.

    python3 loadtests/resolve_db.py <directorio-temporal>

Imprime la URL por stdout (avisos por stderr) o sale con código 2 si se niega:
- NUNCA hereda `DATABASE_URL`: la prueba migra, siembra un admin `bench-admin@…`
  y lanza tráfico hostil; hacerlo por error contra staging sería grave.
- Por defecto: SQLite temporal dentro de la copia (se borra al terminar).
- `LOADTEST_DATABASE_URL`: opt-in explícito. Si apunta a un host no local, además
  hace falta `LOADTEST_ALLOW_REMOTE_DB=1`.
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urlsplit

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", ""}


def resolve(env: dict[str, str], workdir: str) -> tuple[str | None, list[str]]:
    """(url o None si se niega, mensajes para el usuario)."""
    messages: list[str] = []
    url = env.get("LOADTEST_DATABASE_URL", "").strip()
    if env.get("DATABASE_URL"):
        hint = "" if url else " (define LOADTEST_DATABASE_URL si de verdad quieres otra)"
        messages.append(f"Ignorando DATABASE_URL del entorno: la prueba no la usa{hint}.")
    if not url:
        return f"sqlite+aiosqlite:///{workdir}/load.db", messages
    parts = urlsplit(url)
    if parts.scheme.startswith("sqlite"):
        messages.append(f"BD de la prueba: SQLite indicada en LOADTEST_DATABASE_URL ({parts.path})")
        return url, messages
    host = (parts.hostname or "").lower()
    if host not in LOCAL_HOSTS and env.get("LOADTEST_ALLOW_REMOTE_DB") != "1":
        messages.append(
            f"LOADTEST_DATABASE_URL apunta a un host no local ({host}). La prueba crea "
            "tablas bench_*, aplica una migración autogenerada y siembra un admin: "
            "si es intencionado, define LOADTEST_ALLOW_REMOTE_DB=1."
        )
        return None, messages
    messages.append(f"BD de la prueba: {parts.scheme}://{host} (LOADTEST_DATABASE_URL)")
    return url, messages


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    url, messages = resolve(dict(os.environ), sys.argv[1])
    for message in messages:
        print(f"==> {message}", file=sys.stderr)
    if url is None:
        return 2
    print(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
