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
from nexus.agents.orrery.reconstruction import capture_state_checkpoint_sync
from nexus.agents.orrery.replay import (
    reconstruct_state_at_sync,
    verify_checkpoints_sync,
)
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
PAST_STORY_BASE = datetime(1920, 5, 14, 10, 48, tzinfo=timezone.utc)
PAST_STORY_ANCHOR = PAST_STORY_BASE + timedelta(hours=3)


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
    source_db = os.environ.get("NEXUS_TEST_TEMPLATE_DB", "NEXUS_template")
    assert source_db == "NEXUS_template" or source_db.startswith("qa640_")
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
                    sql.Identifier(source_db),
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
    """Install or idempotently re-run migration 100 and return its notices."""

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
            cur.execute(
                "SELECT EXISTS ("
                "SELECT 1 FROM schema_migrations WHERE version = '100'"
                ")"
            )
            already_applied = bool(cur.fetchone()[0])
        if already_applied:
            with conn.cursor() as cur:
                cur.execute(MIGRATION_PATH.read_text())
            conn.commit()
        else:
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


def _insert_atemporal_chunk(cur: Any) -> int:
    """Create a legitimate non-primary-layer chunk with no world clock row."""

    cur.execute(
        """
        INSERT INTO narrative_chunks (raw_text, storyteller_text)
        VALUES ('Issue 640 atemporal probe.', 'Issue 640 atemporal probe.')
        RETURNING id
        """
    )
    return int(cur.fetchone()[0])


def _insert_need_resolution(
    cur: Any,
    *,
    chunk_id: int,
    entity_id: int,
    template_id: str,
    fulfillment: dict[str, Any],
) -> None:
    """Persist the ledger peer for an already-applied need fulfillment."""

    cur.execute(
        """
        INSERT INTO orrery_resolutions (
            tick_chunk_id, template_id, binding_hash, actor_entity_id,
            priority, magnitude, state_delta
        ) VALUES (%s, %s, %s, %s, 50, 0.5, %s::jsonb)
        """,
        (
            chunk_id,
            template_id,
            f"{template_id}-{entity_id}",
            entity_id,
            json.dumps({"need.fulfill": fulfillment}),
        ),
    )


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
                SELECT need_type::text, last_evaluated_at, last_fulfilled_at,
                       metadata
                FROM character_need_states
                WHERE character_entity_id = %s
                ORDER BY need_type::text
                """,
                (entity_id,),
            )
            reconciled = {
                need_type: (last_evaluated_at, last_fulfilled_at, metadata)
                for (
                    need_type,
                    last_evaluated_at,
                    last_fulfilled_at,
                    metadata,
                ) in cur.fetchall()
            }

            assert reconciled["intimacy"][0] == STORY_BASE + timedelta(hours=2)
            assert all(
                evaluated_at == STORY_ANCHOR
                for need_type, (
                    evaluated_at,
                    _fulfilled_at,
                    _metadata,
                ) in reconciled.items()
                if need_type != "intimacy"
            )
            assert reconciled["sleep"][1] == STORY_ANCHOR
            assert reconciled["hunger"][1] == STORY_ANCHOR
            assert reconciled["thirst"][1] == STORY_BASE + timedelta(hours=1)
            assert reconciled["socialize"][1] is None
            assert reconciled["intimacy"][1] is None
            marker_rows = {
                need_type: metadata
                for need_type, (_evaluated, _fulfilled, metadata) in reconciled.items()
                if metadata.get("reconciled_by") == "migration_100"
            }
            assert set(marker_rows) == {"hunger", "sleep", "socialize", "thirst"}
            assert (
                sum(
                    "reconciled_last_evaluated_from" in metadata
                    for metadata in marker_rows.values()
                )
                == 4
            )
            assert (
                sum(
                    "reconciled_last_fulfilled_from" in metadata
                    for metadata in marker_rows.values()
                )
                == 2
            )
            assert all(
                datetime.fromisoformat(metadata["reconciled_last_evaluated_to"])
                == STORY_ANCHOR
                for metadata in marker_rows.values()
            )
            assert all(
                datetime.fromisoformat(
                    marker_rows[need_type]["reconciled_last_fulfilled_from"]
                )
                == POISONED_WALL_TIME
                for need_type in ("hunger", "sleep")
            )
            assert all(
                datetime.fromisoformat(
                    marker_rows[need_type]["reconciled_last_fulfilled_to"]
                )
                == STORY_ANCHOR
                for need_type in ("hunger", "sleep")
            )

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


def test_migration_provenance_counts_and_rerun_are_idempotent(
    disposable_need_clock_db: str,
) -> None:
    """Field markers match reported counts and a rerun changes nothing."""

    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM character_need_states")
            cur.execute("DELETE FROM chunk_metadata")
            _set_base_timestamp(cur, STORY_BASE)
            entity_id = _insert_character(cur, "Migration Marker Counts")
            cur.execute(
                """
                UPDATE character_need_states
                SET last_evaluated_at = %s,
                    last_fulfilled_at = CASE
                        WHEN need_type = 'sleep' THEN %s
                        ELSE NULL
                    END
                WHERE character_entity_id = %s
                """,
                (POISONED_WALL_TIME, POISONED_WALL_TIME, entity_id),
            )
            _insert_chunk_at(cur, STORY_ANCHOR)

    notices = _apply_migration_100(disposable_need_clock_db)
    assert (
        "need-clock reconciliation: last_evaluated_at rows=5, "
        "last_fulfilled_at rows=1"
    ) in "".join(notices)
    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT need_type::text, metadata
                FROM character_need_states
                WHERE character_entity_id = %s
                  AND metadata ->> 'reconciled_by' = 'migration_100'
                ORDER BY need_type::text
                """,
                (entity_id,),
            )
            marker_snapshot = dict(cur.fetchall())
            assert len(marker_snapshot) == 5
            assert (
                sum(
                    "reconciled_last_evaluated_from" in metadata
                    for metadata in marker_snapshot.values()
                )
                == 5
            )
            assert (
                sum(
                    "reconciled_last_fulfilled_from" in metadata
                    for metadata in marker_snapshot.values()
                )
                == 1
            )

    rerun_notices = _apply_migration_100(disposable_need_clock_db)
    assert (
        "need-clock reconciliation: last_evaluated_at rows=0, "
        "last_fulfilled_at rows=0"
    ) in "".join(rerun_notices)
    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT need_type::text, metadata
                FROM character_need_states
                WHERE character_entity_id = %s
                  AND metadata ->> 'reconciled_by' = 'migration_100'
                ORDER BY need_type::text
                """,
                (entity_id,),
            )
            assert dict(cur.fetchall()) == marker_snapshot


def test_migration_reconciles_future_poison_in_a_past_set_story(
    disposable_need_clock_db: str,
) -> None:
    """Wall time after the canon ceiling is as poisoned as time before base."""

    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM character_need_states")
            cur.execute("DELETE FROM chunk_metadata")
            _set_base_timestamp(cur, PAST_STORY_BASE)
            entity_id = _insert_character(cur, "Past-Set Clock Character")
            _insert_chunk_at(cur, PAST_STORY_ANCHOR)
            cur.execute(
                """
                UPDATE character_need_states
                SET last_evaluated_at = CASE
                        WHEN need_type = 'intimacy' THEN %s
                        ELSE %s
                    END,
                    last_fulfilled_at = CASE
                        WHEN need_type IN ('sleep', 'hunger') THEN %s
                        WHEN need_type = 'thirst' THEN %s
                        ELSE NULL
                    END
                WHERE character_entity_id = %s
                """,
                (
                    PAST_STORY_BASE + timedelta(minutes=30),
                    POISONED_WALL_TIME,
                    POISONED_WALL_TIME,
                    PAST_STORY_BASE + timedelta(minutes=15),
                    entity_id,
                ),
            )

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
                need_type: (evaluated_at, fulfilled_at)
                for need_type, evaluated_at, fulfilled_at in cur.fetchall()
            }

    assert reconciled["intimacy"][0] == PAST_STORY_BASE + timedelta(minutes=30)
    assert all(
        evaluated_at == PAST_STORY_ANCHOR
        for need_type, (evaluated_at, _fulfilled_at) in reconciled.items()
        if need_type != "intimacy"
    )
    assert reconciled["sleep"][1] == PAST_STORY_ANCHOR
    assert reconciled["hunger"][1] == PAST_STORY_ANCHOR
    assert reconciled["thirst"][1] == PAST_STORY_BASE + timedelta(minutes=15)


def test_migration_reconciliation_noops_without_base_timestamp(
    disposable_need_clock_db: str,
) -> None:
    """Without a canonical base, migration 100 leaves existing clocks untouched."""

    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM character_need_states")
            cur.execute("DELETE FROM chunk_metadata")
            # Production guarantees clock-before-characters. Seed a valid row,
            # then remove the singleton clock to exercise migration behavior.
            _set_base_timestamp(cur, STORY_BASE)
            entity_id = _insert_character(cur, "Unreconciled Clock Character")
            _set_base_timestamp(cur, None)
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


def test_replay_mirrors_reconciliation_across_migration_100_boundary(
    disposable_need_clock_db: str,
) -> None:
    """Verification applies migration 100's deterministic repair authority."""

    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            # A refreshed template may already carry 100. Remove only its
            # tracking row in this disposable clone to create a local boundary.
            cur.execute("DELETE FROM schema_migrations WHERE version = '100'")
            cur.execute("DELETE FROM character_need_states")
            cur.execute("DELETE FROM chunk_metadata")
            _set_base_timestamp(cur, STORY_BASE)
            base_chunk = _insert_chunk_at(cur, STORY_BASE)
            entity_id = _insert_character(cur, "Replay Boundary Character")
            cur.execute(
                """
                UPDATE character_need_states
                SET last_evaluated_at = %s
                WHERE character_entity_id = %s
                """,
                (POISONED_WALL_TIME, entity_id),
            )
            base_checkpoint_id = capture_state_checkpoint_sync(
                cur,
                chunk_id=base_chunk,
                label="manual",
            )
            assert base_checkpoint_id is not None

    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            target_chunk = _insert_chunk_at(cur, STORY_ANCHOR)

    notices = _apply_migration_100(disposable_need_clock_db)
    assert (
        "need-clock reconciliation: last_evaluated_at rows=5, "
        "last_fulfilled_at rows=0"
    ) in "".join(notices)

    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            target_checkpoint_id = capture_state_checkpoint_sync(
                cur,
                chunk_id=target_chunk,
                label="manual",
            )
            assert target_checkpoint_id is not None
            verdict = next(
                item
                for item in verify_checkpoints_sync(cur)
                if item.base_checkpoint_id == base_checkpoint_id
                and item.target_checkpoint_id == target_checkpoint_id
            )

    assert verdict.drifts == []
    assert any(
        "migration 100 provenance rebased" in note
        for note in verdict.notes["character_need_states"]
    )


def test_replay_does_not_restamp_post_migration_fulfillment(
    disposable_need_clock_db: str,
) -> None:
    """Migration provenance rebases the baseline before later events replay."""

    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM schema_migrations WHERE version = '100'")
            cur.execute("DELETE FROM character_need_states")
            cur.execute("DELETE FROM chunk_metadata")
            _set_base_timestamp(cur, STORY_BASE)
            base_chunk = _insert_chunk_at(cur, STORY_BASE)
            entity_id = _insert_character(cur, "Post-Migration Fulfillment")
            cur.execute(
                """
                UPDATE character_need_states
                SET last_evaluated_at = %s
                WHERE character_entity_id = %s
                """,
                (POISONED_WALL_TIME, entity_id),
            )
            base_checkpoint_id = capture_state_checkpoint_sync(
                cur,
                chunk_id=base_chunk,
                label="manual",
            )
            assert base_checkpoint_id is not None

    notices = _apply_migration_100(disposable_need_clock_db)
    assert (
        "need-clock reconciliation: last_evaluated_at rows=5, "
        "last_fulfilled_at rows=0"
    ) in "".join(notices)

    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            target_chunk = _insert_chunk_at(cur, STORY_ANCHOR)
            fulfillment = {"type": "hunger", "discharge_debt": 0.0}
            _apply_need_fulfillment_sync(
                cur,
                actor_entity_id=entity_id,
                fulfillment=fulfillment,
                template_id="issue_640_post_migration_fulfillment",
                source_chunk_id=target_chunk,
                need_tuning=load_need_tuning(),
            )
            _insert_need_resolution(
                cur,
                chunk_id=target_chunk,
                entity_id=entity_id,
                template_id="issue_640_post_migration_fulfillment",
                fulfillment=fulfillment,
            )
            target_checkpoint_id = capture_state_checkpoint_sync(
                cur,
                chunk_id=target_chunk,
                label="manual",
            )
            assert target_checkpoint_id is not None

            reconstructed = reconstruct_state_at_sync(
                cur,
                target_chunk,
                base_checkpoint_id=base_checkpoint_id,
                target_checkpoint_id=target_checkpoint_id,
            )
            verdict = next(
                item
                for item in verify_checkpoints_sync(cur)
                if item.base_checkpoint_id == base_checkpoint_id
                and item.target_checkpoint_id == target_checkpoint_id
            )

    hunger = next(
        row
        for row in reconstructed.state["character_need_states"]
        if row["character_entity_id"] == entity_id and row["need_type"] == "hunger"
    )
    assert datetime.fromisoformat(hunger["last_evaluated_at"]) == STORY_ANCHOR
    assert datetime.fromisoformat(hunger["last_fulfilled_at"]) == STORY_ANCHOR
    assert verdict.drifts == []


def test_replay_uses_marker_result_for_overlapping_post_migration_chunk(
    disposable_need_clock_db: str,
) -> None:
    """A pre-migration transaction timestamp cannot expand migration authority."""

    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM schema_migrations WHERE version = '100'")
            cur.execute("DELETE FROM character_need_states")
            cur.execute("DELETE FROM chunk_metadata")
            _set_base_timestamp(cur, STORY_BASE)
            base_chunk = _insert_chunk_at(cur, STORY_BASE)
            entity_id = _insert_character(cur, "Overlapping Chunk Boundary")
            cur.execute(
                """
                UPDATE character_need_states
                SET last_evaluated_at = %s
                WHERE character_entity_id = %s
                """,
                (POISONED_WALL_TIME, entity_id),
            )
            base_checkpoint_id = capture_state_checkpoint_sync(
                cur,
                chunk_id=base_chunk,
                label="manual",
            )
            assert base_checkpoint_id is not None

    overlap = _connect(disposable_need_clock_db)
    try:
        with overlap.cursor() as cur:
            target_chunk = _insert_chunk_at(cur, STORY_ANCHOR)
        notices = _apply_migration_100(disposable_need_clock_db)
        assert (
            "need-clock reconciliation: last_evaluated_at rows=5, "
            "last_fulfilled_at rows=0"
        ) in "".join(notices)
        overlap.commit()
    except Exception:
        overlap.rollback()
        raise
    finally:
        overlap.close()

    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            target_checkpoint_id = capture_state_checkpoint_sync(
                cur,
                chunk_id=target_chunk,
                label="manual",
            )
            assert target_checkpoint_id is not None
            cur.execute(
                """
                SELECT DISTINCT last_evaluated_at
                FROM character_need_states
                WHERE character_entity_id = %s
                """,
                (entity_id,),
            )
            assert cur.fetchall() == [(STORY_BASE,)]
            verdict = next(
                item
                for item in verify_checkpoints_sync(cur)
                if item.base_checkpoint_id == base_checkpoint_id
                and item.target_checkpoint_id == target_checkpoint_id
            )

    assert verdict.drifts == []


def test_markerless_null_clock_mismatch_is_a_field_level_remainder(
    disposable_need_clock_db: str,
) -> None:
    """Current-rule replay skips only the markerless value it cannot derive."""

    _apply_migration_100(disposable_need_clock_db)
    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM character_need_states")
            cur.execute("DELETE FROM chunk_metadata")
            _set_base_timestamp(cur, STORY_BASE)
            base_chunk = _insert_chunk_at(cur, STORY_BASE)
            entity_id = _insert_character(cur, "Markerless NULL Clock")
            base_checkpoint_id = capture_state_checkpoint_sync(
                cur,
                chunk_id=base_chunk,
                label="manual",
            )
            assert base_checkpoint_id is not None

    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            _insert_chunk_at(cur, STORY_ANCHOR)
            target_chunk = _insert_atemporal_chunk(cur)
            fulfillment = {"type": "thirst", "discharge_debt": 1.0}
            _apply_need_fulfillment_sync(
                cur,
                actor_entity_id=entity_id,
                fulfillment=fulfillment,
                template_id="issue_640_markerless_null_clock",
                source_chunk_id=target_chunk,
                need_tuning=load_need_tuning(),
            )
            _insert_need_resolution(
                cur,
                chunk_id=target_chunk,
                entity_id=entity_id,
                template_id="issue_640_markerless_null_clock",
                fulfillment=fulfillment,
            )
            in_domain_legacy_value = STORY_BASE + timedelta(minutes=30)
            cur.execute(
                """
                UPDATE character_need_states
                SET last_evaluated_at = %s,
                    metadata = metadata - 'reconciled_by'
                                        - 'reconciled_last_evaluated_from'
                                        - 'reconciled_last_evaluated_to'
                                        - 'reconciled_last_fulfilled_from'
                                        - 'reconciled_last_fulfilled_to'
                WHERE character_entity_id = %s
                  AND need_type = 'thirst'
                """,
                (in_domain_legacy_value, entity_id),
            )
            target_checkpoint_id = capture_state_checkpoint_sync(
                cur,
                chunk_id=target_chunk,
                label="manual",
            )
            assert target_checkpoint_id is not None

            reconstructed = reconstruct_state_at_sync(
                cur,
                target_chunk,
                base_checkpoint_id=base_checkpoint_id,
                target_checkpoint_id=target_checkpoint_id,
            )
            verdict = next(
                item
                for item in verify_checkpoints_sync(cur)
                if item.base_checkpoint_id == base_checkpoint_id
                and item.target_checkpoint_id == target_checkpoint_id
            )

    row_key = f"{entity_id}:thirst"
    need_remainder = {
        item
        for item in reconstructed.unreproducible
        if item[0] == "character_need_states" and item[1] == row_key
    }
    assert need_remainder == {("character_need_states", row_key, "last_evaluated_at")}
    assert verdict.drifts == []
    assert verdict.skipped_unreproducible >= 1


def test_replay_reconstructs_post_migration_trigger_anchor(
    disposable_need_clock_db: str,
) -> None:
    """A post-100 applicability reset has a ledger-reconstructable anchor."""

    _apply_migration_100(disposable_need_clock_db)
    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM character_need_states")
            cur.execute("DELETE FROM chunk_metadata")
            _set_base_timestamp(cur, STORY_BASE)
            base_chunk = _insert_chunk_at(cur, STORY_BASE)
            entity_id = _insert_character(cur, "Replay Trigger Character")
            cur.execute("SELECT id FROM tags WHERE tag = 'inorganic'")
            immunity_tag_id = int(cur.fetchone()[0])
            cur.execute(
                """
                INSERT INTO entity_tags (
                    entity_id, tag_id, source_kind, source_chunk_id
                ) VALUES (%s, %s, 'template', %s)
                RETURNING id
                """,
                (entity_id, immunity_tag_id, base_chunk),
            )
            entity_tag_id = int(cur.fetchone()[0])
            base_checkpoint_id = capture_state_checkpoint_sync(
                cur,
                chunk_id=base_chunk,
                label="manual",
            )
            assert base_checkpoint_id is not None

    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            target_chunk = _insert_chunk_at(cur, STORY_ANCHOR)
            cur.execute(
                "UPDATE entity_tags SET cleared_at = now() WHERE id = %s",
                (entity_tag_id,),
            )
            cur.execute(
                """
                INSERT INTO tag_clearance_log (
                    entity_tag_id, mechanism, source_chunk_id
                ) VALUES (%s, 'authored', %s)
                """,
                (entity_tag_id, target_chunk),
            )
            target_checkpoint_id = capture_state_checkpoint_sync(
                cur,
                chunk_id=target_chunk,
                label="manual",
            )
            assert target_checkpoint_id is not None

            reconstructed = reconstruct_state_at_sync(
                cur,
                target_chunk,
                base_checkpoint_id=base_checkpoint_id,
                target_checkpoint_id=target_checkpoint_id,
            )
            hunger = next(
                row
                for row in reconstructed.state["character_need_states"]
                if row["character_entity_id"] == entity_id
                and row["need_type"] == "hunger"
            )
            verdict = next(
                item
                for item in verify_checkpoints_sync(cur)
                if item.base_checkpoint_id == base_checkpoint_id
                and item.target_checkpoint_id == target_checkpoint_id
            )

    assert (
        datetime.fromisoformat(hunger["last_evaluated_at"]).astimezone(timezone.utc)
        == STORY_ANCHOR
    )
    assert (
        "character_need_states",
        f"{entity_id}:hunger",
        "last_evaluated_at",
    ) not in reconstructed.unreproducible
    assert verdict.drifts == []


def test_atemporal_need_tick_and_replay_use_primary_world_clock(
    disposable_need_clock_db: str,
) -> None:
    """NULL layer time uses the primary clock in both production and replay."""

    _apply_migration_100(disposable_need_clock_db)
    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM character_need_states")
            cur.execute("DELETE FROM chunk_metadata")
            _set_base_timestamp(cur, STORY_BASE)
            base_chunk = _insert_chunk_at(cur, STORY_ANCHOR)
            entity_id = _insert_character(cur, "Atemporal Tick Character")
            base_checkpoint_id = capture_state_checkpoint_sync(
                cur,
                chunk_id=base_chunk,
                label="manual",
            )
            assert base_checkpoint_id is not None

    with _transaction(disposable_need_clock_db) as conn:
        with conn.cursor() as cur:
            target_chunk = _insert_atemporal_chunk(cur)
            fulfillment = {"type": "thirst", "discharge_debt": 1.0}
            _apply_need_fulfillment_sync(
                cur,
                actor_entity_id=entity_id,
                fulfillment=fulfillment,
                template_id="issue_640_atemporal_tick",
                source_chunk_id=target_chunk,
                need_tuning=load_need_tuning(),
            )
            cur.execute(
                """
                INSERT INTO orrery_resolutions (
                    tick_chunk_id, template_id, binding_hash, actor_entity_id,
                    priority, magnitude, state_delta
                ) VALUES (
                    %s, 'issue_640_atemporal_tick', 'issue-640-atemporal',
                    %s, 50, 0.5, %s::jsonb
                )
                """,
                (
                    target_chunk,
                    entity_id,
                    json.dumps({"need.fulfill": fulfillment}),
                ),
            )
            target_checkpoint_id = capture_state_checkpoint_sync(
                cur,
                chunk_id=target_chunk,
                label="manual",
            )
            assert target_checkpoint_id is not None

            reconstructed = reconstruct_state_at_sync(
                cur,
                target_chunk,
                base_checkpoint_id=base_checkpoint_id,
                target_checkpoint_id=target_checkpoint_id,
            )
            verdict = next(
                item
                for item in verify_checkpoints_sync(cur)
                if item.base_checkpoint_id == base_checkpoint_id
                and item.target_checkpoint_id == target_checkpoint_id
            )
            cur.execute(
                """
                SELECT last_evaluated_at, last_fulfilled_at
                FROM character_need_states
                WHERE character_entity_id = %s
                  AND need_type = 'thirst'
                """,
                (entity_id,),
            )
            live_evaluated_at, live_fulfilled_at = cur.fetchone()

    assert live_evaluated_at == STORY_ANCHOR
    assert live_fulfilled_at == STORY_ANCHOR
    row_key = f"{entity_id}:thirst"
    for column in ("last_evaluated_at", "last_fulfilled_at", "debt_score"):
        assert (
            "character_need_states",
            row_key,
            column,
        ) not in reconstructed.unreproducible
    assert verdict.drifts == []


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
