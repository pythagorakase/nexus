#!/usr/bin/env python3
"""Test GPT-5 narrative generation with full output"""

import sys
import os
import json
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from scripts.api_openai import OpenAIProvider
from nexus.agents.lore.logon_schemas import StoryTurnResponse

def test_full_narrative():
    """Test GPT-5 with a more substantial prompt"""

    # Load settings
    settings_path = Path(__file__).parent / "settings.json"
    with open(settings_path) as f:
        settings = json.load(f)

    apex_settings = settings.get("API Settings", {}).get("apex", {})

    print("=" * 80)
    print("GPT-5 FULL NARRATIVE TEST")
    print("=" * 80)
    print(f"\nSettings:")
    print(f"  Model: {apex_settings.get('model', 'gpt-5')}")
    print(f"  Reasoning effort: {apex_settings.get('reasoning_effort', 'high')}")
    print(f"  Max output tokens: {apex_settings.get('max_output_tokens', 25000)}")

    # Initialize provider
    provider = OpenAIProvider(
        model=apex_settings.get("model", "gpt-5"),
        reasoning_effort=apex_settings.get("reasoning_effort", "high"),
        max_output_tokens=apex_settings.get("max_output_tokens", 25000)
    )

    # More substantial prompt that should generate longer output
    narrative_prompt = """=== RECENT NARRATIVE ===
Alex stood at the edge of the digital wasteland, watching the neon lights flicker in the distance. The city's neural network pulsed with data streams visible only through their augmented vision. Behind them, Emilia checked her weapons while Sullivan monitored the security feeds.

"The Nexus is compromised," Sullivan said, his voice crackling through the encrypted comm channel. "We have maybe ten minutes before they trace our location."

The abandoned server farm stretched before them, a graveyard of obsolete technology that might hold the key to understanding the anomaly. Strange signals had been emanating from deep within, patterns that shouldn't exist in dead hardware.

=== USER INPUT ===
Alex decides to lead the team into the server farm, searching for the source of the signal while avoiding corporate security drones. They need to uncover what's happening before it's too late.

=== INSTRUCTIONS ===
Continue this cyberpunk narrative with rich detail and atmosphere. Include:
- Vivid sensory descriptions of the environment
- Character interactions and dialogue
- Building tension as they explore
- At least 3-4 substantial paragraphs
- Approximately 400-500 words

Focus on creating an immersive, cinematic scene that advances the plot."""

    try:
        print("\nCalling GPT-5 API for narrative generation...")
        parsed_response, llm_response = provider.get_structured_completion(
            narrative_prompt,
            StoryTurnResponse
        )

        print(f"\n✅ API Response received!")
        print(f"\n" + "=" * 80)
        print("RESPONSE METRICS")
        print("=" * 80)
        print(f"Input tokens: {llm_response.input_tokens}")
        print(f"Output tokens: {llm_response.output_tokens}")
        print(f"Model: {llm_response.model}")

        if parsed_response and parsed_response.narrative:
            narrative_text = parsed_response.narrative.text
            print(f"\n" + "=" * 80)
            print("NARRATIVE STATISTICS")
            print("=" * 80)
            print(f"Total characters: {len(narrative_text)}")
            print(f"Total words: {len(narrative_text.split())}")
            paragraphs = [p for p in narrative_text.split('\n\n') if p.strip()]
            print(f"Total paragraphs: {len(paragraphs)}")

            print(f"\n" + "=" * 80)
            print("FULL NARRATIVE OUTPUT")
            print("=" * 80)
            print(narrative_text)

            if parsed_response.metadata:
                print(f"\n" + "=" * 80)
                print("METADATA")
                print("=" * 80)
                print(f"Type: {type(parsed_response.metadata).__name__}")
                metadata_dict = parsed_response.metadata.dict() if hasattr(parsed_response.metadata, 'dict') else {}
                for key, value in metadata_dict.items():
                    if value is not None:
                        print(f"  {key}: {value}")

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_full_narrative()