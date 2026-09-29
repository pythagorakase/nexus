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
from tests.pg_fixtures import (
    connect,
    seed_character,
    seed_entity_tag,
    seed_place,
    seed_protagonist,
    seed_relationship,
    seed_story_clock,
)

BASE_TIMESTAMP = datetime(2073, 7, 31, 12, 0, tzinfo=timezone.utc)
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
    """

    home_place_id, _ = seed_place(
        dbname, name="Replay Harbor", longitude=-70.2553, latitude=43.6591
    )
    away_place_id, _ = seed_place(
        dbname, name="Replay Market", longitude=-71.0589, latitude=42.3601
    )
    protagonist_character_id, protagonist_entity_id = seed_protagonist(
        dbname,
        name="Replay Protagonist",
        base_timestamp=BASE_TIMESTAMP.isoformat(),
        current_location=home_place_id,
    )
    head_chunk_id = seed_story_clock(dbname, world_time=HEAD_WORLD_TIME)
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
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        genesis_checkpoint_id = capture_state_checkpoint_sync(
            cur, chunk_id=head_chunk_id, label="genesis"
        )
    assert genesis_checkpoint_id is not None, "genesis checkpoint already existed"
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
