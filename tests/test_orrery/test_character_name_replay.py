"""Canonical name history remains explicit across old and new checkpoints."""

from copy import deepcopy

import pytest

from nexus.agents.orrery.reconstruction import (
    capture_state_checkpoint_sync,
    log_state_delta_sync,
)
from nexus.agents.orrery.retrograde_maturation import _load_job_context
from nexus.agents.orrery.replay import (
    ReplayResult,
    _diff_section,
    _seed_checkpoint_character_names,
    reconstruct_state_at_sync,
    verify_checkpoints_sync,
)
from nexus.config.settings_models import OrreryRetrogradeMaturationSettings
from tests.pg_fixtures import connect
from tests.test_presence_roster_pg import commit_wire, wire
from tests.test_presence_roster_pg import roster_database as _roster_database


name_replay_database = _roster_database


def test_legacy_checkpoint_name_is_unknown_without_changing_recorded_names() -> None:
    characters = {
        3: {"id": 3, "entity_id": 9},
        4: {"id": 4, "entity_id": 10, "name": "Anika Sayegh"},
        5: {"id": 5, "entity_id": 11, "name": None},
    }
    result = ReplayResult(4, 1, 3, {})

    _seed_checkpoint_character_names(characters, result)

    assert characters[3]["name"] is None
    assert characters[4]["name"] == "Anika Sayegh"
    assert characters[5]["name"] is None
    assert result.unreproducible == {("characters", "3", "name")}
    assert result.approximate_sections == {"characters"}
    assert "unknown until a ledgered name write" in result.notes["characters"][0]


@pytest.mark.parametrize("legacy_side", ["expected", "actual"])
def test_checkpoint_comparison_counts_unrecorded_names_as_unknown(
    legacy_side: str,
) -> None:
    expected = [{"id": 3, "name": "Anika Sayegh", "current_activity": "Waiting"}]
    actual = deepcopy(expected)
    (expected if legacy_side == "expected" else actual)[0].pop("name")
    actual[0]["current_activity"] = "Walking"

    drifts, skipped = _diff_section(
        "characters", expected, actual, lambda row: row["id"], set(), set()
    )

    assert skipped == 1
    assert len(drifts) == 1
    assert drifts[0].column == "current_activity"


@pytest.mark.parametrize("recorded_name", [None, "Unnamed witness"])
def test_checkpoint_comparison_detects_unledgered_name_drift(recorded_name) -> None:
    drifts, skipped = _diff_section(
        "characters",
        [{"id": 3, "name": "Anika Sayegh"}],
        [{"id": 3, "name": recorded_name}],
        lambda row: row["id"],
        set(),
        set(),
    )

    assert skipped == 0
    assert len(drifts) == 1
    assert drifts[0].column == "name"


@pytest.mark.requires_postgres
@pytest.mark.parametrize("legacy_base", [False, True])
def test_name_replay_round_trip_preserves_history_and_legacy_uncertainty(
    name_replay_database, legacy_base: bool
) -> None:
    """Exercise real checkpoint and scalar-ledger SQL on a disposable database."""
    dbname, ids, _ = name_replay_database
    character_id = ids["Remote Friend"]
    before = commit_wire(dbname, 0, wire("The unnamed witness waits in the hall."))
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE characters SET name = 'Unnamed witness' WHERE id = %s "
            "RETURNING entity_id",
            (character_id,),
        )
        entity_id = cur.fetchone()[0]
        base_id = capture_state_checkpoint_sync(cur, chunk_id=before, label="manual")
        assert base_id is not None
        cur.execute("SELECT state FROM state_checkpoints WHERE id = %s", (base_id,))
        base = cur.fetchone()[0]
        assert (
            next(row for row in base["characters"] if row["id"] == character_id)["name"]
            == "Unnamed witness"
        )
        if legacy_base:
            cur.execute(
                "UPDATE state_checkpoints SET state = jsonb_set(state, "
                "'{characters}', (SELECT jsonb_agg(item - 'name') "
                "FROM jsonb_array_elements(state->'characters') AS item)) "
                "WHERE id = %s",
                (base_id,),
            )

    after = commit_wire(dbname, before, wire('The witness says, "Anika Sayegh."'))
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE characters SET name = 'Anika Sayegh' WHERE id = %s",
            (character_id,),
        )
        log_state_delta_sync(
            cur,
            source_chunk_id=after,
            writer="skald_state_update",
            entity_id=entity_id,
            field="characters.name",
            old_value="Unnamed witness",
            new_value="Anika Sayegh",
        )
        target_id = capture_state_checkpoint_sync(cur, chunk_id=after, label="manual")
        assert target_id is not None
        # A later live name cannot become the historical answer.
        cur.execute(
            "UPDATE characters SET name = 'A later name' WHERE id = %s",
            (character_id,),
        )
        earlier = reconstruct_state_at_sync(cur, before, base_checkpoint_id=base_id)
        earlier_character = next(
            row for row in earlier.state["characters"] if row["id"] == character_id
        )
        assert earlier_character["name"] == (None if legacy_base else "Unnamed witness")
        assert (
            ("characters", str(character_id), "name") in earlier.unreproducible
        ) is (legacy_base)
        revealed = reconstruct_state_at_sync(cur, after, base_checkpoint_id=base_id)
        revealed_character = next(
            row for row in revealed.state["characters"] if row["id"] == character_id
        )
        assert revealed_character["entity_id"] == entity_id
        assert revealed_character["name"] == "Anika Sayegh"
        assert ("characters", str(character_id), "name") not in revealed.unreproducible
        verdict = next(
            verdict
            for verdict in verify_checkpoints_sync(cur)
            if verdict.base_checkpoint_id == base_id
            and verdict.target_checkpoint_id == target_id
        )
        assert not [drift for drift in verdict.drifts if drift.column == "name"]


@pytest.mark.requires_postgres
def test_maturation_context_excludes_renamed_target_by_identity(
    name_replay_database,
) -> None:
    """A pending job's historical label must not make its target its own anchor."""
    dbname, ids, place_id = name_replay_database
    character_id = ids["Remote Friend"]
    chunk_id = commit_wire(dbname, 0, wire("The witness waits in the hall."))
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE characters SET name = 'Anika Sayegh' WHERE id = %s "
            "RETURNING entity_id",
            (character_id,),
        )
        entity_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO chunk_character_references "
            "(chunk_id, character_id, reference) "
            "VALUES (%s, %s, 'present') ON CONFLICT DO NOTHING",
            (chunk_id, character_id),
        )
        # A place with the old label is a different identity and remains an anchor.
        cur.execute(
            "UPDATE places SET name = 'Unnamed witness' WHERE id = %s", (place_id,)
        )
        context = _load_job_context(
            cur,
            row={
                "job_id": 1,
                "entity_id": entity_id,
                "entity_kind": "character",
                "entity_subtype_id": character_id,
                "entity_name": "Unnamed witness",
                "requesting_chunk_id": chunk_id,
            },
            cfg=OrreryRetrogradeMaturationSettings(),
        )

    anchors = {(entry["kind"], entry["name"]) for entry in context["scene_entities"]}
    assert ("character", "Anika Sayegh") not in anchors
    assert ("place", "Unnamed witness") in anchors
