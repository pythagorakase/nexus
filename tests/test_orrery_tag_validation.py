"""Offline tests for generation-time storyteller Orrery tag validation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast, List, Literal, Optional, Tuple

import pytest
from pydantic_ai import ModelRetry

from nexus.agents.logon.apex_schema import (
    CharacterStateUpdate,
    LocationStateUpdate,
    NewEntityDeclaration,
    NewEntityPairTagHint,
    StateUpdates,
)
from nexus.agents.logon.orrery_tag_validation import (
    StorytellerVocabulary,
    build_storyteller_tag_validator,
    collect_orrery_tag_issues,
)
from nexus.agents.logon.skald_wire import SkaldTurnWire
from nexus.agents.orrery.tag_library import TagLibraryEntry
from nexus.agents.orrery.tag_schemas import OrreryTagBestowal
from scripts.api_anthropic import AnthropicProvider
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

    def __exit__(self, *_args: Any) -> Literal[False]:
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
            tag_row: Optional[Tuple[Any, ...]] = self.tags.get(params[0])
            self._one = tag_row
            self._result = [tag_row] if tag_row else []
        elif "FROM pair_tags" in sql:
            pair_tag_row: Optional[Tuple[Any, ...]] = self.pair_tags.get(params[0])
            self._one = pair_tag_row
            self._result = [pair_tag_row] if pair_tag_row else []
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

    def __exit__(self, *_args: Any) -> Literal[False]:
        return False

    def cursor(self) -> FakeRegistryCursor:
        return self._cursor


def _test_vocabulary() -> StorytellerVocabulary:
    return StorytellerVocabulary(
        tag_names_by_kind={
            "character": frozenset({"human", "perceptive"}),
            "place": frozenset({"haven"}),
            "faction": frozenset({"loyalist"}),
        },
        pair_tag_names=frozenset({"protects", "contact:social", "status:junior"}),
        event_types=frozenset({"evade_pursuit", "slept"}),
    )


@pytest.fixture(autouse=True)
def _stub_storyteller_vocabulary_readers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep generation-validator tests offline with deterministic catalogs."""

    from nexus.agents.logon import orrery_tag_validation

    monkeypatch.setattr(
        orrery_tag_validation,
        "read_tag_library",
        lambda _dbname: [
            _tag_entry("character", "bodyform", "human"),
            _tag_entry("character", "disposition", "perceptive"),
            _tag_entry("place", "place_class", "haven"),
            _tag_entry("faction", "ideology", "loyalist"),
        ],
    )
    monkeypatch.setattr(
        orrery_tag_validation,
        "read_pair_tag_library",
        lambda _dbname: ["protects", "contact:social", "status:junior"],
    )
    monkeypatch.setattr(
        orrery_tag_validation,
        "read_event_types",
        lambda _dbname: ["evade_pursuit", "slept"],
    )


def _storyteller_response(
    *,
    tag_hints: Optional[List[str]] = None,
    pair_tag_hints: Optional[List[dict[str, str]]] = None,
    updates: Optional[List[dict[str, Any]]] = None,
    orrery_adjudications: Optional[List[dict[str, Any]]] = None,
) -> SkaldTurnWire:
    return SkaldTurnWire.model_validate(
        {
            "narrative": "Marra Kest steps out from behind the sluice gate.",
            "choices": ["Question Marra.", "Keep walking."],
            "updates": updates or [],
            "orrery_adjudications": orrery_adjudications or [],
            "new_entities": [
                {
                    "kind": "character",
                    "name": "Marra Kest",
                    "summary": "A sluice keeper with divided loyalties.",
                    "tag_hints": tag_hints or [],
                    "pair_tag_hints": pair_tag_hints or [],
                }
            ],
        }
    )


def _state_updates_with_tag(
    kind: str,
    name: str,
    field_name: str,
    tag_name: str,
) -> List[dict[str, Any]]:
    """Build one semantic update with an Orrery tag delta."""

    wire_field = {
        "applied_tags": "tags_add",
        "tags_to_clear": "tags_clear",
    }[field_name]
    return [{"kind": kind, "name": name, wire_field: [tag_name]}]


def test_valid_bestowals_produce_no_issues() -> None:
    response = _response(
        state_updates=StateUpdates(
            characters=[
                CharacterStateUpdate(
                    character_id=1,
                    character_name="Joryn Peale",
                    orrery_tags=OrreryTagBestowal(applied_tags=["human", "perceptive"]),
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


@pytest.mark.parametrize(
    ("kind", "valid_tag", "invalid_tag"),
    [
        ("character", "human", "haven"),
        ("place", "haven", "human"),
        ("faction", "loyalist", "perceptive"),
    ],
)
@pytest.mark.parametrize(
    "canonical_field",
    [
        "applied_tags",
        "tags_to_clear",
    ],
)
def test_cached_catalog_validates_single_tags_per_kind_and_field(
    kind: str,
    valid_tag: str,
    invalid_tag: str,
    canonical_field: str,
) -> None:
    valid = _storyteller_response(
        updates=_state_updates_with_tag(
            kind,
            f"Known {kind}",
            canonical_field,
            valid_tag,
        )
    )
    invalid = _storyteller_response(
        updates=_state_updates_with_tag(
            kind,
            f"Known {kind}",
            canonical_field,
            invalid_tag,
        )
    )

    assert (
        collect_orrery_tag_issues(
            valid,
            FakeRegistryCursor(),
            vocabulary=_test_vocabulary(),
        )
        == []
    )
    issues = collect_orrery_tag_issues(
        invalid,
        FakeRegistryCursor(),
        vocabulary=_test_vocabulary(),
    )
    assert len(issues) == 1
    assert canonical_field in issues[0]
    assert invalid_tag in issues[0]
    assert kind in issues[0]


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

    issues = collect_orrery_tag_issues(
        response,
        FakeRegistryCursor(),
        vocabulary=_test_vocabulary(),
    )

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

    assert (
        collect_orrery_tag_issues(
            response,
            FakeRegistryCursor(),
            vocabulary=_test_vocabulary(),
        )
        == []
    )


def test_replacement_event_type_uses_cached_catalog() -> None:
    valid = _storyteller_response(
        orrery_adjudications=[
            {
                "proposal_id": "proposal-valid",
                "action": "replace",
                "replacement_event_type": "slept",
            }
        ]
    )
    invalid = _storyteller_response(
        orrery_adjudications=[
            {
                "proposal_id": "proposal-invalid",
                "action": "replace",
                "replacement_event_type": "invented_event",
            }
        ]
    )

    assert (
        collect_orrery_tag_issues(
            valid,
            FakeRegistryCursor(),
            vocabulary=_test_vocabulary(),
        )
        == []
    )
    issues = collect_orrery_tag_issues(
        invalid,
        FakeRegistryCursor(),
        vocabulary=_test_vocabulary(),
    )
    assert issues == [
        "orrery_adjudications[0].replacement_event_type: Unknown or "
        "deprecated event type 'invented_event'"
    ]


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

    assert any(
        "other_entity_name" in issue
        and "does not allow object_kind='character'" in issue
        for issue in issues
    )


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
    assert "For tags_add, tags_clear, and tag_hints" in exc_info.value.message
    assert "pair tags may contain colons" in exc_info.value.message
    assert "'contact:social'" in exc_info.value.message
    assert "resubmit the complete response" in exc_info.value.message


@pytest.mark.asyncio
async def test_storyteller_validator_reads_each_catalog_once_per_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nexus.agents.logon import orrery_tag_validation
    from nexus.api import db_pool

    read_counts = {"tags": 0, "pair_tags": 0, "event_types": 0}

    def read_tags(_dbname: str) -> list[TagLibraryEntry]:
        read_counts["tags"] += 1
        return [
            _tag_entry("character", "bodyform", "human"),
            _tag_entry("character", "disposition", "perceptive"),
        ]

    def read_pair_tags(_dbname: str) -> list[str]:
        read_counts["pair_tags"] += 1
        return ["protects"]

    def read_registered_event_types(_dbname: str) -> list[str]:
        read_counts["event_types"] += 1
        return ["slept"]

    monkeypatch.setattr(orrery_tag_validation, "read_tag_library", read_tags)
    monkeypatch.setattr(
        orrery_tag_validation,
        "read_pair_tag_library",
        read_pair_tags,
    )
    monkeypatch.setattr(
        orrery_tag_validation,
        "read_event_types",
        read_registered_event_types,
    )
    monkeypatch.setattr(
        db_pool,
        "get_connection",
        lambda _dbname: FakeRegistryConnection(FakeRegistryCursor()),
    )
    validator = build_storyteller_tag_validator("test_slot")
    assert validator is not None
    response = _storyteller_response(
        tag_hints=["human", "perceptive"],
        pair_tag_hints=[
            {
                "tag": "protects",
                "other_entity_name": "The Lower Sluice",
                "declared_entity_role": "subject",
            }
        ],
        updates=[
            {
                "kind": "character",
                "name": "Brena Tideloft",
                "tags_add": ["human"],
                "tags_clear": ["perceptive"],
            }
        ],
        orrery_adjudications=[
            {
                "proposal_id": "proposal-1",
                "action": "replace",
                "replacement_event_type": "slept",
            }
        ],
    )

    assert await validator(SimpleNamespace(retry=0), response) is response
    assert read_counts == {"tags": 1, "pair_tags": 1, "event_types": 1}


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
    provider.client = cast(Any, SimpleNamespace(responses=FakeResponses()))

    parsed, _llm_response = provider.get_structured_completion(
        "Continue the story.", SkaldTurnWire
    )

    assert parsed == repaired
    assert outputs == []
    assert len(prompts) == 2
    assert "=== STRUCTURED OUTPUT RETRY ===" in prompts[1]
    assert "new_entities[0].tag_hints" in prompts[1]


def test_openai_chat_transport_repairs_invalid_declaration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The local-model Chat transport enforces catalog validation and repair."""

    from nexus.api import db_pool

    monkeypatch.setattr(
        db_pool,
        "get_connection",
        lambda _dbname: FakeRegistryConnection(FakeRegistryCursor()),
    )
    invalid = _storyteller_response(tag_hints=["invented:tag"])
    repaired = _storyteller_response(tag_hints=["human"])
    outputs = [invalid, repaired]
    prompts: list[str] = []

    class FakeChatCompletions:
        def create(self, **kwargs: Any) -> Any:
            prompts.append(kwargs["messages"][-1]["content"])
            output = outputs.pop(0)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=output.model_dump_json())
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=11, completion_tokens=22),
            )

    provider = OpenAIProvider(
        model="local-test-model",
        api_key="test-key",
        base_url="http://127.0.0.1:8012/v1",
        structured_transport="chat_completions",
        structured_output_retries=1,
        output_validator=build_storyteller_tag_validator("test_slot"),
    )
    provider.client = cast(
        Any,
        SimpleNamespace(
            chat=SimpleNamespace(completions=FakeChatCompletions()),
        ),
    )

    parsed, llm_response = provider.get_structured_completion(
        "Continue the story.",
        SkaldTurnWire,
    )

    assert parsed == repaired
    assert llm_response.content == repaired.model_dump_json()
    assert llm_response.content != invalid.model_dump_json()
    assert outputs == []
    assert len(prompts) == 2
    assert "=== STRUCTURED OUTPUT RETRY ===" in prompts[1]
    assert "new_entities[0].tag_hints" in prompts[1]


def test_anthropic_transport_repairs_invalid_declaration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Anthropic Messages enforces catalog validation inside its retry loop."""

    from nexus.api import db_pool

    monkeypatch.setattr(
        db_pool,
        "get_connection",
        lambda _dbname: FakeRegistryConnection(FakeRegistryCursor()),
    )
    invalid = _storyteller_response(tag_hints=["invented:tag"])
    repaired = _storyteller_response(tag_hints=["human"])
    outputs = [invalid, repaired]
    prompts: list[str] = []

    class FakeMessages:
        def create(self, **kwargs: Any) -> Any:
            prompts.append(kwargs["messages"][-1]["content"])
            output = outputs.pop(0)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(type="text", text=output.model_dump_json()),
                ],
                usage=SimpleNamespace(input_tokens=33, output_tokens=44),
            )

    provider = AnthropicProvider(
        model="claude-sonnet-4-5",
        api_key="test-key",
        structured_output_retries=1,
        output_validator=build_storyteller_tag_validator("test_slot"),
    )
    provider.client = cast(
        Any,
        SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages())),
    )

    parsed, llm_response = provider.get_structured_completion(
        "Continue the story.",
        SkaldTurnWire,
    )

    assert parsed == repaired
    assert llm_response.content == repaired.model_dump_json()
    assert llm_response.content != invalid.model_dump_json()
    assert outputs == []
    assert len(prompts) == 2
    assert "=== STRUCTURED OUTPUT RETRY ===" in prompts[1]
    assert "new_entities[0].tag_hints" in prompts[1]


@pytest.mark.asyncio
async def test_openai_chat_transport_async_repairs_invalid_declaration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real async Chat entry point reaches the same catalog validator."""

    from nexus.api import db_pool

    monkeypatch.setattr(
        db_pool,
        "get_connection",
        lambda _dbname: FakeRegistryConnection(FakeRegistryCursor()),
    )
    invalid = _storyteller_response(tag_hints=["invented:tag"])
    repaired = _storyteller_response(tag_hints=["human"])
    outputs = [invalid, repaired]
    prompts: list[str] = []

    class FakeChatCompletions:
        def create(self, **kwargs: Any) -> Any:
            prompts.append(kwargs["messages"][-1]["content"])
            output = outputs.pop(0)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=output.model_dump_json())
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=11, completion_tokens=22),
            )

    provider = OpenAIProvider(
        model="local-test-model",
        api_key="test-key",
        base_url="http://127.0.0.1:8012/v1",
        structured_transport="chat_completions",
        structured_output_retries=1,
        output_validator=build_storyteller_tag_validator("test_slot"),
    )
    provider.client = cast(
        Any,
        SimpleNamespace(
            chat=SimpleNamespace(completions=FakeChatCompletions()),
        ),
    )

    parsed, llm_response = await provider.get_structured_completion_async(
        "Continue the story.",
        SkaldTurnWire,
    )

    assert parsed == repaired
    assert llm_response.content == repaired.model_dump_json()
    assert llm_response.content != invalid.model_dump_json()
    assert outputs == []
    assert len(prompts) == 2
    assert "=== STRUCTURED OUTPUT RETRY ===" in prompts[1]
    assert "new_entities[0].tag_hints" in prompts[1]


def _retry_boundary_response(
    boundary: str,
    *,
    valid: bool,
) -> SkaldTurnWire:
    if boundary == "character_applied_tags":
        return _storyteller_response(
            updates=_state_updates_with_tag(
                "character",
                "Brena Tideloft",
                "applied_tags",
                "human" if valid else "haven",
            )
        )
    if boundary == "place_tags_to_clear":
        return _storyteller_response(
            updates=_state_updates_with_tag(
                "place",
                "The Lower Sluice",
                "tags_to_clear",
                "haven" if valid else "human",
            )
        )
    if boundary == "faction_applied_tags":
        return _storyteller_response(
            updates=_state_updates_with_tag(
                "faction",
                "The Sluice Guild",
                "applied_tags",
                "loyalist" if valid else "perceptive",
            )
        )
    if boundary == "tag_hints":
        return _storyteller_response(tag_hints=["human" if valid else "invented:tag"])
    if boundary == "pair_tag_hints":
        return _storyteller_response(
            pair_tag_hints=[
                {
                    "tag": "protects" if valid else "invented_pair_tag",
                    "other_entity_name": "The Lower Sluice",
                    "declared_entity_role": "subject",
                }
            ]
        )
    if boundary == "replacement_event_type":
        return _storyteller_response(
            orrery_adjudications=[
                {
                    "proposal_id": "proposal-1",
                    "action": "replace",
                    "replacement_event_type": ("slept" if valid else "invented_event"),
                }
            ]
        )
    raise AssertionError(f"Unknown retry boundary {boundary!r}")


@pytest.mark.parametrize(
    ("boundary", "failure_path"),
    [
        ("character_applied_tags", "updates[0]"),
        ("place_tags_to_clear", "updates[0]"),
        ("faction_applied_tags", "updates[0]"),
        ("tag_hints", "new_entities[0].tag_hints"),
        ("pair_tag_hints", "new_entities[0].pair_tag_hints[0].tag"),
        (
            "replacement_event_type",
            "orrery_adjudications[0].replacement_event_type",
        ),
    ],
)
def test_each_catalog_boundary_consumes_retry_and_returns_valid_output_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    failure_path: str,
) -> None:
    """Every moved catalog is enforced inside the bounded provider retry."""

    from nexus.api import db_pool

    cursor = FakeRegistryCursor()
    monkeypatch.setattr(
        db_pool,
        "get_connection",
        lambda _dbname: FakeRegistryConnection(cursor),
    )
    invalid = _retry_boundary_response(boundary, valid=False)
    valid = _retry_boundary_response(boundary, valid=True)
    outputs = [invalid, valid]
    prompts: list[str] = []

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
    provider.client = cast(Any, SimpleNamespace(responses=FakeResponses()))

    parsed, _llm_response = provider.get_structured_completion(
        "Continue the story.",
        SkaldTurnWire,
    )

    assert parsed is valid
    assert outputs == []
    assert len(prompts) == 2
    assert "=== STRUCTURED OUTPUT RETRY ===" in prompts[1]
    assert failure_path in prompts[1]


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
    storyteller_validator = validator

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
            return await storyteller_validator(
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
