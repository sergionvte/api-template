# Inventario de datos personales

Registro de actividades de tratamiento de esta API (ISO/IEC 27701 7.2.8, RGPD art. 30)
e identificación de información confidencial (SOC 2 C1.1).

## A completar por el responsable (fuera de los marcadores: apigen no lo toca)

| Campo | Valor |
|---|---|
| Responsable del tratamiento | _(empresa, CIF, dirección)_ |
| Delegado de protección de datos / contacto de privacidad | _(email)_ |
| Base legal de cada finalidad | _(contrato, consentimiento, interés legítimo...)_ |
| Encargados (hosting, base de datos, proveedor SMTP...) y sus contratos (DPA) | _(lista)_ |
| Transferencias internacionales y garantías | _(ninguna / cláusulas tipo...)_ |
| Plazo de conservación de los logs (auditoría y acceso) en el SIEM | _(recomendado: 1 año)_ |

<!-- apigen:inventory:begin -->
## Tablas del núcleo (plantilla)

| Tabla | Datos personales | Finalidad | Conservación |
|---|---|---|---|
| `users` | email, full_name, hashed_password (Argon2id), role, locale, last_login_at, email_verified_at, intentos fallidos y bloqueo | Cuenta y autenticación | Hasta la supresión (DELETE /users/me o un admin). Cuentas nunca verificadas con EMAIL_VERIFICATION=required: 30 días (UNVERIFIED_ACCOUNT_RETENTION_DAYS) |
| `refresh_tokens` | client_ip (o prefijo /64), user_agent, hash del token | Sesiones, detección de robo de tokens y bloqueo inteligente | Mientras la sesión viva + 30 días (LOGIN_FAMILIAR_DAYS) |
| `account_tokens` | email de destino, hash del token | Recuperación de contraseña, verificación y cambio de email | 1 día tras caducar o usarse |
| `email_log` | user_id, hash del destinatario, tipo de correo (sin dirección ni contenido) | Cupos antiabuso e idempotencia de envíos | 2 días |
| `jobs` | owner_id; el payload puede incluir datos de la petición (p. ej. el email nuevo) | Cola de trabajos en segundo plano | 7 días tras terminar (JOBS_RETENTION_DAYS) |
| `log de auditoría` | user_id, client_ip completa, request_id (nunca emails, contraseñas ni tokens) | Seguridad y trazabilidad (SOC 2 CC7.2) | Fuera de la API (SIEM): ver «A completar» |
| `log de acceso` | client_ip según ACCESS_LOG_IP (por defecto truncada: /24 o /48), ruta, estado | Operación y diagnóstico | Fuera de la API (SIEM): ver «A completar» |

## Recursos generados (`resources/*.yaml`)

_(ninguno todavía)_

## Derechos de los interesados

| Derecho | Cómo se ejerce |
|---|---|
| Acceso y portabilidad (ISO 27701 7.3.8) | `GET /api/<versión>/users/me/export`: JSON con la cuenta, sesiones, correos, trabajos y filas de los recursos del usuario (sin campos `write_only` ni hashes) |
| Rectificación (7.3.6) | `PATCH /api/<versión>/users/me` y el `PATCH` de cada recurso propio; email: `POST /users/me/email` |
| Supresión (7.3.6) | `DELETE /api/<versión>/users/me` con la contraseña (si ALLOW_SELF_DELETION=true) o `DELETE /users/{id}` (admin). Borra en cascada lo que le pertenece |
| Evidencias | Eventos `privacy.export`, `privacy.erasure`, `retention.prune` en el log de auditoría |

<!-- apigen:inventory:end -->
