"""
Mock OpenAI server for TEST model.

Impersonates OpenAI API at /v1/chat/completions.
Returns cached wizard data with proper conversation flow.

Handles the full wizard conversation:
- Setting phase: artifact only (no intro conversation)
- Character phase: archetype intro → concept → trait selector → wildcard intro → character sheet
- Seed phase: seed intro → seed artifact

Usage:
    poetry run uvicorn nexus.api.mock_openai:app --port 5102
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from nexus.api.wizard_test_cache import get_cached_phase_response

logger = logging.getLogger("nexus.api.mock_openai")

app = FastAPI(title="NEXUS Mock OpenAI")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RESPONSE_DELAY_MS = 1500

# Archetype choices for character intro
ARCHETYPE_CHOICES = [
    "The Amnesiac Courier",
    "The Double Agent",
    "The Memory Architect"
]

# Wildcard choices
WILDCARD_CHOICES = [
    "Ghostprint Key",
    "Neural Echo",
    "Dead Man's Archive"
]

# Seed type choices
SEED_CHOICES = [
    "The Job You Already Took",
    "The Message That Found You",
    "The Face You Used to Wear"
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


def contains_any(text: str, keywords: List[str]) -> bool:
    """Check if text contains any of the keywords (case-insensitive)."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


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


def detect_phase_from_tools(tools: Optional[List[Dict[str, Any]]]) -> tuple[str, Optional[str]]:
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
                    "arguments": json.dumps({
                        "message": message,
                        "choices": choices,
                    }),
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
    message = """[TEST MODE] Welcome to the character phase! I'll help you create a protagonist for your story.

Based on the world of Neon Palimpsest, here are three archetypal paths your character could follow:

**The Amnesiac Courier** - Someone who wakes with no memory but dangerous skills, hunted by forces they don't remember crossing.

**The Double Agent** - A figure walking the line between corporate authority and underground resistance, trusted by neither.

**The Memory Architect** - A technician who can edit, erase, or fabricate identities, now running from their own creations.

Which of these speaks to you?"""
    return build_respond_with_choices(message, ARCHETYPE_CHOICES)


def build_wildcard_intro() -> Dict[str, Any]:
    """Build wildcard selection introduction."""
    message = """[TEST MODE] Your character's core is taking shape. Now let's add something unique—a wildcard element that sets them apart.

Based on Kade's background as a data-smuggler with a burned-out neural mesh, here are three signature elements that could define their edge:

**Ghostprint Key** - A pre-Council identity root hidden under their skin that can briefly assume anyone's credentials, but draws dangerous attention with each use.

**Neural Echo** - Fragmented memories of their erased past that surface unpredictably, sometimes revealing crucial information, sometimes triggering buried protocols.

**Dead Man's Archive** - A cached data-store of secrets they gathered before their memory was wiped, accessible only through specific emotional triggers.

Which resonates with your vision for this character?"""
    return build_respond_with_choices(message, WILDCARD_CHOICES)


def build_seed_intro() -> Dict[str, Any]:
    """Build seed phase introduction with scenario choices."""
    message = """[TEST MODE] Your character is ready. Now let's craft the opening scene that will launch their story.

Given Kade's nature as an amnesiac caught between Syndicates and Ghosts, here are three compelling ways to begin:

**The Job You Already Took** - Kade wakes on a rattling tram in the Roots, a courier's satchel handcuffed to their wrist and no memory of accepting the job. The city's ledgers insist the delivery is already in breach.

**The Message That Found You** - A ghost-frequency ping activates in Kade's burned neural mesh—coordinates and a single word: "Remember." Someone from their erased past wants to make contact.

**The Face You Used to Wear** - Kade spots their own face on a wanted feed, but the name and crimes belong to someone they don't remember being. The bounty is high enough to turn every stranger into a threat.

Which opening draws you in?"""
    return build_respond_with_choices(message, SEED_CHOICES)


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

    # Simulate API latency
    await asyncio.sleep(RESPONSE_DELAY_MS / 1000)

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
        message = build_artifact_response("submit_world_document", cached.get("data", {}))
        logger.info("[MOCK] Returning setting artifact")

    # === CHARACTER PHASE ===
    elif phase == "character":

        # Subphase: Concept (archetype selection)
        if subphase == "concept":
            if forced_tool == "submit_character_concept":
                # Accept Fate pressed - return concept artifact immediately
                cached = get_cached_phase_response("character", "concept")
                message = build_artifact_response("submit_character_concept", cached.get("data", {}))
                logger.info("[MOCK] Returning character concept artifact (Accept Fate)")
            elif is_phase_transition(user_msg):
                # Phase intro - show archetype choices
                message = build_archetype_intro()
                logger.info("[MOCK] Returning archetype intro")
            elif contains_any(user_msg, ARCHETYPE_CHOICES):
                # User selected archetype - return concept artifact
                cached = get_cached_phase_response("character", "concept")
                message = build_artifact_response("submit_character_concept", cached.get("data", {}))
                logger.info("[MOCK] Returning character concept artifact")
            else:
                # Unknown state - default to showing archetype intro
                message = build_archetype_intro()
                logger.info("[MOCK] Returning archetype intro (default)")

        # Subphase: Traits
        elif subphase == "traits":
            # Trait selection is handled by the UI - just return the artifact
            cached = get_cached_phase_response("character", "traits")
            message = build_artifact_response("submit_trait_selection", cached.get("data", {}))
            logger.info("[MOCK] Returning trait selection artifact")

        # Subphase: Wildcard
        elif subphase == "wildcard":
            # Check if Accept Fate is forcing the artifact
            if forced_tool == "submit_wildcard_trait" or contains_any(user_msg, WILDCARD_CHOICES):
                # User selected wildcard OR Accept Fate pressed - return wildcard artifact
                cached = get_cached_phase_response("character", "wildcard")
                wildcard_data = cached.get("data", {}).get("character_state", {}).get("wildcard", {})
                message = build_artifact_response("submit_wildcard_trait", wildcard_data)
                logger.info("[MOCK] Returning wildcard trait artifact")
            else:
                # First request in wildcard subphase - show wildcard choices
                message = build_wildcard_intro()
                logger.info("[MOCK] Returning wildcard intro")

        # Subphase: Character Sheet (all subphases complete)
        elif subphase == "sheet":
            # Return the final character sheet
            cached = get_cached_phase_response("character", "wildcard")
            message = build_artifact_response("submit_character_sheet", cached.get("data", {}))
            logger.info("[MOCK] Returning final character sheet artifact")

    # === SEED PHASE ===
    elif phase == "seed":
        if forced_tool == "submit_starting_scenario":
            # Accept Fate pressed - return seed artifact immediately
            cached = get_cached_phase_response("seed", None)
            message = build_artifact_response("submit_starting_scenario", cached.get("data", {}))
            logger.info("[MOCK] Returning seed artifact (Accept Fate)")
        elif is_phase_transition(user_msg):
            # Phase intro - show seed choices
            message = build_seed_intro()
            logger.info("[MOCK] Returning seed intro")
        elif contains_any(user_msg, SEED_CHOICES):
            # User selected seed - return seed artifact
            cached = get_cached_phase_response("seed", None)
            message = build_artifact_response("submit_starting_scenario", cached.get("data", {}))
            logger.info("[MOCK] Returning seed artifact")
        else:
            # Unknown state - show seed intro
            message = build_seed_intro()
            logger.info("[MOCK] Returning seed intro (default)")

    # Fallback
    if message is None:
        message = build_respond_with_choices(
            f"[TEST MODE] Unexpected state: phase={phase}, subphase={subphase}",
            ["Continue", "Go back"]
        )
        logger.warning(f"[MOCK] Fallback response for phase={phase}, subphase={subphase}")

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5102)
