"""Utilidades para tests (también las usan los tests generados por apigen)."""

import random
import string
import uuid


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def _text(prefix: str, min_length: int = 0, max_length: int = 255) -> str:
    # El identificador aleatorio va delante para sobrevivir al recorte (unicidad).
    value = f"{_uid()}-{prefix}"
    if len(value) < min_length:
        value = value.ljust(min_length, "x")
    return value[:max_length]


def _rand_int(low: int, high: int) -> int:
    return random.randint(low, max(low, high))  # noqa: S311


def _like(example: str) -> str:
    """Valor aleatorio con la misma forma que `example` (a->letra, 9->dígito)."""
    out = []
    for ch in example:
        if ch.isdigit():
            out.append(random.choice(string.digits))  # noqa: S311
        elif ch.islower():
            out.append(random.choice(string.ascii_lowercase))  # noqa: S311
        elif ch.isupper():
            out.append(random.choice(string.ascii_uppercase))  # noqa: S311
        else:
            out.append(ch)
    return "".join(out)
