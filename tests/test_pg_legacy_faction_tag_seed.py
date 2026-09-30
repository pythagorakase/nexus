"""``seed_legacy_faction_tag`` plants a migration-043 legacy faction tag.

The faction table audit maps tags in the seven faction categories migration
043 deprecated, and its assertions pass vacuously on a save without one. These
tests read back what the helper wrote on a disposable template clone: the
deprecated registry row, the live tag row, and exactly one current bestowal,
for a tag already in the template's vocabulary and for a new one. They also
pin its refusals: a category that is not a legacy faction category, and an
entity that is not a faction. Its exclusivity is pinned from the other side:
``seed_entity_tag`` refuses a deprecated-category tag and names the legacy
seed, and ``seed_deprecated_category_tag`` refuses faction entities.
"""

from __future__ import annotations

from contextlib import closing

import pytest

from nexus.api.faction_table_audit import LEGACY_TAG_CATEGORIES
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    seed_deprecated_category_tag,
    seed_entity_tag,
    seed_faction,
    seed_legacy_faction_tag,
    seed_place,
    seed_protagonist,
    seed_zone,
)

pytestmark = pytest.mark.requires_postgres


def test_legacy_tag_is_current_on_the_faction_in_its_deprecated_category() -> None:
    """A template tag and a new tag both land as current legacy rows."""

    with disposable_slot_database("qa885_legacy_tag") as dbname:
        _, faction_entity_id = seed_faction(dbname, name="Legacy Tag Guild")
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM tags")
            tags_before = cur.fetchone()[0]
            cur.execute(
                "SELECT count(*) FROM tag_category_registry "
                "WHERE category = 'operational_secrecy' AND entity_kind = 'faction'"
            )
            assert cur.fetchone()[0] == 1
            cur.execute(
                "DELETE FROM tag_category_registry "
                "WHERE category = 'operational_secrecy' AND entity_kind = 'faction'"
            )
            conn.commit()

        template_row = seed_legacy_faction_tag(
            dbname, faction_entity_id=faction_entity_id, tag="gray_legal"
        )
        new_row = seed_legacy_faction_tag(
            dbname,
            faction_entity_id=faction_entity_id,
            category="operational_secrecy",
            tag="qa885_sealed_ledger",
        )

        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM tags")
            assert cur.fetchone()[0] == tags_before + 1
            cur.execute(
                "SELECT category, deprecated FROM tag_category_registry "
                "WHERE entity_kind = 'faction' AND category = ANY(%s) "
                "ORDER BY category",
                (["legitimacy_status", "operational_secrecy"],),
            )
            assert cur.fetchall() == [
                ("legitimacy_status", True),
                ("operational_secrecy", True),
            ]
            cur.execute(
                "SELECT entity_tag_id, entity_id, category, tag "
                "FROM entity_tags_current WHERE entity_id = %s ORDER BY entity_tag_id",
                (faction_entity_id,),
            )
            assert cur.fetchall() == [
                (template_row, faction_entity_id, "legitimacy_status", "gray_legal"),
                (
                    new_row,
                    faction_entity_id,
                    "operational_secrecy",
                    "qa885_sealed_ledger",
                ),
            ]


def test_legacy_tag_refuses_live_categories_and_non_factions() -> None:
    """Only legacy faction categories on faction entities are planted."""

    assert "legitimacy_status" in LEGACY_TAG_CATEGORIES
    with disposable_slot_database("qa885_legacy_tag") as dbname:
        _, faction_entity_id = seed_faction(dbname, name="Legacy Tag Refusals")
        _, player_entity_id = seed_protagonist(dbname)
        with pytest.raises(ValueError, match="legacy faction categories"):
            seed_legacy_faction_tag(
                dbname,
                faction_entity_id=faction_entity_id,
                category="legitimacy",
                tag="outlaw",
            )
        with pytest.raises(AssertionError, match="is not a faction entity"):
            seed_legacy_faction_tag(
                dbname, faction_entity_id=player_entity_id, tag="gray_legal"
            )
        with pytest.raises(AssertionError, match="is not a live tag"):
            seed_legacy_faction_tag(
                dbname,
                faction_entity_id=faction_entity_id,
                category="operational_secrecy",
                tag="gray_legal",
            )
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM entity_tags")
            assert cur.fetchone()[0] == 0


def _current_tags(dbname: str, entity_id: int) -> list[tuple[int, str, str]]:
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT entity_tag_id, category, tag FROM entity_tags_current "
            "WHERE entity_id = %s ORDER BY entity_tag_id",
            (entity_id,),
        )
        return list(cur.fetchall())


def test_seed_entity_tag_refuses_deprecated_categories_and_plants_live_ones() -> None:
    """Legacy faction vocabulary reaches a clone only through the legacy seed.

    ``gray_legal`` is a live tag in ``legitimacy_status``, which migration 043
    deprecated for factions. ``seed_entity_tag`` refuses it by name and writes
    nothing, ``seed_legacy_faction_tag`` plants it, and ``seed_entity_tag``
    still plants ``contested`` from the live ``legitimacy`` category on the
    same faction.
    """

    with disposable_slot_database("qa885_legacy_tag") as dbname:
        _, faction_entity_id = seed_faction(dbname, name="Exclusive Seed Guild")
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT t.category, r.deprecated FROM tags t "
                "JOIN tag_category_registry r "
                "ON r.category = t.category AND r.entity_kind = 'faction' "
                "WHERE t.tag = 'gray_legal' AND NOT t.deprecated"
            )
            assert cur.fetchall() == [("legitimacy_status", True)]

        with pytest.raises(
            ValueError,
            match=(
                r"tag 'gray_legal' is in the deprecated faction category "
                r"'legitimacy_status'; use seed_legacy_faction_tag"
            ),
        ):
            seed_entity_tag(dbname, entity_id=faction_entity_id, tag="gray_legal")
        assert _current_tags(dbname, faction_entity_id) == []

        legacy_row = seed_legacy_faction_tag(
            dbname, faction_entity_id=faction_entity_id, tag="gray_legal"
        )
        live_row = seed_entity_tag(dbname, entity_id=faction_entity_id, tag="contested")
        assert _current_tags(dbname, faction_entity_id) == [
            (legacy_row, "legitimacy_status", "gray_legal"),
            (live_row, "legitimacy", "contested"),
        ]


def test_deprecated_category_seed_refuses_factions_and_live_categories() -> None:
    """The non-faction deprecated-category seed never plants faction vocabulary.

    ``worksite`` sits in ``place_affordance``, deprecated for places.
    ``seed_entity_tag`` refuses it on a place and names
    ``seed_deprecated_category_tag``, which plants it. That seed refuses a
    faction entity and a live-category tag, and writes nothing for either.
    """

    with disposable_slot_database("qa885_legacy_tag") as dbname:
        seed_zone(
            dbname,
            name="Harbor Ward",
            min_longitude=-74.1,
            min_latitude=40.6,
            max_longitude=-73.8,
            max_latitude=40.9,
        )
        _, place_entity_id = seed_place(dbname, name="Dry Dock Nine")
        _, faction_entity_id = seed_faction(dbname, name="Dockside Compact")

        with pytest.raises(
            ValueError,
            match=(
                r"tag 'worksite' is in the deprecated place category "
                r"'place_affordance'; use seed_deprecated_category_tag"
            ),
        ):
            seed_entity_tag(dbname, entity_id=place_entity_id, tag="worksite")
        with pytest.raises(ValueError, match="use seed_legacy_faction_tag"):
            seed_deprecated_category_tag(
                dbname, entity_id=faction_entity_id, tag="gray_legal"
            )
        with pytest.raises(ValueError, match="not a deprecated place category"):
            seed_deprecated_category_tag(dbname, entity_id=place_entity_id, tag="haven")
        assert _current_tags(dbname, place_entity_id) == []
        assert _current_tags(dbname, faction_entity_id) == []

        row = seed_deprecated_category_tag(
            dbname, entity_id=place_entity_id, tag="worksite"
        )
        assert _current_tags(dbname, place_entity_id) == [
            (row, "place_affordance", "worksite")
        ]
