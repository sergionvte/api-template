.PHONY: install env dev test lint format migrate check audit loadtest graph graph-query worker

install:        ## Instala dependencias (incluye dev)
	uv sync

env:            ## Crea .env con una SECRET_KEY nueva
	uv run apigen init-env

dev:            ## Servidor de desarrollo con recarga
	uv run apigen run

worker:         ## Worker de tareas en segundo plano (en otra terminal junto a `make dev`)
	uv run apigen worker

test:           ## Tests
	uv run pytest -q

lint:           ## Lint
	uv run ruff check .

format:         ## Formatea el código
	uv run ruff format . && uv run ruff check --fix .

migrate:        ## Aplica migraciones pendientes
	uv run apigen db upgrade

check:          ## Valida la configuración
	uv run apigen check

audit:          ## Auditoría de dependencias (vulnerabilidades conocidas)
	uv export --frozen --no-hashes --no-emit-project --format requirements-txt \
		| uvx pip-audit --no-deps --disable-pip -r /dev/stdin

loadtest:       ## Prueba de estrés (ver loadtests/README)
	./loadtests/run_loadtest.sh

GRAPHIFY_CHECK = @command -v graphify >/dev/null 2>&1 || { \
	echo "graphify no está instalado: uv tool install graphifyy==0.9.58 (ver README §11)"; \
	exit 1; }

graph:          ## Actualiza el grafo de graphify tras cambios de código (AST, sin coste)
	$(GRAPHIFY_CHECK)
	graphify update .

graph-query:    ## Consulta el grafo: make graph-query Q="cómo funciona el refresh"
	$(GRAPHIFY_CHECK)
	@test -n "$(Q)" || { echo 'Uso: make graph-query Q="tu pregunta"'; exit 1; }
	graphify query "$(Q)" --budget 1500
