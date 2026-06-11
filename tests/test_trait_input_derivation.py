"""Offline tests for transition-time trait input derivation (pure functions).

The live structured-output call is exercised by the golden-path release gate
(``tests/test_golden_path_live.py``); these tests cover the deterministic
validator and prompt renderer only.
"""

from __future__ import annotations

from typing import List

import pytest

from nexus.api.new_story_schemas import CharacterSheet, CharacterTrait, SettingCard
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
)
from nexus.api.trait_input_derivation import (
    derived_input_issues,
    render_trait_input_prompt,
    selected_canonical_traits,
)


def _character(trait_names: List[str]) -> CharacterSheet:
    traits = [
        CharacterTrait(name=name, description=f"{name} description for testing")
        for name in trait_names
    ]
    return CharacterSheet(
        name="Test Protagonist",
        summary="A test character summary long enough to validate.",
        appearance="A test appearance description long enough to validate.",
        background=(
            "A test background long enough to satisfy the minimum length "
            "constraint on the character sheet."
        ),
        personality="Cautious, wry, loyal to a fault.",
        wildcard_name="Echo Fragment",
        wildcard_description="A memory that is not theirs.",
        trait_1=traits[0],
        trait_2=traits[1],
        trait_3=traits[2],
    )


def _setting() -> SettingCard:
    return SettingCard(
        genre="cyberpunk",
        world_name="Test World",
        time_period="2120s",
        tech_level="near_future",
        political_structure="Corporate city-states",
        major_conflict="Syndicates against the grid communes",
        themes=["memory", "debt"],
        description=(
            "A coastal megacity where corporate enclaves float above flooded "
            "districts and everyone owes someone something."
        ),
        cultural_notes="Debt is social currency; names are collateral.",
        diegetic_artifact=(
            "A laminated transit token stamped with a debt-ledger glyph, "
            "carried as proof of standing."
        ),
    )


def test_selected_canonical_traits_maps_reputation_to_fame() -> None:
    character = _character(["patron", "reputation", "dependents"])
    assert selected_canonical_traits(character) == ["patron", "fame", "dependents"]


def test_valid_inputs_produce_no_issues() -> None:
    inputs = TraitCompileInputs(
        patron=PatronTraitInput(
            name="Doctor Imari Voss", functions=["mentors", "protects"]
        ),
        dependents=DependentsTraitInput(
            targets=[DependentTargetInput(name="Juno Reyes")]
        ),
        resources=SingleEntityTraitInput(level="comfortable"),
    )
    issues = derived_input_issues(
        inputs, selected=["patron", "dependents", "resources"]
    )
    assert issues == []


def test_missing_and_extra_traits_are_flagged() -> None:
    inputs = TraitCompileInputs(
        domain=DomainTraitInput(name="The Stacks"),
    )
    issues = derived_input_issues(inputs, selected=["patron", "dependents"])
    assert "input provided for non-selected trait 'domain'" in issues
    assert "missing input for selected trait 'patron'" in issues
    assert "missing input for selected trait 'dependents'" in issues


def test_database_ids_are_rejected_everywhere() -> None:
    inputs = TraitCompileInputs(
        patron=PatronTraitInput(name="Voss", character_id=3),
        dependents=DependentsTraitInput(
            targets=[DependentTargetInput(name="Juno", character_entity_id=9)]
        ),
        obligations=ObligationsTraitInput(
            targets=[
                ObligationTargetInput(
                    counterparty_kind="faction", name="The Combine", counterparty_id=2
                )
            ]
        ),
    )
    issues = derived_input_issues(
        inputs, selected=["patron", "dependents", "obligations"]
    )
    assert "patron character ids must be null" in issues
    assert "dependents.targets[0] ids must be null" in issues
    assert "obligations.targets[0] ids must be null" in issues


def test_closed_vocabulary_violations_are_flagged() -> None:
    inputs = TraitCompileInputs(
        resources=SingleEntityTraitInput(level="rich"),
        fame=SingleEntityTraitInput(level="famous"),
        status=StatusTraitInput(level="boss", scope_faction_name="The Combine"),
    )
    issues = derived_input_issues(inputs, selected=["resources", "fame", "status"])
    assert any(i.startswith("resources.level 'rich'") for i in issues)
    assert any(i.startswith("fame.level 'famous'") for i in issues)
    assert any(i.startswith("status.level 'boss'") for i in issues)


def test_reputation_alias_is_rejected() -> None:
    inputs = TraitCompileInputs(
        reputation=SingleEntityTraitInput(level="known"),
        patron=PatronTraitInput(name="Voss"),
        dependents=DependentsTraitInput(targets=[DependentTargetInput(name="Juno")]),
    )
    issues = derived_input_issues(inputs, selected=["fame", "patron", "dependents"])
    assert "use the canonical 'fame' field, not 'reputation'" in issues


def test_relationship_pair_tags_are_rejected_in_fresh_world() -> None:
    inputs = TraitCompileInputs(
        enemies=RelationshipTraitInput(
            targets=[
                RelationshipTargetInput(
                    name="Sgt. Hale", apply_pair_tag=True, pair_tag="hostile_to"
                )
            ]
        ),
        patron=PatronTraitInput(name="Voss"),
        dependents=DependentsTraitInput(targets=[DependentTargetInput(name="Juno")]),
    )
    issues = derived_input_issues(inputs, selected=["enemies", "patron", "dependents"])
    assert "enemies.targets[0].apply_pair_tag must be false in a fresh world" in issues


def test_empty_target_lists_are_flagged() -> None:
    inputs = TraitCompileInputs(
        dependents=DependentsTraitInput(targets=[]),
        obligations=ObligationsTraitInput(targets=[]),
        allies=RelationshipTraitInput(targets=[]),
    )
    issues = derived_input_issues(
        inputs, selected=["dependents", "obligations", "allies"]
    )
    assert "dependents requires at least one target" in issues
    assert "obligations requires at least one target" in issues
    assert "allies requires at least one target" in issues


def test_prompt_renders_selected_traits_and_vocabulary() -> None:
    character = _character(["patron", "dependents", "resources"])
    prompt = render_trait_input_prompt(character=character, setting=_setting())
    assert "TRAIT_INPUT_DERIVATION_REQUEST" in prompt
    assert '"patron"' in prompt
    assert '"dependents"' in prompt
    assert '"magnate"' in prompt  # resource vocabulary present
    assert '"sovereign"' in prompt  # status vocabulary present
    assert "Hard Rules" in prompt


def test_prompt_requires_existing_prompt_file() -> None:
    # The deriver must fail loudly if the prompt file is missing.
    from nexus.api import trait_input_derivation

    assert trait_input_derivation.PROMPT_PATH.exists()


@pytest.mark.parametrize("missing_field", ["patron", "domain"])
def test_named_target_required(missing_field: str) -> None:
    if missing_field == "patron":
        inputs = TraitCompileInputs(patron=PatronTraitInput(functions=["mentors"]))
        issues = derived_input_issues(inputs, selected=["patron"])
        assert "patron.name is required" in issues
    else:
        inputs = TraitCompileInputs(domain=DomainTraitInput())
        issues = derived_input_issues(inputs, selected=["domain"])
        assert "domain.name is required" in issues
