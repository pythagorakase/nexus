"""Seat-specific manifests through the real shared renderer and TEST counter."""

from copy import deepcopy

import pytest

from nexus.agents.logon.skald_wire import CharacterRef, PresenceBaseline
from nexus.agents.lore.seat_blocks import SEAT_BLOCKS
from nexus.prompts.registry import PromptId, load
from tests.test_lore.test_scene_order_render import scene_payload
from tests.test_lore.window_helpers import window_logon


def seat_payload() -> dict:
    """Populate the common context lanes and each kind of Orrery card."""
    payload = scene_payload()
    cards = [
        {
            "template_id": "meeting",
            "binding_hash": str(index) * 8,
            "binding_names": {"actor": name},
            "branch_label": "At the gate",
        }
        for index, name in enumerate(("Mara", "Vale"))
    ]
    payload.update(
        scene_conditions={"weather": "Rain"},
        entity_data={"characters": [{"name": "Mara", "summary": "Waiting"}]},
        world_knowledge=[{"character_name": "Mara", "summary": "The gate is shut."}],
        orrery_recent_rulings_section=[
            "=== RECENT ORRERY RULINGS ===",
            "[RATIFIED] Rain",
        ],
        orrery_imminent_activity=cards,
        orrery_scene_pressures=[
            {
                **cards[0],
                "template_id": "pressure",
                "prompt_text": "A bell sounds.",
            }
        ],
        orrery_joint_beats=[
            {
                "forward_proposal_id": "meeting:00000000",
                "reverse_proposal_id": "meeting:11111111",
            }
        ],
    )
    return payload


@pytest.mark.parametrize("seat", ["writer", "gaia"])
def test_seat_block_order_and_card_prose(seat: str) -> None:
    """Context and card identities stay intact while seat instructions differ."""
    utility = window_logon()
    payload = seat_payload()
    original = deepcopy(payload)
    baseline = PresenceBaseline(
        present=[CharacterRef(kind="character", id=7, name="Mara")]
    )
    prompt = utility._format_context_prompt(
        payload, seat=seat, presence_baseline=baseline
    )
    kinds = list(dict.fromkeys(kind for kind, _ in utility._last_rendered_blocks))
    assert kinds == [
        "scene conditions",
        "entity dossier",
        "historical context",
        "recalled scenes",
        "recent narrative",
        "world knowledge",
        "recent orrery rulings",
        "orrery imminent activity",
        "orrery scene pressure",
        "orrery joint beats",
        *(["scene roster"] if seat == "writer" else []),
        "user input",
        f"{seat} closer",
    ]
    for prompt_id in (
        PromptId.TURN_BLOCKS_IMMINENT_ACTIVITY,
        PromptId.TURN_BLOCKS_SCENE_PRESSURE,
        PromptId.TURN_BLOCKS_JOINT_BEATS,
    ):
        assert (load(prompt_id) in prompt) == (seat == "gaia")
    for handle in ("meeting:00000000", "meeting:11111111", "pressure:00000000"):
        assert handle in prompt
    assert "=== INSTRUCTIONS ===" not in prompt
    assert prompt.endswith(
        load(PromptId.WRITER_CLOSER if seat == "writer" else PromptId.GAIA_CLOSER)
    )
    if seat == "writer":
        assert "orrery tag library" not in SEAT_BLOCKS[seat]
        assert prompt.split("=== USER INPUT ===\n")[1] == (
            payload["user_input"] + "\n" + load(PromptId.WRITER_CLOSER)
        )
    assert payload == original
    assert "".join(value for _, value in utility._last_rendered_blocks) == prompt
    sources = utility._last_rendered_block_sources
    assert len(sources) == 6
    assert all(
        utility._last_rendered_blocks[index][0]
        in {"historical context", "recalled scenes", "recent narrative"}
        for index in sources
    )


@pytest.mark.parametrize("seat", ["writer", "gaia"])
def test_blocks_outside_the_seat_manifest_fail_loudly(seat: str) -> None:
    """Bootstrap data on a two-pass turn is a composition error, not a silent drop."""
    utility = window_logon()
    payload = seat_payload()
    payload["bootstrap_data"] = {"setting": {"world_name": "Veyra"}}
    with pytest.raises(ValueError, match=f"outside the {seat} manifest"):
        utility._format_context_prompt(payload, seat=seat)


@pytest.mark.parametrize("seat", ["single_pass", "bootstrap"])
def test_legacy_seat_blocks_keep_union_and_order(seat: str) -> None:
    """The exempt seats retain the previous inputs, instructions, and ordering."""
    utility = window_logon()
    payload = seat_payload()
    if seat == "bootstrap":
        payload["is_bootstrap"] = True
    prompt = utility._format_context_prompt(payload, seat=seat)
    assert prompt.index("=== USER INPUT ===") < prompt.index("=== WORLD KNOWLEDGE ===")
    assert prompt.index("=== ORRERY JOINT BEATS ===") < prompt.index(
        "=== INSTRUCTIONS ==="
    )
    for prompt_id in (
        PromptId.TURN_BLOCKS_IMMINENT_ACTIVITY,
        PromptId.TURN_BLOCKS_SCENE_PRESSURE,
        PromptId.TURN_BLOCKS_JOINT_BEATS,
        PromptId.TURN_BLOCKS_CONTINUE_NARRATIVE,
        PromptId.TURN_BLOCKS_MAINTAIN_CONSISTENCY,
    ):
        assert load(prompt_id) in prompt
    assert "orrery tag library" in SEAT_BLOCKS[seat]
    assert not prompt.endswith(load(PromptId.WRITER_CLOSER))


def test_measured_seat_blocks_match_rendered_requests() -> None:
    """#903 retains seat order and ownership in the actual TEST request path."""
    requests = window_logon().measure_turn_requests(seat_payload(), 75000)
    assert [request.budget.seat for request in requests] == ["skald_writer", "gaia"]
    for request in requests:
        prompt = "".join(value for _, value in request.blocks)
        assert "=== INSTRUCTIONS ===" not in prompt
        assert len(request.sources) == 6
        if request.budget.seat == "skald_writer":
            assert prompt.endswith(load(PromptId.WRITER_CLOSER))
            assert "=== ORRERY TAG LIBRARY ===" not in prompt
        else:
            assert prompt.index(load(PromptId.GAIA_CLOSER)) < prompt.index(
                "=== FINISHED WRITER NARRATIVE (VERBATIM) ==="
            )


@pytest.mark.requires_postgres
def test_seat_prompt_live_tag_library_and_order() -> None:
    """The live library stays in Gaia's measured request and leaves the writer."""
    from nexus.agents.lore.logon_utility import LogonUtility
    from nexus.api import slot_utils
    from nexus.config import load_settings_as_dict
    from nexus.config.story_model import read_story_settings
    from tests.pg_fixtures import connect, disposable_slot_database

    with disposable_slot_database(
        "qa640_742_seat_test", source_db="save_04", include_data=True
    ) as dbname:
        original_dbnames = slot_utils.VALID_DBNAMES
        slot_utils.VALID_DBNAMES = original_dbnames | {dbname}
        try:
            with connect(dbname) as conn, conn.cursor() as cur:
                cur.execute("SELECT max(id) FROM narrative_chunks")
                parent = cur.fetchone()[0]
            utility = LogonUtility(
                load_settings_as_dict(),
                dbname=dbname,
                model_override="TEST",
                story_settings=read_story_settings(dbname),
            )
            payload = seat_payload()
            payload["metadata"] = {"target_chunk_id": parent}
            requests = utility.measure_turn_requests(payload, 75000)
            for request in requests:
                kinds = list(dict.fromkeys(kind for kind, _ in request.blocks))
                prompt = "".join(value for _, value in request.blocks)
                if request.budget.seat == "skald_writer":
                    assert "=== ORRERY TAG LIBRARY ===" not in prompt
                    assert kinds[-3:] == ["scene roster", "user input", "writer closer"]
                    assert prompt.endswith(load(PromptId.WRITER_CLOSER))
                else:
                    assert "=== ORRERY TAG LIBRARY ===" in prompt
                    assert (
                        kinds[kinds.index("world knowledge") + 1]
                        == "orrery tag library"
                    )
                    assert kinds[-3:] == [
                        "user input",
                        "gaia closer",
                        "finished writer framing",
                    ]
        finally:
            slot_utils.VALID_DBNAMES = original_dbnames
