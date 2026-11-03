"""Especificación declarativa de un recurso (lo que va en resources/*.yaml).

Todo identificador que acaba convertido en código Python se valida con
expresiones regulares estrictas y los literales se emiten con `repr()`, de modo
que un YAML malicioso no puede inyectar código en los ficheros generados.
"""

from __future__ import annotations

import difflib
import keyword
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from limits import parse_many
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from apigen.naming import pascal, pluralize

IDENT = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
RESOURCE_NAME = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
VERSION_NAME = re.compile(r"^v[1-9][0-9]{0,2}$")
ENUM_VALUE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")

RESERVED_FIELDS = {
    "id",
    "created_at",
    "updated_at",
    "deleted_at",
    "owner_id",
    "owner",
    "metadata",
    "registry",
    "q",
    "limit",
    "offset",
    "order_by",
    # Nombres de parámetros de los endpoints generados: un filtro con este nombre
    # produciría "duplicate argument" en el router.
    "session",
    "principal",
    "page",
    "request",
    "response",
}
RESERVED_RESOURCES = {
    "user", "users", "auth", "health", "refresh_token", "base", "common", "me",
    # Flujos de cuenta por correo (endpoints/account.py, models/account_token.py, email_log).
    "account", "accounts", "account_token", "account_tokens", "email_log", "email_logs",
}  # fmt: skip

FieldType = Literal[
    "str",
    "text",
    "int",
    "float",
    "decimal",
    "bool",
    "date",
    "datetime",
    "uuid",
    "email",
    "json",
    "enum",
    "fk",
]
FILTERABLE = {"str", "int", "bool", "date", "uuid", "email", "enum", "fk", "decimal"}
SEARCHABLE = {"str", "text", "email"}
ORDERABLE = {"str", "int", "float", "decimal", "date", "datetime", "email", "enum", "bool"}
# Tipos que se cifran en reposo cuando el campo es sensitive (app/db/crypto.py).
ENCRYPTED_TYPES = {"str", "text", "email"}
Level = Literal["public", "user", "owner", "admin"]
ACTIONS = ("list", "read", "create", "update", "delete")
INT64_MIN, INT64_MAX = -(2**63), 2**63 - 1
INT32_MIN, INT32_MAX = -(2**31), 2**31 - 1
# Tamaño máximo por defecto (bytes serializados) de un campo json.
JSON_DEFAULT_MAX_BYTES = 16_384


_LEVEL_ORDER = {"public": 0, "user": 1, "owner": 2, "admin": 3}


class SpecError(ValueError):
    pass


class FieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: FieldType
    nullable: bool = False
    default: Any = None
    unique: bool = False
    index: bool = False
    immutable: bool = False  # no se puede cambiar en PATCH
    write_only: bool = False  # se acepta pero nunca se devuelve
    # Clasificación (ISO 27701 6.5.2, SOC 2 C1.1). pii: dato personal (nombre,
    # teléfono...). sensitive: categoría especial (salud, ideología, biometría,
    # menores...) o confidencial; implica pii y endurece los permisos del recurso.
    pii: bool = False
    sensitive: bool = False
    description: str | None = Field(default=None, max_length=300)
    example: Any = None
    # str / text
    min_length: int | None = Field(default=None, ge=0)
    max_length: int | None = Field(default=None, ge=1, le=1_000_000)
    pattern: str | None = Field(default=None, max_length=300)
    # numéricos
    ge: float | None = None
    le: float | None = None
    gt: float | None = None
    lt: float | None = None
    max_digits: int | None = Field(default=None, ge=1, le=38)
    decimal_places: int | None = Field(default=None, ge=0, le=18)
    # enum
    choices: list[str] | None = None
    # fk
    to: str | None = None
    on_delete: Literal["CASCADE", "SET NULL", "RESTRICT"] | None = None

    @field_validator("on_delete", mode="before")
    @classmethod
    def _on_delete(cls, value: Any) -> Any:
        # UX-46: `cascade`, `set null` o `set_null` valen igual que en mayúsculas.
        if isinstance(value, str):
            return " ".join(value.replace("_", " ").split()).upper()
        return value

    @field_validator("choices")
    @classmethod
    def _choices(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            if not value or len(set(value)) != len(value):
                raise ValueError("choices debe ser una lista no vacía y sin duplicados")
            for item in value:
                if not ENUM_VALUE.match(str(item)):
                    raise ValueError(f"valor de enum no válido: {item!r}")
        return value

    @model_validator(mode="after")
    def _check(self) -> FieldSpec:
        t = self.type
        if t in {"str", "email"} and self.max_length is None:
            self.max_length = 255 if t == "str" else 320
        if t == "text" and self.max_length is None:
            self.max_length = 10_000
        if t == "json" and self.max_length is None:
            self.max_length = JSON_DEFAULT_MAX_BYTES
        if t == "decimal":
            self.max_digits = self.max_digits or 12
            self.decimal_places = 2 if self.decimal_places is None else self.decimal_places
            if self.decimal_places >= self.max_digits:
                raise ValueError("decimal_places debe ser menor que max_digits")
        if t == "enum":
            if not self.choices:
                raise ValueError("un campo enum necesita 'choices'")
            self.max_length = max(len(c) for c in self.choices)
        elif self.choices:
            raise ValueError("'choices' solo aplica a campos enum")
        if t == "fk":
            if not self.to or not RESOURCE_NAME.match(self.to):
                raise ValueError("un campo fk necesita 'to: <recurso>'")
            if self.on_delete is None:
                self.on_delete = "SET NULL" if self.nullable else "RESTRICT"
            if self.on_delete == "SET NULL" and not self.nullable:
                raise ValueError("on_delete SET NULL requiere nullable: true")
            self.index = True
        elif self.to or self.on_delete:
            raise ValueError("'to'/'on_delete' solo aplican a campos fk")
        if t not in {"str", "text", "email"} and (self.min_length or self.pattern):
            raise ValueError("min_length/pattern solo aplican a textos")
        if t not in {"int", "float", "decimal"} and any(
            v is not None for v in (self.ge, self.le, self.gt, self.lt)
        ):
            raise ValueError("ge/le/gt/lt solo aplican a números")
        if t in {"text", "json"} and (self.unique or self.index):
            raise ValueError(f"un campo {t} no puede ser unique/index")
        if self.pattern:
            try:
                re.compile(self.pattern)
                # Pydantic usa el motor de regex de Rust (sin look-around ni
                # backreferences): si no lo acepta, el esquema generado no importaría.
                TypeAdapter(Annotated[str, StringConstraints(pattern=self.pattern)])
            except re.error as exc:
                raise ValueError(f"pattern inválido: {exc}") from exc
            except Exception as exc:  # noqa: BLE001
                raise ValueError(
                    "pattern no soportado por pydantic (sin look-around ni backreferences)"
                ) from exc
            if self.example is None:
                raise ValueError("un campo con 'pattern' necesita 'example' (para los tests)")
        if self.unique and self.type == "bool":
            raise ValueError("un bool no puede ser unique")
        if self.sensitive:
            self.pii = True
            if self.unique or (self.index and self.type != "fk"):
                # El 409 de unicidad revelaría que otra persona tiene ese mismo valor; y un
                # índice sobre un valor cifrado (nonce aleatorio) no sirve de nada.
                raise ValueError("un campo sensitive no puede ser unique ni index")
        if self.default is not None:
            self.default = coerce_value(self, self.default, "default")
        if self.example is not None:
            self.example = coerce_value(self, self.example, "example")
        return self

    @property
    def required(self) -> bool:
        return not self.nullable and self.default is None

    def int_bounds(self) -> tuple[int, int]:
        """Rango efectivo de un campo int, acotado siempre a 64 bits (SEC-07)."""
        low = self.ge if self.ge is not None else (self.gt + 1 if self.gt is not None else None)
        high = self.le if self.le is not None else (self.lt - 1 if self.lt is not None else None)
        low_i = INT64_MIN if low is None else max(int(low), INT64_MIN)
        high_i = INT64_MAX if high is None else min(int(high), INT64_MAX)
        return low_i, high_i

    def fits_int32(self) -> bool:
        low, high = self.int_bounds()
        return INT32_MIN <= low and high <= INT32_MAX


def coerce_value(field: FieldSpec, value: Any, what: str) -> Any:
    """Valida que un default/example tenga el tipo correcto y lo normaliza."""
    t = field.type
    try:
        if t in {"str", "text", "email", "enum"}:
            if not isinstance(value, str):
                raise TypeError
            if field.max_length and len(value) > field.max_length:
                raise ValueError(f"{what} supera max_length")
            if t == "enum" and value not in (field.choices or []):
                raise ValueError(f"{what} no está en choices")
            return value
        if t == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError
            return value
        if t == "float":
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise TypeError
            return float(value)
        if t == "decimal":
            return str(Decimal(str(value)))
        if t == "bool":
            if not isinstance(value, bool):
                raise TypeError
            return value
        if t == "date":
            return (
                value.isoformat()
                if isinstance(value, date)
                else date.fromisoformat(value).isoformat()
            )
        if t == "datetime":
            return (
                value.isoformat()
                if isinstance(value, datetime)
                else datetime.fromisoformat(value).isoformat()
            )
        if t == "json":
            if not isinstance(value, dict | list):
                raise TypeError
            return value
    except (TypeError, ValueError, InvalidOperation) as exc:
        detail = f": {exc}" if str(exc) else ""
        raise ValueError(f"{what} {value!r} no es válido para el tipo {t}{detail}") from exc
    raise ValueError(f"los campos {t} no admiten {what}")


class Permissions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    list: Level | None = None
    read: Level | None = None
    create: Level | None = None
    update: Level | None = None
    delete: Level | None = None


class RateLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    read: str | None = None
    write: str | None = None

    @field_validator("read", "write")
    @classmethod
    def _valid(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                parse_many(value)
            except ValueError as exc:
                raise ValueError(f"límite inválido {value!r} (ej: '100/minute')") from exc
        return value


# Nombres que chocarían con lo que ya definen los módulos de hooks/tareas generados
# o con las operaciones CRUD del router (SEC-31: una acción `read` redefinía el
# permiso de `GET /{id}`; `get`/`create`... repetirían el nombre de su función).
RESERVED_ACTIONS = {
    "task", "uuid", "annotations", "before_create", "after_create", "before_update",
    "after_update", "before_delete", "after_delete", *ACTIONS, "get",
}  # fmt: skip
# Atributos de pydantic.BaseModel: un campo de entrada con ese nombre rompe el esquema
# (`model_config`, `model_dump`...) o lo ensombrece (`json`, `copy`...). SEC-38.
_BASEMODEL_ATTRS = {name for name in dir(BaseModel) if not name.startswith("_")}
ACTION_FIELD_TYPES = {
    "str", "text", "int", "float", "decimal", "bool", "date", "datetime", "uuid", "email", "json",
}  # fmt: skip


class ActionSpec(BaseModel):
    """Endpoint extra de un recurso: `POST /<plural>/{item_id}/<name>` (scope=item)
    o `POST /<plural>/<name>` (scope=collection).

    Con `background: true` la API solo encola el trabajo (responde 202 con el
    job_id) y el proceso pesado lo ejecuta `apigen worker`, sin frenar la API.
    Sin `background`, llama a la función homónima de `app/hooks/<recurso>.py`.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    scope: Literal["item", "collection"] = "item"
    background: bool = False
    permission: Level | None = None  # por defecto: la de update (item) o create (collection)
    rate_limit: str | None = None
    description: str | None = Field(default=None, max_length=300)
    fields: dict[str, FieldSpec] = {}  # cuerpo de entrada opcional
    executor: Literal["async", "thread", "process"] = "async"
    timeout: int = Field(default=300, ge=1, le=86_400)
    max_attempts: int = Field(default=3, ge=1, le=20)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if (
            not IDENT.match(value)
            or keyword.iskeyword(value)
            or value.startswith("model_")
            or value in RESERVED_ACTIONS
        ):
            raise ValueError(f"nombre de acción no permitido: {value!r} (snake_case, no reservado)")
        return value

    @field_validator("rate_limit")
    @classmethod
    def _rate(cls, value: str | None) -> str | None:
        return RateLimits._valid(value)

    @model_validator(mode="after")
    def _check(self) -> ActionSpec:
        for fname, f in self.fields.items():
            if (
                not IDENT.match(fname)
                or keyword.iskeyword(fname)
                or fname == "item_id"
                or fname.startswith("model_")
                or fname in _BASEMODEL_ATTRS
            ):
                raise ValueError(f"acción {self.name}: campo no permitido {fname!r}")
            if f.type not in ACTION_FIELD_TYPES:
                raise ValueError(
                    f"acción {self.name}: el tipo {f.type} no se admite en la entrada "
                    "(usa uuid y valida la referencia en el hook o la tarea)"
                )
        if self.background and self.permission == "public":
            raise ValueError(
                f"acción {self.name}: una acción en segundo plano no puede ser pública "
                "(cualquiera podría llenar la cola)"
            )
        return self


class ResourceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    plural: str | None = None
    description: str | None = Field(default=None, max_length=300)
    # Finalidad del tratamiento (ISO 27701 7.2.1): va al inventario de datos
    # (`apigen privacy inventory`). Recomendable si hay campos pii.
    purpose: str | None = Field(default=None, max_length=300)
    owned: bool = False
    soft_delete: bool = False
    # Recurso owned cuyas filas pueden leer otros usuarios A PROPÓSITO (p. ej. un
    # blog: list/read públicos). Obligatorio si `read` es más permisivo que `list`
    # (si no, sería un BOLA por ID) y silencia el aviso de lectura compartida.
    shared_read: bool = False
    versions: list[str] = ["v1"]
    permissions: Permissions = Permissions()
    rate_limits: RateLimits = RateLimits()
    fields: dict[str, FieldSpec]
    filters: list[str] = []
    search: list[str] = []
    ordering: list[str] = []
    actions: list[ActionSpec] = []

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not RESOURCE_NAME.match(value) or keyword.iskeyword(value):
            raise ValueError("el nombre debe ser snake_case en singular (p. ej. 'blog_post')")
        if value in RESERVED_RESOURCES:
            raise ValueError(f"'{value}' es un nombre reservado")
        return value

    @field_validator("versions")
    @classmethod
    def _versions(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("indica al menos una versión")
        for v in value:
            if not VERSION_NAME.match(v):
                raise ValueError(f"versión inválida {v!r} (formato v1, v2...)")
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def _check(self) -> ResourceSpec:
        self.plural = self.plural or pluralize(self.name)
        if not RESOURCE_NAME.match(self.plural) or self.plural in RESERVED_RESOURCES:
            raise ValueError(f"plural inválido: {self.plural!r}")
        if self.plural == self.name:
            raise ValueError("el plural debe ser distinto del nombre (usa 'plural:')")
        if not self.fields:
            raise ValueError("el recurso necesita al menos un campo")
        for fname in self.fields:
            if (
                not IDENT.match(fname)
                or keyword.iskeyword(fname)
                or fname in RESERVED_FIELDS
                or fname.startswith("model_")
            ):
                raise ValueError(f"nombre de campo no permitido: {fname!r}")

        # Permisos por defecto seguros.
        p = self.permissions
        default_read = "owner" if self.owned else "user"
        default_write = "owner" if self.owned else "admin"
        p.list = p.list or default_read
        p.read = p.read or default_read
        p.create = p.create or ("user" if self.owned else "admin")
        p.update = p.update or default_write
        p.delete = p.delete or default_write
        for action in ACTIONS:
            level = getattr(p, action)
            if level == "owner" and not self.owned:
                raise ValueError(
                    f"permissions.{action}=owner requiere owned: true (--owned en la CLI)"
                )
        if self.owned and p.create in {"public", "owner"}:
            raise ValueError("en un recurso owned, create debe ser 'user' o 'admin'")
        if p.create == "owner":
            raise ValueError("create no puede ser 'owner'")
        if p.update == "public" or p.delete == "public":
            raise ValueError("update/delete públicos no están permitidos")
        if self.owned and "user" in {p.update, p.delete}:
            raise ValueError(
                "en un recurso owned, update/delete='user' permitiría a cualquier usuario "
                "modificar filas ajenas: usa 'owner' o 'admin'"
            )
        if self.owned and _LEVEL_ORDER[p.read] < _LEVEL_ORDER[p.list] and not self.shared_read:
            raise ValueError(
                f"en un recurso owned, read={p.read} con list={p.list} deja leer por ID filas "
                "ajenas que el listado oculta (BOLA). Si es intencionado, añade "
                "`shared_read: true` (--shared-read en la CLI)"
            )
        if self.shared_read and not self.owned:
            raise ValueError("shared_read solo aplica a recursos owned")

        def check_list(attr: str, allowed: set[str], extra: set[str] = frozenset()) -> None:
            for fname in getattr(self, attr):
                if fname in extra:
                    continue
                f = self.fields.get(fname)
                if f is None:
                    close = difflib.get_close_matches(fname, list(self.fields), n=1)
                    hint = f"; ¿quisiste decir {close[0]!r}?" if close else ""
                    raise ValueError(f"{attr}: el campo {fname!r} no existe{hint}")
                if f.type not in allowed:
                    raise ValueError(f"{attr}: el campo {fname!r} ({f.type}) no es válido aquí")
                if f.write_only:
                    raise ValueError(f"{attr}: {fname!r} es write_only")

        check_list("filters", FILTERABLE)
        check_list("search", SEARCHABLE)
        check_list("ordering", ORDERABLE, {"created_at", "updated_at"})

        # Privacidad desde el diseño (ISO 27701 7.4.1/7.4.2): un dato sensible solo lo
        # ve su dueño o un admin, y no se puede filtrar, buscar ni ordenar por él (un
        # filtro o una ordenación permiten deducir el valor aunque no se devuelva).
        sensitive = sorted(n for n, f in self.fields.items() if f.sensitive)
        if sensitive:
            open_levels = {a: getattr(p, a) for a in ("list", "read")}
            too_open = {a: lv for a, lv in open_levels.items() if lv not in {"owner", "admin"}}
            if too_open:
                levels = ", ".join(f"{a}={lv}" for a, lv in too_open.items())
                raise ValueError(
                    f"campos sensitive ({', '.join(sensitive)}) con {levels}: solo el dueño "
                    "(owned + owner) o un admin pueden leerlos"
                )
            for attr in ("filters", "search", "ordering"):
                used = sorted(set(getattr(self, attr)) & set(sensitive))
                if used:
                    raise ValueError(f"{attr}: {', '.join(used)} es sensitive (no se admite)")

        seen: set[str] = set()
        for action in self.actions:
            if action.name in seen:
                raise ValueError(f"acción duplicada: {action.name!r}")
            seen.add(action.name)
            if action.permission is None:
                action.permission = p.update if action.scope == "item" else p.create
            if action.permission == "owner" and not self.owned:
                raise ValueError(f"acción {action.name}: permission=owner requiere owned: true")
            if action.permission == "owner" and action.scope == "collection":
                raise ValueError(
                    f"acción {action.name}: una acción de colección no tiene dueño (usa 'user')"
                )
            if action.background and action.permission == "public":
                raise ValueError(f"acción {action.name}: en segundo plano no puede ser pública")
            # SEC-32: en un recurso owned, una acción de item abierta a cualquier usuario
            # cargaría filas ajenas (BOLA), igual que update/delete='user'. Solo se admite
            # si las filas son legibles por todos a propósito (shared_read + read abierto).
            if (
                self.owned
                and action.scope == "item"
                and action.permission in {"public", "user"}
                and not (
                    self.shared_read and _LEVEL_ORDER[p.read] <= _LEVEL_ORDER[action.permission]
                )
            ):
                raise ValueError(
                    f"acción {action.name}: en un recurso owned, permission={action.permission} "
                    "dejaría actuar sobre filas ajenas (BOLA). Usa 'owner' (el dueño; admins: "
                    "cualquiera) o 'admin'. Solo si todos pueden ver todas las filas, añade "
                    f"`shared_read: true` con read={action.permission}"
                )
        return self

    def warnings(self) -> list[str]:
        """Combinaciones válidas pero que merecen confirmación (SEC-08)."""
        out: list[str] = []
        p = self.permissions
        order = _LEVEL_ORDER
        if self.owned and not self.shared_read:
            for action in ("list", "read"):
                level = getattr(p, action)
                if level in {"public", "user"}:
                    who = "cualquiera" if level == "public" else "cualquier usuario"
                    out.append(
                        f"{self.name}: {action}={level} en un recurso owned -> {who} ve las "
                        "filas de todos los usuarios (incluido owner_id). Si es lo que "
                        "quieres (p. ej. un blog), añade `shared_read: true` para silenciarlo"
                    )
        if not self.owned and order[p.read] < order[p.list]:  # type: ignore[index]
            out.append(
                f"{self.name}: read={p.read} es más permisivo que list={p.list}: quien no ve "
                "una fila en el listado puede leerla por su ID"
            )
        for action in self.actions:
            if action.scope == "item" and self.owned and action.permission in {"public", "user"}:
                out.append(
                    f"{self.name}.{action.name}: permission={action.permission} con shared_read -> "
                    "cualquier usuario ejecuta la acción sobre filas de otros"
                )
            if action.background and not action.rate_limit and action.permission != "admin":
                out.append(
                    f"{self.name}.{action.name}: acción en segundo plano sin rate_limit (solo "
                    "aplica el límite por defecto); añade p. ej. `rate_limit: 10/minute`"
                )
            inherited = "permission" not in action.model_fields_set
            if action.scope == "collection" and action.permission == "public" and inherited:
                out.append(
                    f"{self.name}.{action.name}: acción pública heredada de create=public "
                    "(cualquiera, sin login); pon `permission:` explícito para confirmarlo"
                )
        pii = sorted(n for n, f in self.fields.items() if f.pii)
        if pii and "public" in {p.list, p.read}:
            out.append(
                f"{self.name}: datos personales ({', '.join(pii)}) legibles sin login "
                "(list/read=public); confirma que es su finalidad y que hay base legal"
            )
        if pii and not self.purpose:
            out.append(
                f"{self.name}: tiene campos pii sin `purpose:` (finalidad del tratamiento, "
                "va al inventario de `apigen privacy inventory`)"
            )
        for fname, f in self.fields.items():
            if f.type == "fk" and f.to == "user" and f.on_delete == "RESTRICT":
                out.append(
                    f"{self.name}.{fname}: FK a user con on_delete=RESTRICT -> el usuario no "
                    "podrá borrar su cuenta (DELETE /users/me da 409) mientras tenga filas aquí. "
                    "Para el derecho de supresión usa CASCADE o nullable + SET NULL"
                )
            if f.type == "enum" and len(f.choices or []) == 1:
                out.append(
                    f"{self.name}.{fname}: el enum solo tiene una opción ({f.choices[0]!r}); "
                    "¿olvidaste las comillas? En la shell `|` es una tubería: usa "
                    "'estado:enum=a|b' o separa con comas (enum=a,b)"
                )
        return out

    # --- nombres derivados --------------------------------------------------
    @property
    def class_name(self) -> str:
        return pascal(self.name)

    @property
    def table(self) -> str:
        return self.plural  # type: ignore[return-value]


def load_specs(path: Path) -> list[ResourceSpec]:
    """Carga un fichero YAML (un recurso o `resources: [...]`) o un directorio."""
    return [spec for spec, _ in load_specs_with_sources(path)]


def load_specs_with_sources(path: Path) -> list[tuple[ResourceSpec, Path]]:
    """Como `load_specs`, con el fichero de cada recurso.

    Un recurso definido dos veces (en dos ficheros o dos veces en el mismo) es un
    error: antes ganaba en silencio el último por orden alfabético (UX-50)."""
    files = sorted(path.glob("*.y*ml")) if path.is_dir() else [path]
    specs: list[tuple[ResourceSpec, Path]] = []
    seen: dict[str, Path] = {}
    for file in files:
        try:
            data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            where = f"{file}:{mark.line + 1}:{mark.column + 1}" if mark else str(file)
            problem = getattr(exc, "problem", None) or str(exc)
            raise SpecError(f"{where}: YAML no válido: {problem}") from None
        items = data.get("resources", [data]) if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise SpecError(f"{file}: se esperaba un recurso o 'resources: [...]'")
        for item in items:
            try:
                spec = ResourceSpec.model_validate(item)
            except ValidationError as exc:
                raise SpecError(f"{file}:\n{format_errors(exc)}") from None
            if spec.name in seen:
                where = (
                    f"dos veces en {file.name}"
                    if seen[spec.name] == file
                    else f"en {seen[spec.name].name} y en {file.name}"
                )
                raise SpecError(
                    f"el recurso '{spec.name}' está definido {where}: deja una sola "
                    "definición (borra o renombra la otra)"
                )
            seen[spec.name] = file
            specs.append((spec, file))
    return specs


_CLI_ALIASES = {
    "max_length": "max",
    "min_length": "min",
    "decimal_places": "places",
    "max_digits": "digits",
}


def _translate(err: dict[str, Any]) -> str:
    """Mensajes de pydantic más comunes, en español y con sugerencias."""
    kind, msg = err.get("type", ""), str(err.get("msg", ""))
    value = err.get("input")
    if kind == "literal_error":
        expected = re.findall(r"'([^']+)'", msg)
        hint = ""
        if isinstance(value, str) and expected:
            close = difflib.get_close_matches(value, expected, n=1, cutoff=0.5)
            if close:
                hint = f"; ¿quisiste decir {close[0]!r}?"
        return f"valor {value!r} no válido (opciones: {', '.join(expected)}){hint}"
    if kind == "extra_forbidden":
        return "opción desconocida"
    if kind in {"int_parsing", "int_type", "int_from_float"}:
        return f"debe ser un número entero (recibido {value!r})"
    if kind in {"float_parsing", "float_type"}:
        return f"debe ser un número (recibido {value!r})"
    if kind in {"bool_parsing", "bool_type"}:
        return f"debe ser true o false (recibido {value!r})"
    if kind == "missing":
        return "falta este dato"
    if kind in {"string_type"}:
        return "debe ser un texto"
    return msg.removeprefix("Value error, ")


def format_errors(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        parts = [_CLI_ALIASES.get(str(p), str(p)) for p in err["loc"]]
        loc = ".".join(parts)
        text = _translate(err)
        lines.append(f"  - {loc}: {text}" if loc else f"  - {text}")
    return "\n".join(lines)


def validate_references(specs: list[ResourceSpec]) -> None:
    names = {s.name for s in specs}
    for spec in specs:
        for fname, f in spec.fields.items():
            if f.type == "fk" and f.to != "user" and f.to not in names:
                raise SpecError(
                    f"{spec.name}.{fname}: referencia a '{f.to}', que no existe en resources/"
                )


def spec_to_yaml(spec: ResourceSpec) -> str:
    return yaml.safe_dump(spec_to_data(spec), sort_keys=False, allow_unicode=True)


def spec_to_data(spec: ResourceSpec) -> dict[str, Any]:
    """Spec como dict para YAML, sin los valores por defecto que solo hacen ruido."""
    data = spec.model_dump(exclude_none=True, exclude_defaults=False)
    for f in data["fields"].values():
        for key in ("nullable", "unique", "index", "immutable", "write_only", "pii", "sensitive"):
            if f.get(key) is False:
                f.pop(key)
        if f.get("sensitive"):
            f.pop("pii", None)  # sensitive ya implica pii
    for key in ("filters", "search", "ordering"):
        if not data.get(key):
            data.pop(key, None)
    if not data["rate_limits"]:
        data.pop("rate_limits")
    if not data.get("shared_read"):
        data.pop("shared_read", None)
    if not data.get("actions"):
        data.pop("actions", None)
    else:
        defaults = ActionSpec(name="x").model_dump()
        for action in data["actions"]:
            for key in ("scope", "background", "executor", "timeout", "max_attempts", "fields"):
                if action.get(key) == defaults[key]:
                    action.pop(key)
            # En la entrada de una acción no aplican unique/index/immutable/write_only (UX-66).
            for f in action.get("fields", {}).values():
                for key in ("unique", "index", "immutable", "write_only", "on_delete"):
                    f.pop(key, None)
                for key in ("pii", "sensitive"):
                    if f.get(key) is False:
                        f.pop(key)
                if f.get("nullable") is False:
                    f.pop("nullable")
    return data


def parse_field_option(raw: str) -> tuple[str, FieldSpec]:
    """Mini-DSL de la CLI: `nombre:tipo[:opción...]`.

    Ejemplos: `title:str:max=200:unique`, `price:decimal:ge=0`,
    `status:enum=draft,published:default=draft`, `author_id:fk=author:nullable`.
    """
    parts = raw.split(":")
    if len(parts) < 2:
        raise SpecError(f"campo {raw!r}: formato nombre:tipo[:opciones]")
    name, type_part, *opts = parts
    data: dict[str, Any] = {}
    ftype, _, arg = type_part.partition("=")
    data["type"] = ftype
    if ftype == "fk":
        data["to"] = arg
    elif ftype == "enum":
        # `|` (como en YAML) o `,` (no hay que entrecomillarla en la shell).
        data["choices"] = [c for c in re.split(r"[|,]", arg) if c]
    aliases = {
        "max": "max_length",
        "min": "min_length",
        "places": "decimal_places",
        "digits": "max_digits",
    }
    flags = {"nullable", "unique", "index", "immutable", "write_only", "pii", "sensitive"}
    valued = {
        "max", "min", "ge", "le", "gt", "lt", "digits", "places", "default", "example",
        "pattern", "on_delete", "description", *aliases.values(),
    }  # fmt: skip
    for opt in opts:
        key, eq, value = opt.partition("=")
        key = aliases.get(key, key)
        known = valued if eq else flags
        if key not in known and not (eq and key in FieldSpec.model_fields):
            close = difflib.get_close_matches(key, sorted(flags | valued), n=1)
            hint = f"; ¿quisiste decir {close[0]!r}?" if close else ""
            raise SpecError(f"campo {name!r}: opción desconocida {key!r}{hint}")
        if not eq:
            data[key] = True
            continue
        if key in {"pattern", "on_delete", "description"}:
            data[key] = value
        elif key in {"default", "example"} and ftype in {"str", "text", "email", "enum", "decimal"}:
            data[key] = value
        else:
            data[key] = yaml.safe_load(value)
    try:
        return name, FieldSpec.model_validate(data)
    except ValidationError as exc:
        raise SpecError(f"campo {name!r}:\n{format_errors(exc)}") from None
