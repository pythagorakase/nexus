"""Postgres-gated integration tests for the finished trait compiler (M5).

These tests run the real compiler against a module-scoped disposable template
clone inside a transaction that is always rolled back; no owner slot is read
or written. The clone is at the migration head (so migration 061's
``sponsors`` pair-tag is registered) and carries a canonical player standing
at a zoned place, which is the need-clock anchor every character insert
needs. Domain stubs resolve their zone from the authored point.

Run with: ``NEXUS_RUN_POSTGRES=1 poetry run pytest
tests/test_trait_compiler_integration.py``
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from itertools import permutations
from typing import Any, Optional

import pytest

from nexus.agents.logon.apex_schema import Coordinates
from nexus.api.new_story_schemas import (
    CharacterSheet,
    CharacterTrait,
    TraitConstraint,
    TraitName,
)
from nexus.api.trait_compiler import (
    apply_character_trait_compilation,
    compile_character_traits,
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
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    seed_place,
    seed_protagonist,
    seed_zone,
)

DOMAIN_PLACE_NAME = "M5 Trait Test Spire"
PATRON_NAME = "M5 Trait Test Hale"
OBLIGATION_CHARACTER_NAME = "M5 Trait Test Collector"
OBLIGATION_FACTION_NAME = "M5 Trait Test Tithe"
DEPENDENT_NAME = "M5 Trait Test Pip"
DUNLOW_FACTION_NAME = "Dunlow County Circuit Court [issue 602 rollback test]"
DUNLOW_ENEMY_NAME = "Dunlow County Circuit Court Clerk"
SHARED_CHARACTER_NAME = "Magistrate Hale [issue 602 rollback test]"


@pytest.fixture(scope="module")
def trait_compiler_db() -> Iterator[str]:
    """A clone with a canonical player at a zoned place; every test rolls back.

    Seeded in need-clock anchor order: a bounded zone, a place resolved into
    it, then the located player, whose ``base_timestamp`` anchors the need
    clocks of the characters each test inserts.
    """

    with disposable_slot_database("qa885_trait_compiler") as dbname:
        seed_zone(
            dbname,
            name="Trait Compiler Zone",
            min_longitude=-74.1,
            min_latitude=40.6,
            max_longitude=-73.8,
            max_latitude=40.9,
        )
        place_id, _ = seed_place(dbname, name="Trait Compiler Plaza")
        seed_protagonist(
            dbname,
            name="Trait Compiler Player",
            current_location=place_id,
        )
        yield dbname


def _assert_real_relationship_triggers(
    cur: Any, *, character_id: int, relationship_types: list[str]
) -> None:
    """Prove the writes reached the public table and its migrated triggers.

    The valence-boundary trigger derives ``valence_current`` from the rung
    the compiler wrote, and migration 115's provenance trigger records one
    ``trait_compiler`` insert version per edge (it raises without a
    producer, so a missing attribution fails the compile itself).
    """

    cur.execute(
        """
        SELECT cr.relationship_type,
               cr.valence_current
                   = substring(cr.emotional_valence::text FROM '^([+-]?[0-9]+)\\|')
                     ::numeric / 5.5,
               (SELECT count(*) FROM relationship_versions rv
                WHERE rv.relationship_table = 'character_relationships'
                  AND rv.operation = 'insert'
                  AND rv.producer = 'trait_compiler'
                  AND (rv.old_row->>'character1_id')::int = cr.character1_id
                  AND (rv.old_row->>'character2_id')::int = cr.character2_id)
        FROM public.character_relationships cr
        WHERE cr.character1_id = %s
        ORDER BY cr.relationship_type
        """,
        (character_id,),
    )
    assert cur.fetchall() == [
        (relationship_type, True, 1) for relationship_type in relationship_types
    ]


def _character_sheet(
    *trait_names: TraitName,
    inputs: Optional[TraitCompileInputs],
    constraints: Optional[list[TraitConstraint]] = None,
) -> CharacterSheet:
    traits = [
        CharacterTrait(name=trait_name, description=f"{trait_name} trait prose")
        for trait_name in trait_names
    ]
    return CharacterSheet(
        name="M5 Trait Test Protagonist",
        summary="Integration-test protagonist for the M5 trait compiler.",
        appearance="Deliberately nondescript; exists only inside a transaction.",
        background=(
            "Created by tests/test_trait_compiler_integration.py and rolled "
            "back before commit."
        ),
        personality="Methodical, transactional, and gone before anyone commits.",
        wildcard_name="Rollback Ghost",
        wildcard_description="Vanishes whenever the transaction ends.",
        trait_1=traits[0],
        trait_2=traits[1],
        trait_3=traits[2],
        trait_compile_inputs=inputs,
        trait_constraints=constraints or [],
    )


def _insert_protagonist(cur: Any) -> tuple[int, int]:
    cur.execute(
        """
        INSERT INTO characters (name, summary, background, extra_data)
        VALUES (%s, %s, %s, '{}'::jsonb)
        RETURNING id, entity_id
        """,
        (
            "M5 Trait Test Protagonist",
            "Integration-test protagonist for the M5 trait compiler.",
            "Rolled back before commit.",
        ),
    )
    row = cur.fetchone()
    assert row is not None
    return row[0], row[1]


def _insert_dunlow_enemy(cur: Any) -> tuple[int, int]:
    cur.execute(
        """
        INSERT INTO characters (name, summary, background, extra_data)
        VALUES (%s, %s, %s, '{}'::jsonb)
        RETURNING id, entity_id
        """,
        (
            DUNLOW_ENEMY_NAME,
            "An adverse court clerk for the issue 602 permutation test.",
            "Created inside a rollback-only trait compiler test.",
        ),
    )
    row = cur.fetchone()
    assert row is not None
    return row[0], row[1]


def _active_pair_tags(cur: Any, subject_entity_id: int) -> set[tuple[str, int]]:
    cur.execute(
        """
        SELECT pt.tag, ept.object_entity_id
        FROM entity_pair_tags ept
        JOIN pair_tags pt ON pt.id = ept.pair_tag_id
        WHERE ept.subject_entity_id = %s
          AND ept.cleared_at IS NULL
        """,
        (subject_entity_id,),
    )
    return {(row[0], row[1]) for row in cur.fetchall()}


def _normalized_result_surface(
    result: TraitCompileResult,
    *,
    entity_names: dict[int, str],
    row_names: dict[int, str],
    include_execution_fields: bool,
) -> str:
    """Serialize the complete result surface with generated ids replaced by names."""

    def entity_identity(entity_id: Optional[int], name: Optional[str]) -> Optional[str]:
        if name is not None:
            return name
        if entity_id is None:
            return None
        return entity_names.get(entity_id, f"entity:{entity_id}")

    def row_identity(row_id: Optional[int], name: Optional[str]) -> Optional[str]:
        if name is not None:
            return name
        if row_id is None:
            return None
        return row_names.get(row_id, f"character:{row_id}")

    surface: dict[str, Any] = {
        "applied_single_entity_tags": [
            {
                "trait": item.trait,
                "entity": entity_identity(item.entity_id, None),
                "tag": item.tag,
                "category": item.category,
                **(
                    {"inserted": item.inserted, "dry_run": item.dry_run}
                    if include_execution_fields
                    else {}
                ),
            }
            for item in result.applied_single_entity_tags
        ],
        "applied_pair_tags": [
            {
                "trait": item.trait,
                "subject": entity_identity(item.subject_entity_id, item.subject_name),
                "object": entity_identity(item.object_entity_id, item.object_name),
                "tag": item.tag,
                **(
                    {"inserted": item.inserted, "dry_run": item.dry_run}
                    if include_execution_fields
                    else {}
                ),
            }
            for item in result.applied_pair_tags
        ],
        "created_entities": [
            {
                "trait": item.trait,
                "entity_kind": item.entity_kind,
                "name": item.name,
                **({"dry_run": item.dry_run} if include_execution_fields else {}),
            }
            for item in result.created_entities
        ],
        "created_relationships": [
            {
                "trait": item.trait,
                "character1": row_identity(item.character1_id, None),
                "character2": row_identity(item.character2_id, item.character2_name),
                "relationship_type": item.relationship_type,
                "emotional_valence": item.emotional_valence,
                "pair_tag": item.pair_tag,
                "contact_kind": item.contact_kind,
                **({"dry_run": item.dry_run} if include_execution_fields else {}),
            }
            for item in result.created_relationships
        ],
        "prose_only_remainders": [
            item.model_dump(mode="json") for item in result.prose_only_remainders
        ],
        "counters": result.counters.model_dump(mode="json"),
    }
    if include_execution_fields:
        surface["dry_run"] = result.dry_run
    return json.dumps(surface, sort_keys=True)


@pytest.mark.requires_postgres
def test_dunlow_shared_faction_is_permutation_invariant_on_seeded_clone(
    trait_compiler_db: str,
) -> None:
    """Every live-trio ordering shares one planned or materialized faction."""

    conn = connect(trait_compiler_db)

    dry_result_surfaces: list[str] = []
    apply_result_surfaces: list[str] = []
    canonical_db_snapshots = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM factions WHERE name = %s",
                (DUNLOW_FACTION_NAME,),
            )
            assert cur.fetchone() == (0,), "rollback test faction must start absent"

            selected_traits: tuple[TraitName, TraitName, TraitName] = (
                "status",
                "enemies",
                "obligations",
            )
            for trait_order in permutations(selected_traits):
                cur.execute("SAVEPOINT issue_602_permutation")
                try:
                    character_id, character_entity_id = _insert_protagonist(cur)
                    enemy_id, enemy_entity_id = _insert_dunlow_enemy(cur)
                    inputs = TraitCompileInputs(
                        status=StatusTraitInput(
                            scope_faction_name=DUNLOW_FACTION_NAME,
                            scope_faction_entity_id=None,
                            level="senior",
                        ),
                        enemies=RelationshipTraitInput(
                            targets=[
                                RelationshipTargetInput(
                                    character_id=enemy_id,
                                    character_entity_id=enemy_entity_id,
                                    name=DUNLOW_ENEMY_NAME,
                                    relationship_type=None,
                                    emotional_valence=None,
                                    dynamic="",
                                    recent_events="",
                                    history="",
                                    apply_pair_tag=True,
                                    pair_tag=None,
                                    pair_tag_direction="protagonist_to_target",
                                    contact_kind=None,
                                )
                            ]
                        ),
                        obligations=ObligationsTraitInput(
                            targets=[
                                ObligationTargetInput(
                                    counterparty_kind="faction",
                                    counterparty_id=None,
                                    counterparty_entity_id=None,
                                    name=DUNLOW_FACTION_NAME,
                                    emotional_valence=None,
                                    dynamic="",
                                    recent_events="",
                                    history="",
                                )
                            ]
                        ),
                    )
                    sheet = _character_sheet(*trait_order, inputs=inputs)

                    dry_result = compile_character_traits(
                        cur,
                        character=sheet,
                        character_id=character_id,
                        character_entity_id=character_entity_id,
                        dry_run=True,
                    )
                    assert dry_result.prose_only_remainders == []
                    assert [
                        (item.trait, item.entity_kind, item.name)
                        for item in dry_result.created_entities
                    ] == [("obligations", "faction", DUNLOW_FACTION_NAME)]
                    dry_pair_targets = {
                        (
                            item.trait,
                            item.tag,
                            item.object_name
                            or (
                                DUNLOW_ENEMY_NAME
                                if item.object_entity_id == enemy_entity_id
                                else None
                            ),
                        )
                        for item in dry_result.applied_pair_tags
                    }
                    assert dry_pair_targets == {
                        ("status", "status:senior", DUNLOW_FACTION_NAME),
                        ("enemies", "hostile_to", DUNLOW_ENEMY_NAME),
                        ("obligations", "obligation", DUNLOW_FACTION_NAME),
                    }
                    cur.execute(
                        "SELECT COUNT(*) FROM factions WHERE name = %s",
                        (DUNLOW_FACTION_NAME,),
                    )
                    assert cur.fetchone() == (0,)
                    entity_names = {
                        character_entity_id: "protagonist",
                        enemy_entity_id: DUNLOW_ENEMY_NAME,
                    }
                    row_names = {
                        character_id: "protagonist",
                        enemy_id: DUNLOW_ENEMY_NAME,
                    }
                    dry_result_surfaces.append(
                        _normalized_result_surface(
                            dry_result,
                            entity_names=entity_names,
                            row_names=row_names,
                            include_execution_fields=True,
                        )
                    )
                    dry_semantic_surface = _normalized_result_surface(
                        dry_result,
                        entity_names=entity_names,
                        row_names=row_names,
                        include_execution_fields=False,
                    )

                    apply_result = apply_character_trait_compilation(
                        cur,
                        character=sheet,
                        character_id=character_id,
                        character_entity_id=character_entity_id,
                    )
                    assert apply_result.prose_only_remainders == []
                    assert len(apply_result.created_entities) == 1
                    created_faction = apply_result.created_entities[0]
                    assert created_faction.name == DUNLOW_FACTION_NAME
                    assert created_faction.entity_id is not None
                    faction_entity_id = created_faction.entity_id
                    entity_names[faction_entity_id] = DUNLOW_FACTION_NAME
                    apply_result_surfaces.append(
                        _normalized_result_surface(
                            apply_result,
                            entity_names=entity_names,
                            row_names=row_names,
                            include_execution_fields=True,
                        )
                    )
                    assert (
                        _normalized_result_surface(
                            apply_result,
                            entity_names=entity_names,
                            row_names=row_names,
                            include_execution_fields=False,
                        )
                        == dry_semantic_surface
                    )

                    apply_pair_targets = {
                        (
                            item.trait,
                            item.tag,
                            (
                                DUNLOW_FACTION_NAME
                                if item.object_entity_id == faction_entity_id
                                else (
                                    DUNLOW_ENEMY_NAME
                                    if item.object_entity_id == enemy_entity_id
                                    else None
                                )
                            ),
                        )
                        for item in apply_result.applied_pair_tags
                    }
                    assert apply_pair_targets == dry_pair_targets

                    cur.execute(
                        "SELECT id, entity_id FROM factions WHERE name = %s",
                        (DUNLOW_FACTION_NAME,),
                    )
                    assert cur.fetchall() == [
                        (created_faction.row_id, faction_entity_id)
                    ]
                    active_tags = _active_pair_tags(cur, character_entity_id)
                    canonical_db_tags = {
                        (
                            tag,
                            (
                                DUNLOW_FACTION_NAME
                                if object_id == faction_entity_id
                                else (
                                    DUNLOW_ENEMY_NAME
                                    if object_id == enemy_entity_id
                                    else str(object_id)
                                )
                            ),
                        )
                        for tag, object_id in active_tags
                    }
                    cur.execute(
                        """
                        SELECT cr.relationship_type, c2.name,
                               cr.extra_data->>'source'
                        FROM character_relationships cr
                        JOIN characters c2 ON c2.id = cr.character2_id
                        WHERE cr.character1_id = %s
                        ORDER BY cr.relationship_type, c2.name
                        """,
                        (character_id,),
                    )
                    canonical_relationships = tuple(cur.fetchall())
                    canonical_db_snapshots.append(
                        (
                            frozenset(canonical_db_tags),
                            canonical_relationships,
                            tuple(
                                item.model_dump(mode="json")
                                for item in apply_result.prose_only_remainders
                            ),
                        )
                    )
                finally:
                    cur.execute("ROLLBACK TO SAVEPOINT issue_602_permutation")
                    cur.execute("RELEASE SAVEPOINT issue_602_permutation")

            assert len(dry_result_surfaces) == 6
            assert len(apply_result_surfaces) == 6
            assert all(
                surface == dry_result_surfaces[0] for surface in dry_result_surfaces[1:]
            )
            assert all(
                surface == apply_result_surfaces[0]
                for surface in apply_result_surfaces[1:]
            )
            assert len(canonical_db_snapshots) == 6
            assert all(
                snapshot == canonical_db_snapshots[0]
                for snapshot in canonical_db_snapshots[1:]
            )
            assert canonical_db_snapshots[0][0] == frozenset(
                {
                    ("status:senior", DUNLOW_FACTION_NAME),
                    ("hostile_to", DUNLOW_ENEMY_NAME),
                    ("obligation", DUNLOW_FACTION_NAME),
                }
            )
            assert canonical_db_snapshots[0][1] == (
                ("enemy", DUNLOW_ENEMY_NAME, "trait_compiler"),
            )
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.requires_postgres
def test_shared_character_relationship_is_permutation_invariant_on_seeded_clone(
    trait_compiler_db: str,
) -> None:
    """Patron deterministically owns a shared one-row relationship slot."""

    conn = connect(trait_compiler_db)

    dry_result_surfaces: list[str] = []
    apply_result_surfaces: list[str] = []
    canonical_db_snapshots = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM characters WHERE name = %s",
                (SHARED_CHARACTER_NAME,),
            )
            assert cur.fetchone() == (0,), "rollback test character must start absent"

            selected_traits: tuple[TraitName, TraitName, TraitName] = (
                "patron",
                "obligations",
                "resources",
            )
            for trait_order in permutations(selected_traits):
                cur.execute("SAVEPOINT issue_602_relationship_permutation")
                try:
                    character_id, character_entity_id = _insert_protagonist(cur)
                    inputs = TraitCompileInputs(
                        patron=PatronTraitInput(
                            character_id=None,
                            character_entity_id=None,
                            name=SHARED_CHARACTER_NAME,
                            functions=[],
                            emotional_valence=None,
                            dynamic="A formal sponsor with exacting expectations.",
                            recent_events="",
                            history="",
                        ),
                        obligations=ObligationsTraitInput(
                            targets=[
                                ObligationTargetInput(
                                    counterparty_kind="character",
                                    counterparty_id=None,
                                    counterparty_entity_id=None,
                                    name=SHARED_CHARACTER_NAME,
                                    emotional_valence=None,
                                    dynamic="A debt owed to the same sponsor.",
                                    recent_events="",
                                    history="",
                                )
                            ]
                        ),
                        resources=SingleEntityTraitInput(level="wealthy"),
                    )
                    sheet = _character_sheet(*trait_order, inputs=inputs)
                    entity_names = {character_entity_id: "protagonist"}
                    row_names = {character_id: "protagonist"}

                    dry_result = compile_character_traits(
                        cur,
                        character=sheet,
                        character_id=character_id,
                        character_entity_id=character_entity_id,
                        dry_run=True,
                    )
                    assert [
                        (item.trait, item.entity_kind, item.name)
                        for item in dry_result.created_entities
                    ] == [("patron", "character", SHARED_CHARACTER_NAME)]
                    assert [
                        (item.trait, item.relationship_type)
                        for item in dry_result.created_relationships
                    ] == [("patron", "patron")]
                    assert len(dry_result.prose_only_remainders) == 1
                    dry_remainder = dry_result.prose_only_remainders[0]
                    assert (
                        dry_remainder.reason_code
                        == TraitCompileReasonCode.RELATIONSHIP_PAIR_CONFLICT
                    )
                    assert dry_remainder.trait == "obligations"
                    assert dry_remainder.details == {
                        "constraint": "character_relationships_pkey",
                        "target_name": SHARED_CHARACTER_NAME,
                        "winner_trait": "patron",
                        "winner_relationship_type": "patron",
                        "displaced_relationship_type": "obligation",
                    }
                    cur.execute(
                        "SELECT COUNT(*) FROM characters WHERE name = %s",
                        (SHARED_CHARACTER_NAME,),
                    )
                    assert cur.fetchone() == (0,)
                    dry_result_surfaces.append(
                        _normalized_result_surface(
                            dry_result,
                            entity_names=entity_names,
                            row_names=row_names,
                            include_execution_fields=True,
                        )
                    )
                    dry_semantic_surface = _normalized_result_surface(
                        dry_result,
                        entity_names=entity_names,
                        row_names=row_names,
                        include_execution_fields=False,
                    )

                    apply_result = apply_character_trait_compilation(
                        cur,
                        character=sheet,
                        character_id=character_id,
                        character_entity_id=character_entity_id,
                    )
                    assert len(apply_result.created_entities) == 1
                    created_character = apply_result.created_entities[0]
                    assert created_character.trait == "patron"
                    assert created_character.name == SHARED_CHARACTER_NAME
                    assert created_character.row_id is not None
                    assert created_character.entity_id is not None
                    row_names[created_character.row_id] = SHARED_CHARACTER_NAME
                    entity_names[created_character.entity_id] = SHARED_CHARACTER_NAME
                    assert [
                        (item.trait, item.relationship_type)
                        for item in apply_result.created_relationships
                    ] == [("patron", "patron")]
                    assert [
                        item.model_dump(mode="json")
                        for item in apply_result.prose_only_remainders
                    ] == [
                        item.model_dump(mode="json")
                        for item in dry_result.prose_only_remainders
                    ]
                    apply_result_surfaces.append(
                        _normalized_result_surface(
                            apply_result,
                            entity_names=entity_names,
                            row_names=row_names,
                            include_execution_fields=True,
                        )
                    )
                    assert (
                        _normalized_result_surface(
                            apply_result,
                            entity_names=entity_names,
                            row_names=row_names,
                            include_execution_fields=False,
                        )
                        == dry_semantic_surface
                    )

                    cur.execute(
                        """
                        SELECT cr.relationship_type,
                               cr.extra_data->>'trait',
                               c2.name
                        FROM character_relationships cr
                        JOIN characters c2 ON c2.id = cr.character2_id
                        WHERE cr.character1_id = %s
                          AND cr.character2_id = %s
                        """,
                        (character_id, created_character.row_id),
                    )
                    relationship_rows = tuple(cur.fetchall())
                    assert relationship_rows == (
                        ("patron", "patron", SHARED_CHARACTER_NAME),
                    )
                    canonical_db_snapshots.append(relationship_rows)
                finally:
                    cur.execute(
                        "ROLLBACK TO SAVEPOINT issue_602_relationship_permutation"
                    )
                    cur.execute("RELEASE SAVEPOINT issue_602_relationship_permutation")

            assert len(dry_result_surfaces) == 6
            assert all(
                surface == dry_result_surfaces[0] for surface in dry_result_surfaces[1:]
            )
            assert len(apply_result_surfaces) == 6
            assert all(
                surface == apply_result_surfaces[0]
                for surface in apply_result_surfaces[1:]
            )
            assert len(canonical_db_snapshots) == 6
            assert all(
                snapshot == canonical_db_snapshots[0]
                for snapshot in canonical_db_snapshots[1:]
            )
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.requires_postgres
def test_full_trait_selection_compiles_on_seeded_clone(trait_compiler_db: str) -> None:
    """A standard selection compiles with zero prose-only remainders."""

    conn = connect(trait_compiler_db)

    try:
        with conn.cursor() as cur:
            drift_before = reconcile_trait_relationship_pair_tags(cur)
            character_id, character_entity_id = _insert_protagonist(cur)

            inputs = TraitCompileInputs(
                domain=DomainTraitInput(
                    place_id=None,
                    place_entity_id=None,
                    name=DOMAIN_PLACE_NAME,
                    coordinates=Coordinates(lat=40.8, lon=-74.0),
                ),
                patron=PatronTraitInput(
                    character_id=None,
                    character_entity_id=None,
                    name=PATRON_NAME,
                    functions=["sponsors", "mentors"],
                    emotional_valence=None,
                    dynamic="Backs the protagonist's ventures discreetly.",
                    recent_events="",
                    history="",
                ),
                obligations=ObligationsTraitInput(
                    targets=[
                        ObligationTargetInput(
                            counterparty_kind="character",
                            counterparty_id=None,
                            counterparty_entity_id=None,
                            name=OBLIGATION_CHARACTER_NAME,
                            emotional_valence=None,
                            dynamic="A patient ledger, collected in favors.",
                            recent_events="",
                            history="",
                        ),
                        ObligationTargetInput(
                            counterparty_kind="faction",
                            counterparty_id=None,
                            counterparty_entity_id=None,
                            name=OBLIGATION_FACTION_NAME,
                            emotional_valence=None,
                            dynamic="",
                            recent_events="",
                            history="",
                        ),
                    ]
                ),
            )
            sheet = _character_sheet("domain", "patron", "obligations", inputs=inputs)

            result = apply_character_trait_compilation(
                cur,
                character=sheet,
                character_id=character_id,
                character_entity_id=character_entity_id,
            )

            assert (
                result.counters.prose_only_remainders == 0
            ), result.prose_only_remainders
            # claims + sponsors + mentors + obligation x2.
            assert result.counters.applied_pair_tags == 5
            # place + patron char + obligation char + obligation faction.
            assert result.counters.created_entities == 4
            # patron + obligation character counterparty.
            assert result.counters.created_relationships == 2

            created_by_kind = {
                item.entity_kind: item for item in result.created_entities
            }
            assert set(created_by_kind) == {"character", "place", "faction"}

            place_entity_id = next(
                item.entity_id
                for item in result.created_entities
                if item.entity_kind == "place"
            )
            assert place_entity_id is not None

            protagonist_tags = _active_pair_tags(cur, character_entity_id)
            assert ("claims", place_entity_id) in protagonist_tags
            obligation_objects = {
                object_id for tag, object_id in protagonist_tags if tag == "obligation"
            }
            assert len(obligation_objects) == 2

            patron_entity_id = next(
                item.entity_id
                for item in result.created_entities
                if item.name == PATRON_NAME
            )
            assert patron_entity_id is not None
            patron_tags = _active_pair_tags(cur, patron_entity_id)
            assert ("sponsors", character_entity_id) in patron_tags
            assert ("mentors", character_entity_id) in patron_tags

            cur.execute(
                """
                SELECT relationship_type, emotional_valence,
                       extra_data->>'source'
                FROM character_relationships
                WHERE character1_id = %s
                ORDER BY relationship_type
                """,
                (character_id,),
            )
            relationships = cur.fetchall()
            assert [(row[0], row[2]) for row in relationships] == [
                ("obligation", "trait_compiler"),
                ("patron", "trait_compiler"),
            ]
            _assert_real_relationship_triggers(
                cur,
                character_id=character_id,
                relationship_types=["obligation", "patron"],
            )

            cur.execute(
                """
                SELECT extra_data->>'source', extra_data->>'stub_kind'
                FROM characters
                WHERE name = %s
                """,
                (PATRON_NAME,),
            )
            assert cur.fetchone() == ("trait_compiler", "trait_compiler_target_ref")
            cur.execute(
                """
                SELECT p.type::text, p.extra_data->>'stub_kind',
                       ST_X(p.coordinates::geometry),
                       ST_Y(p.coordinates::geometry),
                       ST_Z(p.coordinates::geometry),
                       ST_M(p.coordinates::geometry),
                       ST_SRID(p.coordinates::geometry), z.name
                FROM places p JOIN zones z ON z.id = p.zone
                WHERE p.name = %s
                """,
                (DOMAIN_PLACE_NAME,),
            )
            assert cur.fetchone() == (
                "other",
                "trait_compiler_target_ref",
                -74.0,
                40.8,
                0,
                0,
                4326,
                "Trait Compiler Zone",
            )
            cur.execute(
                "SELECT extra_data->>'stub_kind' FROM factions WHERE name = %s",
                (OBLIGATION_FACTION_NAME,),
            )
            assert cur.fetchone() == ("trait_compiler_target_ref",)

            # Functional trait edges must not add affective-layer drift.
            assert reconcile_trait_relationship_pair_tags(cur) == drift_before
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.requires_postgres
@pytest.mark.parametrize("dry_run", [True, False])
def test_domain_stub_without_point_is_refused_on_seeded_clone(
    trait_compiler_db: str, dry_run: bool
) -> None:
    """Both the audit and apply path refuse an unlocated new Domain target."""

    conn = connect(trait_compiler_db)
    try:
        with conn.cursor() as cur:
            character_id, character_entity_id = _insert_protagonist(cur)
            sheet = _character_sheet(
                "domain",
                "resources",
                "fame",
                inputs=TraitCompileInputs(
                    domain=DomainTraitInput(name=DOMAIN_PLACE_NAME),
                    resources=SingleEntityTraitInput(level="wealthy"),
                    fame=SingleEntityTraitInput(level="known"),
                ),
            )
            with pytest.raises(
                ValueError,
                match=f"domain place '{DOMAIN_PLACE_NAME}'.*carries no point",
            ):
                if dry_run:
                    compile_character_traits(
                        cur,
                        character=sheet,
                        character_id=character_id,
                        character_entity_id=character_entity_id,
                        dry_run=True,
                    )
                else:
                    apply_character_trait_compilation(
                        cur,
                        character=sheet,
                        character_id=character_id,
                        character_entity_id=character_entity_id,
                    )
            cur.execute(
                "SELECT count(*) FROM places WHERE name = %s", (DOMAIN_PLACE_NAME,)
            )
            assert cur.fetchone()[0] == 0
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.requires_postgres
def test_dependents_apply_and_dry_run_audit_on_seeded_clone(
    trait_compiler_db: str,
) -> None:
    """Dependents writes protects + bond; the audit surface reports cleanly."""

    conn = connect(trait_compiler_db)

    try:
        with conn.cursor() as cur:
            character_id, character_entity_id = _insert_protagonist(cur)

            inputs = TraitCompileInputs(
                dependents=DependentsTraitInput(
                    targets=[
                        DependentTargetInput(
                            character_id=None,
                            character_entity_id=None,
                            name=DEPENDENT_NAME,
                            emotional_valence=None,
                            dynamic="",
                            recent_events="",
                            history="",
                        )
                    ]
                ),
                resources=SingleEntityTraitInput(level="wealthy"),
                fame=SingleEntityTraitInput(level="known"),
            )
            sheet = _character_sheet("dependents", "resources", "fame", inputs=inputs)

            # Dry-run first: the trait-audit surface must report zero
            # remainders and a pending stub without touching the database.
            audit = compile_character_traits(
                cur,
                character=sheet,
                character_id=character_id,
                character_entity_id=character_entity_id,
                dry_run=True,
            )
            assert (
                audit.counters.prose_only_remainders == 0
            ), audit.prose_only_remainders
            assert audit.created_entities[0].entity_id is None
            assert audit.created_entities[0].name == DEPENDENT_NAME
            assert audit.applied_pair_tags[0].object_entity_id is None
            assert audit.applied_pair_tags[0].object_name == DEPENDENT_NAME
            cur.execute(
                "SELECT COUNT(*) FROM characters WHERE name = %s",
                (DEPENDENT_NAME,),
            )
            assert cur.fetchone() == (0,)

            result = apply_character_trait_compilation(
                cur,
                character=sheet,
                character_id=character_id,
                character_entity_id=character_entity_id,
            )
            assert result.counters.prose_only_remainders == 0
            assert result.counters.applied_single_entity_tags == 2
            dependent_entity_id = result.created_entities[0].entity_id
            assert dependent_entity_id is not None

            protagonist_tags = _active_pair_tags(cur, character_entity_id)
            assert ("protects", dependent_entity_id) in protagonist_tags

            cur.execute(
                """
                SELECT relationship_type, emotional_valence,
                       extra_data->>'trait_compiler_functional_pair_tag'
                FROM character_relationships
                WHERE character1_id = %s
                """,
                (character_id,),
            )
            assert cur.fetchall() == [("dependent", "+3|trusting", "protects")]
            _assert_real_relationship_triggers(
                cur, character_id=character_id, relationship_types=["dependent"]
            )
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.requires_postgres
def test_forbidden_relationship_traits_have_dry_run_apply_parity_on_seeded_clone(
    trait_compiler_db: str,
) -> None:
    """The constraint gate precedes #605 target pre-resolution in both modes."""

    conn = connect(trait_compiler_db)

    try:
        with conn.cursor() as cur:
            character_id, character_entity_id = _insert_protagonist(cur)
            inputs = TraitCompileInputs.model_validate(
                {
                    "patron": {
                        "name": PATRON_NAME,
                        "functions": ["mentors", "protects"],
                    },
                    "dependents": {"targets": [{"name": DEPENDENT_NAME}]},
                    "obligations": {
                        "targets": [
                            {
                                "counterparty_kind": "character",
                                "name": OBLIGATION_CHARACTER_NAME,
                            }
                        ]
                    },
                }
            )
            constraints = [
                TraitConstraint.model_validate(
                    {"trait": trait, "cold_start_relationships": "forbidden"}
                )
                for trait in ("patron", "dependents", "obligations")
            ]
            sheet = _character_sheet(
                "patron",
                "dependents",
                "obligations",
                inputs=inputs,
                constraints=constraints,
            )

            dry_result = compile_character_traits(
                cur,
                character=sheet,
                character_id=character_id,
                character_entity_id=character_entity_id,
                dry_run=True,
            )
            apply_result = apply_character_trait_compilation(
                cur,
                character=sheet,
                character_id=character_id,
                character_entity_id=character_entity_id,
            )

            for result in (dry_result, apply_result):
                assert result.created_entities == []
                assert result.created_relationships == []
                assert result.applied_pair_tags == []
                assert {item.reason_code for item in result.prose_only_remainders} == {
                    TraitCompileReasonCode.COLD_START_RELATIONSHIPS_FORBIDDEN
                }
            cur.execute(
                "SELECT count(*) FROM characters WHERE name = ANY(%s)",
                ([PATRON_NAME, DEPENDENT_NAME, OBLIGATION_CHARACTER_NAME],),
            )
            assert cur.fetchone() == (0,)
            cur.execute(
                "SELECT count(*) FROM character_relationships "
                "WHERE character1_id = %s",
                (character_id,),
            )
            assert cur.fetchone() == (0,)
    finally:
        conn.rollback()
        conn.close()
