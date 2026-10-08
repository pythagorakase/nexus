"""
FastAPI endpoints for the new story wizard chat functionality.

This module handles the conversational wizard that guides users through
story creation, including:
- Chat interactions with phase-specific tool calls
- Character creation sub-phases (concept, traits, wildcard)
- Transition from wizard to narrative mode
"""

import asyncio
import logging
from dataclasses import replace
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
import frontmatter
from pydantic import ValidationError
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import DeferredToolRequests

from nexus.api.conversations import ConversationsClient
from nexus.api.config_utils import (
    get_new_story_model,
    get_retrograde_status_poll_interval_seconds,
    get_wizard_history_limit,
    get_wizard_max_tokens,
)
from nexus.api.narrative_schemas import (
    ChatRequest,
    TransitionRequest,
    TransitionResponse,
    WeirdLevel,
    WeirdLevelRequest,
)
from nexus.api.new_story_cache import (
    WizardCache,
    claim_wizard_introduction,
    clear_suggested_traits,
    complete_wizard_introduction,
    guarded_wizard_write,
    read_cache,
    write_weird_level,
    write_wizard_choices,
)
from nexus.api.new_story_flow import (
    build_transition_data_from_cache,
    perform_transition_with_retrograde,
    record_drafts,
    switch_wizard_model,
)
from nexus.api.new_story_generator import generate_set_design
from nexus.api.new_story_schemas import (
    CharacterCreationState,
    SettingCard,
    StorySeed,
    TraitSelection,
    TraitRationales,
)
from nexus.api.pydantic_ai_utils import (
    build_message_history,
    build_pydantic_ai_model_with_provider,
)
from nexus.api.slot_mutations import require_writable_slot
from nexus.api.slot_utils import slot_dbname
from nexus.api.wizard_confirmation import WizardStateConflict
from nexus.api.wizard_transcript import introduction_delivered
from nexus.api.wizard_agent import (
    WizardContext,
    wizard_debug_agent,
    get_wizard_agent,
    apply_trait_selection_to_state,
    _character_subphase,
)
from nexus.config import load_settings
from nexus.telemetry.usage import record_pydantic_ai_result
from nexus.prompts.registry import PromptId, load

logger = logging.getLogger("nexus.api.wizard_chat")

router = APIRouter(prefix="/api/story/new", tags=["wizard"])


def resolve_wizard_model(
    request_model: Optional[str], slot_model: Optional[str]
) -> str:
    """Resolve the effective wizard model for a turn.

    Precedence: explicit request override -> the slot's stamped model
    (locked at setup start) -> player wizard preference -> nexus.toml default. The mock TEST model is never introduced here; it can only
    arrive as an explicit request override or a deliberate slot stamp.
    """
    from nexus.config.story_model import StorySettings, resolve_story_model

    return resolve_story_model(
        "wizard", story=StorySettings(skald_model=slot_model), override=request_model
    )


def wizard_model_lock_candidate(
    request_model: Optional[str], slot_model: Optional[str]
) -> bool:
    """Whether a request may violate the wizard model lock.

    Only an explicit request override that differs from the slot's stamped
    model can conflict; an omitted model always resolves to the stamped
    model and is therefore never a lock violation. The caller still checks
    message history before raising 409 (the lock engages after the first
    user message).
    """
    return bool(request_model and slot_model and request_model != slot_model)


def _wizard_subphase_for_state(
    phase: str,
    *,
    has_concept: bool,
    has_traits: bool,
    has_wildcard: bool,
) -> str:
    """Name the canonical wizard subphase represented by persisted state."""
    if phase != "character":
        return "none"
    if not has_concept:
        return "concept"
    if not has_traits:
        return "traits"
    if not has_wildcard:
        return "wildcard"
    return "complete"


def _hydrate_character_context(request: ChatRequest) -> Optional[Dict[str, Any]]:
    """Use persisted character subphases instead of stale client-side concepts."""
    context = request.context_data
    if request.current_phase != "character":
        return context

    cache = read_cache(slot_dbname(request.slot))
    char_state = cache.get_character_state_dict() if cache else None
    return {**(context or {}), "character_state": char_state}


_ALREADY_INTRODUCED = "This phase was already introduced. Resume before continuing."


def _reconcile_introduction(
    cache: Optional[WizardCache],
    message_origin: str,
    *,
    slot: int,
    request_model: Optional[str],
    slot_model: Optional[str],
) -> Optional[str]:
    """Refuse a delivered introduction; return an undelivered claim to replace.

    Until a character concept or seed draft exists, the only wizard control
    message is the introduction that artifact acceptance requests. A completed
    reply records its choices, so that introduction already arrived. An
    unfinished claim is settled against the transcript: a reply after its
    control message was delivered, so the claim is completed and this request
    refused; otherwise its writer failed or is still running, and this request
    may replace exactly that claim.
    """
    if (
        cache is None
        or message_origin != "wizard_control"
        or not cache.phase_untouched()
    ):
        return None
    if cache.choices_recorded:
        raise HTTPException(status_code=409, detail=_ALREADY_INTRODUCED)
    claim = cache.introduction_claim
    if claim is None:
        return None
    thread_id = cache.thread_id
    if thread_id is None:
        raise WizardStateConflict("The saved wizard is missing its conversation.")
    # The same store the introduction's control and reply were written to.
    client = ConversationsClient(model=resolve_wizard_model(request_model, slot_model))
    try:
        transcript = client.list_messages(thread_id, limit=0)
    finally:
        if client.client is not None:
            client.client.close()
    if introduction_delivered(list(reversed(transcript))):
        complete_wizard_introduction(
            claim.id, claim.choices, slot_dbname(slot), expected_thread_id=thread_id
        )
        raise HTTPException(status_code=409, detail=_ALREADY_INTRODUCED)
    return claim.id


def _is_introduction(cache: Optional[WizardCache], message_origin: str) -> bool:
    """Whether this control message requests an accepted phase's introduction."""
    return bool(
        cache is not None
        and message_origin == "wizard_control"
        and cache.awaiting_introduction()
    )


def _record_text_reply(
    client: ConversationsClient,
    *,
    slot: int,
    thread_id: str,
    message: str,
    choices: List[str],
    introduction: bool,
    replaces_claim: Optional[str],
) -> None:
    """Persist a text reply's transcript message and presented choices.

    The conversation store cannot share a transaction with the recorded choices
    that prove an introduction arrived. An introduction therefore claims its
    reply first, so concurrent introductions keep one reply, then writes the
    transcript and completes the claim. A failure or crash between those steps
    leaves an unfinished claim that the next request reconciles.
    """
    dbname = slot_dbname(slot)
    if not introduction:
        client.add_message(thread_id, "assistant", message)
        write_wizard_choices(choices, dbname, expected_thread_id=thread_id)
        return
    claim_id = claim_wizard_introduction(
        choices, dbname, expected_thread_id=thread_id, replaces_claim=replaces_claim
    )
    client.add_message(thread_id, "assistant", message)
    complete_wizard_introduction(
        claim_id, choices, dbname, expected_thread_id=thread_id
    )


def _accept_fate_prompt(message: Optional[str]) -> str:
    """Provide a deterministic user prompt when accept_fate is requested."""
    if message and message.strip():
        return message
    return "Accept fate."


async def _handle_accept_fate_traits(
    context: WizardContext,
    accept_fate: bool,
    current_phase: Optional[str],
    slot: int,
    message_history: list,
    model: Any,
    model_name: str,
    provider_name: str,
    model_settings: ModelSettings,
    client: ConversationsClient,
    thread_id: str,
) -> Optional[dict]:
    """
    Handle accept_fate during traits subphase deterministically.

    Returns tool result dict if handled, None to fall through to standard flow.
    """
    if not (
        accept_fate
        and current_phase == "character"
        and _character_subphase(context) == "traits"
    ):
        return None

    cache = context.cache
    if not cache or not cache.character.suggested_traits:
        return None
    if (
        cache.character_revision_pending
        or cache.thread_id != thread_id
        or cache.current_phase() != "character"
    ):
        raise WizardStateConflict("The wizard changed before traits could be accepted.")

    # Build TraitSelection from suggested traits (exactly 3 guaranteed by schema)
    selected = [st.trait for st in cache.character.suggested_traits]
    rationales_dict = {
        st.trait: st.rationale for st in cache.character.suggested_traits
    }
    trait_selection = TraitSelection(
        selected_traits=selected,
        trait_rationales=TraitRationales(**rationales_dict),
        suggested_by_llm=selected,
    )

    # Get current character state and apply trait selection
    char_state_data = cache.get_character_state_dict()
    creation_state = CharacterCreationState.model_validate(char_state_data)
    updated_state = apply_trait_selection_to_state(creation_state, trait_selection)

    # Commit to cache (same as tool would do)
    with guarded_wizard_write(slot_dbname(slot), cache):
        clear_suggested_traits(slot_dbname(slot))
        record_drafts(slot, character=updated_state.model_dump())
        # Capture the exact committed state before releasing its lock.
        context.cache = read_cache(slot_dbname(slot))

    # This deterministic transition committed before the wildcard model starts.
    # Update context for wildcard phase
    context.context_data = {"character_state": updated_state.model_dump()}

    # Now invoke wildcard agent (still accept_fate=True for forced submission)
    # The agent will generate wildcard content and submit it
    wildcard_agent = get_wizard_agent(context)
    result = await wildcard_agent.run(
        "Traits confirmed. Now introduce the wildcard trait phase.",
        deps=context,
        message_history=message_history,
        model=model,
        model_settings=model_settings,
    )
    record_pydantic_ai_result(
        result,
        provider=provider_name,
        model=model_name,
        seat="wizard_wildcard",
        model_settings=model_settings,
        slot=slot,
        run_id=thread_id,
    )

    if context.last_tool_result:
        # Add note about traits being auto-confirmed
        context.last_tool_result["traits_auto_confirmed"] = True
        return context.last_tool_result

    if isinstance(result.output, DeferredToolRequests):
        raise HTTPException(
            status_code=500,
            detail="Wizard tool call completed without a response payload.",
        )

    # Shouldn't reach here with accept_fate (validator should force tool call)
    wizard_response = result.output
    client.add_message(thread_id, "assistant", wizard_response.message)
    return {
        "message": wizard_response.message,
        "choices": [c.strip() for c in wizard_response.choices if c.strip()],
        "phase_complete": False,
        "thread_id": thread_id,
        "traits_auto_confirmed": True,
        # _artifact_response compares these against the persisted draft, so the
        # committed trait state must travel with this response like every other
        # path through that gate.
        **context.cache.confirmation_metadata(),
    }


def _record_set_design(slot: int, expected_cache: Any, **drafts: Any) -> Any:
    """Do not attach a delayed location design to a changed setup."""
    with guarded_wizard_write(slot_dbname(slot), expected_cache):
        record_drafts(slot, **drafts)
        return read_cache(slot_dbname(slot))


def _artifact_response(result: dict, slot: int, thread_id: str) -> dict:
    """Do not pair an old artifact with a newer draft's confirmation token."""
    dbname = slot_dbname(slot)
    cache = read_cache(dbname)
    if (
        cache is None
        or cache.thread_id != thread_id
        or result.get("thread_id") != thread_id
    ):
        raise HTTPException(status_code=409, detail="The wizard session changed.")
    if cache.confirmation_metadata() != {
        key: result.get(key) for key in cache.confirmation_metadata()
    }:
        raise HTTPException(
            status_code=409,
            detail="This artifact changed before its response arrived. Resume to review the current draft.",
        )
    with guarded_wizard_write(dbname, cache):
        write_wizard_choices(
            result.get("choices", []), dbname, expected_thread_id=thread_id
        )
    return result


@router.post("/chat")
async def new_story_chat_endpoint(request: ChatRequest):
    """Handle chat for new story wizard with tool calling."""
    require_writable_slot(request.slot)
    try:
        from nexus.api.slot_state import get_slot_state

        state = get_slot_state(request.slot)
        if not state.is_wizard_mode:
            raise HTTPException(
                status_code=400,
                detail="Slot is not in wizard mode. Use /api/narrative/continue for narrative mode.",
            )
        if state.wizard_state is None:
            raise HTTPException(
                status_code=400,
                detail="No wizard state found. Initialize with /api/story/new/setup first.",
            )

        if request.thread_id is None:
            request.thread_id = state.wizard_state.thread_id
        if request.current_phase is None:
            request.current_phase = state.wizard_state.phase

        state_phase = state.wizard_state.phase
        if (
            request.thread_id != state.wizard_state.thread_id
            or request.current_phase != state_phase
        ):
            raise HTTPException(
                status_code=409,
                detail="The wizard phase or conversation changed. Resume before continuing.",
            )
        persisted_cache = read_cache(slot_dbname(request.slot))
        if persisted_cache and persisted_cache.character_revision_pending:
            if request.trait_choice is not None or request.accept_fate:
                raise HTTPException(
                    status_code=409,
                    detail="Describe the character revision before continuing.",
                )
        elif persisted_cache and persisted_cache.pending_confirmation() == "character":
            raise HTTPException(
                status_code=409,
                detail="Confirm or revise the completed character before continuing.",
            )
        replaces_claim = _reconcile_introduction(
            persisted_cache,
            request.message_origin,
            slot=request.slot,
            request_model=request.model,
            slot_model=state.model,
        )
        introduction = _is_introduction(persisted_cache, request.message_origin)
        state_subphase = _wizard_subphase_for_state(
            state_phase,
            has_concept=state.wizard_state.has_concept,
            has_traits=state.wizard_state.has_traits,
            has_wildcard=state.wizard_state.has_wildcard,
        )

        if request.trait_choice is not None and not (
            state_phase == "character" and state_subphase == "traits"
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "trait_choice is only valid during phase 'character', "
                    "subphase 'traits'; current wizard state is phase "
                    f"'{state_phase}', subphase '{state_subphase}'. Send a "
                    "non-empty message to continue the current wizard step."
                ),
            )

        # Handle trait toggle/confirm operations (no LLM call needed)
        if request.trait_choice is not None:
            from nexus.api.new_story_cache import (
                confirm_trait_selection,
                get_selected_trait_count,
                get_trait_menu,
                toggle_trait,
            )

            dbname = slot_dbname(request.slot)
            cache = read_cache(dbname)

            if (
                cache
                and cache.character.has_concept()
                and not cache.character.has_traits()
                and not cache.character_revision_pending
                and cache.thread_id == request.thread_id
                and cache.current_phase() == "character"
            ):
                with guarded_wizard_write(dbname, cache):
                    if request.trait_choice == 0:
                        selected_count = get_selected_trait_count(dbname)
                        if selected_count != 3:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Must select exactly 3 traits. Currently: {selected_count}",
                            )
                        confirm_trait_selection(dbname)
                        return {
                            "message": "Traits confirmed. Moving to wildcard definition.",
                            "phase": "character",
                            "subphase": "wildcard",
                            "subphase_complete": True,
                        }
                    if 1 <= request.trait_choice <= 10:
                        trait_menu = get_trait_menu(dbname)
                        trait = trait_menu[request.trait_choice - 1]
                        toggle_trait(dbname, trait.name)

                        trait_menu = get_trait_menu(dbname)
                        selected_count = get_selected_trait_count(dbname)

                        return {
                            "message": "",
                            "phase": "character",
                            "subphase": "traits",
                            "trait_menu": [
                                {
                                    "id": t.id,
                                    "name": t.name,
                                    "description": t.description,
                                    "is_selected": t.is_selected,
                                    "rationale": t.rationale,
                                }
                                for t in trait_menu
                            ],
                            "can_confirm": selected_count == 3,
                        }
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Invalid trait_choice: {request.trait_choice}. Must be 0-10."
                        ),
                    )

            raise HTTPException(
                status_code=409,
                detail=(
                    "trait_choice could not be applied because wizard state changed; "
                    f"last observed phase was '{state_phase}', subphase "
                    f"'{state_subphase}'. Reload the wizard state before retrying."
                ),
            )

        request.context_data = _hydrate_character_context(request)

        dev_mode = request.dev
        if request.message:
            stripped = request.message.lstrip()
            if stripped.startswith("--dev"):
                dev_mode = True
                stripped = stripped[len("--dev") :].lstrip()
                request.message = stripped

        if dev_mode and request.accept_fate:
            raise HTTPException(
                status_code=400,
                detail="Dev mode cannot be used with accept_fate.",
            )

        if dev_mode and not request.message.strip():
            raise HTTPException(
                status_code=400,
                detail="Dev mode requires a non-empty message.",
            )

        history_limit = get_wizard_history_limit()

        slot_model = state.model
        selected_model = resolve_wizard_model(request.model, slot_model)

        if wizard_model_lock_candidate(request.model, slot_model):
            history_client = ConversationsClient(model=slot_model)
            history = history_client.list_messages(
                request.thread_id, limit=history_limit
            )
            if any(msg["role"] == "user" for msg in history):
                logger.info(
                    "Wizard model lock active: slot=%s thread=%s current=%s requested=%s",
                    request.slot,
                    request.thread_id,
                    slot_model,
                    request.model,
                )
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Wizard model is locked after the first user message; "
                        "start a new setup to switch models."
                    ),
                )

        if request.model:
            # Moves the thread when the new provider uses another store, and
            # saves the model and thread ID together before any read below.
            request.thread_id = switch_wizard_model(
                request.slot,
                thread_id=request.thread_id,
                slot_model=slot_model,
                model=request.model,
            )
            logger.info("Persisted model %s to slot %s", request.model, request.slot)

        client = ConversationsClient(model=selected_model)

        doc = frontmatter.loads(load(PromptId.STORYTELLER_NEW))
        welcome_message = doc.get("welcome_message", "")

        history = client.list_messages(request.thread_id, limit=history_limit)
        if len(history) == 0 and welcome_message:
            client.add_message(request.thread_id, "assistant", welcome_message)
            history = client.list_messages(request.thread_id, limit=history_limit)

        if not request.accept_fate:
            client.add_message(
                request.thread_id,
                "user",
                request.message,
                origin=request.message_origin,
            )

        history = client.list_messages(request.thread_id, limit=history_limit)
        history.reverse()
        history_len = len(history)
        user_turns = sum(1 for msg in history if msg.get("role") == "user")
        assistant_turns = sum(1 for msg in history if msg.get("role") == "assistant")

        context = WizardContext.from_request(
            slot=request.slot,
            phase=request.current_phase,
            thread_id=request.thread_id,
            model=selected_model,
            context_data=request.context_data,
            accept_fate=request.accept_fate,
            dev_mode=dev_mode,
            history_len=history_len,
            user_turns=user_turns,
            assistant_turns=assistant_turns,
        )

        message_history = build_message_history(history)
        model, provider_name = build_pydantic_ai_model_with_provider(selected_model)
        model_settings = ModelSettings(max_tokens=get_wizard_max_tokens())

        if dev_mode:
            result = await wizard_debug_agent.run(
                None,
                deps=context,
                message_history=message_history,
                model=model,
                model_settings=model_settings,
            )
            record_pydantic_ai_result(
                result,
                provider=provider_name,
                model=selected_model,
                seat="wizard_debug",
                model_settings=model_settings,
                slot=request.slot,
                run_id=request.thread_id,
            )
            content = result.output
            client.add_message(request.thread_id, "assistant", content)
            write_wizard_choices(
                [], slot_dbname(request.slot), expected_thread_id=request.thread_id
            )
            return {
                "message": content,
                "choices": [],
                "phase_complete": False,
                "thread_id": request.thread_id,
                "dev_mode": True,
            }

        # =================================================================
        # Deterministic traits + auto-advance to wildcard
        # =================================================================
        # When accept_fate is active during traits subphase, commit the
        # suggested traits deterministically (no LLM needed for copy-paste)
        # then immediately invoke the wildcard phase.
        traits_result = await _handle_accept_fate_traits(
            context=context,
            accept_fate=request.accept_fate,
            current_phase=request.current_phase,
            slot=request.slot,
            message_history=message_history,
            model=model,
            model_name=selected_model,
            provider_name=provider_name,
            model_settings=model_settings,
            client=client,
            thread_id=request.thread_id,
        )
        if traits_result is not None:
            return _artifact_response(traits_result, request.slot, request.thread_id)

        # =================================================================
        # Standard wizard agent flow
        # =================================================================
        user_prompt = (
            _accept_fate_prompt(request.message) if request.accept_fate else None
        )
        agent = get_wizard_agent(context)
        result = await agent.run(
            user_prompt,
            deps=context,
            message_history=message_history,
            model=model,
            model_settings=model_settings,
        )
        record_pydantic_ai_result(
            result,
            provider=provider_name,
            model=selected_model,
            seat="wizard",
            model_settings=model_settings,
            slot=request.slot,
            run_id=request.thread_id,
        )

        if context.last_tool_result:
            # =================================================================
            # Phase 2: Set Designer (for seed submissions only)
            # =================================================================
            # When the seed tool signals requires_set_design, invoke the set
            # designer to translate the location_sketch into structured data.
            if context.last_tool_result.get("requires_set_design"):
                tool_data = context.last_tool_result.get("data", {})
                location_sketch = context.last_tool_result.get("location_sketch", "")
                seed_data = tool_data.get("seed", {})

                # Get setting from cache
                cache = context.persisted_tool_cache
                if cache and cache.setting_complete() and seed_data:
                    setting = SettingCard(**cache.get_setting_dict())
                    seed = StorySeed(**seed_data)

                    # TEST provider: use pre-computed location data from the
                    # mock database
                    if load_settings().is_test_model(selected_model):
                        logger.info(
                            "TEST mode: Using mock location data for slot %s",
                            request.slot,
                        )
                        from nexus.api.mock_openai import query_wizard_cache

                        mock_cache = query_wizard_cache()
                        layer_data = {
                            "name": mock_cache.get("layer_name"),
                            "type": mock_cache.get("layer_type"),
                            "description": mock_cache.get("layer_description"),
                        }
                        zone_data = {
                            "name": mock_cache.get("zone_name"),
                            "summary": mock_cache.get("zone_summary"),
                        }
                        location_data = mock_cache.get("initial_location") or {}

                        persisted_design = _record_set_design(
                            request.slot,
                            cache,
                            layer=layer_data,
                            zone=zone_data,
                            location=location_data,
                        )
                        context.last_tool_result.update(
                            persisted_design.confirmation_metadata()
                        )
                        context.last_tool_result["phase_complete"] = True
                        context.last_tool_result["set_design"] = {
                            "layer": layer_data,
                            "zone": zone_data,
                            "location": location_data,
                        }
                        logger.info(
                            "TEST mode set design complete: %s -> %s -> %s",
                            layer_data.get("name"),
                            zone_data.get("name"),
                            location_data.get("name"),
                        )
                    else:
                        # Production: Call set designer to generate location data
                        logger.info("Running set designer for slot %s", request.slot)
                        # selected_model, not request.model: the request
                        # may omit the model (it is persisted on the slot),
                        # and the effective model is locked after the first
                        # user message regardless of provider.
                        layer, zone, place = await generate_set_design(
                            location_sketch=location_sketch,
                            setting=setting,
                            seed=seed,
                            model=selected_model,
                        )

                        # Record the generated location data
                        persisted_design = _record_set_design(
                            request.slot,
                            cache,
                            layer=layer.model_dump(),
                            zone=zone.model_dump(),
                            location=place.model_dump(),
                        )
                        context.last_tool_result.update(
                            persisted_design.confirmation_metadata()
                        )

                        # Update the result to indicate full completion
                        context.last_tool_result["phase_complete"] = True
                        context.last_tool_result["set_design"] = {
                            "layer": layer.model_dump(),
                            "zone": zone.model_dump(),
                            "location": place.model_dump(),
                        }
                        logger.info(
                            "Set designer complete: %s -> %s -> %s",
                            layer.name,
                            zone.name,
                            place.name,
                        )

            return _artifact_response(
                context.last_tool_result, request.slot, request.thread_id
            )
        if isinstance(result.output, DeferredToolRequests):
            raise HTTPException(
                status_code=500,
                detail="Wizard tool call completed without a response payload.",
            )

        wizard_response = result.output

        def prepare_choices_for_ui(raw_choices: List[str]) -> List[str]:
            return [c.strip() for c in raw_choices if isinstance(c, str) and c.strip()]

        ui_choices = prepare_choices_for_ui(wizard_response.choices)
        logger.info(
            "Wizard response: message_len=%d choices=%s",
            len(wizard_response.message or ""),
            ui_choices,
        )
        _record_text_reply(
            client,
            slot=request.slot,
            thread_id=request.thread_id,
            message=wizard_response.message,
            choices=ui_choices,
            introduction=introduction,
            replaces_claim=replaces_claim,
        )

        return {
            "message": wizard_response.message,
            "choices": ui_choices,
            "phase_complete": False,
            "thread_id": request.thread_id,
        }

    except HTTPException:
        raise
    except WizardStateConflict as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        logger.exception("Error in chat endpoint: %s", e)
        detail = f"{e} (cause: {e.__cause__})" if e.__cause__ is not None else str(e)
        raise HTTPException(status_code=500, detail=detail)


def _record_weird_level(
    dbname: str, cache: WizardCache, level: WeirdLevel
) -> WizardCache:
    """Persist a strangeness selection on the wizard the caller read.

    Raises:
        HTTPException: 409 when the wizard changed after ``cache`` was read.
    """
    try:
        with guarded_wizard_write(dbname, cache):
            write_weird_level(dbname, level)
    except WizardStateConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return replace(cache, weird_level=level)


@router.put("/weird")
def record_weird_level_endpoint(request: WeirdLevelRequest) -> Dict[str, Any]:
    """Record the player's genesis strangeness for the story's transition.

    The level is player consent and calibration, not a promise of bizarre
    content: Retrograde maps it onto the story genre's configured band.
    """
    require_writable_slot(request.slot)
    dbname = slot_dbname(request.slot)
    cache = read_cache(dbname)
    if cache is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active setup found for slot {request.slot}",
        )
    recorded = _record_weird_level(dbname, cache, request.weird_level)
    return {
        "status": "recorded",
        "slot": request.slot,
        "weird_level": recorded.weird_level,
    }


@router.post("/transition", response_model=TransitionResponse)
async def transition_to_narrative_endpoint(request: TransitionRequest):
    """
    Transition from wizard setup to narrative mode.

    Reads from assets.new_story_creator cache, validates completeness,
    and calls perform_transition() to populate public schema atomically.

    This is the final step that:
    1. Moves all wizard data to the game database
    2. Creates the character, location hierarchy
    3. Sets new_story=false to enable narrative mode
    4. Clears the setup cache
    """
    require_writable_slot(request.slot)
    dbname = slot_dbname(request.slot)

    # Read the setup cache
    cache = read_cache(dbname)
    if not cache:
        raise HTTPException(
            status_code=400,
            detail=f"No setup data found for slot {request.slot}. Complete the wizard first.",
        )

    if cache.character_revision_pending:
        raise HTTPException(
            status_code=409,
            detail="Finish the character revision before starting the story.",
        )

    if not cache.setting_confirmed or not cache.character_confirmed:
        raise HTTPException(
            status_code=409,
            detail="Confirm the setting and character before starting the story.",
        )

    # Validate all phases are complete
    if not cache.setting_complete():
        raise HTTPException(
            status_code=422, detail="Incomplete setup data. Missing: setting"
        )
    if not cache.character_complete():
        raise HTTPException(
            status_code=422, detail="Incomplete setup data. Missing: character"
        )
    if not cache.seed_complete():
        raise HTTPException(
            status_code=422, detail="Incomplete setup data. Missing: seed"
        )
    if cache.base_timestamp is None:
        raise HTTPException(
            status_code=422,
            detail="Incomplete setup data. Missing: base_timestamp",
        )
    if not cache.get_layer_dict():
        raise HTTPException(
            status_code=422, detail="Incomplete setup data. Missing: layer"
        )
    if not cache.get_zone_dict():
        raise HTTPException(
            status_code=422, detail="Incomplete setup data. Missing: zone"
        )
    if not cache.get_initial_location():
        raise HTTPException(
            status_code=422, detail="Incomplete setup data. Missing: initial_location"
        )

    # A supplied strangeness is persisted first, so a retry after a failed
    # transition runs with the same level; the stored selection applies
    # otherwise (None resolves to the configured default in Retrograde).
    if request.weird_level is not None:
        cache = _record_weird_level(dbname, cache, request.weird_level)

    # Build TransitionData from cache
    try:
        transition_data = build_transition_data_from_cache(cache)
    except ValidationError as e:
        # Fail loudly per user directive
        logger.error(f"Validation error building TransitionData: {e}")
        raise HTTPException(
            status_code=422, detail=f"Setup data validation failed: {e.errors()}"
        )

    # Perform atomic transition with Retrograde cold-start history. The
    # frontier generation takes minutes, so it runs in a worker thread to
    # keep the event loop (and the progress endpoint) responsive.
    try:
        result = await asyncio.to_thread(
            perform_transition_with_retrograde,
            request.slot,
            transition_data,
            weird_level=cache.weird_level,
        )
        logger.info(
            "Transition complete for slot %s: character_id=%s retrograde=%s",
            request.slot,
            result["character_id"],
            result.get("retrograde", {}).get("enabled"),
        )

        return TransitionResponse(
            status="transitioned",
            character_id=result["character_id"],
            place_id=result["place_id"],
            layer_id=result["layer_id"],
            zone_id=result["zone_id"],
            message=f"Welcome to {transition_data.setting.world_name}. Your story begins.",
            retrograde=result.get("retrograde"),
            trait_inputs=result.get("trait_inputs"),
        )
    except ValueError as e:
        # Includes RetrogradePersistenceBlockedError: the transaction rolled
        # back, the wizard cache is intact, and the transition is retryable.
        logger.error(f"Transition validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Transition failed: {e}")
        raise HTTPException(status_code=500, detail=f"Transition failed: {str(e)}")


@router.get("/retrograde/status")
async def retrograde_status_endpoint(slot: int) -> Dict[str, Any]:
    """
    Report wizard-time Retrograde progress for a slot.

    Stages: packet -> seed_candidates -> expansion -> persistence ->
    embedding -> done (or failed). ``run`` identifies the transition run that
    owns the record; it is null, with stage "idle", when no run has started
    for the slot. The record lives in genesis_runs and genesis_run_stages.
    Every answer also carries the configured ``status_poll_interval_seconds``,
    so a player-plane waiter paces its reads without the operator settings route.
    """
    from nexus.agents.orrery.retrograde_orchestrator import get_retrograde_progress

    poll_interval = get_retrograde_status_poll_interval_seconds()
    progress = await asyncio.to_thread(get_retrograde_progress, slot)
    if progress is None:
        progress = {
            "slot": slot,
            "run": None,
            "run_status": None,
            "error": None,
            "stage": "idle",
            "stages": [],
        }
    return {**progress, "status_poll_interval_seconds": poll_interval}
