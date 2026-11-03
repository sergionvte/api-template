# apigen: a secure FastAPI generator, built with AI agents

A template plus a code generator (`apigen`) that turns a YAML file into a **production-ready REST API**: FastAPI, async SQLModel, JWT and rate limiting. The generated APIs are already hardened against the **OWASP API Top 10** and aligned with **SOC 2** and **ISO/IEC 27701**.

The project was designed, built, audited and hardened with **AI agents** (Claude Code plus specialized agents), in review cycles similar to those of a real team. How that worked is explained below.

```yaml
# resources/order.yaml
- name: order
  owned: true                          # each user only sees their own orders
  purpose: Order management and delivery
  fields:
    product_id: {type: fk, to: product}
    quantity: {type: int, ge: 1, le: 100}
    contact_email: {type: email, pii: true}
    medical_notes: {type: text, sensitive: true, nullable: true}   # encrypted with AES-256-GCM
  actions:
    - {name: export_invoice, background: true, rate_limit: "10/minute"}
```

```bash
apigen generate resources/order.yaml --migrate
```

This generates:
- the model, schemas and versioned router (`/api/v1/orders`);
- the Alembic migration;
- owner-based permissions and rate limiting;
- the background endpoint with its job queue;
- its tests (CRUD, permissions, isolation, data export and erasure);
- client-facing documentation and the personal data inventory.

---

## How it was built: development with AI agents

The main **Claude Code** session acts as the orchestrator. It coordinates three **specialized agents** (defined in `.claude/agents/`), each with its own role, tools and judgment:

| Agent | Role |
|---|---|
| `security-expert` | Defensive AppSec auditor. Reviews code against the OWASP API Top 10 and ASVS L2, threat-models, and **verifies every finding in an isolated lab** (`security/lab.sh`) with its own scripts (`security/checks/`). |
| `developer` | Senior backend engineer. Evaluates each report, **decides with explicit reasoning** what gets fixed and what is accepted as risk, and ships the fixes with tests. |
| `user` | A developer using the template for the first time. Measures the real experience: confusing errors, documentation, and friction caused by security. |

**Process:**
1. **Iterative rounds.** The expert and the user work in parallel; the developer answers point by point; the next round verifies the fixes.
2. **The main session validates every delivery** with tests, lint, `pip-audit`, load tests and real generated examples.
3. **A knowledge graph of the codebase** ([graphify](https://pypi.org/project/graphifyy/)). Agents query the graph before reading files, which greatly reduces the tokens spent per review.
4. **Security vs. usability trade-offs are debated and documented.** Examples: account lockout vs. denial of service, email enumeration, the refresh-token grace period.

| Round | Outcome |
|---|---|
| 1 | Initial audit: 0 critical, 4 medium. The user finds 28 usability issues (rated 5/10). |
| 2-4 | 53 items resolved. Smart lockout, concurrent refresh race, trusted proxies, IP retention. Verdict: **production-ready with conditions**. |
| 5-6 | Graph-guided review: 0 critical, 0 high, 0 medium. User rating: **9/10**. |
| 7-8 | Hooks, job queue, and validation with Docker, PostgreSQL and Redis. 4 medium findings closed (BOLA in actions, task timeouts...). |
| Phase 2 | Email verification, password recovery and per-client email, with its own audit round. |
| 9 | **SOC 2 / ISO 27701 hardening** (see below). |

People define the product, make the decisions and validate the result. The agents widen the coverage: every relevant change goes through a security audit and a usability test, and everything is documented in `security/reports/` (20 reports).

---

## What's included

### Generator (`apigen`)
- **Declarative CRUD** from YAML or the CLI: 13 field types, FKs with `on_delete`, enums, soft delete, and allow-listed filtering, search and ordering.
- **Per-action permissions** (`public`, `user`, `owner`, `admin`) with validations that **reject insecure configurations**: BOLA by ID, open `update` on owned resources, public background actions...
- **Hooks** (`app/hooks/`) and **background actions** (`apigen worker`). The queue lives in the database itself, with no broker, async/thread/process executors and real timeouts.
- **API versioning** (`v1`, `v2`, deprecation and *sunset* headers) and automatic Alembic migrations.
- **Generated tests** per resource: CRUD, permissions, user isolation, mass assignment, data export and erasure.
- **Client documentation** (`apigen docs`, en/es) and a Postman collection.
- **Safe code generation**: identifiers are validated and literals are emitted with `repr()`. A malicious YAML cannot inject code.

### Security of the generated APIs
- Argon2id (RFC 9106) and a password policy. 15-minute JWTs plus opaque refresh tokens with **rotation and reuse detection**.
- **Smart lockout**: a third party cannot lock the owner out. Per-user and per-IP rate limiting (Redis) and strict trusted proxies.
- Strict validation (extra=forbid, size limits, NUL bytes, bounded integers), security headers, and errors with a stable `code` that never leak information.
- Insecure configuration **prevents startup** in production. Containers run as non-root, read-only, with `cap_drop: ALL`.
- Least privilege between processes: the worker never gets the JWT key and the API never gets the SMTP credentials.

### Privacy and compliance (SOC 2 / ISO 27701)
- **Tamper-evident audit log**: events chained with HMAC, checked by `apigen audit verify`.
- **Data subject rights**: `GET /users/me/export` (access and portability) and `DELETE /users/me` (cascading erasure).
- **Data classification** (`pii`, `sensitive`, `purpose`) carried into the model, the OpenAPI schema and the **personal data inventory**, which CI checks.
- **Encryption at rest** for sensitive fields (AES-256-GCM, with key rotation).
- **Automatic retention**, truncated IPs in logs, **access reviews** and **incident response** from the CLI.
- CI with lint, tests, `pip-audit`, the inventory check and the image build, plus Dependabot.
- Full matrix of controls, evidence and responsibilities (in Spanish): [`docs/CUMPLIMIENTO_SOC2_ISO27701.md`](docs/CUMPLIMIENTO_SOC2_ISO27701.md).

---

## Metrics

| | |
|---|---|
| Code (app + generator + templates) | ~13,800 lines of Python |
| Repository tests | **363** (~5,000 lines) |
| Full suite with the generated examples | 392 tests (`shop.yaml`) and 398 (`cursos.yaml`), all green |
| Dependency vulnerabilities (`pip-audit`) | **0** |
| Load: 500 users, 60 s | 1,712 req/s, 38 ms median, **0 errors** |
| Load with hostile traffic + rate limiting | ~80,000 requests, **0 failures, 0 5xx** |
| Open critical/high findings | **0** |

## Stack

Python 3.12+ · FastAPI · SQLModel / SQLAlchemy 2 async · Alembic · PostgreSQL / SQLite · Redis · PyJWT · pwdlib (Argon2id) · SlowAPI / limits · cryptography · Typer · Jinja2 · uv · ruff · pytest · Locust · Docker · GitHub Actions · Claude Code + agents · graphify

## Quick start

```bash
uv sync
uv run apigen init-env                        # .env with random secrets
uv run apigen generate examples/shop.yaml --migrate
uv run apigen createsuperuser --email admin@example.com
uv run apigen run                             # http://127.0.0.1:8000/docs
uv run pytest -q
```

In production: `docker compose up -d --build` (API, worker, PostgreSQL and Redis).

## Layout

```
apigen/          generator and CLI (spec, codegen, Jinja templates, docs, inventory)
app/             base API: auth, users, accounts, email, job queue, privacy
tests/           core and generator tests
examples/        example specs (online shop, course platform)
security/        review reports, verification scripts and lab
docs/            SOC 2 / ISO 27701 compliance, data inventory, Postman
.claude/agents/  AI agent definitions (security-expert, developer, user)
loadtests/       Locust load tests
```

## Documentation

The internal documentation and the CLI are in Spanish; the generated APIs and their client docs are in English (or Spanish).

- [`README.txt`](README.txt): full technical manual for the template.
- [`guia/README.txt`](guia/README.txt): practical usage guide.
- [`security/REVISION_SEGURIDAD.md`](security/REVISION_SEGURIDAD.md): summary of every review round.
- [`docs/CUMPLIMIENTO_SOC2_ISO27701.md`](docs/CUMPLIMIENTO_SOC2_ISO27701.md): controls, evidence and operator responsibilities.

## Known limitations

- SOC 2 and ISO 27701 certify **organizations**, not code. This template provides the technical controls and the evidence; policies, processor agreements, backups and the SIEM are the operator's responsibility (detailed in the matrix).
- Pending: live validation of password-protected Redis under Docker, and pinning images and CI actions by digest.

---

Author: **sergionvte** · Built with [Claude Code](https://claude.com/claude-code) and specialized AI agents.
