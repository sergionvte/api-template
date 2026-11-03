# Revisión de seguridad y usabilidad: resumen de las 4 rondas

**Fecha:** 2026-09-25

**Participantes** (definidos en `.claude/agents/`):

| Agente | Papel |
|---|---|
| `security-expert` | Experto en ciberseguridad (AppSec, enfoque defensivo). Revisión de código con OWASP API Top 10 2023 / ASVS L2 y verificación en el laboratorio local. |
| `developer` | Desarrollador backend senior. Decide cada punto de forma razonada y lo corrige con tests. |
| `user` | Usuario normal. Desarrollador que usa la plantilla por primera vez. |

**Orquestación:** Claude Code (sesión principal).
- Las rondas se hacen en secuencia; el experto y el usuario trabajan en paralelo dentro de cada ronda.
- La sesión principal verifica cada entrega (tests, lint y pruebas de carga).

Informes completos en `security/reports/`. Scripts de verificación del experto en `security/checks/`. Laboratorio: `./security/lab.sh <puerto>`.

---

## Resultado

| Métrica | Inicio | Final |
|---|---|---|
| Tests del repo | 66 | **132** |
| Tests generados (`examples/shop.yaml`) | 20 | **158** |
| Hallazgos críticos/altos abiertos | — | **0** |
| Vulnerabilidades en dependencias (pip-audit, 250 paquetes) | — | **0** |
| Valoración del usuario | 5/10 (estimada en ronda 1) | **8,5/10** (ronda 3; 9 previsto con UX-29/34, ya corregidos) |
| Veredicto del experto | — | **Apta para producción con condiciones** (ver "Pendiente") |
| Carga *throughput* (60 s, 500 usuarios) | — | 102.772 peticiones, 1.712 req/s, mediana 38 ms, **0 errores** |
| Carga *ratelimit* + tráfico hostil | — | 79.970 peticiones, **0 fallos, 0 5xx** |

---

## Cronología

### Ronda 1: auditoría y prueba de uso (en paralelo)

**Experto: 0 críticos, 0 altos, 4 medios, 10 bajos, 5 informativos. 88 comprobaciones del laboratorio correctas.**
- SEC-01: carrera en refresh concurrente → 500 y la sesión robada no se revoca (reproducido).
- SEC-02: cualquier anónimo puede bloquear cualquier cuenta.
- SEC-03: compose arrancaba en *development*.
- SEC-04: detrás del proxy, todos los clientes compartían IP.

**Usuario: 28 puntos.** Destacan:
- UX-01: el `.env` generado no arrancaba.
- UX-02: el mismo bug de refresh que SEC-01, encontrado de forma independiente.
- UX-03: `db migrate` sin cambios → traceback.
- Además de los puntos de uso, planteó 6 medidas de seguridad "que estorban" para debatir.

### Ronda 2: el desarrollador responde a los 53 puntos

Corrige todos los bugs confirmados y resuelve las **6 tensiones** entre seguridad y usabilidad:

| Tensión | Decisión |
|---|---|
| T1 Bloqueo de cuenta | *Smart lockout*: bloqueo por cuenta solo para IPs desconocidas, duración creciente 15 → 240 min |
| T2 Reutilización de refresh frente a pestañas | Gracia de 10 s solo desde la misma IP; responde 409 sin emitir ni revocar nada |
| T3 Enumeración en el registro | Se mantiene el 409 `email_taken` (riesgo aceptado hasta tener verificación de email) |
| T4 Límite de registro | Los 422 de política no consumen cupo |
| T5 409 genéricos | `code` + nombres de campo (nunca valores); unicidad por propietario en recursos *owned* |
| T6 Formato e idioma | `code` estable en todos los errores; API en inglés, CLI en español; sin RFC 9457 |

### Ronda 3: verificación

**Experto: "Apta para producción con condiciones".**
- Verificadas en el laboratorio: SEC-01, 07, 11, 12, 13, 14, 16 y 19.
- Acepta T1 y T2 con riesgo residual, y T3 a T6.
- No acepta que en un recurso *owned* cualquiera pueda leer por ID lo que no aparece en su listado.
- Nuevos hallazgos:
  - SEC-20: el login del titular levantaba el bloqueo para todos.
  - SEC-21: comodines en `TRUSTED_PROXIES`.
  - SEC-22: red de confianza de compose demasiado amplia.
  - SEC-23: retención indefinida de `client_ip`.
  - SEC-24: detalles varios.

**Usuario: 8,5/10.**
- De sus 34 puntos: 24 resueltos, 6 mejorados y 4 con la decisión aceptada.
- Nuevas regresiones: UX-29 (errores de política sin campo en `loc`) y UX-34 (límite de registro molesto en desarrollo).

### Ronda 4: cierre del desarrollador

| ID | Cambio |
|---|---|
| SEC-21 | En producción se rechazan comodines y redes mayores de /8 en `TRUSTED_PROXIES`; documentado que el proxy debe sobrescribir `X-Forwarded-For` |
| SEC-22 | Red `backend` con subred fija; solo se confía en el gateway |
| SEC-20 | El login del titular ya no levanta el bloqueo para otros orígenes; al cambiar la contraseña se olvidan las IPs conocidas |
| SEC-08 | *owned* con `read` más permisivo que `list` es error salvo `shared_read: true` (UX-35: el mismo flag silencia el aviso del patrón blog) |
| T2 | Documentado cómo debe reaccionar el cliente a un 409 `refresh_token_rotated` (ejemplo en TypeScript) |
| UX-29 | Un error por problema, cada uno con su campo en `loc` |
| UX-34 | Registro 5/h en producción y 50/h fuera de ella |
| SEC-23 | `apigen db prune`, limpieza en cada login, índice y política de retención documentada |
| SEC-24 | `OverflowError` solo de la BD; recuperación de Redis en un hilo con timeout; SQLite en producción requiere flag |
| Menores | 413 con `code`; `tokenUrl` en la última versión; 415 si el cuerpo no es JSON; lista de contraseñas ampliada; CLI más silenciosa; `make audit` arreglado |

La sesión principal verificó después: 132 tests, ruff limpio, `pip-audit` sin vulnerabilidades y pruebas de carga sin errores.

---

## Bugs reales encontrados en el proceso

1. **Rate limit desactivado en silencio.** SlowAPIMiddleware no ve los routers de FastAPI ≥ 0.140. Lo encontró la sesión principal y ahora se aplica con una dependencia global.
2. **"database is locked" bajo carga.** Se retenía la transacción durante Argon2 y el `busy_timeout` era demasiado corto. Lo encontraron las pruebas de estrés.
3. **Carrera en refresh concurrente → 500** (SEC-01 / UX-02). La encontraron el experto y el usuario por separado.
4. **`.env` generado no arrancaba** (UX-01).
5. **`EmailStr` en la salida → 500 con dominios especiales** (SEC-12).
6. **Enteros sin límite → 500** (SEC-07).
7. **`db migrate` sin cambios → traceback** (UX-03).

---

## Riesgos aceptados (documentados en el README)

- **Enumeración de emails en el registro (409):** se resuelve con la verificación por email (pendiente).
- **Atacante en la misma IP que la víctima (NAT):** no le afecta el bloqueo inteligente. Queda limitado por el rate limit de login (10/min y 50/h por IP) y la política de contraseñas.
- **Gracia de 10 s en refresh:** un atacante en la misma red que gane la carrera obtiene un 409, no tokens. El cliente legítimo, al reintentar o hacer logout, revoca la sesión.
- **`/logout` no invalida el access token vigente** (dura como máximo 15 min). Para cortar al instante: `/logout-all`.
- **`kid` derivado del secreto:** aceptado por el experto (no aporta ventaja práctica).

## Pendiente antes del primer despliegue real

- [ ] Probar con **PostgreSQL** (NUL en query, `constraint_name` en 409, índices parciales, int4/int8).
- [ ] Probar con **Redis** (límites compartidos entre workers y fallback/recuperación).
- [ ] Probar **Docker/compose** (subred fija, proxy de confianza, HSTS detrás del proxy).
- [ ] `make audit` en CI.

## Mejoras futuras (pospuestas con justificación)

- Verificación de email con registro 202 uniforme y desbloqueo por email.
- Comprobación de contraseñas filtradas (HIBP con k-anonimato o lista top-100k).
- Esquemas por versión en el generador (hoy las versiones comparten modelos y esquemas).
- Anillo de claves asimétricas; protección del último admin con `SELECT … FOR UPDATE`.
- Digests de imagen, usuario de BD separado para migraciones, `requirepass` en Redis.
- `unique: global` en recursos *owned*; excluir `json`/`text` de los listados.

---

## Rondas 5–8 (2026-09-26): revisión completa con graphify y funcionalidades nuevas

| Ronda | Quién | Resultado |
|---|---|---|
| 5 | Experto + usuario (guiados por el grafo) | Experto: 0 críticos, 0 altos y 0 medios; 3 bajos; 49 comprobaciones OK. Usuario: **9/10** |
| 6 | Desarrollador | SEC-30 (último admin), el soft delete respeta `on_delete`, la carga no usa BD heredada, documentación de graphify · 151 tests |
| — | Sesión principal | Hooks, acciones y cola de trabajos (`apigen worker`) · **validación con Docker** (PostgreSQL + Redis): 24/24, corregido NUL en query (500 → 422) y healthcheck del worker · `scripts/new_api.py` · `apigen docs` |
| 7 | Experto + usuario | Experto: 0 críticos y 0 altos; **4 medios**: SEC-31 (alias de permisos pisados por acciones), SEC-32 (BOLA en acciones de recursos owned), SEC-33 (los timeouts no detenían tareas thread/process), SEC-35 (el script copiaba ficheros sin versionar). Usuario: 9/10 global, 8/10 en el flujo de cliente |
| 8 | Desarrollador | Todo lo medio corregido con tests: nombres de acción reservados y alias propios, acciones owned=user solo con `shared_read`, un proceso por tarea que se mata al vencer el timeout, el script copia solo lo versionado y busca secretos antes del commit. README para clientes con guía de integración · **205 tests** (generados: 233 shop / 238 cursos) |

**Pospuesto o aceptado en la ronda 8:**
- `response_model` opcional por acción;
- el límite de trabajos pendientes en SQLite puede pasarse un poco en ráfagas (en PostgreSQL está serializado por usuario).

---

## Ronda 9 (2026-11-03): hardening SOC 2 / ISO 27701

Detalle completo, con la correspondencia con los criterios, las evidencias, los
procedimientos y la responsabilidad del operador: `docs/CUMPLIMIENTO_SOC2_ISO27701.md`
(va también a los proyectos de cliente).

| Ámbito | Cambio |
|---|---|
| API generada | Auditoría encadenada con HMAC + `apigen audit verify`. `GET /users/me/export` y `DELETE /users/me`. Retención de cuentas sin verificar y de filas con soft delete. IP truncada en el log de acceso. Cifrado AES-256-GCM de los campos `sensitive`, con rotación de clave. |
| Generador | `pii`, `sensitive` y `purpose` en las specs. Reglas de privacidad desde el diseño (sensitive solo para dueño/admin, sin filtros, orden, unique ni index). Avisos (pii público, falta `purpose`, FK a user con RESTRICT). Clasificación en `Column.info` y en el OpenAPI. Test generado de exportación y supresión. `apigen privacy inventory` se mantiene solo al día. |
| Operación | `apigen users review`, `users export` y `users revoke-sessions`. `init-env` genera las claves nuevas y la contraseña de Redis. `apigen check` muestra auditoría, privacidad y retención. |
| Cadena de suministro | Redis con `requirepass` en compose. CI (lint, tests, pip-audit, inventario, generación del ejemplo, build de la imagen) y Dependabot. |

Tests del repo: 322 → **363**. Generados: shop 392 y cursos 398, en verde.

**Pendiente:**
- validar Redis con contraseña en Docker (el daemon no estaba disponible);
- fijar las imágenes y acciones por digest;
- revisión de esta ronda por los agentes `security-expert` y `user`.
