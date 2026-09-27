"""Return recap clock and route on disposable slot clones (issue #832).

Requires template narrative_chunks, chunk_metadata, incubator, characters,
places, the chunk reference tables and global_variables. Fixtures own every
write; no provider is called.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import closing
from datetime import datetime
from typing import Any, Optional

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from psycopg2.extras import Json

from nexus.agents.orrery.retrograde_markers import RETROGRADE_PROLOGUE_MARKER
from nexus.api import narrative, reader_endpoints, slot_utils
from nexus.api.config_utils import get_max_choice_text_length
from nexus.api.return_recap import (
    RecapEvidenceError,
    RecapItem,
    ReturnRecap,
    SourceHandle,
    verify_recap_sources,
)
from nexus.config import load_settings
from nexus.memory.manager import empty_pass2_baseline
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    seed_committed_chunk,
    seed_protagonist,
)

pytestmark = pytest.mark.requires_postgres

SLOT = 5
DOOR_CHOICES = ["Open the door.", "Wait in silence."]
EDITED_DOOR = "Open the door slowly, listening first."
MEMORIAL_CHOICES = [
    "Close your hand around the brass key and follow Rook into the rain.",
    "Show Ren the warrant is premature and ask for an hour.",
    "Take Ivo's call on the viaduct stairs.",
]
LAST_ACTION = "Offer Rook the thumb-to-temple greeting."
EARLIER = "2026-01-01T00:00:00+00:00"


@pytest.fixture
def recap_slot(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[str, int]]:
    """Route slot 5 to a private clone with a canonical player."""
    with disposable_slot_database("qa832_recap") as dbname:
        slot_utils.VALID_DBNAMES.add(dbname)
        monkeypatch.setattr(slot_utils, "slot_dbname", lambda _slot: dbname)
        try:
            player_id, _ = seed_protagonist(
                dbname,
                name="Mara Vey",
                summary="Archive auditor who certified Elian Rook's death.",
            )
            yield dbname, player_id
        finally:
            slot_utils.VALID_DBNAMES.discard(dbname)


def _last_played(dbname: str) -> Optional[datetime]:
    """Read the recap clock through a fresh connection (committed state only)."""
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT last_played FROM global_variables WHERE id = true")
        return cur.fetchone()[0]


def _set_last_played(dbname: str, value: str) -> None:
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE global_variables SET last_played = %s WHERE id = true", (value,)
        )


def _choice_chunk(
    dbname: str,
    choices: list[str],
    *,
    scene: int,
    choice_text: Optional[str] = None,
    selected: Optional[int] = None,
) -> int:
    """Commit one chunk presenting ``choices``, optionally already answered."""
    chunk_id = seed_committed_chunk(
        dbname, raw_text=f"Scene {scene} prose.", scene=scene
    )
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE narrative_chunks SET choice_object = %s, choice_text = %s "
            "WHERE id = %s",
            (
                Json({"presented": choices, "selected": selected}),
                choice_text,
                chunk_id,
            ),
        )
    return chunk_id


def _record(chunk_id: int, **payload: Any) -> str:
    """Accept input on a committed chunk through the production writer."""
    return narrative._record_player_response_for_chunk(
        slot=SLOT,
        chunk_id=chunk_id,
        user_text=payload.get("user_text", ""),
        choice=payload.get("choice"),
        accept_fate=False,
        require_response=True,
    )


# ---------------------------------------------------------------------------
# The last_played writer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "recorded"),
    [
        ({"choice": 2}, "Wait in silence."),
        ({"choice": 1, "user_text": EDITED_DOOR}, EDITED_DOOR),
        ({"user_text": "Knock twice, then wait."}, "Knock twice, then wait."),
    ],
    ids=["choice", "edited-choice", "freeform"],
)
def test_accepted_action_moves_last_played(
    recap_slot: tuple[str, int], payload: dict[str, Any], recorded: str
) -> None:
    """A choice, an edited choice and free text each commit a fresh stamp."""
    dbname, _ = recap_slot
    chunk_id = _choice_chunk(dbname, DOOR_CHOICES, scene=1)
    _set_last_played(dbname, EARLIER)

    assert _record(chunk_id, **payload) == recorded

    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "SELECT choice_text, now() - last_played < interval '1 minute' "
            "FROM narrative_chunks, global_variables "
            "WHERE narrative_chunks.id = %s AND global_variables.id = true",
            (chunk_id,),
        )
        assert cur.fetchone() == (recorded, True)


def test_resubmitted_and_rejected_input_leaves_last_played(
    recap_slot: tuple[str, int],
) -> None:
    """Only a newly accepted action moves the clock."""
    dbname, _ = recap_slot
    answered = _choice_chunk(dbname, DOOR_CHOICES, scene=1)
    assert _record(answered, choice=1, user_text=EDITED_DOOR) == EDITED_DOOR
    open_chunk = _choice_chunk(dbname, DOOR_CHOICES, scene=2)
    _set_last_played(dbname, EARLIER)
    stamped = _last_played(dbname)

    # The same edited choice again is idempotent.
    assert _record(answered, choice=1, user_text=EDITED_DOOR) == EDITED_DOOR
    assert _last_played(dbname) == stamped

    rejected: list[tuple[int, dict[str, Any], int]] = [
        (answered, {"choice": 1}, 409),
        (open_chunk, {"choice": 9}, 400),
        (open_chunk, {}, 400),
        (open_chunk, {"user_text": "o" * (get_max_choice_text_length() + 1)}, 400),
    ]
    for chunk_id, payload, status in rejected:
        with pytest.raises(HTTPException) as exc:
            _record(chunk_id, **payload)
        assert exc.value.status_code == status
        assert _last_played(dbname) == stamped


def test_incubator_acceptance_stamps_inside_the_callers_transaction(
    recap_slot: tuple[str, int],
) -> None:
    """The pending-draft branch stamps on the caller's cursor, commit or not."""
    dbname, _ = recap_slot
    parent = seed_committed_chunk(dbname, raw_text="The platform waits.")
    session_id = str(uuid.uuid4())
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO incubator (
                id, chunk_id, parent_chunk_id, user_text, storyteller_text,
                generation_model, choice_object, choice_text,
                metadata_updates, entity_updates, reference_updates,
                orrery_proposal, orrery_adjudications, new_entities,
                lore_pass_baseline, session_id, llm_response_id, status
            ) VALUES (
                TRUE, %s, %s, %s, %s, %s, %s, NULL,
                %s, %s, %s, NULL, %s, %s, %s, %s, %s, 'provisional'
            )
            """,
            (
                parent + 1,
                parent,
                "Approach the door.",
                "The door waits.",
                "recap-fixture",
                Json({"presented": DOOR_CHOICES, "selected": None}),
                Json(
                    {
                        "chronology": {
                            "episode_transition": "continue",
                            "time_delta_minutes": 1,
                        },
                        "world_layer": "primary",
                    }
                ),
                Json({}),
                Json({"characters": [], "places": [], "factions": []}),
                Json([]),
                Json([]),
                Json(empty_pass2_baseline({}).model_dump(mode="json")),
                session_id,
                "recap-fixture",
            ),
        )
    _set_last_played(dbname, EARLIER)
    stamped = _last_played(dbname)

    def accept(conn: Any) -> str:
        return narrative._record_player_response_for_chunk(
            slot=SLOT,
            chunk_id=None,
            user_text=EDITED_DOOR,
            choice=1,
            accept_fate=False,
            require_response=True,
            connection=conn,
            incubator_session_id=session_id,
        )

    with closing(connect(dbname)) as conn:
        assert accept(conn) == EDITED_DOOR
        with conn.cursor() as cur:
            cur.execute("SELECT last_played FROM global_variables WHERE id = true")
            assert cur.fetchone()[0] != stamped
        # Uncommitted: nobody else sees the stamp, and rollback drops it.
        assert _last_played(dbname) == stamped
        conn.rollback()
        assert _last_played(dbname) == stamped

        assert accept(conn) == EDITED_DOOR
        conn.commit()
    assert _last_played(dbname) != stamped


# ---------------------------------------------------------------------------
# GET /api/narrative/recap on a seeded story
# ---------------------------------------------------------------------------


def _seed_memorial(dbname: str, player_id: int) -> dict[str, int]:
    """Two committed scenes at the memorial, plus rows the recap must ignore."""
    earlier = _choice_chunk(
        dbname,
        ["Offer Rook the thumb-to-temple greeting.", "Keep your distance."],
        scene=1,
        choice_text=LAST_ACTION,
        selected=1,
    )
    frontier = _choice_chunk(dbname, MEMORIAL_CHOICES, scene=2)
    ids = {"earlier": earlier, "frontier": frontier, "player": player_id}
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        for key, name in (
            ("hall", "Lantern Quay Memorial Hall"),
            ("viaduct", "Transit Viaduct"),
            ("archive", "Drowned Archive"),
        ):
            cur.execute(
                "INSERT INTO places (name, type) VALUES (%s, 'fixed_location') "
                "RETURNING id",
                (name,),
            )
            ids[key] = cur.fetchone()[0]
        for key, name in (
            ("rook", "Elian Rook"),
            ("ren", "Ren Vale"),
            ("ivo", "Ivo Senn"),
        ):
            cur.execute(
                "INSERT INTO characters (name, summary) VALUES (%s, %s) RETURNING id",
                (name, f"{name}, at the Rook memorial."),
            )
            ids[key] = cur.fetchone()[0]
        settings = [
            (earlier, ids["hall"]),
            (frontier, ids["hall"]),
            (frontier, ids["viaduct"]),
        ]
        for chunk_id, place_id in settings:
            cur.execute(
                "INSERT INTO place_chunk_references (chunk_id, place_id, "
                "reference_type) VALUES (%s, %s, 'setting')",
                (chunk_id, place_id),
            )
        references = [
            (earlier, player_id, "present"),
            (earlier, ids["rook"], "present"),
            (frontier, player_id, "present"),
            (frontier, ids["rook"], "present"),
            (frontier, ids["ren"], "present"),
            (frontier, ids["ivo"], "mentioned"),
        ]
        for chunk_id, character_id, reference in references:
            cur.execute(
                "INSERT INTO chunk_character_references (chunk_id, character_id, "
                "reference) VALUES (%s, %s, %s)",
                (chunk_id, character_id, reference),
            )

        # Later ids the recap must never read: an uncommitted draft chunk and
        # a Retrograde prologue anchor, each with its own setting and action.
        cur.execute(
            "INSERT INTO narrative_chunks (raw_text, choice_text) "
            "VALUES ('Draft prose.', 'Draft action.') RETURNING id"
        )
        ids["draft"] = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO narrative_chunks (
                raw_text, storyteller_text, choice_text, authorial_directives
            ) VALUES ('Prologue.', 'Prologue.', 'Prologue action.', %s)
            RETURNING id
            """,
            (Json([RETROGRADE_PROLOGUE_MARKER]),),
        )
        ids["prologue"] = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO chunk_metadata (
                chunk_id, season, episode, scene, world_layer, time_delta,
                generation_date
            ) VALUES (%s, 0, 0, 0, 'retrograde', interval '0 seconds', now())
            """,
            (ids["prologue"],),
        )
        for hidden in (ids["draft"], ids["prologue"]):
            cur.execute(
                "INSERT INTO place_chunk_references (chunk_id, place_id, "
                "reference_type) VALUES (%s, %s, 'setting')",
                (hidden, ids["archive"]),
            )
            cur.execute(
                "INSERT INTO chunk_character_references (chunk_id, character_id, "
                "reference) VALUES (%s, %s, 'present')",
                (hidden, ids["ivo"]),
            )
    return ids


def _reader() -> TestClient:
    app = FastAPI()
    app.include_router(reader_endpoints.router)
    return TestClient(app)


def test_recap_on_a_seeded_story_cites_valid_reader_ids(
    recap_slot: tuple[str, int],
) -> None:
    """Location, roster, last action and open decision, each from canon."""
    dbname, player_id = recap_slot
    ids = _seed_memorial(dbname, player_id)
    hiatus = load_settings().ui.recap.hiatus_hours
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE global_variables SET last_played = now() - %s * interval '1 hour' "
            "WHERE id = true",
            (hiatus + 1,),
        )

    client = _reader()
    response = client.get("/api/narrative/recap", params={"slot": SLOT})
    assert response.status_code == 200, response.text
    recap = response.json()

    assert recap["due"] is True
    assert recap["last_played"] is not None
    assert recap["items"] == [
        {
            "kind": "location",
            "text": "Lantern Quay Memorial Hall, Transit Viaduct",
            "sources": [
                {"kind": "chunk", "id": ids["frontier"]},
                {"kind": "place", "id": ids["hall"]},
                {"kind": "place", "id": ids["viaduct"]},
            ],
        },
        {
            "kind": "roster",
            "text": "Mara Vey, Elian Rook, Ren Vale",
            "sources": [
                {"kind": "chunk", "id": ids["frontier"]},
                {"kind": "character", "id": player_id},
                {"kind": "character", "id": ids["rook"]},
                {"kind": "character", "id": ids["ren"]},
            ],
        },
        {
            "kind": "last_action",
            "text": LAST_ACTION,
            "sources": [{"kind": "chunk", "id": ids["earlier"]}],
        },
        {
            "kind": "open_decision",
            "text": "\n".join(MEMORIAL_CHOICES),
            "sources": [{"kind": "chunk", "id": ids["frontier"]}],
        },
    ]

    # Every cited ID is one the ordinary reader already serves.
    places = {row["id"] for row in client.get(f"/api/places?slot={SLOT}").json()}
    cast = {row["id"] for row in client.get(f"/api/characters?slot={SLOT}").json()}
    for item in recap["items"]:
        for source in item["sources"]:
            if source["kind"] == "chunk":
                chunk = client.get(f"/api/narrative/chunks/{source['id']}?slot={SLOT}")
                assert chunk.status_code == 200
            else:
                assert source["id"] in (places if source["kind"] == "place" else cast)


def test_accepting_the_open_decision_closes_it_and_resets_the_clock(
    recap_slot: tuple[str, int],
) -> None:
    dbname, player_id = recap_slot
    ids = _seed_memorial(dbname, player_id)
    _set_last_played(dbname, EARLIER)
    client = _reader()
    assert client.get(f"/api/narrative/recap?slot={SLOT}").json()["due"] is True

    _record(ids["frontier"], choice=2)

    recap = client.get(f"/api/narrative/recap?slot={SLOT}").json()
    assert recap["due"] is False
    assert [item["kind"] for item in recap["items"]] == [
        "location",
        "roster",
        "last_action",
    ]
    assert recap["items"][-1] == {
        "kind": "last_action",
        "text": MEMORIAL_CHOICES[1],
        "sources": [{"kind": "chunk", "id": ids["frontier"]}],
    }


def test_new_story_recap_is_empty_and_not_due(recap_slot: tuple[str, int]) -> None:
    response = _reader().get(f"/api/narrative/recap?slot={SLOT}")

    assert response.status_code == 200, response.text
    assert response.json() == {"due": False, "last_played": None, "items": []}


def test_forged_handles_fail_server_side_verification(
    recap_slot: tuple[str, int],
) -> None:
    """Handles outside committed canon, or unrelated to their chunk, are refused."""
    dbname, player_id = recap_slot
    ids = _seed_memorial(dbname, player_id)
    forged = ReturnRecap(
        due=False,
        last_played=None,
        items=[
            RecapItem(
                kind="location",
                text="Drowned Archive",
                sources=[
                    SourceHandle(kind="chunk", id=ids["prologue"]),
                    SourceHandle(kind="place", id=ids["archive"]),
                ],
            ),
            RecapItem(
                kind="roster",
                text="Ivo Senn",
                sources=[
                    SourceHandle(kind="chunk", id=ids["frontier"]),
                    SourceHandle(kind="character", id=ids["ivo"]),
                ],
            ),
            RecapItem(
                kind="last_action",
                text="Draft action.",
                sources=[SourceHandle(kind="chunk", id=ids["draft"])],
            ),
        ],
    )

    with closing(connect(dbname)) as conn:
        with pytest.raises(RecapEvidenceError) as exc:
            verify_recap_sources(conn, forged)

    message = str(exc.value)
    assert f"location: chunk {ids['prologue']}" in message
    assert f"roster: character {ids['ivo']} on chunk {ids['frontier']}" in message
    assert f"last_action: chunk {ids['draft']}" in message
