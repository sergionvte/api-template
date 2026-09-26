"""Registro de tareas en segundo plano.

    from app.tasks.registry import TaskContext, task

    @task("product.export_pdf", timeout=600)
    async def export_pdf(ctx: TaskContext, payload: dict) -> dict:
        async with ctx.session() as session:
            ...
        return {"url": "..."}

Tipos de ejecución (`executor`):
- ``async``   (por defecto) corrutina en el event loop del worker. Para E/S:
  llamadas HTTP, BD, envío de emails.
- ``thread``  función síncrona en un hilo. Para librerías bloqueantes.
- ``process`` función síncrona en un proceso aparte. Para CPU intensiva
  (PDFs, imágenes, cálculos): no bloquea al resto de tareas por el GIL. Debe
  estar definida a nivel de módulo y recibir/devolver datos serializables.

Las tareas síncronas reciben solo ``payload``; las async reciben ``ctx`` y
``payload``. Todas devuelven un dict/list serializable a JSON (o None).
"""

from __future__ import annotations

import inspect
import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel

Executor = Literal["async", "thread", "process"]
_NAME = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")


class TaskError(Exception):
    """Error de negocio cuyo mensaje SÍ se puede mostrar al cliente.

    Cualquier otra excepción se guarda como "Task failed" (la traza va al log).
    Por defecto un TaskError no se reintenta; usa ``retry=True`` si procede.
    """

    def __init__(self, message: str, *, retry: bool = False) -> None:
        super().__init__(message)
        self.retry = retry


@dataclass(frozen=True, slots=True)
class TaskDef:
    name: str
    func: Callable[..., Any]
    executor: Executor
    max_attempts: int
    timeout: float
    payload_model: type[BaseModel] | None = None
    description: str = ""


@dataclass(slots=True)
class TaskContext:
    """Contexto que reciben las tareas async."""

    job_id: uuid.UUID
    owner_id: uuid.UUID | None
    attempt: int
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("app.tasks"))

    def session(self):
        """Sesión de BD propia de la tarea: `async with ctx.session() as session:`."""
        from app.db.session import SessionFactory

        return SessionFactory()


REGISTRY: dict[str, TaskDef] = {}


def task(
    name: str,
    *,
    executor: Executor = "async",
    max_attempts: int = 3,
    timeout: float = 300,
    payload_model: type[BaseModel] | None = None,
    description: str = "",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Registra una función como tarea en segundo plano."""
    if not _NAME.match(name):
        raise ValueError(f"nombre de tarea inválido: {name!r} (usa p. ej. 'product.export_pdf')")
    if not 1 <= max_attempts <= 20 or not 0 < timeout <= 86_400:
        raise ValueError("max_attempts debe estar entre 1 y 20 y timeout entre 0 y 86400 s")

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        is_async = inspect.iscoroutinefunction(func)
        if executor == "async" and not is_async:
            raise TypeError(f"{name}: executor='async' requiere una función async")
        if executor != "async" and is_async:
            raise TypeError(f"{name}: executor='{executor}' requiere una función síncrona")
        existing = REGISTRY.get(name)
        if existing and existing.func is not func:
            raise ValueError(f"la tarea {name!r} ya está registrada en {existing.func.__module__}")
        REGISTRY[name] = TaskDef(
            name=name,
            func=func,
            executor=executor,
            max_attempts=max_attempts,
            timeout=float(timeout),
            payload_model=payload_model,
            description=description or (func.__doc__ or "").strip().split("\n")[0],
        )
        return func

    return decorator


def get_task(name: str) -> TaskDef:
    try:
        return REGISTRY[name]
    except KeyError:
        hint = "¿falta importarla en app/tasks/__init__.py?"
        raise LookupError(f"tarea no registrada: {name!r} ({hint})") from None
