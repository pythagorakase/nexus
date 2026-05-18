"""Tests for prompt-facing Orrery tag-library rendering."""

from __future__ import annotations

from typing import Any, Optional

import pytest

import nexus.agents.orrery.tag_library as tag_library


def test_format_tag_library_groups_live_tags_by_entity_kind(monkeypatch) -> None:
    """Prompt renderer exposes the DB-backed vocabulary without hand examples."""

    rows = [
        {
            "entity_kind": "character",
            "category": "state",
            "category_description": "Character state.",
            "prompt_order": 10,
            "tag": "wounded",
            "is_ephemeral": True,
            "description": "Character has an acute wound.",
        },
        {
            "entity_kind": "place",
            "category": "place_affordance",
            "category_description": "Functional place affordance.",
            "prompt_order": 10,
            "tag": "safe_house",
            "is_ephemeral": False,
            "description": "Place can shelter people from danger.",
        },
    ]
    monkeypatch.setattr(tag_library, "_connect", lambda _dbname: _Conn(rows))

    rendered = tag_library.format_tag_library_for_prompt("save_05")

    assert "Current Orrery Tag Library" in rendered
    assert "Prefer exact registered tags when they fit" in rendered
    assert "add new tags when the existing library does not cover" in rendered
    assert "### Character Tags" in rendered
    assert "`wounded` (ephemeral): Character has an acute wound." in rendered
    assert "### Place Tags" in rendered
    assert "`safe_house`: Place can shelter people from danger." in rendered


def test_format_tag_library_rejects_unknown_entity_kind() -> None:
    with pytest.raises(ValueError, match="Unknown Orrery entity kind"):
        tag_library.format_tag_library_for_prompt(
            "save_05", entity_kinds=["character", "monster"]
        )


class _Conn:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def __enter__(self) -> "_Conn":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def cursor(self) -> "_Cursor":
        return _Cursor(self.rows)

    def close(self) -> None:
        return None


class _Cursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.params: Optional[tuple[object, ...]] = None

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, _sql: str, params: tuple[object, ...]) -> None:
        self.params = params

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows
