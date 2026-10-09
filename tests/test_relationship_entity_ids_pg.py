"""Migration 151 preserves relationship history while adding entity identities.

Ordinary cases own template clones. The four explicitly corpus-marked cases
read an owner source only through the fixture's dump into a disposable clone.
Tables: the three relationship tables, characters, factions, entities,
relationship_versions, state_checkpoints and schema_migrations.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import closing
from datetime import datetime, timezone
import json
from typing import Any

import pytest
from psycopg2.errors import ForeignKeyViolation

from nexus.agents.orrery.reconstruction import capture_state_checkpoint_sync
from nexus.agents.orrery.replay import verify_checkpoints_sync
from nexus.api.new_story_db_mapper import NewStoryDatabaseMapper
from scripts import migrate
from tests.pg_fixtures import (
    CharacterPairSeed,
    connect,
    disposable_slot_database,
    seed_character,
    seed_character_pair,
    seed_committed_chunk,
    seed_faction,
    seed_faction_membership,
    seed_relationship,
)
from tests.test_orrery.checkpointed_story_support import seed_checkpointed_story
from tests.test_orrery.test_need_clock_anchor_pg import _build_story_transition

pytestmark = pytest.mark.requires_postgres
WORLD_TIME = datetime(2073, 8, 1, 12, tzinfo=timezone.utc)
# table: (subtype key, entity key, subtype table, composite-FK stem)
PAIRS = {
    "character_relationships": (
        ("character1_id", "character1_entity_id", "characters", "character1"),
        ("character2_id", "character2_entity_id", "characters", "character2"),
    ),
    "faction_relationships": (
        ("faction1_id", "faction1_entity_id", "factions", "faction1"),
        ("faction2_id", "faction2_entity_id", "factions", "faction2"),
    ),
    "faction_character_relationships": (
        ("faction_id", "faction_entity_id", "factions", "faction"),
        ("character_id", "character_entity_id", "characters", "character"),
    ),
}
ENTITY_KEYS = [pair[1] for pairs in PAIRS.values() for pair in pairs]


@pytest.fixture
def relationship_db() -> Iterator[str]:
    """Own one fully migrated clone; leave no database after the test."""
    with disposable_slot_database("qa640_836s6a") as dbname:
        yield dbname


def _restore_pre_151_shape(dbname: str) -> None:
    """Remove only named 151 additions and strip their ledger keys on the clone."""
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        for table, pairs in PAIRS.items():
            cur.execute(f"DROP TRIGGER trg_{table}_entity_ids ON public.{table}")
            for _, _, _, stem in pairs:
                cur.execute(
                    f"ALTER TABLE public.{table} DROP CONSTRAINT "
                    f"{table}_{stem}_entity_fkey"
                )
            for _, entity_key, _, _ in pairs:
                cur.execute(f"ALTER TABLE public.{table} DROP COLUMN {entity_key}")
        cur.execute("DROP FUNCTION public.fn_relationship_entity_ids()")
        cur.execute(
            "ALTER TABLE public.characters DROP CONSTRAINT characters_id_entity_id_key"
        )
        cur.execute(
            "ALTER TABLE public.factions DROP CONSTRAINT factions_id_entity_id_key"
        )
        cur.execute(
            "UPDATE relationship_versions SET old_row = old_row - %s::text[]",
            (ENTITY_KEYS,),
        )
        cur.execute("DELETE FROM schema_migrations WHERE version = '151'")
        assert cur.rowcount == 1


def _snapshot(dbname: str) -> dict[str, Any]:
    """Read complete row multisets and ledger identities without changing them."""
    result: dict[str, Any] = {}
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        for table in PAIRS:
            cur.execute(f"SELECT to_jsonb(r) FROM public.{table} r")
            result[table] = [row[0] for row in cur.fetchall()]
        cur.execute("SELECT to_jsonb(v) FROM relationship_versions v ORDER BY id")
        result["versions"] = [row[0] for row in cur.fetchall()]
        cur.execute("SELECT count(*), max(id) FROM relationship_versions")
        result["ledger_identity"] = tuple(cur.fetchone())
    return result


def _without_entity_keys(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in ENTITY_KEYS}


def _multiset(rows: list[dict[str, Any]]) -> list[str]:
    return sorted(json.dumps(row, sort_keys=True) for row in rows)


def _assert_parity(before: dict[str, Any], after: dict[str, Any]) -> None:
    """Fail on changed original values, dropped/extra rows or a new ledger id."""
    for table in PAIRS:
        assert _multiset(before[table]) == _multiset(
            [_without_entity_keys(row) for row in after[table]]
        ), table
    assert after["ledger_identity"] == before["ledger_identity"]
    assert before["versions"] == [
        {**row, "old_row": _without_entity_keys(row["old_row"])}
        for row in after["versions"]
    ]


def _assert_entity_mapping(dbname: str) -> None:
    """Every live and ledger identity must agree with the current subtype row."""
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        subtypes = {}
        for subtype in ("characters", "factions"):
            cur.execute(f"SELECT id, entity_id FROM public.{subtype}")
            subtypes[subtype] = dict(cur.fetchall())
    snapshot = _snapshot(dbname)
    for table, pairs in PAIRS.items():
        rows = snapshot[table] + [
            version["old_row"]
            for version in snapshot["versions"]
            if version["relationship_table"] == table
        ]
        for row in rows:
            for subtype_key, entity_key, subtype, _ in pairs:
                assert row[entity_key] == subtypes[subtype][row[subtype_key]], row


def _assert_version_triggers_enabled(dbname: str) -> None:
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        for table in PAIRS:
            cur.execute(
                "SELECT tgenabled FROM pg_trigger WHERE tgrelid = %s::regclass "
                "AND tgname = %s",
                (f"public.{table}", f"trg_version_{table}"),
            )
            assert cur.fetchall() == [("O",)]


def _seed_all_relationships(dbname: str) -> CharacterPairSeed:
    """Use real seed writers, plus the ordered direct faction relationship INSERT."""
    pair = seed_character_pair(
        dbname,
        world_time=WORLD_TIME,
        actor_name="Identity Actor",
        target_name="Identity Target",
    )
    seed_relationship(
        dbname,
        subject_character_id=pair.actor_character_id,
        object_character_id=pair.target_character_id,
        relationship_type="ally",
    )
    first, _ = seed_faction(dbname, name="Identity Guild")
    second, _ = seed_faction(dbname, name="Identity League")
    assert first < second
    for character in (pair.actor_character_id, pair.target_character_id):
        seed_faction_membership(
            dbname, character_id=character, faction_id=first, role="member"
        )
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("SET LOCAL nexus.write_producer = 'manual'")
        cur.execute(
            "INSERT INTO faction_relationships "
            "(faction1_id, faction2_id, relationship_type) "
            "VALUES (%s, %s, 'alliance')",
            (first, second),
        )
    return pair


def test_backfill_and_rewrite_parity(relationship_db: str) -> None:
    """Fails if backfill versions rows or the rewrite drops any original key/value."""
    pair = _seed_all_relationships(relationship_db)
    with closing(connect(relationship_db)) as conn, conn, conn.cursor() as cur:
        cur.execute("SET LOCAL nexus.write_producer = 'manual'")
        cur.execute(
            "UPDATE character_relationships SET valence_current = 0.25 "
            "WHERE character1_id = %s AND character2_id = %s",
            (pair.actor_character_id, pair.target_character_id),
        )
        cur.execute(
            "DELETE FROM faction_character_relationships WHERE character_id = %s",
            (pair.target_character_id,),
        )
        assert cur.rowcount == 1
    _restore_pre_151_shape(relationship_db)
    before = _snapshot(relationship_db)
    assert all(before[table] for table in PAIRS)
    assert {row["operation"] for row in before["versions"]} == {
        "insert",
        "update",
        "delete",
    }
    assert migrate.migrate_database(relationship_db, skip_locked=False) == (1, 0)
    _assert_parity(before, _snapshot(relationship_db))
    _assert_entity_mapping(relationship_db)
    _assert_version_triggers_enabled(relationship_db)


def test_empty_backfill_preserves_null_ledger_max(relationship_db: str) -> None:
    """Fails if an empty ledger cannot migrate or gains a version row or maximum."""
    _restore_pre_151_shape(relationship_db)
    before = _snapshot(relationship_db)
    assert before["ledger_identity"] == (0, None)
    assert migrate.migrate_database(relationship_db, skip_locked=False) == (1, 0)
    _assert_parity(before, _snapshot(relationship_db))
    _assert_version_triggers_enabled(relationship_db)


def test_writers_fill_entity_ids(relationship_db: str) -> None:
    """Fails with NOT NULL if any of the three writer shapes loses the fill trigger."""
    _seed_all_relationships(relationship_db)
    snapshot = _snapshot(relationship_db)
    assert all(snapshot[table] for table in PAIRS)
    assert {row["relationship_table"] for row in snapshot["versions"]} == set(PAIRS)
    assert all(row["operation"] == "insert" for row in snapshot["versions"])
    _assert_entity_mapping(relationship_db)


def test_entity_ids_cannot_diverge(relationship_db: str) -> None:
    """Fails if supplied IDs are overwritten, pairs diverge or FK identity is lost."""
    pair = seed_character_pair(
        relationship_db,
        world_time=WORLD_TIME,
        actor_name="Pair Actor",
        target_name="Pair Target",
    )
    third, third_entity = seed_character(relationship_db, name="Pair Replacement")
    with pytest.raises(ForeignKeyViolation) as insert_error:
        with closing(connect(relationship_db)) as conn, conn, conn.cursor() as cur:
            cur.execute("SET LOCAL nexus.write_producer = 'manual'")
            cur.execute(
                "INSERT INTO character_relationships "
                "(character1_id, character2_id, character1_entity_id, "
                "relationship_type) "
                "VALUES (%s, %s, %s, 'ally')",
                (pair.actor_character_id, pair.target_character_id, third_entity),
            )
    assert (
        insert_error.value.diag.constraint_name
        == "character_relationships_character1_entity_fkey"
    )
    seed_relationship(
        relationship_db,
        subject_character_id=pair.actor_character_id,
        object_character_id=pair.target_character_id,
        relationship_type="ally",
    )
    with pytest.raises(ForeignKeyViolation) as update_error:
        with closing(connect(relationship_db)) as conn, conn, conn.cursor() as cur:
            cur.execute("SET LOCAL nexus.write_producer = 'manual'")
            cur.execute(
                "UPDATE character_relationships SET character2_entity_id = %s",
                (third_entity,),
            )
    assert (
        update_error.value.diag.constraint_name
        == "character_relationships_character2_entity_fkey"
    )
    with closing(connect(relationship_db)) as conn, conn, conn.cursor() as cur:
        cur.execute("SET LOCAL nexus.write_producer = 'manual'")
        cur.execute(
            "UPDATE character_relationships SET character1_id = %s "
            "RETURNING character1_entity_id",
            (third,),
        )
        assert cur.fetchall() == [(third_entity,)]
        cur.execute("SELECT max(id) + 1 FROM characters")
        absent = cur.fetchone()[0]
    with pytest.raises(
        ForeignKeyViolation, match="names no characters row"
    ) as missing_error:
        with closing(connect(relationship_db)) as conn, conn, conn.cursor() as cur:
            cur.execute("SET LOCAL nexus.write_producer = 'manual'")
            cur.execute(
                "INSERT INTO character_relationships "
                "(character1_id, character2_id, relationship_type) "
                "VALUES (%s, %s, 'ally')",
                (absent, pair.target_character_id),
            )
    assert (
        missing_error.value.diag.constraint_name
        == "character_relationships_character1_entity_fkey"
    )
    _assert_entity_mapping(relationship_db)


def test_migration_151_refuses_stale_ledger(
    relationship_db: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Fails without the guard: a real reset reuses subtype IDs for new entities."""
    pair = seed_character_pair(
        relationship_db,
        world_time=WORLD_TIME,
        actor_name="Old Actor",
        target_name="Old Target",
    )
    seed_relationship(
        relationship_db,
        subject_character_id=pair.actor_character_id,
        object_character_id=pair.target_character_id,
        relationship_type="ally",
    )
    old = {
        pair.actor_character_id: pair.actor_entity_id,
        pair.target_character_id: pair.target_entity_id,
    }
    _restore_pre_151_shape(relationship_db)
    transition = _build_story_transition(relationship_db)
    NewStoryDatabaseMapper(dbname=relationship_db).perform_transition(transition)
    with closing(connect(relationship_db)) as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM characters")
        current = {row[0] for row in cur.fetchall()}
    while not set(old).issubset(current):
        new_id, _ = seed_character(
            relationship_db, name=f"Reset replacement {len(current)}"
        )
        current.add(new_id)
        assert new_id <= max(old), "reset did not reuse the expected subtype ids"
    with closing(connect(relationship_db)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, entity_id FROM characters WHERE id = ANY(%s)", (list(old),)
        )
        replacements = dict(cur.fetchall())
    assert set(replacements) == set(old)
    assert all(replacements[key] != entity for key, entity in old.items())
    before = _snapshot(relationship_db)
    assert migrate.migrate_database(relationship_db, skip_locked=False) == (0, 1)
    assert "FAILED: 151_relationship_entity_ids" in caplog.text
    assert "refusing to map them to entity ids" in caplog.text
    assert _snapshot(relationship_db) == before
    with closing(connect(relationship_db)) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM schema_migrations WHERE version = '151'")
        assert cur.fetchone()[0] == 0
        for table, pairs in PAIRS.items():
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s",
                (table,),
            )
            assert not {pair[1] for pair in pairs}.intersection(
                row[0] for row in cur.fetchall()
            )
    assert all(
        not set(ENTITY_KEYS).intersection(row["old_row"]) for row in before["versions"]
    )


def _strip_checkpoint_entity_keys(cur: Any, checkpoint_id: int) -> None:
    cur.execute("SELECT state FROM state_checkpoints WHERE id = %s", (checkpoint_id,))
    state = cur.fetchone()[0]
    assert state["character_relationships"]
    for table in PAIRS:
        state[table] = [_without_entity_keys(row) for row in state[table]]
    cur.execute(
        "UPDATE state_checkpoints SET state = %s::jsonb WHERE id = %s",
        (json.dumps(state), checkpoint_id),
    )


@pytest.mark.parametrize("legacy_side", ["genesis", "interval"])
def test_verify_skips_entity_ids_absent_from_old_checkpoints(
    relationship_db: str, legacy_side: str
) -> None:
    """Fails on character1_entity_id drift when absent checkpoint keys become NULL."""
    story = seed_checkpointed_story(relationship_db)
    if legacy_side == "genesis":
        with closing(connect(relationship_db)) as conn, conn, conn.cursor() as cur:
            _strip_checkpoint_entity_keys(cur, story.genesis_checkpoint_id)
            target = capture_state_checkpoint_sync(
                cur, chunk_id=story.head_chunk_id, label="manual"
            )
    else:
        chunk = seed_committed_chunk(
            relationship_db, raw_text="The same relationships endure.", scene=2
        )
        with closing(connect(relationship_db)) as conn, conn, conn.cursor() as cur:
            target = capture_state_checkpoint_sync(
                cur, chunk_id=chunk, label="interval"
            )
            assert target is not None
            _strip_checkpoint_entity_keys(cur, target)
    assert target is not None
    with closing(connect(relationship_db)) as conn, conn.cursor() as cur:
        verdicts = verify_checkpoints_sync(cur)
    assert len(verdicts) == 1
    verdict = verdicts[0]
    assert (verdict.base_checkpoint_id, verdict.target_checkpoint_id) == (
        story.genesis_checkpoint_id,
        target,
    )
    assert verdict.drifts == []
    assert verdict.skipped_unreproducible >= 4


@pytest.mark.requires_corpus
@pytest.mark.parametrize("source", ["save_01", "save_02", "save_03", "save_04"])
def test_fleet_backfill_parity(source: str) -> None:
    """Fails on an incorrect live/ledger mapping or drift in an owned full clone."""
    with disposable_slot_database(
        "qa640_836s6a", source_db=source, include_data=True
    ) as dbname:
        _assert_entity_mapping(dbname)
        _assert_version_triggers_enabled(dbname)
        if source in {"save_03", "save_04"}:
            with closing(connect(dbname)) as conn, conn.cursor() as cur:
                verdicts = verify_checkpoints_sync(cur)
            assert verdicts, "the corpus clone has no checkpoint pair to verify"
            assert all(not verdict.drifts for verdict in verdicts), verdicts
