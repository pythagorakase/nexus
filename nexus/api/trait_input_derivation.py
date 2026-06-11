"""Transition-time derivation of typed trait-compiler inputs.

The wizard's conversational character phase records trait selections and
prose rationales, but it never gathers the typed ``TraitCompileInputs`` the
M5 trait compilers consume. Without them every selected trait falls to a
prose-only remainder and Patron/Dependents/Obligations/Domain never create
their stub entities -- breaking the "compiled relationships get cold-start
history" promise.

This module closes the gap at the wizard -> narrative transition: one
structured-output Skald call reads the finished character sheet plus the
setting card and emits ``TraitCompileInputs`` for exactly the selected
traits. The derived inputs are validated (no database ids, closed
vocabularies, named targets) before the trait compiler runs.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional

from nexus.agents.orrery.status_family import STATUS_LEVELS
from nexus.api.trait_compiler import FAME_TAGS, RESOURCE_TAGS
from nexus.api.trait_compiler_schemas import (
    TraitCompileInputs,
    canonical_trait_name,
)

if TYPE_CHECKING:
    from nexus.api.new_story_schemas import CharacterSheet, SettingCard

logger = logging.getLogger("nexus.api.trait_input_derivation")

PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "trait_input_deriver.md"

# Patron functions mirror trait_compiler_schemas.PatronFunction.
PATRON_FUNCTIONS = ("mentors", "sponsors", "protects", "authority_over")

# Trait fields on TraitCompileInputs that target other entities by name.
_RELATIONSHIP_TRAITS = ("allies", "contacts", "enemies")


def selected_canonical_traits(character: "CharacterSheet") -> List[str]:
    """Return the canonical names of the character's three selected traits."""

    return [
        canonical_trait_name(str(trait.name)) for trait in character.get_trait_entries()
    ]


def derived_input_issues(
    inputs: TraitCompileInputs, *, selected: List[str]
) -> List[str]:
    """Validate derived inputs against the hard rules; return issue strings."""

    issues: List[str] = []
    selected_set = set(selected)

    if inputs.reputation is not None:
        issues.append("use the canonical 'fame' field, not 'reputation'")

    provided = {
        trait
        for trait in (
            "resources",
            "fame",
            "status",
            "allies",
            "contacts",
            "enemies",
            "domain",
            "patron",
            "dependents",
            "obligations",
        )
        if getattr(inputs, trait) is not None
    }
    for extra in sorted(provided - selected_set):
        issues.append(f"input provided for non-selected trait '{extra}'")
    for missing in sorted(selected_set - provided):
        issues.append(f"missing input for selected trait '{missing}'")

    if inputs.resources is not None and inputs.resources.level not in RESOURCE_TAGS:
        issues.append(
            f"resources.level {inputs.resources.level!r} not in "
            f"{sorted(RESOURCE_TAGS)}"
        )
    if inputs.fame is not None and inputs.fame.level not in FAME_TAGS:
        issues.append(f"fame.level {inputs.fame.level!r} not in {sorted(FAME_TAGS)}")

    if inputs.status is not None:
        if inputs.status.level not in STATUS_LEVELS:
            issues.append(
                f"status.level {inputs.status.level!r} not in {sorted(STATUS_LEVELS)}"
            )
        if inputs.status.scope_faction_entity_id is not None:
            issues.append("status.scope_faction_entity_id must be null")
        if not inputs.status.scope_faction_name:
            issues.append("status.scope_faction_name is required")

    if inputs.domain is not None:
        if inputs.domain.place_id is not None or inputs.domain.place_entity_id:
            issues.append("domain place ids must be null")
        if not inputs.domain.name:
            issues.append("domain.name is required")

    if inputs.patron is not None:
        if inputs.patron.character_id is not None or inputs.patron.character_entity_id:
            issues.append("patron character ids must be null")
        if not inputs.patron.name:
            issues.append("patron.name is required")

    if inputs.dependents is not None:
        if not inputs.dependents.targets:
            issues.append("dependents requires at least one target")
        for index, target in enumerate(inputs.dependents.targets):
            if target.character_id is not None or target.character_entity_id:
                issues.append(f"dependents.targets[{index}] ids must be null")
            if not target.name:
                issues.append(f"dependents.targets[{index}].name is required")

    if inputs.obligations is not None:
        if not inputs.obligations.targets:
            issues.append("obligations requires at least one target")
        for index, obligation in enumerate(inputs.obligations.targets):
            if (
                obligation.counterparty_id is not None
                or obligation.counterparty_entity_id is not None
            ):
                issues.append(f"obligations.targets[{index}] ids must be null")
            if not obligation.name:
                issues.append(f"obligations.targets[{index}].name is required")

    for trait in _RELATIONSHIP_TRAITS:
        trait_input = getattr(inputs, trait)
        if trait_input is None:
            continue
        if not trait_input.targets:
            issues.append(f"{trait} requires at least one target")
        for index, relation in enumerate(trait_input.targets):
            if relation.character_id is not None or relation.character_entity_id:
                issues.append(f"{trait}.targets[{index}] ids must be null")
            if not relation.name:
                issues.append(f"{trait}.targets[{index}].name is required")
            if relation.apply_pair_tag:
                issues.append(
                    f"{trait}.targets[{index}].apply_pair_tag must be false in "
                    "a fresh world"
                )

    return issues


def render_trait_input_prompt(
    *, character: "CharacterSheet", setting: "SettingCard"
) -> str:
    """Render the deterministic derivation prompt for the Skald call."""

    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"Trait input deriver prompt not found: {PROMPT_PATH}")
    instructions = PROMPT_PATH.read_text()

    payload = {
        "selected_traits": selected_canonical_traits(character),
        "character": {
            "name": character.name,
            "summary": character.summary,
            "background": character.background,
            "personality": character.personality,
            "traits": [
                {
                    "name": canonical_trait_name(str(trait.name)),
                    "description": trait.description,
                }
                for trait in character.get_trait_entries()
            ],
            "wildcard": {
                "name": character.wildcard_name,
                "description": character.wildcard_description,
            },
        },
        "setting": {
            "genre": setting.genre.value,
            "world_name": setting.world_name,
            "time_period": setting.time_period,
        },
        "vocabulary": {
            "resource_levels": sorted(RESOURCE_TAGS),
            "fame_levels": sorted(FAME_TAGS),
            "status_levels": sorted(STATUS_LEVELS),
            "patron_functions": list(PATRON_FUNCTIONS),
        },
    }
    return (
        f"{instructions}\n\n"
        "TRAIT_INPUT_DERIVATION_REQUEST:\n"
        f"{json.dumps(payload, indent=2, sort_keys=True)}"
    )


def derive_trait_compile_inputs(
    *,
    character: "CharacterSheet",
    setting: "SettingCard",
    model_name: str,
    max_tokens: int,
    retries: int,
) -> TraitCompileInputs:
    """Make the structured-output Skald call that derives trait inputs."""

    from pydantic_ai import Agent, ModelRetry, RunContext
    from pydantic_ai.settings import ModelSettings

    from nexus.api.pydantic_ai_utils import build_pydantic_ai_model

    selected = selected_canonical_traits(character)
    prompt = render_trait_input_prompt(character=character, setting=setting)

    agent: Any = Agent(
        model=build_pydantic_ai_model(model_name),
        output_type=TraitCompileInputs,
        system_prompt=(
            "You convert finished NEXUS character-wizard prose into typed "
            "trait compiler inputs. Follow the hard rules exactly."
        ),
        model_settings=ModelSettings(max_tokens=max_tokens),
        retries=retries,
    )

    async def _validate_output(
        _ctx: RunContext[None], output: TraitCompileInputs
    ) -> TraitCompileInputs:
        issues = derived_input_issues(output, selected=selected)
        if issues:
            formatted = "\n".join(f"- {issue}" for issue in issues)
            raise ModelRetry(
                "Derived trait inputs violate the hard rules. Fix every "
                f"issue and resubmit:\n{formatted}"
            )
        return output

    agent.output_validator(_validate_output)
    result = agent.run_sync(prompt)
    output = result.output
    if not isinstance(output, TraitCompileInputs):
        raise TypeError(
            "Trait input derivation returned "
            f"{type(output).__name__}, expected TraitCompileInputs"
        )
    return output


def ensure_trait_compile_inputs(
    transition_data: Any,
    *,
    slot: int,
    model_name: str,
    max_tokens: int,
    retries: int,
) -> Optional[dict[str, Any]]:
    """Derive and attach trait inputs to the transition's character sheet.

    Returns an outcome block for the transition result, or ``None`` when the
    sheet already carries typed inputs (a future wizard may collect them
    conversationally; derivation never overwrites).
    """

    character = transition_data.character
    if character.trait_compile_inputs is not None:
        logger.info(
            "Slot %s character already has trait_compile_inputs; skipping "
            "derivation",
            slot,
        )
        return None

    derived = derive_trait_compile_inputs(
        character=character,
        setting=transition_data.setting,
        model_name=model_name,
        max_tokens=max_tokens,
        retries=retries,
    )
    character.trait_compile_inputs = derived
    derived_traits = sorted(
        trait
        for trait in (
            "resources",
            "fame",
            "status",
            "allies",
            "contacts",
            "enemies",
            "domain",
            "patron",
            "dependents",
            "obligations",
        )
        if getattr(derived, trait) is not None
    )
    logger.info("Derived trait compile inputs for slot %s: %s", slot, derived_traits)
    return {
        "derived": True,
        "model": model_name,
        "traits": derived_traits,
    }
