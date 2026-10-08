"""Tests for the local TEST-mode OpenAI impersonator."""

from collections.abc import Callable
from contextlib import closing
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
import uuid

import pytest
import requests  # type: ignore[import-untyped]

from nexus.agents.logon.apex_schema import (
    StorytellerResponseBootstrap,
)
from nexus.agents.logon.skald_wire import (
    SkaldGaiaWire,
    SkaldTurnWire,
    SkaldWriterWire,
)
from nexus.api.mock_openai import (
    ChatCompletionRequest,
    ResponsesRequest,
    _collect_text,
    _mock_gaia_response,
    _mock_storyteller_response,
    _mock_writer_response,
    _requested_output_properties,
    chat_completions,
    get_cached_bootstrap_narrative,
    query_bootstrap_narrative,
    query_traits,
    query_wizard_cache,
    responses_create,
)
from nexus.api.native_structured_output import openai_response_text_format
from nexus.config.loader import TEST_PROVIDER_DATABASE_ENV
from nexus.presence.roster import PresenceRoster, RosterEntry, write_roster
from scripts.entity_reference_parity import run as reference_parity
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_test_provider_database,
    seed_committed_chunk,
    seed_faction,
)
from tests.test_logon_mock_integration import mock_openai_server  # noqa: F401


def _final_result_tool(schema_model) -> dict:
    """Build the pydantic_ai-style output tool for a Storyteller schema."""
    return {
        "name": "final_result",
        "type": "function",
        "parameters": schema_model.model_json_schema(),
        "strict": True,
    }


def _native_text_format(schema_model) -> dict:
    """Build the OpenAI native Responses text.format payload."""

    return {"format": openai_response_text_format(schema_model)}


def test_mock_non_bootstrap_payload_is_sparse_skald_wire() -> None:
    """TEST turns track the provider wire and exercise optional omissions."""

    payload = _mock_storyteller_response("")

    wire = SkaldTurnWire.model_validate(payload)

    assert set(payload) == {"narrative", "choices", "letter"}
    assert wire.updates is None
    assert wire.model_dump(exclude_unset=True, mode="json") == payload


@pytest.mark.asyncio
async def test_mock_chat_completion_does_not_log_private_prompt(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even the TEST transport must not emit correspondence at INFO or below."""

    secret = "PRIVATE-CONSPIRACY-LETTER-617"
    monkeypatch.setattr(
        "nexus.api.mock_openai.get_cached_phase_response",
        lambda _phase, _subphase: {"data": {}},
    )
    with caplog.at_level("DEBUG", logger="nexus.api.mock_openai"):
        await chat_completions(
            ChatCompletionRequest(
                model="TEST",
                messages=[{"role": "user", "content": secret}],
            )
        )

    assert secret not in caplog.text


@pytest.mark.asyncio
async def test_mock_responses_returns_orrery_adjudication_fixture() -> None:
    """TEST mode can force defer, void, and replace without live API calls."""

    prompt = """
=== ORRERY IMMINENT ACTIVITY ===
- drink:aaa [Drink routinely]: state_delta={'character.current_activity': 'drinking'}
- hide:bbb [Go dark]: state_delta={'character.current_activity': 'hiding'}
- tend_craft:ccc [Tend craft]: state_delta={'character.current_activity': 'tending'}
- evade_pursuers:ddd [Evade]: state_delta={'character.current_activity': 'moving'}
"""

    response = await responses_create(
        ResponsesRequest(model="TEST", input=[{"role": "user", "content": prompt}])
    )

    payload = json.loads(response["output_text"])
    parsed = SkaldTurnWire.model_validate(payload)

    assert [item.action for item in parsed.orrery_adjudications] == [
        "defer",
        "void",
        "replace",
    ]
    assert parsed.orrery_adjudications[0].proposal_id == "drink:aaa"
    assert parsed.orrery_adjudications[1].proposal_id == "hide:bbb"
    replacement = parsed.orrery_adjudications[2]
    assert replacement.proposal_id == "tend_craft:ccc"
    assert replacement.replacement_event_type == "work_performed"
    from nexus.agents.orrery.event_vocabulary import known_event_types

    assert replacement.replacement_event_type in known_event_types()
    assert replacement.replacement_state_delta is not None
    assert (
        replacement.replacement_state_delta.character_current_activity
        == "following the mock-server replacement beat"
    )


@pytest.mark.asyncio
async def test_mock_responses_single_orrery_proposal_only_defers() -> None:
    """A one-proposal prompt returns a schema-valid partial adjudication list."""

    response = await responses_create(
        ResponsesRequest(
            model="TEST",
            input=[
                {
                    "role": "user",
                    "content": (
                        "=== ORRERY IMMINENT ACTIVITY ===\n"
                        "- sleep_pressure:aaa [Doze off]: "
                        "state_delta={'character.current_activity': 'sleeping'}"
                    ),
                }
            ],
        )
    )

    payload = json.loads(response["output_text"])
    parsed = SkaldTurnWire.model_validate(payload)

    assert [item.action for item in parsed.orrery_adjudications] == ["defer"]
    assert parsed.orrery_adjudications[0].proposal_id == "sleep_pressure:aaa"


@pytest.mark.asyncio
async def test_mock_responses_parses_nested_responses_input_content() -> None:
    """Pydantic AI style nested content still exposes Orrery proposal IDs."""

    response = await responses_create(
        ResponsesRequest(
            model="TEST",
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Story turn"},
                        {
                            "type": "input_text",
                            "text": '- "proposal_id": "drink:aaa"',
                        },
                    ],
                }
            ],
        )
    )

    payload = json.loads(response["output_text"])
    assert payload["orrery_adjudications"][0]["proposal_id"] == "drink:aaa"


@pytest.mark.asyncio
async def test_mock_responses_prioritizes_orrery_fixture_over_cached_story() -> None:
    """Orrery proposal prompts use the adjudication fixture even if narrative-like."""

    response = await responses_create(
        ResponsesRequest(
            model="TEST",
            input=[
                {
                    "role": "user",
                    "content": (
                        "Continue the protagonist story.\n"
                        "=== ORRERY IMMINENT ACTIVITY ===\n"
                        "- honor_debt:aaa [Repay debt]: state_delta={}"
                    ),
                }
            ],
        )
    )

    payload = json.loads(response["output_text"])
    assert payload["narrative"].startswith("[TEST MODE]")
    assert payload["orrery_adjudications"][0]["proposal_id"] == "honor_debt:aaa"


@pytest.mark.asyncio
async def test_mock_responses_routes_turn_schema_without_orrery_proposals() -> None:
    """A turn request with no Orrery section still gets a wire payload.

    Regression for the issue #401 reproduction blocker: keyword routing sent
    proposal-free turn requests to the bootstrap-shaped payload, which fails
    turn-wire validation and stalls TEST-mode turn loops.
    """

    response = await responses_create(
        ResponsesRequest(
            model="TEST",
            input=[{"role": "user", "content": "Continue the protagonist story."}],
            tools=[_final_result_tool(SkaldTurnWire)],
        )
    )

    tool_call = response["output"][0]
    assert tool_call["type"] == "function_call"
    assert tool_call["name"] == "final_result"

    payload = json.loads(response["output_text"])
    assert json.loads(tool_call["arguments"]) == payload
    parsed = SkaldTurnWire.model_validate(payload)
    assert parsed.narrative.startswith("[TEST MODE]")
    assert parsed.updates is None
    assert parsed.orrery_adjudications == []


@pytest.mark.asyncio
async def test_mock_responses_routes_turn_schema_as_native_text_format() -> None:
    """Native OpenAI strict schemas should route without a final_result tool."""

    response = await responses_create(
        ResponsesRequest(
            model="TEST",
            input=[{"role": "user", "content": "Continue the protagonist story."}],
            text=_native_text_format(SkaldTurnWire),
        )
    )

    message = response["output"][0]
    assert message["type"] == "message"

    payload = json.loads(response["output_text"])
    parsed = SkaldTurnWire.model_validate(payload)
    assert parsed.narrative.startswith("[TEST MODE]")
    assert parsed.updates is None
    assert parsed.orrery_adjudications == []


_ORRERY_PROMPT = """
=== ORRERY IMMINENT ACTIVITY ===
- drink:aaa [Drink routinely]: state_delta={'character.current_activity': 'x'}
"""


def test_mock_two_pass_projections_partition_the_full_fixture() -> None:
    """Every full-fixture key lands in exactly one pass (extra=forbid guard)."""

    full = _mock_storyteller_response(_ORRERY_PROMPT)
    writer = _mock_writer_response(_ORRERY_PROMPT)
    gaia = _mock_gaia_response(_ORRERY_PROMPT)

    SkaldWriterWire.model_validate(writer)
    SkaldGaiaWire.model_validate(gaia)
    assert set(writer) | set(gaia) == set(full)
    assert set(writer) & set(gaia) == {"letter"}


@pytest.mark.asyncio
async def test_mock_responses_routes_writer_schema_to_writer_projection() -> None:
    """The two-pass writer request must not receive bootstrap or gaia fields.

    Regression for the PR #579 Codex P1: before signature routing, a writer
    schema (no updates property) fell through to the cached bootstrap payload.
    """

    response = await responses_create(
        ResponsesRequest(
            model="TEST",
            input=[{"role": "user", "content": "Continue the protagonist story."}],
            tools=[_final_result_tool(SkaldWriterWire)],
        )
    )

    payload = json.loads(response["output_text"])
    parsed = SkaldWriterWire.model_validate(payload)
    assert parsed.narrative.startswith("[TEST MODE]")
    assert "updates" not in payload


@pytest.mark.asyncio
async def test_mock_responses_routes_gaia_schema_to_gaia_projection() -> None:
    """The two-pass gaia request must not receive narrative/choices extras.

    Regression for the PR #579 Codex P1: the gaia schema contains the updates
    property, so the old routing returned the FULL turn payload, whose
    narrative/choices are forbidden extras under SkaldGaiaWire.
    """

    response = await responses_create(
        ResponsesRequest(
            model="TEST",
            input=[{"role": "user", "content": _ORRERY_PROMPT}],
            tools=[_final_result_tool(SkaldGaiaWire)],
        )
    )

    payload = json.loads(response["output_text"])
    parsed = SkaldGaiaWire.model_validate(payload)
    assert "narrative" not in payload
    assert [item.action for item in parsed.orrery_adjudications] == ["defer"]


@pytest.mark.asyncio
async def test_mock_responses_gaia_schema_without_proposals_is_empty() -> None:
    """A proposal-free gaia request returns a valid all-defaults payload."""

    response = await responses_create(
        ResponsesRequest(
            model="TEST",
            input=[{"role": "user", "content": "Continue the protagonist story."}],
            tools=[_final_result_tool(SkaldGaiaWire)],
        )
    )

    payload = json.loads(response["output_text"])
    parsed = SkaldGaiaWire.model_validate(payload)
    assert set(payload) == {"letter"}
    assert payload["letter"]
    assert parsed.updates is None
    assert parsed.orrery_adjudications == []


@pytest.mark.asyncio
@pytest.mark.requires_postgres
@pytest.mark.usefixtures("routed_test_provider_database")
async def test_mock_responses_routes_bootstrap_schema_as_final_result_tool() -> None:
    """Bootstrap structured output must also call the required output tool."""

    response = await responses_create(
        ResponsesRequest(
            model="TEST",
            input=[{"role": "user", "content": "Bootstrap the protagonist story."}],
            tools=[_final_result_tool(StorytellerResponseBootstrap)],
        )
    )

    tool_call = response["output"][0]
    assert tool_call["type"] == "function_call"
    assert tool_call["name"] == "final_result"
    payload = json.loads(tool_call["arguments"])
    StorytellerResponseBootstrap.model_validate(payload)


@pytest.mark.asyncio
@pytest.mark.requires_postgres
@pytest.mark.usefixtures("routed_test_provider_database")
async def test_mock_responses_routes_bootstrap_schema_as_native_text_format() -> None:
    """Bootstrap native structured output should return message JSON."""

    response = await responses_create(
        ResponsesRequest(
            model="TEST",
            input=[{"role": "user", "content": "Bootstrap the protagonist story."}],
            text=_native_text_format(StorytellerResponseBootstrap),
        )
    )

    message = response["output"][0]
    assert message["type"] == "message"
    StorytellerResponseBootstrap.model_validate_json(response["output_text"])


@pytest.mark.requires_postgres
def test_seeded_test_provider_database_holds_the_rows_the_provider_reads(
    routed_test_provider_database: str,
) -> None:
    """Migration 008 seeds and reseeds the provider, including pre-148 schema."""

    result = _run_test_provider_seeder(routed_test_provider_database)
    assert result.returncode == 0, result.stderr
    assert (
        f"TEST provider database {routed_test_provider_database!r} "
        "populated successfully!"
    ) in result.stdout

    cache = query_wizard_cache()
    assert cache["base_timestamp"] is not None
    assert cache["layer_name"]

    traits = query_traits()
    selected = [row for row in traits if row["is_selected"] and row["id"] <= 10]
    assert len(selected) == 3, selected
    assert "fame" in {row["name"] for row in selected}
    assert {row["id"]: row["name"] for row in traits}[11] == "Ghostprint Key"

    assert get_cached_bootstrap_narrative()["narrative"].startswith("The tram shudders")

    with closing(connect(routed_test_provider_database)) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT model, new_story, user_character "
                "FROM global_variables WHERE id = TRUE"
            )
            assert cur.fetchone() == ("TEST", False, 1)


@pytest.mark.requires_postgres
@pytest.mark.parametrize(
    "reader, table",
    [
        (query_wizard_cache, "assets.new_story_creator"),
        (query_bootstrap_narrative, "incubator"),
        (get_cached_bootstrap_narrative, "incubator"),
        (query_traits, "assets.traits"),
    ],
    ids=["wizard", "bootstrap", "cached-bootstrap", "traits"],
)
def test_missing_test_provider_rows_raise(
    monkeypatch: pytest.MonkeyPatch,
    reader: Callable[[], Any],
    table: str,
) -> None:
    """An unseeded TEST provider database raises; it never returns a placeholder."""

    with disposable_slot_database("qa640_816_empty") as dbname:
        route_test_provider_database(monkeypatch.setenv, dbname)
        if table == "assets.traits":
            with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
                cur.execute("DELETE FROM assets.traits")
        message = re.escape(f"TEST provider database {dbname!r} has no {table} rows")
        with pytest.raises(RuntimeError, match=message):
            reader()


@pytest.mark.requires_postgres
def test_seeder_trait_mismatch_rolls_back_every_write() -> None:
    """A legacy trait spelling refuses the CLI seed and rolls back earlier writes."""
    with disposable_slot_database("qa640_816_legacy_trait") as dbname:
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE assets.traits SET name = 'reputation', "
                "is_selected = TRUE, rationale = 'preserve this rationale' "
                "WHERE name = 'fame'"
            )
            assert cur.rowcount == 1
            cur.execute("INSERT INTO assets.new_story_creator (id) VALUES (TRUE)")

        result = _run_test_provider_seeder(dbname)
        assert result.returncode != 0
        assert "selected unknown trait 'reputation'" in result.stderr
        assert "populated successfully" not in result.stdout
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT is_selected, rationale FROM assets.traits "
                "WHERE name = 'reputation'"
            )
            assert cur.fetchone() == (True, "preserve this rationale")
            cur.execute("SELECT count(*) FROM assets.new_story_creator")
            assert cur.fetchone() == (1,)


def _run_test_provider_seeder(dbname: str) -> subprocess.CompletedProcess[str]:
    """Run the production 008 operator against one explicit disposable target."""
    root = Path(__file__).resolve().parents[1]
    return subprocess.run(
        [
            sys.executable,
            str(root / "migrations/008_populate_mock_database.py"),
            "--dbname",
            dbname,
        ],
        cwd=root,
        env={**os.environ, "PYTHONPATH": str(root)},
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.requires_postgres
@pytest.mark.skipif(
    not (
        Path(__file__).resolve().parents[1]
        / "migrations/148_chunk_entity_references.sql"
    ).exists(),
    reason="cross-slice reseed proof requires the real migration 148",
)
def test_reseeding_test_provider_preserves_reference_parity(
    routed_test_provider_database: str,
) -> None:
    """Reseeding clears every mirrored kind while its chunk/entities survive."""
    dbname = routed_test_provider_database
    chunk_id = seed_committed_chunk(dbname, raw_text="Keep this provider chunk.")
    faction_id, faction_entity = seed_faction(dbname, name="Provider Faction")
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.chunk_entity_references')")
        assert cur.fetchone()[0] is not None, "migration 148 was not applied"
        cur.execute("SELECT id, name, entity_id FROM characters WHERE id = 1")
        character_id, character_name, character_entity = cur.fetchone()
        cur.execute("SELECT id, name, entity_id FROM places WHERE id = 1")
        place_id, place_name, place_entity = cur.fetchone()
        character = RosterEntry(kind="character", id=character_id, name=character_name)
        place = RosterEntry(kind="place", id=place_id, name=place_name)
        faction = RosterEntry(kind="faction", id=faction_id, name="Provider Faction")
        write_roster(
            conn,
            chunk_id,
            PresenceRoster(
                present={character.key: character},
                setting={place.key: place},
                referenced={faction.key: faction},
            ),
        )
    original_entities = [character_entity, place_entity, faction_entity]
    before = reference_parity(dbname, target="chunk_entity_references")
    assert before["parity"], before["kinds"]
    assert {kind: rows["target"] for kind, rows in before["kinds"].items()} == {
        "character": 1,
        "place": 1,
        "faction": 1,
    }

    for _ in range(2):
        result = _run_test_provider_seeder(dbname)
        assert result.returncode == 0, result.stderr
        after = reference_parity(dbname, target="chunk_entity_references")
        assert after["parity"], after["kinds"]
        assert all(
            rows["expected"] == rows["target"] == 0 for rows in after["kinds"].values()
        ), after["kinds"]
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT raw_text FROM narrative_chunks WHERE id = %s", (chunk_id,)
            )
            assert cur.fetchone() == ("Keep this provider chunk.",)
            cur.execute(
                "SELECT count(*) FROM entities WHERE id = ANY(%s)",
                (original_entities,),
            )
            assert cur.fetchone() == (3,)


def _post_bootstrap_request(base_url: str) -> requests.Response:
    """POST a native ``text.format`` bootstrap request to a TEST provider child."""

    return requests.post(
        f"{base_url}/responses",
        json={
            "model": "TEST",
            "input": [{"role": "user", "content": "Bootstrap the protagonist story."}],
            "text": _native_text_format(StorytellerResponseBootstrap),
        },
        timeout=30,
    )


@pytest.mark.requires_postgres
def test_child_mock_server_reads_the_routed_database(
    routed_test_provider_database: str,
    mock_openai_server: str,  # noqa: F811
) -> None:
    """A spawned TEST provider reads the clone its parent routed."""

    sentinel = f"qa640-816-sentinel-{uuid.uuid4().hex}"
    with closing(connect(routed_test_provider_database)) as conn:
        with conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE incubator SET storyteller_text = %s WHERE id = TRUE",
                (sentinel,),
            )
            assert cur.rowcount == 1

    response = _post_bootstrap_request(mock_openai_server)

    assert response.status_code == 200, response.text
    payload = json.loads(response.json()["output_text"])
    assert payload["narrative"] == sentinel


@pytest.mark.requires_postgres
def test_unrouted_child_mock_server_refuses(
    mock_openai_server: str,  # noqa: F811
    tmp_path: Path,
) -> None:
    """Without a route the child reads the never-created default and fails."""

    response = _post_bootstrap_request(mock_openai_server)

    assert response.status_code == 500, response.text
    unrouted = os.environ[TEST_PROVIDER_DATABASE_ENV]
    # Uvicorn logs the traceback after it has sent the 500, so poll briefly.
    log_path = tmp_path / "mock_openai.log"
    deadline = time.monotonic() + 10
    log = log_path.read_text(errors="replace")
    while unrouted not in log and time.monotonic() < deadline:
        time.sleep(0.1)
        log = log_path.read_text(errors="replace")
    assert unrouted in log, log


def test_requested_output_properties_extracts_schema_fields() -> None:
    """The output-tool discriminator sees the schema's top-level properties."""

    request = ResponsesRequest(
        model="TEST",
        input=[],
        tools=[_final_result_tool(StorytellerResponseBootstrap)],
    )
    fields = _requested_output_properties(request)
    assert "narrative" in fields
    assert "choices" in fields
    assert "updates" not in fields

    native_request = ResponsesRequest(
        model="TEST",
        input=[],
        text=_native_text_format(SkaldTurnWire),
    )
    native_fields = _requested_output_properties(native_request)
    assert "updates" in native_fields
    assert "presence" in native_fields

    bare = ResponsesRequest(model="TEST", input=[])
    assert _requested_output_properties(bare) == set()


def test_collect_text_uses_first_prompt_like_key() -> None:
    """Sibling text fields do not duplicate or alter higher-priority content."""

    assert (
        _collect_text(
            {
                "content": "canonical prompt with drink:aaa",
                "text": "ignored sibling with hide:bbb",
            }
        )
        == "canonical prompt with drink:aaa"
    )
