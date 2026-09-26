#!/usr/bin/env bash
# Prueba de estrés reproducible con Locust.
#
#   ./loadtests/run_loadtest.sh [perfil]
#
# Perfiles:
#   throughput  rate limit DESACTIVADO: mide el rendimiento bruto (RPS, latencias).
#   ratelimit   rate limit ACTIVADO + atacantes: comprueba que la API se defiende
#               (429/401/413/422) sin errores 5xx ni caída de rendimiento.
#
# Variables: USERS (200), SPAWN (50), DURATION (60s), WORKERS (4), PORT (8765),
#            LOCUST_PROCESSES (2).
# Base de datos (SEC-29): SQLite temporal por defecto. DATABASE_URL del entorno se
# IGNORA; para usar otra BD define LOADTEST_DATABASE_URL (y LOADTEST_ALLOW_REMOTE_DB=1
# si el host no es local). En ese caso las cuentas bench-* se borran al terminar.
#
# Genera los modelos de prueba en una COPIA temporal del proyecto, así que la
# plantilla nunca se ensucia. Los informes quedan en loadtests/reports/.
set -euo pipefail

PROFILE="${1:-throughput}"
USERS="${USERS:-200}"
SPAWN="${SPAWN:-50}"
DURATION="${DURATION:-60s}"
WORKERS="${WORKERS:-4}"
PORT="${PORT:-8765}"
LOCUST_PROCESSES="${LOCUST_PROCESSES:-2}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d -t apigen-load-XXXXXX)"
REPORTS="$ROOT/loadtests/reports"
mkdir -p "$REPORTS"

cleanup() {
  [[ -n "${SERVER_PID:-}" ]] && kill "$SERVER_PID" 2>/dev/null && wait "$SERVER_PID" 2>/dev/null || true
  if [[ -n "${LOADTEST_DATABASE_URL:-}" && -n "${SEEDED:-}" ]]; then
    # BD persistente elegida a propósito: no dejar el admin ni los usuarios de la prueba.
    (cd "$WORK" && "$ROOT/.venv/bin/python" loadtests/seed.py --cleanup) || true
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT

# Nunca se hereda DATABASE_URL (podría ser staging): ver loadtests/resolve_db.py.
DB_URL="$(python3 "$ROOT/loadtests/resolve_db.py" "$WORK")" || exit 2
unset DATABASE_URL

echo "==> Copia temporal en $WORK"
rsync -a --exclude .venv --exclude '__pycache__' --exclude '*.db*' --exclude resources \
  --exclude 'loadtests/reports' --exclude .env "$ROOT/" "$WORK/"

export PYTHONPATH="$WORK"
export ENVIRONMENT=development DOCS_ENABLED=false LOG_LEVEL=WARNING
export SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
export DATABASE_URL="$DB_URL"
export LOADTEST_PASSWORD="bench-$(python3 -c 'import secrets;print(secrets.token_hex(8))')"
export SEED_USERS="${SEED_USERS:-200}" SEED_PRODUCTS="${SEED_PRODUCTS:-500}"
export PASSWORD_HASH_CONCURRENCY="${PASSWORD_HASH_CONCURRENCY:-4}"
if [[ "$PROFILE" == "throughput" ]]; then
  export RATE_LIMIT_ENABLED=false LOADTEST_ATTACKERS=0
else
  export RATE_LIMIT_ENABLED=true LOADTEST_ATTACKERS=1
fi

PY="$ROOT/.venv/bin/python"
cd "$WORK"
echo "==> Generando modelos de prueba y migrando"
"$PY" -m apigen.cli generate loadtests/resources.loadtest.yaml --no-tests >/dev/null
"$PY" -m apigen.cli db migrate -m loadtest >/dev/null 2>&1
"$PY" loadtests/seed.py
SEEDED=1

STAMP="$(date +%Y%m%d-%H%M%S)"
SERVER_LOG="$REPORTS/${PROFILE}-${STAMP}-server.log"
echo "==> Arrancando API: $WORKERS workers en :$PORT (rate limit: $RATE_LIMIT_ENABLED)"
"$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --workers "$WORKERS" \
  --no-access-log --no-server-header --no-proxy-headers --log-level warning >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 50); do
  curl -sf "http://127.0.0.1:$PORT/health/live" >/dev/null && break
  sleep 0.2
done

echo "==> Locust: $USERS usuarios, spawn $SPAWN/s, $DURATION"
"$ROOT/.venv/bin/locust" -f loadtests/locustfile.py --headless \
  --host "http://127.0.0.1:$PORT" -u "$USERS" -r "$SPAWN" -t "$DURATION" \
  --processes "$LOCUST_PROCESSES" --only-summary \
  --csv "$REPORTS/${PROFILE}-${STAMP}" --html "$REPORTS/${PROFILE}-${STAMP}.html" || true

echo "==> Comprobando que la API sigue sana tras la carga"
curl -sf "http://127.0.0.1:$PORT/health/ready" && echo
echo "==> Errores 5xx registrados por el servidor: $(grep -c 'unhandled error' "$SERVER_LOG" || true)"
echo "==> Informes: $REPORTS/${PROFILE}-${STAMP}*"
