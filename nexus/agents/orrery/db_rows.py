"""Small row-access helpers shared by Orrery DB-API call sites."""

from __future__ import annotations

from typing import Any, Mapping


def row_get(row: Any, key: str, index: int) -> Any:
    """Read one value from either a mapping row or a positional row."""

    if isinstance(row, Mapping) or hasattr(row, "keys"):
        return row[key]
    return row[index]
