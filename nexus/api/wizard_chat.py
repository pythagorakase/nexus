"""
FastAPI endpoints for the new story wizard chat functionality.

This module handles the conversational wizard that guides users through
story creation, including:
- Chat interactions with phase-specific tool calls
- Character creation sub-phases (concept, traits, wildcard)
- Transition from wizard to narrative mode
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import frontmatter
from pydantic import ValidationError
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import DeferredToolRequests

from nexus.api.conversations import ConversationsClient
from nexus.api.config_utils import (
    get_new_story_model,
    get_wizard_history_limit,
    get_wizard_max_tokens,
    get_wizard_streaming_enabled,
)
from nexus.api.narrative_schemas import (
    ChatRequest,
    TransitionRequest,
    TransitionResponse,
)
from nexus.api.new_story_cache import read_cache, write_wizard_choices
from nexus.api.new_story_db_mapper import NewStoryDatabaseMapper
from nexus.api.new_story_schemas import (
    SettingCard,
    CharacterSheet,
    StorySeed,
    LayerDefinition,
    ZoneDefinition,
    PlaceProfile,
    CharacterCreationState,
    TransitionData,
    WizardResponse,
)
from nexus.api.pydantic_ai_utils import build_message_history, build_pydantic_ai_model
from nexus.api.slot_utils import slot_dbname
from nexus.api.wizard_agent import WizardContext, wizard_agent, wizard_debug_agent

logger = logging.getLogger("nexus.api.wizard_chat")

router = APIRouter(prefix="/api/story/new", tags=["wizard"])


def _hydrate_character_context(request: ChatRequest) -> Optional[Dict[str, Any]]:
    """Load character_state from cache if in character phase and no context provided."""
    if request.current_phase != "character" or request.context_data is not None:
        return request.context_data

    cache = read_cache(slot_dbname(request.slot))
    if not cache:
        return None

    char_state: Dict[str, Any] = {}
    if cache.character.has_concept():
        selected = [st.trait for st in cache.character.suggested_traits]
        rationales = {
            st.trait: st.rationale for st in cache.character.suggested_traits
        }
        char_state["concept"] = {
            "name": cache.character.name,
            "archetype": cache.character.archetype,
            "background": cache.character.background,
            "appearance": cache.character.appearance,
            "suggested_traits": selected,
            "trait_rationales": rationales,
        }
    if cache.character.has_traits():
        selected = [st.trait for st in cache.character.suggested_traits]
        rationales = {
            st.trait: st.rationale for st in cache.character.suggested_traits
        }
        char_state["trait_selection"] = {
            "selected_traits": selected,
            "trait_rationales": rationales,
        }
    if cache.character.has_wildcard():
        char_state["wildcard"] = {
            "wildcard_name": cache.character.wildcard_name,
            "wildcard_description": cache.character.wildcard_rationale,
        }

    if char_state:
        return {"character_state": char_state}
    return None


@router.post("/chat")
async def new_story_chat_endpoint(request: ChatRequest):
    """Handle chat for new story wizard with tool calling."""
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

        request.context_data = _hydrate_character_context(request)

        # Handle trait toggle/confirm operations (no LLM call needed)
        if request.trait_choice is not None and request.current_phase == "character":
            from nexus.api.new_story_cache import (
                confirm_trait_selection,
                get_selected_trait_count,
                get_trait_menu,
                toggle_trait,
            )

            dbname = slot_dbname(request.slot)
            cache = read_cache(dbname)

            if cache and cache.character.has_concept() and not cache.character.has_traits():
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
        selected_model = request.model or slot_model or get_new_story_model()

        if request.model and slot_model and request.model != slot_model:
            history_client = ConversationsClient(model=slot_model)
            history = history_client.list_messages(request.thread_id, limit=history_limit)
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
            from nexus.api.save_slots import upsert_slot

            upsert_slot(
                request.slot, model=request.model, dbname=slot_dbname(request.slot)
            )
            logger.info("Persisted model %s to slot %s", request.model, request.slot)

        client = ConversationsClient(model=selected_model)

        prompt_path = (
            Path(__file__).parent.parent.parent / "prompts" / "storyteller_new.md"
        )
        with prompt_path.open() as handle:
            doc = frontmatter.load(handle)
            welcome_message = doc.get("welcome_message", "")

        history = client.list_messages(request.thread_id, limit=history_limit)
        if len(history) == 0 and welcome_message:
            client.add_message(request.thread_id, "assistant", welcome_message)
            history = client.list_messages(request.thread_id, limit=history_limit)

        if not request.accept_fate:
            client.add_message(request.thread_id, "user", request.message)

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
        model = build_pydantic_ai_model(selected_model)
        model_settings = ModelSettings(max_tokens=get_wizard_max_tokens())

        if dev_mode:
            result = await wizard_debug_agent.run(
                None,
                deps=context,
                message_history=message_history,
                model=model,
                model_settings=model_settings,
            )
            content = result.output
            client.add_message(request.thread_id, "assistant", content)
            return {
                "message": content,
                "choices": [],
                "phase_complete": False,
                "thread_id": request.thread_id,
                "dev_mode": True,
            }

        result = await wizard_agent.run(
            None,
            deps=context,
            message_history=message_history,
            model=model,
            model_settings=model_settings,
        )

        if context.last_tool_result:
            return context.last_tool_result
        if isinstance(result.output, DeferredToolRequests):
            raise HTTPException(
                status_code=500,
                detail="Wizard tool call completed without a response payload.",
            )

        wizard_response = result.output

        def prepare_choices_for_ui(raw_choices: List[str]) -> List[str]:
            return [c.strip() for c in raw_choices if isinstance(c, str) and c.strip()]

        client.add_message(request.thread_id, "assistant", wizard_response.message)
        ui_choices = prepare_choices_for_ui(wizard_response.choices)
        logger.info(
            "Wizard response: message_len=%d choices=%s",
            len(wizard_response.message or ""),
            ui_choices,
        )

        if ui_choices:
            write_wizard_choices(ui_choices, slot_dbname(request.slot))

        return {
            "message": wizard_response.message,
            "choices": ui_choices,
            "phase_complete": False,
            "thread_id": request.thread_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in chat endpoint: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def new_story_chat_stream_endpoint(request: ChatRequest):
    """Stream wizard responses for progressive UI updates."""
    if not get_wizard_streaming_enabled():
        raise HTTPException(status_code=404, detail="Wizard streaming is disabled.")
    if request.trait_choice is not None:
        raise HTTPException(
            status_code=400,
            detail="Trait selection actions are not supported on the streaming endpoint.",
        )

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
    selected_model = request.model or slot_model or get_new_story_model()

    if request.model and slot_model and request.model != slot_model:
        history_client = ConversationsClient(model=slot_model)
        history = history_client.list_messages(request.thread_id, limit=history_limit)
        if any(msg["role"] == "user" for msg in history):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Wizard model is locked after the first user message; "
                    "start a new setup to switch models."
                ),
            )

    if request.model:
        from nexus.api.save_slots import upsert_slot

        upsert_slot(request.slot, model=request.model, dbname=slot_dbname(request.slot))

    client = ConversationsClient(model=selected_model)
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / "storyteller_new.md"
    with prompt_path.open() as handle:
        doc = frontmatter.load(handle)
        welcome_message = doc.get("welcome_message", "")

    history = client.list_messages(request.thread_id, limit=history_limit)
    if len(history) == 0 and welcome_message:
        client.add_message(request.thread_id, "assistant", welcome_message)
        history = client.list_messages(request.thread_id, limit=history_limit)

    if not request.accept_fate:
        client.add_message(request.thread_id, "user", request.message)

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
    model = build_pydantic_ai_model(selected_model)
    model_settings = ModelSettings(max_tokens=get_wizard_max_tokens())

    async def event_stream():
        if dev_mode:
            result = await wizard_debug_agent.run(
                None,
                deps=context,
                message_history=message_history,
                model=model,
                model_settings=model_settings,
            )
            payload = {"type": "message", "message": result.output, "choices": []}
            yield json.dumps(payload) + "\n"
            client.add_message(request.thread_id, "assistant", result.output)
            return

        async for streamed_result in wizard_agent.run_stream(
            None,
            deps=context,
            message_history=message_history,
            model=model,
            model_settings=model_settings,
        ):
            async for output in streamed_result.stream_output():
                if isinstance(output, DeferredToolRequests):
                    continue
                if isinstance(output, WizardResponse):
                    yield json.dumps(
                        {
                            "type": "message",
                            "message": output.message,
                            "choices": output.choices,
                        }
                    ) + "\n"

            final_output = await streamed_result.get_output()
            if isinstance(final_output, DeferredToolRequests):
                payload = context.last_tool_result or {
                    "message": "Wizard tool call completed without a response payload.",
                    "phase_complete": False,
                }
                yield json.dumps({"type": "artifact", "data": payload}) + "\n"
                return

            client.add_message(request.thread_id, "assistant", final_output.message)
            ui_choices = [
                c.strip()
                for c in final_output.choices
                if isinstance(c, str) and c.strip()
            ]
            if ui_choices:
                write_wizard_choices(ui_choices, slot_dbname(request.slot))
            yield json.dumps(
                {"type": "final", "message": final_output.message, "choices": ui_choices}
            ) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


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
    dbname = slot_dbname(request.slot)

    # Read the setup cache
    cache = read_cache(dbname)
    if not cache:
        raise HTTPException(
            status_code=400,
            detail=f"No setup data found for slot {request.slot}. Complete the wizard first."
        )

    # Validate all phases are complete
    if not cache.setting_complete():
        raise HTTPException(
            status_code=422,
            detail="Incomplete setup data. Missing: setting"
        )
    if not cache.character_complete():
        raise HTTPException(
            status_code=422,
            detail="Incomplete setup data. Missing: character"
        )
    if not cache.seed_complete():
        raise HTTPException(
            status_code=422,
            detail="Incomplete setup data. Missing: seed"
        )
    if not cache.get_layer_dict():
        raise HTTPException(
            status_code=422,
            detail="Incomplete setup data. Missing: layer"
        )
    if not cache.get_zone_dict():
        raise HTTPException(
            status_code=422,
            detail="Incomplete setup data. Missing: zone"
        )
    if not cache.get_initial_location():
        raise HTTPException(
            status_code=422,
            detail="Incomplete setup data. Missing: initial_location"
        )

    # Build TransitionData from cache
    try:
        # Get base_timestamp from cache
        base_timestamp = cache.base_timestamp or datetime.now(timezone.utc)

        # Get character dict and assemble CharacterSheet from CharacterCreationState
        char_draft = cache.get_character_dict()
        state = CharacterCreationState(**char_draft)
        char_sheet = state.to_character_sheet().model_dump()

        transition_data = TransitionData(
            setting=SettingCard(**cache.get_setting_dict()),
            character=CharacterSheet(**char_sheet),
            seed=StorySeed(**cache.get_seed_dict()),
            layer=LayerDefinition(**cache.get_layer_dict()),
            zone=ZoneDefinition(**cache.get_zone_dict()),
            location=PlaceProfile(**cache.get_initial_location()),
            base_timestamp=base_timestamp,
            thread_id=cache.thread_id or "",
        )
    except ValidationError as e:
        # Fail loudly per user directive
        logger.error(f"Validation error building TransitionData: {e}")
        raise HTTPException(
            status_code=422,
            detail=f"Setup data validation failed: {e.errors()}"
        )

    # Perform atomic transition
    mapper = NewStoryDatabaseMapper(dbname=dbname)
    try:
        result = mapper.perform_transition(transition_data)
        logger.info(f"Transition complete for slot {request.slot}: {result}")

        return TransitionResponse(
            status="transitioned",
            character_id=result["character_id"],
            place_id=result["place_id"],
            layer_id=result["layer_id"],
            zone_id=result["zone_id"],
            message=f"Welcome to {transition_data.setting.world_name}. Your story begins."
        )
    except ValueError as e:
        logger.error(f"Transition validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Transition failed: {e}")
        raise HTTPException(status_code=500, detail=f"Transition failed: {str(e)}")
