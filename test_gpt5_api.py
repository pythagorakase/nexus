#!/usr/bin/env python3
"""Test GPT-5 API directly"""

import sys
import os
import json
from pathlib import Path

# Add scripts directory to path
sys.path.append(str(Path(__file__).parent))

from scripts.api_openai import OpenAIProvider
from nexus.agents.lore.logon_schemas import StoryTurnResponse

def test_gpt5_api():
    """Test GPT-5 API with structured output"""

    # Load settings
    settings_path = Path(__file__).parent / "settings.json"
    with open(settings_path) as f:
        settings = json.load(f)

    apex_settings = settings.get("API Settings", {}).get("apex", {})

    print("=" * 60)
    print("GPT-5 API TEST")
    print("=" * 60)
    print(f"\nSettings:")
    print(f"  Model: {apex_settings.get('model', 'gpt-5')}")
    print(f"  Reasoning effort: {apex_settings.get('reasoning_effort', 'high')}")
    print(f"  Max output tokens: {apex_settings.get('max_output_tokens', 25000)}")

    # Initialize provider
    print("\n1. Initializing OpenAI provider...")
    try:
        provider = OpenAIProvider(
            model=apex_settings.get("model", "gpt-5"),
            reasoning_effort=apex_settings.get("reasoning_effort", "high"),
            max_output_tokens=apex_settings.get("max_output_tokens", 25000)
        )
        print("   ✓ Provider initialized")
    except Exception as e:
        print(f"   ✗ Failed to initialize: {e}")
        return

    # Test with a simple prompt
    print("\n2. Testing GPT-5 with structured output...")

    simple_prompt = """Continue this narrative:

=== RECENT NARRATIVE ===
Alex stood at the edge of the digital wasteland, watching the neon lights flicker in the distance.

=== USER INPUT ===
Continue.

=== INSTRUCTIONS ===
Write a brief continuation (1-2 paragraphs) of this cyberpunk narrative.
"""

    try:
        print("   Calling API (this may take 30+ seconds for reasoning)...")
        parsed_response, llm_response = provider.get_structured_completion(
            simple_prompt,
            StoryTurnResponse
        )

        print("   ✓ API call successful!")
        print(f"\n3. Response details:")
        print(f"   Input tokens: {llm_response.input_tokens}")
        print(f"   Output tokens: {llm_response.output_tokens}")
        print(f"   Model: {llm_response.model}")

        if parsed_response:
            print(f"\n4. Structured response received:")
            print(f"   Narrative length: {len(parsed_response.narrative.text)} chars")
            print(f"   Has metadata: {parsed_response.metadata is not None}")
            if parsed_response.metadata:
                # Check for available metadata fields
                print(f"   Metadata type: {type(parsed_response.metadata).__name__}")
                if hasattr(parsed_response.metadata, 'scene_marker'):
                    print(f"   Has scene marker: {parsed_response.metadata.scene_marker is not None}")
                if hasattr(parsed_response.metadata, 'word_count'):
                    print(f"   Word count: {parsed_response.metadata.word_count}")
            print(f"\n   First 200 chars of narrative:")
            print(f"   {parsed_response.narrative.text[:200]}...")

    except Exception as e:
        print(f"   ✗ API call failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_gpt5_api()