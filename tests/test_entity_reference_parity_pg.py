"""Chunk entity reference parity on a seeded, disposable template clone (#836).

The clone holds references of all three kinds written by the production
commit: two turns accepted through ``seed_accepted_turn``, whose commit
writes the chunk junctions through ``nexus.presence.roster.write_roster``.
The second turn references one place as both setting and transit, so one
place holds two roles in one chunk; place references carry evidence in some
rows and none in others. ``tests.pg_fixtures`` owns creation, seeding, and
drop; no owner database is read or written. The invariant-violation test
seeds a second clone of its own, because it changes an entity's kind.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import closing
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, NamedTuple

import psycopg2
import pytest

from scripts import entity_reference_parity as parity
from tests.pg_fixtures import (
    FIXTURE_TURN_CHOICES,
    connect,
    disposable_slot_database,
    seed_accepted_turn,
    seed_character,
    seed_faction,
    seed_place,
    seed_protagonist,
    seed_zone,
)

pytestmark = pytest.mark.requires_postgres

REPO_ROOT = Path(__file__).resolve().parents[1]
UNIFIED_TABLE = "qa836_unified_references"


class SeededStory(NamedTuple):
    """The clone and the IDs its references name."""

    dbname: str
    chunk_ids: list[int]
    plaza_entity_id: int
    docks_entity_id: int


# Seeded reference rows per kind: turn 1 references the player (present) and
# Mara (mentioned), Fixture Plaza (setting, with evidence) and Fixture Docks
# (mentioned, no evidence), and the Wardens; turn 2 references the player,
# Fixture Plaza as setting (no evidence) and as transit (with evidence),
# Fixture Tower (transit, with evidence), and both factions.
SEEDED_ROWS = {"character": 3, "place": 5, "faction": 3}
SEEDED_EVIDENCE_ROWS = 3


def _seed(dbname: str) -> SeededStory:
    """Seed two accepted turns that reference every kind through the commit."""
    seed_zone(
        dbname,
        name="Fixture Zone",
        min_longitude=-74.1,
        min_latitude=40.6,
        max_longitude=-73.8,
        max_latitude=40.9,
    )
    plaza_id, plaza_entity_id = seed_place(dbname, name="Fixture Plaza")
    docks_id, docks_entity_id = seed_place(
        dbname, name="Fixture Docks", longitude=-74.0, latitude=40.7
    )
    tower_id, _ = seed_place(
        dbname, name="Fixture Tower", longitude=-73.95, latitude=40.75
    )
    player_id, _ = seed_protagonist(dbname, current_location=plaza_id)
    mara_id, _ = seed_character(dbname, name="Mara Quill", current_location=docks_id)
    wardens_id, _ = seed_faction(dbname, name="Fixture Wardens")
    couriers_id, _ = seed_faction(dbname, name="Fixture Couriers")
    player = {
        "character_id": player_id,
        "character_name": "Fixture Player",
        "reference_type": "present",
    }
    turns: list[dict[str, Any]] = [
        {
            "storyteller_text": (
                "Fixture turn 1: the player crosses Fixture Plaza while Mara "
                "Quill keeps to the docks."
            ),
            "reference_updates": {
                "characters": [
                    player,
                    {
                        "character_id": mara_id,
                        "character_name": "Mara Quill",
                        "reference_type": "mentioned",
                    },
                ],
                "places": [
                    {
                        "place_id": plaza_id,
                        "reference_type": "setting",
                        "evidence": "Lamps ring the plaza.",
                    },
                    {"place_id": docks_id, "reference_type": "mentioned"},
                ],
                "factions": [{"faction_id": wardens_id}],
            },
        },
        {
            "storyteller_text": (
                "Fixture turn 2: the player cuts back across the plaza toward "
                "the tower as the evening crowd thins."
            ),
            "reference_updates": {
                "characters": [player],
                "places": [
                    {"place_id": plaza_id, "reference_type": "setting"},
                    {
                        "place_id": plaza_id,
                        "reference_type": "transit",
                        "evidence": "The player cuts back across the plaza.",
                    },
                    {
                        "place_id": tower_id,
                        "reference_type": "transit",
                        "evidence": "Heading toward the tower.",
                    },
                ],
                "factions": [
                    {"faction_id": wardens_id},
                    {"faction_id": couriers_id},
                ],
            },
        },
    ]
    chunk_ids: list[int] = []
    user_text = "Begin the story."
    for number, turn in enumerate(turns, start=1):
        chunk_ids.append(
            seed_accepted_turn(
                dbname,
                user_text=user_text,
                storyteller_text=turn["storyteller_text"],
                choices=list(FIXTURE_TURN_CHOICES),
                choice_text=FIXTURE_TURN_CHOICES[0],
                reference_updates=turn["reference_updates"],
                time_delta=timedelta(0) if number == 1 else timedelta(minutes=5),
            )
        )
        user_text = FIXTURE_TURN_CHOICES[0]
    return SeededStory(dbname, chunk_ids, plaza_entity_id, docks_entity_id)


@pytest.fixture(scope="module")
def story() -> Iterator[SeededStory]:
    """Yield one seeded clone shared by this module's read-only checks."""
    with disposable_slot_database("qa640_836_parity") as dbname:
        yield _seed(dbname)


def _junction_counts(dbname: str) -> dict[str, int]:
    """Count each junction directly, independently of the script."""
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT (SELECT count(*) FROM chunk_character_references), "
            "(SELECT count(*) FROM place_chunk_references), "
            "(SELECT count(*) FROM chunk_faction_references)"
        )
        character, place, faction = cur.fetchone()
    return {"character": character, "place": place, "faction": faction}


def _run_cli(dbname: str, *args: str) -> tuple[int, dict[str, Any], str]:
    """Run the script as the shell does; return status, report, and stderr."""
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "entity_reference_parity.py"),
            "--dbname",
            dbname,
            *args,
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )
    assert result.returncode in (0, parity.EXIT_MISMATCH), result.stderr
    return result.returncode, json.loads(result.stdout), result.stderr


def test_view_has_exact_parity_with_the_seeded_junctions(story: SeededStory) -> None:
    """The bridging view matches every seeded reference row, kind by kind."""
    counts = _junction_counts(story.dbname)
    assert counts == SEEDED_ROWS
    assert all(count > 0 for count in counts.values())

    status, report, stderr = _run_cli(story.dbname)

    assert status == 0, report
    assert report["parity"] is True and report["exit_status"] == 0
    assert report["read_only"] is True
    assert report["snapshot"]["isolation"] == "repeatable read"
    assert report["database"] == story.dbname
    assert report["target"] == {
        "relation": "public.chunk_entity_references_v",
        "relkind": "view",
        "columns": ["chunk_id", "entity_id", "reference_type"],
    }
    assert report["compared_columns"] == ["chunk_id", "entity_id", "reference_type"]
    for kind, count in SEEDED_ROWS.items():
        block = report["kinds"][kind]
        assert (block["expected"], block["target"]) == (count, count), kind
        assert block["missing"] == {"count": 0, "examples": []}
        assert block["extra"] == {"count": 0, "examples": []}
        assert block["invariant_violations"]["count"] == 0
        assert block["parity"] is True
    assert report["unattributed"] == {
        "expected": 0,
        "target": 0,
        "missing": {"count": 0, "examples": []},
        "extra": {"count": 0, "examples": []},
        "parity": True,
    }
    assert report["columns"]["kind"]["carried"] is False
    assert report["columns"]["kind"]["expected_non_null"] == sum(SEEDED_ROWS.values())

    invariants = report["invariants"]
    assert invariants["chunk_character_references"]["primary_key"] == {
        "name": "chunk_character_references_pkey",
        "columns": ["chunk_id", "character_id"],
        "definition": "PRIMARY KEY (chunk_id, character_id)",
        "nulls_not_distinct": False,
        "deferrable": False,
        "initially_deferred": False,
    }
    assert invariants["chunk_faction_references"]["primary_key"]["columns"] == [
        "chunk_id",
        "faction_id",
    ]
    assert invariants["chunk_faction_references"]["role_column"] is None
    places = invariants["place_chunk_references"]
    assert places["primary_key"]["columns"] == [
        "place_id",
        "chunk_id",
        "reference_type",
    ]
    assert places["role_column"] == {
        "name": "reference_type",
        "type": "place_reference_type",
        "enum_labels": ["setting", "mentioned", "transit"],
    }
    assert invariants["chunk_character_references"]["role_column"] == {
        "name": "reference",
        "type": "reference_type",
        "enum_labels": ["present", "mentioned"],
    }
    for table in (
        "chunk_character_references",
        "chunk_faction_references",
        "place_chunk_references",
    ):
        block = invariants[table]
        assert (
            block["row_count"]
            == counts[
                {
                    "chunk_character_references": "character",
                    "chunk_faction_references": "faction",
                    "place_chunk_references": "place",
                }[table]
            ]
        )
        assert len(block["foreign_keys"]) == 2
        assert all(
            (fk["on_update"], fk["on_delete"]) == ("CASCADE", "CASCADE")
            for fk in block["foreign_keys"]
        ), block["foreign_keys"]
    assert invariants["target"]["row_count"] == sum(SEEDED_ROWS.values())
    assert invariants["target"]["primary_key"] is None
    assert stderr.splitlines()[-1] == (
        f"INFO {story.dbname} vs public.chunk_entity_references_v: parity"
    )


def test_place_with_two_roles_counts_as_two_rows_and_one_pair(
    story: SeededStory,
) -> None:
    """Setting plus transit for one place in one chunk is two rows, one pair."""
    with closing(connect(story.dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT pcr.reference_type::text FROM place_chunk_references pcr "
            "JOIN places p ON p.id = pcr.place_id "
            "WHERE p.entity_id = %s AND pcr.chunk_id = %s "
            "ORDER BY 1",
            (story.plaza_entity_id, story.chunk_ids[1]),
        )
        roles = [row[0] for row in cur.fetchall()]
    assert roles == ["setting", "transit"]

    report = parity.run(story.dbname)

    places = report["kinds"]["place"]
    assert places["expected"] == places["target"] == SEEDED_ROWS["place"]
    assert places["parity"] is True
    recorded = {
        "multi_role_place_pairs": 1,
        "chunks_with_multiple_setting_places": 0,
    }
    assert (
        report["invariants"]["place_chunk_references"]["recorded_not_enforced"]
        == recorded
    )
    assert report["invariants"]["target"]["recorded_not_enforced"] == recorded


def test_evidence_not_carried_counts_rows_with_evidence(story: SeededStory) -> None:
    """The view drops evidence; the report counts exactly the rows that hold it."""
    with closing(connect(story.dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FILTER (WHERE evidence IS NOT NULL), "
            "count(*) FILTER (WHERE evidence IS NULL) FROM place_chunk_references"
        )
        with_evidence, without_evidence = cur.fetchone()
    assert (with_evidence, without_evidence) == (
        SEEDED_EVIDENCE_ROWS,
        SEEDED_ROWS["place"] - SEEDED_EVIDENCE_ROWS,
    )

    report = parity.run(story.dbname)

    assert report["columns"]["evidence"] == {
        "carried": False,
        "expected_non_null": with_evidence,
        "expected_non_null_by_kind": {
            "character": 0,
            "place": with_evidence,
            "faction": 0,
            "unattributed": 0,
        },
    }
    assert (
        report["invariants"]["place_chunk_references"]["null_evidence_rows"]
        == without_evidence
    )
    assert report["exit_status"] == 0


def _unified_rows(dbname: str) -> list[tuple[Any, ...]]:
    """Read the target table's rows in a stable order."""
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT chunk_id, entity_id, kind::text, reference_type::text, "
            f"evidence FROM {UNIFIED_TABLE} ORDER BY 1, 2, 3, 4"
        )
        return list(cur.fetchall())


def _create_unified_table(
    dbname: str, table: str = UNIFIED_TABLE, key: str = ""
) -> None:
    """Create a unified-shape target table and fill it from the junctions.

    ``key`` is an optional table-constraint clause, such as a unique key.
    """
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            f"""
            CREATE TABLE {table} (
                chunk_id bigint NOT NULL,
                entity_id bigint NOT NULL,
                kind entity_kind NOT NULL,
                reference_type text,
                evidence text
                {key}
            );
            INSERT INTO {table}
            SELECT r.chunk_id, c.entity_id, e.kind, r.reference::text, NULL
            FROM chunk_character_references r
            JOIN characters c ON c.id = r.character_id
            JOIN entities e ON e.id = c.entity_id
            UNION ALL
            SELECT r.chunk_id, f.entity_id, e.kind, NULL, NULL
            FROM chunk_faction_references r
            JOIN factions f ON f.id = r.faction_id
            JOIN entities e ON e.id = f.entity_id
            UNION ALL
            SELECT r.chunk_id, p.entity_id, e.kind, r.reference_type::text,
                   r.evidence
            FROM place_chunk_references r
            JOIN places p ON p.id = r.place_id
            JOIN entities e ON e.id = p.entity_id
            """
        )


def test_unified_table_target_carries_every_column_and_catches_drift(
    story: SeededStory,
) -> None:
    """A table of the unified shape shows parity, then each seeded drift."""
    _create_unified_table(story.dbname)
    status, report, _ = _run_cli(story.dbname, "--target", UNIFIED_TABLE)
    assert status == 0, report
    assert report["compared_columns"] == list(parity.EXPECTED_COLUMNS)
    assert all(block["carried"] for block in report["columns"].values())
    for kind, count in SEEDED_ROWS.items():
        assert report["kinds"][kind]["expected"] == count
        assert report["kinds"][kind]["target"] == count
    # Place rows only, as on the junction.
    assert report["invariants"]["target"]["null_evidence_rows"] == (
        SEEDED_ROWS["place"] - SEEDED_EVIDENCE_ROWS
    )
    recorded = report["invariants"]["place_chunk_references"]["recorded_not_enforced"]
    assert report["invariants"]["target"]["recorded_not_enforced"] == recorded
    columns = list(parity.EXPECTED_COLUMNS)

    # A second copy of one row is one extra row (multiset, not set, parity),
    # and it is neither a second role nor a second setting place.
    plaza_first_setting = (
        story.chunk_ids[0],
        story.plaza_entity_id,
        "place",
        "setting",
        "Lamps ring the plaza.",
    )
    with closing(connect(story.dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO {UNIFIED_TABLE} VALUES (%s, %s, %s, %s, %s)",
            plaza_first_setting,
        )
    status, report, _ = _run_cli(story.dbname, "--target", UNIFIED_TABLE)
    assert status == parity.EXIT_MISMATCH
    places = report["kinds"]["place"]
    assert places["extra"] == {
        "count": 1,
        "examples": [dict(zip(columns, plaza_first_setting))],
    }
    assert places["missing"]["count"] == 0
    assert places["target"] == SEEDED_ROWS["place"] + 1
    assert report["invariants"]["target"]["recorded_not_enforced"] == recorded
    with closing(connect(story.dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            f"DELETE FROM {UNIFIED_TABLE} WHERE ctid = (SELECT ctid FROM "
            f"{UNIFIED_TABLE} WHERE chunk_id = %s AND entity_id = %s "
            "AND reference_type = 'setting' LIMIT 1)",
            plaza_first_setting[:2],
        )
        assert cur.rowcount == 1

    plaza_setting = (
        story.chunk_ids[1],
        story.plaza_entity_id,
        "place",
        "setting",
        None,
    )
    plaza_transit = (
        story.chunk_ids[1],
        story.plaza_entity_id,
        "place",
        "transit",
        "The player cuts back across the plaza.",
    )
    rows = _unified_rows(story.dbname)
    assert plaza_setting in rows and plaza_transit in rows
    assert rows.count(plaza_first_setting) == 1

    # One deleted row is one missing row, attributed to its kind.
    with closing(connect(story.dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            f"DELETE FROM {UNIFIED_TABLE} WHERE chunk_id = %s AND entity_id = %s "
            "AND reference_type = 'transit'",
            (story.chunk_ids[1], story.plaza_entity_id),
        )
        assert cur.rowcount == 1
    status, report, _ = _run_cli(story.dbname, "--target", UNIFIED_TABLE)
    assert status == parity.EXIT_MISMATCH
    assert report["parity"] is False
    places = report["kinds"]["place"]
    assert places["missing"] == {
        "count": 1,
        "examples": [dict(zip(columns, plaza_transit))],
    }
    assert places["extra"] == {"count": 0, "examples": []}
    assert report["kinds"]["character"]["parity"] is True
    assert report["kinds"]["faction"]["parity"] is True

    # Restore it; one changed role is one missing and one extra row.
    with closing(connect(story.dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO {UNIFIED_TABLE} VALUES (%s, %s, %s, %s, %s)",
            plaza_transit,
        )
        cur.execute(
            f"UPDATE {UNIFIED_TABLE} SET reference_type = 'mentioned' "
            "WHERE chunk_id = %s AND entity_id = %s AND reference_type = 'setting'",
            (story.chunk_ids[1], story.plaza_entity_id),
        )
        assert cur.rowcount == 1
    status, report, _ = _run_cli(story.dbname, "--target", UNIFIED_TABLE)
    assert status == parity.EXIT_MISMATCH
    places = report["kinds"]["place"]
    assert places["missing"] == {
        "count": 1,
        "examples": [dict(zip(columns, plaza_setting))],
    }
    assert places["extra"] == {
        "count": 1,
        "examples": [dict(zip(columns, (*plaza_setting[:3], "mentioned", None)))],
    }
    assert places["expected"] == places["target"] == SEEDED_ROWS["place"]

    # Both drifts at once: the deletion and the role change add up.
    with closing(connect(story.dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            f"DELETE FROM {UNIFIED_TABLE} WHERE chunk_id = %s AND entity_id = %s "
            "AND reference_type = 'transit'",
            (story.chunk_ids[1], story.plaza_entity_id),
        )
        assert cur.rowcount == 1
    status, report, _ = _run_cli(
        story.dbname, "--target", UNIFIED_TABLE, "--limit", "1"
    )
    assert status == parity.EXIT_MISMATCH
    places = report["kinds"]["place"]
    assert (places["missing"]["count"], places["extra"]["count"]) == (2, 1)
    assert len(places["missing"]["examples"]) == 1
    assert places["target"] == SEEDED_ROWS["place"] - 1


def test_connection_helper_refuses_writes(story: SeededStory) -> None:
    """A write through the script's own connection fails as read-only."""
    with closing(parity.open_read_only_connection(story.dbname)) as conn:
        with conn.cursor() as cur:
            cur.execute("SHOW transaction_read_only")
            assert cur.fetchone() == ("on",)
            cur.execute("SHOW search_path")
            assert cur.fetchone() == (parity.SEARCH_PATH,)
            with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
                cur.execute(
                    "DELETE FROM chunk_faction_references WHERE chunk_id = %s",
                    (story.chunk_ids[0],),
                )
        conn.rollback()
        with conn.cursor() as cur:
            with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
                cur.execute("CREATE TABLE qa836_write_probe (id int)")
        conn.rollback()
    assert _junction_counts(story.dbname) == SEEDED_ROWS


def test_report_refuses_a_session_that_is_not_read_only_repeatable_read(
    story: SeededStory,
) -> None:
    """The report reads its session state back instead of asserting it."""
    with closing(connect(story.dbname)) as conn:
        with pytest.raises(
            RuntimeError,
            match="transaction_read_only='off', "
            "transaction_isolation='read committed'",
        ):
            parity.build_report(conn, parity.DEFAULT_TARGET, 1)
        conn.rollback()
        conn.set_session(readonly=True)
        with pytest.raises(
            RuntimeError,
            match="transaction_read_only='on', "
            "transaction_isolation='read committed'",
        ):
            parity.build_report(conn, parity.DEFAULT_TARGET, 1)
        conn.rollback()


def test_unique_constraints_report_their_null_semantics(story: SeededStory) -> None:
    """A unified key reads differently with and without NULLS NOT DISTINCT.

    Faction rows have no role, so ``(chunk_id, entity_id, reference_type)``
    reproduces the faction junction's key only when its NULLs are not
    distinct; the invariant block must tell the two keys apart.
    """
    key_columns = "(chunk_id, entity_id, reference_type)"
    variants = {
        "qa836_key_nulls_distinct": f"UNIQUE {key_columns}",
        "qa836_key_nulls_not_distinct": f"UNIQUE NULLS NOT DISTINCT {key_columns}",
        "qa836_key_deferrable": f"UNIQUE {key_columns} DEFERRABLE INITIALLY DEFERRED",
    }
    blocks: dict[str, dict[str, Any]] = {}
    for table, clause in variants.items():
        _create_unified_table(story.dbname, table, f", CONSTRAINT {table}_key {clause}")
        report = parity.run(story.dbname, table)
        assert report["parity"] is True, table
        target = report["invariants"]["target"]
        assert target["unique_indexes"] == []
        (blocks[table],) = target["unique_constraints"]

    assert blocks["qa836_key_nulls_distinct"] == {
        "name": "qa836_key_nulls_distinct_key",
        "columns": ["chunk_id", "entity_id", "reference_type"],
        "definition": f"UNIQUE {key_columns}",
        "nulls_not_distinct": False,
        "deferrable": False,
        "initially_deferred": False,
    }
    assert blocks["qa836_key_nulls_not_distinct"] == {
        "name": "qa836_key_nulls_not_distinct_key",
        "columns": ["chunk_id", "entity_id", "reference_type"],
        "definition": f"UNIQUE NULLS NOT DISTINCT {key_columns}",
        "nulls_not_distinct": True,
        "deferrable": False,
        "initially_deferred": False,
    }
    assert blocks["qa836_key_deferrable"] == {
        "name": "qa836_key_deferrable_key",
        "columns": ["chunk_id", "entity_id", "reference_type"],
        "definition": f"UNIQUE {key_columns} DEFERRABLE INITIALLY DEFERRED",
        "nulls_not_distinct": False,
        "deferrable": True,
        "initially_deferred": True,
    }

    # The difference is real: only the NULLS NOT DISTINCT key refuses a
    # second copy of a role-less faction row.
    with closing(connect(story.dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "SELECT chunk_id, entity_id FROM qa836_key_nulls_distinct "
            "WHERE kind = 'faction' ORDER BY 1, 2 LIMIT 1"
        )
        faction_row = cur.fetchone()
        cur.execute(
            "INSERT INTO qa836_key_nulls_distinct "
            "VALUES (%s, %s, 'faction', NULL, NULL)",
            faction_row,
        )
    with closing(connect(story.dbname)) as conn:
        with pytest.raises(psycopg2.errors.UniqueViolation):
            with conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO qa836_key_nulls_not_distinct "
                    "VALUES (%s, %s, 'faction', NULL, NULL)",
                    faction_row,
                )


def test_kind_mismatch_and_unattributed_rows_fail_the_run() -> None:
    """Each invariant violation is reported once and fails the run.

    No production writer gives an entity a kind that differs from its subtype
    table, or writes a reference to an absent entity, so this test plants both
    directly on a second clone: ``entities`` has no trigger or check on
    ``kind``. It also shows that a plain unique index on the target stays in
    the invariant block when another table's foreign key references it.
    """
    with disposable_slot_database("qa640_836_parity") as dbname:
        seeded = _seed(dbname)
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM place_chunk_references r "
                "JOIN places p ON p.id = r.place_id WHERE p.entity_id = %s",
                (seeded.docks_entity_id,),
            )
            (docks_rows,) = cur.fetchone()
            assert docks_rows == 1
            # Work order 836-S3: migration 148's chunk_entity_references names
            # the Docks entity through a composite foreign key to
            # entities(id, kind), which refuses the kind change below while a
            # row names it. Delete the Docks entity's mirrored rows first; the
            # report under test reads the junctions and the view, not the table.
            cur.execute(
                "DELETE FROM chunk_entity_references WHERE entity_id = %s",
                (seeded.docks_entity_id,),
            )
            assert cur.rowcount == docks_rows
            cur.execute(
                "UPDATE entities SET kind = 'faction' WHERE id = %s",
                (seeded.docks_entity_id,),
            )
            assert cur.rowcount == 1

        status, report, _ = _run_cli(dbname)

        assert status == parity.EXIT_MISMATCH
        assert report["parity"] is False
        places = report["kinds"]["place"]
        mismatch = places["invariant_violations"]["by_reason"]
        assert mismatch["entity_kind_mismatch"]["count"] == docks_rows
        assert mismatch["subtype_has_no_entity"]["count"] == 0
        assert places["invariant_violations"]["count"] == docks_rows
        assert places["parity"] is False
        # Filed under its entity's kind on both sides: no missing or extra row.
        assert places["expected"] == places["target"] == SEEDED_ROWS["place"] - 1
        factions = report["kinds"]["faction"]
        assert factions["expected"] == factions["target"] == SEEDED_ROWS["faction"] + 1
        for kind in SEEDED_ROWS:
            block = report["kinds"][kind]
            assert block["missing"]["count"] == 0, kind
            assert block["extra"]["count"] == 0, kind
        assert report["unattributed"]["expected"] == 0
        assert report["unattributed"]["target"] == 0
        # Not-carried counts use the same attribution: the Docks row counts
        # under its entity's kind (faction), not under its junction (place).
        assert report["columns"]["reference_type"]["expected_non_null_by_kind"] == {
            "character": SEEDED_ROWS["character"],
            "place": SEEDED_ROWS["place"] - docks_rows,
            "faction": docks_rows,
            "unattributed": 0,
        }

        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE entities SET kind = 'place' WHERE id = %s",
                (seeded.docks_entity_id,),
            )
        _create_unified_table(dbname)
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                f"CREATE UNIQUE INDEX qa836_unified_key ON {UNIFIED_TABLE} "
                "(chunk_id, entity_id, reference_type)"
            )
            cur.execute(
                "CREATE TABLE qa836_referrer (chunk_id bigint, entity_id bigint, "
                "reference_type text, FOREIGN KEY (chunk_id, entity_id, "
                f"reference_type) REFERENCES {UNIFIED_TABLE} "
                "(chunk_id, entity_id, reference_type))"
            )
        status, report, _ = _run_cli(dbname, "--target", UNIFIED_TABLE)
        assert status == 0, report
        assert [
            (index["name"], index["nulls_not_distinct"])
            for index in report["invariants"]["target"]["unique_indexes"]
        ] == [("qa836_unified_key", False)]

        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT max(id) + 1000 FROM entities")
            (absent_entity_id,) = cur.fetchone()
            cur.execute(
                f"INSERT INTO {UNIFIED_TABLE} VALUES (%s, %s, 'place', 'mentioned', "
                "NULL)",
                (seeded.chunk_ids[0], absent_entity_id),
            )

        status, report, _ = _run_cli(dbname, "--target", UNIFIED_TABLE)

        assert status == parity.EXIT_MISMATCH
        assert report["parity"] is False
        assert report["unattributed"]["target"] == 1
        assert report["unattributed"]["extra"]["count"] == 1
        assert report["unattributed"]["missing"]["count"] == 0
        assert report["unattributed"]["parity"] is False
        for kind in SEEDED_ROWS:
            assert report["kinds"][kind]["parity"] is True, kind
