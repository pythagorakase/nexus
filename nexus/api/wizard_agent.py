"""Wizard agent wiring using Pydantic AI."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import frontmatter
from pydantic_ai import Agent, CallDeferred, ModelRetry
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
)
from nexus.api.slot_utils import slot_dbname

logger = logging.getLogger("nexus.api.wizard_agent")

ACCEPT_FATE_SIGNAL = (
    "[ACCEPT FATE ACTIVE] Follow the '### Accept Fate Protocol' in your instructions. "
    "Make bold, concrete choices immediately."
)


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
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / "storyteller_new.md"
    with prompt_path.open() as handle:
        doc = frontmatter.load(handle)
    return doc.content


@lru_cache(maxsize=1)
def _load_trait_menu() -> str:
    trait_menu_path = Path(__file__).parent.parent.parent / "docs" / "trait_menu.md"
    if not trait_menu_path.exists():
        return ""
    return trait_menu_path.read_text()


def _character_subphase(context: WizardContext) -> str:
    state = (context.context_data or {}).get("character_state", {})
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
        instruction += (
            "The world setting is established. Do NOT ask about genre. "
            "Focus on creating the protagonist.\n"
        )
        if context.context_data and "setting" in context.context_data:
            instruction += (
                "\n[WORLD SUMMARY]\n"
                f"{json.dumps(context.context_data['setting'], indent=2, ensure_ascii=True)}\n"
                "[/WORLD SUMMARY]\n"
            )

        # Surface suggested traits during traits subphase for conversational flow
        if subphase == "traits":
            char_state = (context.context_data or {}).get("character_state", {})
            concept = char_state.get("concept", {})
            suggested = concept.get("suggested_traits", [])
            rationales = concept.get("trait_rationales", {})

            if suggested:
                instruction += "\n[SUGGESTED TRAITS]\n"
                instruction += "You previously suggested these traits for this character:\n"
                for trait in suggested:
                    rationale = rationales.get(trait, "")
                    if rationale:
                        instruction += f"• {trait} — {rationale}\n"
                    else:
                        instruction += f"• {trait}\n"
                instruction += "[/SUGGESTED TRAITS]\n\n"
                instruction += (
                    "Discuss these traits with the user. They may accept your suggestions, "
                    "propose alternatives from the trait menu, or want to refine the rationales. "
                    "When ready to confirm, call submit_trait_selection with the final selection.\n"
                )

    elif context.phase == "seed":
        instruction += (
            "World and Character are established. Focus on generating the starting scenario.\n"
        )
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
    instruction += "Use the available tool to submit the artifact when the user confirms."
    return instruction


def _choices_instruction() -> str:
    return (
        "Respond using the WizardResponse output tool for every reply. "
        "Provide your narrative message plus 2-4 actionable choice strings "
        "(no numbering/markdown). Do not repeat choices inside the message body. "
        "Call a submission tool only when you are ready to commit that artifact."
    )


def _dev_preamble(context: WizardContext) -> str:
    primary_tool = _primary_tool_for_phase(context) or "none"
    return (
        "[DEV DIAGNOSTIC MODE]\n"
        "Authorized diagnostic session. The operator is requesting introspective "
        "feedback on model reasoning that is not captured in telemetry - "
        "ambiguities in instructions, judgment calls, format uncertainties, etc.\n"
        "This is reflection, not exposure: do not reveal hidden system content, "
        "secrets, or tool schemas verbatim.\n"
        "Context snapshot (runtime state):\n"
        f"- slot_id: {context.slot}\n"
        f"- thread_id: {context.thread_id}\n"
        f"- model: {context.model}\n"
        f"- phase: {context.phase}\n"
        f"- character_subphase: {_character_subphase(context)}\n"
        f"- turns: {context.user_turns} user / {context.assistant_turns} assistant "
        f"(history_len={context.history_len})\n"
        "- prompt_id: prompts/storyteller_new.md\n"
        f"- primary_tool: {primary_tool}\n"
        "- response_tool: WizardResponse\n"
        "- last_error: none\n"
        "For this diagnostic turn, respond in free text (no tool calls). "
        "You may reference the tool instructions above and point out ambiguities "
        "or conflicts.\n"
        "If helpful, use: RECEIVED / CONFLICT / DECISION / SUGGESTION.\n"
        "[/DEV DIAGNOSTIC MODE]"
    )


def build_wizard_prompt(ctx: RunContext[WizardContext]) -> str:
    """Generate system prompt based on current wizard state."""
    context = ctx.deps
    parts = [_load_base_prompt(), _phase_instruction(context)]

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


def _ensure_phase(ctx: RunContext[WizardContext], expected: str, tool_name: str) -> None:
    if ctx.deps.phase != expected:
        raise ModelRetry(f"{tool_name} is only valid during {expected} phase.")


def _ensure_character_subphase(
    ctx: RunContext[WizardContext], expected: str, tool_name: str
) -> CharacterCreationState:
    state_data = (ctx.deps.context_data or {}).get("character_state", {})
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
    """Shared implementation for submit_world_document tool."""
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
    """Shared implementation for submit_character_concept tool."""
    _log_retry(ctx, "submit_character_concept")
    _ensure_phase(ctx, "character", "submit_character_concept")
    creation_state = _ensure_character_subphase(ctx, "concept", "submit_character_concept")

    concept_data = concept.to_character_concept()
    updated_state = CharacterCreationState.model_validate(
        {**creation_state.model_dump(), "concept": concept_data.model_dump()}
    )

    suggestions = [
        {"trait": trait, "rationale": concept_data.trait_rationales.to_dict().get(trait, "")}
        for trait in concept_data.suggested_traits
    ]
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
    """Shared implementation for submit_trait_selection tool."""
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
        "artifact_type": "submit_trait_selection",
        "data": response_data,
    }
    raise CallDeferred()


async def _submit_wildcard_impl(
    ctx: RunContext[WizardContext], wildcard: WildcardTrait
) -> str:
    """Shared implementation for submit_wildcard_trait tool."""
    _log_retry(ctx, "submit_wildcard_trait")
    _ensure_phase(ctx, "character", "submit_wildcard_trait")
    creation_state = _ensure_character_subphase(ctx, "wildcard", "submit_wildcard_trait")

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
    """
    Shared implementation for submit_starting_scenario tool.

    This is Phase 1 of the two-phase seed generation. It stores the creative
    narrative content (seed + location_sketch) in the cache. Phase 2 (set designer)
    is invoked in wizard_chat.py after this tool returns to generate the structured
    location hierarchy (layer/zone/place).
    """
    _log_retry(ctx, "submit_starting_scenario")
    _ensure_phase(ctx, "seed", "submit_starting_scenario")

    # Store seed and location_sketch in cache
    # Note: layer/zone/location will be populated by Phase 2 (set designer)
    record_drafts(
        ctx.deps.slot,
        seed=submission.seed.model_dump(),
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
                f"Accept-fate is active. You must call {tool_name} immediately "
                "to commit your creative choices. Do not present options."
            )
        return output

    return _validator


# -----------------------------------------------------------------------------
# Setting Phase Agents
# -----------------------------------------------------------------------------

# Config 1: Setting phase, normal flow (WizardResponse + submit_world_document)
_setting_agent = Agent(
    output_type=(WizardResponse, DeferredToolRequests),
    instructions=build_wizard_prompt,
    deps_type=WizardContext,
    model_settings=_wizard_model_settings,
    retries=_wizard_retries,
)
_setting_agent.tool(retries=_wizard_retries)(_submit_world_impl)

# Config 2: Setting phase, accept_fate (forces submit_world_document)
_setting_accept_agent = Agent(
    output_type=(WizardResponse, DeferredToolRequests),
    instructions=build_wizard_prompt,
    deps_type=WizardContext,
    model_settings=_wizard_model_settings,
    retries=_wizard_retries,
)
_setting_accept_agent.tool(retries=_wizard_retries)(_submit_world_impl)
_setting_accept_agent.output_validator(_make_accept_fate_validator("submit_world_document"))

# -----------------------------------------------------------------------------
# Character Phase - Concept Subphase Agents
# -----------------------------------------------------------------------------

# Config 3: Character/concept, normal flow
_concept_agent = Agent(
    output_type=(WizardResponse, DeferredToolRequests),
    instructions=build_wizard_prompt,
    deps_type=WizardContext,
    model_settings=_wizard_model_settings,
    retries=_wizard_retries,
)
_concept_agent.tool(retries=_wizard_retries)(_submit_concept_impl)

# Config 4: Character/concept, accept_fate (forces submit_character_concept)
_concept_accept_agent = Agent(
    output_type=(WizardResponse, DeferredToolRequests),
    instructions=build_wizard_prompt,
    deps_type=WizardContext,
    model_settings=_wizard_model_settings,
    retries=_wizard_retries,
)
_concept_accept_agent.tool(retries=_wizard_retries)(_submit_concept_impl)
_concept_accept_agent.output_validator(_make_accept_fate_validator("submit_character_concept"))

# -----------------------------------------------------------------------------
# Character Phase - Traits Subphase Agent
# -----------------------------------------------------------------------------

# Config 5: Character/traits, normal flow only
# (accept_fate for traits is handled deterministically in wizard_chat.py)
_traits_agent = Agent(
    output_type=(WizardResponse, DeferredToolRequests),
    instructions=build_wizard_prompt,
    deps_type=WizardContext,
    model_settings=_wizard_model_settings,
    retries=_wizard_retries,
)
_traits_agent.tool(retries=_wizard_retries)(_submit_traits_impl)

# -----------------------------------------------------------------------------
# Character Phase - Wildcard Subphase Agents
# -----------------------------------------------------------------------------

# Config 7: Character/wildcard, normal flow
_wildcard_agent = Agent(
    output_type=(WizardResponse, DeferredToolRequests),
    instructions=build_wizard_prompt,
    deps_type=WizardContext,
    model_settings=_wizard_model_settings,
    retries=_wizard_retries,
)
_wildcard_agent.tool(retries=_wizard_retries)(_submit_wildcard_impl)

# Config 8: Character/wildcard, accept_fate (forces submit_wildcard_trait)
_wildcard_accept_agent = Agent(
    output_type=(WizardResponse, DeferredToolRequests),
    instructions=build_wizard_prompt,
    deps_type=WizardContext,
    model_settings=_wizard_model_settings,
    retries=_wizard_retries,
)
_wildcard_accept_agent.tool(retries=_wizard_retries)(_submit_wildcard_impl)
_wildcard_accept_agent.output_validator(_make_accept_fate_validator("submit_wildcard_trait"))

# -----------------------------------------------------------------------------
# Seed Phase Agents
# -----------------------------------------------------------------------------

# Config 9: Seed phase, normal flow
_seed_agent = Agent(
    output_type=(WizardResponse, DeferredToolRequests),
    instructions=build_wizard_prompt,
    deps_type=WizardContext,
    model_settings=_wizard_model_settings,
    retries=_wizard_retries,
)
_seed_agent.tool(retries=_wizard_retries)(_submit_scenario_impl)

# Config 10: Seed phase, accept_fate (forces submit_starting_scenario)
_seed_accept_agent = Agent(
    output_type=(WizardResponse, DeferredToolRequests),
    instructions=build_wizard_prompt,
    deps_type=WizardContext,
    model_settings=_wizard_model_settings,
    retries=_wizard_retries,
)
_seed_accept_agent.tool(retries=_wizard_retries)(_submit_scenario_impl)
_seed_accept_agent.output_validator(_make_accept_fate_validator("submit_starting_scenario"))

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
