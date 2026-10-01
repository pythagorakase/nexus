"""Tests for prompt-facing Orrery tag-library rendering."""

from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
import re
from typing import Any, cast, Iterator, Optional


import pytest
import tiktoken

from nexus.agents.logon.skald_wire import PlaceRef, PresenceBaseline
import nexus.agents.orrery.tag_library as tag_library
from nexus.agents.lore.logon_utility import (
    LogonUtility,
    proposal_tag_names_from_payload,
)
from nexus.config.story_model import StorySettings
from nexus.prompts.registry import PromptId, load
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    seed_deprecated_category_tag,
    seed_entity_tag,
    seed_place,
    seed_protagonist,
    seed_story_clock,
    seed_zone,
)
from tests.settings_helpers import settings_with
from tests.test_orrery.checkpointed_story_support import seed_checkpointed_story

# A label for the fake-backed tests below, which replace every connection and
# session with fakes; no database of this name exists or is ever opened.
FAKE_DBNAME = "fake_tag_library_db"


def test_format_tag_library_groups_live_tags_by_entity_kind(monkeypatch) -> None:
    """Prompt renderer exposes the DB-backed vocabulary without hand examples."""

    rows = [
        {
            "entity_kind": "character",
            "category": "state",
            "category_description": "Character state.",
            "prompt_order": 10,
            "category_deprecated": False,
            "active_somewhere": False,
            "tag": "wounded",
            "is_ephemeral": True,
            "description": "Character has an acute wound.",
        },
        {
            "entity_kind": "place",
            "category": "place_function",
            "category_description": "Functional role a place serves.",
            "prompt_order": 10,
            "category_deprecated": False,
            "active_somewhere": False,
            "tag": "haven",
            "is_ephemeral": False,
            "description": "Place can shelter or hide someone safely.",
        },
    ]
    monkeypatch.setattr(tag_library, "_connect", lambda _dbname: _Conn(rows))

    rendered = tag_library.format_tag_library_for_prompt(FAKE_DBNAME)

    assert "Current Orrery Tag Library" in rendered
    assert load(PromptId.TAG_LIBRARY_HEADER) in rendered
    assert "Do not invent new tag names at runtime" in rendered
    assert "### Character Tags" in rendered
    assert "`wounded` (ephemeral): Character has an acute wound." in rendered
    assert "### Place Tags" in rendered
    assert "`haven`: Place can shelter or hide someone safely." in rendered


def test_format_tag_library_rejects_unknown_entity_kind() -> None:
    with pytest.raises(ValueError, match="Unknown Orrery entity kind"):
        tag_library.format_tag_library_for_prompt(
            FAKE_DBNAME, entity_kinds=["character", "monster"]
        )


def test_read_pair_tag_library_uses_shared_connection(monkeypatch) -> None:
    rows = [{"tag": "hiding"}, {"tag": "shelters"}]
    monkeypatch.setattr(tag_library, "_connect", lambda _dbname: _Conn(rows))

    assert tag_library.read_pair_tag_library(FAKE_DBNAME) == ["hiding", "shelters"]


def test_read_tag_library_captures_reapplication_policy(monkeypatch) -> None:
    rows = [
        {
            "entity_kind": "character",
            "category": "disposition",
            "category_description": "Recent conduct.",
            "prompt_order": 10,
            "category_deprecated": False,
            "active_somewhere": False,
            "tag": "recently_protective",
            "is_ephemeral": True,
            "description": "Recently acted to protect someone.",
            "reapplication_policy": "extend_expiry",
        }
    ]
    monkeypatch.setattr(tag_library, "_connect", lambda _dbname: _Conn(rows))

    entries = tag_library.read_tag_library(FAKE_DBNAME)

    assert len(entries) == 1
    assert entries[0].reapplication_policy == "extend_expiry"


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
            category="place_function",
            tag="haven",
            is_ephemeral=False,
            description="Place can shelter or hide someone safely.",
            category_description="Functional role a place serves.",
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
        lambda _dbname, **_options: registry_entries,
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
        FAKE_DBNAME,
        context=tag_library.TagLibraryContext(
            present_entity_refs=[
                tag_library.EntityRowReference("character", 1),
                tag_library.EntityRowReference("place", 2),
            ],
            proposal_tag_names={"haven"},
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
        FAKE_DBNAME,
        context=tag_library.TagLibraryContext(
            present_entity_refs=[tag_library.EntityRowReference("character", 1)],
            proposal_tag_names={"haven"},
            has_pending_proposals=True,
        ),
    )
    without_proposals = tag_library.format_contextual_tag_library(
        FAKE_DBNAME,
        context=tag_library.TagLibraryContext(
            present_entity_refs=[tag_library.EntityRowReference("character", 1)],
            proposal_tag_names=set(),
            has_pending_proposals=False,
        ),
    )

    relevant = with_proposals.split("### Scene-Relevant Tags", 1)[1]
    assert "`wounded` (ephemeral): Character has an acute wound." in relevant
    assert "`haven`: Place can shelter or hide someone safely." in relevant
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
        FAKE_DBNAME,
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
                    "tag": "haven",
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
        FAKE_DBNAME,
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
    assert "`haven`" not in relevant
    assert session.translation_queries == 1


def test_contextual_library_digest_is_stable_and_registry_sensitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Digest is deterministic and changes when the closed registry changes."""

    _patch_contextual_registry(monkeypatch)
    context = tag_library.TagLibraryContext([], set(), False)
    first = tag_library.format_contextual_tag_library(FAKE_DBNAME, context=context)
    second = tag_library.format_contextual_tag_library(FAKE_DBNAME, context=context)
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
    expanded = tag_library.format_contextual_tag_library(FAKE_DBNAME, context=context)

    assert _registry_digest(first) == _registry_digest(second)
    assert _registry_digest(first) != _registry_digest(expanded)


@pytest.mark.requires_postgres
def test_deprecated_registry_category_leaves_the_library(monkeypatch) -> None:
    """A live tag under a deprecated category never reaches the prompts.

    On a fresh template clone, ``worksite`` is itself live but sits under
    ``place_affordance``, which migration 043 deprecated; ``haven`` sits
    under the live ``place_function``. Reviving the category on the clone
    brings ``worksite`` back, so the registry flag alone decides.
    """

    with disposable_slot_database("qa640_811_tag_library") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=5, dbname=dbname)
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.tag, t.category, t.deprecated, r.deprecated
                FROM tags t
                JOIN tag_category_registry r ON r.category = t.category
                WHERE t.tag IN ('worksite', 'haven')
                ORDER BY t.tag
                """
            )
            assert cur.fetchall() == [
                ("haven", "place_function", False, False),
                ("worksite", "place_affordance", False, True),
            ]

        library = {entry.tag for entry in tag_library.read_tag_library(dbname)}
        categories = {
            entry.category for entry in tag_library.read_tag_categories(dbname)
        }
        rendered = tag_library.format_tag_library_for_prompt(dbname)

        assert "haven" in library
        assert "worksite" not in library
        assert "place_function" in categories
        assert "place_affordance" not in categories
        assert "`haven`" in rendered
        assert "worksite" not in rendered
        assert "place_affordance" not in rendered

        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE tag_category_registry SET deprecated = FALSE "
                "WHERE category = 'place_affordance'"
            )
        assert "worksite" in {
            entry.tag for entry in tag_library.read_tag_library(dbname)
        }
        assert "place_affordance" in {
            entry.category for entry in tag_library.read_tag_categories(dbname)
        }


def _scene_library(dbname: str, place_id: int) -> str:
    """Render the contextual library with one place present.

    The proposal names ``worksite`` too: a proposal never selects a
    deprecated-category entry, only a present entity's active tag does.
    """

    return tag_library.format_contextual_tag_library(
        dbname,
        context=tag_library.TagLibraryContext(
            present_entity_refs=[
                tag_library.EntityRowReference(kind="place", row_id=place_id)
            ],
            proposal_tag_names={"worksite", "haven"},
            has_pending_proposals=False,
        ),
    )


def _section(rendered: str, heading: str) -> str:
    """Return one ``###`` section of a rendered library, heading excluded."""

    body = rendered.split(f"### {heading}\n", 1)[1]
    return body.split("\n### ", 1)[0]


@pytest.mark.requires_postgres
def test_scene_shows_a_present_entitys_deprecated_tag_as_clear_only(
    monkeypatch,
) -> None:
    """Scene-Relevant Tags list an active deprecated-category tag, marked.

    ``worksite`` sits under ``place_affordance``, which the registry
    deprecates. The first place carries it and the second does not. With the
    first present the scene lists the tag's real entry with ``(clear only)``;
    with only the second present it appears nowhere. The name index, the full
    library, and the taxonomy never list it.
    """

    with disposable_slot_database("qa640_811_scene_clear_only") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=5, dbname=dbname)
        seed_zone(
            dbname,
            name="Harbor Ward",
            min_longitude=-74.1,
            min_latitude=40.6,
            max_longitude=-73.8,
            max_latitude=40.9,
        )
        carrying, carrying_entity = seed_place(dbname, name="Dry Dock Nine")
        bare, _ = seed_place(dbname, name="Lamplighter Row", longitude=-73.95)
        seed_deprecated_category_tag(dbname, entity_id=carrying_entity, tag="worksite")
        (worksite,) = [
            entry
            for entry in tag_library.read_tag_library(
                dbname, include_deprecated_categories=True
            )
            if entry.tag == "worksite"
        ]
        assert (worksite.category, worksite.category_deprecated) == (
            "place_affordance",
            True,
        )
        assert worksite.active_somewhere is True

        present = _scene_library(dbname, carrying)
        scene = _section(present, "Scene-Relevant Tags")
        entry_line = (
            f"- place/place_affordance: {tag_library._format_tag_entry(worksite)}"
            " (clear only)"
        )
        assert entry_line in scene.splitlines()
        assert [line for line in scene.splitlines() if "worksite" in line] == [
            entry_line
        ]
        assert "(clear only)" not in scene.replace(entry_line, "")
        assert "`haven`" in scene
        assert "worksite" not in _section(present, "Complete Tag-Name Index")
        assert "place_affordance" not in _section(present, "Category Taxonomy")

        absent = _scene_library(dbname, bare)
        assert "worksite" not in absent
        assert "(clear only)" not in absent
        assert "`haven`" in _section(absent, "Scene-Relevant Tags")

        assert "worksite" not in {
            entry.tag for entry in tag_library.read_tag_library(dbname)
        }
        assert "place_affordance" not in {
            entry.category for entry in tag_library.read_tag_categories(dbname)
        }


@pytest.mark.requires_postgres
def test_scene_clear_only_line_follows_the_carrying_entitys_kind(
    monkeypatch,
) -> None:
    """A deprecated category registered for two kinds marks only the carrier's.

    The clone registers ``place_affordance`` for characters as well, still
    deprecated. A present character carries ``worksite``; a present place
    does not. The scene lists the character-kind entry as clear only and no
    place-kind entry, since the validator accepts the clear only where an
    entity of that kind carries the tag.
    """

    with disposable_slot_database("qa640_811_scene_kind") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=5, dbname=dbname)
        seed_zone(
            dbname,
            name="Harbor Ward",
            min_longitude=-74.1,
            min_latitude=40.6,
            max_longitude=-73.8,
            max_latitude=40.9,
        )
        bare_place, _ = seed_place(dbname, name="Lamplighter Row")
        character, character_entity = seed_protagonist(dbname)
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tag_category_registry (
                    category, entity_kind, prompt_order, description, deprecated
                )
                SELECT category, 'character', prompt_order, description, TRUE
                FROM tag_category_registry
                WHERE category = 'place_affordance' AND entity_kind = 'place'
                """
            )
            assert cur.rowcount == 1
        seed_deprecated_category_tag(dbname, entity_id=character_entity, tag="worksite")

        entries = {
            entry.entity_kind: entry
            for entry in tag_library.read_tag_library(
                dbname, include_deprecated_categories=True
            )
            if entry.tag == "worksite"
        }
        assert set(entries) == {"character", "place"}
        assert entries["character"].active_somewhere is True
        assert entries["place"].active_somewhere is False

        rendered = tag_library.format_contextual_tag_library(
            dbname,
            context=tag_library.TagLibraryContext(
                present_entity_refs=[
                    tag_library.EntityRowReference(kind="character", row_id=character),
                    tag_library.EntityRowReference(kind="place", row_id=bare_place),
                ],
                proposal_tag_names=set(),
                has_pending_proposals=False,
            ),
        )
        scene = _section(rendered, "Scene-Relevant Tags").splitlines()
        character_line = (
            "- character/place_affordance: "
            f"{tag_library._format_tag_entry(entries['character'])} (clear only)"
        )
        assert [line for line in scene if "(clear only)" in line] == [character_line]
        assert not any(line.startswith("- place/place_affordance") for line in scene)


def _seed_worksite_scene(dbname: str) -> tuple[int, int]:
    """Seed a player, a place carrying ``worksite``, and a bare place.

    Returns the carrying and bare place row IDs.
    """

    seed_zone(
        dbname,
        name="Harbor Ward",
        min_longitude=-74.1,
        min_latitude=40.6,
        max_longitude=-73.8,
        max_latitude=40.9,
    )
    carrying, carrying_entity = seed_place(dbname, name="Dry Dock Nine")
    bare, _ = seed_place(dbname, name="Lamplighter Row", longitude=-73.95)
    seed_protagonist(dbname)
    seed_deprecated_category_tag(dbname, entity_id=carrying_entity, tag="worksite")
    return carrying, bare


@pytest.mark.requires_postgres
def test_full_turn_library_still_lists_scene_clear_only_tags(monkeypatch) -> None:
    """``contextual = false`` keeps the scene's clear-only tags visible.

    A turn with the switch off renders the full live-only library. With the
    place carrying ``worksite`` as its setting, the ``worksite`` clear-only
    line follows under Clear-Only Tags in This Scene; with the bare place as
    the setting, the full library stands alone.
    """

    with disposable_slot_database("qa640_811_full_clear_only") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=5, dbname=dbname)
        carrying, bare = _seed_worksite_scene(dbname)
        utility = LogonUtility(
            settings_with({"apex.tag_library.contextual": False}),
            dbname=dbname,
            model_override="TEST",
            story_settings=StorySettings(),
        )
        (worksite,) = [
            entry
            for entry in tag_library.read_tag_library(
                dbname, include_deprecated_categories=True
            )
            if entry.tag == "worksite"
        ]
        full_library = tag_library.format_tag_library_for_prompt(dbname)
        assert "worksite" not in full_library
        assert "### Place Tags" in full_library

        def _turn_library(place_id: int, name: str) -> str:
            return utility._format_turn_tag_library(
                {"user_input": "Continue."},
                presence_baseline=PresenceBaseline(
                    setting=PlaceRef(kind="place", id=place_id, name=name)
                ),
            )

        present = _turn_library(carrying, "Dry Dock Nine")
        assert present == (
            f"{full_library}\n\n### Clear-Only Tags in This Scene\n\n"
            f"- place/place_affordance: {tag_library._format_tag_entry(worksite)}"
            " (clear only)"
        )

        absent = _turn_library(bare, "Lamplighter Row")
        assert absent == full_library
        assert "Clear-Only Tags in This Scene" not in absent
        assert "worksite" not in absent


@pytest.mark.requires_postgres
def test_contextual_scene_rendering_is_pinned(monkeypatch) -> None:
    """``contextual = true`` renders the scene exactly as before the refactor.

    The contextual library and the full-library turn share one clear-only
    selection and line renderer. The Scene-Relevant Tags section, the only
    one that selection touches, is pinned byte for byte for a scene with and
    without ``worksite``; the clear-only line sorts before the live
    ``haven`` entry by category order, so it stays interleaved, not appended.
    """

    with disposable_slot_database("qa640_811_scene_pin") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=5, dbname=dbname)
        carrying, bare = _seed_worksite_scene(dbname)
        haven = (
            "- place/place_function: `haven`: "
            "Place can shelter or hide someone safely."
        )
        worksite = (
            "- place/place_affordance: `worksite`: Place supports physical, "
            "field, maintenance, construction, or repair work. (clear only)"
        )

        present = _scene_library(dbname, carrying)
        absent = _scene_library(dbname, bare)

        assert present.split("### Scene-Relevant Tags\n", 1)[1] == (
            f"\n{worksite}\n{haven}"
        )
        assert absent.split("### Scene-Relevant Tags\n", 1)[1] == f"\n{haven}"
        assert (
            present.split("### Scene-Relevant Tags\n", 1)[0]
            == absent.split("### Scene-Relevant Tags\n", 1)[0]
        )
        assert (
            tag_library.format_scene_clear_only_tags(
                dbname,
                present_entity_refs=[
                    tag_library.EntityRowReference(kind="place", row_id=carrying)
                ],
                anchor_chunk_id=None,
            )
            == worksite
        )
        assert (
            tag_library.format_scene_clear_only_tags(
                dbname,
                present_entity_refs=[
                    tag_library.EntityRowReference(kind="place", row_id=bare)
                ],
                anchor_chunk_id=None,
            )
            == ""
        )


@pytest.fixture
def routed_slot5_clone(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Yield a template clone that slot 5 resolves to for the test's duration."""

    with disposable_slot_database("qa885_tag_library") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=5, dbname=dbname)
        yield dbname


@pytest.mark.requires_postgres
def test_contextual_library_seeded_story_completeness_and_size(
    routed_slot5_clone: str,
) -> None:
    """Live registry stays complete while a realistic slice is at most half-size.

    ``seed_checkpointed_story`` gives the clone a tagged confidant
    (``kin_protector``) and a head chunk on the canonical clock.
    """

    dbname = routed_slot5_clone
    story = seed_checkpointed_story(dbname)
    conn = tag_library._connect(dbname)
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
    assert entity_refs == [
        tag_library.EntityRowReference("character", story.confidant_character_id)
    ], "the seeded confidant's kin_protector tag must be current"
    assert anchor_row is not None and int(anchor_row["chunk_id"]) == (
        story.head_chunk_id
    ), "the seeded head chunk must carry the anchor world time"

    entries = tag_library.read_tag_library(dbname)
    full = tag_library.format_tag_library_for_prompt(dbname)
    contextual = tag_library.format_contextual_tag_library(
        dbname,
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
        "seeded story tag library size: "
        f"full={len(full.encode('utf-8'))} bytes/{full_tokens} o200k tokens; "
        f"contextual={len(contextual.encode('utf-8'))} bytes/"
        f"{contextual_tokens} o200k tokens"
    )

    relevant = contextual.split("### Scene-Relevant Tags", 1)[1]
    assert "`kin_protector`" in relevant
    assert "`recently_violent`" in relevant
    assert sorted(_index_names(contextual)) == sorted(entry.tag for entry in entries)
    assert contextual_tokens <= full_tokens * 0.5


@pytest.mark.requires_postgres
def test_contextual_library_skewed_character_row_id_uses_entity_id(
    routed_slot5_clone: str,
) -> None:
    """A skewed character row ID must not select another entity's tags.

    The zone and place are seeded first, so the place takes the clone's
    first entity ID and the protagonist's ``characters.id`` equals that
    place's entity ID while its own ``entity_id`` differs. The character
    carries ``kin_protector`` and the place carries ``haven``; a lookup by
    row ID instead of entity ID would render ``haven`` for the character.
    """

    dbname = routed_slot5_clone
    seed_zone(
        dbname,
        name="Namespace Ward",
        min_longitude=-74.1,
        min_latitude=40.6,
        max_longitude=-73.8,
        max_latitude=40.9,
    )
    _, place_entity_id = seed_place(dbname, name="Namespace Refuge")
    story_clock = datetime(2100, 1, 2, tzinfo=timezone.utc)
    seeded_row_id, seeded_entity_id = seed_protagonist(
        dbname, name="Namespace Protagonist", base_timestamp=story_clock.isoformat()
    )
    assert place_entity_id == seeded_row_id != seeded_entity_id, (
        f"place entity {place_entity_id}, character row {seeded_row_id}, and "
        f"character entity {seeded_entity_id} must skew the two namespaces"
    )
    seed_story_clock(dbname, world_time=story_clock)
    seed_entity_tag(dbname, entity_id=seeded_entity_id, tag="kin_protector")
    seed_entity_tag(dbname, entity_id=place_entity_id, tag="haven")

    conn = tag_library._connect(dbname)
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, entity_id, name
                FROM characters
                WHERE id <> entity_id
                ORDER BY id
                LIMIT 1
                """
            )
            character = cur.fetchone()
            assert character is not None and (
                int(character["id"]),
                int(character["entity_id"]),
            ) == (seeded_row_id, seeded_entity_id), (
                "the seeded protagonist must be a character whose characters.id "
                "differs from characters.entity_id"
            )
            row_id = int(character["id"])
            entity_id = int(character["entity_id"])
            character_name = str(character["name"])

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
            assert anchor is not None, "the seeded story clock must set world time"

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

            character_tags = active_tags(entity_id)
            wrong_entity_tags = active_tags(row_id)
    finally:
        conn.close()

    wrong_only_tags = wrong_entity_tags - character_tags
    assert character_tags, (
        f"{character_name} (entity {entity_id}) must have active tags for the "
        "namespace proof"
    )
    assert (
        wrong_only_tags
    ), f"canonical entity {row_id} must have a tag not active on {character_name}"

    rendered = tag_library.format_contextual_tag_library(
        dbname,
        context=tag_library.TagLibraryContext(
            present_entity_refs=[tag_library.EntityRowReference("character", row_id)],
            proposal_tag_names=set(),
            has_pending_proposals=False,
            anchor_chunk_id=int(anchor["chunk_id"]),
        ),
    )
    relevant = rendered.split("### Scene-Relevant Tags", 1)[1]
    rendered_names = set(re.findall(r"`([^`]+)`", relevant))

    assert character_tags <= rendered_names
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
