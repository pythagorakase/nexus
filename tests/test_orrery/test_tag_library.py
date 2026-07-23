"""Tests for prompt-facing Orrery tag-library rendering."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
import re
from typing import Any, cast, Optional

import pytest
import tiktoken

import nexus.agents.orrery.tag_library as tag_library
from nexus.agents.lore.logon_utility import proposal_tag_names_from_payload


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
            tag="restless",
            is_ephemeral=True,
            description="Character cannot settle into a stable rhythm.",
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
    patch_active_lookup: bool = True,
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
    if patch_active_lookup:
        monkeypatch.setattr(
            tag_library,
            "read_current_entity_tag_names",
            lambda _dbname, *, entity_refs, anchor_chunk_id: active_tags or set(),
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
            present_entity_refs=[
                tag_library.EntityRowReference("character", 1),
                tag_library.EntityRowReference("place", 2),
            ],
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
            present_entity_refs=[tag_library.EntityRowReference("character", 1)],
            proposal_tag_names={"safe_house"},
            has_pending_proposals=True,
        ),
    )
    without_proposals = tag_library.format_contextual_tag_library(
        "save_05",
        context=tag_library.TagLibraryContext(
            present_entity_refs=[tag_library.EntityRowReference("character", 1)],
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


def test_pending_mood_set_expands_the_mood_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mood.set is a single-entity tag carrier for Tier-2 selection."""

    _patch_contextual_registry(monkeypatch)
    proposal_names = proposal_tag_names_from_payload(
        {
            "orrery_imminent_activity": [
                {"state_delta": {"mood.set": {"mood": "restless"}}}
            ]
        }
    )

    rendered = tag_library.format_contextual_tag_library(
        "save_05",
        context=tag_library.TagLibraryContext(
            present_entity_refs=[],
            proposal_tag_names=proposal_names,
            has_pending_proposals=True,
        ),
    )

    relevant = rendered.split("### Scene-Relevant Tags", 1)[1]
    assert (
        "`restless` (ephemeral): Character cannot settle into a stable rhythm."
        in relevant
    )


class _MappingResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def mappings(self) -> "_MappingResult":
        return self

    def first(self) -> Optional[dict[str, Any]]:
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class _TwoClockTagSession:
    """Fake SQLAlchemy session with skewed row/entity IDs and two clocks."""

    def __init__(self) -> None:
        self.anchor = datetime(2073, 5, 3, 12, tzinfo=timezone.utc)
        self.translation_queries = 0

    def execute(
        self,
        statement: object,
        params: Optional[dict[str, Any]] = None,
    ) -> _MappingResult:
        sql = str(statement)
        bound = params or {}
        if "orrery:tag_library_entity_id_translation" in sql:
            self.translation_queries += 1
            assert bound == {
                "entity_kinds": ["character"],
                "row_ids": [9],
            }
            return _MappingResult([{"entity_id": 18}])
        if "orrery:anchor_world_time" in sql:
            assert bound == {"anchor_chunk_id": 44}
            return _MappingResult([{"world_time": self.anchor}])
        if "orrery:current_tags" in sql:
            assert bound == {"current_world_time": self.anchor}
            assert "et.expires_at_world_time > :current_world_time" in sql
            rows: list[dict[str, Any]] = [
                {
                    "entity_id": 18,
                    "tag": "watchful",
                    "is_ephemeral": False,
                    "expires_at": self.anchor + timedelta(hours=1),
                },
                {
                    "entity_id": 18,
                    "tag": "wounded",
                    "is_ephemeral": True,
                    "expires_at": self.anchor - timedelta(minutes=1),
                },
                {
                    "entity_id": 9,
                    "tag": "safe_house",
                    "is_ephemeral": False,
                    "expires_at": None,
                },
            ]
            return _MappingResult(
                [
                    {
                        "entity_id": row["entity_id"],
                        "tag": row["tag"],
                        "is_ephemeral": row["is_ephemeral"],
                    }
                    for row in rows
                    if row["expires_at"] is None or row["expires_at"] > self.anchor
                ]
            )
        raise AssertionError(f"Unexpected query: {sql}")


def test_active_tag_lookup_translates_skewed_ids_and_uses_anchor_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Row 9 resolves to entity 18; expired and entity-9 tags do not render."""

    session = _TwoClockTagSession()

    @contextmanager
    def fake_session(_dbname: Optional[str]):
        yield session

    monkeypatch.setattr(tag_library, "_slot_session", fake_session)
    _patch_contextual_registry(monkeypatch, patch_active_lookup=False)

    rendered = tag_library.format_contextual_tag_library(
        "save_05",
        context=tag_library.TagLibraryContext(
            present_entity_refs=[tag_library.EntityRowReference("character", 9)],
            proposal_tag_names=set(),
            has_pending_proposals=False,
            anchor_chunk_id=44,
        ),
    )
    relevant = rendered.split("### Scene-Relevant Tags", 1)[1]

    assert "`watchful`: Character is alert to subtle danger." in relevant
    assert "`wounded`" not in relevant
    assert "`safe_house`" not in relevant
    assert session.translation_queries == 1


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
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT etc.entity_kind::text AS entity_kind,
                                CASE etc.entity_kind::text
                                    WHEN 'character' THEN characters.id
                                    WHEN 'place' THEN places.id
                                    WHEN 'faction' THEN factions.id
                                END AS row_id
                FROM entity_tags_current AS etc
                LEFT JOIN characters
                  ON etc.entity_kind::text = 'character'
                 AND characters.entity_id = etc.entity_id
                LEFT JOIN places
                  ON etc.entity_kind::text = 'place'
                 AND places.entity_id = etc.entity_id
                LEFT JOIN factions
                  ON etc.entity_kind::text = 'faction'
                 AND factions.entity_id = etc.entity_id
                ORDER BY entity_kind, row_id
                LIMIT 5
                """
            )
            entity_refs = [
                tag_library.EntityRowReference(
                    kind=cast(tag_library.EntityKind, str(row["entity_kind"])),
                    row_id=int(row["row_id"]),
                )
                for row in cur.fetchall()
            ]
            cur.execute(
                """
                SELECT chunk_id
                FROM chunk_metadata
                WHERE world_time IS NOT NULL
                ORDER BY world_time DESC, chunk_id DESC
                LIMIT 1
                """
            )
            anchor_row = cur.fetchone()
    finally:
        conn.close()
    assert entity_refs, "save_05 must contain current entity tags"
    assert anchor_row is not None, "save_05 must contain an anchor world time"

    entries = tag_library.read_tag_library("save_05")
    full = tag_library.format_tag_library_for_prompt("save_05")
    contextual = tag_library.format_contextual_tag_library(
        "save_05",
        context=tag_library.TagLibraryContext(
            present_entity_refs=entity_refs,
            proposal_tag_names={"recently_violent"},
            has_pending_proposals=True,
            anchor_chunk_id=int(anchor_row["chunk_id"]),
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


@pytest.mark.skipif(
    os.environ.get("NEXUS_RUN_POSTGRES") != "1",
    reason="Set NEXUS_RUN_POSTGRES=1 for the read-only save_05 namespace proof.",
)
def test_contextual_library_save_05_kosi_uses_character_entity_id() -> None:
    """Kosi's row ID must not select the unrelated canonical entity's tags."""

    conn = tag_library._connect("save_05")
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, entity_id
                FROM characters
                WHERE name = 'Kosi'
                """
            )
            kosi = cur.fetchone()
            assert kosi is not None, "save_05 must contain Kosi"
            row_id = int(kosi["id"])
            entity_id = int(kosi["entity_id"])
            assert row_id != entity_id, "Kosi must retain a skewed ID namespace"

            cur.execute(
                """
                SELECT chunk_id, world_time
                FROM chunk_metadata
                WHERE world_time IS NOT NULL
                ORDER BY world_time DESC, chunk_id DESC
                LIMIT 1
                """
            )
            anchor = cur.fetchone()
            assert anchor is not None, "save_05 must contain an anchor world time"

            def active_tags(target_entity_id: int) -> set[str]:
                cur.execute(
                    """
                    SELECT DISTINCT etc.tag
                    FROM entity_tags_current AS etc
                    JOIN entity_tags AS et ON et.id = etc.entity_tag_id
                    WHERE etc.entity_id = %s
                      AND (
                          et.expires_at_world_time IS NULL
                          OR et.expires_at_world_time > %s
                      )
                    ORDER BY etc.tag
                    """,
                    (target_entity_id, anchor["world_time"]),
                )
                return {str(row["tag"]) for row in cur.fetchall()}

            kosi_tags = active_tags(entity_id)
            wrong_entity_tags = active_tags(row_id)
    finally:
        conn.close()

    wrong_only_tags = wrong_entity_tags - kosi_tags
    assert kosi_tags, "Kosi must have active tags for the namespace proof"
    assert wrong_only_tags, "entity 9 must have a discriminating active tag"

    rendered = tag_library.format_contextual_tag_library(
        "save_05",
        context=tag_library.TagLibraryContext(
            present_entity_refs=[tag_library.EntityRowReference("character", row_id)],
            proposal_tag_names=set(),
            has_pending_proposals=False,
            anchor_chunk_id=int(anchor["chunk_id"]),
        ),
    )
    relevant = rendered.split("### Scene-Relevant Tags", 1)[1]
    rendered_names = set(re.findall(r"`([^`]+)`", relevant))

    assert kosi_tags <= rendered_names
    assert wrong_only_tags.isdisjoint(rendered_names)


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
