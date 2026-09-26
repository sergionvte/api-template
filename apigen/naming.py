"""Utilidades de nombres (singular/plural, snake_case/PascalCase)."""

import re

_IRREGULAR = {"person": "people", "child": "children", "man": "men", "woman": "women"}


def pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def snake(name: str) -> str:
    name = re.sub(r"[\s\-]+", "_", name.strip())
    name = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    return name.lower()


def pluralize(name: str) -> str:
    head, _, last = name.rpartition("_")
    prefix = f"{head}_" if head else ""
    if last in _IRREGULAR:
        return prefix + _IRREGULAR[last]
    if re.search(r"[^aeiou]y$", last):
        return prefix + last[:-1] + "ies"
    if re.search(r"(s|x|z|ch|sh)$", last):
        return prefix + last + "es"
    return prefix + last + "s"
