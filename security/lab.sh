#!/usr/bin/env bash
# Laboratorio aislado para auditorías: copia el proyecto a un directorio temporal,
# genera los recursos de examples/shop.yaml, crea usuarios de prueba y arranca la
# API en primer plano con configuración de PRODUCCIÓN (rate limit activo, sin docs).
#
#   ./security/lab.sh [puerto]          (por defecto 8900)
#   LAB_ENV=development ./security/lab.sh   # con /docs activado
#
# Las credenciales de prueba se escriben en $LAB_DIR/credentials.json.
# Los usuarios usan @example.com (dominio reservado para documentación y válido
# para email-validator; `.test` no lo es).
set -euo pipefail

PORT="${1:-8900}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LAB_DIR="${LAB_DIR:-$(mktemp -d -t apigen-lab-XXXXXX)}"
PY="$ROOT/.venv/bin/python"

rsync -a --exclude .venv --exclude '__pycache__' --exclude '*.db*' --exclude resources \
  --exclude 'loadtests/reports' --exclude 'security/reports' --exclude .env "$ROOT/" "$LAB_DIR/app-copy/"
cd "$LAB_DIR/app-copy"

export PYTHONPATH="$PWD"
export ENVIRONMENT="${LAB_ENV:-production}"
export SECRET_KEY="$("$PY" -c 'import secrets;print(secrets.token_urlsafe(48))')"
export DATABASE_URL="sqlite+aiosqlite:///$LAB_DIR/lab.db"
export ALLOWED_HOSTS="127.0.0.1,localhost"
# Producción con SQLite: permitido solo porque es un laboratorio de un proceso.
export ALLOW_SQLITE_IN_PRODUCTION=true
export LOG_LEVEL=INFO LOG_JSON=false

"$PY" -m apigen.cli generate examples/shop.yaml >/dev/null
"$PY" -m apigen.cli db migrate -m lab >/dev/null 2>&1

"$PY" - "$LAB_DIR/credentials.json" <<'PYEOF'
import asyncio, json, secrets, sys
from app.core.permissions import Role
from app.core.security import hash_password
from app.db.session import SessionFactory, engine
from app.models.user import User

async def main():
    creds = {}
    async with SessionFactory() as s:
        for email, role in [("admin@example.com", Role.admin), ("alice@example.com", Role.user), ("bob@example.com", Role.user)]:
            pw = "lab-" + secrets.token_urlsafe(12)
            s.add(User(email=email, hashed_password=await hash_password(pw), role=role))
            creds[email] = {"password": pw, "role": role.value}
        await s.commit()
    await engine.dispose()
    json.dump(creds, open(sys.argv[1], "w"), indent=2)

asyncio.run(main())
PYEOF

echo "LAB_DIR=$LAB_DIR"
echo "API en http://127.0.0.1:$PORT  (entorno: $ENVIRONMENT)"
echo "Credenciales de prueba: $LAB_DIR/credentials.json"
echo "Código desplegado en:   $LAB_DIR/app-copy"
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" \
  --no-server-header --no-proxy-headers --log-level warning
