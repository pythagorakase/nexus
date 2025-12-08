"""
Mock OpenAI server for TEST model.

Impersonates OpenAI API at /v1/chat/completions.
Returns cached wizard data after 1500ms delay.

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


def detect_phase_from_tools(tools: Optional[List[Dict[str, Any]]]) -> tuple[str, Optional[str]]:
    """
    Detect wizard phase and subphase from the tools array in the request.

    Returns:
        (phase, subphase) tuple
    """
    if not tools:
        return "setting", None

    tool_names = [t.get("function", {}).get("name", "") for t in tools]

    # Phase detection based on tool names
    if "submit_world_document" in tool_names:
        return "setting", None
    elif "submit_character_concept" in tool_names:
        return "character", "concept"
    elif "submit_trait_selection" in tool_names:
        return "character", "traits"
    elif "submit_wildcard_trait" in tool_names:
        return "character", "wildcard"
    elif "submit_starting_scenario" in tool_names:
        return "seed", None

    # Default to setting if no recognized tools
    return "setting", None


def build_tool_call_response(phase: str, subphase: Optional[str]) -> Dict[str, Any]:
    """
    Build an OpenAI-compatible tool_calls response from cached data.

    Args:
        phase: Current wizard phase
        subphase: Character subphase (if applicable)

    Returns:
        OpenAI message dict with tool_calls
    """
    # Get cached response data
    cached = get_cached_phase_response(phase, subphase)

    # Map artifact_type to function name
    artifact_type = cached.get("artifact_type", "respond_with_choices")

    # For artifacts, return tool call with the data
    if artifact_type != "respond_with_choices":
        arguments = json.dumps(cached.get("data", {}))
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": artifact_type,
                        "arguments": arguments,
                    },
                }
            ],
        }

    # For conversational responses, use respond_with_choices
    wizard_response = {
        "message": cached.get("message", "[TEST MODE] Processing..."),
        "choices": cached.get("choices", ["Continue", "Go back"]),
    }
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": "respond_with_choices",
                    "arguments": json.dumps(wizard_response),
                },
            }
        ],
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "mock_openai"}


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """
    Mock OpenAI chat completions endpoint.

    Detects wizard phase from tools in request and returns cached data
    after a simulated delay.
    """
    logger.info(f"[MOCK] Received request for model: {request.model}")

    # Simulate API latency
    await asyncio.sleep(RESPONSE_DELAY_MS / 1000)

    # Detect phase from tools
    phase, subphase = detect_phase_from_tools(request.tools)
    logger.info(f"[MOCK] Detected phase: {phase}, subphase: {subphase}")

    # Build response
    try:
        message = build_tool_call_response(phase, subphase)
        finish_reason = "tool_calls" if message.get("tool_calls") else "stop"
    except Exception as e:
        logger.error(f"[MOCK] Error building response: {e}")
        # Return a fallback conversational response
        message = {
            "role": "assistant",
            "content": json.dumps({
                "message": f"[TEST MODE] Error loading cache: {str(e)}",
                "choices": ["Retry", "Skip"],
            }),
        }
        finish_reason = "stop"

    return {
        "id": f"chatcmpl-mock-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(datetime.now().timestamp()),
        "model": "TEST",
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
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
