"""Postgres-gated integration tests for the finished trait compiler (M5).

These tests run the real compiler against ``save_05`` inside a transaction
that is always rolled back, so the dev slot is left untouched. They require
migration 061 (the ``sponsors`` pair-tag) to be applied.

Run with: ``NEXUS_RUN_POSTGRES=1 poetry run pytest
tests/test_trait_compiler_integration.py``
"""

from __future__ import annotations

from typing import Any, Optional

import psycopg2
import pytest

from nexus.api.new_story_schemas import CharacterSheet, CharacterTrait
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
    SingleEntityTraitInput,
    TraitCompileInputs,
)

TEST_DBNAME = "save_05"

DOMAIN_PLACE_NAME = "M5 Trait Test Spire"
PATRON_NAME = "M5 Trait Test Hale"
OBLIGATION_CHARACTER_NAME = "M5 Trait Test Collector"
OBLIGATION_FACTION_NAME = "M5 Trait Test Tithe"
DEPENDENT_NAME = "M5 Trait Test Pip"


def _character_sheet(
    *trait_names: str, inputs: Optional[TraitCompileInputs]
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


@pytest.mark.requires_postgres
def test_full_trait_selection_compiles_on_save_05() -> None:
    """A standard selection compiles with zero prose-only remainders."""

    try:
        conn = psycopg2.connect(dbname=TEST_DBNAME)
    except psycopg2.Error as exc:  # pragma: no cover - environment guard
        pytest.skip(f"{TEST_DBNAME} PostgreSQL test database unavailable: {exc}")

    try:
        with conn.cursor() as cur:
            drift_before = reconcile_trait_relationship_pair_tags(cur)
            character_id, character_entity_id = _insert_protagonist(cur)

            inputs = TraitCompileInputs(
                domain=DomainTraitInput(name=DOMAIN_PLACE_NAME),
                patron=PatronTraitInput(
                    name=PATRON_NAME,
                    functions=["sponsors", "mentors"],
                    dynamic="Backs the protagonist's ventures discreetly.",
                ),
                obligations=ObligationsTraitInput(
                    targets=[
                        ObligationTargetInput(
                            counterparty_kind="character",
                            name=OBLIGATION_CHARACTER_NAME,
                            dynamic="A patient ledger, collected in favors.",
                        ),
                        ObligationTargetInput(
                            counterparty_kind="faction",
                            name=OBLIGATION_FACTION_NAME,
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
                "SELECT type::text, extra_data->>'stub_kind' FROM places "
                "WHERE name = %s",
                (DOMAIN_PLACE_NAME,),
            )
            assert cur.fetchone() == ("other", "trait_compiler_target_ref")
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
def test_dependents_apply_and_dry_run_audit_on_save_05() -> None:
    """Dependents writes protects + bond; the audit surface reports cleanly."""

    try:
        conn = psycopg2.connect(dbname=TEST_DBNAME)
    except psycopg2.Error as exc:  # pragma: no cover - environment guard
        pytest.skip(f"{TEST_DBNAME} PostgreSQL test database unavailable: {exc}")

    try:
        with conn.cursor() as cur:
            character_id, character_entity_id = _insert_protagonist(cur)

            inputs = TraitCompileInputs(
                dependents=DependentsTraitInput(
                    targets=[DependentTargetInput(name=DEPENDENT_NAME)]
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
    finally:
        conn.rollback()
        conn.close()
