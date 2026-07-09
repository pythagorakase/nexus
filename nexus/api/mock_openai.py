"""
Mock OpenAI server for TEST model.

Impersonates OpenAI API at /v1/chat/completions and /v1/responses.
Queries mock database for test data - no inline caching.

The mock database mirrors save_* schemas and contains:
- assets.new_story_creator: Wizard phase data
- characters, layers, zones, places: Post-transition data
- incubator: Bootstrap narrative

Usage:
    poetry run uvicorn nexus.api.mock_openai:app --port 5102
"""

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logger = logging.getLogger("nexus.api.mock_openai")

MOCK_DB = "mock"
MOCK_STORY_BASE_TIMESTAMP = {
    "year": 2087,
    "month": 11,
    "day": 3,
    "hour": 22,
    "minute": 47,
}


def _parse_pg_array(value: Any) -> List[str]:
    """Parse PostgreSQL array literal to Python list.

    psycopg2's RealDictCursor returns arrays as strings like '{foo,bar}'.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
        inner = value[1:-1]
        return inner.split(",") if inner else []
    return []


app = FastAPI(title="NEXUS Mock OpenAI")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_mock_connection():
    """Get connection to mock database."""
    return psycopg2.connect(
        host="localhost",
        database=MOCK_DB,
        user="pythagor",
        cursor_factory=RealDictCursor,
    )


def query_wizard_cache() -> Dict[str, Any]:
    """Query wizard cache from mock.assets.new_story_creator."""
    with get_mock_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    -- Setting
                    setting_genre, setting_secondary_genres, setting_world_name,
                    setting_tone, setting_themes, setting_diegetic_artifact,
                    setting_tech_level, setting_magic_exists, setting_magic_description,
                    setting_geographic_scope, setting_political_structure, setting_major_conflict,
                    setting_cultural_notes, setting_language_notes, setting_time_period,
                    -- Character (traits now in assets.traits table)
                    character_name, character_archetype, character_background,
                    character_appearance,
                    -- Seed
                    seed_type, seed_title, seed_situation, seed_hook,
                    seed_immediate_goal, seed_stakes, seed_tension_source,
                    seed_weather, seed_key_npcs,
                    seed_secrets,
                    -- Layer/Zone/Location
                    layer_name, layer_type, layer_description,
                    zone_name, zone_summary,
                    initial_location
                FROM assets.new_story_creator
                WHERE id = TRUE
            """
            )
            return cur.fetchone() or {}


def query_traits() -> List[Dict[str, Any]]:
    """Query all traits from mock.assets.traits."""
    with get_mock_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, description, is_selected, rationale
                FROM assets.traits
                ORDER BY id
            """
            )
            return list(cur.fetchall())


def query_bootstrap_narrative() -> Dict[str, Any]:
    """Query bootstrap narrative from mock.incubator."""
    with get_mock_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT storyteller_text, choice_object, metadata_updates,
                       reference_updates
                FROM incubator
                WHERE id = TRUE
            """
            )
            return cur.fetchone() or {}


def get_cached_phase_response(
    phase: str, subphase: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get cached response for a wizard phase from mock database.

    Replaces JSON file-based caching with database queries.
    """
    cache = query_wizard_cache()

    if phase == "setting":
        return {
            "phase_complete": True,
            "artifact_type": "submit_world_document",
            "data": {
                "tone": cache.get("setting_tone"),
                "genre": cache.get("setting_genre"),
                "themes": _parse_pg_array(cache.get("setting_themes")),
                "tech_level": cache.get("setting_tech_level"),
                "world_name": cache.get("setting_world_name"),
                "time_period": cache.get("setting_time_period"),
                "magic_exists": cache.get("setting_magic_exists", False),
                "magic_description": cache.get("setting_magic_description"),
                "cultural_notes": cache.get("setting_cultural_notes"),
                "language_notes": cache.get("setting_language_notes"),
                "major_conflict": cache.get("setting_major_conflict"),
                "geographic_scope": cache.get("setting_geographic_scope"),
                "secondary_genres": _parse_pg_array(
                    cache.get("setting_secondary_genres")
                ),
                "political_structure": cache.get("setting_political_structure"),
                "diegetic_artifact": cache.get("setting_diegetic_artifact"),
            },
            "message": "[TEST MODE] World setting loaded from mock database.",
        }

    elif phase == "character":
        # Query traits from assets.traits table
        traits = query_traits()
        selected_traits = [
            t for t in traits if t.get("is_selected") and t.get("id") <= 10
        ]
        wildcard = next((t for t in traits if t.get("id") == 11), None)

        # Build trait names and rationales from selected traits
        selected_names = [t.get("name") for t in selected_traits]
        trait_rationales = {
            t.get("name"): t.get("rationale")
            for t in selected_traits
            if t.get("rationale")
        }

        if subphase == "concept":
            # For concept submission, suggest 3 traits if none are selected yet
            if not selected_names:
                # Default suggestions based on typical character archetypes
                suggested_names = ["status", "reputation", "obligations"]
                suggested_rationales = {
                    "status": "Given the character's background, their status in the world creates tension.",
                    "reputation": "The character's reputation precedes them, opening some doors while slamming others.",
                    "obligations": "Obligations pull the character into situations against their better judgment.",
                }
            else:
                suggested_names = selected_names
                suggested_rationales = trait_rationales

            return {
                "phase_complete": False,
                "artifact_type": "submit_character_concept",
                "data": {
                    "name": cache.get("character_name"),
                    "archetype": cache.get("character_archetype"),
                    "background": cache.get("character_background"),
                    "appearance": cache.get("character_appearance"),
                    "suggested_traits": suggested_names,
                    "trait_rationales": suggested_rationales,
                },
                "message": "[TEST MODE] Character concept loaded from mock database.",
            }
        elif subphase == "traits":
            return {
                "phase_complete": False,
                "artifact_type": "submit_trait_selection",
                "data": {
                    "selected_traits": selected_names,
                    "trait_rationales": trait_rationales,
                },
                "message": "[TEST MODE] Traits loaded from mock database.",
            }
        elif subphase == "wildcard":
            return {
                "phase_complete": True,
                "artifact_type": "submit_wildcard_trait",
                "data": {
                    "character_state": {
                        "concept": {
                            "name": cache.get("character_name"),
                            "archetype": cache.get("character_archetype"),
                            "background": cache.get("character_background"),
                            "appearance": cache.get("character_appearance"),
                        },
                        "trait_selection": {
                            "selected_traits": selected_names,
                        },
                        "wildcard": {
                            "wildcard_name": (
                                wildcard.get("name") if wildcard else "wildcard"
                            ),
                            "wildcard_description": (
                                wildcard.get("rationale") if wildcard else None
                            ),
                        },
                    },
                },
                "message": "[TEST MODE] Wildcard loaded from mock database.",
            }

    elif phase == "seed":
        location = cache.get("initial_location") or {}
        # Two-phase seed generation: Return StorySeedSubmission format
        # Phase 1: seed + location_sketch (creative content)
        # Phase 2: set designer generates layer/zone/location (handled in wizard_chat.py)

        # Generate location_sketch from existing location data for backward compatibility
        location_name = location.get("name", "unknown location")
        location_summary = location.get("summary", "")
        zone_name = cache.get("zone_name", "")
        layer_name = cache.get("layer_name", "")

        location_sketch = (
            f"A place called {location_name} in the {zone_name} region of {layer_name}. "
            f"{location_summary}"
        )

        return {
            "phase_complete": False,  # Not complete until set designer runs
            "requires_set_design": True,
            "artifact_type": "submit_starting_scenario",
            "data": {
                "seed": {
                    "seed_type": cache.get("seed_type"),
                    "title": cache.get("seed_title"),
                    "situation": cache.get("seed_situation"),
                    "hook": cache.get("seed_hook"),
                    "immediate_goal": cache.get("seed_immediate_goal"),
                    "stakes": cache.get("seed_stakes"),
                    "tension_source": cache.get("seed_tension_source"),
                    "base_timestamp": MOCK_STORY_BASE_TIMESTAMP,
                    "weather": cache.get("seed_weather"),
                    "key_npcs": _parse_pg_array(cache.get("seed_key_npcs")),
                    "secrets": cache.get("seed_secrets"),
                },
                "location_sketch": location_sketch,
            },
            # Include pre-computed location data for TEST mode bypass
            # wizard_chat.py can use this instead of calling set designer
            "_mock_location_data": {
                "layer": {
                    "name": cache.get("layer_name"),
                    "type": cache.get("layer_type"),
                    "description": cache.get("layer_description"),
                },
                "zone": {
                    "name": cache.get("zone_name"),
                    "summary": cache.get("zone_summary"),
                },
                "location": location,
            },
            "message": "[TEST MODE] Seed loaded from mock database.",
        }

    return {"data": {}, "message": "[TEST MODE] Unknown phase"}


# Archetype choices for character intro
ARCHETYPE_CHOICES = ["The Amnesiac Courier", "The Double Agent", "The Memory Architect"]

# Wildcard choices
WILDCARD_CHOICES = ["Ghostprint Key", "Neural Echo", "Dead Man's Archive"]

# Seed type choices
SEED_CHOICES = [
    "The Job You Already Took",
    "The Message That Found You",
    "The Face You Used to Wear",
]


class ChatMessage(BaseModel):
    role: str
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Dict[str, Any]]
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Any] = None
    response_format: Optional[Dict[str, Any]] = None


def get_latest_user_message(messages: List[Dict[str, Any]]) -> Optional[str]:
    """Get the content of the most recent user message."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            return content if isinstance(content, str) else None
    return None


def is_phase_transition(content: str) -> bool:
    """Check if message is a phase transition system message."""
    return "[SYSTEM] Phase" in content and "Proceeding to" in content


def get_forced_tool(tool_choice: Any) -> Optional[str]:
    """
    Check if tool_choice is forcing a specific tool.
    Returns the tool name if forced, None otherwise.

    tool_choice can be:
    - "auto" or "required" or "none" (string)
    - {"type": "function", "function": {"name": "tool_name"}} (force specific)
    """
    if isinstance(tool_choice, dict):
        if tool_choice.get("type") == "function":
            return tool_choice.get("function", {}).get("name")
    return None


def detect_phase_from_tools(
    tools: Optional[List[Dict[str, Any]]],
) -> tuple[str, Optional[str]]:
    """
    Detect wizard phase and subphase from the tools array in the request.
    """
    if not tools:
        return "setting", None

    tool_names = [t.get("function", {}).get("name", "") for t in tools]

    if "submit_world_document" in tool_names:
        return "setting", None
    elif "submit_character_concept" in tool_names:
        return "character", "concept"
    elif "submit_trait_selection" in tool_names:
        return "character", "traits"
    elif "submit_wildcard_trait" in tool_names:
        return "character", "wildcard"
    elif "submit_character_sheet" in tool_names:
        # All character subphases complete, ready for final sheet
        return "character", "sheet"
    elif "submit_starting_scenario" in tool_names:
        return "seed", None

    return "setting", None


def build_respond_with_choices(message: str, choices: List[str]) -> Dict[str, Any]:
    """Build a respond_with_choices tool call response."""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": "respond_with_choices",
                    "arguments": json.dumps(
                        {
                            "message": message,
                            "choices": choices,
                        }
                    ),
                },
            }
        ],
    }


def build_artifact_response(artifact_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Build an artifact submission tool call response."""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": artifact_type,
                    "arguments": json.dumps(data),
                },
            }
        ],
    }


def build_archetype_intro() -> Dict[str, Any]:
    """Build character phase introduction with archetype choices."""
    message = "[TEST MODE] Welcome to character creation. Based on the world of Neon Palimpsest, which archetypal path speaks to you?"
    choices = [
        "The Amnesiac Courier - Someone who wakes with no memory but dangerous skills, hunted by forces they don't remember crossing.",
        "The Double Agent - A figure walking the line between corporate authority and underground resistance, trusted by neither.",
        "The Memory Architect - A technician who can edit, erase, or fabricate identities, now running from their own creations.",
    ]
    return build_respond_with_choices(message, choices)


def build_wildcard_intro() -> Dict[str, Any]:
    """Build wildcard selection introduction."""
    message = "[TEST MODE] Your character's core is taking shape. Now add a wildcard element that sets them apart. Which resonates with your vision?"
    choices = [
        "Ghostprint Key - A pre-Council identity root hidden under their skin that can briefly assume anyone's credentials, but draws dangerous attention with each use.",
        "Neural Echo - Fragmented memories of their erased past that surface unpredictably, sometimes revealing crucial information, sometimes triggering buried protocols.",
        "Dead Man's Archive - A cached data-store of secrets they gathered before their memory was wiped, accessible only through specific emotional triggers.",
    ]
    return build_respond_with_choices(message, choices)


def build_seed_intro() -> Dict[str, Any]:
    """Build seed phase introduction with scenario choices."""
    message = "[TEST MODE] Your character is ready. Now let's craft the opening scene. Which draws you in?"
    choices = [
        "The Job You Already Took - Kade wakes on a rattling tram, a courier's satchel handcuffed to their wrist and no memory of accepting the job. The city's ledgers insist the delivery is already in breach.",
        "The Message That Found You - A ghost-frequency ping activates in Kade's burned neural mesh—coordinates and a single word: 'Remember.' Someone from their erased past wants to make contact.",
        "The Face You Used to Wear - Kade spots their own face on a wanted feed, but the name and crimes belong to someone they don't remember being. The bounty is high enough to turn every stranger into a threat.",
    ]
    return build_respond_with_choices(message, choices)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "mock_openai"}


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """
    Mock OpenAI chat completions endpoint.

    Handles the full wizard conversation flow by analyzing:
    1. Current phase (from tools)
    2. User message content (to determine intro vs artifact)
    3. Forced tool_choice (Accept Fate bypasses conversation)
    """
    logger.info(f"[MOCK] Received request for model: {request.model}")

    # Detect phase from tools
    phase, subphase = detect_phase_from_tools(request.tools)
    user_msg = get_latest_user_message(request.messages) or ""
    forced_tool = get_forced_tool(request.tool_choice)

    logger.info(f"[MOCK] Phase: {phase}, Subphase: {subphase}")
    logger.info(f"[MOCK] User message: {user_msg[:100]}...")
    if forced_tool:
        logger.info(f"[MOCK] Forced tool: {forced_tool} (Accept Fate)")

    # Determine response based on phase and conversation state
    message = None

    # === SETTING PHASE ===
    if phase == "setting":
        # Setting phase goes straight to artifact (no intro conversation)
        cached = get_cached_phase_response("setting", None)
        message = build_artifact_response(
            "submit_world_document", cached.get("data", {})
        )
        logger.info("[MOCK] Returning setting artifact")

    # === CHARACTER PHASE ===
    elif phase == "character":

        # Subphase: Concept (archetype selection)
        if subphase == "concept":
            if is_phase_transition(user_msg):
                # Phase intro - show archetype choices
                message = build_archetype_intro()
                logger.info("[MOCK] Returning archetype intro")
            else:
                # Any input (choice selection, accept_fate, or freeform) → advance
                cached = get_cached_phase_response("character", "concept")
                message = build_artifact_response(
                    "submit_character_concept", cached.get("data", {})
                )
                logger.info("[MOCK] Returning character concept artifact")

        # Subphase: Traits
        elif subphase == "traits":
            # Trait selection is handled by the UI - just return the artifact
            cached = get_cached_phase_response("character", "traits")
            message = build_artifact_response(
                "submit_trait_selection", cached.get("data", {})
            )
            logger.info("[MOCK] Returning trait selection artifact")

        # Subphase: Wildcard
        elif subphase == "wildcard":
            if is_phase_transition(user_msg):
                # Phase intro - show wildcard choices
                message = build_wildcard_intro()
                logger.info("[MOCK] Returning wildcard intro")
            else:
                # Any input (choice selection, accept_fate, or freeform) → advance
                cached = get_cached_phase_response("character", "wildcard")
                wildcard_data = (
                    cached.get("data", {})
                    .get("character_state", {})
                    .get("wildcard", {})
                )
                message = build_artifact_response(
                    "submit_wildcard_trait", wildcard_data
                )
                logger.info("[MOCK] Returning wildcard trait artifact")

        # Subphase: Character Sheet (all subphases complete)
        elif subphase == "sheet":
            # Return the final character sheet
            cached = get_cached_phase_response("character", "wildcard")
            message = build_artifact_response(
                "submit_character_sheet", cached.get("data", {})
            )
            logger.info("[MOCK] Returning final character sheet artifact")

    # === SEED PHASE ===
    elif phase == "seed":
        if is_phase_transition(user_msg):
            # Phase intro - show seed choices
            message = build_seed_intro()
            logger.info("[MOCK] Returning seed intro")
        else:
            # Any input (choice selection, accept_fate, or freeform) → advance
            cached = get_cached_phase_response("seed", None)
            message = build_artifact_response(
                "submit_starting_scenario", cached.get("data", {})
            )
            logger.info("[MOCK] Returning seed artifact")

    # Fallback
    if message is None:
        message = build_respond_with_choices(
            f"[TEST MODE] Unexpected state: phase={phase}, subphase={subphase}",
            ["Continue", "Go back"],
        )
        logger.warning(
            f"[MOCK] Fallback response for phase={phase}, subphase={subphase}"
        )

    return {
        "id": f"chatcmpl-mock-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(datetime.now().timestamp()),
        "model": "TEST",
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# RESPONSES API (for narrative generation via LogonUtility)
# ═══════════════════════════════════════════════════════════════════════════════


class ResponsesRequest(BaseModel):
    """Request format for /v1/responses endpoint."""

    model: str
    input: Any
    max_output_tokens: Optional[int] = None
    temperature: Optional[float] = None
    reasoning: Optional[Dict[str, Any]] = None
    text: Optional[Dict[str, Any]] = None  # OpenAI native strict text.format
    text_format: Optional[Any] = None  # Pydantic schema for structured output
    tools: Optional[Any] = None  # pydantic_ai output tool ("final_result")


def _schema_property_names(payload: Any) -> set[str]:
    """Return top-level property names from OpenAI structured-output payloads."""

    if not isinstance(payload, dict):
        return set()
    if "format" in payload:
        return _schema_property_names(payload.get("format"))
    if payload.get("type") == "json_schema":
        schema = payload.get("schema")
        if schema is None and isinstance(payload.get("json_schema"), dict):
            schema = payload["json_schema"].get("schema")
        if isinstance(schema, dict):
            return set((schema.get("properties") or {}).keys())
    return set((payload.get("properties") or {}).keys())


def _requested_output_uses_final_result_tool(request: "ResponsesRequest") -> bool:
    """Return whether the request expects a Pydantic-AI final_result call."""

    for tool in request.tools or []:
        if isinstance(tool, dict) and tool.get("name") == "final_result":
            return True
    return False


def _requested_output_properties(request: "ResponsesRequest") -> set[str]:
    """Return the property names of the requested structured output, if present.

    pydantic_ai delivers the caller's output schema as a ``final_result``
    function tool with ``tool_choice: required``; the schema's top-level
    properties identify WHICH Storyteller schema the caller will validate
    against. Routing on this is exact, where the legacy keyword sniffing of
    the prompt text was not (a turn request without Orrery proposals used to
    fall through to the bootstrap-shaped payload and fail validation).

    Native OpenAI structured output arrives as ``text.format`` with the same
    top-level schema properties.
    """
    fields = _schema_property_names(request.text)
    if fields:
        return fields
    fields = _schema_property_names(request.text_format)
    if fields:
        return fields
    for tool in request.tools or []:
        if isinstance(tool, dict) and tool.get("name") == "final_result":
            params = tool.get("parameters") or {}
            return _schema_property_names(params)
    return set()


def _collect_text(value: Any) -> str:
    """Flatten OpenAI Responses input variants into searchable prompt text.

    When a dict has multiple prompt-like keys, use the first known Responses API
    shape instead of concatenating siblings that may duplicate the same content.
    """

    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(part for item in value if (part := _collect_text(item)))
    if isinstance(value, dict):
        for key in ("content", "text", "input", "message"):
            if key in value:
                text = _collect_text(value[key])
                if text:
                    return text
        return "\n".join(
            part for item in value.values() if (part := _collect_text(item))
        )
    return ""


def _extract_orrery_proposal_ids(prompt: str) -> List[str]:
    """Extract proposal IDs from LogonUtility's prompt-facing Orrery list.

    Orrery proposal IDs are generated as ``template_id:binding_hash`` in
    ``nexus.agents.orrery.resolver``. Requiring the colon keeps generic markdown
    bullets from being mistaken for proposal IDs.
    """

    proposal_ids: List[str] = []
    seen: set[str] = set()
    patterns = (
        re.compile(r"^-\s+(?P<id>[^:\s\[]+:[^\s\[]+)\s+\[", re.MULTILINE),
        re.compile(r'"proposal_id"\s*:\s*"(?P<id>[^":]+:[^"]+)"'),
    )
    for pattern in patterns:
        for match in pattern.finditer(prompt):
            proposal_id = match.group("id").strip()
            if ":" not in proposal_id or proposal_id in seen:
                continue
            seen.add(proposal_id)
            proposal_ids.append(proposal_id)
    return proposal_ids


def _mock_orrery_adjudications(prompt: str) -> List[Dict[str, Any]]:
    """Return deterministic defer/void/replace decisions for Orrery tests."""

    proposal_ids = _extract_orrery_proposal_ids(prompt)
    adjudications: List[Dict[str, Any]] = []
    for index, proposal_id in enumerate(proposal_ids[:3]):
        if index == 0:
            adjudications.append(
                {
                    "proposal_id": proposal_id,
                    "action": "defer",
                    "note": "[TEST MODE] Deferred so pressure can remain live.",
                }
            )
        elif index == 1:
            adjudications.append(
                {
                    "proposal_id": proposal_id,
                    "action": "void",
                    "note": "[TEST MODE] Voided as definitively untrue this tick.",
                }
            )
        else:
            adjudications.append(
                {
                    "proposal_id": proposal_id,
                    "action": "replace",
                    "note": "[TEST MODE] Replaced with a story-truer activity.",
                    "replacement_event_type": "mock_replacement",
                    "replacement_state_delta": {
                        "character_current_activity": (
                            "following the mock-server replacement beat"
                        )
                    },
                }
            )
    return adjudications


def _mock_storyteller_response(prompt: str) -> Dict[str, Any]:
    """Build a schema-valid deterministic narrative response for TEST mode."""

    adjudications = _mock_orrery_adjudications(prompt)
    return {
        "narrative": (
            "[TEST MODE] The scene advances under deterministic mock control. "
            "Orrery pressure is acknowledged structurally, while the prose remains "
            "simple enough for integration tests to inspect."
        ),
        "choices": [
            "Continue following the immediate lead.",
            "Pause and reassess the pressure around the scene.",
            "Shift attention to the quieter off-screen consequence.",
        ],
        "chunk_metadata": {
            "chronology": {
                "episode_transition": "continue",
                "time_delta_minutes": 5,
                "time_delta_hours": None,
                "time_delta_days": None,
                "time_delta_description": "A few focused minutes pass.",
            },
            "world_layer": "primary",
        },
        "referenced_entities": {
            "characters": [],
            "places": [],
            "factions": [],
        },
        "state_updates": {
            "characters": [],
            "relationships": [],
            "locations": [],
            "factions": [],
        },
        "operations": None,
        "orrery_adjudications": adjudications,
        "reasoning": "[TEST MODE] Deterministic mock storyteller response.",
    }


def _responses_payload(
    output_data: Dict[str, Any], *, final_result_tool: bool = False
) -> Dict[str, Any]:
    """Format structured JSON as an OpenAI Responses-compatible payload."""

    output_json = json.dumps(output_data)
    if final_result_tool:
        output = [
            {
                "type": "function_call",
                "id": f"fc-mock-{uuid.uuid4().hex[:8]}",
                "call_id": f"call-mock-{uuid.uuid4().hex[:8]}",
                "name": "final_result",
                "arguments": output_json,
                "status": "completed",
            }
        ]
    else:
        output = [
            {
                "type": "message",
                "id": f"msg-mock-{uuid.uuid4().hex[:8]}",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": output_json,
                        "annotations": [],
                    }
                ],
            }
        ]
    return {
        "id": f"resp-mock-{uuid.uuid4().hex[:8]}",
        "object": "response",
        "created_at": int(datetime.now().timestamp()),
        "model": "TEST",
        "status": "completed",
        "output": output,
        "output_text": output_json,
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 800,
            "total_tokens": 1800,
        },
    }


def get_cached_bootstrap_narrative() -> Dict[str, Any]:
    """
    Get bootstrap narrative from mock database.

    Queries incubator and transforms to StorytellerResponseBootstrap format
    (narrative + choices, extra fields forbidden).
    Must match the exact schema in nexus/agents/logon/apex_schema.py: the
    bootstrap path validates StorytellerResponseBootstrap, which rejects the
    Extended-shaped payload this function used to emit.
    """
    row = query_bootstrap_narrative()

    if not row:
        logger.warning("[MOCK] No bootstrap narrative found in mock.incubator")
        return {
            "narrative": "[TEST MODE] No mock data available",
            "choices": ["Continue", "Wait"],
        }

    # Extract choices from choice_object
    choice_obj = row.get("choice_object") or {}
    choices = choice_obj.get("presented", [])

    return {
        "narrative": row.get("storyteller_text", ""),
        "choices": choices,
    }


@app.post("/v1/responses")
async def responses_create(request: ResponsesRequest):
    """
    Mock OpenAI responses endpoint for narrative generation.

    This handles requests from LogonUtility.generate_narrative() which uses
    the OpenAI responses API with structured output.
    """
    logger.info(f"[MOCK] Responses request for model: {request.model}")

    input_text = _collect_text(request.input)
    proposal_ids = _extract_orrery_proposal_ids(input_text)

    # Exact routing: the structured-output tool's schema says which
    # Storyteller response the caller validates against. Turn requests
    # (StorytellerResponseExtended) carry state_updates; bootstrap requests
    # (StorytellerResponseBootstrap) do not.
    output_fields = _requested_output_properties(request)
    if output_fields:
        final_result_tool = _requested_output_uses_final_result_tool(request)
        if "state_updates" in output_fields:
            logger.info(
                "[MOCK] Extended turn schema requested (%d Orrery proposals)",
                len(proposal_ids),
            )
            return _responses_payload(
                _mock_storyteller_response(input_text),
                final_result_tool=final_result_tool,
            )
        logger.info("[MOCK] Bootstrap schema requested, returning cached bootstrap")
        return _responses_payload(
            get_cached_bootstrap_narrative(), final_result_tool=final_result_tool
        )

    # Legacy keyword routing for callers without a structured-output tool.
    is_narrative = any(
        kw in input_text.lower()
        for kw in ["narrative", "story", "protagonist", "bootstrap", "user input"]
    )

    if proposal_ids:
        logger.info(
            "[MOCK] Detected %d Orrery proposals, returning adjudication fixture",
            len(proposal_ids),
        )
        return _responses_payload(_mock_storyteller_response(input_text))

    if is_narrative:
        logger.info("[MOCK] Detected narrative request, returning cached bootstrap")
        return _responses_payload(get_cached_bootstrap_narrative())

    # Default fallback for non-narrative requests
    logger.warning("[MOCK] Unknown responses request type")
    return {
        "id": f"resp-mock-{uuid.uuid4().hex[:8]}",
        "object": "response",
        "created_at": int(datetime.now().timestamp()),
        "model": "TEST",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "id": f"msg-mock-{uuid.uuid4().hex[:8]}",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "[TEST MODE] Mock response",
                        "annotations": [],
                    }
                ],
            }
        ],
        "output_text": "[TEST MODE] Mock response",
        "usage": {
            "input_tokens": 100,
            "output_tokens": 10,
            "total_tokens": 110,
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5102)
