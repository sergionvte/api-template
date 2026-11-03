# apigen: generador de APIs FastAPI seguras, construido con agentes de IA

Plantilla y generador de código (`apigen`) que crea **APIs REST de producción** a partir de un YAML: FastAPI, SQLModel asíncrono, JWT y rate limiting. Las APIs salen ya endurecidas según **OWASP API Top 10**, **SOC 2** e **ISO/IEC 27701**.

El proyecto se diseñó, se programó, se auditó y se endureció con **agentes de IA** (Claude Code y agentes especializados), en ciclos de revisión parecidos a los de un equipo real. Abajo se explica cómo.

```yaml
# resources/order.yaml
- name: order
  owned: true                          # cada usuario solo ve sus pedidos
  purpose: Gestión y entrega de pedidos
  fields:
    product_id: {type: fk, to: product}
    quantity: {type: int, ge: 1, le: 100}
    contact_email: {type: email, pii: true}
    medical_notes: {type: text, sensitive: true, nullable: true}   # se cifra con AES-256-GCM
  actions:
    - {name: export_invoice, background: true, rate_limit: "10/minute"}
```

```bash
apigen generate resources/order.yaml --migrate
```

Con esto se genera:
- el modelo, los esquemas y el router versionado (`/api/v1/orders`);
- la migración de Alembic;
- los permisos por dueño y el rate limit;
- el endpoint en segundo plano con su cola de trabajos;
- sus tests (CRUD, permisos, aislamiento, exportación y supresión);
- la documentación para el cliente y el inventario de datos personales.

---

## Cómo se construyó: desarrollo con agentes de IA

La sesión principal de **Claude Code** actúa como orquestadora. Coordina tres **agentes especializados** (definidos en `.claude/agents/`), cada uno con su papel, sus herramientas y su criterio:

| Agente | Papel |
|---|---|
| `security-expert` | Auditor AppSec defensivo. Revisa el código con OWASP API Top 10 y ASVS L2, modela amenazas y **verifica cada hallazgo en un laboratorio aislado** (`security/lab.sh`) con scripts propios (`security/checks/`). |
| `developer` | Backend senior. Evalúa cada informe, **decide de forma razonada** qué se corrige y qué se acepta como riesgo, y aplica las correcciones con tests. |
| `user` | Desarrollador que usa la plantilla por primera vez. Mide la experiencia real: errores confusos, documentación y fricción que provoca la seguridad. |

**Proceso:**
1. **Rondas iterativas.** El experto y el usuario trabajan en paralelo; el desarrollador responde punto por punto; la ronda siguiente verifica las correcciones.
2. **La sesión principal valida cada entrega** con tests, lint, `pip-audit`, pruebas de carga y generación de ejemplos reales.
3. **Grafo de conocimiento del código** ([graphify](https://pypi.org/project/graphifyy/)). Los agentes consultan el grafo antes de leer ficheros, lo que reduce mucho los tokens por revisión.
4. **Las tensiones entre seguridad y usabilidad se debaten y se documentan.** Ejemplos: bloqueo de cuenta frente a denegación de servicio, enumeración de emails, periodo de gracia del refresh.

| Ronda | Resultado |
|---|---|
| 1 | Auditoría inicial: 0 críticos, 4 medios. El usuario encuentra 28 problemas de uso (valoración 5/10). |
| 2-4 | 53 puntos resueltos. *Smart lockout*, carrera en el refresh concurrente, proxies de confianza, retención de IPs. Veredicto: **apta para producción con condiciones**. |
| 5-6 | Revisión guiada por el grafo: 0 críticos, 0 altos y 0 medios. Usuario: **9/10**. |
| 7-8 | Hooks, cola de trabajos y validación con Docker, PostgreSQL y Redis. Se cierran 4 hallazgos medios (BOLA en acciones, timeouts de tareas...). |
| Fase 2 | Verificación de email, recuperación de contraseña y correo por cliente, con su propia ronda de auditoría. |
| 9 | **Hardening SOC 2 / ISO 27701** (abajo). |

Las personas definen el producto, toman las decisiones y validan el resultado. Los agentes amplían la cobertura: cada cambio relevante pasa una auditoría de seguridad y una prueba de uso, y todo queda documentado en `security/reports/` (20 informes).

---

## Qué incluye

### Generador (`apigen`)
- **CRUD declarativo** desde YAML o CLI: 13 tipos de campo, FKs con `on_delete`, enums, soft delete, filtros, búsqueda y ordenación con listas blancas.
- **Permisos por acción** (`public`, `user`, `owner`, `admin`) con validaciones que **impiden configuraciones inseguras**: BOLA por ID, `update` abierto en recursos con dueño, acciones públicas en segundo plano...
- **Hooks** (`app/hooks/`) y **acciones en segundo plano** (`apigen worker`). La cola vive en la propia BD, sin broker, con executors async, thread o process y timeouts reales.
- **Versionado de la API** (`v1`, `v2`, cabeceras de deprecación y *sunset*) y migraciones Alembic automáticas.
- **Tests generados** por recurso: CRUD, permisos, aislamiento entre usuarios, asignación masiva, exportación y supresión de datos.
- **Documentación para el cliente** (`apigen docs`, en/es) y colección de Postman.
- **Generación segura de código**: identificadores validados y literales emitidos con `repr()`. Un YAML malicioso no puede inyectar código.

### Seguridad de las APIs generadas
- Argon2id (RFC 9106) y política de contraseñas. JWT de 15 min y refresh opaco con **rotación y detección de reutilización**.
- **Bloqueo inteligente**: un tercero no puede dejar fuera al titular. Rate limiting por usuario e IP (Redis) y proxies de confianza estrictos.
- Validación estricta (extra=forbid, límites de tamaño, NUL, enteros acotados), cabeceras de seguridad y errores con `code` estable que no filtran información.
- La configuración insegura **impide arrancar** en producción. Contenedores sin root, read-only y con `cap_drop: ALL`.
- Mínimo privilegio entre procesos: el worker no recibe la clave JWT y la API no recibe las credenciales SMTP.

### Privacidad y cumplimiento (SOC 2 / ISO 27701)
- **Auditoría a prueba de manipulaciones**: eventos encadenados con HMAC y `apigen audit verify`.
- **Derechos del interesado**: `GET /users/me/export` (acceso y portabilidad) y `DELETE /users/me` (supresión en cascada).
- **Clasificación de datos** (`pii`, `sensitive`, `purpose`) en el modelo, el OpenAPI y el **inventario de datos personales**, que CI comprueba.
- **Cifrado en reposo** de los campos sensibles (AES-256-GCM, con rotación de claves).
- **Retención automática**, IPs truncadas en los logs, **revisión de accesos** y **respuesta a incidentes** desde la CLI.
- CI con lint, tests, `pip-audit`, inventario y build de la imagen, más Dependabot.
- Matriz completa de controles, evidencias y responsabilidades: [`docs/CUMPLIMIENTO_SOC2_ISO27701.md`](docs/CUMPLIMIENTO_SOC2_ISO27701.md).

---

## Métricas

| | |
|---|---|
| Código (app + generador + plantillas) | ~13.800 líneas de Python |
| Tests del repo | **363** (~5.000 líneas) |
| Suite completa con los ejemplos generados | 392 tests (`shop.yaml`) y 398 (`cursos.yaml`), todos en verde |
| Vulnerabilidades en dependencias (`pip-audit`) | **0** |
| Carga: 500 usuarios, 60 s | 1.712 req/s, mediana 38 ms, **0 errores** |
| Carga con tráfico hostil + rate limit | ~80.000 peticiones, **0 fallos y 0 errores 5xx** |
| Hallazgos críticos o altos abiertos | **0** |

## Stack

Python 3.12+ · FastAPI · SQLModel / SQLAlchemy 2 async · Alembic · PostgreSQL / SQLite · Redis · PyJWT · pwdlib (Argon2id) · SlowAPI / limits · cryptography · Typer · Jinja2 · uv · ruff · pytest · Locust · Docker · GitHub Actions · Claude Code + agentes · graphify

## Inicio rápido

```bash
uv sync
uv run apigen init-env                        # .env con secretos aleatorios
uv run apigen generate examples/shop.yaml --migrate
uv run apigen createsuperuser --email admin@example.com
uv run apigen run                             # http://127.0.0.1:8000/docs
uv run pytest -q
```

En producción: `docker compose up -d --build` (API, worker, PostgreSQL y Redis).

## Estructura

```
apigen/          generador y CLI (spec, codegen, plantillas Jinja, docs, inventario)
app/             API base: auth, usuarios, cuentas, correo, cola de trabajos, privacidad
tests/           tests del núcleo y del generador
examples/        specs de ejemplo (tienda, plataforma de cursos)
security/        informes de las rondas, scripts de verificación y laboratorio
docs/            cumplimiento SOC 2 / ISO 27701, inventario de datos, Postman
.claude/agents/  definición de los agentes de IA (security-expert, developer, user)
loadtests/       pruebas de carga con Locust
```

## Documentación

- [`README.txt`](README.txt): manual técnico completo de la plantilla.
- [`guia/README.txt`](guia/README.txt): guía práctica de uso.
- [`security/REVISION_SEGURIDAD.md`](security/REVISION_SEGURIDAD.md): resumen de todas las rondas de revisión.
- [`docs/CUMPLIMIENTO_SOC2_ISO27701.md`](docs/CUMPLIMIENTO_SOC2_ISO27701.md): controles, evidencias y responsabilidad del operador.

## Limitaciones conocidas

- SOC 2 e ISO 27701 certifican **organizaciones**, no código. Esta plantilla aporta los controles técnicos y las evidencias; las políticas, los contratos con encargados, los backups y el SIEM son responsabilidad del operador (detallado en la matriz).
- Pendiente: validar en vivo Redis con contraseña en Docker y fijar las imágenes y acciones de CI por digest.

---

Autor: **sergionvte** · Desarrollado con [Claude Code](https://claude.com/claude-code) y agentes de IA especializados.
