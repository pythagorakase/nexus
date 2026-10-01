"""Migration 139 widens the character_relationships ids to bigint (issue #836).

Every case runs on a disposable ``qa640_836s2_*`` clone of ``NEXUS_template``
made through ``tests/pg_fixtures.py``. A clone runs pending migrations when it
is made, so 139 has already applied when a test body starts. Cases that need
the pre-139 shape rebuild it inside the clone (views dropped, ids altered back
to ``integer``, views and comments recreated from the clone's own catalog),
delete the ``139`` stamp, and rerun the real ``scripts/migrate.py`` runner. No
save slot or template is written.
"""

from __future__ import annotations

import logging
from contextlib import closing
from datetime import datetime, timezone
from typing import Any

import pytest

from scripts import migrate
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    seed_character_pair,
    seed_relationship,
)

pytestmark = pytest.mark.requires_postgres

MIGRATION = "139_character_relationship_bigint_ids"
INT4_MAX = 2147483647
WORLD_TIME = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)

PAIRS = "character_relationship_pairs"
SUMMARY = "character_relationship_summary"
EDGES = "entity_relationships_v"
# Drop order: a dependent view before the view it reads.
VIEWS_DROP_ORDER = (SUMMARY, PAIRS, EDGES)
# Create order: a view after the view it reads.
VIEWS_CREATE_ORDER = (PAIRS, SUMMARY, EDGES)

# Source of every constant below: NEXUS_template at migration 138, read-only,
# 2026-09-30 (identical on save_01..save_05). md5 of
# pg_get_viewdef(view, true) and of obj_description(view, 'pg_class').
VIEW_DEFINITION_MD5 = {
    PAIRS: "b6a065311f82626698e5231b3b47b7bc",
    SUMMARY: "5377171baacbe9e70f04f984ebc37972",
    EDGES: "c09dd8617c1e293b96ce711c1321a609",
}
VIEW_COMMENT_MD5 = {
    PAIRS: "7c8f9eae92a3c251388e75dfabeaaf4b",
    SUMMARY: "3a4e2c33216a42861b66302fb93e28c0",
    EDGES: "8d50c14c081bbfc2f8bd8d9499af393f",
}
PAIRS_COMMENT = (
    "Bidirectional view of character relationships showing both perspectives"
)
SUMMARY_COMMENT = (
    "Simplified summary of character relationships focusing on key dynamics"
)
EDGES_COLUMN_COMMENTS = {
    "valence_magnitude": (
        "Signed integer in -5..+5 derived from canonical valence_current via "
        "round(valence_current * 5.5); NULL outside character scope."
    ),
    "valence_current": (
        "Canonical continuous signed valence for character relationships; NULL "
        "for faction and faction_character scopes."
    ),
}

# Ordered (attname, format_type) of each view on NEXUS_template at 138, with
# char_id_1 and char_id_2 changed from integer to bigint by migration 139.
PAIRS_COLUMNS = [
    ("char_id_1", "bigint"),
    ("char_id_2", "bigint"),
    ("char_name_1", "character varying(50)"),
    ("char_name_2", "character varying(50)"),
    ("type_1_to_2", "character varying(50)"),
    ("valence_1_to_2", "character varying(50)"),
    ("dynamic_1_to_2", "text"),
    ("recent_1_to_2", "text"),
    ("history_1_to_2", "text"),
    ("extra_1_to_2", "jsonb"),
    ("type_2_to_1", "character varying(50)"),
    ("valence_2_to_1", "character varying(50)"),
    ("dynamic_2_to_1", "text"),
    ("recent_2_to_1", "text"),
    ("history_2_to_1", "text"),
    ("extra_2_to_1", "jsonb"),
    ("created_at", "timestamp with time zone"),
    ("updated_at", "timestamp with time zone"),
]
SUMMARY_COLUMNS = [
    ("char_id_1", "bigint"),
    ("char_id_2", "bigint"),
    ("char_name_1", "character varying(50)"),
    ("char_name_2", "character varying(50)"),
    ("type_1_to_2", "character varying(50)"),
    ("type_2_to_1", "character varying(50)"),
    ("valence_1_to_2", "character varying(50)"),
    ("valence_2_to_1", "character varying(50)"),
    ("dynamic_1_to_2", "text"),
    ("dynamic_2_to_1", "text"),
]
EDGES_COLUMNS = [
    ("source_entity_id", "bigint"),
    ("target_entity_id", "bigint"),
    ("relationship_scope", "text"),
    ("relationship_type", "text"),
    ("valence", "text"),
    ("dynamic", "text"),
    ("recent_events", "text"),
    ("history", "text"),
    ("extra_data", "jsonb"),
    ("valence_magnitude", "integer"),
    ("valence_current", "numeric"),
]
VIEW_COLUMNS = {PAIRS: PAIRS_COLUMNS, SUMMARY: SUMMARY_COLUMNS, EDGES: EDGES_COLUMNS}

TABLE_INDEXES = (
    "character_relationships_pkey",
    "idx_character_relationships_character1",
    "idx_character_relationships_character2",
    "idx_character_relationships_type",
)
TABLE_TRIGGERS = (
    "trg_character_relationships_valence_boundary",
    "trg_version_character_relationships",
)


def _columns(cur: Any, relation: str) -> list[tuple[str, str]]:
    """Return the ordered (attname, format_type) list of ``public.relation``."""

    cur.execute(
        """
        SELECT a.attname::text, format_type(a.atttypid, a.atttypmod)
        FROM pg_attribute AS a
        WHERE a.attrelid = to_regclass(%s)
          AND a.attnum > 0
          AND NOT a.attisdropped
        ORDER BY a.attnum
        """,
        (f"public.{relation}",),
    )
    return [(str(name), str(type_name)) for name, type_name in cur.fetchall()]


def _id_types(cur: Any) -> dict[str, str]:
    columns = dict(_columns(cur, "character_relationships"))
    return {name: columns[name] for name in ("character1_id", "character2_id")}


def _all_column_types(cur: Any) -> dict[tuple[str, str], str]:
    types: dict[tuple[str, str], str] = {}
    for relation in ("character_relationships", *VIEWS_CREATE_ORDER):
        for name, type_name in _columns(cur, relation):
            types[(relation, name)] = type_name
    return types


def _is_stamped(cur: Any) -> bool:
    cur.execute("SELECT 1 FROM schema_migrations WHERE version = '139'")
    return cur.fetchone() is not None


def _capture_views(cur: Any) -> dict[str, tuple[str, str | None, dict[str, str]]]:
    """Return each view's definition, view comment, and column comments."""

    captured: dict[str, tuple[str, str | None, dict[str, str]]] = {}
    for view in VIEWS_CREATE_ORDER:
        cur.execute(
            """
            SELECT pg_get_viewdef(c.oid, true), obj_description(c.oid, 'pg_class')
            FROM pg_class AS c
            WHERE c.oid = %s::regclass
            """,
            (f"public.{view}",),
        )
        definition, comment = cur.fetchone()
        cur.execute(
            """
            SELECT a.attname::text, col_description(a.attrelid, a.attnum)
            FROM pg_attribute AS a
            WHERE a.attrelid = %s::regclass
              AND a.attnum > 0
              AND NOT a.attisdropped
              AND col_description(a.attrelid, a.attnum) IS NOT NULL
            """,
            (f"public.{view}",),
        )
        captured[view] = (
            str(definition),
            comment,
            {str(name): str(text) for name, text in cur.fetchall()},
        )
    return captured


def _restore_pre_139_shape(dbname: str) -> None:
    """Return the clone to the integer-id shape and delete the 139 stamp."""

    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        captured = _capture_views(cur)
        for view in VIEWS_DROP_ORDER:
            cur.execute(f"DROP VIEW public.{view}")
        cur.execute(
            "ALTER TABLE public.character_relationships "
            "ALTER COLUMN character1_id TYPE integer, "
            "ALTER COLUMN character2_id TYPE integer"
        )
        for view in VIEWS_CREATE_ORDER:
            definition, comment, column_comments = captured[view]
            cur.execute(f"CREATE VIEW public.{view} AS {definition}")
            if comment is not None:
                cur.execute(f"COMMENT ON VIEW public.{view} IS %s", (comment,))
            for column, text in column_comments.items():
                cur.execute(f"COMMENT ON COLUMN public.{view}.{column} IS %s", (text,))
        cur.execute("DELETE FROM schema_migrations WHERE version = '139'")
        assert _id_types(cur) == {
            "character1_id": "integer",
            "character2_id": "integer",
        }
        assert _capture_views(cur) == captured


def _table_snapshot(cur: Any) -> dict[str, Any]:
    cur.execute(
        """
        SELECT conname::text, pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid = 'public.character_relationships'::regclass
        ORDER BY conname
        """
    )
    constraints = [tuple(row) for row in cur.fetchall()]
    cur.execute(
        """
        SELECT indexname::text, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = 'character_relationships'
        ORDER BY indexname
        """
    )
    indexes = [tuple(row) for row in cur.fetchall()]
    cur.execute(
        """
        SELECT tgname::text, pg_get_triggerdef(oid)
        FROM pg_trigger
        WHERE tgrelid = 'public.character_relationships'::regclass
          AND NOT tgisinternal
        ORDER BY tgname
        """
    )
    triggers = [tuple(row) for row in cur.fetchall()]
    cur.execute(
        """
        SELECT to_jsonb(cr)
        FROM public.character_relationships AS cr
        ORDER BY cr.character1_id, cr.character2_id
        """
    )
    rows = [row[0] for row in cur.fetchall()]
    cur.execute("SELECT count(*) FROM relationship_versions")
    versions = int(cur.fetchone()[0])
    return {
        "constraints": constraints,
        "indexes": indexes,
        "triggers": triggers,
        "rows": rows,
        "versions": versions,
    }


def _seed_two_way_relationship(dbname: str) -> tuple[int, int]:
    pair = seed_character_pair(
        dbname,
        world_time=WORLD_TIME,
        actor_name="Ines Varga",
        target_name="Tomas Brandt",
    )
    actor = pair.actor_character_id
    target = pair.target_character_id
    seed_relationship(
        dbname,
        subject_character_id=actor,
        object_character_id=target,
        relationship_type="ally",
    )
    seed_relationship(
        dbname,
        subject_character_id=target,
        object_character_id=actor,
        relationship_type="ally",
        emotional_valence="+2|warm",
    )
    return actor, target


def test_migration_139_widens_ids_and_keeps_views() -> None:
    """A fresh clone has bigint ids and the template's views, byte for byte."""

    with disposable_slot_database("qa640_836s2_widen") as dbname:
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            assert _is_stamped(cur)
            assert _id_types(cur) == {
                "character1_id": "bigint",
                "character2_id": "bigint",
            }
            for view, expected_columns in VIEW_COLUMNS.items():
                assert _columns(cur, view) == expected_columns, view
                cur.execute(
                    """
                    SELECT md5(pg_get_viewdef(c.oid, true)),
                           md5(obj_description(c.oid, 'pg_class')),
                           obj_description(c.oid, 'pg_class'),
                           c.relacl IS NULL,
                           pg_get_userbyid(c.relowner) = current_user
                    FROM pg_class AS c
                    WHERE c.oid = %s::regclass
                    """,
                    (f"public.{view}",),
                )
                definition_md5, comment_md5, comment, no_acl, owned = cur.fetchone()
                assert definition_md5 == VIEW_DEFINITION_MD5[view], view
                assert comment_md5 == VIEW_COMMENT_MD5[view], view
                assert no_acl, view
                assert owned, view
                if view == PAIRS:
                    assert comment == PAIRS_COMMENT
                if view == SUMMARY:
                    assert comment == SUMMARY_COMMENT
            cur.execute(
                """
                SELECT a.attname::text, col_description(a.attrelid, a.attnum)
                FROM pg_attribute AS a
                WHERE a.attrelid = 'public.entity_relationships_v'::regclass
                  AND a.attnum > 0
                  AND col_description(a.attrelid, a.attnum) IS NOT NULL
                """
            )
            assert dict(cur.fetchall()) == EDGES_COLUMN_COMMENTS


def test_migration_139_reruns_from_integer_ids() -> None:
    """From the pre-139 shape, 139 changes six column types and nothing else."""

    with disposable_slot_database("qa640_836s2_rerun") as dbname:
        actor, target = _seed_two_way_relationship(dbname)
        _restore_pre_139_shape(dbname)

        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            before = _table_snapshot(cur)
            before_types = _all_column_types(cur)
        assert [name for name, _ in before["indexes"]] == sorted(TABLE_INDEXES)
        assert [name for name, _ in before["triggers"]] == sorted(TABLE_TRIGGERS)
        assert len(before["constraints"]) == 5
        assert [
            (row["character1_id"], row["character2_id"]) for row in before["rows"]
        ] == sorted([(actor, target), (target, actor)])

        assert migrate.migrate_database(dbname, skip_locked=False) == (1, 0)

        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            after = _table_snapshot(cur)
            after_types = _all_column_types(cur)
            assert _is_stamped(cur)
        assert after == before
        assert set(after_types) == set(before_types)
        changed = {
            key: (before_types[key], after_types[key])
            for key in before_types
            if before_types[key] != after_types[key]
        }
        assert changed == {
            ("character_relationships", "character1_id"): ("integer", "bigint"),
            ("character_relationships", "character2_id"): ("integer", "bigint"),
            (PAIRS, "char_id_1"): ("integer", "bigint"),
            (PAIRS, "char_id_2"): ("integer", "bigint"),
            (SUMMARY, "char_id_1"): ("integer", "bigint"),
            (SUMMARY, "char_id_2"): ("integer", "bigint"),
        }


def test_relationship_ids_above_int4_max() -> None:
    """Characters with ids above the int4 range hold relationships both ways."""

    with disposable_slot_database("qa640_836s2_int8") as dbname:
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT setval('characters_id_seq', 2147483648)")
        pair = seed_character_pair(
            dbname,
            world_time=WORLD_TIME,
            actor_name="Ines Varga",
            target_name="Tomas Brandt",
        )
        actor = pair.actor_character_id
        target = pair.target_character_id
        assert actor > INT4_MAX and target > INT4_MAX
        seed_relationship(
            dbname,
            subject_character_id=actor,
            object_character_id=target,
            relationship_type="ally",
        )
        seed_relationship(
            dbname,
            subject_character_id=target,
            object_character_id=actor,
            relationship_type="ally",
            emotional_valence="+2|warm",
        )

        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT (old_row->>'character1_id')::bigint,
                       (old_row->>'character2_id')::bigint
                FROM relationship_versions
                WHERE relationship_table = 'character_relationships'
                  AND operation = 'insert'
                ORDER BY id
                """
            )
            assert cur.fetchall() == [(actor, target), (target, actor)]

            cur.execute(f"SELECT char_id_1, char_id_2 FROM public.{PAIRS}")
            assert cur.fetchall() == [(min(actor, target), max(actor, target))]
            cur.execute(f"SELECT char_id_1, char_id_2 FROM public.{SUMMARY}")
            assert cur.fetchall() == [(min(actor, target), max(actor, target))]

            cur.execute(
                f"""
                SELECT source_entity_id, target_entity_id
                FROM public.{EDGES}
                WHERE relationship_scope = 'character'
                ORDER BY source_entity_id, target_entity_id
                """
            )
            assert cur.fetchall() == sorted(
                [
                    (pair.actor_entity_id, pair.target_entity_id),
                    (pair.target_entity_id, pair.actor_entity_id),
                ]
            )


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        (
            "summary_drift",
            "Migration 139: view character_relationship_summary definition "
            "differs from the one it replaced",
        ),
        (
            "unknown_dependent",
            "cannot drop view entity_relationships_v because other objects "
            "depend on it",
        ),
    ],
)
def test_migration_139_refuses_drift(
    case: str, expected_error: str, caplog: pytest.LogCaptureFixture
) -> None:
    """A drifted view or an unknown dependent rolls the whole file back."""

    with disposable_slot_database(f"qa640_836s2_{case}") as dbname:
        _restore_pre_139_shape(dbname)
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            if case == "summary_drift":
                cur.execute(
                    f"SELECT obj_description('public.{SUMMARY}'::regclass, "
                    "'pg_class')"
                )
                comment = cur.fetchone()[0]
                cur.execute(f"DROP VIEW public.{SUMMARY}")
                cur.execute(
                    f"""
                    CREATE VIEW public.{SUMMARY} AS
                    SELECT char_id_1, char_id_2, char_name_1, char_name_2,
                           type_1_to_2, type_2_to_1, valence_1_to_2,
                           valence_2_to_1, dynamic_1_to_2
                    FROM public.{PAIRS}
                    """
                )
                cur.execute(f"COMMENT ON VIEW public.{SUMMARY} IS %s", (comment,))
            else:
                cur.execute(
                    f"""
                    CREATE VIEW public.qa_m139_dependent AS
                    SELECT source_entity_id FROM public.{EDGES}
                    """
                )

        with caplog.at_level(logging.ERROR, logger="nexus.migrate"):
            assert migrate.migrate_database(dbname, skip_locked=False) == (0, 1)
        assert f"FAILED: {MIGRATION}" in caplog.text
        assert expected_error in caplog.text

        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            assert not _is_stamped(cur)
            assert _id_types(cur) == {
                "character1_id": "integer",
                "character2_id": "integer",
            }
