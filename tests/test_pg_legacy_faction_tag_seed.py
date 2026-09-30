"""``seed_legacy_faction_tag`` plants a migration-043 legacy faction tag.

The faction table audit maps tags in the seven faction categories migration
043 deprecated, and its assertions pass vacuously on a save without one. These
tests read back what the helper wrote on a disposable template clone: the
deprecated registry row, the live tag row, and exactly one current bestowal,
for a tag already in the template's vocabulary and for a new one. They also
pin its refusals: a category that is not a legacy faction category, and an
entity that is not a faction.
"""

from __future__ import annotations

from contextlib import closing

import pytest

from nexus.api.faction_table_audit import LEGACY_TAG_CATEGORIES
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    seed_faction,
    seed_legacy_faction_tag,
    seed_protagonist,
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
