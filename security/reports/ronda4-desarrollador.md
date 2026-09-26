# Ronda 4 (cierre) — Respuesta del desarrollador

- **Fecha:** 2026-09-25
- **Entrada:** `ronda3-seguridad.md` (condiciones bloqueantes, SEC-20…SEC-24) y `ronda3-usuario.md` (UX-29…UX-37).

**Estado final**

| Comprobación | Resultado |
|---|---|
| `.venv/bin/pytest -q -p no:cacheprovider` | **132 passed** (ronda 2: 112) |
| `.venv/bin/ruff check .` | limpio |
| Copia temporal + `apigen generate examples/shop.yaml` + `db migrate` ×2 + pytest | **158 passed**, ruff limpio. El segundo `migrate` responde "Sin cambios"; la migración autogenerada no toca `refresh_tokens`, así que el modelo y las migraciones coinciden. |
| Copia con un blog owned + `shared_read` + fk→user | 139 passed, sin avisos |
| Laboratorio `security/lab.sh` (producción + SQLite con `ALLOW_SQLITE_IN_PRODUCTION`, `TRUSTED_PROXIES=127.0.0.1`) + `security/checks/ronda3_lock_reset.py` | Ver SEC-20. 0 trazas. |

`resources/` no existe en el repo. No he lanzado pruebas de carga.

## 1. Obligatorios

| ID | Cambio (ficheros) | Test |
|---|---|---|
| **SEC-21** `TRUSTED_PROXIES` comodín | Ver detalle 1. | `test_wildcard_trusted_proxies_rejected_in_production` (`*`, `0.0.0.0/0`, `::/0`, `10.0.0.0/4`), `test_trusted_proxies_must_be_ips`, `test_production_baseline_is_valid` |
| **SEC-22** CIDR amplio en compose | Ver detalle 2. | Estático (no hay Docker) |
| **SEC-20** El login del titular levanta el bloqueo | Ver detalle 3. | `test_owner_login_during_lockout_keeps_lock_for_others` (comprueba en BD que se conservan el contador y `locked_until`), `test_password_change_forgets_familiar_ips`, y siguen pasando `test_lockout_by_third_party_does_not_lock_out_owner` y `test_admin_unlock_resets_lockout`. Laboratorio: se muestra después de la tabla. |
| **SEC-08 / UX-35** Owned con `read` más permisivo que `list` | Ver detalle 4. | `test_insecure_permission_combinations`; en la copia, el YAML `list: owner, read: user` falla con el mensaje citado y el blog con `shared_read` se genera sin avisos (139 passed). |
| **T2** Qué hacer ante un 409 `refresh_token_rotated` | Ver detalle 5. | `test_logout_after_409_revokes_the_whole_family` (carrera → 409 → `/logout` con el token viejo → el token del ganador da 401) |
| **UX-29** `loc` por campo y un error por problema | Ver detalle 6. | `test_password_policy_errors_point_to_the_field`, `test_partial_update_messages` (con `loc`); plantilla `test_immutable_field_rejected_on_patch` |
| **UX-34** El límite de registro estorba en desarrollo | Ver detalle 7. | `test_register_limit_depends_on_environment`, `test_weak_passwords_do_not_consume_register_quota` |
| **SEC-23** Retención de `client_ip` | Ver detalle 8. | `test_prune_removes_only_dead_old_sessions` (borra la sesión muerta antigua; conserva la fila rotada antigua de una sesión viva y la fila actual). En la copia: `apigen db prune` → `✓ 0 refresh tokens borrados…`; upgrade y downgrade de las migraciones correctos. |
| **SEC-24** Detalles | Ver detalle 9. | `test_generic_overflow_error_is_still_a_500`, `test_repository_converts_driver_overflow`, `test_backend_recovery_check_does_not_block` (un `check()` que tarda 2 s → la función vuelve en menos de 1,5 s), `test_sqlite_in_production_needs_explicit_opt_in`; plantilla `test_int_out_of_range_is_422`. Laboratorio con SQLite y la variable: arranca bien. |
| **Makefile `audit`** | `uv export --frozen --no-hashes --no-emit-project … \| uvx pip-audit --no-deps --disable-pip -r /dev/stdin`. `--no-emit-project` evita la línea `-e .`, que pip-audit no sabe auditar. | Resultado del coordinador: 0 vulnerabilidades en 250 dependencias. Añadido al checklist ("también en CI"). |

**Detalle por punto**

1. **SEC-21, `TRUSTED_PROXIES` comodín.**
   - `app/core/config.py`: `_valid_proxies` exige una IP o un CIDR válidos siempre.
   - `_proxy_problems`, **en producción**, da error con `*`, con redes más amplias que /8 (IPv4) o /32 (IPv6), lo que incluye `0.0.0.0/0` y `::/0`, y avisa por encima de /16 y /48.
   - Documentado en README §9, `.env.example` y la guía: el proxy debe **sobrescribir** `X-Forwarded-For` (snippet de nginx con `proxy_set_header X-Forwarded-For $remote_addr;` y `X-Forwarded-Proto`).

2. **SEC-22, CIDR amplio en compose.**
   - `docker-compose.yml`: red `backend` con `ipam` fija `172.30.57.0/24` (gateway `172.30.57.1`) para api, db y redis.
   - `TRUSTED_PROXIES=${TRUSTED_PROXIES:-172.30.57.1}`, es decir, solo el gateway, que es la IP con la que llega un proxy del host a `127.0.0.1:8000`.
   - Documentado: si el proxy es un contenedor, se le da una `ipv4_address` fija y se confía en esa IP.
   - `init-env --production` y la guía ya no mencionan `172.16.0.0/12`.

3. **SEC-20, el login del titular levanta el bloqueo.**
   - `app/services/auth.py` (`authenticate`): un login correcto **durante un bloqueo** (desde una IP conocida) solo actualiza `last_login_at`. Ya no toca `failed_login_attempts` ni `locked_until`.
   - El contador solo se reinicia con un login correcto fuera de bloqueo o con `unlock`.
   - **Condición T1:** `_is_familiar` cuenta solo los logins con `created_at >= max(hace LOGIN_FAMILIAR_DAYS, password_changed_at)`.
   - Documentado en el README §10 (procedimiento `unlock` y alerta a vigilar: `auth.account.locked` con nivel ERROR).
   - **Laboratorio** (`ronda3_lock_reset.py`):

     | Paso | Códigos |
     |---|---|
     | fallos del atacante | `[401×5]` |
     | titular desde IP nueva | `401` |
     | titular desde IP conocida | `200` |
     | atacante después | `[401×6]` |

     Los 6 intentos del atacante se registran como `auth.login.blocked` (sin evaluar la contraseña). En la ronda 3 eran 5 contraseñas evaluadas de nuevo.

4. **SEC-08 / UX-35, owned con `read` más permisivo que `list`.**
   - `apigen/spec.py`: nuevo flag de spec **`shared_read: true`** (CLI `--shared-read`).
   - Owned + `read` más permisivo que `list` (p. ej. `list: owner`, `read: user/public`) pasa a ser **error** salvo `shared_read`: *"…deja leer por ID filas ajenas que el listado oculta (BOLA). Si es intencionado, añade `shared_read: true`"*.
   - `shared_read` también **silencia** el aviso de owned + `list/read` public o user (el blog). `shared_read` sin `owned` es un error.
   - Se guarda en `resources/*.yaml` solo si es `true` y aparece como `shared-read` en `apigen list`.
   - La guía recomienda `--owned --shared-read` para el blog.

5. **T2, qué hacer ante un 409 `refresh_token_rotated`.**
   - README §6 y guía §4 explican el procedimiento:
     1. si en el almacenamiento hay un refresh más nuevo, reintentar con él;
     2. si no, llamar a `POST /auth/logout` con el **viejo** e ir al login. Así se revoca la familia entera, incluido el token del ganador.
   - Ejemplo de cliente `fetch` en TypeScript que **serializa** los refresh (una promesa compartida en vuelo) y aplica esas dos ramas, con la nota sobre `navigator.locks`.
   - OpenAPI de `/auth/refresh` documenta el 409 con esa instrucción.

6. **UX-29, `loc` por campo y un error por problema.**
   - `app/schemas/common.py`: `raise_field_errors()` lanza un `ValidationError` con varios `InitErrorDetails`. Pydantic antepone el `loc` exterior, así que llegan como `["body","<campo>"]`.
   - Contraseña: un `password_policy` por problema, con `loc: ["body","password"]` y `msg` "Password …".
   - `immutable_field` y `null_not_allowed`: un error por campo.
   - `/users/me/password`: un error por problema, con `loc: ["body","new_password"]`.
   - Se mantiene el `type`.

7. **UX-34, límite de registro en desarrollo.**
   - `RATE_LIMIT_REGISTER` es `None` por defecto: **5/hour en producción y 50/hour fuera** (validador de `Settings`). Un valor explícito se respeta.
   - En `.env.example` queda vacío y documentado. Producción no se debilita.

8. **SEC-23, retención de `client_ip`.**
   - `app/services/auth.py`: `prune_refresh_tokens()` borra las filas con `created_at` anterior a `LOGIN_FAMILIAR_DAYS` **cuya sesión está muerta** (ningún token vivo en la familia). Las filas rotadas de sesiones vivas se conservan para no perder la detección de robo.
   - Limpieza oportunista de las filas del usuario en cada login (`start_session`), más el comando **`apigen db prune`** para el resto (a diario).
   - Índice `(user_id, client_ip)`: modelo + migración nueva `c4e8b19d0a52`.
   - Retención y base legal documentadas en el README §10 y `.env.example`.
   - Además, la migración `a7d3c2e1b4f0` se ha renombrado a `20260925_1640_…` para que el orden de los ficheros coincida con la cadena (UX-33). El ID de revisión no cambia.

9. **SEC-24, detalles.**
   - **`OverflowError`:** se quita el handler global. `app/crud/base.py` (`_commit`) convierte en `DatabaseValueError` solo el `OverflowError` del driver, y este se transforma en un 422 `invalid_value`. Cualquier otro `OverflowError` sigue siendo 500.
   - **Redis:** la comprobación de recuperación (`_maybe_recover_backend`) ya es asíncrona. Se ejecuta en un hilo con `move_on_after(0.5)` y `abandon_on_cancel`, así que no bloquea el event loop. Compose y `.env.example` usan `?socket_timeout=0.5&socket_connect_timeout=0.5` (verificado que redis-py y limits lo interpretan).
   - **SQLite en producción:** pasa a ser un **error** salvo `ALLOW_SQLITE_IN_PRODUCTION=true`, lo que cubre un `DATABASE_URL` vacío. `security/lab.sh` exporta esa variable.

## 2. Menores

| ID | Decisión | Cambio | Test |
|---|---|---|---|
| **UX-30** 413 sin `code` | Hecho | `middleware.py`: `BodyTooLarge.code` y el cuerpo de `_send_413` incluyen `"code":"body_too_large"`. | `test_body_size_limit` |
| **UX-31** `tokenUrl` y respuestas de auth | Hecho | `deps._login_version()`: `tokenUrl` usa la versión más reciente no deprecada. `login` documenta 401/415/429, `refresh` 401/409/415/429 y `register` 409/415/429, todos con `ErrorBody`. | `test_swagger_token_url_uses_active_version` |
| **UX-32** CLI | Hecho | `password_problems(..., lang="es")` en `createsuperuser` ("Contraseña débil: debe tener al menos 12 caracteres"). Las opciones desconocidas sugieren alternativa (`maxx` → "¿quisiste decir 'max'?"). `check` muestra `CORS  localhost:* (desarrollo)`. | `test_cli_password_policy_in_spanish`, `test_cli_errors_are_translated_with_suggestions` |
| **UX-33** `db upgrade/downgrade/current` verbosos | Hecho | Silenciosos salvo con `--verbose`, con una línea de confirmación. Se renombra el fichero de la migración (ver SEC-23). | Verificado en la copia |
| **UX-36** Patrones de teclado | Hecho (barato) | Lista de contraseñas comunes ampliada, más una regla de **secuencia**: tramos de filas QWERTY/QWERTZ/AZERTY, diagonales (`1qaz2wsx…`), alfabeto y dígitos, también invertidos. La lista top-10k/100k sigue pendiente (SEC-15). | `test_keyboard_sequences_are_rejected` (`qwertyuiopas`, `1qaz2wsx3edc`, `abcdefghijklm`, `lkjhgfdsapoiu`) |
| **UX-37** 415 en endpoints JSON | Hecho | `errors.py`: si el 422 se debe solo a que el cuerpo no es JSON (Content-Type presente y no JSON, error de forma en `["body"]`), responde **415 `expects_json`**. Sin Content-Type se mantiene el 422 (test existente). | `test_non_json_body_gets_415` |
| **SEC-10** (residual) | Documentado | Comentario en el router generado para fk→user y nota en la guía (§3). | — |
| Sugerencia T1 del usuario | Hecho | `.env.example` explica cómo bajar `LOGIN_LOCKOUT_MAX_MINUTES`. | — |

## 3. Pendiente

- **Condición 6 del experto:** probar con PostgreSQL, Redis y Docker. En este entorno no se puede. Queda en la lista "Pendiente de verificar en un entorno real" del README §9:
  - NUL en parámetros de query;
  - índices parciales;
  - `constraint_name`;
  - fallback y recuperación de Redis;
  - compose, HSTS y XFF detrás del proxy real.
- Sigue pospuesto desde la ronda 2:
  - verificación de email y desbloqueo por email (T1/T3);
  - lista de contraseñas comprometidas top-10k (condición del experto si el registro es público; añadida al checklist);
  - esquemas por versión;
  - digests de imagen, usuario de migración separado y `requirepass` en Redis.

## 4. Cambios visibles en la API

- Los 422 de política, inmutables y null vuelven a tener `loc` por campo y ahora llegan como varios errores.
- Cuerpo no JSON con Content-Type → 415 `expects_json` (antes 422).
- En producción, `TRUSTED_PROXIES` comodín o SQLite sin `ALLOW_SQLITE_IN_PRODUCTION` impiden arrancar.
- Specs: owned + `read` más permisivo que `list` exige `shared_read: true`.
- Migración nueva `c4e8b19d0a52`.

## 5. Ficheros modificados en esta ronda

**Aplicación**
- `app/core/config.py`
- `app/core/security.py`
- `app/core/errors.py`
- `app/core/exceptions.py`
- `app/core/middleware.py`
- `app/core/rate_limit.py`
- `app/services/auth.py`
- `app/crud/base.py`
- `app/api/deps.py`
- `app/api/v1/endpoints/auth.py`
- `app/api/v1/endpoints/users.py`
- `app/schemas/common.py`
- `app/schemas/user.py`
- `app/models/refresh_token.py`

**Migraciones**
- `alembic/versions/20260925_1640_a7d3c2e1b4f0_refresh_token_client_ip.py` (renombrada)
- `alembic/versions/20260925_1641_c4e8b19d0a52_refresh_token_client_ip_index.py` (nueva)

**Generador**
- `apigen/spec.py`
- `apigen/cli.py`
- `apigen/templates/router.py.j2`

**Tests**
- `tests/test_auth.py`
- `tests/test_config.py`
- `tests/test_security.py`
- `tests/test_generator.py`

**Despliegue, configuración y documentación**
- `docker-compose.yml`
- `.env.example`
- `Makefile`
- `security/lab.sh`
- `README.txt`
- `guia/README.txt`
- `security/reports/ronda4-desarrollador.md`
