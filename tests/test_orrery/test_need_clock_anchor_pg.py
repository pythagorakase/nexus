"""Real-schema regressions for issue #640's two-clocks doctrine."""

from __future__ import annotations

import copy
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any, Iterator
import uuid

import psycopg2
from psycopg2 import sql
import pytest

from nexus.agents.orrery.events import (
    NeedDebtScoreDomainError,
    _apply_need_fulfillment_sync,
)
from nexus.agents.orrery.needs import load_need_tuning
from nexus.api.db_pool import close_all_pools
from nexus.api.new_story_cache import read_cache, write_cache
from nexus.api.new_story_db_mapper import NewStoryDatabaseMapper
from nexus.api.new_story_flow import build_transition_data_from_cache
from nexus.api.slot_utils import VALID_DBNAMES
from scripts import migrate


pytestmark = pytest.mark.requires_postgres

ROOT = Path(__file__).parents[2]
MIGRATION_PATH = ROOT / "migrations" / "100_orrery_need_clock_anchor.sql"
WIZARD_FIXTURE_PATH = (
    ROOT / "tests" / "fixtures" / "slot3_midnight_qa_wizard_cache.json"
)
STORY_BASE = datetime(2189, 10, 17, 19, 12, tzinfo=timezone.utc)
STORY_ANCHOR = STORY_BASE + timedelta(hours=3)
STALE_STORY_BASE = datetime(2089, 4, 2, 8, 30, tzinfo=timezone.utc)
POISONED_WALL_TIME = datetime(2026, 7, 30, 5, 55, 20, tzinfo=timezone.utc)


def _connect(dbname: str) -> Any:
    """Open a direct PostgreSQL connection to a disposable clone."""

    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


@contextmanager
def _transaction(dbname: str) -> Iterator[Any]:
    """Commit one clone transaction, rolling it back on failure."""

    conn = _connect(dbname)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@pytest.fixture()
def disposable_need_clock_db() -> Iterator[str]:
    """Yield a NEXUS_template clone whose name cannot collide with a save slot."""

    dbname = f"qa640_{uuid.uuid4().hex[:12]}"
    admin: Any = None
    try:
        try:
            admin = _connect("postgres")
        except psycopg2.Error as exc:
            pytest.skip(f"PostgreSQL admin connection unavailable: {exc}")
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    sql.Identifier(dbname),
                    sql.Identifier("NEXUS_template"),
                )
            )
        VALID_DBNAMES.add(dbname)
        yield dbname
    finally:
        close_all_pools()
        VALID_DBNAMES.discard(dbname)
        if admin is not None:
            with admin.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (dbname,),
                )
                cur.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(dbname))
                )
            admin.close()


def _apply_migration_100(dbname: str) -> tuple[str, ...]:
    """Apply migration 100 through the managed runner and return its notices."""

    discovered = {
        (version, name, path.name)
        for version, name, path in migrate.discover_migrations()
    }
    assert (
        "100",
        "orrery_need_clock_anchor",
        MIGRATION_PATH.name,
    ) in discovered

    conn = _connect(dbname)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM schema_migrations WHERE version = '100'")
            assert cur.fetchone()[0] == 0
        assert migrate.apply_migration(
            conn,
            "100",
            "orrery_need_clock_anchor",
            MIGRATION_PATH,
        )
        notices = tuple(conn.notices)
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM schema_migrations WHERE version = '100'")
            assert cur.fetchone()[0] == "orrery_need_clock_anchor"
        return notices
    finally:
        conn.close()


def _set_base_timestamp(cur: Any, value: datetime | None) -> None:
    """Ensure the singleton global row exists with the requested story clock."""

    cur.execute(
        """
        INSERT INTO global_variables (id, new_story, base_timestamp)
        VALUES (true, true, %s)
        ON CONFLICT (id) DO UPDATE
        SET base_timestamp = EXCLUDED.base_timestamp
        """,
        (value,),
    )


def _insert_character(cur: Any, name: str) -> int:
    """Insert one real-schema character and return its entity-spine ID."""

    cur.execute(
        "INSERT INTO entities (kind, is_active) "
        "VALUES ('character', true) RETURNING id"
    )
    entity_id = int(cur.fetchone()[0])
    cur.execute(
        "INSERT INTO characters (name, entity_id) VALUES (%s, %s)",
        (name, entity_id),
    )
    return entity_id


def _insert_chunk_at(cur: Any, world_time: datetime) -> int:
    """Create a real chunk and pin its metadata to an exact test world time."""

    cur.execute(
        """
        INSERT INTO narrative_chunks (raw_text, storyteller_text)
        VALUES ('Issue 640 clock probe.', 'Issue 640 clock probe.')
        RETURNING id
        """
    )
    chunk_id = int(cur.fetchone()[0])
    cur.execute(
        "INSERT INTO chunk_metadata (chunk_id, world_time) VALUES (%s, %s)",
        (chunk_id, world_time),
    )
    # The statement trigger derives world_time from base_timestamp on INSERT.
    # A world_time-only UPDATE does not retrigger it, matching replay test idioms.
    cur.execute(
        "UPDATE chunk_metadata SET world_time = %s WHERE chunk_id = %s",
        (world_time, chunk_id),
    )
    return chunk_id


def _build_story_transition(dbname: str) -> Any:
    """Hydrate the checked-in wizard artifact with issue #640's future clock."""

    payload = copy.deepcopy(json.loads(WIZARD_FIXTURE_PATH.read_text()))
    seed_bundle = payload["seed"]
    seed_bundle["story_seed"]["base_timestamp"] = {
        "year": STORY_BASE.year,
        "month": STORY_BASE.month,
        "day": STORY_BASE.day,
        "hour": STORY_BASE.hour,
        "minute": STORY_BASE.minute,
        "second": STORY_BASE.second,
    }
    write_cache(
        thread_id="issue_640_ordering_regression",
        setting_draft=payload["setting"],
        character_draft=payload["character"],
        selected_seed=seed_bundle["story_seed"],
        layer_draft=seed_bundle["layer"],
        zone_draft=seed_bundle["zone"],
        initial_location=seed_bundle["initial_location"],
        base_timestamp=STORY_BASE.isoformat(),
        target_slot=3,
        dbname=dbname,
    )
    cache = read_cache(dbname)
    assert cache is not None
    assert cache.current_phase() == "ready"
    return build_transition_data_from_cache(cache)


def test_character_need_rows_anchor_to_base_without_chunks(
    disposable_need_clock_db: str,
) -> None:
    """A pre-narrative character uses base_timestamp, never wall time."""

    _apply_migration_100(disposable_need_clock_db)
    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM character_need_states")
            cur.execute("DELETE FROM chunk_metadata")
            _set_base_timestamp(cur, STORY_BASE)
            entity_id = _insert_character(cur, "Base Clock Character")
            cur.execute(
                """
                SELECT last_evaluated_at
                FROM character_need_states
                WHERE character_entity_id = %s
                ORDER BY need_type::text
                """,
                (entity_id,),
            )
            anchors = [row[0] for row in cur.fetchall()]

    assert len(anchors) == 5
    assert set(anchors) == {STORY_BASE}


def test_character_need_rows_raise_when_all_clock_sources_are_absent(
    disposable_need_clock_db: str,
) -> None:
    """The database function names the violated world-clock invariant."""

    _apply_migration_100(disposable_need_clock_db)
    with pytest.raises(
        psycopg2.errors.RaiseException,
        match=(
            "need-clock anchor unavailable: "
            "no canonical world time or base_timestamp"
        ),
    ):
        with _transaction(disposable_need_clock_db) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM character_need_states")
                cur.execute("DELETE FROM chunk_metadata")
                _set_base_timestamp(cur, None)
                _insert_character(cur, "Clockless Character")


def test_migration_reconciles_poisoned_rows_and_guards_fulfillment_domain(
    disposable_need_clock_db: str,
) -> None:
    """Repair the real issue shape before fulfillment debt is materialized."""

    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM character_need_states")
            cur.execute("DELETE FROM chunk_metadata")
            _set_base_timestamp(cur, STORY_BASE)
            entity_id = _insert_character(cur, "Poisoned Clock Character")
            cur.execute(
                """
                UPDATE character_need_states
                SET last_evaluated_at = %s,
                    last_fulfilled_at = CASE
                        WHEN need_type IN ('sleep', 'hunger') THEN %s
                        WHEN need_type = 'thirst' THEN %s
                        ELSE NULL
                    END
                WHERE character_entity_id = %s
                """,
                (
                    POISONED_WALL_TIME,
                    POISONED_WALL_TIME,
                    STORY_BASE + timedelta(hours=1),
                    entity_id,
                ),
            )
            cur.execute(
                """
                UPDATE character_need_states
                SET last_evaluated_at = %s
                WHERE character_entity_id = %s
                  AND need_type = 'intimacy'
                """,
                (STORY_BASE + timedelta(hours=2), entity_id),
            )
            chunk_id = _insert_chunk_at(cur, STORY_ANCHOR)

    notices = _apply_migration_100(disposable_need_clock_db)
    assert (
        "need-clock reconciliation: last_evaluated_at rows=4, "
        "last_fulfilled_at rows=2"
    ) in "".join(notices)

    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT need_type::text, last_evaluated_at, last_fulfilled_at
                FROM character_need_states
                WHERE character_entity_id = %s
                ORDER BY need_type::text
                """,
                (entity_id,),
            )
            reconciled = {
                need_type: (last_evaluated_at, last_fulfilled_at)
                for need_type, last_evaluated_at, last_fulfilled_at in cur.fetchall()
            }

            assert reconciled["intimacy"][0] == STORY_BASE + timedelta(hours=2)
            assert all(
                evaluated_at == STORY_ANCHOR
                for need_type, (evaluated_at, _fulfilled_at) in reconciled.items()
                if need_type != "intimacy"
            )
            assert reconciled["sleep"][1] == STORY_ANCHOR
            assert reconciled["hunger"][1] == STORY_ANCHOR
            assert reconciled["thirst"][1] == STORY_BASE + timedelta(hours=1)
            assert reconciled["socialize"][1] is None
            assert reconciled["intimacy"][1] is None

            _apply_need_fulfillment_sync(
                cur,
                actor_entity_id=entity_id,
                fulfillment={
                    "type": "thirst",
                    "quality": "routine",
                    "discharge_debt": 9999,
                },
                template_id="issue_640_reconciled",
                source_chunk_id=chunk_id,
                need_tuning=load_need_tuning(),
            )
            cur.execute(
                """
                SELECT debt_score, last_evaluated_at, last_fulfilled_at
                FROM character_need_states
                WHERE character_entity_id = %s
                  AND need_type = 'thirst'
                """,
                (entity_id,),
            )
            stored_debt, evaluated_at, fulfilled_at = cur.fetchone()
            assert stored_debt == 0
            assert evaluated_at == STORY_ANCHOR
            assert fulfilled_at == STORY_ANCHOR

            cur.execute(
                """
                UPDATE character_need_states
                SET last_evaluated_at = %s
                WHERE character_entity_id = %s
                  AND need_type = 'thirst'
                """,
                (POISONED_WALL_TIME, entity_id),
            )
            with pytest.raises(
                NeedDebtScoreDomainError,
                match=(
                    r"need debt score outside numeric\(8,2\) domain: "
                    rf"character={entity_id}, need=thirst, value="
                ),
            ):
                _apply_need_fulfillment_sync(
                    cur,
                    actor_entity_id=entity_id,
                    fulfillment={
                        "type": "thirst",
                        "quality": "routine",
                        "discharge_debt": 0,
                    },
                    template_id="issue_640_domain_guard",
                    source_chunk_id=chunk_id,
                    need_tuning=load_need_tuning(),
                )

            cur.execute(
                """
                SELECT debt_score, last_evaluated_at
                FROM character_need_states
                WHERE character_entity_id = %s
                  AND need_type = 'thirst'
                """,
                (entity_id,),
            )
            stored_debt, evaluated_at = cur.fetchone()
            assert stored_debt == 0
            assert evaluated_at == POISONED_WALL_TIME


def test_migration_reconciliation_noops_without_base_timestamp(
    disposable_need_clock_db: str,
) -> None:
    """Without a canonical base, migration 100 leaves existing clocks untouched."""

    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM character_need_states")
            cur.execute("DELETE FROM chunk_metadata")
            _set_base_timestamp(cur, None)
            entity_id = _insert_character(cur, "Unreconciled Clock Character")
            cur.execute(
                """
                UPDATE character_need_states
                SET last_evaluated_at = %s
                WHERE character_entity_id = %s
                """,
                (POISONED_WALL_TIME, entity_id),
            )

    notices = _apply_migration_100(disposable_need_clock_db)
    assert (
        "need-clock reconciliation: last_evaluated_at rows=0, "
        "last_fulfilled_at rows=0"
    ) in "".join(notices)
    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT last_evaluated_at
                FROM character_need_states
                WHERE character_entity_id = %s
                """,
                (entity_id,),
            )
            assert cur.fetchall() == [(POISONED_WALL_TIME,)]


def test_atomic_transition_replaces_stale_clock_before_protagonist_trigger(
    disposable_need_clock_db: str,
) -> None:
    """The wizard transaction exposes the new clock before character creation."""

    _apply_migration_100(disposable_need_clock_db)
    transition = _build_story_transition(disposable_need_clock_db)
    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chunk_metadata")
            _set_base_timestamp(cur, STALE_STORY_BASE)

    result = NewStoryDatabaseMapper(dbname=disposable_need_clock_db).perform_transition(
        transition
    )

    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT base_timestamp FROM global_variables WHERE id = true")
            assert cur.fetchone()[0] == STORY_BASE
            cur.execute(
                """
                SELECT cns.last_evaluated_at
                FROM character_need_states cns
                JOIN characters c ON c.entity_id = cns.character_entity_id
                WHERE c.id = %s
                ORDER BY cns.need_type::text
                """,
                (result["character_id"],),
            )
            anchors = [row[0] for row in cur.fetchall()]

    assert len(anchors) == 5
    assert set(anchors) == {STORY_BASE}
    assert STALE_STORY_BASE not in anchors
    assert POISONED_WALL_TIME not in anchors
