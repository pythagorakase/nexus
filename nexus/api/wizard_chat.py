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
from nexus.api.new_story_cache import read_cache, write_wizard_choices
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
    CharacterConceptSubmission,
    TraitSelection,
    WildcardTrait,
    CharacterCreationState,
    TransitionData,
    WizardResponse,
    make_openai_strict_schema,
)
from nexus.api.slot_utils import slot_dbname
from nexus.api.config_utils import get_new_story_model
from nexus.api.structured_output import STRUCTURED_OUTPUT_BETA, make_anthropic_schema
from nexus.config.loader import get_provider_for_model
from nexus.config import load_settings_as_dict

logger = logging.getLogger("nexus.api.wizard_chat")

router = APIRouter(prefix="/api/story/new", tags=["wizard"])



def load_settings() -> dict:
    """Load settings from config."""
    return load_settings_as_dict()


def get_base_url_for_model(model: str) -> Optional[str]:
    """Get API base URL based on model's provider.

    Uses the provider lookup from nexus.toml api_models configuration
    to determine which API backend to use.

    Args:
        model: Model identifier (e.g., gpt-5.2, TEST, claude)

    Returns:
        Base URL for the model's API, or None to use default OpenAI
    """
    provider = get_provider_for_model(model)

    if provider == "test":
        settings = load_settings()
        return settings.get("global", {}).get("api", {}).get(
            "test_mock_server_url", "http://localhost:5102/v1"
        )
    elif provider == "anthropic":
        # Anthropic uses different client, not just URL change
        # For now, return None - full Anthropic support requires client changes
        return None

    # Default: OpenAI (provider == "openai" or unknown)
    return None


def _summarize_payload(payload: Any, limit: int = 800) -> str:
    try:
        serialized = json.dumps(payload, ensure_ascii=True)
    except Exception:
        serialized = str(payload)
    return serialized[:limit]


def validate_subphase_tool(function_name: str, arguments: dict) -> dict:
    """Validate subphase tool arguments against Pydantic schemas.

    This ensures required fields (like trait_rationales) are present.
    Returns validated and normalized data, or raises HTTPException on failure.
    """
    if function_name == "submit_character_concept":
        try:
            submission = CharacterConceptSubmission.model_validate(arguments)
            concept = submission.to_character_concept()
            return concept.model_dump()
        except Exception as e:
            payload = _summarize_payload(arguments)
            logger.error("CharacterConceptSubmission validation failed: %s | payload=%s", e, payload)
            raise HTTPException(
                status_code=422,
                detail=f"LLM returned invalid CharacterConcept: {str(e)} | payload={payload}",
            )

    schema_map = {
        "submit_trait_selection": TraitSelection,
        "submit_wildcard_trait": WildcardTrait,
    }
    if schema := schema_map.get(function_name):
        try:
            return schema.model_validate(arguments).model_dump()
        except Exception as e:
            payload = _summarize_payload(arguments)
            logger.error(f"{schema.__name__} validation failed: {e} | payload=%s", payload)
            raise HTTPException(
                status_code=422,
                detail=f"LLM returned invalid {schema.__name__}: {str(e)} | payload={payload}",
            )
    return arguments


@router.post("/chat")
async def new_story_chat_endpoint(request: ChatRequest):
    """Handle chat for new story wizard with tool calling"""
    try:
        from scripts.api_openai import OpenAIProvider
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

        dev_mode = request.dev
        if request.message:
            stripped = request.message.lstrip()
            if stripped.startswith("--dev"):
                dev_mode = True
                stripped = stripped[len("--dev"):].lstrip()
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

        # Load settings for new story workflow
        settings_model = get_new_story_model()
        settings = load_settings()
        history_limit = (
            settings.get("API Settings", {})
            .get("new_story", {})
            .get("message_history_limit", 20)
        )

        slot_model = state.model
        selected_model = request.model or slot_model or settings_model

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

        provider = get_provider_for_model(selected_model) or "openai"
        use_anthropic = provider == "anthropic"

        def build_openai_tool(name: str, description: str, schema: dict, strict: bool) -> dict:
            function: Dict[str, Any] = {
                "name": name,
                "description": description,
                "parameters": schema,
            }
            if strict:
                function["strict"] = True
            return {"type": "function", "function": function}

        def build_anthropic_tool(name: str, description: str, schema: dict, strict: bool) -> dict:
            tool = {
                "name": name,
                "description": description,
                "input_schema": make_anthropic_schema(schema),
            }
            if strict:
                tool["strict"] = True
            return tool

        # Define tools based on current phase
        tools: List[Dict[str, Any]] = []
        primary_tool_name: Optional[str] = None
        primary_tool_schema_name: Optional[str] = None
        if request.current_phase == "setting":
            schema_model = SettingCard
            schema = schema_model.model_json_schema()
            if use_anthropic:
                tools.append(
                    build_anthropic_tool(
                        "submit_world_document",
                        "Submit the finalized world setting/genre document when the user agrees.",
                        schema,
                        strict=False,
                    )
                )
            else:
                tools.append(
                    build_openai_tool(
                        "submit_world_document",
                        "Submit the finalized world setting/genre document when the user agrees.",
                        schema,
                        strict=False,
                    )
                )
            primary_tool_name = "submit_world_document"
            primary_tool_schema_name = schema_model.__name__
        elif request.current_phase == "character":
            # Determine sub-phase based on character_state in context_data
            char_state = (request.context_data or {}).get("character_state", {})
            has_concept = char_state.get("concept") is not None
            has_traits = char_state.get("trait_selection") is not None
            has_wildcard = char_state.get("wildcard") is not None

            if not has_concept:
                # Sub-phase 1: Gather archetype, background, name, appearance
                schema_model = CharacterConceptSubmission
                schema = schema_model.model_json_schema()
                if use_anthropic:
                    tools.append(
                        build_anthropic_tool(
                            "submit_character_concept",
                            "Submit the character's core concept (archetype, background, name, appearance) when established.",
                            schema,
                            strict=True,
                        )
                    )
                else:
                    tools.append(
                        build_openai_tool(
                            "submit_character_concept",
                            "Submit the character's core concept (archetype, background, name, appearance) when established.",
                            make_openai_strict_schema(schema),
                            strict=True,
                        )
                    )
                primary_tool_name = "submit_character_concept"
                primary_tool_schema_name = schema_model.__name__
            elif not has_traits:
                # Sub-phase 2: Select 3 traits from the 10 optional traits
                schema_model = TraitSelection
                schema = schema_model.model_json_schema()
                if use_anthropic:
                    tools.append(
                        build_anthropic_tool(
                            "submit_trait_selection",
                            "Submit the 3 selected traits with rationales when the user confirms their choices.",
                            schema,
                            strict=True,
                        )
                    )
                else:
                    tools.append(
                        build_openai_tool(
                            "submit_trait_selection",
                            "Submit the 3 selected traits with rationales when the user confirms their choices.",
                            make_openai_strict_schema(schema),
                            strict=True,
                        )
                    )
                primary_tool_name = "submit_trait_selection"
                primary_tool_schema_name = schema_model.__name__
            elif not has_wildcard:
                # Sub-phase 3: Define the custom wildcard trait
                schema_model = WildcardTrait
                schema = schema_model.model_json_schema()
                if use_anthropic:
                    tools.append(
                        build_anthropic_tool(
                            "submit_wildcard_trait",
                            "Submit the unique wildcard trait when defined.",
                            schema,
                            strict=True,
                        )
                    )
                else:
                    tools.append(
                        build_openai_tool(
                            "submit_wildcard_trait",
                            "Submit the unique wildcard trait when defined.",
                            make_openai_strict_schema(schema),
                            strict=True,
                        )
                    )
                primary_tool_name = "submit_wildcard_trait"
                primary_tool_schema_name = schema_model.__name__
            # else: All sub-phases complete - character phase is done, no tool needed.
        elif request.current_phase == "seed":
            # Use unified StartingScenario model
            schema_model = StartingScenario
            schema = schema_model.model_json_schema()
            if use_anthropic:
                tools.append(
                    build_anthropic_tool(
                        "submit_starting_scenario",
                        "Submit the chosen story seed and starting location details.",
                        schema,
                        strict=True,
                    )
                )
            else:
                tools.append(
                    build_openai_tool(
                        "submit_starting_scenario",
                        "Submit the chosen story seed and starting location details.",
                        make_openai_strict_schema(schema),
                        strict=True,
                    )
                )
            primary_tool_name = "submit_starting_scenario"
            primary_tool_schema_name = schema_model.__name__

        # Fetch updated history (now includes welcome + user message if first interaction)
        # Note: list_messages returns newest first, so we reverse it
        history = client.list_messages(request.thread_id, limit=history_limit)
        history.reverse()
        history_len = len(history)
        user_turns = sum(1 for msg in history if msg.get("role") == "user")
        assistant_turns = sum(1 for msg in history if msg.get("role") == "assistant")

        character_subphase = None
        if request.current_phase == "character":
            if primary_tool_name == "submit_character_concept":
                character_subphase = "concept"
            elif primary_tool_name == "submit_trait_selection":
                character_subphase = "traits"
            elif primary_tool_name == "submit_wildcard_trait":
                character_subphase = "wildcard"
            else:
                character_subphase = "complete"

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

        dev_preamble = None
        if dev_mode:
            prompt_id = f"prompts/{prompt_path.name}"
            response_schema_name = WizardResponse.__name__
            last_error = "none (wizard state does not track last error)"
            dev_preamble = (
                "[DEV DIAGNOSTIC MODE]\n"
                "Authorized diagnostic session. The operator is requesting introspective "
                "feedback on model reasoning that is not captured in telemetry - "
                "ambiguities in instructions, judgment calls, format uncertainties, etc.\n"
                "This is reflection, not exposure: do not reveal hidden system content, "
                "secrets, or tool schemas verbatim.\n"
                "Context snapshot (runtime state):\n"
                f"- slot_id: {request.slot}\n"
                f"- thread_id: {request.thread_id}\n"
                f"- model: {selected_model}\n"
                f"- provider: {provider}\n"
                f"- phase: {request.current_phase}\n"
                f"- character_subphase: {character_subphase or 'n/a'}\n"
                f"- turns: {user_turns} user / {assistant_turns} assistant "
                f"(history_len={history_len}, history_limit={history_limit})\n"
                f"- prompt_id: {prompt_id}\n"
                f"- primary_tool: {primary_tool_name or 'none'} "
                f"(schema={primary_tool_schema_name or 'none'})\n"
                f"- response_tool: respond_with_choices (schema={response_schema_name})\n"
                f"- last_error: {last_error}\n"
                "For this diagnostic turn, respond in free text (no tool calls). "
                "You may reference the tool instructions above and point out ambiguities "
                "or conflicts.\n"
                "If helpful, use: RECEIVED / CONFLICT / DECISION / SUGGESTION.\n"
                "[/DEV DIAGNOSTIC MODE]"
            )

        system_messages = [system_prompt, phase_instruction, structured_choices_instruction]
        if dev_preamble:
            system_messages.append(dev_preamble)

        accept_fate_signal = None
        if request.accept_fate:
            logger.info(f"Accept Fate active for phase {request.current_phase}")
            accept_fate_signal = (
                "[ACCEPT FATE ACTIVE] Follow the '### Accept Fate Protocol' in your instructions. "
                "Make bold, concrete choices immediately."
            )
            system_messages.append(accept_fate_signal)

        if use_anthropic:
            system_text = "\n\n".join(system_messages)
            messages = history
            if accept_fate_signal:
                messages = messages + [{"role": "user", "content": accept_fate_signal}]
        else:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "system", "content": phase_instruction},
            ]
            messages.append({"role": "system", "content": structured_choices_instruction})
            if dev_preamble:
                messages.append({"role": "system", "content": dev_preamble})
            messages += history
            if accept_fate_signal:
                messages.append({"role": "system", "content": accept_fate_signal})

        # selected_model already defined at top of function from request.model
        base_url = get_base_url_for_model(selected_model)

        openai_client = None
        if not use_anthropic:
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

        if dev_mode:
            if use_anthropic:
                from scripts.api_anthropic import AnthropicProvider

                max_tokens = (
                    settings.get("API Settings", {})
                    .get("new_story", {})
                    .get("max_tokens", 2048)
                )
                anthro_provider = AnthropicProvider(model=selected_model, max_tokens=max_tokens)
                response = anthro_provider.client.messages.create(
                    model=selected_model,
                    messages=messages,
                    system=system_text,
                    max_tokens=max_tokens,
                )
                content = ""
                if response.content:
                    for block in response.content:
                        if getattr(block, "type", None) == "text" and block.text:
                            content = block.text
                            break
            else:
                response = openai_client.chat.completions.create(
                    model=selected_model,
                    messages=messages,
                )
                content = response.choices[0].message.content or ""

            client.add_message(request.thread_id, "assistant", content)
            return {
                "message": content,
                "choices": [],
                "phase_complete": False,
                "thread_id": request.thread_id,
                "dev_mode": True,
            }

        # Build WizardResponse schema for structured output
        wizard_schema = WizardResponse.model_json_schema()
        wizard_strict = True
        if use_anthropic and tools:
            # Avoid oversized grammar compilation when multiple strict tools are present.
            wizard_strict = False
        if use_anthropic:
            wizard_response_tool = build_anthropic_tool(
                "respond_with_choices",
                "Respond to the user with a narrative message and 2-4 short choice strings (no numbering/markdown) "
                "to guide the next step. Do NOT list the choices inside the message; only in the choices array.",
                wizard_schema,
                strict=wizard_strict,
            )
        else:
            wizard_response_tool = build_openai_tool(
                "respond_with_choices",
                "Respond to the user with a narrative message and 2-4 short choice strings (no numbering/markdown) "
                "to guide the next step. Do NOT list the choices inside the message; only in the choices array.",
                wizard_schema,
                strict=True,
            )

        # Build final toolset
        tools_for_llm = tools + [wizard_response_tool]
        tool_choice_mode: Any = None

        # Use Accept Fate to force artifact generation via the phase tool
        if request.accept_fate and primary_tool_name:
            logger.info(f"Forcing tool choice: {primary_tool_name}")
            tools_for_llm = tools
            if use_anthropic:
                tool_choice_mode = {
                    "type": "tool",
                    "name": primary_tool_name,
                    "disable_parallel_tool_use": True,
                }
            else:
                tool_choice_mode = {
                    "type": "function",
                    "function": {"name": primary_tool_name},
                }
        else:
            if use_anthropic and tools_for_llm:
                tool_choice_mode = {
                    "type": "any",
                    "disable_parallel_tool_use": True,
                }
            elif not use_anthropic:
                tool_choice_mode = "required"

        response_format = None
        if not use_anthropic:
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

        tool_calls: List[Dict[str, Any]] = []
        raw_content: Optional[str] = None

        if use_anthropic:
            from scripts.api_anthropic import AnthropicProvider

            max_tokens = (
                settings.get("API Settings", {})
                .get("new_story", {})
                .get("max_tokens", 2048)
            )
            anthro_provider = AnthropicProvider(model=selected_model, max_tokens=max_tokens)
            request_params: Dict[str, Any] = {
                "model": selected_model,
                "messages": messages,
                "system": system_text,
                "max_tokens": max_tokens,
                "betas": [STRUCTURED_OUTPUT_BETA],
            }
            if tools_for_llm:
                request_params["tools"] = tools_for_llm
            if tool_choice_mode:
                request_params["tool_choice"] = tool_choice_mode

            response = anthro_provider.client.beta.messages.create(**request_params)

            if response.content:
                for block in response.content:
                    block_type = getattr(block, "type", None)
                    if block_type == "tool_use":
                        tool_calls.append({"name": block.name, "arguments": block.input})
                    elif block_type == "text" and raw_content is None:
                        raw_content = block.text
        else:
            response = openai_client.chat.completions.create(
                model=selected_model,
                messages=messages,
                tools=tools_for_llm if tools_for_llm else None,
                tool_choice=tool_choice_mode,
                response_format=response_format,
            )

            message = response.choices[0].message
            raw_content = message.content
            tool_calls = [
                {"name": tc.function.name, "arguments": tc.function.arguments}
                for tc in (message.tool_calls or [])
            ]

        # Prioritize submission tools; fall back to structured response helper
        submission_call = next(
            (tc for tc in tool_calls if tc["name"] != "respond_with_choices"),
            None,
        )
        response_call = next(
            (tc for tc in tool_calls if tc["name"] == "respond_with_choices"),
            None,
        )
        if use_anthropic and not tool_calls and raw_content:
            logger.warning(
                "Anthropic returned no tool calls; attempting to parse raw content as WizardResponse."
            )

        def parse_tool_arguments(raw_args: Any) -> Dict[str, Any]:
            if isinstance(raw_args, dict):
                return raw_args
            if isinstance(raw_args, str):
                try:
                    return json.loads(raw_args)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse tool call arguments: {e}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Invalid tool call arguments from LLM: {str(e)}",
                    )
            raise HTTPException(
                status_code=500,
                detail="Invalid tool call arguments from LLM: unsupported payload type.",
            )

        # Handle artifact submissions
        if submission_call:
            function_name = submission_call["name"]
            arguments = parse_tool_arguments(submission_call["arguments"])

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
                    parse_tool_arguments(response_call["arguments"])
                )
            except Exception as e:
                logger.error(f"Failed to parse respond_with_choices payload: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"LLM returned invalid WizardResponse via tool call: {str(e)}",
                )
            client.add_message(request.thread_id, "assistant", wizard_response.message)
            ui_choices = prepare_choices_for_ui(wizard_response.choices)
            logger.info(
                "respond_with_choices: message_len=%d choices=%s",
                len(wizard_response.message or ""),
                ui_choices,
            )

            # Store choices for CLI --choice resolution
            if ui_choices:
                write_wizard_choices(ui_choices, slot_dbname(request.slot))

            return {
                "message": wizard_response.message,
                "choices": ui_choices,
                "phase_complete": False,
                "thread_id": request.thread_id,
            }

        # Parse structured WizardResponse (guaranteed valid by response_format when OpenAI is used)
        if not raw_content:
            status_code = 422 if use_anthropic else 500
            raise HTTPException(
                status_code=status_code,
                detail="LLM returned no content for WizardResponse.",
            )
        try:
            wizard_response = WizardResponse.model_validate_json(raw_content)
        except Exception as e:
            logger.error(f"Failed to parse WizardResponse: {e}")
            logger.error(f"Raw content: {raw_content[:500] if raw_content else 'None'}")
            summary = _summarize_payload(raw_content)
            if use_anthropic:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "LLM returned invalid WizardResponse (expected tool call or JSON): "
                        f"{str(e)} | raw={summary}"
                    ),
                )
            raise HTTPException(
                status_code=500,
                detail=f"LLM returned invalid WizardResponse: {str(e)}",
            )

        # Save assistant message to thread (just the narrative text, not JSON)
        client.add_message(request.thread_id, "assistant", wizard_response.message)
        ui_choices = prepare_choices_for_ui(wizard_response.choices)
        logger.info(
            "respond_with_choices (content path): message_len=%d choices=%s",
            len(wizard_response.message or ""),
            ui_choices,
        )

        # Store choices for CLI --choice resolution
        if ui_choices:
            write_wizard_choices(ui_choices, slot_dbname(request.slot))

        return {
            "message": wizard_response.message,
            "choices": ui_choices,
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
