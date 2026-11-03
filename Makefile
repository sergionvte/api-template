.PHONY: install env dev test lint format migrate check audit inventory loadtest graph graph-query worker mail new-api docs deliver

install:        ## Instala dependencias (incluye dev)
	uv sync

env:            ## Crea .env con una SECRET_KEY nueva
	uv run apigen init-env

dev:            ## Servidor de desarrollo con recarga
	uv run apigen run

worker:         ## Worker de tareas en segundo plano (en otra terminal junto a `make dev`)
	uv run apigen worker

mail:           ## Mailpit para probar correos en local (bandeja en http://localhost:8025)
	docker compose -f compose.mail.yml up -d
	@echo "Mailpit: http://localhost:8025 · en .env: EMAIL_BACKEND=smtp SMTP_HOST=localhost SMTP_PORT=1025 SMTP_SECURITY=none"

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

inventory:      ## Inventario de datos personales (docs/DATA_INVENTORY.md, ISO 27701)
	uv run apigen privacy inventory

loadtest:       ## Prueba de estrés (ver README §8)
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

new-api:        ## Nueva API en ~/Developer: make new-api NAME=cursos-api [LANG=es]
	python3 scripts/new_api.py $(NAME) $(if $(LANG),--lang $(LANG),)

docs:           ## README.md para el cliente a partir de los recursos (LANG=en|es)
	uv run apigen docs $(if $(LANG),--lang $(LANG),)

deliver:        ## Zip para entregar al cliente (lo versionado, sin herramientas internas)
	git archive --format=zip -o ../$(notdir $(CURDIR))-entrega.zip HEAD -- . \
		':(exclude).claude' ':(exclude)graphify-out' ':(exclude)security' ':(exclude)loadtests' \
		':(exclude)CLAUDE.md'
	@echo "Entrega: ../$(notdir $(CURDIR))-entrega.zip (sin .claude/, graphify-out/, security/, loadtests/)"
