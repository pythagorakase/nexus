"""Seat-specific manifests through the real shared renderer and TEST counter."""

import json
from copy import copy, deepcopy
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, get_args

import pytest

from nexus.agents.logon.skald_wire import (
    CharacterRef,
    PresenceBaseline,
    SkaldWriterWire,
)
from nexus.agents.lore.seat_blocks import (
    BLOCK_INFLUENCE_ROLES,
    SEAT_BLOCKS,
    BlockId,
    InfluenceRole,
    ManifestKind,
    influence_role,
    influence_token_totals,
)
from nexus.prompts.registry import PromptId, load
from nexus.telemetry import attempt_manifest, usage
from nexus.telemetry.attempt_manifest import attempt_blocks, identity_hash
from nexus.telemetry.prompt_window import PromptWindowRecord
from nexus.telemetry.usage import read_prompt_windows, record_prompt_window
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


def finished_writer() -> SkaldWriterWire:
    """A complete writer pass for Gaia's rendered suffix."""
    return SkaldWriterWire.model_validate(
        {
            "narrative": "Rain runs off the shut gate.",
            "choices": ["Wait.", "Knock."],
            "letter": "Keep the gate shut until the bell.",
        }
    )


def test_every_block_kind_declares_one_influence_role() -> None:
    """Rendered and manifest-only kinds each carry one declared role (#744)."""
    block_ids = get_args(BlockId)
    manifest_kinds = get_args(ManifestKind)
    assert isinstance(BLOCK_INFLUENCE_ROLES, MappingProxyType)
    assert not set(block_ids) & set(manifest_kinds)
    assert set(BLOCK_INFLUENCE_ROLES) == {*block_ids, *manifest_kinds}
    assert len(BLOCK_INFLUENCE_ROLES) == len(block_ids) + len(manifest_kinds)
    roles = get_args(InfluenceRole)
    assert {influence_role(kind) for kind in BLOCK_INFLUENCE_ROLES} == set(roles)
    # Only the prompt family, recent accepted prose and the player's exact
    # words may teach diction; everything else arrives as evidence or plan.
    assert {
        kind
        for kind, role in BLOCK_INFLUENCE_ROLES.items()
        if role in {"voice_source", "player_language"}
    } == {"system", "recent narrative", "user input"}


@pytest.mark.parametrize("kind", ["story", "Recent Narrative", ""])
def test_undeclared_block_kind_fails_loudly(kind: str) -> None:
    """An unmapped kind raises everywhere roles are read; nothing defaults."""
    with pytest.raises(ValueError, match="declares no influence role"):
        influence_role(kind)
    with pytest.raises(ValueError, match="declares no influence role"):
        influence_token_totals({"system": 3, kind: 1})
    with pytest.raises(ValueError, match="declares no influence role"):
        attempt_blocks(
            [("user input", "Wait."), (kind, "Unmapped.")],
            len,
            system_prompt="",
            system_tokens=0,
            wire_schema={},
            framing_tokens=0,
        )


def test_influence_tokens_sum_block_tokens_per_role() -> None:
    """Totals keep every role, in declaration order, including framing deltas."""
    totals = influence_token_totals(
        {
            "system": 100,
            "recent narrative": 40,
            "user input": 5,
            "entity dossier": 30,
            "world knowledge": 20,
            "writer closer": 12,
            "request framing": -2,
        }
    )
    assert totals == {
        "voice_source": 140,
        "player_language": 5,
        "canonical_evidence": 50,
        "authorial_plan": 10,
    }
    assert list(totals) == list(get_args(InfluenceRole))


@pytest.mark.parametrize("seat", ["writer", "gaia", "single_pass", "bootstrap"])
def test_attempt_blocks_attach_roles_to_rendered_blocks(seat: str) -> None:
    """The manifest builder labels the exact rendered bytes without touching them."""
    utility = window_logon()
    payload = seat_payload()
    if seat == "bootstrap":
        payload["is_bootstrap"] = True
    prompt = utility._format_context_prompt(payload, seat=seat)
    blocks = list(utility._last_rendered_blocks)
    assert "".join(text for _, text in blocks) == prompt
    if seat == "gaia":
        gaia_prompt = utility._format_gaia_user_prompt(prompt, finished_writer())
        blocks.append(("finished writer output", gaia_prompt[len(prompt) :]))
        blocks.append(("structured output retry", "\nReturn valid JSON."))
    wire_schema = {"type": "json_schema", "name": "turn"}
    entries = attempt_blocks(
        blocks,
        len,
        system_prompt="Second person, present tense.",
        system_tokens=6,
        wire_schema=wire_schema,
        framing_tokens=9,
    )
    assert [entry["kind"] for entry in entries] == [
        "system",
        *(kind for kind, _ in blocks),
        "request framing",
    ]
    assert [entry["tokens"] for entry in entries] == [
        6,
        *(len(text) for _, text in blocks),
        9,
    ]
    assert [entry["sha256"] for entry in entries] == [
        identity_hash("Second person, present tense."),
        *(identity_hash(text) for _, text in blocks),
        identity_hash(wire_schema),
    ]
    assert [entry["influence_role"] for entry in entries] == [
        BLOCK_INFLUENCE_ROLES[entry["kind"]] for entry in entries
    ]


def test_prompt_window_guard_records_roles_for_every_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Writer, Gaia and a structured retry carry roles into manifest and ledger."""
    started: list[tuple[PromptWindowRecord, list[dict[str, Any]]]] = []
    real_start = attempt_manifest.start_attempt

    def recording_start(record: PromptWindowRecord, **kwargs: Any) -> None:
        # Observe the manifest payload; the real start still runs (unscoped here).
        started.append((record, kwargs["blocks"]))
        real_start(record, **kwargs)

    monkeypatch.setattr(attempt_manifest, "start_attempt", recording_start)
    utility = window_logon()
    utility._ensure_provider()
    payload = seat_payload()
    writer_prompt = utility._format_context_prompt(payload, seat="writer")
    utility._writer_window_blocks = list(utility._last_rendered_blocks)
    gaia_turn = utility._format_context_prompt(payload, seat="gaia")
    utility._gaia_window_blocks = list(utility._last_rendered_blocks)
    utility._window_payload = {"metadata": {"turn_id": "744-roles"}}
    writer_provider = copy(utility.provider)
    utility._attach_prompt_window_guard(
        writer_provider, writer_prompt, seat="skald_writer", window=75000
    )
    writer_provider.prompt_window_guard(writer_prompt, 1)
    gaia_prompt = utility._format_gaia_user_prompt(gaia_turn, finished_writer())
    gaia_provider = copy(utility.provider)
    utility._attach_prompt_window_guard(
        gaia_provider, gaia_prompt, seat="gaia", window=75000
    )
    gaia_provider.prompt_window_guard(gaia_prompt, 1)
    gaia_provider.prompt_window_guard(gaia_prompt + "\nReturn valid JSON.", 2)

    day = datetime.now(timezone.utc).date().isoformat()
    ledger = {
        (row.seat, row.attempt): row for row in read_prompt_windows("744-roles", day)
    }
    assert list(ledger) == [("skald_writer", 1), ("gaia", 1), ("gaia", 2)]
    for record, blocks in started:
        totals = dict.fromkeys(get_args(InfluenceRole), 0)
        for block in blocks:
            assert block["influence_role"] == influence_role(block["kind"])
            totals[block["influence_role"]] += block["tokens"]
        assert totals == record.influence_tokens
        assert ledger[(record.seat, record.attempt)].influence_tokens == totals
    assert [[block["kind"] for block in blocks][-3:] for _, blocks in started] == [
        ["user input", "writer closer", "request framing"],
        ["gaia closer", "finished writer output", "request framing"],
        ["finished writer output", "structured output retry", "request framing"],
    ]


def test_prompt_window_lines_before_roles_still_validate() -> None:
    """Ledger lines written before #744 read back with no role totals."""
    day = datetime.now(timezone.utc).date().isoformat()
    ledger = usage._get_recorder_config().usage_dir / f"windows-{day}.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    legacy: dict[str, Any] = {
        "generation_session": "pre-744",
        "seat": "gaia",
        "attempt": 1,
        "model": "TEST",
        "block_tokens": {"system": 20, "user input": 5},
        "input_tokens": 25,
        "effective_ceiling": 100,
        "policy_headroom": 4,
        "headroom": 75,
        "trimming": {},
        "validation_notes": [],
    }
    ledger.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
    record_prompt_window(
        PromptWindowRecord(
            **{
                **legacy,
                "attempt": 2,
                "influence_tokens": influence_token_totals(legacy["block_tokens"]),
            }
        )
    )
    old, new = read_prompt_windows("pre-744", day)
    assert old.influence_tokens == {}
    assert new.influence_tokens == {
        "voice_source": 20,
        "player_language": 5,
        "canonical_evidence": 0,
        "authorial_plan": 0,
    }


@pytest.mark.requires_postgres
def test_seat_prompt_live_tag_library_and_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live library stays in Gaia's measured request and leaves the writer."""
    from nexus.agents.lore.logon_utility import LogonUtility
    from nexus.config import load_settings
    from nexus.config.story_model import read_story_settings
    from tests.pg_fixtures import (
        connect,
        disposable_slot_database,
        route_slot_to_disposable,
    )

    with disposable_slot_database(
        "qa640_742_seat_test", source_db="save_04", include_data=True
    ) as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=4, dbname=dbname)
        with connect(dbname) as conn, conn.cursor() as cur:
            cur.execute("SELECT max(id) FROM narrative_chunks")
            parent = cur.fetchone()[0]
        utility = LogonUtility(
            load_settings(),
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
                assert kinds[kinds.index("world knowledge") + 1] == "orrery tag library"
                assert kinds[-3:] == [
                    "user input",
                    "gaia closer",
                    "finished writer framing",
                ]
