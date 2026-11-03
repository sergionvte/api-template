# Hardening SOC 2 e ISO/IEC 27701: controles, evidencias y responsabilidades

**Fecha:** 2026-11-03 · **Alcance:** el generador `apigen` y las APIs que genera.

**Marcos de referencia:**
- SOC 2: Trust Services Criteria del AICPA (2017, puntos de enfoque revisados en 2022). Criterios comunes (CC), confidencialidad (C) y privacidad (P).
- ISO/IEC 27701: se cita con la numeración de la edición 2019 (cláusula 6, extensión de ISO 27002, y cláusula 7, controles del responsable). En la edición 2025, que es una norma independiente, los mismos controles están en el Anexo A.

> **Una plantilla no "cumple" SOC 2 ni ISO 27701 por sí sola.** SOC 2 es un informe de un auditor sobre una organización, e ISO 27701 es la certificación de un sistema de gestión (PIMS).
>
> Lo que sí hace este código:
> 1. implementa los **controles técnicos** que esos marcos esperan de una aplicación;
> 2. **genera evidencias** de que esos controles funcionan;
> 3. deja claro qué parte depende **del operador** (sección 4).

---

## 1. Controles añadidos en este hardening

| ID | Control | SOC 2 | ISO 27701 | Dónde / evidencia |
|---|---|---|---|---|
| HD-01 | **Auditoría a prueba de manipulaciones.** Cada proceso encadena sus eventos con HMAC-SHA256 (`AUDIT_HMAC_KEY`): `audit_stream`, `audit_seq`, `audit_prev` y `audit_hash`. `apigen audit verify` detecta eventos alterados, insertados o borrados del medio. | CC7.2, CC7.3, CC4.1 | 6.9.4.1, 6.9.4.2 | `app/core/audit.py` · `tests/test_audit.py` · `apigen audit verify logs.json` |
| HD-02 | **Minimización de IPs en el log de acceso.** `ACCESS_LOG_IP=truncated` (/24 en IPv4, /48 en IPv6) por defecto. La auditoría conserva la IP completa porque su finalidad es la seguridad. | P3.1, C1.1 | 7.4.4, 7.4.5 | `app/core/middleware.py:log_ip` · `tests/test_audit.py` |
| HD-03 | **Derecho de acceso y portabilidad.** `GET /users/me/export` devuelve un JSON con la cuenta, las sesiones, los correos, los trabajos y las filas de todos los recursos ligados al usuario. Nunca incluye hashes ni campos `write_only`. Rate limit `RATE_LIMIT_PRIVACY`; evento `privacy.export`. Para quien no puede iniciar sesión: `apigen users export --email` (solo el operador). | P5.1 | 7.3.6, 7.3.8, 7.3.9 | `app/services/privacy.py` · `tests/test_privacy.py` · test generado `test_privacy_export_and_erasure` |
| HD-04 | **Derecho de supresión.** `DELETE /users/me` pide la contraseña actual, protege al último admin y borra en cascada todo lo del usuario. Se puede desactivar con `ALLOW_SELF_DELETION`. El log guarda solo el ID (seudónimo). El generador avisa si una FK a `user` con RESTRICT impediría la supresión. | P4.3 | 7.3.6, 7.4.5 | `app/api/v1/endpoints/users.py:delete_me` · `tests/test_privacy.py` |
| HD-05 | **Retención automática.** `apigen db prune` borra además las cuentas nunca verificadas (`UNVERIFIED_ACCOUNT_RETENTION_DAYS`, solo con verificación `required`) y las filas borradas lógicamente (`SOFT_DELETE_RETENTION_DAYS`). Cada ejecución deja el evento `retention.prune` con lo borrado. | C1.2, P4.2, P4.3 | 7.4.7, 7.4.8 | `app/services/privacy.py` · `apigen db prune` · `tests/test_privacy.py` |
| HD-06 | **Clasificación de datos en el generador.** Las specs admiten `pii: true` y `sensitive: true` por campo y `purpose:` por recurso. La clasificación llega a `Column.info`, al OpenAPI (`x-data-classification`) y al inventario. | C1.1 | 6.5.2.1, 6.5.2.2, 7.2.1 | `apigen/spec.py` · `apigen/codegen.py` · `tests/test_generator.py` |
| HD-07 | **Privacidad desde el diseño en las specs.** Un campo `sensitive` solo lo leen su dueño o un admin, y no admite filtros, búsqueda, ordenación, `unique` ni `index` (todos ellos permiten deducir el valor). El generador avisa si hay datos `pii` legibles sin login o si falta `purpose`. | CC6.1, C1.1 | 7.4.1, 7.4.2, 7.4.4 | `ResourceSpec._check` y `warnings()` · `tests/test_generator.py` |
| HD-08 | **Cifrado en reposo de los campos `sensitive`** (str, text y email) con AES-256-GCM: nonce aleatorio y autenticación. Tiene `kid` y rotación (`DATA_ENCRYPTION_PREVIOUS_KEYS`). En producción, la API y el worker no arrancan si hay columnas cifradas sin `DATA_ENCRYPTION_KEY`. | CC6.1, C1.1 | 6.7.1.1, 6.7.1.2 | `app/db/crypto.py` · `tests/test_crypto.py` |
| HD-09 | **Inventario de datos personales** (registro de actividades de tratamiento). `apigen privacy inventory` genera `docs/DATA_INVENTORY.md`. Se actualiza solo con `generate`, `add` y `remove`, y CI comprueba que está al día (`--check`). | C1.1, P1.1 | 7.2.1, 7.2.2, 7.2.8 | `apigen/privacy.py` · `docs/DATA_INVENTORY.md` |
| HD-10 | **Revisión periódica de accesos.** `apigen users review` lista los admins, las cuentas inactivas, bloqueadas y sin verificar. Con `--json` sirve de evidencia; deja el evento `admin.access_review`. | CC6.2, CC6.3 | 6.6.2 (27002 9.2.5) | `apigen/cli.py` · `tests/test_privacy.py` |
| HD-11 | **Respuesta a incidentes.** `apigen users revoke-sessions --email X` o `--all` invalida al instante los access tokens y revoca los refresh tokens. Evento `admin.sessions.revoke`. | CC7.4, CC7.5 | 6.13.1.5 | `apigen/cli.py` · `tests/test_privacy.py` |
| HD-12 | **Redis con contraseña** en docker compose (`REDIS_PASSWORD`, `--requirepass`). Un contenedor comprometido de la red ya no puede borrar los contadores del rate limit ni del bloqueo de login. | CC6.1, CC6.6 | 6.10.1 | `docker-compose.yml` |
| HD-13 | **Gestión de secretos.** `apigen init-env` genera `AUDIT_HMAC_KEY`, `DATA_ENCRYPTION_KEY`, `REDIS_PASSWORD` y `POSTGRES_PASSWORD`. La configuración rechaza claves cortas o repetidas (la de auditoría igual a `SECRET_KEY`, por ejemplo). | CC6.1 | 6.7.1.2 | `apigen/cli.py:init_env` · `app/core/config.py` · `tests/test_config.py` |
| HD-14 | **Control de cambios y vulnerabilidades.** CI (`.github/workflows/ci.yml`) pasa lint, tests, `pip-audit`, el `--check` del inventario, la generación del ejemplo y el build de la imagen. Dependabot cubre uv, GitHub Actions, Docker y compose. | CC8.1, CC7.1 | 6.11.2.1, 6.11.2.5, 6.9.6.1 | `.github/` |
| HD-15 | **Visibilidad de la configuración.** `apigen check` muestra la auditoría (HMAC/JSON), la IP en logs, los derechos del interesado y la retención. Avisa en producción sin `AUDIT_HMAC_KEY` o con `LOG_JSON=false`. | CC7.1 | 6.9.4.1 | `apigen check` |

### Controles que ya existían (relación con los criterios)

| Control existente | SOC 2 | ISO 27701 |
|---|---|---|
| Argon2id (RFC 9106), política de contraseñas, bloqueo inteligente, rate limit por usuario/IP | CC6.1, CC6.6 | 6.6.4.2, 6.6.4.3 |
| JWT de 15 min; refresh opaco hasheado con rotación, detección de reutilización y caducidad absoluta | CC6.1 | 6.6.4.2 |
| Roles y scopes; aislamiento por dueño (404, no 403); protección del último admin | CC6.1, CC6.3 | 6.6.2.2, 6.6.1.2 |
| Validación estricta (extra=forbid, límites de tamaño, NUL, enteros acotados) | PI1.2, CC6.1 | 6.11.2.5 |
| Cabeceras de seguridad (HSTS, CSP, no-store), TrustedHost, CORS cerrado, docs apagados en producción | CC6.6, CC6.7 | 6.10.1, 7.4.9 |
| La configuración insegura impide arrancar en producción | CC7.1, CC8.1 | 6.11.2.5 |
| Contenedores sin root, read-only, `cap_drop: ALL`, `no-new-privileges`. El worker no recibe la clave JWT; la API no recibe las credenciales SMTP | CC6.1, CC6.8 | 6.6.2.3 |
| Tokens de cuenta de un solo uso, hasheados; enlaces solo hacia `FRONTEND_URL`; respuestas uniformes que no revelan cuentas | CC6.1 | 7.4.1 |
| Logs sin emails, contraseñas ni tokens; `request_id`; escape de CR/LF | CC7.2 | 6.9.4.1, 7.4.5 |
| Retención de IPs de sesión (`LOGIN_FAMILIAR_DAYS`), de trabajos y de tokens de cuenta | C1.2, P4.2 | 7.4.7 |
| Pruebas de carga y de seguridad por rondas (`security/`) | CC4.1, CC7.1 | 6.15.2.1 |

---

## 2. Procedimientos operativos

| Frecuencia | Acción | Evidencia |
|---|---|---|
| Diaria (cron/CronJob) | `apigen db prune` | Evento `retention.prune` con lo borrado |
| Trimestral | `apigen users review --json > evidencias/accesos-AAAA-TN.json`. Degrada o desactiva lo que sobre | JSON firmado/archivado y evento `admin.access_review` |
| Semanal y tras cada incidente | `apigen audit verify logs/*.json` (en orden de rotación) | Salida del comando |
| Por cada cambio | PR con CI en verde y revisión (protege `main`) | Historial de PRs |
| Por cada nuevo recurso con datos personales | Marca `pii`/`sensitive` y `purpose` en la spec, y revisa `docs/DATA_INVENTORY.md` | Inventario versionado |
| Cuando lo pida un titular | Acceso: él mismo con `GET /users/me/export` o, tras verificar su identidad, `apigen users export --email`. Supresión: `DELETE /users/me` o `DELETE /users/{id}` (admin). Plazo RGPD: 1 mes | Eventos `privacy.export` y `privacy.erasure` |
| Incidente (credenciales o claves) | 1) `apigen users revoke-sessions --all`; 2) rotar `SECRET_KEY` dejando `JWT_PREVIOUS_SECRET_KEYS` vacío; 3) si se filtró la BD, rotar `DATA_ENCRYPTION_KEY` (la antigua pasa a `PREVIOUS`); 4) evaluar la notificación de la brecha (RGPD: 72 h a la autoridad) | Eventos `admin.sessions.revoke` e informe del incidente |

**Rotar `AUDIT_HMAC_KEY`** abre cadenas nuevas. Para verificar los logs anteriores, ejecuta `apigen audit verify` con la clave antigua en el entorno.

---

## 3. Riesgos residuales y decisiones

- **Corte del final de la cadena de auditoría.** Borrar los últimos eventos de un flujo no se detecta en local. Mitigación: enviar los logs JSON en tiempo real a un almacén externo inmutable (SIEM o bucket WORM).
- **Solo se cifran los `sensitive` de tipo str, text y email.** Los de tipo int, date o json quedan protegidos por permisos y por la prohibición de filtrar u ordenar, pero en claro en la BD.
- **Valores en claro anteriores.** Al marcar como `sensitive` una columna que ya tenía datos, los valores antiguos se leen tal cual y se cifran al volver a guardarse. Para cifrarlos todos de golpe, haz una migración de datos que reescriba cada fila.
- **Exportación limitada a `PRIVACY_EXPORT_MAX_ROWS` filas por tabla** (si se llega al límite, se marca `truncated`). Para volúmenes mayores, el operador atiende la solicitud.
- **Los backups conservan datos ya suprimidos** hasta que caducan. El operador debe fijar y documentar esa retención (ISO 27701 7.4.7).
- **Imágenes base y acciones de CI por etiqueta, no por digest/SHA.** Dependabot las mantiene; fijarlas por digest queda en manos del operador.
- **Redis con contraseña: no validado en vivo en esta ronda** (Docker no estaba disponible). Sí se validó `docker compose config`.

---

## 4. Responsabilidad del operador (fuera del código)

| Área | SOC 2 | ISO 27701 |
|---|---|---|
| Políticas de seguridad y privacidad, análisis de riesgos, roles y formación | CC1, CC2, CC3, CC5 | 5.x, 6.4 |
| Aviso de privacidad, base legal, consentimiento cuando aplique | P1, P2 | 7.2.2-7.2.4, 7.3.2, 7.3.3 |
| Evaluación de impacto (DPIA) para datos `sensitive` | CC3.2 | 7.2.5 |
| Contratos con encargados (hosting, BD, SMTP) y gestión de proveedores | CC9.2 | 7.2.6, 7.5.x |
| TLS en el proxy, cifrado de discos/volúmenes y backups, pruebas de restauración | CC6.7, A1.2, A1.3 | 6.9.3, 7.4.9 |
| SIEM: conservación (recomendado ≥ 1 año), alertas sobre `auth.*` y `admin.*` | CC7.2, CC7.3 | 6.9.4 |
| Custodia de claves (`SECRET_KEY`, `AUDIT_HMAC_KEY`, `DATA_ENCRYPTION_KEY`) en un gestor de secretos, con copia de la de datos | CC6.1 | 6.7.1.2 |
| Protección de rama, revisión obligatoria, pentest periódico | CC8.1, CC4.1 | 6.11.2, 6.15.2 |
| Gestión de brechas y notificación (autoridad e interesados) | CC7.4, CC7.5 | 6.13.1.5 |

Completa también la tabla «A completar» de `docs/DATA_INVENTORY.md` (responsable, DPO, base legal, encargados, transferencias y conservación de logs).
