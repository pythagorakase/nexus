"""Tests for deterministic trait-to-Orrery compilation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

import pytest

from nexus.api.new_story_schemas import CharacterSheet, CharacterTrait
from nexus.api.trait_compiler import (
    apply_character_trait_compilation,
    compile_character_traits,
    reconcile_trait_relationship_pair_tags,
)
from nexus.api.trait_compiler_schemas import (
    RelationshipTargetInput,
    RelationshipTraitInput,
    SingleEntityTraitInput,
    StatusTraitInput,
    TraitCompileInputs,
    TraitCompileReasonCode,
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
            "hostile_to": {
                "id": 103,
                "subject_kinds": ["character", "faction"],
                "object_kinds": ["character", "faction"],
            },
        }
        self.characters = {
            1: {"entity_id": 501},
            2: {"entity_id": 502},
        }
        self.factions = {"The Guild": 900}
        self.entity_tags: list[dict[str, Any]] = []
        self.entity_pair_tags: list[dict[str, Any]] = []
        self.character_relationships: list[dict[str, Any]] = []
        self.fail_relationship = fail_relationship
        self.rowcount = 0
        self._next_row: Optional[Any] = None
        self._next_rows: list[Any] = []
        self._savepoints: list[tuple[list[dict[str, Any]], list[dict[str, Any]]]] = []

    def execute(self, sql: str, params: Optional[tuple] = None) -> None:
        params = params or ()
        normalized = " ".join(sql.strip().upper().split())

        if normalized.startswith("SAVEPOINT"):
            self._savepoints.append(
                (
                    deepcopy(self.entity_pair_tags),
                    deepcopy(self.character_relationships),
                )
            )
            self.rowcount = 0
            return
        if normalized.startswith("ROLLBACK TO SAVEPOINT"):
            self.entity_pair_tags, self.character_relationships = deepcopy(
                self._savepoints[-1]
            )
            self.rowcount = 0
            return
        if normalized.startswith("RELEASE SAVEPOINT"):
            self._savepoints.pop()
            self.rowcount = 0
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
                (row["id"], row["category"], False) if row is not None else None
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
            entity_id = self.factions.get(name)
            self._next_row = (entity_id,) if entity_id is not None else None
            self.rowcount = 1 if entity_id is not None else 0
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
            entity_id, tag_id, _world_time, source_kind = params
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
            subject_id, object_id, pair_tag_id, _world_time, source_kind = params
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
            self._next_rows = []
            self.rowcount = 0
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
    assert {
        item.reason_code for item in result.prose_only_remainders
    } == {TraitCompileReasonCode.MISSING_STRUCTURED_TRAIT_INPUT}


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
