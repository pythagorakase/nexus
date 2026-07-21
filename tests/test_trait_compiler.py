"""Tests for deterministic trait-to-Orrery compilation."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Optional

import pytest

from nexus.api.new_story_schemas import CharacterSheet, CharacterTrait
from nexus.api.trait_compiler import (
    apply_character_trait_compilation,
    compile_character_traits,
    persist_trait_compile_result,
    reconcile_trait_relationship_pair_tags,
)
from nexus.api.trait_compiler_schemas import (
    DependentsTraitInput,
    DependentTargetInput,
    DomainTraitInput,
    ObligationsTraitInput,
    ObligationTargetInput,
    PatronTraitInput,
    RelationshipTargetInput,
    RelationshipTraitInput,
    SingleEntityTraitInput,
    StatusTraitInput,
    TraitCompileInputs,
    TraitCompileReasonCode,
    TraitCompileResult,
)


class TraitCompilerCursor:
    """Fake psycopg cursor for the compiler and Orrery writer SQL shapes."""

    def __init__(self, *, fail_relationship: bool = False):
        self.tags = {
            "wealthy": {"id": 10, "category": "role.resources"},
            "known": {"id": 11, "category": "role.fame"},
            "poor": {"id": 12, "category": "role.resources"},
        }
        self.category_registry = {
            "character": {"role.resources", "role.fame"},
        }
        self.pair_tags = {
            "status:senior": {
                "id": 100,
                "subject_kinds": ["character", "faction"],
                "object_kinds": ["faction"],
            },
            "ally": {
                "id": 101,
                "subject_kinds": ["character"],
                "object_kinds": ["character"],
            },
            "contact": {
                "id": 102,
                "subject_kinds": ["character"],
                "object_kinds": ["character"],
            },
            "contact:lodging": {
                "id": 104,
                "subject_kinds": ["character"],
                "object_kinds": ["character"],
            },
            "contact:social": {
                "id": 105,
                "subject_kinds": ["character"],
                "object_kinds": ["character"],
            },
            "contact:intimate": {
                "id": 106,
                "subject_kinds": ["character"],
                "object_kinds": ["character"],
            },
            "hostile_to": {
                "id": 103,
                "subject_kinds": ["character", "faction"],
                "object_kinds": ["character", "faction"],
            },
            "claims": {
                "id": 110,
                "subject_kinds": ["character", "faction"],
                "object_kinds": ["place"],
            },
            "protects": {
                "id": 111,
                "subject_kinds": ["character", "faction"],
                "object_kinds": ["character"],
            },
            "obligation": {
                "id": 112,
                "subject_kinds": ["character", "faction"],
                "object_kinds": ["character", "faction"],
            },
            "mentors": {
                "id": 113,
                "subject_kinds": ["character"],
                "object_kinds": ["character"],
            },
            "sponsors": {
                "id": 114,
                "subject_kinds": ["character", "faction"],
                "object_kinds": ["character"],
            },
            "authority_over": {
                "id": 115,
                "subject_kinds": ["character", "faction"],
                "object_kinds": ["character", "faction"],
            },
        }
        self.characters: dict[int, dict[str, Any]] = {
            1: {"entity_id": 501, "name": "Mara"},
            2: {"entity_id": 502, "name": "Bren"},
        }
        self.places: dict[int, dict[str, Any]] = {
            7: {"entity_id": 701, "name": "The Roost"},
        }
        self.factions: dict[int, dict[str, Any]] = {
            3: {"entity_id": 900, "name": "The Guild"},
        }
        self.entity_tags: list[dict[str, Any]] = []
        self.entity_pair_tags: list[dict[str, Any]] = []
        self.character_relationships: list[dict[str, Any]] = []
        self.fail_relationship = fail_relationship
        self.rowcount = 0
        self._next_row: Optional[Any] = None
        self._next_rows: list[Any] = []
        self._savepoints: list[dict[str, Any]] = []

    def _lookup_rows(
        self, table: dict[int, dict[str, Any]], normalized: str, params: tuple
    ) -> list[tuple[int, int, str]]:
        (value,) = params
        if "WHERE ID =" in normalized:
            rows = [(row_id, row) for row_id, row in table.items() if row_id == value]
        elif "WHERE ENTITY_ID =" in normalized:
            rows = [
                (row_id, row)
                for row_id, row in table.items()
                if row["entity_id"] == value
            ]
        else:
            rows = [
                (row_id, row) for row_id, row in table.items() if row["name"] == value
            ]
        return [
            (row_id, row["entity_id"], row["name"])
            for row_id, row in sorted(rows, key=lambda item: item[0])
        ]

    def execute(self, sql: str, params: Optional[tuple] = None) -> None:
        params = params or ()
        normalized = " ".join(sql.strip().upper().split())

        if normalized.startswith("SAVEPOINT"):
            self._savepoints.append(
                deepcopy(
                    {
                        "entity_pair_tags": self.entity_pair_tags,
                        "character_relationships": self.character_relationships,
                        "entity_tags": self.entity_tags,
                        "characters": self.characters,
                        "places": self.places,
                        "factions": self.factions,
                    }
                )
            )
            self.rowcount = 0
            return
        if normalized.startswith("ROLLBACK TO SAVEPOINT"):
            snapshot = deepcopy(self._savepoints[-1])
            self.entity_pair_tags = snapshot["entity_pair_tags"]
            self.character_relationships = snapshot["character_relationships"]
            self.entity_tags = snapshot["entity_tags"]
            self.characters = snapshot["characters"]
            self.places = snapshot["places"]
            self.factions = snapshot["factions"]
            self.rowcount = 0
            return
        if normalized.startswith("RELEASE SAVEPOINT"):
            self._savepoints.pop()
            self.rowcount = 0
            return

        if normalized.startswith("SELECT ID, ENTITY_ID, NAME FROM CHARACTERS"):
            self._next_rows = self._lookup_rows(self.characters, normalized, params)
            self.rowcount = len(self._next_rows)
            return

        if normalized.startswith("SELECT ID, ENTITY_ID, NAME FROM PLACES"):
            self._next_rows = self._lookup_rows(self.places, normalized, params)
            self.rowcount = len(self._next_rows)
            return

        if normalized.startswith("SELECT ID, ENTITY_ID, NAME FROM FACTIONS"):
            self._next_rows = self._lookup_rows(self.factions, normalized, params)
            self.rowcount = len(self._next_rows)
            return

        if normalized.startswith("SELECT KIND::TEXT AS KIND FROM ENTITIES"):
            entity_id = int(params[0])
            kind = next(
                (
                    entity_kind
                    for table, entity_kind in (
                        (self.characters, "character"),
                        (self.places, "place"),
                        (self.factions, "faction"),
                    )
                    if any(int(row["entity_id"]) == entity_id for row in table.values())
                ),
                None,
            )
            self._next_row = (kind,) if kind is not None else None
            self.rowcount = int(kind is not None)
            return

        if "TRAIT_COMPILER:INSERT_CHARACTER_STUB" in normalized:
            name, _summary, _background, _activity, extra_data = params
            row_id = max(self.characters, default=0) + 1
            entity_id = 1000 + row_id
            self.characters[row_id] = {
                "entity_id": entity_id,
                "name": name,
                "extra_data": json.loads(extra_data),
            }
            self._next_row = (row_id, entity_id)
            self.rowcount = 1
            return

        if "TRAIT_COMPILER:INSERT_PLACE_STUB" in normalized:
            name, _summary, _status, extra_data = params
            row_id = max(self.places, default=0) + 1
            entity_id = 2000 + row_id
            self.places[row_id] = {
                "entity_id": entity_id,
                "name": name,
                "extra_data": json.loads(extra_data),
            }
            self._next_row = (row_id, entity_id)
            self.rowcount = 1
            return

        if normalized.startswith("LOCK TABLE FACTIONS"):
            self.rowcount = 0
            return

        if normalized.startswith("SELECT COALESCE(MAX(ID), 0) + 1 AS ID FROM FACTIONS"):
            self._next_row = (max(self.factions, default=0) + 1,)
            self.rowcount = 1
            return

        if "TRAIT_COMPILER:INSERT_FACTION_STUB" in normalized:
            row_id, name, _summary, extra_data = params
            entity_id = 3000 + row_id
            self.factions[row_id] = {
                "entity_id": entity_id,
                "name": name,
                "extra_data": json.loads(extra_data),
            }
            self._next_row = (entity_id,)
            self.rowcount = 1
            return

        if normalized.startswith("SELECT MAX(WORLD_TIME)"):
            self._next_row = (None,)
            self.rowcount = 1
            return

        if "FROM TAG_CATEGORY_REGISTRY" in normalized:
            (entity_kind,) = params
            self._next_rows = [
                (category,)
                for category in self.category_registry.get(entity_kind, set())
            ]
            self.rowcount = len(self._next_rows)
            return

        if normalized.startswith("SELECT ID, CATEGORY, IS_EPHEMERAL"):
            (tag,) = params
            row = self.tags.get(tag)
            self._next_row = (
                (row["id"], row["category"], False, None) if row is not None else None
            )
            self.rowcount = 1 if row else 0
            return

        if normalized.startswith("SELECT 1 FROM TAGS"):
            tag, category = params
            row = self.tags.get(tag)
            self._next_row = (1,) if row and row["category"] == category else None
            self.rowcount = 1 if self._next_row else 0
            return

        if normalized.startswith("SELECT 1 FROM PAIR_TAGS"):
            (tag,) = params
            self._next_row = (1,) if tag in self.pair_tags else None
            self.rowcount = 1 if self._next_row else 0
            return

        if normalized.startswith("SELECT ID, SUBJECT_KINDS, OBJECT_KINDS"):
            (tag,) = params
            row = self.pair_tags.get(tag)
            self._next_row = (
                (row["id"], row["subject_kinds"], row["object_kinds"])
                if row is not None
                else None
            )
            self.rowcount = 1 if row else 0
            return

        if normalized.startswith("SELECT ENTITY_ID FROM FACTIONS"):
            (name,) = params
            entity_ids = [
                row["entity_id"]
                for row in self.factions.values()
                if row["name"] == name
            ]
            self._next_row = (entity_ids[0],) if entity_ids else None
            self.rowcount = 1 if entity_ids else 0
            return

        if normalized.startswith("UPDATE ENTITY_TAGS ET"):
            entity_id, category, keep_tag_id = params
            tag_by_id = {row["id"]: row for row in self.tags.values()}
            cleared = 0
            for row in self.entity_tags:
                tag_row = tag_by_id[row["tag_id"]]
                if (
                    row["entity_id"] == entity_id
                    and row["tag_id"] != keep_tag_id
                    and tag_row["category"] == category
                    and row["cleared_at"] is None
                ):
                    row["cleared_at"] = "now"
                    cleared += 1
            self.rowcount = cleared
            return

        if normalized.startswith("INSERT INTO ENTITY_TAGS"):
            if len(params) == 4:
                entity_id, tag_id, _world_time, source_kind = params
            else:
                entity_id, tag_id, _world_time, _expires_at_world_time, source_kind = (
                    params[:5]
                )
            active = [
                row
                for row in self.entity_tags
                if row["entity_id"] == entity_id
                and row["tag_id"] == tag_id
                and row["cleared_at"] is None
            ]
            if active:
                self.rowcount = 0
                return
            self.entity_tags.append(
                {
                    "entity_id": entity_id,
                    "tag_id": tag_id,
                    "source_kind": source_kind,
                    "cleared_at": None,
                }
            )
            self.rowcount = 1
            return

        if normalized.startswith("UPDATE ENTITY_PAIR_TAGS EPT"):
            subject_id, object_id, tags = params
            tag_by_id = {row["id"]: tag for tag, row in self.pair_tags.items()}
            cleared = 0
            for row in self.entity_pair_tags:
                tag = tag_by_id[row["pair_tag_id"]]
                if (
                    row["subject_entity_id"] == subject_id
                    and row["object_entity_id"] == object_id
                    and tag in tags
                    and row["cleared_at"] is None
                ):
                    row["cleared_at"] = "now"
                    cleared += 1
            self.rowcount = cleared
            return

        if normalized.startswith("INSERT INTO ENTITY_PAIR_TAGS"):
            (
                subject_id,
                object_id,
                pair_tag_id,
                _world_time,
                source_kind,
                _source_chunk_id,
                _template_id,
            ) = params
            active = [
                row
                for row in self.entity_pair_tags
                if row["subject_entity_id"] == subject_id
                and row["object_entity_id"] == object_id
                and row["pair_tag_id"] == pair_tag_id
                and row["cleared_at"] is None
            ]
            if active:
                self.rowcount = 0
                return
            self.entity_pair_tags.append(
                {
                    "subject_entity_id": subject_id,
                    "object_entity_id": object_id,
                    "pair_tag_id": pair_tag_id,
                    "source_kind": source_kind,
                    "cleared_at": None,
                }
            )
            self.rowcount = 1
            return

        if normalized.startswith("INSERT INTO CHARACTER_RELATIONSHIPS"):
            if self.fail_relationship:
                raise RuntimeError("relationship write failed")
            (
                character1_id,
                character2_id,
                relationship_type,
                emotional_valence,
                dynamic,
                recent_events,
                history,
                extra_data,
            ) = params
            self.character_relationships.append(
                {
                    "character1_id": character1_id,
                    "character2_id": character2_id,
                    "relationship_type": relationship_type,
                    "emotional_valence": emotional_valence,
                    "dynamic": dynamic,
                    "recent_events": recent_events,
                    "history": history,
                    "extra_data": extra_data,
                }
            )
            self.rowcount = 1
            return

        if "AND CR.CHARACTER1_ID IS NULL" in normalized:
            tags = set(params[0])
            rows = []
            tag_by_id = {row["id"]: tag for tag, row in self.pair_tags.items()}
            entity_to_character = {
                row["entity_id"]: character_id
                for character_id, row in self.characters.items()
            }
            relationship_keys = {
                (row["character1_id"], row["character2_id"])
                for row in self.character_relationships
            }
            relationship_keys |= {
                (character2_id, character1_id)
                for character1_id, character2_id in relationship_keys
            }
            for row in self.entity_pair_tags:
                tag = tag_by_id[row["pair_tag_id"]]
                character1_id = entity_to_character.get(row["subject_entity_id"])
                character2_id = entity_to_character.get(row["object_entity_id"])
                if (
                    tag in tags
                    and row["cleared_at"] is None
                    and (character1_id, character2_id) not in relationship_keys
                ):
                    rows.append(
                        (
                            row["subject_entity_id"],
                            row["object_entity_id"],
                            tag,
                            character1_id,
                            character2_id,
                        )
                    )
            self._next_rows = rows
            self.rowcount = len(rows)
            return

        if "CR.EXTRA_DATA->>'TRAIT_COMPILER_PAIR_TAG' = ANY" in normalized:
            tags = set(params[0])
            rows = []
            character_to_entity = {
                character_id: row["entity_id"]
                for character_id, row in self.characters.items()
            }
            tag_by_id = {row["id"]: tag for tag, row in self.pair_tags.items()}
            active_pair_keys = {
                (
                    row["subject_entity_id"],
                    row["object_entity_id"],
                    tag_by_id[row["pair_tag_id"]],
                )
                for row in self.entity_pair_tags
                if row["cleared_at"] is None
            }
            for row in self.character_relationships:
                extra_data = row["extra_data"]
                if isinstance(extra_data, str):
                    extra_data = json.loads(extra_data)
                pair_tag = extra_data.get("trait_compiler_pair_tag")
                if pair_tag not in tags:
                    continue
                character1_entity_id = character_to_entity[row["character1_id"]]
                character2_entity_id = character_to_entity[row["character2_id"]]
                pair_key = (
                    character1_entity_id,
                    character2_entity_id,
                    pair_tag,
                )
                if (
                    extra_data.get("trait_compiler_pair_tag_direction")
                    == "target_to_protagonist"
                ):
                    pair_key = (
                        character2_entity_id,
                        character1_entity_id,
                        pair_tag,
                    )
                if pair_key not in active_pair_keys:
                    rows.append(
                        (
                            character1_entity_id,
                            character2_entity_id,
                            pair_tag,
                            row["character1_id"],
                            row["character2_id"],
                        )
                    )
            self._next_rows = rows
            self.rowcount = len(rows)
            return

        raise AssertionError(f"Unhandled SQL: {sql.strip()[:120]}")

    def fetchone(self):
        row = self._next_row
        self._next_row = None
        return row

    def fetchall(self):
        rows = self._next_rows
        self._next_rows = []
        return rows


def _character(
    *trait_names: str,
    inputs: TraitCompileInputs | None = None,
) -> CharacterSheet:
    traits = [
        CharacterTrait(name=trait_name, description=f"{trait_name} description")
        for trait_name in trait_names
    ]
    return CharacterSheet(
        name="Mara",
        summary="A wary operator with ties across the city.",
        appearance="Lean, watchful, and dressed for quick departures.",
        background="Mara has survived by cultivating favors and avoiding easy debts.",
        personality="Careful, loyal to a fault, and slow to trust strangers.",
        wildcard_name="Storm Marked",
        wildcard_description="Lightning follows her in ways nobody can explain.",
        trait_1=traits[0],
        trait_2=traits[1],
        trait_3=traits[2],
        trait_compile_inputs=inputs,
    )


def test_no_typed_inputs_returns_structured_remainders() -> None:
    cur = TraitCompilerCursor()
    result = compile_character_traits(
        cur,
        character=_character("resources", "status", "allies"),
        character_id=1,
        character_entity_id=501,
        dry_run=True,
    )

    assert result.counters.prose_only_remainders == 3
    assert {item.trait for item in result.prose_only_remainders} == {
        "resources",
        "status",
        "allies",
    }
    assert {item.reason_code for item in result.prose_only_remainders} == {
        TraitCompileReasonCode.MISSING_STRUCTURED_TRAIT_INPUT
    }


def test_resources_and_reputation_compile_to_single_entity_tags() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(
        resources=SingleEntityTraitInput(level="wealthy"),
        reputation=SingleEntityTraitInput(level="known"),
    )

    result = apply_character_trait_compilation(
        cur,
        character=_character("resources", "reputation", "domain", inputs=inputs),
        character_id=1,
        character_entity_id=501,
    )

    assert {
        (item.trait, item.tag, item.category)
        for item in result.applied_single_entity_tags
    } == {
        ("resources", "wealthy", "role.resources"),
        ("reputation", "known", "role.fame"),
    }
    assert {row["tag_id"] for row in cur.entity_tags} == {10, 11}
    assert result.counters.prose_only_remainders == 1


def test_status_compiles_to_scoped_pair_tag() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(
        status=StatusTraitInput(scope_faction_entity_id=900, level="senior")
    )

    result = apply_character_trait_compilation(
        cur,
        character=_character("status", "resources", "domain", inputs=inputs),
        character_id=1,
        character_entity_id=501,
    )

    assert result.applied_pair_tags[0].tag == "status:senior"
    assert cur.entity_pair_tags == [
        {
            "subject_entity_id": 501,
            "object_entity_id": 900,
            "pair_tag_id": 100,
            "source_kind": "skald_inline",
            "cleared_at": None,
        }
    ]


def test_allies_default_to_relationship_without_pair_tag() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(
        allies=RelationshipTraitInput(
            targets=[
                RelationshipTargetInput(
                    character_id=2,
                    character_entity_id=502,
                    dynamic="A trusted ally from before the story opens.",
                )
            ]
        )
    )

    result = apply_character_trait_compilation(
        cur,
        character=_character("allies", "resources", "domain", inputs=inputs),
        character_id=1,
        character_entity_id=501,
    )

    assert result.created_relationships[0].relationship_type == "ally"
    assert result.applied_pair_tags == []
    assert cur.entity_pair_tags == []


def test_explicit_ally_pair_tag_writes_both_layers() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(
        allies=RelationshipTraitInput(
            targets=[
                RelationshipTargetInput(
                    character_id=2,
                    character_entity_id=502,
                    dynamic="A package gate explicitly needs this ally edge.",
                    apply_pair_tag=True,
                )
            ]
        )
    )

    result = apply_character_trait_compilation(
        cur,
        character=_character("allies", "resources", "domain", inputs=inputs),
        character_id=1,
        character_entity_id=501,
    )

    assert result.applied_pair_tags[0].tag == "ally"
    assert result.created_relationships[0].pair_tag == "ally"
    assert len(cur.entity_pair_tags) == 1
    assert len(cur.character_relationships) == 1


def test_contacts_pair_tag_requires_kind() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(
        contacts=RelationshipTraitInput(
            targets=[
                RelationshipTargetInput(
                    character_id=2,
                    character_entity_id=502,
                    dynamic="A contact without a known gate kind.",
                    apply_pair_tag=True,
                )
            ]
        )
    )

    result = apply_character_trait_compilation(
        cur,
        character=_character("contacts", "resources", "domain", inputs=inputs),
        character_id=1,
        character_entity_id=501,
    )

    assert result.applied_pair_tags == []
    assert cur.entity_pair_tags == []
    assert result.prose_only_remainders[0].reason_code == (
        TraitCompileReasonCode.MISSING_STRUCTURED_TRAIT_INPUT
    )
    assert "contact_kind" in result.prose_only_remainders[0].message


def test_contact_kind_pair_tag_writes_kind_specific_edge() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(
        contacts=RelationshipTraitInput(
            targets=[
                RelationshipTargetInput(
                    character_id=2,
                    character_entity_id=502,
                    dynamic="A lodging contact for safe-house access.",
                    apply_pair_tag=True,
                    contact_kind="lodging",
                )
            ]
        )
    )

    result = apply_character_trait_compilation(
        cur,
        character=_character("contacts", "resources", "domain", inputs=inputs),
        character_id=1,
        character_entity_id=501,
    )

    assert result.applied_pair_tags[0].tag == "contact:lodging"
    assert result.created_relationships[0].pair_tag == "contact:lodging"
    assert result.created_relationships[0].contact_kind == "lodging"
    assert cur.entity_pair_tags[0]["pair_tag_id"] == 104
    assert (
        '"trait_compiler_contact_kind": "lodging"'
        in cur.character_relationships[0]["extra_data"]
    )


def test_explicit_contact_pair_tag_infers_contact_kind_metadata() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(
        contacts=RelationshipTraitInput(
            targets=[
                RelationshipTargetInput(
                    character_id=2,
                    character_entity_id=502,
                    dynamic="A social contact for messages and favors.",
                    apply_pair_tag=True,
                    pair_tag="contact:social",
                )
            ]
        )
    )

    result = apply_character_trait_compilation(
        cur,
        character=_character("contacts", "resources", "domain", inputs=inputs),
        character_id=1,
        character_entity_id=501,
    )

    assert result.applied_pair_tags[0].tag == "contact:social"
    assert result.created_relationships[0].pair_tag == "contact:social"
    assert result.created_relationships[0].contact_kind == "social"
    assert cur.entity_pair_tags[0]["pair_tag_id"] == 105
    assert (
        '"trait_compiler_contact_kind": "social"'
        in cur.character_relationships[0]["extra_data"]
    )


def test_unknown_contact_pair_tag_is_structured_remainder() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(
        contacts=RelationshipTraitInput(
            targets=[
                RelationshipTargetInput(
                    character_id=2,
                    character_entity_id=502,
                    dynamic="A contact with an unsupported gate kind.",
                    apply_pair_tag=True,
                    pair_tag="contact:trade",
                )
            ]
        )
    )

    result = apply_character_trait_compilation(
        cur,
        character=_character("contacts", "resources", "domain", inputs=inputs),
        character_id=1,
        character_entity_id=501,
    )

    assert result.applied_pair_tags == []
    assert cur.entity_pair_tags == []
    assert result.prose_only_remainders[0].reason_code == (
        TraitCompileReasonCode.MISSING_STRUCTURED_TRAIT_INPUT
    )
    assert result.prose_only_remainders[0].details["pair_tag"] == "contact:trade"


def test_enemy_pair_tag_can_point_from_target_to_protagonist() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(
        enemies=RelationshipTraitInput(
            targets=[
                RelationshipTargetInput(
                    character_id=2,
                    character_entity_id=502,
                    dynamic="The enemy is hunting for payback.",
                    apply_pair_tag=True,
                    pair_tag_direction="target_to_protagonist",
                )
            ]
        )
    )

    result = apply_character_trait_compilation(
        cur,
        character=_character("enemies", "resources", "domain", inputs=inputs),
        character_id=1,
        character_entity_id=501,
    )

    assert result.applied_pair_tags[0].tag == "hostile_to"
    assert result.applied_pair_tags[0].subject_entity_id == 502
    assert result.applied_pair_tags[0].object_entity_id == 501
    assert result.created_relationships[0].relationship_type == "enemy"
    assert cur.entity_pair_tags[0]["subject_entity_id"] == 502
    assert cur.entity_pair_tags[0]["object_entity_id"] == 501
    assert cur.character_relationships[0]["character1_id"] == 1
    assert cur.character_relationships[0]["character2_id"] == 2
    assert (
        '"trait_compiler_pair_tag_direction": "target_to_protagonist"'
        in cur.character_relationships[0]["extra_data"]
    )
    assert reconcile_trait_relationship_pair_tags(cur) == []


def test_failed_relationship_write_rolls_back_pair_tag_savepoint() -> None:
    cur = TraitCompilerCursor(fail_relationship=True)
    inputs = TraitCompileInputs(
        allies=RelationshipTraitInput(
            targets=[
                RelationshipTargetInput(
                    character_id=2,
                    character_entity_id=502,
                    apply_pair_tag=True,
                )
            ]
        )
    )

    with pytest.raises(RuntimeError, match="relationship write failed"):
        apply_character_trait_compilation(
            cur,
            character=_character("allies", "resources", "domain", inputs=inputs),
            character_id=1,
            character_entity_id=501,
        )

    assert cur.entity_pair_tags == []
    assert cur.character_relationships == []


def test_reconciliation_reports_pair_tag_without_relationship() -> None:
    cur = TraitCompilerCursor()
    cur.entity_pair_tags.append(
        {
            "subject_entity_id": 501,
            "object_entity_id": 502,
            "pair_tag_id": 101,
            "source_kind": "skald_inline",
            "cleared_at": None,
        }
    )

    drift = reconcile_trait_relationship_pair_tags(cur)

    assert len(drift) == 1
    assert drift[0].drift_kind == "missing_relationship"
    assert drift[0].pair_tag == "ally"


def test_reconciliation_reports_relationship_without_pair_tag() -> None:
    cur = TraitCompilerCursor()
    cur.character_relationships.append(
        {
            "character1_id": 1,
            "character2_id": 2,
            "relationship_type": "ally",
            "emotional_valence": "+3|trusting",
            "dynamic": "A compiler-authored ally relationship.",
            "recent_events": "",
            "history": "",
            "extra_data": json.dumps(
                {
                    "source": "trait_compiler",
                    "trait": "allies",
                    "trait_compiler_pair_tag": "ally",
                }
            ),
        }
    )

    drift = reconcile_trait_relationship_pair_tags(cur)

    assert len(drift) == 1
    assert drift[0].drift_kind == "missing_pair_tag"
    assert drift[0].pair_tag == "ally"


def test_reconciliation_ignores_deprecated_bare_contact_pair_tag() -> None:
    cur = TraitCompilerCursor()
    cur.character_relationships.append(
        {
            "character1_id": 1,
            "character2_id": 2,
            "relationship_type": "contact",
            "emotional_valence": "+1|favorable",
            "dynamic": "Legacy compiler-authored contact relationship.",
            "recent_events": "",
            "history": "",
            "extra_data": json.dumps(
                {
                    "source": "trait_compiler",
                    "trait": "contacts",
                    "trait_compiler_pair_tag": "contact",
                }
            ),
        }
    )

    assert reconcile_trait_relationship_pair_tags(cur) == []


def test_new_trait_compilers_without_inputs_return_structured_remainders() -> None:
    cur = TraitCompilerCursor()
    result = compile_character_traits(
        cur,
        character=_character("domain", "patron", "dependents"),
        character_id=1,
        character_entity_id=501,
        dry_run=True,
    )

    assert result.counters.prose_only_remainders == 3
    assert {item.trait for item in result.prose_only_remainders} == {
        "domain",
        "patron",
        "dependents",
    }
    assert {item.reason_code for item in result.prose_only_remainders} == {
        TraitCompileReasonCode.MISSING_STRUCTURED_TRAIT_INPUT
    }


def test_domain_claims_existing_place_by_name() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(domain=DomainTraitInput(name="The Roost"))

    result = apply_character_trait_compilation(
        cur,
        character=_character("domain", "resources", "allies", inputs=inputs),
        character_id=1,
        character_entity_id=501,
    )

    domain_tags = [item for item in result.applied_pair_tags if item.trait == "domain"]
    assert domain_tags[0].tag == "claims"
    assert domain_tags[0].subject_entity_id == 501
    assert domain_tags[0].object_entity_id == 701
    assert result.created_entities == []
    assert cur.entity_pair_tags[0]["pair_tag_id"] == 110


def test_domain_creates_place_stub_for_unknown_name() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(domain=DomainTraitInput(name="Hollow Spire"))

    result = apply_character_trait_compilation(
        cur,
        character=_character("domain", "resources", "allies", inputs=inputs),
        character_id=1,
        character_entity_id=501,
    )

    created = result.created_entities[0]
    assert created.entity_kind == "place"
    assert created.name == "Hollow Spire"
    assert created.entity_id is not None
    assert created.row_id is not None
    stub_row = cur.places[created.row_id]
    assert stub_row["extra_data"]["source"] == "trait_compiler"
    assert stub_row["extra_data"]["stub_kind"] == "trait_compiler_target_ref"
    assert stub_row["extra_data"]["sources"][0]["trait"] == "domain"
    assert cur.entity_pair_tags[0]["object_entity_id"] == created.entity_id


def test_domain_dry_run_reports_pending_stub_without_writes() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(domain=DomainTraitInput(name="Hollow Spire"))

    result = compile_character_traits(
        cur,
        character=_character("domain", "resources", "allies", inputs=inputs),
        character_id=1,
        character_entity_id=501,
        dry_run=True,
    )

    domain_tags = [item for item in result.applied_pair_tags if item.trait == "domain"]
    assert domain_tags[0].object_entity_id is None
    assert domain_tags[0].object_name == "Hollow Spire"
    assert result.created_entities[0].entity_id is None
    assert result.created_entities[0].dry_run is True
    assert cur.entity_pair_tags == []
    assert all(item.trait != "domain" for item in result.prose_only_remainders)


def test_domain_unknown_place_id_is_structured_remainder() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(domain=DomainTraitInput(place_id=999))

    result = compile_character_traits(
        cur,
        character=_character("domain", "resources", "allies", inputs=inputs),
        character_id=1,
        character_entity_id=501,
        dry_run=True,
    )

    remainder = result.prose_only_remainders[0]
    assert remainder.trait == "domain"
    assert remainder.reason_code == TraitCompileReasonCode.AMBIGUOUS_TARGET
    assert remainder.details["place_id"] == 999


def test_patron_default_compiles_relationship_row_only() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(
        patron=PatronTraitInput(
            name="Magistrate Hale",
            dynamic="Hale opens doors and expects discretion.",
        )
    )

    result = apply_character_trait_compilation(
        cur,
        character=_character("patron", "resources", "allies", inputs=inputs),
        character_id=1,
        character_entity_id=501,
    )

    assert result.applied_pair_tags == []
    assert cur.entity_pair_tags == []
    created = result.created_entities[0]
    assert created.entity_kind == "character"
    assert created.name == "Magistrate Hale"
    relationship = result.created_relationships[0]
    assert relationship.relationship_type == "patron"
    assert relationship.emotional_valence == "+2|friendly"
    assert relationship.character2_id == created.row_id
    assert cur.character_relationships[0]["character2_id"] == created.row_id
    extra_data = json.loads(cur.character_relationships[0]["extra_data"])
    assert extra_data["source"] == "trait_compiler"
    assert "trait_compiler_patron_functions" not in extra_data


def test_patron_user_affirmed_functions_write_pair_tags() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(
        patron=PatronTraitInput(
            character_id=2,
            functions=["sponsors", "mentors", "sponsors"],
        )
    )

    result = apply_character_trait_compilation(
        cur,
        character=_character("patron", "resources", "allies", inputs=inputs),
        character_id=1,
        character_entity_id=501,
    )

    assert [
        (item.tag, item.subject_entity_id, item.object_entity_id)
        for item in result.applied_pair_tags
    ] == [
        ("sponsors", 502, 501),
        ("mentors", 502, 501),
    ]
    assert {row["pair_tag_id"] for row in cur.entity_pair_tags} == {113, 114}
    extra_data = json.loads(cur.character_relationships[0]["extra_data"])
    assert extra_data["trait_compiler_patron_functions"] == ["sponsors", "mentors"]


def test_patron_unregistered_function_is_structured_remainder() -> None:
    cur = TraitCompilerCursor()
    del cur.pair_tags["sponsors"]
    inputs = TraitCompileInputs(
        patron=PatronTraitInput(character_id=2, functions=["sponsors"])
    )

    result = apply_character_trait_compilation(
        cur,
        character=_character("patron", "resources", "allies", inputs=inputs),
        character_id=1,
        character_entity_id=501,
    )

    remainder = result.prose_only_remainders[0]
    assert remainder.trait == "patron"
    assert remainder.reason_code == TraitCompileReasonCode.REGISTRY_MISSING_PAIR_TAG
    assert remainder.details["pair_tag"] == "sponsors"
    assert cur.entity_pair_tags == []
    assert cur.character_relationships == []


def test_dependents_compile_protects_edge_and_relationship_per_target() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(
        dependents=DependentsTraitInput(
            targets=[
                DependentTargetInput(character_id=2),
                DependentTargetInput(name="Pip"),
            ]
        )
    )

    result = apply_character_trait_compilation(
        cur,
        character=_character("dependents", "resources", "allies", inputs=inputs),
        character_id=1,
        character_entity_id=501,
    )

    assert result.counters.prose_only_remainders == 2  # resources/allies no input
    assert all(item.tag == "protects" for item in result.applied_pair_tags)
    assert all(item.subject_entity_id == 501 for item in result.applied_pair_tags)
    assert len(result.applied_pair_tags) == 2
    assert len(result.created_relationships) == 2
    assert {item.relationship_type for item in result.created_relationships} == {
        "dependent"
    }
    created = result.created_entities[0]
    assert created.entity_kind == "character"
    assert created.name == "Pip"
    extra_data = json.loads(cur.character_relationships[0]["extra_data"])
    assert extra_data["trait_compiler_functional_pair_tag"] == "protects"
    assert reconcile_trait_relationship_pair_tags(cur) == []


def test_dependent_target_resolving_to_protagonist_is_remainder() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(
        dependents=DependentsTraitInput(targets=[DependentTargetInput(name="Mara")])
    )

    result = apply_character_trait_compilation(
        cur,
        character=_character("dependents", "resources", "allies", inputs=inputs),
        character_id=1,
        character_entity_id=501,
    )

    remainder = result.prose_only_remainders[0]
    assert remainder.trait == "dependents"
    assert remainder.reason_code == TraitCompileReasonCode.AMBIGUOUS_TARGET
    assert "protagonist" in remainder.message
    assert cur.entity_pair_tags == []
    assert cur.character_relationships == []


def test_ambiguous_target_name_is_structured_remainder() -> None:
    cur = TraitCompilerCursor()
    cur.characters[4] = {"entity_id": 504, "name": "Bren"}
    inputs = TraitCompileInputs(
        dependents=DependentsTraitInput(targets=[DependentTargetInput(name="Bren")])
    )

    result = compile_character_traits(
        cur,
        character=_character("dependents", "resources", "allies", inputs=inputs),
        character_id=1,
        character_entity_id=501,
        dry_run=True,
    )

    remainder = result.prose_only_remainders[0]
    assert remainder.trait == "dependents"
    assert remainder.reason_code == TraitCompileReasonCode.AMBIGUOUS_TARGET
    assert remainder.details["match_count"] == 2


def test_obligation_character_counterparty_writes_edge_and_relationship() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(
        obligations=ObligationsTraitInput(
            targets=[
                ObligationTargetInput(
                    counterparty_kind="character",
                    counterparty_id=2,
                    dynamic="A debt collector with a patient ledger.",
                )
            ]
        )
    )

    result = apply_character_trait_compilation(
        cur,
        character=_character("obligations", "resources", "allies", inputs=inputs),
        character_id=1,
        character_entity_id=501,
    )

    tag = result.applied_pair_tags[0]
    assert tag.tag == "obligation"
    assert tag.subject_entity_id == 501
    assert tag.object_entity_id == 502
    relationship = result.created_relationships[0]
    assert relationship.relationship_type == "obligation"
    assert relationship.emotional_valence == "-1|wary"
    assert cur.entity_pair_tags[0]["pair_tag_id"] == 112
    extra_data = json.loads(cur.character_relationships[0]["extra_data"])
    assert extra_data["trait_compiler_functional_pair_tag"] == "obligation"


def test_obligation_faction_counterparty_writes_pair_tag_only() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(
        obligations=ObligationsTraitInput(
            targets=[
                ObligationTargetInput(counterparty_kind="faction", name="The Guild")
            ]
        )
    )

    result = apply_character_trait_compilation(
        cur,
        character=_character("obligations", "resources", "allies", inputs=inputs),
        character_id=1,
        character_entity_id=501,
    )

    tag = result.applied_pair_tags[0]
    assert tag.tag == "obligation"
    assert tag.object_entity_id == 900
    assert result.created_relationships == []
    assert cur.character_relationships == []
    assert result.created_entities == []


def test_obligation_unknown_faction_creates_stub() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(
        obligations=ObligationsTraitInput(
            targets=[
                ObligationTargetInput(counterparty_kind="faction", name="Iron Tithe")
            ]
        )
    )

    result = apply_character_trait_compilation(
        cur,
        character=_character("obligations", "resources", "allies", inputs=inputs),
        character_id=1,
        character_entity_id=501,
    )

    created = result.created_entities[0]
    assert created.entity_kind == "faction"
    assert created.name == "Iron Tithe"
    assert created.row_id == 4
    stub_row = cur.factions[4]
    assert stub_row["extra_data"]["stub_kind"] == "trait_compiler_target_ref"
    assert cur.entity_pair_tags[0]["object_entity_id"] == created.entity_id


def test_dry_run_coalesces_duplicate_pending_stubs() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(
        patron=PatronTraitInput(name="Magistrate Hale"),
        obligations=ObligationsTraitInput(
            targets=[
                ObligationTargetInput(
                    counterparty_kind="character", name="Magistrate Hale"
                )
            ]
        ),
    )

    result = compile_character_traits(
        cur,
        character=_character("patron", "obligations", "resources", inputs=inputs),
        character_id=1,
        character_entity_id=501,
        dry_run=True,
    )

    assert len(result.created_entities) == 1
    assert result.created_entities[0].name == "Magistrate Hale"
    assert result.created_entities[0].entity_id is None
    obligation_tags = [
        item for item in result.applied_pair_tags if item.tag == "obligation"
    ]
    assert obligation_tags[0].object_name == "Magistrate Hale"


def test_apply_resolves_second_reference_to_created_stub() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(
        patron=PatronTraitInput(name="Magistrate Hale"),
        obligations=ObligationsTraitInput(
            targets=[
                ObligationTargetInput(
                    counterparty_kind="character", name="Magistrate Hale"
                )
            ]
        ),
    )

    result = apply_character_trait_compilation(
        cur,
        character=_character("patron", "obligations", "resources", inputs=inputs),
        character_id=1,
        character_entity_id=501,
    )

    assert len(result.created_entities) == 1
    stub_entity_id = result.created_entities[0].entity_id
    assert stub_entity_id is not None
    obligation_tags = [
        item for item in result.applied_pair_tags if item.tag == "obligation"
    ]
    assert obligation_tags[0].object_entity_id == stub_entity_id
    assert {item.relationship_type for item in result.created_relationships} == {
        "patron",
        "obligation",
    }


def test_standard_selection_with_full_inputs_has_zero_remainders() -> None:
    cur = TraitCompilerCursor()
    inputs = TraitCompileInputs(
        domain=DomainTraitInput(name="The Roost"),
        patron=PatronTraitInput(name="Magistrate Hale", functions=["sponsors"]),
        obligations=ObligationsTraitInput(
            targets=[
                ObligationTargetInput(counterparty_kind="faction", name="The Guild")
            ]
        ),
    )

    result = apply_character_trait_compilation(
        cur,
        character=_character("domain", "patron", "obligations", inputs=inputs),
        character_id=1,
        character_entity_id=501,
    )

    assert result.counters.prose_only_remainders == 0
    assert result.counters.applied_pair_tags == 3  # claims, sponsors, obligation
    assert result.counters.created_relationships == 1
    assert result.counters.created_entities == 1


def test_persist_trait_compile_result_requires_wizard_cache_row() -> None:
    class PersistCursor:
        def __init__(self) -> None:
            self.rowcounts = [1, 0]
            self.rowcount = 0

        def execute(self, _sql, _params=None):
            self.rowcount = self.rowcounts.pop(0)

    result = TraitCompileResult(
        character_id=1,
        character_entity_id=501,
        dry_run=False,
    )

    with pytest.raises(RuntimeError, match="new_story_creator"):
        persist_trait_compile_result(
            PersistCursor(),
            character_id=1,
            result=result,
        )
