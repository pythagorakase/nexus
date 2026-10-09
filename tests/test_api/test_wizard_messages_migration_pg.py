"""Migration 150 cutover and refusal on disposable, routed slot databases.

Tables: assets.new_story_creator, assets.traits, assets.wizard_messages and
schema_migrations. No owner database or provider transcript is accessed.
"""

from contextlib import closing
from pathlib import Path
import re
from typing import Any
from uuid import UUID

import pytest
from psycopg2.extras import RealDictCursor

from nexus.api.conversations import new_conversation_id
from nexus.api.new_story_cache import clear_cache, init_cache
from nexus.api.new_story_flow import start_setup
from nexus.api.slot_state import get_slot_state
from nexus.config import load_settings
from scripts import migrate
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slots_to_disposable,
)

pytestmark = [
    pytest.mark.requires_postgres,
    pytest.mark.usefixtures("offline_registry"),
]
MIGRATION = Path(__file__).resolve().parents[2] / "migrations/150_wizard_messages.sql"


def _remove_migration(dbname: str) -> None:
    """Leave one clone at the exact pre-150 transcript schema and stamp."""
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("DROP TABLE assets.wizard_messages")
        cur.execute("DELETE FROM schema_migrations WHERE version = '150'")


def _cache_bytes(dbname: str) -> str | None:
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT row_to_json(cache)::text FROM assets.new_story_creator cache "
            "WHERE id = TRUE"
        )
        row = cur.fetchone()
        return row[0] if row is not None else None


def _traits(dbname: str) -> list[dict[str, Any]]:
    with closing(connect(dbname, cursor_factory=RealDictCursor)) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM assets.traits ORDER BY id")
            return [dict(row) for row in cur.fetchall()]


def _assert_comments(dbname: str) -> None:
    """Compare every live object comment with the migration's exact text."""
    expected = {
        target: text.replace("''", "'")
        for _, target, text in re.findall(
            r"^COMMENT ON (TABLE|COLUMN) assets\.(\S+) IS '((?:[^']|'')*)';$",
            MIGRATION.read_text(),
            flags=re.M,
        )
    }
    assert len(expected) == 10
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT obj_description('assets.wizard_messages'::regclass, 'pg_class')"
        )
        assert cur.fetchone()[0] == expected.pop("wizard_messages")
        for table in ("wizard_messages", "new_story_creator"):
            cur.execute(
                "SELECT attname, col_description(attrelid, attnum) "
                "FROM pg_attribute WHERE attrelid = %s::regclass "
                "AND attnum > 0 AND NOT attisdropped",
                (f"assets.{table}",),
            )
            for name, comment in cur.fetchall():
                key = f"{table}.{name}"
                if key in expected:
                    assert comment == expected.pop(key)
    assert expected == {}


def test_migration_150_discards_only_hosted_thread_wizards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hosted cutover resets traits; UUID cache bytes remain exactly unchanged."""
    with disposable_slot_database("qa640_776_hosted") as hosted:
        with disposable_slot_database("qa640_776_uuid") as retained:
            route_slots_to_disposable(monkeypatch.setattr, {5: hosted, 4: retained})
            clear_cache(hosted)
            reset_traits = _traits(hosted)
            init_cache(hosted, "conv_776_disposable_hosted", 5)
            init_cache(retained, new_conversation_id(), 4)
            with closing(connect(hosted)) as conn, conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE assets.traits SET is_selected = TRUE, "
                    "rationale = 'Selected before cutover' WHERE id = 1"
                )
                cur.execute(
                    "UPDATE assets.traits SET name = 'old wildcard', "
                    "rationale = 'Old wildcard choice' WHERE id = 11"
                )
            retained_bytes = _cache_bytes(retained)
            assert retained_bytes is not None
            for dbname in (hosted, retained):
                _remove_migration(dbname)
                assert migrate.migrate_database(dbname, skip_locked=False) == (1, 0)
                _assert_comments(dbname)
            assert _cache_bytes(hosted) is None
            assert _traits(hosted) == reset_traits
            assert _cache_bytes(retained) == retained_bytes
            assert get_slot_state(5).is_empty
            model = load_settings().global_.model.api_models["test"].models[0].id
            new_thread = start_setup(5, model)
            assert str(UUID(new_thread)) == new_thread


@pytest.mark.parametrize(
    "legacy_thread", ["local_thread_776_disposable", "test_thread_776_disposable", None]
)
def test_migration_150_refuses_retired_local_threads(
    offline_gate_db: str, legacy_thread: str | None
) -> None:
    """Local or NULL identifiers roll back the cache, new table and stamp."""
    init_cache(offline_gate_db, new_conversation_id(), 4)
    with closing(connect(offline_gate_db)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE assets.new_story_creator SET thread_id = %s WHERE id = TRUE",
            (legacy_thread,),
        )
    before = _cache_bytes(offline_gate_db)
    _remove_migration(offline_gate_db)
    assert migrate.migrate_database(offline_gate_db, skip_locked=False) == (0, 1)
    assert _cache_bytes(offline_gate_db) == before
    with closing(connect(offline_gate_db)) as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('assets.wizard_messages')")
        assert cur.fetchone()[0] is None
        cur.execute("SELECT count(*) FROM schema_migrations WHERE version = '150'")
        assert cur.fetchone()[0] == 0
