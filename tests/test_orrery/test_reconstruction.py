"""Live tests for the reconstruction-sufficiency layer (migration 065).

Real writers and real triggers against a fixture-owned template clone seeded
by ``seed_checkpointed_story``, inside always-rolled-back transactions. Pins
the issue #426 decisions:

- 7b: every Skald-side scalar write lands in ``state_delta_log``, chunk-keyed.
- 7c: checkpoints capture every section of the mutable state surface and are
  idempotent per (chunk, label).
- 7d: the relationship-versioning triggers write pre-images on UPDATE and
  DELETE with chunk attribution from the transaction-local setting — and
  NULL attribution when a writer forgets, never a silent skip.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pytest

from nexus.agents.logon.apex_schema import (
    CharacterStateUpdate,
    LocationStateUpdate,
    StateUpdates,
)
from nexus.agents.orrery.reconstruction import (
    CHECKPOINT_SECTIONS,
    MATURATION_JOBS_CONTROL_KEY,
    capture_state_checkpoint_sync,
    set_commit_chunk_attribution_sync,
)
from nexus.api.commit_handler_sync import apply_state_updates_sync
from tests.pg_fixtures import connect, disposable_slot_database
from tests.test_orrery.checkpointed_story_support import seed_checkpointed_story

pytestmark = pytest.mark.requires_postgres


@pytest.fixture(scope="module")
def reconstruction_db() -> Iterator[str]:
    """Own one seeded, checkpointed template clone for the whole module."""

    with disposable_slot_database("qa640_reconstruction") as dbname:
        seed_checkpointed_story(dbname)
        yield dbname


def _head_chunk(cur: Any) -> int:
    cur.execute("SELECT max(id) FROM narrative_chunks")
    head = cur.fetchone()[0]
    assert head is not None, "seed_checkpointed_story seeds a head chunk"
    return int(head)


def _connect(dbname: str) -> Any:
    conn = connect(dbname)
    with conn.cursor() as cur:
        cur.execute(Path("migrations/074_plan_relocation_projects.sql").read_text())
        cur.execute("CREATE TEMP TABLE backstory_secrets (id bigint) ON COMMIT DROP")
    return conn


def test_checkpoint_captures_every_section_and_is_idempotent(
    reconstruction_db: str,
) -> None:
    conn = _connect(reconstruction_db)
    try:
        with conn.cursor() as cur:
            chunk_id = _head_chunk(cur)
            checkpoint_id = capture_state_checkpoint_sync(
                cur, chunk_id=chunk_id, label="manual"
            )
            assert checkpoint_id is not None

            cur.execute(
                "SELECT state FROM state_checkpoints WHERE id = %s",
                (checkpoint_id,),
            )
            state = cur.fetchone()[0]
            if isinstance(state, str):
                state = json.loads(state)
            assert set(state) == set(CHECKPOINT_SECTIONS) | {
                MATURATION_JOBS_CONTROL_KEY
            }
            assert isinstance(state[MATURATION_JOBS_CONTROL_KEY], list)

            cur.execute("SELECT count(*) FROM entity_tags WHERE cleared_at IS NULL")
            active_tags = cur.fetchone()[0]
            assert len(state["entity_tags"]) == active_tags
            assert active_tags > 0, "seed_checkpointed_story seeds an active tag"
            assert state["characters"], "character scalars must be captured"
            cur.execute("SELECT count(*) FROM entities")
            assert len(state["entities"]) == cur.fetchone()[0]
            assert all(set(row) == {"id", "is_active"} for row in state["entities"])

            # Idempotent per (chunk, label): re-commit of the same tick
            # cannot duplicate the snapshot.
            assert (
                capture_state_checkpoint_sync(cur, chunk_id=chunk_id, label="manual")
                is None
            )
        with conn.cursor() as cur:
            with pytest.raises(ValueError, match="Unknown checkpoint label"):
                capture_state_checkpoint_sync(cur, chunk_id=chunk_id, label="hourly")
    finally:
        conn.rollback()
        conn.close()


def test_skald_state_updates_are_ledgered(reconstruction_db: str) -> None:
    conn = _connect(reconstruction_db)
    try:
        with conn.cursor() as cur:
            chunk_id = _head_chunk(cur)
            cur.execute("SELECT COALESCE(max(id), 0) FROM state_delta_log")
            state_delta_baseline = cur.fetchone()[0]
            cur.execute(
                """
                SELECT c.id, c.entity_id FROM characters c
                WHERE c.entity_id IS NOT NULL ORDER BY c.id LIMIT 1
                """
            )
            character = cur.fetchone()
            assert character is not None, "seed_checkpointed_story seeds characters"
            character_id, entity_id = character
            cur.execute("SELECT id, entity_id FROM places ORDER BY id LIMIT 1")
            place = cur.fetchone()
            assert place is not None, "seed_checkpointed_story seeds places"
            place_id, place_entity_id = place

        apply_state_updates_sync(
            conn,
            StateUpdates(
                characters=[
                    CharacterStateUpdate(
                        character_id=character_id,
                        character_name="probe",
                        current_activity="ledger probe activity",
                        current_location=place_id,
                    )
                ],
                locations=[
                    LocationStateUpdate(
                        place_id=place_id,
                        place_name="probe",
                        current_conditions="ledger probe conditions",
                    )
                ],
            ),
            source_chunk_id=chunk_id,
        )

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT field, entity_id, new_value
                FROM state_delta_log
                WHERE source_chunk_id = %s AND writer = 'skald_state_update'
                  AND id > %s
                ORDER BY id
                """,
                (chunk_id, state_delta_baseline),
            )
            rows = cur.fetchall()
        by_field = {row[0]: row for row in rows}
        assert set(by_field) == {
            "characters.current_activity",
            "characters.current_location",
            "places.current_status",
        }
        assert by_field["characters.current_activity"][1] == entity_id
        assert by_field["characters.current_activity"][2] == "ledger probe activity"
        assert by_field["characters.current_location"][2] == place_id
        assert by_field["places.current_status"][1] == place_entity_id
    finally:
        conn.rollback()
        conn.close()


def test_relationship_triggers_version_updates_and_deletes(
    reconstruction_db: str,
) -> None:
    conn = _connect(reconstruction_db)
    try:
        with conn.cursor() as cur:
            chunk_id = _head_chunk(cur)
            set_commit_chunk_attribution_sync(cur, chunk_id)

            cur.execute("SET LOCAL nexus.write_producer = 'manual'")
            cur.execute(
                """
                UPDATE character_relationships
                SET dynamic = dynamic || ' [version probe]'
                WHERE (character1_id, character2_id) IN (
                    SELECT character1_id, character2_id
                    FROM character_relationships LIMIT 1
                )
                RETURNING character1_id, character2_id
                """
            )
            updated = cur.fetchone()
            assert (
                updated is not None
            ), "seed_checkpointed_story seeds a relationship to version"
            c1, c2 = updated
            cur.execute(
                """
                SELECT operation, source_chunk_id, old_row
                FROM relationship_versions
                WHERE relationship_table = 'character_relationships'
                ORDER BY id DESC LIMIT 1
                """
            )
            operation, source_chunk_id, old_row = cur.fetchone()
            assert operation == "update"
            assert source_chunk_id == chunk_id
            assert int(old_row["character1_id"]) == c1
            assert (
                "[version probe]" not in old_row["dynamic"]
            ), "trigger must capture the PRE-image"

            cur.execute("SET LOCAL nexus.write_producer = 'manual'")
            cur.execute(
                """
                DELETE FROM character_relationships
                WHERE character1_id = %s AND character2_id = %s
                """,
                (c1, c2),
            )
            cur.execute(
                """
                SELECT operation FROM relationship_versions
                WHERE relationship_table = 'character_relationships'
                ORDER BY id DESC LIMIT 1
                """
            )
            assert cur.fetchone()[0] == "delete"
    finally:
        conn.rollback()
        conn.close()


def test_unattributed_relationship_write_versions_with_null_chunk(
    reconstruction_db: str,
) -> None:
    """A manual writer without source-chunk attribution is versioned with NULL
    chunk. Explicit producer attribution is still required."""

    conn = _connect(reconstruction_db)
    try:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL nexus.write_producer = 'manual'")
            cur.execute(
                """
                UPDATE character_relationships
                SET dynamic = dynamic || ' [unattributed]'
                WHERE (character1_id, character2_id) IN (
                    SELECT character1_id, character2_id
                    FROM character_relationships LIMIT 1
                )
                """
            )
            cur.execute(
                """
                SELECT source_chunk_id FROM relationship_versions
                ORDER BY id DESC LIMIT 1
                """
            )
            assert cur.fetchone()[0] is None
    finally:
        conn.rollback()
        conn.close()


def test_migration_genesis_sections_mirror_checkpoint_sections() -> None:
    """Checkpoint sections are introduced by their owning migrations."""

    from pathlib import Path

    migration = Path("migrations/065_reconstructability.sql").read_text()
    genesis = migration[migration.index("jsonb_build_object") :]
    additive = Path("migrations/074_plan_relocation_projects.sql").read_text()
    propagation = Path("migrations/083_claim_propagation_ledger.sql").read_text()
    backstory = Path("migrations/091_backstory_secrets.sql").read_text()
    genesis_sources = genesis + additive + propagation + backstory
    for section in CHECKPOINT_SECTIONS:
        assert (
            f"'{section}'" in genesis_sources
        ), f"migration genesis/extension SQL lacks section {section!r}"
    import re

    migration_sections = set(re.findall(r"'(\w+)', \(SELECT", genesis))
    migration_sections.update(re.findall(r"'(character_project_states)', \(", additive))
    if "'claim_awareness'" in propagation:
        migration_sections.add("claim_awareness")
    if "'backstory_secrets'" in backstory:
        migration_sections.add("backstory_secrets")
    assert migration_sections == set(CHECKPOINT_SECTIONS)
