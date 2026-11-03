# api-template

Plantilla + generador (`apigen`) de APIs FastAPI + SQLModel async + JWT + SlowAPI.
Documentación: `README.txt` (repo), `guia/README.txt` (uso), `security/REVISION_SEGURIDAD.md`.

## Cómo trabajar aquí
- **Primero el grafo** (sección graphify más abajo): orienta con `graphify query`,
  `graphify explain` o `graphify path` y solo después lee las líneas concretas.
- Tras cambiar código: `graphify update .` (o `make graph`). `apigen add/generate/
  remove/version add` ya lo hacen solos. Si cambian documentos o informes de
  `security/`, ejecuta `/graphify . --update` (extracción semántica).
- Verificación antes de dar algo por terminado: `.venv/bin/pytest -q -p no:cacheprovider`
  y `.venv/bin/ruff check .`. Los cambios en `apigen/templates/` se prueban generando
  `examples/shop.yaml` en una copia temporal (nunca dentro del repo: `resources/` vacío).
- Comentarios en español, identificadores en inglés, ruff line-length 100.
- Lógica de negocio de un recurso: `app/hooks/<recurso>.py` (apigen nunca lo pisa).
  Procesos pesados: acciones `background: true` en el YAML → `app/tasks/resources/`
  y `apigen worker` (cola en la tabla `jobs`, sin broker). Tests: `process_pending()`.
- Nuevos proyectos: `make new-api NAME=x` (scripts/new_api.py). README.md para clientes: `apigen docs`.
- Privacidad/cumplimiento: `docs/CUMPLIMIENTO_SOC2_ISO27701.md`. Campos `pii`/`sensitive` y
  `purpose` en las specs; `sensitive` se cifra (app/db/crypto.py). Tablas nuevas con datos
  de usuario: FK a `users.id` (la exportación y la supresión las descubren solas).
- Agentes de revisión en `.claude/agents/` (security-expert, developer, user);
  laboratorio aislado: `./security/lab.sh <puerto>`.
- No reintroducir `SlowAPIMiddleware`: con FastAPI >= 0.140 no aplica límites
  (se usan dependencias globales en `app/core/rate_limit.py`).

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
