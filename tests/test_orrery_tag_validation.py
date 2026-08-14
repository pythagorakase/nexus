"""Offline tests for generation-time storyteller Orrery tag validation."""

from __future__ import annotations

import logging
from pathlib import Path
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
    collect_faction_identity_issues,
    collect_orrery_tag_issues,
)
from nexus.agents.logon.skald_wire import SkaldTurnWire
from nexus.agents.orrery.tag_library import TagLibraryEntry
from nexus.agents.orrery.tag_schemas import OrreryTagBestowal
from nexus.api.native_structured_output import structured_output_error_text
from scripts.api_anthropic import AnthropicProvider
from scripts.api_openai import OpenAIProvider


class FakeRegistryCursor:
    """Cursor stand-in serving a tiny in-memory tag registry."""

    def __init__(
        self,
        *,
        entities_by_name: Optional[dict[str, list[str]]] = None,
        entity_kinds_by_id: Optional[dict[int, str]] = None,
        faction_ids_by_name: Optional[dict[str, int]] = None,
    ) -> None:
        # tag -> (id, category, is_ephemeral, reapplication_policy)
        self.tags = {
            "human": (1, "bodyform", False, None),
            "perceptive": (2, "disposition", False, None),
            "haven": (3, "place_class", False, None),
            "recently_protective": (
                4,
                "disposition",
                True,
                "extend_expiry",
            ),
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
        self.entity_kinds_by_id = (
            {
                101: "character",
                202: "place",
                303: "faction",
            }
            if entity_kinds_by_id is None
            else entity_kinds_by_id
        )
        self.faction_ids_by_name = (
            {
                "Office of Civic Continuity": 91,
                "The Sluice Guild": 92,
                "Quay Witness Circle": 93,
            }
            if faction_ids_by_name is None
            else faction_ids_by_name
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
        if "WITH candidates AS" in sql:
            ordinals, kinds, wire_ids, names, _tags, _anchor = params
            self._result = []
            for ordinal, kind, wire_id, name in zip(ordinals, kinds, wire_ids, names):
                name_matches = self.entities_by_name.get(str(name), [])
                has_name_match = kind in name_matches
                name_entity_id = 9000 + int(ordinal) if has_name_match else None
                id_entity_id = (
                    int(wire_id)
                    if wire_id is not None
                    and self.entity_kinds_by_id.get(int(wire_id)) == kind
                    else None
                )
                verified_entity_id = id_entity_id or name_entity_id
                self._result.append(
                    (
                        ordinal,
                        id_entity_id,
                        name if id_entity_id is not None else None,
                        has_name_match,
                        name_entity_id,
                        name if name_entity_id is not None else None,
                        verified_entity_id,
                        None,
                        None,
                        False,
                    )
                )
            self._one = None
        elif "FROM entities" in sql and "kind::text" in sql:
            entity_ids = params[0]
            self._result = [
                (entity_id, self.entity_kinds_by_id[entity_id])
                for entity_id in entity_ids
                if entity_id in self.entity_kinds_by_id
            ]
            self._one = self._result[0] if self._result else None
        elif "SELECT entity_kind" in sql:
            self._result = [
                (kind,) for kind in self.entities_by_name.get(str(params[0]), [])
            ]
            self._one = self._result[0] if self._result else None
        elif "SELECT id, name FROM factions" in sql:
            self._result = [
                (faction_id, name)
                for name, faction_id in sorted(self.faction_ids_by_name.items())
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
            "character": frozenset({"human", "perceptive", "recently_protective"}),
            "place": frozenset({"haven"}),
            "faction": frozenset({"loyalist"}),
        },
        pair_tag_names=frozenset({"protects", "contact:social", "status:junior"}),
        event_types=frozenset({"evade_pursuit", "slept"}),
        tag_reapplication_policies_by_kind={
            "character": {"recently_protective": "extend_expiry"},
        },
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
            _tag_entry(
                "character",
                "disposition",
                "recently_protective",
                reapplication_policy="extend_expiry",
            ),
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
    updates: Optional[dict[str, List[dict[str, Any]]]] = None,
    orrery_adjudications: Optional[List[dict[str, Any]]] = None,
    new_entities: Optional[List[dict[str, Any]]] = None,
) -> SkaldTurnWire:
    payload: dict[str, Any] = {
        "narrative": "Marra Kest steps out from behind the sluice gate.",
        "choices": ["Question Marra.", "Keep walking."],
        "letter": "Keep Marra's divided loyalty private for the next beat.",
        "orrery_adjudications": orrery_adjudications or [],
        "new_entities": (
            [
                {
                    "kind": "character",
                    "name": "Marra Kest",
                    "summary": "A sluice keeper with divided loyalties.",
                    "tag_hints": tag_hints or [],
                    "pair_tag_hints": pair_tag_hints or [],
                }
            ]
            if new_entities is None
            else new_entities
        ),
    }
    if updates is not None:
        payload["updates"] = updates
    return SkaldTurnWire.model_validate(payload)


def _updates_block(
    *,
    characters: Optional[List[dict[str, Any]]] = None,
    places: Optional[List[dict[str, Any]]] = None,
    factions: Optional[List[dict[str, Any]]] = None,
    relationships: Optional[List[dict[str, Any]]] = None,
) -> dict[str, List[dict[str, Any]]]:
    """Build the complete provider-facing updates namespace."""

    return {
        "characters": characters or [],
        "places": places or [],
        "factions": factions or [],
        "relationships": relationships or [],
    }


def _updates_block_with_tag(
    kind: str,
    name: str,
    field_name: str,
    tag_name: str,
) -> dict[str, List[dict[str, Any]]]:
    """Build one semantic update with an Orrery tag delta."""

    wire_field = {
        "applied_tags": "tags_add",
        "tags_to_clear": "tags_clear",
    }[field_name]
    array_name = {
        "character": "characters",
        "place": "places",
        "faction": "factions",
    }[kind]
    return _updates_block(**{array_name: [{"name": name, wire_field: [tag_name]}]})


@pytest.mark.parametrize(
    "alias",
    [
        "Civic Continuity Office",
        "Blackwake Assembly",
    ],
)
def test_unpersisted_faction_aliases_fail_before_incubation(alias: str) -> None:
    """Live-reproduced prose aliases are not valid durable update identities."""

    response = _storyteller_response(
        updates=_updates_block(
            factions=[
                {
                    "name": alias,
                    "action": "tightens its control of the quay",
                }
            ]
        )
    )

    issues = collect_faction_identity_issues(response, FakeRegistryCursor())

    assert len(issues) == 1
    assert issues[0].startswith("updates.factions[0]:")
    assert f"Unknown canonical faction name {alias!r}" in issues[0]


def test_faction_update_identity_honors_same_turn_maturation_gate() -> None:
    """Declared factions are writable only when commit-time stubs are enabled."""

    canonical = _storyteller_response(
        updates=_updates_block(
            factions=[
                {
                    "id": 91,
                    "name": "Office of Civic Continuity",
                    "action": "opens a formal inquiry",
                }
            ]
        )
    )
    declared = _storyteller_response(
        updates=_updates_block(
            factions=[
                {
                    "name": "The Lantern Delegation",
                    "action": "announces its first assembly",
                }
            ]
        ),
        new_entities=[
            {
                "kind": "faction",
                "name": "The Lantern Delegation",
                "summary": "A new delegation from the outer quay.",
            }
        ],
    )
    cursor = FakeRegistryCursor()

    assert collect_faction_identity_issues(canonical, cursor) == []
    disabled_issues = collect_faction_identity_issues(declared, cursor)
    assert len(disabled_issues) == 1
    assert (
        "Unknown canonical faction name 'The Lantern Delegation'" in disabled_issues[0]
    )
    assert (
        collect_faction_identity_issues(
            declared,
            cursor,
            allow_same_turn_faction_declarations=True,
        )
        == []
    )


def test_faction_update_id_and_name_must_identify_the_same_row() -> None:
    """An ID cannot silently bless a conflicting prose alias."""

    response = _storyteller_response(
        updates=_updates_block(
            factions=[
                {
                    "id": 91,
                    "name": "Civic Continuity Office",
                    "action": "opens a formal inquiry",
                }
            ]
        )
    )

    issues = collect_faction_identity_issues(response, FakeRegistryCursor())

    assert issues == [
        "updates.factions[0]: Faction id 91 is canonically named "
        "'Office of Civic Continuity', not 'Civic Continuity Office'"
    ]


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
        updates=_updates_block_with_tag(
            kind,
            f"Known {kind}",
            canonical_field,
            valid_tag,
        )
    )
    invalid = _storyteller_response(
        updates=_updates_block_with_tag(
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


def test_cached_catalog_rejects_unexpressible_extend_expiry_add() -> None:
    response = _storyteller_response(
        updates=_updates_block(
            characters=[
                {
                    "name": "Brena Tideloft",
                    "tags_add": ["recently_protective"],
                }
            ]
        )
    )

    issues = collect_orrery_tag_issues(
        response,
        FakeRegistryCursor(),
        vocabulary=_test_vocabulary(),
    )

    assert len(issues) == 1
    assert issues[0].startswith("updates.characters[0]: applied_tags:")
    assert "reapplication_policy='extend_expiry'" in issues[0]
    assert "storyteller tags_add cannot express duration_override" in issues[0]
    assert "leave it unchanged" in issues[0]


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


def test_duplicate_invalid_hints_each_receive_bounded_suggestions() -> None:
    response = _storyteller_response(tag_hints=["humna", "humna"])

    issues = collect_orrery_tag_issues(
        response,
        FakeRegistryCursor(),
        vocabulary=_test_vocabulary(),
        suggestion_limit=1,
    )

    assert len(issues) == 2
    assert all(issue.count("did you mean:") == 1 for issue in issues)
    for issue in issues:
        suggestions = issue.split("did you mean:", 1)[1].split(",")
        assert len(suggestions) <= 1


def test_replacement_event_type_uses_cached_catalog() -> None:
    valid = _storyteller_response(
        orrery_adjudications=[
            {
                "proposal_id": "proposal-valid",
                "action": "replace",
                "replacement_state_delta": {},
                "replacement_event_type": "slept",
            }
        ]
    )
    invalid = _storyteller_response(
        orrery_adjudications=[
            {
                "proposal_id": "proposal-invalid",
                "action": "replace",
                "replacement_state_delta": {},
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
    "field_name",
    [
        "entity_tags_add",
        "entity_tags_remove",
        "entity_tags_target_add",
        "entity_tags_target_remove",
        "entity_pair_tags_target_clear_inbound",
    ],
)
def test_replacement_state_delta_rejects_every_unregistered_tag_list(
    field_name: str,
) -> None:
    response = _storyteller_response(
        orrery_adjudications=[
            {
                "proposal_id": "proposal-1",
                "action": "replace",
                "replacement_state_delta": {field_name: ["invented"]},
            }
        ]
    )

    issues = collect_orrery_tag_issues(
        response,
        FakeRegistryCursor(),
        vocabulary=_test_vocabulary(),
        proposal_bindings={
            "proposal-1": {
                "actor": 101,
                "target": 202,
            }
        },
    )

    assert len(issues) == 1
    assert f"orrery_adjudications[0].replacement_state_delta.{field_name}" in issues[0]
    assert "'invented'" in issues[0]


def test_replacement_state_delta_uses_actor_target_and_pair_partitions() -> None:
    response = _storyteller_response(
        orrery_adjudications=[
            {
                "proposal_id": "proposal-1",
                "action": "replace",
                "replacement_state_delta": {
                    "entity_tags_add": ["human"],
                    "entity_tags_remove": ["perceptive"],
                    "entity_tags_target_add": ["haven"],
                    "entity_tags_target_remove": ["haven"],
                    "entity_pair_tags_target_clear_inbound": ["protects"],
                },
            }
        ]
    )

    assert (
        collect_orrery_tag_issues(
            response,
            FakeRegistryCursor(),
            vocabulary=_test_vocabulary(),
            proposal_bindings={
                "proposal-1": {
                    "actor": 101,
                    "target": 202,
                }
            },
        )
        == []
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field_name",
    [
        "entity_tags_add",
        "entity_tags_target_add",
        "entity_pair_tags_target_clear_inbound",
    ],
)
async def test_replacement_state_delta_arm_failure_becomes_named_model_retry(
    field_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Actor, target, and pair-list shapes fail inside the repair boundary."""

    from nexus.api import db_pool

    monkeypatch.setattr(
        db_pool,
        "get_connection",
        lambda _dbname: FakeRegistryConnection(FakeRegistryCursor()),
    )
    validator = build_storyteller_tag_validator(
        "test_slot",
        proposal_bindings_provider=lambda: {
            "proposal-1": {
                "actor": 101,
                "target": 202,
            }
        },
    )
    assert validator is not None
    response = _storyteller_response(
        orrery_adjudications=[
            {
                "proposal_id": "proposal-1",
                "action": "replace",
                "replacement_state_delta": {field_name: ["invented"]},
            }
        ]
    )

    with pytest.raises(ModelRetry) as exc_info:
        await validator(SimpleNamespace(retry=0), response)

    assert (
        f"orrery_adjudications[0].replacement_state_delta.{field_name}"
        in exc_info.value.message
    )


@pytest.mark.asyncio
async def test_pair_clear_without_target_binding_becomes_named_model_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An actor-only pair clear fails while the model can repair its response."""

    from nexus.api import db_pool

    monkeypatch.setattr(
        db_pool,
        "get_connection",
        lambda _dbname: FakeRegistryConnection(FakeRegistryCursor()),
    )
    validator = build_storyteller_tag_validator(
        "test_slot",
        proposal_bindings_provider=lambda: {
            "proposal-1": {
                "actor": 101,
            }
        },
    )
    assert validator is not None
    response = _storyteller_response(
        orrery_adjudications=[
            {
                "proposal_id": "proposal-1",
                "action": "replace",
                "replacement_state_delta": {
                    "entity_pair_tags_target_clear_inbound": ["protects"],
                },
            }
        ]
    )

    with pytest.raises(ModelRetry) as exc_info:
        await validator(SimpleNamespace(retry=0), response)

    assert (
        "orrery_adjudications[0].replacement_state_delta."
        "entity_pair_tags_target_clear_inbound" in exc_info.value.message
    )
    assert "no scalar target entity binding" in exc_info.value.message


@pytest.mark.asyncio
async def test_pair_clear_rejects_target_kind_excluded_by_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bound target must be allowed on the pair tag's object side."""

    from nexus.api import db_pool

    monkeypatch.setattr(
        db_pool,
        "get_connection",
        lambda _dbname: FakeRegistryConnection(FakeRegistryCursor()),
    )
    validator = build_storyteller_tag_validator(
        "test_slot",
        proposal_bindings_provider=lambda: {
            "proposal-1": {
                "actor": 101,
                "target": 202,
            }
        },
    )
    assert validator is not None
    response = _storyteller_response(
        orrery_adjudications=[
            {
                "proposal_id": "proposal-1",
                "action": "replace",
                "replacement_state_delta": {
                    "entity_pair_tags_target_clear_inbound": ["contact:social"],
                },
            }
        ]
    )

    with pytest.raises(ModelRetry) as exc_info:
        await validator(SimpleNamespace(retry=0), response)

    assert (
        "orrery_adjudications[0].replacement_state_delta."
        "entity_pair_tags_target_clear_inbound" in exc_info.value.message
    )
    assert (
        "pair_tag 'contact:social' does not allow object_kind='place'"
        in exc_info.value.message
    )


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
    caplog: pytest.LogCaptureFixture,
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

    with caplog.at_level(
        logging.INFO,
        logger="nexus.logon.orrery_tag_validation",
    ):
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
    validation_log = next(
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith(
            "Storyteller output failed registry validation"
        )
    )
    formatted_issues = exc_info.value.message.rsplit(":\n", maxsplit=1)[1]
    assert "requesting model retry:\n- new_entities[0].tag_hints:" in validation_log
    assert validation_log.endswith(formatted_issues)


@pytest.mark.asyncio
async def test_storyteller_validator_model_retry_text_omits_wire_payload_prose(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LOGON registry retry guidance never copies narrative correspondence."""

    from nexus.api import db_pool

    sentinel = "RETRY637"
    monkeypatch.setattr(
        db_pool,
        "get_connection",
        lambda _dbname: FakeRegistryConnection(FakeRegistryCursor()),
    )
    validator = build_storyteller_tag_validator("test_slot")
    assert validator is not None
    response = _storyteller_response(tag_hints=["invented:tag"]).model_copy(
        update={
            "narrative": f"{sentinel} narrative",
            "choices": [
                f"{sentinel} choice one",
                f"{sentinel} choice two",
            ],
            "letter": f"{sentinel} letter",
        }
    )

    caplog.clear()
    with caplog.at_level(logging.INFO):
        with pytest.raises(ModelRetry) as exc_info:
            await validator(SimpleNamespace(retry=0), response)

    assert sentinel not in structured_output_error_text(exc_info.value)
    assert sentinel not in caplog.text


@pytest.mark.asyncio
async def test_storyteller_validator_retries_unexpressible_extend_expiry_add(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nexus.api import db_pool

    monkeypatch.setattr(
        db_pool,
        "get_connection",
        lambda _dbname: FakeRegistryConnection(FakeRegistryCursor()),
    )
    validator = build_storyteller_tag_validator("test_slot")
    assert validator is not None

    with pytest.raises(ModelRetry) as exc_info:
        await validator(
            SimpleNamespace(retry=0),
            _storyteller_response(
                updates=_updates_block(
                    characters=[
                        {
                            "name": "Brena Tideloft",
                            "tags_add": ["recently_protective"],
                        }
                    ]
                )
            ),
        )

    assert "updates.characters[0]" in exc_info.value.message
    assert "requires duration_override" in exc_info.value.message
    assert "omit that tag" in exc_info.value.message


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
        updates=_updates_block(
            characters=[
                {
                    "name": "Brena Tideloft",
                    "tags_add": ["human"],
                    "tags_clear": ["perceptive"],
                }
            ]
        ),
        orrery_adjudications=[
            {
                "proposal_id": "proposal-1",
                "action": "replace",
                "replacement_state_delta": {},
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
            updates=_updates_block_with_tag(
                "character",
                "Brena Tideloft",
                "applied_tags",
                "human" if valid else "humam",
            )
        )
    if boundary == "place_tags_to_clear":
        return _storyteller_response(
            updates=_updates_block_with_tag(
                "place",
                "The Lower Sluice",
                "tags_to_clear",
                "haven" if valid else "human",
            )
        )
    if boundary == "faction_applied_tags":
        return _storyteller_response(
            updates=_updates_block_with_tag(
                "faction",
                "The Sluice Guild",
                "applied_tags",
                "loyalist" if valid else "perceptive",
            )
        )
    if boundary == "faction_identity":
        return _storyteller_response(
            updates=_updates_block(
                factions=(
                    [
                        {
                            "id": 91,
                            "name": "Office of Civic Continuity",
                            "action": "opens a formal inquiry",
                        }
                    ]
                    if valid
                    else [
                        {
                            "name": "Civic Continuity Office",
                            "action": "opens a formal inquiry",
                        }
                    ]
                )
            )
        )
    if boundary == "tag_hints":
        return _storyteller_response(tag_hints=["human" if valid else "humam"])
    if boundary == "pair_tag_hints":
        return _storyteller_response(
            pair_tag_hints=[
                {
                    "tag": "protects" if valid else "protectz",
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
                    "replacement_state_delta": {},
                    "replacement_event_type": ("slept" if valid else "sleptt"),
                }
            ]
        )
    raise AssertionError(f"Unknown retry boundary {boundary!r}")


@pytest.mark.parametrize(
    ("boundary", "failure_path", "expected_suggestion"),
    [
        ("character_applied_tags", "updates.characters[0]", "human"),
        ("place_tags_to_clear", "updates.places[0]", None),
        ("faction_applied_tags", "updates.factions[0]", None),
        (
            "faction_identity",
            "updates.factions[0]",
            "Office of Civic Continuity",
        ),
        ("tag_hints", "new_entities[0].tag_hints", "human"),
        ("pair_tag_hints", "new_entities[0].pair_tag_hints[0].tag", "protects"),
        (
            "replacement_event_type",
            "orrery_adjudications[0].replacement_event_type",
            "slept",
        ),
    ],
)
def test_each_catalog_boundary_consumes_retry_and_returns_valid_output_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    failure_path: str,
    expected_suggestion: Optional[str],
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
    if expected_suggestion is not None:
        assert f"did you mean: {expected_suggestion}" in prompts[1]
    if boundary in {"character_applied_tags", "tag_hints"}:
        retry_issue = prompts[1].split("did you mean:", 1)[1]
        assert "haven" not in retry_issue
        assert "loyalist" not in retry_issue


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
            self.settings_path = Path("test-settings.toml")
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
        manage_generation_lease=False,
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


def _tag_entry(
    entity_kind: str,
    category: str,
    tag: str,
    *,
    reapplication_policy: Optional[str] = None,
) -> TagLibraryEntry:
    return TagLibraryEntry(
        entity_kind=entity_kind,
        category=category,
        tag=tag,
        is_ephemeral=False,
        description=f"{tag} description",
        category_description=f"{category} description",
        prompt_order=10,
        reapplication_policy=reapplication_policy,
    )
