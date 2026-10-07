"""Unified chunk entity references: backfill, trigger sync, and limits (#836 S3).

Migration 148 creates ``chunk_entity_references``, fills it from the three
chunk junctions, and installs row triggers that mirror every junction write
into it and forget a subtype's rows when the subtype row is deleted. These
tests run on disposable clones from ``tests.pg_fixtures`` (migrated through
the runner, so migration 148 is applied) and seed references through the
production writer ``nexus.presence.roster.write_roster`` wherever it reaches
the case. Parity is read by ``scripts/entity_reference_parity.py`` with
``--target chunk_entity_references``, run as the shell runs it. No owner
database is written; the fleet test reads owner corpora only through the
read-only pg_dump of ``disposable_slot_database(include_data=True)``.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, NamedTuple

import psycopg2
import psycopg2.errors
import pytest

from nexus.api.db_pool import close_all_pools
from nexus.api.new_story_db_mapper import NewStoryDatabaseMapper
from nexus.presence.roster import PresenceRoster, RosterEntry, write_roster
from scripts import entity_reference_parity as parity
from scripts import migrate
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    seed_character,
    seed_committed_chunk,
    seed_faction,
    seed_place,
    seed_protagonist,
    seed_zone,
)

pytestmark = pytest.mark.requires_postgres

REPO_ROOT = Path(__file__).resolve().parents[1]
UNIFIED_TABLE = "chunk_entity_references"
CLONE_PREFIX = "qa640_836s3"
FLEET_SOURCES = ("save_01", "save_02", "save_03", "save_04")
KINDS = ("character", "place", "faction")
# Every object migration 148 creates, dropped one by one to rerun it.
MIGRATION_148_DROPS = (
    "DROP TRIGGER trg_chunk_character_references_mirror "
    "ON public.chunk_character_references",
    "DROP TRIGGER trg_chunk_faction_references_mirror "
    "ON public.chunk_faction_references",
    "DROP TRIGGER trg_place_chunk_references_mirror ON public.place_chunk_references",
    "DROP TRIGGER trg_characters_forget_chunk_references ON public.characters",
    "DROP TRIGGER trg_factions_forget_chunk_references ON public.factions",
    "DROP TRIGGER trg_places_forget_chunk_references ON public.places",
    "DROP FUNCTION public.chunk_character_references_mirror()",
    "DROP FUNCTION public.chunk_faction_references_mirror()",
    "DROP FUNCTION public.place_chunk_references_mirror()",
    "DROP FUNCTION public.chunk_entity_references_forget_subtype()",
    "DROP INDEX public.chunk_entity_references_entity_idx",
    "DROP INDEX public.chunk_entity_references_place_role_key",
    "DROP INDEX public.chunk_entity_references_single_role_key",
    "DROP TABLE public.chunk_entity_references",
    "ALTER TABLE public.entities DROP CONSTRAINT entities_id_kind_key",
    "DROP TYPE public.chunk_reference_kind",
)


class Ref(NamedTuple):
    """One seeded subtype row: its kind, subtype ID, entity ID, and name."""

    kind: str
    id: int
    entity_id: int
    name: str

    def entry(self, evidence: str | None = None) -> RosterEntry:
        """Return the roster entry the production writer persists."""
        return RosterEntry(
            kind=self.kind, id=self.id, name=self.name, evidence=evidence
        )


def _seed_story(dbname: str) -> Ref:
    """Give a fresh clone a zone and a bound player; return the player."""
    seed_zone(
        dbname,
        name="Fixture Zone",
        min_longitude=-74.1,
        min_latitude=40.6,
        max_longitude=-73.8,
        max_latitude=40.9,
    )
    player_id, player_entity_id = seed_protagonist(dbname)
    return Ref("character", player_id, player_entity_id, "Fixture Player")


@pytest.fixture(scope="module")
def story() -> Iterator[tuple[str, Ref]]:
    """Yield one seeded clone shared by the tests that keep parity."""
    with disposable_slot_database(CLONE_PREFIX) as dbname:
        yield dbname, _seed_story(dbname)


def _place(dbname: str, name: str) -> Ref:
    place_id, entity_id = seed_place(dbname, name=name)
    return Ref("place", place_id, entity_id, name)


def _character(dbname: str, name: str) -> Ref:
    character_id, entity_id = seed_character(dbname, name=name)
    return Ref("character", character_id, entity_id, name)


def _faction(dbname: str, name: str) -> Ref:
    faction_id, entity_id = seed_faction(dbname, name=name)
    return Ref("faction", faction_id, entity_id, name)


def _seed_kind(dbname: str, kind: str, name: str) -> Ref:
    return {"character": _character, "place": _place, "faction": _faction}[kind](
        dbname, name
    )


def _chunk(dbname: str, label: str) -> int:
    """Seed one committed chunk on the next free scene of S01E01."""
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(max(scene), 0) + 1 FROM chunk_metadata "
            "WHERE season = 1 AND episode = 1"
        )
        scene = int(cur.fetchone()[0])
    return seed_committed_chunk(dbname, raw_text=label, scene=scene)


def _write(
    dbname: str,
    chunk_id: int,
    *,
    present: Sequence[RosterEntry] = (),
    setting: Sequence[RosterEntry] = (),
    transitioning: Sequence[RosterEntry] = (),
    referenced: Sequence[RosterEntry] = (),
) -> None:
    """Commit one roster through the production junction writer."""
    roster = PresenceRoster(
        present={entry.key: entry for entry in present},
        setting={entry.key: entry for entry in setting},
        transitioning={entry.key: entry for entry in transitioning},
        referenced={entry.key: entry for entry in referenced},
    )
    with closing(connect(dbname)) as conn, conn:
        write_roster(conn, chunk_id, roster)


def _execute(dbname: str, statement: str, params: Sequence[Any] = ()) -> int:
    """Run one statement in its own committed transaction; return rowcount."""
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(statement, params)
        return int(cur.rowcount)


def _unified_rows(dbname: str, entity_id: int) -> list[tuple[Any, ...]]:
    """Read one entity's unified rows in a stable order."""
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT chunk_id, entity_id, entity_kind::text, reference_kind::text, "
            f"evidence FROM {UNIFIED_TABLE} WHERE entity_id = %s ORDER BY 1, 4",
            (entity_id,),
        )
        return list(cur.fetchall())


def _run_parity(dbname: str) -> tuple[int, dict[str, Any]]:
    """Run the parity script against the unified table as the shell does."""
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "entity_reference_parity.py"),
            "--dbname",
            dbname,
            "--target",
            UNIFIED_TABLE,
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )
    assert result.returncode in (0, parity.EXIT_MISMATCH), result.stderr
    return result.returncode, json.loads(result.stdout)


def _assert_parity(dbname: str) -> dict[str, Any]:
    """Require exit 0 on every unified column, with the faction rule stated."""
    status, report = _run_parity(dbname)
    assert status == 0, json.dumps(report["kinds"], indent=2)
    assert report["target"]["relation"] == f"public.{UNIFIED_TABLE}"
    assert report["target"]["columns"] == [
        "chunk_id",
        "entity_id",
        "entity_kind",
        "reference_kind",
        "evidence",
    ]
    assert report["compared_columns"] == list(parity.EXPECTED_COLUMNS)
    assert all(block["carried"] for block in report["columns"].values())
    assert report["normalizations"] == {
        "faction_reference": parity.FACTION_UNIFIED_REFERENCE
    }
    return report


def test_writer_rows_mirror_with_parity(story: tuple[str, Ref]) -> None:
    """Every production write of the three junctions lands in the unified table.

    Fails if any junction trigger is missing or mirrors the wrong key: a
    missing insert branch leaves rows missing, a missing delete branch leaves
    the deleted faction row extra, and a place key without the role merges
    the two roles of one place.
    """
    dbname, player = story
    plaza = _place(dbname, "Mirror Plaza")
    docks = _place(dbname, "Mirror Docks")
    tower = _place(dbname, "Mirror Tower")
    mara = _character(dbname, "Mirror Mara")
    wardens = _faction(dbname, "Mirror Wardens")
    couriers = _faction(dbname, "Mirror Couriers")
    chunk_id = _chunk(dbname, "Mirror chunk.")

    # One place with two roles (setting with evidence, transit with evidence),
    # one place without evidence, a mentioned character, two factions.
    _write(
        dbname,
        chunk_id,
        present=[player.entry()],
        setting=[plaza.entry("Lamps ring the plaza.")],
        transitioning=[plaza.entry("The player crosses the plaza.")],
        referenced=[mara.entry(), docks.entry(), wardens.entry(), couriers.entry()],
    )
    # The roster refuses two setting places (roster.py:410-411), and the
    # writer only upserts (roster.py:448): a second roster on the same chunk
    # with a different single setting place gives the chunk two of them.
    _write(dbname, chunk_id, setting=[tower.entry()])
    report = _assert_parity(dbname)
    assert {kind: report["kinds"][kind]["target"] for kind in KINDS} == {
        "character": 2,
        "place": 4,
        "faction": 2,
    }
    assert report["invariants"]["target"]["recorded_not_enforced"] == {
        "multi_role_place_pairs": 1,
        "chunks_with_multiple_setting_places": 1,
    }
    assert report["invariants"]["target"]["null_evidence_rows"] == 2
    assert _unified_rows(dbname, plaza.entity_id) == [
        (chunk_id, plaza.entity_id, "place", "setting", "Lamps ring the plaza."),
        (
            chunk_id,
            plaza.entity_id,
            "place",
            "transit",
            "The player crosses the plaza.",
        ),
    ]
    assert _unified_rows(dbname, wardens.entity_id) == [
        (chunk_id, wardens.entity_id, "faction", "mentioned", None)
    ]

    # Mara goes from mentioned to present; the plaza's setting evidence changes.
    _write(
        dbname,
        chunk_id,
        present=[mara.entry()],
        setting=[plaza.entry("The lamps gutter.")],
    )
    _assert_parity(dbname)
    assert _unified_rows(dbname, mara.entity_id) == [
        (chunk_id, mara.entity_id, "character", "present", None)
    ]
    assert _unified_rows(dbname, plaza.entity_id)[0] == (
        chunk_id,
        plaza.entity_id,
        "place",
        "setting",
        "The lamps gutter.",
    )

    # scripts/process_factions.py:218,228: delete a chunk's faction rows,
    # then insert one back.
    assert (
        _execute(
            dbname,
            "DELETE FROM chunk_faction_references WHERE chunk_id = %s",
            (chunk_id,),
        )
        == 2
    )
    _execute(
        dbname,
        "INSERT INTO chunk_faction_references (chunk_id, faction_id) VALUES (%s, %s)",
        (chunk_id, wardens.id),
    )
    report = _assert_parity(dbname)
    assert _unified_rows(dbname, couriers.entity_id) == []
    assert _unified_rows(dbname, wardens.entity_id) == [
        (chunk_id, wardens.entity_id, "faction", "mentioned", None)
    ]


@pytest.mark.parametrize("kind", KINDS)
def test_subtype_delete_forgets_rows_and_keeps_entity(
    story: tuple[str, Ref], kind: str
) -> None:
    """Deleting a subtype row deletes every unified row of its entity.

    The directly inserted row has no junction row, so only the subtype
    table's forget trigger can remove it. Fails if that table's forget
    trigger is missing (the directly inserted row survives).
    """
    dbname, _ = story
    subject = _seed_kind(dbname, kind, f"Forget {kind.title()}")
    referenced_chunk = _chunk(dbname, f"Forget {kind} referenced.")
    direct_chunk = _chunk(dbname, f"Forget {kind} direct.")
    _write(dbname, referenced_chunk, referenced=[subject.entry()])
    _execute(
        dbname,
        f"INSERT INTO {UNIFIED_TABLE} "
        "(chunk_id, entity_id, entity_kind, reference_kind) "
        "VALUES (%s, %s, %s, 'mentioned')",
        (direct_chunk, subject.entity_id, kind),
    )
    assert len(_unified_rows(dbname, subject.entity_id)) == 2

    table = {"character": "characters", "place": "places", "faction": "factions"}
    assert (
        _execute(dbname, f"DELETE FROM {table[kind]} WHERE id = %s", (subject.id,)) == 1
    )

    assert _unified_rows(dbname, subject.entity_id) == []
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT kind::text FROM entities WHERE id = %s", (subject.entity_id,)
        )
        assert cur.fetchall() == [(kind,)]
    _assert_parity(dbname)


def test_subtype_renumber_keeps_rows(story: tuple[str, Ref]) -> None:
    """Renumbering a character keeps its unified rows unchanged.

    The junction's ON UPDATE CASCADE fires the mirror's UPDATE branch while
    the lookup of OLD's characters row misses. Fails if the mirror's UPDATE
    branch raises or deletes when OLD's subtype lookup misses.
    """
    dbname, _ = story
    cast = _character(dbname, "Renumber Cast")
    first = _chunk(dbname, "Renumber first.")
    second = _chunk(dbname, "Renumber second.")
    _write(dbname, first, referenced=[cast.entry()])
    _write(dbname, second, present=[cast.entry()])
    before = _unified_rows(dbname, cast.entity_id)
    assert [row[3] for row in before] == ["mentioned", "present"]

    assert (
        _execute(
            dbname, "UPDATE characters SET id = id + 1000 WHERE id = %s", (cast.id,)
        )
        == 1
    )

    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM chunk_character_references WHERE character_id = %s",
            (cast.id + 1000,),
        )
        assert cur.fetchone()[0] == 2
    assert _unified_rows(dbname, cast.entity_id) == before
    _assert_parity(dbname)


def _refused(
    cur: Any,
    error: type[psycopg2.Error],
    constraint: str,
    statement: str,
    params: Sequence[Any],
) -> None:
    """Require ``statement`` to fail with ``error`` on ``constraint``."""
    cur.execute("SAVEPOINT probe")
    with pytest.raises(error) as caught:
        cur.execute(statement, params)
    cur.execute("ROLLBACK TO SAVEPOINT probe")
    assert caught.value.diag.constraint_name == constraint


def test_per_kind_validity_and_uniqueness(story: tuple[str, Ref]) -> None:
    """The check, the composite foreign key, and the partial keys refuse.

    Fails if ``chunk_entity_references_kind_check`` admits a role outside its
    kind, evidence on a character row, or a NULL place role; if the composite
    foreign key admits a stated kind that differs from ``entities.kind`` or
    lets a referenced entity's kind change; or if either partial unique index
    is missing. It also fails if a NULL character role or a second setting
    place in one chunk is refused.
    """
    dbname, _ = story
    cast = _character(dbname, "Validity Cast")
    extra = _character(dbname, "Validity Extra")
    plaza = _place(dbname, "Validity Plaza")
    annex = _place(dbname, "Validity Annex")
    guild = _faction(dbname, "Validity Guild")
    chunk_id = _chunk(dbname, "Validity chunk.")
    _write(
        dbname,
        chunk_id,
        setting=[plaza.entry("The plaza.")],
        referenced=[cast.entry(), guild.entry()],
    )
    insert = (
        f"INSERT INTO {UNIFIED_TABLE} "
        "(chunk_id, entity_id, entity_kind, reference_kind, evidence) "
        "VALUES (%s, %s, %s, %s, %s)"
    )
    check = "chunk_entity_references_kind_check"
    entity_fkey = "chunk_entity_references_entity_fkey"
    with closing(connect(dbname)) as conn:
        with conn.cursor() as cur:
            for params in (
                (chunk_id, extra.entity_id, "character", "setting", None),
                (chunk_id, annex.entity_id, "place", None, None),
                (chunk_id, guild.entity_id, "faction", "present", None),
                (chunk_id, extra.entity_id, "character", "mentioned", "Seen."),
            ):
                _refused(cur, psycopg2.errors.CheckViolation, check, insert, params)
            _refused(
                cur,
                psycopg2.errors.ForeignKeyViolation,
                entity_fkey,
                insert,
                (chunk_id, extra.entity_id, "place", "setting", None),
            )
            _refused(
                cur,
                psycopg2.errors.ForeignKeyViolation,
                entity_fkey,
                "UPDATE entities SET kind = 'faction' WHERE id = %s",
                (cast.entity_id,),
            )
            _refused(
                cur,
                psycopg2.errors.UniqueViolation,
                "chunk_entity_references_single_role_key",
                insert,
                (chunk_id, cast.entity_id, "character", "present", None),
            )
            _refused(
                cur,
                psycopg2.errors.UniqueViolation,
                "chunk_entity_references_place_role_key",
                insert,
                (chunk_id, plaza.entity_id, "place", "setting", "Again."),
            )
            cur.execute(insert, (chunk_id, extra.entity_id, "character", None, None))
            cur.execute(insert, (chunk_id, annex.entity_id, "place", "setting", None))
            cur.execute(
                f"SELECT count(*) FROM {UNIFIED_TABLE} "
                "WHERE chunk_id = %s AND reference_kind = 'setting'",
                (chunk_id,),
            )
            assert cur.fetchone()[0] == 2
        # The two admitted rows have no junction row; keep the shared clone at
        # parity for the other tests.
        conn.rollback()
    _assert_parity(dbname)


def test_backfill_rebuilds_from_populated_junctions() -> None:
    """Rerunning migration 148 over populated junctions rebuilds the table.

    Fails if the backfill misses a kind (its DO block raises and the runner
    reports the migration unapplied) or if the file is not rerunnable once
    its objects are gone.
    """
    with disposable_slot_database(CLONE_PREFIX) as dbname:
        player = _seed_story(dbname)
        plaza = _place(dbname, "Backfill Plaza")
        docks = _place(dbname, "Backfill Docks")
        mara = _character(dbname, "Backfill Mara")
        wardens = _faction(dbname, "Backfill Wardens")
        chunk_id = _chunk(dbname, "Backfill chunk.")
        _write(
            dbname,
            chunk_id,
            present=[player.entry()],
            setting=[plaza.entry("Lamps ring the plaza.")],
            transitioning=[plaza.entry("Crossing the plaza.")],
            referenced=[mara.entry(), docks.entry(), wardens.entry()],
        )
        before = _assert_parity(dbname)
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            for statement in MIGRATION_148_DROPS:
                cur.execute(statement)
            cur.execute("DELETE FROM schema_migrations WHERE version = '148'")
            assert cur.rowcount == 1

        assert migrate.migrate_database(dbname, skip_locked=False) == (1, 0)

        after = _assert_parity(dbname)
        for kind in KINDS:
            block = after["kinds"][kind]
            assert block["target"] == block["expected"] > 0, kind
            assert block["target"] == before["kinds"][kind]["target"], kind


def test_wizard_reset_clears_unified_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """The wizard's clean slate empties chunk_entity_references.

    Rows naming a character, faction or place are already removed by the
    forget triggers when the reset deletes the subtype rows, so the row that
    shows the reset's own DELETE names an entity with no subtype row, on a
    chunk the reset keeps. Fails without the DELETE of chunk_entity_references
    in perform_transition (the orphan-entity row survives).
    """
    from tests.test_orrery.test_need_clock_anchor_pg import _build_story_transition

    with disposable_slot_database(CLONE_PREFIX) as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=3, dbname=dbname)
        try:
            player = _seed_story(dbname)
            plaza = _place(dbname, "Reset Plaza")
            mara = _character(dbname, "Reset Mara")
            wardens = _faction(dbname, "Reset Wardens")
            chunk_id = _chunk(dbname, "Reset chunk.")
            _write(
                dbname,
                chunk_id,
                present=[player.entry()],
                setting=[plaza.entry("The plaza.")],
                referenced=[mara.entry(), wardens.entry()],
            )
            with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
                cur.execute("INSERT INTO entities (kind) VALUES ('place') RETURNING id")
                (orphan_entity_id,) = cur.fetchone()
                cur.execute(
                    f"INSERT INTO {UNIFIED_TABLE} "
                    "(chunk_id, entity_id, entity_kind, reference_kind) "
                    "VALUES (%s, %s, 'place', 'setting')",
                    (chunk_id, orphan_entity_id),
                )
                cur.execute(f"SELECT count(*) FROM {UNIFIED_TABLE}")
                assert cur.fetchone()[0] == 5

            transition = _build_story_transition(dbname)
            NewStoryDatabaseMapper(dbname=dbname).perform_transition(transition)

            with closing(connect(dbname)) as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM narrative_chunks WHERE id = %s", (chunk_id,)
                )
                assert cur.fetchone()[0] == 1
                cur.execute(f"SELECT count(*) FROM {UNIFIED_TABLE}")
                assert cur.fetchone()[0] == 0
        finally:
            close_all_pools()


@pytest.mark.requires_corpus
@pytest.mark.parametrize("source_db", FLEET_SOURCES)
def test_fleet_backfill_parity(source_db: str) -> None:
    """Migration 148 on a data clone of each corpus slot has exact parity.

    Fails if the backfill or the check differs from the clone's junctions on
    any kind, or if a kind is empty on a corpus that holds references.
    """
    with disposable_slot_database(
        CLONE_PREFIX, source_db=source_db, include_data=True
    ) as dbname:
        report = _assert_parity(dbname)
        for kind in KINDS:
            block = report["kinds"][kind]
            assert block["target"] == block["expected"] > 0, (kind, block)
