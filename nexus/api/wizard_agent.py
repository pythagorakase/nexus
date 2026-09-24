"""Wizard agent wiring using Pydantic AI."""

from __future__ import annotations


import calendar
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import frontmatter
from pydantic_ai import Agent, CallDeferred, ModelRetry, NativeOutput
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import DeferredToolRequests, RunContext

from nexus.api.config_utils import get_wizard_max_tokens, get_wizard_retry_budget
from nexus.api.new_story_cache import (
    clear_suggested_traits,
    get_selected_trait_count,
    get_trait_menu,
    read_cache,
    write_suggested_traits,
)
from nexus.api.new_story_flow import record_drafts
from nexus.api.new_story_schemas import (
    CharacterConceptSubmission,
    CharacterCreationState,
    CharacterSheet,
    SettingCard,
    StorySeedSubmission,
    TraitSelection,
    WildcardTrait,
    WizardResponse,
    extract_setting_date_constraint,
)
from nexus.api.slot_utils import slot_dbname
from nexus.api.trait_compiler_schemas import canonical_trait_name
from nexus.agents.orrery.tag_library import format_tag_library_for_prompt
from nexus.prompts.registry import PromptId, load

logger = logging.getLogger("nexus.api.wizard_agent")

ACCEPT_FATE_SIGNAL = load(PromptId.WIZARD_ACCEPT_FATE)


@dataclass
class WizardContext:
    """Dependency container for wizard agent runs."""

    slot: int
    cache: Any
    phase: str
    thread_id: str
    model: str
    context_data: Optional[Dict[str, Any]] = None
    accept_fate: bool = False
    dev_mode: bool = False
    history_len: int = 0
    user_turns: int = 0
    assistant_turns: int = 0
    last_tool_result: Optional[Dict[str, Any]] = None
    last_tool_name: Optional[str] = None

    @classmethod
    def from_request(
        cls,
        *,
        slot: int,
        phase: str,
        thread_id: str,
        model: str,
        context_data: Optional[Dict[str, Any]],
        accept_fate: bool,
        dev_mode: bool,
        history_len: int,
        user_turns: int,
        assistant_turns: int,
    ) -> "WizardContext":
        cache = read_cache(slot_dbname(slot))
        if not cache:
            raise ValueError(f"No wizard cache found for slot {slot}")
        return cls(
            slot=slot,
            cache=cache,
            phase=phase,
            thread_id=thread_id,
            model=model,
            context_data=context_data,
            accept_fate=accept_fate,
            dev_mode=dev_mode,
            history_len=history_len,
            user_turns=user_turns,
            assistant_turns=assistant_turns,
        )

    @classmethod
    def from_slot(cls, *, slot: int, model: str) -> "WizardContext":
        cache = read_cache(slot_dbname(slot))
        if not cache:
            raise ValueError(f"No wizard cache found for slot {slot}")
        return cls(
            slot=slot,
            cache=cache,
            phase=cache.current_phase(),
            thread_id=cache.thread_id or "",
            model=model,
        )


@lru_cache(maxsize=1)
def _load_base_prompt() -> str:
    return frontmatter.loads(load(PromptId.STORYTELLER_NEW)).content


@lru_cache(maxsize=1)
def _load_trait_menu() -> str:
    trait_menu_path = Path(__file__).parent.parent.parent / "docs" / "trait_menu.md"
    if not trait_menu_path.exists():
        return ""
    return trait_menu_path.read_text()


def _character_subphase(context: WizardContext) -> str:
    state = (context.context_data or {}).get("character_state") or {}
    if state.get("concept") is None:
        return "concept"
    if state.get("trait_selection") is None:
        return "traits"
    if state.get("wildcard") is None:
        return "wildcard"
    return "complete"


def _primary_tool_for_phase(context: WizardContext) -> Optional[str]:
    if context.phase == "setting":
        return "submit_world_document"
    if context.phase == "seed":
        return "submit_starting_scenario"
    if context.phase == "character":
        subphase = _character_subphase(context)
        if subphase == "concept":
            return "submit_character_concept"
        if subphase == "traits":
            return "submit_trait_selection"
        if subphase == "wildcard":
            return "submit_wildcard_trait"
    return None


def _phase_instruction(context: WizardContext) -> str:
    instruction = f"Current Phase: {context.phase.upper()}.\n"
    if context.phase == "character":
        subphase = _character_subphase(context)
        instruction += load(PromptId.WIZARD_CHARACTER_PHASE)
        if context.context_data and "setting" in context.context_data:
            instruction += (
                "\n[WORLD SUMMARY]\n"
                f"{json.dumps(context.context_data['setting'], indent=2, ensure_ascii=True)}\n"
                "[/WORLD SUMMARY]\n"
            )

        # Surface suggested traits during traits subphase for conversational flow
        if subphase == "traits":
            char_state = (context.context_data or {}).get("character_state") or {}
            concept = char_state.get("concept", {})
            suggested = concept.get("suggested_traits", [])
            rationales = concept.get("trait_rationales", {})

            if suggested:
                instruction += "\n[SUGGESTED TRAITS]\n"
                instruction += load(PromptId.WIZARD_SUGGESTED_TRAITS_INTRO)
                for trait in suggested:
                    rationale = rationales.get(trait, "")
                    if rationale:
                        instruction += f"• {trait} — {rationale}\n"
                    else:
                        instruction += f"• {trait}\n"
                instruction += "[/SUGGESTED TRAITS]\n\n"
                instruction += load(PromptId.WIZARD_SUGGESTED_TRAITS_INSTRUCTION)

    elif context.phase == "seed":
        instruction += load(PromptId.WIZARD_SEED_PHASE)
        if context.context_data:
            if "setting" in context.context_data:
                instruction += (
                    "\n[WORLD SUMMARY]\n"
                    f"{json.dumps(context.context_data['setting'], indent=2, ensure_ascii=True)}\n"
                    "[/WORLD SUMMARY]\n"
                )
            if "character" in context.context_data:
                instruction += (
                    "\n[CHARACTER SHEET]\n"
                    f"{json.dumps(context.context_data['character'], indent=2, ensure_ascii=True)}\n"
                    "[/CHARACTER SHEET]\n"
                )
    instruction += load(PromptId.WIZARD_SUBMIT_INSTRUCTION)
    return instruction


def _choices_instruction() -> str:
    return load(PromptId.WIZARD_CHOICES_INSTRUCTION)


def _dev_preamble(context: WizardContext) -> str:
    primary_tool = _primary_tool_for_phase(context) or "none"
    return load(
        PromptId.WIZARD_DEV_PREAMBLE,
        CONTEXT_SLOT=f"{context.slot}",
        CONTEXT_THREAD_ID=f"{context.thread_id}",
        CONTEXT_MODEL=f"{context.model}",
        CONTEXT_PHASE=f"{context.phase}",
        CHARACTER_SUBPHASE_CONTEXT=f"{_character_subphase(context)}",
        CONTEXT_USER_TURNS=f"{context.user_turns}",
        CONTEXT_ASSISTANT_TURNS=f"{context.assistant_turns}",
        CONTEXT_HISTORY_LEN=f"{context.history_len}",
        PRIMARY_TOOL=f"{primary_tool}",
    )


def build_wizard_prompt(ctx: RunContext[WizardContext]) -> str:
    """Generate system prompt based on current wizard state."""
    context = ctx.deps
    parts = [_load_base_prompt(), _phase_instruction(context)]
    parts.append(
        "\n\n---\n\n" + format_tag_library_for_prompt(slot_dbname(context.slot))
    )

    if context.phase == "character":
        trait_menu = _load_trait_menu()
        if trait_menu:
            parts.append("\n\n---\n\n# Trait Reference\n\n" + trait_menu)

    if context.dev_mode:
        parts.append(_dev_preamble(context))
    else:
        parts.append(_choices_instruction())

    if context.accept_fate:
        parts.append(ACCEPT_FATE_SIGNAL)

    return "\n\n".join(parts)


def _log_retry(ctx: RunContext[WizardContext], tool_name: str) -> None:
    if ctx.retry > 0:
        logger.warning(
            "ModelRetry triggered",
            extra={
                "tool": tool_name,
                "attempt": ctx.retry + 1,
                "slot": ctx.deps.slot,
            },
        )


def _ensure_phase(
    ctx: RunContext[WizardContext], expected: str, tool_name: str
) -> None:
    if ctx.deps.phase != expected:
        raise ModelRetry(f"{tool_name} is only valid during {expected} phase.")


def _ensure_character_subphase(
    ctx: RunContext[WizardContext], expected: str, tool_name: str
) -> CharacterCreationState:
    state_data = (ctx.deps.context_data or {}).get("character_state") or {}
    creation_state = CharacterCreationState.model_validate(state_data)
    subphase = creation_state.current_subphase()
    if subphase != expected:
        raise ModelRetry(
            f"{tool_name} is only valid during character subphase {expected}."
        )
    return creation_state


# =============================================================================
# Tool Implementation Functions (shared across agents)
# =============================================================================


async def _submit_world_impl(
    ctx: RunContext[WizardContext], setting: SettingCard
) -> str:
    _log_retry(ctx, "submit_world_document")
    _ensure_phase(ctx, "setting", "submit_world_document")

    record_drafts(ctx.deps.slot, setting=setting.model_dump())

    ctx.deps.last_tool_name = "submit_world_document"
    ctx.deps.last_tool_result = {
        "message": "Generating artifact...",
        "phase_complete": True,
        "subphase_complete": False,
        "phase": ctx.deps.phase,
        "artifact_type": "submit_world_document",
        "data": setting.model_dump(),
    }
    raise CallDeferred()


async def _submit_concept_impl(
    ctx: RunContext[WizardContext], concept: CharacterConceptSubmission
) -> str:
    _log_retry(ctx, "submit_character_concept")
    _ensure_phase(ctx, "character", "submit_character_concept")
    creation_state = _ensure_character_subphase(
        ctx, "concept", "submit_character_concept"
    )

    concept_data = concept.to_character_concept()
    updated_state = CharacterCreationState.model_validate(
        {**creation_state.model_dump(), "concept": concept_data.model_dump()}
    )

    rationales = concept_data.trait_rationales.to_dict()
    suggestions = []
    for trait in concept_data.suggested_traits:
        storage_name = canonical_trait_name(trait)
        rationale = (
            rationales.get(trait)
            or rationales.get(storage_name)
            or (rationales.get("reputation") if storage_name == "fame" else None)
            or ""
        )
        suggestions.append({"trait": trait, "rationale": rationale})
    if suggestions:
        write_suggested_traits(slot_dbname(ctx.deps.slot), suggestions)

    record_drafts(ctx.deps.slot, character=updated_state.model_dump())

    response_data: Dict[str, Any] = {"character_state": updated_state.model_dump()}
    phase_complete = updated_state.is_complete()
    if phase_complete:
        response_data["character_sheet"] = (
            updated_state.to_character_sheet().model_dump()
        )

    result = {
        "message": "Generating artifact...",
        "phase_complete": phase_complete,
        "subphase_complete": True,
        "phase": ctx.deps.phase,
        "artifact_type": "submit_character_concept",
        "data": response_data,
    }

    dbname = slot_dbname(ctx.deps.slot)
    trait_menu = get_trait_menu(dbname)
    selected_count = get_selected_trait_count(dbname)
    result["subphase"] = "traits"
    result["trait_menu"] = [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "is_selected": t.is_selected,
            "rationale": t.rationale,
        }
        for t in trait_menu
    ]
    result["can_confirm"] = selected_count == 3

    ctx.deps.last_tool_name = "submit_character_concept"
    ctx.deps.last_tool_result = result
    raise CallDeferred()


async def _submit_traits_impl(
    ctx: RunContext[WizardContext], selection: TraitSelection
) -> str:
    _log_retry(ctx, "submit_trait_selection")
    _ensure_phase(ctx, "character", "submit_trait_selection")
    creation_state = _ensure_character_subphase(ctx, "traits", "submit_trait_selection")

    updated_state = apply_trait_selection_to_state(creation_state, selection)

    clear_suggested_traits(slot_dbname(ctx.deps.slot))
    record_drafts(ctx.deps.slot, character=updated_state.model_dump())

    response_data: Dict[str, Any] = {"character_state": updated_state.model_dump()}
    phase_complete = updated_state.is_complete()
    if phase_complete:
        response_data["character_sheet"] = (
            updated_state.to_character_sheet().model_dump()
        )

    ctx.deps.last_tool_name = "submit_trait_selection"
    ctx.deps.last_tool_result = {
        "message": "Generating artifact...",
        "phase_complete": phase_complete,
        "subphase_complete": True,
        "phase": ctx.deps.phase,
        "subphase": "wildcard",
        "artifact_type": "submit_trait_selection",
        "data": response_data,
    }
    raise CallDeferred()


async def _submit_wildcard_impl(
    ctx: RunContext[WizardContext], wildcard: WildcardTrait
) -> str:
    _log_retry(ctx, "submit_wildcard_trait")
    _ensure_phase(ctx, "character", "submit_wildcard_trait")
    creation_state = _ensure_character_subphase(
        ctx, "wildcard", "submit_wildcard_trait"
    )

    # Validate bestowed Orrery tags against the live registry now, while
    # Skald can still repair them; an invalid name would otherwise explode
    # later inside the transition transaction (M9 gate finding).
    if wildcard.orrery_tags is not None:
        from nexus.agents.orrery.tag_writer import validate_tag_bestowal
        from nexus.api.db_pool import get_connection

        with get_connection(slot_dbname(ctx.deps.slot)) as conn:
            with conn.cursor() as cur:
                tag_issues = validate_tag_bestowal(
                    cur,
                    entity_kind="character",
                    bestowal=wildcard.orrery_tags,
                )
        if tag_issues:
            formatted = "\n".join(f"- {issue}" for issue in tag_issues)
            raise ModelRetry(
                load(PromptId.WIZARD_WILDCARD_TAG_RETRY, FORMATTED=f"{formatted}")
            )

    updated_state = CharacterCreationState.model_validate(
        {**creation_state.model_dump(), "wildcard": wildcard.model_dump()}
    )

    record_drafts(ctx.deps.slot, character=updated_state.model_dump())

    response_data: Dict[str, Any] = {"character_state": updated_state.model_dump()}
    phase_complete = updated_state.is_complete()
    if phase_complete:
        response_data["character_sheet"] = (
            updated_state.to_character_sheet().model_dump()
        )

    ctx.deps.last_tool_name = "submit_wildcard_trait"
    ctx.deps.last_tool_result = {
        "message": "Generating artifact...",
        "phase_complete": phase_complete,
        "subphase_complete": True,
        "phase": ctx.deps.phase,
        "artifact_type": "submit_wildcard_trait",
        "data": response_data,
    }
    raise CallDeferred()


async def _submit_scenario_impl(
    ctx: RunContext[WizardContext], submission: StorySeedSubmission
) -> str:
    _log_retry(ctx, "submit_starting_scenario")
    _ensure_phase(ctx, "seed", "submit_starting_scenario")

    setting_data: Optional[Dict[str, Any]] = None
    if ctx.deps.cache is not None:
        get_setting_dict = getattr(ctx.deps.cache, "get_setting_dict", None)
        if get_setting_dict is None:
            raise TypeError("Wizard seed context cache cannot provide its setting")
        setting_data = get_setting_dict()
    elif ctx.deps.context_data is not None:
        setting_data = ctx.deps.context_data.get("setting")

    if setting_data is None:
        raise RuntimeError("Seed submission requires an accepted setting artifact")

    setting = SettingCard.model_validate(setting_data)
    date_constraint = extract_setting_date_constraint(setting)
    seed_timestamp = submission.seed.base_timestamp
    if date_constraint and date_constraint.conflicts_with(seed_timestamp):
        received = (
            f"{calendar.month_name[seed_timestamp.month]} {seed_timestamp.day}, "
            f"{seed_timestamp.year}"
        )
        raise ModelRetry(
            "submit_starting_scenario rejected: base_timestamp conflicts with "
            "the accepted SettingCard date. Expected "
            f"{date_constraint.describe()} from SettingCard.time_period and any "
            f"matching full diegetic_artifact date; received {received}. Repair "
            "base_timestamp to match the accepted setting before resubmitting."
        )

    # Store seed and location_sketch in cache
    # Note: layer/zone/location will be populated by Phase 2 (set designer)
    record_drafts(
        ctx.deps.slot,
        seed=submission.seed.model_dump(),
        base_timestamp=submission.seed.get_base_datetime().isoformat(),
    )

    ctx.deps.last_tool_name = "submit_starting_scenario"
    ctx.deps.last_tool_result = {
        "message": "Generating artifact...",
        "phase_complete": False,  # Not complete until set designer runs
        "subphase_complete": False,
        "phase": ctx.deps.phase,
        "artifact_type": "submit_starting_scenario",
        "data": submission.model_dump(),
        "location_sketch": submission.location_sketch,  # Pass to Phase 2
        "requires_set_design": True,  # Signal that Phase 2 is needed
    }
    raise CallDeferred()


# =============================================================================
# Shared State Helpers
# =============================================================================


def apply_trait_selection_to_state(
    creation_state: CharacterCreationState, selection: TraitSelection
) -> CharacterCreationState:
    """
    Apply trait selection to character creation state.

    Used by both the submit_trait_selection tool and the deterministic
    accept_fate path to ensure consistent state updates.
    """
    return CharacterCreationState.model_validate(
        {**creation_state.model_dump(), "trait_selection": selection.model_dump()}
    )


# =============================================================================
# Agent Configurations
# =============================================================================
#
# TODO: Refactor phase names from strings to ordinals in a subsequent PR:
#   Phase 1 = "setting"    (world/genre)
#   Phase 2 = "character"  subphase "concept" (archetype)
#   Phase 3 = "character"  subphase "traits"
#   Phase 4 = "character"  subphase "wildcard"
#   Phase 5 = "seed"       (story seed/starting scenario)
#

# Common settings for all wizard agents
_wizard_model_settings = ModelSettings(max_tokens=get_wizard_max_tokens())
_wizard_retries = get_wizard_retry_budget()

# Type alias for agent output
AgentOutput = WizardResponse | DeferredToolRequests
_wizard_response_output = NativeOutput(WizardResponse, strict=True)


def _make_accept_fate_validator(tool_name: str):
    """
    Create a result validator that rejects WizardResponse for accept_fate agents.

    This enforces tool calling by rejecting conversational responses and
    instructing the model to call the appropriate submission tool.
    """

    async def _validator(
        ctx: RunContext[WizardContext], output: AgentOutput
    ) -> AgentOutput:
        if isinstance(output, WizardResponse):
            raise ModelRetry(
                load(PromptId.WIZARD_ACCEPT_FATE_RETRY, TOOL_NAME=f"{tool_name}")
            )
        return output

    return _validator


# -----------------------------------------------------------------------------
# Setting Phase Agents
# -----------------------------------------------------------------------------

# Config 1: Setting phase, normal flow (WizardResponse + submit_world_document)
_setting_agent = Agent(
    output_type=(_wizard_response_output, DeferredToolRequests),
    instructions=build_wizard_prompt,
    deps_type=WizardContext,
    model_settings=_wizard_model_settings,
    retries=_wizard_retries,
)
_setting_agent.tool(
    description=load(PromptId.WIZARD_TOOL_SUBMIT_WORLD_DOCUMENT),
    name="submit_world_document",
    retries=_wizard_retries,
)(_submit_world_impl)

# Config 2: Setting phase, accept_fate (forces submit_world_document)
_setting_accept_agent = Agent(
    output_type=(_wizard_response_output, DeferredToolRequests),
    instructions=build_wizard_prompt,
    deps_type=WizardContext,
    model_settings=_wizard_model_settings,
    retries=_wizard_retries,
)
_setting_accept_agent.tool(
    description=load(PromptId.WIZARD_TOOL_SUBMIT_WORLD_DOCUMENT),
    name="submit_world_document",
    retries=_wizard_retries,
)(_submit_world_impl)
_setting_accept_agent.output_validator(
    _make_accept_fate_validator("submit_world_document")
)

# -----------------------------------------------------------------------------
# Character Phase - Concept Subphase Agents
# -----------------------------------------------------------------------------

# Config 3: Character/concept, normal flow
_concept_agent = Agent(
    output_type=(_wizard_response_output, DeferredToolRequests),
    instructions=build_wizard_prompt,
    deps_type=WizardContext,
    model_settings=_wizard_model_settings,
    retries=_wizard_retries,
)
_concept_agent.tool(
    description=load(PromptId.WIZARD_TOOL_SUBMIT_CHARACTER_CONCEPT),
    name="submit_character_concept",
    retries=_wizard_retries,
)(_submit_concept_impl)

# Config 4: Character/concept, accept_fate (forces submit_character_concept)
_concept_accept_agent = Agent(
    output_type=(_wizard_response_output, DeferredToolRequests),
    instructions=build_wizard_prompt,
    deps_type=WizardContext,
    model_settings=_wizard_model_settings,
    retries=_wizard_retries,
)
_concept_accept_agent.tool(
    description=load(PromptId.WIZARD_TOOL_SUBMIT_CHARACTER_CONCEPT),
    name="submit_character_concept",
    retries=_wizard_retries,
)(_submit_concept_impl)
_concept_accept_agent.output_validator(
    _make_accept_fate_validator("submit_character_concept")
)

# -----------------------------------------------------------------------------
# Character Phase - Traits Subphase Agent
# -----------------------------------------------------------------------------

# Config 5: Character/traits, normal flow only
# (accept_fate for traits is handled deterministically in wizard_chat.py)
_traits_agent = Agent(
    output_type=(_wizard_response_output, DeferredToolRequests),
    instructions=build_wizard_prompt,
    deps_type=WizardContext,
    model_settings=_wizard_model_settings,
    retries=_wizard_retries,
)
_traits_agent.tool(
    description=load(PromptId.WIZARD_TOOL_SUBMIT_TRAIT_SELECTION),
    name="submit_trait_selection",
    retries=_wizard_retries,
)(_submit_traits_impl)

# -----------------------------------------------------------------------------
# Character Phase - Wildcard Subphase Agents
# -----------------------------------------------------------------------------

# Config 7: Character/wildcard, normal flow
_wildcard_agent = Agent(
    output_type=(_wizard_response_output, DeferredToolRequests),
    instructions=build_wizard_prompt,
    deps_type=WizardContext,
    model_settings=_wizard_model_settings,
    retries=_wizard_retries,
)
_wildcard_agent.tool(
    description=load(PromptId.WIZARD_TOOL_SUBMIT_WILDCARD_TRAIT),
    name="submit_wildcard_trait",
    retries=_wizard_retries,
)(_submit_wildcard_impl)

# Config 8: Character/wildcard, accept_fate (forces submit_wildcard_trait)
_wildcard_accept_agent = Agent(
    output_type=(_wizard_response_output, DeferredToolRequests),
    instructions=build_wizard_prompt,
    deps_type=WizardContext,
    model_settings=_wizard_model_settings,
    retries=_wizard_retries,
)
_wildcard_accept_agent.tool(
    description=load(PromptId.WIZARD_TOOL_SUBMIT_WILDCARD_TRAIT),
    name="submit_wildcard_trait",
    retries=_wizard_retries,
)(_submit_wildcard_impl)
_wildcard_accept_agent.output_validator(
    _make_accept_fate_validator("submit_wildcard_trait")
)

# -----------------------------------------------------------------------------
# Seed Phase Agents
# -----------------------------------------------------------------------------

# Config 9: Seed phase, normal flow
_seed_agent = Agent(
    output_type=(_wizard_response_output, DeferredToolRequests),
    instructions=build_wizard_prompt,
    deps_type=WizardContext,
    model_settings=_wizard_model_settings,
    retries=_wizard_retries,
)
_seed_agent.tool(
    description=load(PromptId.WIZARD_TOOL_SUBMIT_STARTING_SCENARIO),
    name="submit_starting_scenario",
    retries=_wizard_retries,
)(_submit_scenario_impl)

# Config 10: Seed phase, accept_fate (forces submit_starting_scenario)
_seed_accept_agent = Agent(
    output_type=(_wizard_response_output, DeferredToolRequests),
    instructions=build_wizard_prompt,
    deps_type=WizardContext,
    model_settings=_wizard_model_settings,
    retries=_wizard_retries,
)
_seed_accept_agent.tool(
    description=load(PromptId.WIZARD_TOOL_SUBMIT_STARTING_SCENARIO),
    name="submit_starting_scenario",
    retries=_wizard_retries,
)(_submit_scenario_impl)
_seed_accept_agent.output_validator(
    _make_accept_fate_validator("submit_starting_scenario")
)

# -----------------------------------------------------------------------------
# Debug Agent (unchanged)
# -----------------------------------------------------------------------------

wizard_debug_agent = Agent(
    output_type=str,
    instructions=build_wizard_prompt,
    deps_type=WizardContext,
    model_settings=_wizard_model_settings,
)


# =============================================================================
# Agent Factory
# =============================================================================


def get_wizard_agent(context: WizardContext) -> Agent:
    """
    Return the appropriate agent configuration for the current wizard state.

    This factory selects an agent based on phase, subphase, and accept_fate flag.
    Each agent configuration exposes only the tools valid for that state:
    - Normal flow: WizardResponse (choices) + phase-appropriate submission tool
    - Accept-fate: Phase-appropriate submission tool only (no WizardResponse)

    Note: Traits + accept_fate is handled deterministically in wizard_chat.py,
    so this factory won't be called for that combination.
    """
    phase = context.phase
    accept_fate = context.accept_fate

    if phase == "setting":
        return _setting_accept_agent if accept_fate else _setting_agent

    if phase == "character":
        subphase = _character_subphase(context)
        if subphase == "concept":
            return _concept_accept_agent if accept_fate else _concept_agent
        if subphase == "traits":
            # Accept-fate for traits is deterministic (no LLM call)
            # This branch only handles conversational flow
            return _traits_agent
        if subphase == "wildcard":
            return _wildcard_accept_agent if accept_fate else _wildcard_agent
        # subphase == "complete" shouldn't reach here
        raise ValueError(f"Character phase complete, cannot get agent")

    if phase == "seed":
        return _seed_accept_agent if accept_fate else _seed_agent

    raise ValueError(f"Unknown wizard phase: {phase}")


# Public API aliases (used by tests and external consumers)
wizard_agent = _setting_agent

# Tool function aliases for testing (tests call these directly with mock contexts)
submit_world_document = _submit_world_impl
submit_character_concept = _submit_concept_impl
submit_trait_selection = _submit_traits_impl
submit_wildcard_trait = _submit_wildcard_impl
submit_starting_scenario = _submit_scenario_impl
