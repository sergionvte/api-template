"""Configuración central de la aplicación.

Todo se lee de variables de entorno (o de `.env`). En producción la configuración
se valida de forma estricta y la aplicación se niega a arrancar si detecta
valores inseguros.
"""

from __future__ import annotations

import ipaddress
import logging
import secrets
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from limits import parse_many
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

logger = logging.getLogger(__name__)

_INSECURE_SECRETS = {
    "",
    "secret",
    "changeme",
    "change-me",
    "change_me",
    "please-change-me",
    "supersecret",
    "your-secret-key",
}
_SYMMETRIC_ALGORITHMS = {"HS256", "HS384", "HS512"}

CommaList = Annotated[list[str], NoDecode]


class Environment(StrEnum):
    development = "development"
    testing = "testing"
    production = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
        # `DOCS_ENABLED=` (vacío) en .env significa "valor por defecto", no un error
        # de validación: así el .env que genera `apigen init-env` arranca tal cual.
        env_ignore_empty=True,
    )

    # --- General -----------------------------------------------------------
    PROJECT_NAME: str = "API Template"
    PROJECT_VERSION: str = "0.1.0"
    # Texto que aparece en la portada de /docs (OpenAPI `info.description`).
    PROJECT_DESCRIPTION: str = ""
    ENVIRONMENT: Environment = Environment.development
    DEBUG: bool = False
    # None = activado salvo en producción.
    DOCS_ENABLED: bool | None = None
    API_PREFIX: str = "/api"

    # --- JWT -----------------------------------------------------------------
    SECRET_KEY: SecretStr = SecretStr("")
    JWT_ALGORITHM: Literal[
        "HS256", "HS384", "HS512", "RS256", "RS384", "RS512", "ES256", "ES384", "EdDSA"
    ] = "HS256"
    # Solo para algoritmos asimétricos (RS*/ES*/EdDSA).
    JWT_PRIVATE_KEY_FILE: Path | None = None
    JWT_PUBLIC_KEY_FILE: Path | None = None
    # Claves HS antiguas que se siguen aceptando para verificar durante una rotación.
    JWT_PREVIOUS_SECRET_KEYS: CommaList = []
    JWT_ISSUER: str = "api-template"
    JWT_AUDIENCE: str = "api-template-clients"
    JWT_LEEWAY_SECONDS: int = Field(default=10, ge=0, le=120)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, ge=1, le=1440)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, ge=1, le=90)

    # --- Política de autenticación -----------------------------------------
    ALLOW_REGISTRATION: bool = True
    PASSWORD_MIN_LENGTH: int = Field(default=12, ge=8, le=64)
    PASSWORD_MAX_LENGTH: int = Field(default=128, ge=64, le=1024)
    LOGIN_MAX_ATTEMPTS: int = Field(default=5, ge=1)
    LOGIN_LOCKOUT_MINUTES: int = Field(default=15, ge=1)
    # Cada bloqueo consecutivo dobla la duración hasta este tope.
    LOGIN_LOCKOUT_MAX_MINUTES: int = Field(default=240, ge=1)
    # Durante un bloqueo, un cliente (IP o /64) desde el que el usuario ya inició
    # sesión en estos días puede seguir entrando ("smart lockout"): un tercero no
    # puede dejar fuera al titular solo por conocer su email.
    LOGIN_FAMILIAR_DAYS: int = Field(default=30, ge=0, le=365)
    # Reutilizar un refresh token ya rotado revoca la sesión (robo). Excepción:
    # si ocurre en estos segundos, desde la misma IP y la sesión sigue viva, se
    # trata como una carrera legítima (dos pestañas) y se responde 409 sin revocar.
    # 0 = sin periodo de gracia.
    REFRESH_REUSE_GRACE_SECONDS: int = Field(default=10, ge=0, le=60)
    # Coste de Argon2id (por defecto: RFC 9106, 64 MiB / 3 pasadas). Bajarlo acelera
    # el login pero abarata los ataques offline si se filtra la BD. Mínimo OWASP:
    # 19 MiB (19456 KiB), 2 pasadas, 1 hilo.
    ARGON2_TIME_COST: int = Field(default=3, ge=2, le=20)
    ARGON2_MEMORY_COST_KIB: int = Field(default=65_536, ge=19_456, le=1_048_576)
    ARGON2_PARALLELISM: int = Field(default=4, ge=1, le=16)
    # Hashes Argon2 calculándose a la vez (cada uno usa ARGON2_MEMORY_COST_KIB de RAM).
    PASSWORD_HASH_CONCURRENCY: int = Field(default=8, ge=1, le=256)
    # Sesiones de refresh activas por usuario; las más antiguas se revocan.
    MAX_SESSIONS_PER_USER: int = Field(default=10, ge=1, le=1000)

    # --- Base de datos -------------------------------------------------------
    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"
    # En producción SQLite es un error salvo que se confirme expresamente (p. ej.
    # laboratorios o demos de un solo proceso).
    ALLOW_SQLITE_IN_PRODUCTION: bool = False
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = Field(default=10, ge=1)
    DB_MAX_OVERFLOW: int = Field(default=20, ge=0)
    DB_POOL_TIMEOUT: int = Field(default=30, ge=1)
    DB_POOL_RECYCLE: int = Field(default=1800, ge=-1)
    # Solo PostgreSQL: corta consultas que tarden demasiado (0 = sin límite).
    DB_STATEMENT_TIMEOUT_MS: int = Field(default=15000, ge=0)

    # --- Rate limiting (SlowAPI) --------------------------------------------
    RATE_LIMIT_ENABLED: bool = True
    # memory:// (una instancia) o redis://host:6379/0 (varias instancias/workers).
    RATE_LIMIT_STORAGE_URI: str = "memory://"
    RATE_LIMIT_STRATEGY: Literal["fixed-window", "moving-window", "sliding-window-counter"] = (
        "sliding-window-counter"
    )
    RATE_LIMIT_DEFAULT: str = "120/minute"
    RATE_LIMIT_GLOBAL: str = "1000/minute"
    RATE_LIMIT_LOGIN: str = "10/minute;50/hour"
    # None = 5/hour en producción y 50/hour fuera de ella (en desarrollo creas
    # muchas cuentas de prueba seguidas).
    RATE_LIMIT_REGISTER: str | None = None
    RATE_LIMIT_REFRESH: str = "30/minute"
    RATE_LIMIT_HEADERS: bool = True

    # --- HTTP -------------------------------------------------------------
    CORS_ORIGINS: CommaList = []
    CORS_ALLOW_CREDENTIALS: bool = False
    ALLOWED_HOSTS: CommaList = ["*"]
    # IPs/CIDR de proxies de confianza cuyos X-Forwarded-For se aceptan.
    TRUSTED_PROXIES: CommaList = []
    MAX_BODY_SIZE: int = Field(default=1_048_576, ge=1024)
    GZIP_MIN_SIZE: int = Field(default=1024, ge=0)  # 0 = desactivado
    HSTS_SECONDS: int = Field(default=63_072_000, ge=0)

    # --- Tareas en segundo plano (apigen worker) -----------------------------
    JOBS_CONCURRENCY: int = Field(default=4, ge=1, le=256)  # trabajos a la vez por worker
    JOBS_POLL_INTERVAL: float = Field(default=1.0, ge=0.05, le=60)  # s entre consultas
    JOBS_PROCESS_WORKERS: int = Field(default=2, ge=1, le=64)  # procesos para executor=process
    JOBS_DEFAULT_TIMEOUT: int = Field(default=300, ge=1, le=86_400)
    JOBS_LEASE_GRACE: int = Field(default=60, ge=5, le=3600)  # margen sobre el timeout
    JOBS_RECLAIM_INTERVAL: int = Field(default=30, ge=5, le=3600)
    JOBS_SHUTDOWN_GRACE: int = Field(default=30, ge=0, le=3600)
    JOBS_MAX_PENDING_PER_USER: int = Field(default=20, ge=0)  # 0 = sin límite
    JOBS_MAX_PAYLOAD_BYTES: int = Field(default=65_536, ge=256)
    JOBS_MAX_RESULT_BYTES: int = Field(default=262_144, ge=256)
    JOBS_RETENTION_DAYS: int = Field(default=7, ge=0, le=3650)

    # --- Paginación ---------------------------------------------------------
    PAGE_SIZE_DEFAULT: int = Field(default=20, ge=1)
    PAGE_SIZE_MAX: int = Field(default=100, ge=1, le=1000)
    MAX_OFFSET: int = Field(default=10_000, ge=0)

    # --- Logging --------------------------------------------------------------
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    # None = JSON en producción, texto legible en desarrollo.
    LOG_JSON: bool | None = None

    @field_validator(
        "CORS_ORIGINS",
        "ALLOWED_HOSTS",
        "TRUSTED_PROXIES",
        "JWT_PREVIOUS_SECRET_KEYS",
        mode="before",
    )
    @classmethod
    def _split_commas(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("API_PREFIX")
    @classmethod
    def _normalize_prefix(cls, value: str) -> str:
        value = "/" + value.strip("/")
        return "" if value == "/" else value

    @field_validator(
        "RATE_LIMIT_DEFAULT",
        "RATE_LIMIT_GLOBAL",
        "RATE_LIMIT_LOGIN",
        "RATE_LIMIT_REGISTER",
        "RATE_LIMIT_REFRESH",
    )
    @classmethod
    def _valid_limit(cls, value: str | None) -> str | None:
        if value is not None:
            parse_many(value)  # lanza ValueError si el formato no es válido
        return value

    @field_validator("TRUSTED_PROXIES")
    @classmethod
    def _valid_proxies(cls, value: list[str]) -> list[str]:
        for item in value:
            if item == "*":
                continue  # se rechaza en producción (_check_security)
            try:
                ipaddress.ip_network(item, strict=False)
            except ValueError as exc:
                raise ValueError(f"TRUSTED_PROXIES: {item!r} no es una IP ni un CIDR") from exc
        return value

    @model_validator(mode="after")
    def _check_security(self) -> Settings:
        if self.RATE_LIMIT_REGISTER is None:
            self.RATE_LIMIT_REGISTER = "5/hour" if self.is_production else "50/hour"
        problems: list[str] = []
        symmetric = self.JWT_ALGORITHM in _SYMMETRIC_ALGORITHMS
        secret = self.SECRET_KEY.get_secret_value()

        if self.PASSWORD_MIN_LENGTH > self.PASSWORD_MAX_LENGTH:
            problems.append("PASSWORD_MIN_LENGTH no puede ser mayor que PASSWORD_MAX_LENGTH")

        if symmetric:
            weak = secret.lower() in _INSECURE_SECRETS or len(secret) < 32
            if weak and self.is_production:
                problems.append("SECRET_KEY debe tener al menos 32 caracteres aleatorios")
            elif weak:
                # En desarrollo/testing generamos una clave efímera para no bloquear.
                self.SECRET_KEY = SecretStr(secrets.token_urlsafe(64))
                logger.warning(
                    "SECRET_KEY no configurada o débil: usando una clave efímera "
                    "(los tokens dejarán de valer al reiniciar). Ejecuta `apigen init-env`."
                )
        else:
            if not self.JWT_PRIVATE_KEY_FILE or not self.JWT_PUBLIC_KEY_FILE:
                problems.append(
                    f"{self.JWT_ALGORITHM} requiere JWT_PRIVATE_KEY_FILE y JWT_PUBLIC_KEY_FILE"
                )

        if self.CORS_ALLOW_CREDENTIALS and "*" in self.CORS_ORIGINS:
            problems.append("CORS_ORIGINS='*' no se puede combinar con CORS_ALLOW_CREDENTIALS")

        if self.is_production:
            if self.DEBUG:
                problems.append("DEBUG debe ser false en producción")
            if "*" in self.CORS_ORIGINS:
                problems.append("CORS_ORIGINS no puede ser '*' en producción")
            if "*" in self.ALLOWED_HOSTS:
                problems.append("ALLOWED_HOSTS debe enumerar los dominios reales en producción")
            if self.DATABASE_URL.startswith("sqlite"):
                if self.ALLOW_SQLITE_IN_PRODUCTION:
                    logger.warning("Usando SQLite en producción: recomendado PostgreSQL.")
                else:
                    # Un DATABASE_URL ausente o vacío acabaría aquí en silencio.
                    problems.append(
                        "DATABASE_URL apunta a SQLite: usa PostgreSQL en producción "
                        "(o ALLOW_SQLITE_IN_PRODUCTION=true si es intencionado)"
                    )
            if self.RATE_LIMIT_ENABLED and self.RATE_LIMIT_STORAGE_URI.startswith("memory"):
                logger.warning(
                    "Rate limit en memoria: con varios workers/instancias cada uno "
                    "cuenta por separado. Usa Redis (RATE_LIMIT_STORAGE_URI)."
                )
            problems += _proxy_problems(self.TRUSTED_PROXIES)
            if not self.TRUSTED_PROXIES:
                logger.warning(
                    "TRUSTED_PROXIES vacío: si la API está detrás de un proxy inverso, "
                    "todos los clientes compartirán la IP del proxy (rate limit y bloqueo "
                    "de login globales) y no se enviará HSTS. Ver README, sección Despliegue."
                )
            weak_old = [k for k in self.JWT_PREVIOUS_SECRET_KEYS if len(k) < 32]
            if symmetric and weak_old:
                problems.append("JWT_PREVIOUS_SECRET_KEYS: cada clave necesita 32+ caracteres")

        if problems:
            raise ValueError("Configuración insegura:\n  - " + "\n  - ".join(problems))
        return self

    # --- Propiedades derivadas ----------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == Environment.production

    @property
    def is_testing(self) -> bool:
        return self.ENVIRONMENT == Environment.testing

    @property
    def docs_enabled(self) -> bool:
        return (not self.is_production) if self.DOCS_ENABLED is None else self.DOCS_ENABLED

    @property
    def log_json(self) -> bool:
        return self.is_production if self.LOG_JSON is None else self.LOG_JSON

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.DATABASE_URL.startswith("postgresql")


def _proxy_problems(proxies: list[str]) -> list[str]:
    """SEC-21: la IP del cliente decide rate limits, bloqueo de login y gracia del
    refresh. Confiar en X-Forwarded-For de cualquiera permite falsificarla."""
    problems: list[str] = []
    for item in proxies:
        if item == "*":
            problems.append("TRUSTED_PROXIES='*' permite falsificar la IP del cliente")
            continue
        net = ipaddress.ip_network(item, strict=False)
        # Más amplio que /8 (IPv4) o /32 (IPv6) no puede ser "la red del proxy".
        if net.prefixlen < (8 if net.version == 4 else 32):
            problems.append(f"TRUSTED_PROXIES={item} es demasiado amplio: pon la IP del proxy")
        elif net.prefixlen < (16 if net.version == 4 else 48):
            logger.warning(
                "TRUSTED_PROXIES=%s es muy amplio: confía solo en la IP/subred del proxy.", item
            )
    return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
