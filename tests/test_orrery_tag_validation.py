"""Offline tests for generation-time storyteller Orrery tag validation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List, Optional, Tuple

import pytest
from pydantic_ai import ModelRetry

from nexus.agents.logon.apex_schema import (
    CharacterReference,
    CharacterStateUpdate,
    LocationStateUpdate,
    NewCharacter,
    NewEntityDeclaration,
    NewEntityPairTagHint,
    ReferencedEntities,
    ReferenceType,
    StateUpdates,
    StorytellerResponseExtended,
)
from nexus.agents.logon.orrery_tag_schema import (
    storyteller_anthropic_output_config,
    storyteller_openai_text_format,
    storyteller_schema_with_runtime_tag_enums,
)
from nexus.agents.logon.orrery_tag_validation import (
    build_storyteller_tag_validator,
    collect_orrery_tag_issues,
)
from nexus.agents.orrery.tag_library import TagLibraryEntry
from nexus.agents.orrery.tag_schemas import OrreryTagBestowal
from scripts.api_openai import OpenAIProvider


class FakeRegistryCursor:
    """Cursor stand-in serving a tiny in-memory tag registry."""

    def __init__(
        self,
        *,
        entities_by_name: Optional[dict[str, list[str]]] = None,
    ) -> None:
        # tag -> (id, category, is_ephemeral, reapplication_policy)
        self.tags = {
            "human": (1, "bodyform", False, None),
            "perceptive": (2, "disposition", False, None),
            "haven": (3, "place_class", False, None),
        }
        # tag -> (id, subject_kinds, object_kinds)
        self.pair_tags = {
            "protects": (11, ["character", "faction"], ["place"]),
            "contact:social": (12, ["character"], ["character"]),
            "status:junior": (13, ["character", "faction"], ["faction"]),
        }
        self.entities_by_name = (
            {
                "Brena Tideloft": ["character"],
                "The Lower Sluice": ["place"],
                "The Sluice Guild": ["faction"],
            }
            if entities_by_name is None
            else entities_by_name
        )
        self.categories_by_kind = {
            "character": {"bodyform", "disposition"},
            "place": {"place_class"},
            "faction": {"ideology"},
        }
        self._result: List[Tuple[Any, ...]] = []
        self._one: Optional[Tuple[Any, ...]] = None

    def __enter__(self) -> "FakeRegistryCursor":
        return self

    def __exit__(self, *_args: Any) -> bool:
        return False

    def execute(self, sql: str, params: Tuple[Any, ...] = ()) -> None:
        if "SELECT entity_kind" in sql:
            self._result = [
                (kind,) for kind in self.entities_by_name.get(str(params[0]), [])
            ]
            self._one = self._result[0] if self._result else None
        elif "tag_category_registry" in sql:
            kind = params[0]
            self._result = [
                (category,) for category in sorted(self.categories_by_kind[kind])
            ]
            self._one = None
        elif "FROM tags" in sql:
            row = self.tags.get(params[0])
            self._one = row
            self._result = [row] if row else []
        elif "FROM pair_tags" in sql:
            row = self.pair_tags.get(params[0])
            self._one = row
            self._result = [row] if row else []
        else:
            raise AssertionError(f"Unexpected query: {sql}")

    def fetchall(self) -> List[Tuple[Any, ...]]:
        return self._result

    def fetchone(self) -> Optional[Tuple[Any, ...]]:
        return self._one


def _response(**kwargs: Any) -> Any:
    class _FakeResponse:
        referenced_entities = kwargs.get("referenced_entities")
        state_updates = kwargs.get("state_updates")
        new_entities = kwargs.get("new_entities", [])

    return _FakeResponse()


class FakeRegistryConnection:
    """Context-managed connection exposing a fixed registry cursor."""

    def __init__(self, cursor: FakeRegistryCursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> "FakeRegistryConnection":
        return self

    def __exit__(self, *_args: Any) -> bool:
        return False

    def cursor(self) -> FakeRegistryCursor:
        return self._cursor


def _storyteller_response(
    *,
    tag_hints: Optional[List[str]] = None,
    pair_tag_hints: Optional[List[dict[str, str]]] = None,
) -> StorytellerResponseExtended:
    return StorytellerResponseExtended.model_validate(
        {
            "narrative": "Marra Kest steps out from behind the sluice gate.",
            "choices": ["Question Marra.", "Keep walking."],
            "chunk_metadata": {},
            "referenced_entities": {},
            "state_updates": {},
            "operations": None,
            "orrery_adjudications": [],
            "new_entities": [
                {
                    "kind": "character",
                    "name": "Marra Kest",
                    "summary": "A sluice keeper with divided loyalties.",
                    "tag_hints": tag_hints or [],
                    "pair_tag_hints": pair_tag_hints or [],
                }
            ],
            "reasoning": None,
        }
    )


def test_valid_bestowals_produce_no_issues() -> None:
    response = _response(
        referenced_entities=ReferencedEntities(
            characters=[
                CharacterReference(
                    reference_type=ReferenceType.PRESENT,
                    new_character=NewCharacter(
                        name="Joryn Peale",
                        summary="A frightened junior copyist.",
                        orrery_tags=OrreryTagBestowal(
                            applied_tags=["human", "perceptive"]
                        ),
                    ),
                )
            ]
        ),
    )
    assert collect_orrery_tag_issues(response, FakeRegistryCursor()) == []


def test_composite_tag_names_are_flagged_with_paths() -> None:
    response = _response(
        state_updates=StateUpdates(
            characters=[
                CharacterStateUpdate(
                    character_id=1,
                    character_name="Brena Tideloft",
                    orrery_tags=OrreryTagBestowal(
                        applied_tags=["role.resources:comfortable"]
                    ),
                )
            ],
            locations=[
                LocationStateUpdate(
                    place_id=4,
                    orrery_tags=OrreryTagBestowal(
                        applied_tags=["place_affordance:neutral_ground"]
                    ),
                )
            ],
        ),
    )
    issues = collect_orrery_tag_issues(response, FakeRegistryCursor())
    assert len(issues) == 2
    assert any(issue.startswith("state_updates.characters[0]") for issue in issues)
    assert any(issue.startswith("state_updates.locations[0]") for issue in issues)
    assert all("Unknown or deprecated" in issue for issue in issues)


def test_kind_incompatible_tags_are_flagged() -> None:
    # 'haven' is a place tag; bestowing it on a character must fail.
    response = _response(
        state_updates=StateUpdates(
            characters=[
                CharacterStateUpdate(
                    character_id=1,
                    character_name="Brena Tideloft",
                    orrery_tags=OrreryTagBestowal(applied_tags=["haven"]),
                )
            ],
        ),
    )
    issues = collect_orrery_tag_issues(response, FakeRegistryCursor())
    assert len(issues) == 1
    assert "haven" in issues[0]


def test_new_entity_hint_issues_are_path_qualified_and_aggregated() -> None:
    response = _response(
        new_entities=[
            NewEntityDeclaration.model_validate(
                {
                    "kind": "character",
                    "name": "Marra Kest",
                    "summary": "A sluice keeper with divided loyalties.",
                    "tag_hints": ["invented:tag"],
                    "pair_tag_hints": [
                        {
                            "tag": "invented_pair_tag",
                            "other_entity_name": "The Sluice Guild",
                            "declared_entity_role": "subject",
                        },
                        {
                            "tag": "protects",
                            "other_entity_name": "The Sluice Guild",
                            "declared_entity_role": "object",
                        },
                    ],
                }
            )
        ]
    )

    issues = collect_orrery_tag_issues(response, FakeRegistryCursor())

    assert len(issues) == 3
    assert issues[0].startswith("new_entities[0].tag_hints:")
    assert issues[1].startswith("new_entities[0].pair_tag_hints[0].tag:")
    assert issues[2].startswith("new_entities[0].pair_tag_hints[1].tag:")
    assert "does not allow object_kind='character'" in issues[2]


def test_registered_new_entity_hints_produce_no_issues() -> None:
    response = _storyteller_response(
        tag_hints=["human"],
        pair_tag_hints=[
            {
                "tag": "protects",
                "other_entity_name": "The Lower Sluice",
                "declared_entity_role": "subject",
            }
        ],
    )

    assert collect_orrery_tag_issues(response, FakeRegistryCursor()) == []


@pytest.mark.parametrize(
    ("other_entity_name", "entities_by_name", "message"),
    [
        ("Nobody There", {}, "does not resolve"),
        (
            "Shared Name",
            {"Shared Name": ["character", "faction"]},
            "is ambiguous",
        ),
        ("Marra Kest", {}, "cannot name the declared entity itself"),
    ],
)
def test_generation_rejects_unusable_pair_hint_endpoints(
    other_entity_name: str,
    entities_by_name: dict[str, list[str]],
    message: str,
) -> None:
    response = _storyteller_response(
        pair_tag_hints=[
            {
                "tag": "contact:social",
                "other_entity_name": other_entity_name,
                "declared_entity_role": "subject",
            }
        ]
    )

    issues = collect_orrery_tag_issues(
        response,
        FakeRegistryCursor(entities_by_name=entities_by_name),
    )

    assert any("other_entity_name" in issue and message in issue for issue in issues)


def test_generation_rejects_wrong_kind_resolved_endpoint() -> None:
    """A resolvable endpoint whose kind the registry forbids fails at generation.

    Regression for PR #515 review: contact:social (character->character) with a
    place endpoint previously passed generation and wedged the accept
    transaction inside apply_pair_tag_bestowal.
    """

    response = _storyteller_response(
        pair_tag_hints=[
            {
                "tag": "contact:social",
                "other_entity_name": "Gullwharf Market",
                "declared_entity_role": "subject",
            }
        ]
    )

    issues = collect_orrery_tag_issues(
        response,
        FakeRegistryCursor(entities_by_name={"Gullwharf Market": ["place"]}),
    )

    assert any(
        "other_entity_name" in issue and "does not allow object_kind='place'" in issue
        for issue in issues
    )


def test_generation_rejects_status_hint_with_non_faction_scope() -> None:
    response = _storyteller_response(
        pair_tag_hints=[
            {
                "tag": "status:junior",
                "other_entity_name": "Brena Tideloft",
                "declared_entity_role": "subject",
            }
        ]
    )

    issues = collect_orrery_tag_issues(response, FakeRegistryCursor())

    assert any("object endpoint to be a faction" in issue for issue in issues)


def test_generation_accepts_same_batch_pair_hint_endpoint() -> None:
    declarations = [
        NewEntityDeclaration.model_validate(
            {
                "kind": "character",
                "name": "Marra Kest",
                "summary": "A sluice keeper with divided loyalties.",
                "pair_tag_hints": [
                    {
                        "tag": "status:junior",
                        "other_entity_name": "The New Assembly",
                        "declared_entity_role": "subject",
                    }
                ],
            }
        ),
        NewEntityDeclaration.model_validate(
            {
                "kind": "faction",
                "name": "The New Assembly",
                "summary": "A newly chartered institution.",
            }
        ),
    ]

    assert (
        collect_orrery_tag_issues(
            _response(new_entities=declarations),
            FakeRegistryCursor(entities_by_name={}),
        )
        == []
    )


def test_declaration_schema_describes_generation_and_commit_validation() -> None:
    """Schema documentation matches the two validation boundaries."""

    declaration_description = " ".join(
        NewEntityDeclaration.model_json_schema()["description"].split()
    )
    pair_hint_description = " ".join(
        NewEntityPairTagHint.model_json_schema()["description"].split()
    )

    assert "generation-time repair" in declaration_description
    assert "commit-time validation" in declaration_description
    assert "during generation" in pair_hint_description
    assert "commit path revalidates" in pair_hint_description


@pytest.mark.asyncio
async def test_storyteller_validator_attributes_declaration_failure_to_model_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nexus.api import db_pool

    cursor = FakeRegistryCursor()
    monkeypatch.setattr(
        db_pool,
        "get_connection",
        lambda _dbname: FakeRegistryConnection(cursor),
    )
    validator = build_storyteller_tag_validator("test_slot")
    assert validator is not None

    with pytest.raises(ModelRetry) as exc_info:
        await validator(
            SimpleNamespace(retry=0),
            _storyteller_response(
                tag_hints=["invented:tag"],
                pair_tag_hints=[
                    {
                        "tag": "contact:social",
                        "other_entity_name": "Brena Tideloft",
                        "declared_entity_role": "subject",
                    }
                ],
            ),
        )

    assert "new_entities[0].tag_hints" in exc_info.value.message
    assert "For applied_tags and tag_hints" in exc_info.value.message
    assert "pair tags may contain colons" in exc_info.value.message
    assert "'contact:social'" in exc_info.value.message
    assert "resubmit the complete response" in exc_info.value.message


def test_provider_repairs_invalid_declaration_inside_structured_retry_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the repaired response can escape LOGON's provider boundary."""

    from nexus.api import db_pool

    cursor = FakeRegistryCursor()
    monkeypatch.setattr(
        db_pool,
        "get_connection",
        lambda _dbname: FakeRegistryConnection(cursor),
    )

    invalid = _storyteller_response(tag_hints=["invented:tag"])
    repaired = _storyteller_response(tag_hints=["human"])
    prompts: list[str] = []
    outputs = [invalid, repaired]

    class FakeResponses:
        def parse(self, **kwargs: Any) -> Any:
            prompts.append(kwargs["input"][-1]["content"])
            output = outputs.pop(0)
            return SimpleNamespace(
                output_parsed=output,
                output_text=output.model_dump_json(),
                usage=SimpleNamespace(input_tokens=11, output_tokens=22),
            )

    provider = OpenAIProvider(
        model="gpt-4.1",
        api_key="test-key",
        structured_output_retries=1,
        output_validator=build_storyteller_tag_validator("test_slot"),
    )
    provider.client = SimpleNamespace(responses=FakeResponses())

    parsed, _llm_response = provider.get_structured_completion(
        "Continue the story.", StorytellerResponseExtended
    )

    assert parsed == repaired
    assert outputs == []
    assert len(prompts) == 2
    assert "=== STRUCTURED OUTPUT RETRY ===" in prompts[1]
    assert "new_entities[0].tag_hints" in prompts[1]


@pytest.mark.asyncio
async def test_exhausted_declaration_validation_never_reaches_incubator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A declaration rejected at LOGON's boundary cannot be persisted."""

    from nexus.api import db_pool, narrative_generation

    cursor = FakeRegistryCursor()
    monkeypatch.setattr(
        db_pool,
        "get_connection",
        lambda _dbname: FakeRegistryConnection(cursor),
    )
    validator = build_storyteller_tag_validator("test_slot")
    assert validator is not None

    class InvalidDeclarationLore:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self.turn_context = SimpleNamespace(error_log=[])

        async def process_turn(
            self,
            _user_text: str,
            parent_chunk_id: int,
            note: Optional[str] = None,
        ) -> Any:
            del parent_chunk_id, note
            return await validator(
                SimpleNamespace(retry=1),
                _storyteller_response(tag_hints=["invented:tag"]),
            )

        def close(self) -> None:
            pass

    class GenerationConnection:
        closed = False

        def close(self) -> None:
            self.closed = True

    class ProgressManager:
        def __init__(self) -> None:
            self.events: list[tuple[str, str, Optional[dict[str, Any]]]] = []

        async def send_progress(
            self,
            session_id: str,
            status: str,
            data: Optional[dict[str, Any]] = None,
        ) -> None:
            self.events.append((session_id, status, data))

    async def get_chunk_info(_conn: Any, _chunk_id: int) -> dict[str, Any]:
        return {"season": 1, "episode": 1, "place_name": "The Sluice"}

    async def reject_incubator_write(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("invalid declaration output must not reach the incubator")

    monkeypatch.setattr(narrative_generation, "LORE", InvalidDeclarationLore)
    monkeypatch.setattr(narrative_generation, "get_chunk_info", get_chunk_info)
    monkeypatch.setattr(
        narrative_generation, "write_to_incubator", reject_incubator_write
    )
    conn = GenerationConnection()
    manager = ProgressManager()

    await narrative_generation.generate_narrative_async(
        session_id="invalid-declaration",
        parent_chunk_id=12,
        user_text="Continue.",
        slot=5,
        get_db_connection=lambda _slot: conn,
        load_settings=lambda: {},
        manager=manager,
    )

    errors = [data for _session, status, data in manager.events if status == "error"]
    assert len(errors) == 1
    assert errors[0] is not None
    assert "new_entities[0].tag_hints" in errors[0]["error"]
    assert conn.closed is True


def test_validator_skipped_without_slot_database() -> None:
    assert build_storyteller_tag_validator(None) is None
    assert build_storyteller_tag_validator("") is None
    assert build_storyteller_tag_validator("save_05") is not None


def test_storyteller_schema_uses_runtime_tag_enums(monkeypatch) -> None:
    """Native LOGON schema constrains Orrery tags by live entity kind."""

    from nexus.agents.logon import orrery_tag_schema
    from nexus.agents.logon.apex_schema import StorytellerResponseExtended

    entries = [
        _tag_entry("character", "bodyform", "human"),
        _tag_entry("character", "disposition", "perceptive"),
        _tag_entry("place", "place_class", "haven"),
        _tag_entry("faction", "ideology", "loyalist"),
    ]
    monkeypatch.setattr(
        orrery_tag_schema,
        "read_tag_library",
        lambda _dbname: entries,
    )

    schema = storyteller_schema_with_runtime_tag_enums(
        StorytellerResponseExtended,
        "save_05",
    )

    assert schema is not None
    defs = schema["$defs"]
    character_tags = defs["OrreryTagBestowalCharacter"]["properties"]["applied_tags"][
        "items"
    ]["enum"]
    place_tags = defs["OrreryTagBestowalPlace"]["properties"]["applied_tags"]["items"][
        "enum"
    ]
    faction_tags = defs["OrreryTagBestowalFaction"]["properties"]["tags_to_clear"][
        "items"
    ]["enum"]
    assert character_tags == ["human", "perceptive"]
    assert place_tags == ["haven"]
    assert faction_tags == ["loyalist"]
    assert (
        defs["NewCharacter"]["properties"]["orrery_tags"]["anyOf"][0]["$ref"]
        == "#/$defs/OrreryTagBestowalCharacter"
    )
    assert (
        defs["LocationStateUpdate"]["properties"]["orrery_tags"]["anyOf"][0]["$ref"]
        == "#/$defs/OrreryTagBestowalPlace"
    )
    assert (
        defs["FactionStateUpdate"]["properties"]["orrery_tags"]["anyOf"][0]["$ref"]
        == "#/$defs/OrreryTagBestowalFaction"
    )


def test_storyteller_openai_text_format_wraps_runtime_schema(monkeypatch) -> None:
    from nexus.agents.logon import orrery_tag_schema
    from nexus.agents.logon.apex_schema import StorytellerResponseExtended

    monkeypatch.setattr(
        orrery_tag_schema,
        "read_tag_library",
        lambda _dbname: [_tag_entry("character", "bodyform", "human")],
    )

    text_format = storyteller_openai_text_format(
        StorytellerResponseExtended,
        "save_05",
    )

    assert text_format is not None
    assert text_format["type"] == "json_schema"
    assert text_format["strict"] is True
    assert text_format["schema"]["$defs"]["OrreryTagBestowalCharacter"]["properties"][
        "applied_tags"
    ]["items"]["enum"] == ["human"]


def test_storyteller_anthropic_output_config_uses_compact_extended_schema(
    monkeypatch,
) -> None:
    """Anthropic extended turns avoid the full DB-mirroring grammar."""

    from nexus.agents.logon import orrery_tag_schema
    from nexus.agents.logon.apex_schema import StorytellerResponseExtended

    entries = [
        _tag_entry("character", "bodyform", "human"),
        _tag_entry("character", "disposition", "perceptive"),
        _tag_entry("place", "place_class", "haven"),
        _tag_entry("faction", "ideology", "loyalist"),
    ]
    monkeypatch.setattr(
        orrery_tag_schema,
        "read_tag_library",
        lambda _dbname: entries,
    )
    monkeypatch.setattr(
        orrery_tag_schema,
        "_read_pair_tags",
        lambda _dbname: ["hiding", "shelters"],
    )
    monkeypatch.setattr(
        orrery_tag_schema,
        "_read_event_types",
        lambda _dbname: ["evade_pursuit", "slept"],
    )

    output_config = storyteller_anthropic_output_config(
        StorytellerResponseExtended,
        "save_05",
    )

    assert output_config is not None
    schema = output_config["format"]["schema"]
    assert "$defs" not in schema
    assert set(schema["properties"]) == {
        "narrative",
        "choices",
        "chunk_metadata",
        "referenced_entities",
        "state_updates",
        "operations",
        "orrery_adjudications",
        "new_entities",
        "reasoning",
    }
    state_update_schema = schema["properties"]["state_updates"]
    assert set(state_update_schema["properties"]) == {
        "updates",
    }
    update_schema = state_update_schema["properties"]["updates"]["items"]
    assert update_schema["properties"]["kind"]["enum"] == [
        "character",
        "place",
        "faction",
    ]
    assert update_schema["properties"]["tag_add"] == {
        "type": "string",
        "description": "Registered tag name to apply.",
    }
    entity_schema = schema["properties"]["new_entities"]["items"]
    assert entity_schema["properties"]["tag_hints"]["items"]["enum"] == [
        "haven",
        "human",
        "loyalist",
        "perceptive",
    ]
    pair_tag_schema = entity_schema["properties"]["pair_tag_hints"]["items"]
    assert pair_tag_schema["properties"]["tag"]["enum"] == ["hiding", "shelters"]
    adjudication_schema = schema["properties"]["orrery_adjudications"]["items"]
    assert adjudication_schema["properties"]["replacement_event_type"]["enum"] == [
        "evade_pursuit",
        "slept",
    ]

    response = StorytellerResponseExtended.model_validate(
        {
            "narrative": "Brena follows the wet bell-sound into the stacks.",
            "choices": ["Follow the footprints.", "Call for Odile."],
            "chunk_metadata": {},
            "referenced_entities": {},
            "state_updates": {
                "updates": [
                    {
                        "kind": "character",
                        "name": "Brena Tideloft",
                        "status": "following a wet bell-sound",
                        "tag_add": "perceptive",
                    }
                ]
            },
            "operations": {},
            "orrery_adjudications": [],
            "new_entities": [
                {
                    "kind": "character",
                    "name": "Marra Kest",
                    "summary": "A drowned clerk animated by echo and current.",
                    "tag_hints": [],
                    "pair_tag_hints": [],
                }
            ],
            "reasoning": "",
        }
    )

    assert response.state_updates.characters[0].character_name == "Brena Tideloft"
    assert (
        response.state_updates.characters[0].current_activity
        == "following a wet bell-sound"
    )
    assert response.state_updates.characters[0].orrery_tags is not None
    assert response.state_updates.characters[0].orrery_tags.applied_tags == [
        "perceptive"
    ]
    assert response.new_entities[0].name == "Marra Kest"


def _tag_entry(entity_kind: str, category: str, tag: str) -> TagLibraryEntry:
    return TagLibraryEntry(
        entity_kind=entity_kind,
        category=category,
        tag=tag,
        is_ephemeral=False,
        description=f"{tag} description",
        category_description=f"{category} description",
        prompt_order=10,
    )
