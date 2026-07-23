"""Tests for prompt-facing Orrery tag-library rendering."""

from __future__ import annotations

import os
import re
from typing import Any, Optional

import pytest
import tiktoken

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
    assert "Do not invent new tag names at runtime" in rendered
    assert "### Character Tags" in rendered
    assert "`wounded` (ephemeral): Character has an acute wound." in rendered
    assert "### Place Tags" in rendered
    assert "`safe_house`: Place can shelter people from danger." in rendered


def test_format_tag_library_rejects_unknown_entity_kind() -> None:
    with pytest.raises(ValueError, match="Unknown Orrery entity kind"):
        tag_library.format_tag_library_for_prompt(
            "save_05", entity_kinds=["character", "monster"]
        )


def test_read_pair_tag_library_uses_shared_connection(monkeypatch) -> None:
    rows = [{"tag": "hiding"}, {"tag": "shelters"}]
    monkeypatch.setattr(tag_library, "_connect", lambda _dbname: _Conn(rows))

    assert tag_library.read_pair_tag_library("save_05") == ["hiding", "shelters"]


def _fake_entries() -> list[tag_library.TagLibraryEntry]:
    return [
        tag_library.TagLibraryEntry(
            entity_kind="character",
            category="state",
            tag="wounded",
            is_ephemeral=True,
            description="Character has an acute wound.",
            category_description="Immediate character state.",
            prompt_order=10,
        ),
        tag_library.TagLibraryEntry(
            entity_kind="character",
            category="state",
            tag="watchful",
            is_ephemeral=False,
            description="Character is alert to subtle danger.",
            category_description="Immediate character state.",
            prompt_order=10,
        ),
        tag_library.TagLibraryEntry(
            entity_kind="place",
            category="place_affordance",
            tag="safe_house",
            is_ephemeral=False,
            description="Place can shelter people from danger.",
            category_description="Functional place affordance.",
            prompt_order=10,
        ),
        tag_library.TagLibraryEntry(
            entity_kind="faction",
            category="ideology",
            tag="loyalist",
            is_ephemeral=False,
            description="Faction defends the current order.",
            category_description="Faction's political commitment.",
            prompt_order=10,
        ),
    ]


def _patch_contextual_registry(
    monkeypatch: pytest.MonkeyPatch,
    *,
    entries: Optional[list[tag_library.TagLibraryEntry]] = None,
    active_tags: Optional[set[str]] = None,
) -> None:
    registry_entries = entries or _fake_entries()
    categories = [
        tag_library.TagCategoryEntry(
            entity_kind=entry.entity_kind,
            category=entry.category,
            description=entry.category_description,
            prompt_order=entry.prompt_order,
        )
        for entry in registry_entries
    ]
    categories = list(
        {(entry.entity_kind, entry.category): entry for entry in categories}.values()
    )
    monkeypatch.setattr(
        tag_library,
        "read_tag_library",
        lambda _dbname: registry_entries,
    )
    monkeypatch.setattr(
        tag_library,
        "read_tag_categories",
        lambda _dbname: categories,
    )
    monkeypatch.setattr(
        tag_library,
        "read_pair_tag_entries",
        lambda _dbname: [
            tag_library.PairTagLibraryEntry(
                tag="protects",
                description="Subject actively protects object.",
            ),
            tag_library.PairTagLibraryEntry(
                tag="contact:social",
                description="Subject can reach object socially.",
            ),
        ],
    )
    monkeypatch.setattr(
        tag_library,
        "read_event_types",
        lambda _dbname: ["evade_pursuit", "slept"],
    )
    monkeypatch.setattr(
        tag_library,
        "read_current_entity_tag_names",
        lambda _dbname, *, entity_ids: active_tags or set(),
    )


def _index_names(rendered: str) -> list[str]:
    index = rendered.split("### Complete Tag-Name Index", 1)[1].split(
        "### Pair-Tag Names", 1
    )[0]
    names: list[str] = []
    for line in index.splitlines():
        if " — " not in line:
            continue
        names.extend(
            name.strip()
            for name in line.split(" — ", 1)[1].split(",")
            if name.strip() and name.strip() != "(none)"
        )
    return names


def _registry_digest(rendered: str) -> str:
    match = re.search(r"registry digest: ([0-9a-f]{12})", rendered)
    assert match is not None
    return match.group(1)


def test_contextual_library_keeps_complete_name_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every registered tag name appears exactly once in the Tier 1 index."""

    entries = _fake_entries()
    _patch_contextual_registry(monkeypatch, entries=entries, active_tags={"wounded"})

    rendered = tag_library.format_contextual_tag_library(
        "save_05",
        context=tag_library.TagLibraryContext(
            present_entity_ids=[1, 2],
            proposal_tag_names={"safe_house"},
            has_pending_proposals=True,
        ),
    )

    assert _index_names(rendered) == [entry.tag for entry in entries]
    assert len(_index_names(rendered)) == len(set(_index_names(rendered)))


def test_contextual_library_expands_active_and_proposal_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tier 2 describes active and proposed tags, with conditional event types."""

    _patch_contextual_registry(monkeypatch, active_tags={"wounded"})
    with_proposals = tag_library.format_contextual_tag_library(
        "save_05",
        context=tag_library.TagLibraryContext(
            present_entity_ids=[1],
            proposal_tag_names={"safe_house"},
            has_pending_proposals=True,
        ),
    )
    without_proposals = tag_library.format_contextual_tag_library(
        "save_05",
        context=tag_library.TagLibraryContext(
            present_entity_ids=[1],
            proposal_tag_names=set(),
            has_pending_proposals=False,
        ),
    )

    relevant = with_proposals.split("### Scene-Relevant Tags", 1)[1]
    assert "`wounded` (ephemeral): Character has an acute wound." in relevant
    assert "`safe_house`: Place can shelter people from danger." in relevant
    assert "watchful" not in relevant
    assert "### Event-Type Names" in with_proposals
    assert "evade_pursuit" in with_proposals
    assert "### Event-Type Names" not in without_proposals
    assert "evade_pursuit" not in without_proposals


def test_contextual_library_digest_is_stable_and_registry_sensitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Digest is deterministic and changes when the closed registry changes."""

    _patch_contextual_registry(monkeypatch)
    context = tag_library.TagLibraryContext([], set(), False)
    first = tag_library.format_contextual_tag_library("save_05", context=context)
    second = tag_library.format_contextual_tag_library("save_05", context=context)
    expanded_entries = [
        *_fake_entries(),
        tag_library.TagLibraryEntry(
            entity_kind="character",
            category="state",
            tag="rested",
            is_ephemeral=False,
            description="Character is well rested.",
            category_description="Immediate character state.",
            prompt_order=10,
        ),
    ]
    _patch_contextual_registry(monkeypatch, entries=expanded_entries)
    expanded = tag_library.format_contextual_tag_library("save_05", context=context)

    assert _registry_digest(first) == _registry_digest(second)
    assert _registry_digest(first) != _registry_digest(expanded)


@pytest.mark.skipif(
    os.environ.get("NEXUS_RUN_POSTGRES") != "1",
    reason="Set NEXUS_RUN_POSTGRES=1 for the read-only save_05 size proof.",
)
def test_contextual_library_save_05_completeness_and_size() -> None:
    """Live registry stays complete while a realistic slice is at most half-size."""

    conn = tag_library._connect("save_05")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT entity_id
                FROM entity_tags_current
                ORDER BY entity_id
                LIMIT 5
                """
            )
            entity_ids = [int(row["entity_id"]) for row in cur.fetchall()]
    finally:
        conn.close()
    assert entity_ids, "save_05 must contain current entity tags"

    entries = tag_library.read_tag_library("save_05")
    full = tag_library.format_tag_library_for_prompt("save_05")
    contextual = tag_library.format_contextual_tag_library(
        "save_05",
        context=tag_library.TagLibraryContext(
            present_entity_ids=entity_ids,
            proposal_tag_names={"recently_violent"},
            has_pending_proposals=True,
        ),
    )
    encoding = tiktoken.get_encoding("o200k_base")
    full_tokens = len(encoding.encode(full))
    contextual_tokens = len(encoding.encode(contextual))
    print(
        "save_05 tag library size: "
        f"full={len(full.encode('utf-8'))} bytes/{full_tokens} o200k tokens; "
        f"contextual={len(contextual.encode('utf-8'))} bytes/"
        f"{contextual_tokens} o200k tokens"
    )

    assert sorted(_index_names(contextual)) == sorted(entry.tag for entry in entries)
    assert contextual_tokens <= full_tokens * 0.5


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

    def execute(self, _sql: str, params: tuple[object, ...] = ()) -> None:
        self.params = params

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows
