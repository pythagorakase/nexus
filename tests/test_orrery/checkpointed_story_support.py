"""A small seeded, checkpointed story for replay and reconstruction tests.

Replay and reconstruction tests fabricate post-checkpoint history inside
rolled-back transactions. They need a story underneath: a player with need
rows, other characters, located places, relationships, an active tag, a head
chunk on the canonical clock, and a genesis checkpoint that bounds the
instrumentation era. ``seed_checkpointed_story`` commits exactly that into a
fixture-owned template clone through the shared ``tests.pg_fixtures`` seeds.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone

from nexus.agents.orrery.reconstruction import capture_state_checkpoint_sync
from nexus.agents.orrery.replay import reconstruct_state_at_sync
from tests.pg_fixtures import (
    connect,
    require_disposable_target,
    seed_character,
    seed_entity_tag,
    seed_place,
    seed_protagonist,
    seed_relationship,
    seed_story_clock,
    seed_zone,
)

# The first story-clock instant: base_timestamp and the bootstrap head chunk.
HEAD_WORLD_TIME = datetime(2073, 8, 1, 12, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class CheckpointedStory:
    """IDs of the rows ``seed_checkpointed_story`` committed."""

    protagonist_character_id: int
    protagonist_entity_id: int
    confidant_character_id: int
    confidant_entity_id: int
    rival_character_id: int
    rival_entity_id: int
    home_place_id: int
    away_place_id: int
    active_tag_row_id: int
    head_chunk_id: int
    genesis_checkpoint_id: int


def seed_checkpointed_story(dbname: str) -> CheckpointedStory:
    """Commit a three-character, two-place story with a genesis checkpoint.

    The protagonist (lowest character ID) is located at the home place and
    has no project. Two directed relationships chain protagonist, confidant,
    and rival, which leaves the protagonist/rival pair free. The confidant
    carries one active non-severity tag. The head chunk sits on the canonical
    clock at ``HEAD_WORLD_TIME``, and the genesis checkpoint is taken there.

    Every row is committed before the head chunk. Replay drops a relationship
    version with no source chunk when its ``created_at`` is later than the
    target chunk's (``replay.py`` gap 2), so rows seeded after the head chunk
    would vanish from a reconstruction at the head that the checkpoint still
    holds. The protagonist sets ``base_timestamp`` to ``HEAD_WORLD_TIME``
    first (the need-clock anchor for the other characters and the tag), and
    ``seed_story_clock`` runs last, just before the checkpoint, seeding the
    bootstrap chunk at that same instant: ``base_timestamp`` is the clock at
    the end of the bootstrap chunk, which elapses no time. Reconstruction at
    the head is then asserted to hold the checkpoint's relationships.
    """

    require_disposable_target(dbname)
    seed_zone(
        dbname,
        name="Replay Coast",
        min_longitude=-72.0,
        min_latitude=42.0,
        max_longitude=-69.0,
        max_latitude=44.5,
    )
    home_place_id, _ = seed_place(
        dbname, name="Replay Harbor", longitude=-70.2553, latitude=43.6591
    )
    away_place_id, _ = seed_place(
        dbname, name="Replay Market", longitude=-71.0589, latitude=42.3601
    )
    protagonist_character_id, protagonist_entity_id = seed_protagonist(
        dbname,
        name="Replay Protagonist",
        base_timestamp=HEAD_WORLD_TIME.isoformat(),
        current_location=home_place_id,
    )
    confidant_character_id, confidant_entity_id = seed_character(
        dbname, name="Replay Confidant", current_location=home_place_id
    )
    rival_character_id, rival_entity_id = seed_character(
        dbname, name="Replay Rival", current_location=away_place_id
    )
    seed_relationship(
        dbname,
        subject_character_id=protagonist_character_id,
        object_character_id=confidant_character_id,
        relationship_type="ally",
        emotional_valence="+3|trusting",
    )
    seed_relationship(
        dbname,
        subject_character_id=confidant_character_id,
        object_character_id=rival_character_id,
        relationship_type="rival",
        emotional_valence="-3|resentful",
    )
    active_tag_row_id = seed_entity_tag(
        dbname, entity_id=confidant_entity_id, tag="kin_protector"
    )
    head_chunk_id = seed_story_clock(dbname, world_time=HEAD_WORLD_TIME)
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        genesis_checkpoint_id = capture_state_checkpoint_sync(
            cur, chunk_id=head_chunk_id, label="genesis"
        )
    assert genesis_checkpoint_id is not None, "genesis checkpoint already existed"
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT jsonb_array_length(state->'character_relationships') "
            "FROM state_checkpoints WHERE id = %s",
            (genesis_checkpoint_id,),
        )
        checkpoint_row = cur.fetchone()
        assert checkpoint_row is not None and checkpoint_row[0] == 2, (
            f"seed_checkpointed_story: genesis checkpoint holds {checkpoint_row!r} "
            "relationships, expected 2"
        )
        replayed = reconstruct_state_at_sync(cur, head_chunk_id)
        conn.rollback()
    assert len(replayed.state["character_relationships"]) == checkpoint_row[0], (
        "seed_checkpointed_story: reconstruction at the head chunk holds "
        f"{len(replayed.state['character_relationships'])} relationships, but the "
        f"genesis checkpoint holds {checkpoint_row[0]}; a seed row landed after "
        "the head chunk"
    )
    return CheckpointedStory(
        protagonist_character_id=protagonist_character_id,
        protagonist_entity_id=protagonist_entity_id,
        confidant_character_id=confidant_character_id,
        confidant_entity_id=confidant_entity_id,
        rival_character_id=rival_character_id,
        rival_entity_id=rival_entity_id,
        home_place_id=home_place_id,
        away_place_id=away_place_id,
        active_tag_row_id=active_tag_row_id,
        head_chunk_id=head_chunk_id,
        genesis_checkpoint_id=genesis_checkpoint_id,
    )
