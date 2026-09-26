"""Tareas usadas solo por los tests (módulo aparte: las de executor=process deben
poder importarse desde el proceso hijo sin arrastrar la app entera)."""

from __future__ import annotations

import asyncio
import time

from app.tasks.registry import TaskContext, TaskError, task


@task("tests.square", executor="process", timeout=30)
def square(payload: dict) -> dict:
    return {"value": payload["n"] * payload["n"]}


@task("tests.blocking", executor="thread", timeout=30)
def blocking(payload: dict) -> dict:
    time.sleep(0.01)
    return {"slept": True}


@task("tests.flaky", max_attempts=2)
async def flaky(ctx: TaskContext, payload: dict) -> dict:
    raise RuntimeError("database password is hunter2")  # nunca debe llegar al cliente


@task("tests.business_error", max_attempts=3)
async def business_error(ctx: TaskContext, payload: dict) -> dict:
    raise TaskError("The report has no rows")


@task("tests.slow", timeout=0.05, max_attempts=1)
async def slow(ctx: TaskContext, payload: dict) -> dict:
    await asyncio.sleep(1)
    return {}
