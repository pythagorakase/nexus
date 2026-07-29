"""Schema and routing coverage for TEST-mode Responses API wizard calls."""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

import psycopg2
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from psycopg2 import sql

from nexus.api import mock_openai
from nexus.api import new_story_cache as cache_module
from nexus.api import new_story_flow
from nexus.api.db_pool import close_all_pools
from nexus.api.new_story_schemas import (
    CharacterConceptSubmission,
    SettingCard,
    StorySeed,
    StorySeedSubmission,
    TraitSelection,
    WildcardTrait,
    WizardResponse,
)
from nexus.api.slot_utils import VALID_DBNAMES
from nexus.api.wizard_agent import WizardContext, get_wizard_agent

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "test_cache_wizard.json"


def _pg_array(values: List[str]) -> str:
    """Render a list in the row shape returned by the mock RealDictCursor."""

    return "{" + ",".join(values) + "}"


def _fixture_rows() -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Derive mock database rows from the persisted wizard fixture."""

    raw = json.loads(FIXTURE_PATH.read_text())
    setting = json.loads(raw["setting_draft"])
    character = json.loads(raw["character_draft"])
    seed = json.loads(raw["selected_seed"])
    location = json.loads(raw["initial_location"])
    layer = json.loads(raw["layer_draft"])
    zone = json.loads(raw["zone_draft"])
    concept = character["concept"]
    selection = character["trait_selection"]

    cache_row = {
        **{f"setting_{key}": value for key, value in setting.items()},
        "setting_themes": _pg_array(setting["themes"]),
        "setting_secondary_genres": _pg_array(setting["secondary_genres"]),
        "character_name": concept["name"],
        "character_archetype": concept["archetype"],
        "character_background": concept["background"],
        "character_appearance": concept["appearance"],
        "seed_type": seed["seed_type"],
        "seed_title": seed["title"],
        "seed_situation": seed["situation"],
        "seed_hook": seed["hook"],
        "seed_immediate_goal": seed["immediate_goal"],
        "seed_stakes": seed["stakes"],
        "seed_tension_source": seed["tension_source"],
        "seed_weather": seed["weather"],
        "seed_key_npcs": _pg_array(seed["key_npcs"]),
        "seed_secrets": seed["secrets"],
        "base_timestamp": datetime.fromisoformat(raw["base_timestamp"]),
        "initial_location": location,
        "layer_name": layer["name"],
        "layer_type": layer["type"],
        "layer_description": layer["description"],
        "zone_name": zone["name"],
        "zone_summary": zone["summary"],
    }
    selected_traits = [
        {
            "id": index,
            "name": name,
            "description": f"Mock description for {name}",
            "is_selected": True,
            "rationale": selection["trait_rationales"][name],
        }
        for index, name in enumerate(selection["selected_traits"], start=1)
    ]
    wildcard = character["wildcard"]
    trait_rows = selected_traits + [
        {
            "id": 11,
            "name": wildcard["wildcard_name"],
            "description": "Unique wildcard trait",
            "is_selected": False,
            "rationale": wildcard["wildcard_description"],
        }
    ]
    return cache_row, trait_rows


def _responses_tool(name: str, schema: type[BaseModel]) -> Dict[str, Any]:
    """Build a pydantic-ai Responses-format function tool."""

    return {
        "type": "function",
        "name": name,
        "parameters": schema.model_json_schema(),
        "strict": True,
    }


def _connect(dbname: str) -> Any:
    """Open a direct connection for disposable-database administration."""
    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


@pytest.fixture()
def disposable_timestamp_dbname() -> Iterator[str]:
    """Yield a current-template clone and remove it after the regression."""
    dbname = f"nexus_test_issue_613_{uuid.uuid4().hex[:12]}"
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


@pytest.mark.requires_postgres
def test_seconds_round_trip_through_cache_resume_and_transition(
    disposable_timestamp_dbname: str,
    monkeypatch,
) -> None:
    """Real PostgreSQL preserves an explicit second through transition."""
    raw = json.loads(FIXTURE_PATH.read_text())
    seed_payload = json.loads(raw["selected_seed"])
    seed_payload["base_timestamp"]["second"] = 30
    accepted_seed = StorySeed.model_validate(seed_payload)
    expected_timestamp = accepted_seed.get_base_datetime()
    cache_module.write_cache(
        thread_id=raw["thread_id"],
        setting_draft=json.loads(raw["setting_draft"]),
        character_draft=json.loads(raw["character_draft"]),
        selected_seed=accepted_seed.model_dump(),
        layer_draft=json.loads(raw["layer_draft"]),
        zone_draft=json.loads(raw["zone_draft"]),
        initial_location=json.loads(raw["initial_location"]),
        base_timestamp=expected_timestamp.isoformat(),
        target_slot=4,
        dbname=disposable_timestamp_dbname,
    )
    monkeypatch.setattr(
        new_story_flow,
        "slot_dbname",
        lambda _slot: disposable_timestamp_dbname,
    )

    resumed = new_story_flow.resume_setup(4)
    assert resumed is not None
    resumed_seed = resumed.get_seed_dict()
    assert resumed_seed is not None
    assert resumed_seed["base_timestamp"]["second"] == 30

    transition = new_story_flow.build_transition_data_from_cache(resumed)
    assert transition.seed.base_timestamp.second == 30
    assert transition.seed.get_base_datetime() == expected_timestamp
    assert transition.base_timestamp == expected_timestamp
    assert (
        transition.base_timestamp.astimezone(timezone.utc).isoformat()
        == "2087-11-03T22:47:30+00:00"
    )


def test_canned_artifact_arguments_validate_against_current_schemas() -> None:
    """Every row-to-arguments builder must track its live Pydantic schema."""

    cache_row, trait_rows = _fixture_rows()

    SettingCard.model_validate(mock_openai.build_setting_arguments(cache_row))
    CharacterConceptSubmission.model_validate(
        mock_openai.build_character_concept_arguments(cache_row, trait_rows)
    )
    TraitSelection.model_validate(
        mock_openai.build_trait_selection_arguments(trait_rows)
    )
    WildcardTrait.model_validate(mock_openai.build_wildcard_trait_arguments(trait_rows))
    StorySeedSubmission.model_validate(
        mock_openai.build_story_seed_arguments(cache_row)
    )


@pytest.mark.parametrize(
    ("phase", "subphase"),
    [
        ("setting", None),
        ("character", "concept"),
        ("character", "traits"),
        ("character", "wildcard"),
        ("seed", None),
    ],
)
def test_canned_intro_payloads_validate_as_wizard_response(
    phase: str, subphase: str | None
) -> None:
    """Every wizard phase introduction obeys the native output contract."""

    WizardResponse.model_validate(mock_openai.build_wizard_intro_data(phase, subphase))


@pytest.mark.parametrize(
    ("phase", "context_data", "accept_fate", "expected_name"),
    [
        ("setting", None, False, "submit_world_document"),
        ("setting", None, True, "submit_world_document"),
        ("character", {"character_state": {}}, False, "submit_character_concept"),
        ("character", {"character_state": {}}, True, "submit_character_concept"),
        (
            "character",
            {"character_state": {"concept": {}}},
            False,
            "submit_trait_selection",
        ),
        (
            "character",
            {"character_state": {"concept": {}, "trait_selection": {}}},
            False,
            "submit_wildcard_trait",
        ),
        (
            "character",
            {"character_state": {"concept": {}, "trait_selection": {}}},
            True,
            "submit_wildcard_trait",
        ),
        ("seed", None, False, "submit_starting_scenario"),
        ("seed", None, True, "submit_starting_scenario"),
    ],
)
def test_wizard_factory_tool_names_match_mock_routing(
    phase: str,
    context_data: Dict[str, Any] | None,
    accept_fate: bool,
    expected_name: str,
) -> None:
    """Keep factory tool names aligned with prompts and mock routing."""

    context = WizardContext(
        slot=1,
        cache=None,
        phase=phase,
        thread_id="tool-name-tripwire",
        model="TEST",
        context_data=context_data,
        accept_fate=accept_fate,
    )
    agent = get_wizard_agent(context)

    # Deliberate drift tripwire against pydantic-ai's registered function tools.
    registered_names = set(agent._function_toolset.tools)
    assert registered_names == {expected_name}
    assert registered_names <= mock_openai.RESPONSES_WIZARD_TOOLS.keys()


@pytest.fixture
def mock_rows(monkeypatch) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Replace the mock server's thin DB wrappers with fixture-derived rows."""

    cache_row, trait_rows = _fixture_rows()
    monkeypatch.setattr(mock_openai, "query_wizard_cache", lambda: cache_row)
    monkeypatch.setattr(mock_openai, "query_traits", lambda: trait_rows)
    return cache_row, trait_rows


@pytest.mark.parametrize(
    ("tool_name", "schema"),
    [
        ("submit_world_document", SettingCard),
        ("submit_character_concept", CharacterConceptSubmission),
        ("submit_trait_selection", TraitSelection),
        ("submit_wildcard_trait", WildcardTrait),
        ("submit_starting_scenario", StorySeedSubmission),
    ],
)
def test_responses_wizard_artifact_returns_submission_function_call(
    mock_rows, tool_name: str, schema: type[BaseModel]
) -> None:
    """A normal wizard turn invokes the phase's flattened submission tool."""

    response = TestClient(mock_openai.app).post(
        "/v1/responses",
        json={
            "model": "TEST",
            "tools": [_responses_tool(tool_name, schema)],
            "input": [{"role": "user", "content": "Accept fate."}],
        },
    )

    assert response.status_code == 200
    tool_call = response.json()["output"][0]
    assert tool_call["type"] == "function_call"
    assert tool_call["name"] == tool_name
    schema.model_validate(json.loads(tool_call["arguments"]))


@pytest.mark.parametrize(
    ("tool_name", "schema", "transition_message", "expected_copy"),
    [
        (
            "submit_character_concept",
            CharacterConceptSubmission,
            "[SYSTEM] Phase setting complete. Proceeding to character.",
            "character creation",
        ),
        (
            "submit_wildcard_trait",
            WildcardTrait,
            "[SYSTEM] Phase traits complete. Proceeding to wildcard.",
            "wildcard",
        ),
        (
            "submit_starting_scenario",
            StorySeedSubmission,
            "[SYSTEM] Phase character complete. Proceeding to seed.",
            "opening scene",
        ),
    ],
)
def test_responses_wizard_transition_returns_phase_specific_intro(
    mock_rows,
    tool_name: str,
    schema: type[BaseModel],
    transition_message: str,
    expected_copy: str,
) -> None:
    """A phase-transition turn returns WizardResponse JSON as output text."""

    response = TestClient(mock_openai.app).post(
        "/v1/responses",
        json={
            "model": "TEST",
            "tools": [_responses_tool(tool_name, schema)],
            "input": [
                {"role": "assistant", "content": "Prior wizard message."},
                {
                    "role": "user",
                    "content": transition_message,
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["output"][0]["type"] == "message"
    wizard_response = WizardResponse.model_validate_json(payload["output_text"])
    assert expected_copy in wizard_response.message.lower()


@pytest.mark.parametrize(
    "builder",
    [
        lambda cache, traits: mock_openai.build_character_concept_arguments(
            cache, traits
        ),
        lambda _cache, traits: mock_openai.build_trait_selection_arguments(traits),
    ],
)
def test_selected_trait_builders_reject_wrong_count(builder) -> None:
    """Selected-trait schema drift fails before an invalid tool call is emitted."""

    cache_row, trait_rows = _fixture_rows()
    incomplete_rows = [row for row in trait_rows if row.get("id") != 3]

    with pytest.raises(ValueError, match="exactly 3 selected rows"):
        builder(cache_row, incomplete_rows)


@pytest.mark.parametrize("rationale", [None, "too short"])
def test_wildcard_builder_rejects_missing_or_short_rationale(rationale) -> None:
    """The wildcard builder enforces the schema's minimum description length."""

    _, trait_rows = _fixture_rows()
    wildcard = next(row for row in trait_rows if row["id"] == 11)
    wildcard["rationale"] = rationale

    with pytest.raises(ValueError, match="at least 20 characters"):
        mock_openai.build_wildcard_trait_arguments(trait_rows)


def test_wildcard_builder_rejects_missing_row() -> None:
    """The wildcard builder requires the canonical id-11 row."""

    _, trait_rows = _fixture_rows()

    with pytest.raises(ValueError, match="missing.*id 11"):
        mock_openai.build_wildcard_trait_arguments(trait_rows[:-1])
