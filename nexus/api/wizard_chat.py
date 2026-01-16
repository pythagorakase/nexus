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
from typing import Dict, Any, Optional, List

import frontmatter
import openai
from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from nexus.api.conversations import ConversationsClient
from nexus.api.narrative_schemas import (
    ChatRequest,
    TransitionRequest,
    TransitionResponse,
)
from nexus.api.new_story_cache import read_cache
from nexus.api.new_story_db_mapper import NewStoryDatabaseMapper
from nexus.api.new_story_flow import record_drafts
from nexus.api.new_story_schemas import (
    SettingCard,
    CharacterSheet,
    StorySeed,
    LayerDefinition,
    ZoneDefinition,
    PlaceProfile,
    StartingScenario,
    CharacterConcept,
    TraitSelection,
    WildcardTrait,
    CharacterCreationState,
    TransitionData,
    WizardResponse,
    make_openai_strict_schema,
)
from nexus.api.slot_utils import slot_dbname
from nexus.config import load_settings_as_dict

logger = logging.getLogger("nexus.api.wizard_chat")

router = APIRouter(prefix="/api/story/new", tags=["wizard"])


def load_settings() -> dict:
    """Load settings from config."""
    return load_settings_as_dict()


def get_new_story_model() -> str:
    """Get the configured model for new story workflow."""
    settings = load_settings()
    return settings.get("API Settings", {}).get("new_story", {}).get("model", "gpt-5.1")


def get_base_url_for_model(model: str) -> Optional[str]:
    """Get API base URL based on model selection.

    Args:
        model: Model identifier (gpt-5.1, TEST, claude)

    Returns:
        Base URL for the model's API, or None to use default OpenAI
    """
    if model == "TEST":
        settings = load_settings()
        return settings.get("global", {}).get("api", {}).get(
            "test_mock_server_url", "http://localhost:5102/v1"
        )
    # Future: route Claude models to Anthropic API
    return None  # Use default OpenAI


def validate_subphase_tool(function_name: str, arguments: dict) -> dict:
    """Validate subphase tool arguments against Pydantic schemas.

    This ensures required fields (like trait_rationales) are present.
    Returns validated and normalized data, or raises HTTPException on failure.
    """
    schema_map = {
        "submit_character_concept": CharacterConcept,
        "submit_trait_selection": TraitSelection,
        "submit_wildcard_trait": WildcardTrait,
    }
    if schema := schema_map.get(function_name):
        try:
            return schema.model_validate(arguments).model_dump()
        except Exception as e:
            logger.error(f"{schema.__name__} validation failed: {e}")
            raise HTTPException(
                status_code=422,
                detail=f"LLM returned invalid {schema.__name__}: {str(e)}",
            )
    return arguments


@router.post("/chat")
async def new_story_chat_endpoint(request: ChatRequest):
    """Handle chat for new story wizard with tool calling"""
    try:
        from scripts.api_openai import OpenAIProvider

        # Resolve thread_id and current_phase from slot state if not provided
        if request.thread_id is None or request.current_phase is None:
            from nexus.api.slot_state import get_slot_state

            state = get_slot_state(request.slot)
            if not state.is_wizard_mode:
                raise HTTPException(
                    status_code=400,
                    detail="Slot is not in wizard mode. Use /api/narrative/continue for narrative mode."
                )
            if state.wizard_state is None:
                raise HTTPException(
                    status_code=400,
                    detail="No wizard state found. Initialize with /api/story/new/setup first."
                )

            if request.thread_id is None:
                request.thread_id = state.wizard_state.thread_id
            if request.current_phase is None:
                request.current_phase = state.wizard_state.phase

        # Load character_state from cache if in character phase (always, not just when resolving)
        if request.current_phase == "character" and request.context_data is None:
            cache = read_cache(slot_dbname(request.slot))
            if cache:
                # Build character_state from normalized columns
                char_state = {}
                if cache.character.has_concept():
                    # Build concept dict with trait data from assets.traits
                    selected = [st.trait for st in cache.character.suggested_traits]
                    rationales = {st.trait: st.rationale for st in cache.character.suggested_traits}
                    concept_dict = {
                        "name": cache.character.name,
                        "archetype": cache.character.archetype,
                        "background": cache.character.background,
                        "appearance": cache.character.appearance,
                        # Always include traits (may be empty during early subphases)
                        "suggested_traits": selected,
                        "trait_rationales": rationales,
                    }
                    char_state["concept"] = concept_dict
                if cache.character.has_traits():
                    selected = [st.trait for st in cache.character.suggested_traits]
                    rationales = {st.trait: st.rationale for st in cache.character.suggested_traits}
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
                    request.context_data = {"character_state": char_state}

        # Handle trait toggle/confirm operations (no LLM call needed)
        if request.trait_choice is not None and request.current_phase == "character":
            from nexus.api.new_story_cache import (
                get_trait_menu,
                get_selected_trait_count,
                toggle_trait,
                confirm_trait_selection,
            )

            dbname = slot_dbname(request.slot)
            cache = read_cache(dbname)

            # Only handle if we're in traits subphase (has concept, not has_traits)
            if cache and cache.character.has_concept() and not cache.character.has_traits():
                if request.trait_choice == 0:
                    # Confirm selection - validate and advance to wildcard
                    selected_count = get_selected_trait_count(dbname)
                    if selected_count != 3:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Must select exactly 3 traits. Currently: {selected_count}"
                        )
                    confirm_trait_selection(dbname)
                    # Return success - CLI will request next phase
                    return {
                        "message": "Traits confirmed. Moving to wildcard definition.",
                        "phase": "character",
                        "subphase": "wildcard",
                        "subphase_complete": True,
                    }
                elif 1 <= request.trait_choice <= 10:
                    # Toggle trait by ID
                    trait_menu = get_trait_menu(dbname)
                    trait = trait_menu[request.trait_choice - 1]  # 0-indexed
                    toggle_trait(dbname, trait.name)

                    # Get updated menu
                    trait_menu = get_trait_menu(dbname)
                    selected_count = get_selected_trait_count(dbname)

                    return {
                        "message": "",  # No message needed for toggle
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
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid trait_choice: {request.trait_choice}. Must be 0-10."
                    )

        # Load settings for new story workflow
        settings_model = get_new_story_model()
        settings = load_settings()
        history_limit = (
            settings.get("API Settings", {})
            .get("new_story", {})
            .get("message_history_limit", 20)
        )

        # Use request model if specified (enables TEST mode), otherwise fall back to settings
        selected_model = request.model if request.model else settings_model

        # Persist model to save_slots if explicitly provided (so it persists for future requests)
        if request.model:
            from nexus.api.save_slots import upsert_slot
            upsert_slot(request.slot, model=request.model, dbname=slot_dbname(request.slot))
            logger.info("Persisted model %s to slot %s", request.model, request.slot)

        # Initialize client with user's selected model
        # TEST mode uses in-memory storage, avoiding 1Password biometric auth
        client = ConversationsClient(model=selected_model)

        # Load prompt and extract welcome message from frontmatter
        prompt_path = (
            Path(__file__).parent.parent.parent / "prompts" / "storyteller_new.md"
        )
        with prompt_path.open() as f:
            doc = frontmatter.load(f)
            system_prompt = doc.content  # The markdown content without frontmatter
            welcome_message = doc.get("welcome_message", "")

        # Conditionally append trait menu for character creation phase
        if request.current_phase == "character":
            trait_menu_path = (
                Path(__file__).parent.parent.parent / "docs" / "trait_menu.md"
            )
            if trait_menu_path.exists():
                trait_menu = trait_menu_path.read_text()
                system_prompt += f"\n\n---\n\n# Trait Reference\n\n{trait_menu}"

        # Check if this is the first message (thread is empty)
        # If so, prepend the welcome message as an assistant message
        history = client.list_messages(request.thread_id, limit=history_limit)

        # Log history state for debugging
        logger.debug(f"Thread {request.thread_id} history length: {len(history)}")

        if len(history) == 0 and welcome_message:
            # Thread is empty, prepend welcome message
            logger.debug(f"Prepending welcome message to thread {request.thread_id}")
            client.add_message(request.thread_id, "assistant", welcome_message)
            # Re-fetch history to include the new message
            history = client.list_messages(request.thread_id, limit=history_limit)
        # Add user message (skip when accept_fate to avoid polluting thread)
        if not request.accept_fate:
            client.add_message(request.thread_id, "user", request.message)

        # Define tools based on current phase
        tools = []
        primary_tool_name: Optional[str] = None
        if request.current_phase == "setting":
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "submit_world_document",
                        "description": "Submit the finalized world setting/genre document when the user agrees.",
                        "parameters": SettingCard.model_json_schema(),
                    },
                }
            )
            primary_tool_name = "submit_world_document"
        elif request.current_phase == "character":
            # Determine sub-phase based on character_state in context_data
            char_state = (request.context_data or {}).get("character_state", {})
            has_concept = char_state.get("concept") is not None
            has_traits = char_state.get("trait_selection") is not None
            has_wildcard = char_state.get("wildcard") is not None

            if not has_concept:
                # Sub-phase 1: Gather archetype, background, name, appearance
                tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_character_concept",
                            "strict": True,
                            "description": "Submit the character's core concept (archetype, background, name, appearance) when established.",
                            "parameters": make_openai_strict_schema(CharacterConcept.model_json_schema()),
                        },
                    }
                )
                primary_tool_name = "submit_character_concept"
            elif not has_traits:
                # Sub-phase 2: Select 3 traits from the 10 optional traits
                tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_trait_selection",
                            "strict": True,
                            "description": "Submit the 3 selected traits with rationales when the user confirms their choices.",
                            "parameters": make_openai_strict_schema(TraitSelection.model_json_schema()),
                        },
                    }
                )
                primary_tool_name = "submit_trait_selection"
            elif not has_wildcard:
                # Sub-phase 3: Define the custom wildcard trait
                tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_wildcard_trait",
                            "strict": True,
                            "description": "Submit the unique wildcard trait when defined.",
                            "parameters": make_openai_strict_schema(WildcardTrait.model_json_schema()),
                        },
                    }
                )
                primary_tool_name = "submit_wildcard_trait"
            # else: All sub-phases complete - character phase is done, no tool needed.
        elif request.current_phase == "seed":
            # Use unified StartingScenario model
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "submit_starting_scenario",
                        "strict": True,
                        "description": "Submit the chosen story seed and starting location details.",
                        "parameters": make_openai_strict_schema(StartingScenario.model_json_schema()),
                    },
                }
            )
            primary_tool_name = "submit_starting_scenario"

        # Fetch updated history (now includes welcome + user message if first interaction)
        # Note: list_messages returns newest first, so we reverse it
        history = client.list_messages(request.thread_id, limit=history_limit)
        history.reverse()

        # Construct dynamic system instruction
        phase_instruction = f"Current Phase: {request.current_phase.upper()}.\n"

        if request.current_phase == "character":
            phase_instruction += "The world setting is established. Do NOT ask about genre. Focus on creating the protagonist.\n"
            if request.context_data and "setting" in request.context_data:
                phase_instruction += f"\n[WORLD SUMMARY]\n{json.dumps(request.context_data['setting'], indent=2)}\n[/WORLD SUMMARY]\n"

        elif request.current_phase == "seed":
            phase_instruction += "World and Character are established. Focus on generating the starting scenario.\n"
            if request.context_data:
                if "setting" in request.context_data:
                    phase_instruction += f"\n[WORLD SUMMARY]\n{json.dumps(request.context_data['setting'], indent=2)}\n[/WORLD SUMMARY]\n"
                if "character" in request.context_data:
                    phase_instruction += f"\n[CHARACTER SHEET]\n{json.dumps(request.context_data['character'], indent=2)}\n[/CHARACTER SHEET]\n"

        phase_instruction += (
            "Use the available tool to submit the artifact when the user confirms."
        )

        structured_choices_instruction = (
            "Use tools for every reply. Call `respond_with_choices` to deliver your "
            "narrative message plus 2-4 actionable choice strings (no numbering/markdown). "
            "Call a submission tool only when you are ready to commit that artifact. "
            "Do not send freeform text outside tool calls. Do not repeat the choices inside "
            "your message body; keep options only in the choices array."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": phase_instruction},
            {"role": "system", "content": structured_choices_instruction},
        ] + history

        # selected_model already defined at top of function from request.model
        base_url = get_base_url_for_model(selected_model)

        # For TEST mode, use dummy API key to avoid 1Password biometric auth
        if selected_model == "TEST":
            client_kwargs = {"api_key": "test-dummy-key", "base_url": base_url}
            logger.info(f"TEST mode: routing to mock server at {base_url}")
        else:
            provider = OpenAIProvider(model=selected_model)
            client_kwargs = {"api_key": provider.api_key}
            if base_url:
                client_kwargs["base_url"] = base_url
                logger.info(f"Routing to: {base_url}")
        openai_client = openai.OpenAI(**client_kwargs)

        # Build WizardResponse schema for structured output
        wizard_schema = WizardResponse.model_json_schema()
        wizard_response_tool = {
            "type": "function",
            "function": {
                "name": "respond_with_choices",
                "strict": True,  # Enforce schema constraints including maxItems on choices
                "description": (
                    "Respond to the user with a narrative message and 2-4 short choice "
                    "strings (no numbering/markdown) to guide the next step. Do NOT list the "
                    "choices inside the message; only in the choices array."
                ),
                "parameters": wizard_schema,
            },
        }

        # Inject Accept Fate signal as system message if active
        if request.accept_fate:
            logger.info(f"Accept Fate active for phase {request.current_phase}")
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "[ACCEPT FATE ACTIVE] Follow the '### Accept Fate Protocol' in your instructions. "
                        "Make bold, concrete choices immediately."
                    ),
                }
            )

        # Build final toolset
        tools_for_llm = tools + [wizard_response_tool]
        tool_choice_mode: Any = "required"

        # Use Accept Fate to force artifact generation via the phase tool
        if request.accept_fate and primary_tool_name:
            logger.info(f"Forcing tool choice: {primary_tool_name}")
            tools_for_llm = tools
            tool_choice_mode = {
                "type": "function",
                "function": {"name": primary_tool_name},
            }

        # Use response_format to enforce structured WizardResponse on normal runs
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "wizard_response",
                "strict": True,
                "schema": wizard_schema,
            },
        }

        if request.accept_fate and primary_tool_name:
            response_format = None

        logger.info(f"Calling LLM with tool_choice_mode: {tool_choice_mode}")
        response = openai_client.chat.completions.create(
            model=selected_model,
            messages=messages,
            tools=tools_for_llm if tools_for_llm else None,
            tool_choice=tool_choice_mode,
            response_format=response_format,
        )

        message = response.choices[0].message
        tool_calls = message.tool_calls or []

        # Prioritize submission tools; fall back to structured response helper
        submission_call = next(
            (tc for tc in tool_calls if tc.function.name != "respond_with_choices"),
            None,
        )
        response_call = next(
            (tc for tc in tool_calls if tc.function.name == "respond_with_choices"),
            None,
        )

        def parse_tool_arguments(raw_args: str) -> Dict[str, Any]:
            try:
                return json.loads(raw_args)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse tool call arguments: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Invalid tool call arguments from LLM: {str(e)}",
                )

        # Handle artifact submissions
        if submission_call:
            function_name = submission_call.function.name
            arguments = parse_tool_arguments(submission_call.function.arguments)

            # Persist the artifact to the setup cache
            try:
                if function_name == "submit_world_document":
                    record_drafts(request.slot, setting=arguments)
                elif function_name == "submit_character_sheet":
                    record_drafts(request.slot, character=arguments)
                elif function_name == "submit_starting_scenario":
                    # The tool returns a composite object with seed, layer, zone, and location
                    record_drafts(
                        request.slot,
                        seed=arguments.get("seed"),
                        layer=arguments.get("layer"),
                        zone=arguments.get("zone"),
                        location=arguments.get("location"),
                    )
            except Exception as e:
                logger.error(f"Failed to persist artifact for {function_name}: {e}")

            # Determine if this completes the entire phase or just a sub-phase
            is_subphase_tool = function_name in [
                "submit_character_concept",
                "submit_trait_selection",
                "submit_wildcard_trait",
            ]

            # First validation: check individual sub-phase data against its Pydantic schema
            validated_data = validate_subphase_tool(function_name, arguments)

            # Track character creation progress and assemble final sheet when complete
            phase_complete = not is_subphase_tool
            response_data: Dict[str, Any] = validated_data

            if is_subphase_tool:
                # Merge the newly submitted sub-phase data with the accumulated state
                char_state_data = (request.context_data or {}).get("character_state", {})

                if function_name == "submit_character_concept":
                    char_state_updates = {"concept": validated_data}
                    # Persist suggested traits to ephemeral table
                    if "suggested_traits" in validated_data and "trait_rationales" in validated_data:
                        from nexus.api.new_story_cache import write_suggested_traits
                        suggestions = [
                            {"trait": trait, "rationale": validated_data["trait_rationales"].get(trait, "")}
                            for trait in validated_data["suggested_traits"]
                        ]
                        write_suggested_traits(slot_dbname(request.slot), suggestions)
                elif function_name == "submit_trait_selection":
                    char_state_updates = {"trait_selection": validated_data}
                    # Clear suggestions now that traits are selected
                    from nexus.api.new_story_cache import clear_suggested_traits
                    clear_suggested_traits(slot_dbname(request.slot))
                else:
                    char_state_updates = {"wildcard": validated_data}

                # Second validation: merge into accumulated state
                logger.debug("Merging char_state_data keys: %s", list(char_state_data.keys()))
                logger.debug("Merging char_state_updates keys: %s", list(char_state_updates.keys()))
                creation_state = CharacterCreationState.model_validate(
                    {**char_state_data, **char_state_updates}
                )

                response_data = {"character_state": creation_state.model_dump()}
                phase_complete = creation_state.is_complete()

                # Always save character state to cache (for CLI sub-phase continuity)
                record_drafts(request.slot, character=creation_state.model_dump())
                logger.debug("Saved character state to cache: %s", list(creation_state.model_dump().keys()))

                if phase_complete:
                    # Character sheet is built when all sub-phases are complete
                    logger.info("Character phase complete - building sheet")
                    character_sheet = creation_state.to_character_sheet().model_dump()
                    response_data.update({"character_sheet": character_sheet})
                    logger.info("Character sheet built successfully")

            # Return the structured data to frontend
            result = {
                "message": "Generating artifact...",
                "phase_complete": phase_complete,
                "subphase_complete": is_subphase_tool,
                "phase": request.current_phase,
                "artifact_type": function_name,
                "data": response_data,
            }

            # Add trait menu after concept submission (entering traits subphase)
            if function_name == "submit_character_concept":
                from nexus.api.new_story_cache import get_trait_menu, get_selected_trait_count
                dbname = slot_dbname(request.slot)
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

            return result

        # Handle structured conversational responses via helper tool
        def prepare_choices_for_ui(raw_choices: List[str]) -> List[str]:
            return [c.strip() for c in raw_choices if isinstance(c, str) and c.strip()]

        if response_call:
            try:
                wizard_response = WizardResponse.model_validate(
                    parse_tool_arguments(response_call.function.arguments)
                )
            except Exception as e:
                logger.error(f"Failed to parse respond_with_choices payload: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"LLM returned invalid WizardResponse via tool call: {str(e)}",
                )
            client.add_message(request.thread_id, "assistant", wizard_response.message)
            logger.info(
                "respond_with_choices: message_len=%d choices=%s",
                len(wizard_response.message or ""),
                prepare_choices_for_ui(wizard_response.choices),
            )

            return {
                "message": wizard_response.message,
                "choices": prepare_choices_for_ui(wizard_response.choices),
                "phase_complete": False,
                "thread_id": request.thread_id,
            }

        # Parse structured WizardResponse (guaranteed valid by response_format)
        try:
            wizard_response = WizardResponse.model_validate_json(message.content)
        except Exception as e:
            logger.error(f"Failed to parse WizardResponse: {e}")
            logger.error(f"Raw content: {message.content[:500] if message.content else 'None'}")
            raise HTTPException(
                status_code=500,
                detail=f"LLM returned invalid WizardResponse: {str(e)}",
            )

        # Save assistant message to thread (just the narrative text, not JSON)
        client.add_message(request.thread_id, "assistant", wizard_response.message)
        logger.info(
            "respond_with_choices (content path): message_len=%d choices=%s",
            len(wizard_response.message or ""),
            prepare_choices_for_ui(wizard_response.choices),
        )

        return {
            "message": wizard_response.message,
            "choices": prepare_choices_for_ui(wizard_response.choices),
            "phase_complete": False,
            "thread_id": request.thread_id,
        }

    except HTTPException:
        # Preserve explicit HTTP errors such as validation failures
        raise
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
