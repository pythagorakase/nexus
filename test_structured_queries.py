#!/usr/bin/env python3
"""Test structured output for retrieval queries"""

import sys
import json
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from nexus.agents.lore.utils.local_llm import LocalLLMManager

def test_structured_queries():
    print("Testing structured output for retrieval queries...")

    # Load settings
    settings_path = Path(__file__).parent / "settings.json"
    with open(settings_path) as f:
        settings = json.load(f)

    llm = LocalLLMManager(settings)

    # Load LORE system prompt - NO FALLBACK as per user directive
    prompt_path = Path(__file__).parent / "nexus/agents/lore/lore_system_prompt.md"
    if not prompt_path.exists():
        print(f"ERROR: LORE system prompt not found at {prompt_path}")
        print("Cannot proceed without system prompt (no fallbacks allowed)")
        return False

    with open(prompt_path) as f:
        llm.system_prompt = f.read()

    # Mock context analysis
    context_analysis = {
        "characters": ["Alex", "Sullivan"],
        "locations": ["The Land Rig"],
        "context_type": "action",
        "entities_for_retrieval": ["Dynacorp", "Frederick Zhao"]
    }

    user_input = "Continue."

    try:
        queries = llm.generate_retrieval_queries(context_analysis, user_input)
        print(f"\nSuccess! Generated {len(queries)} queries:")
        for i, query in enumerate(queries, 1):
            print(f"  {i}. {query}")  # Show cleaned queries

        # Verify we got 3-5 queries as specified
        assert 3 <= len(queries) <= 5, f"Expected 3-5 queries, got {len(queries)}"
        print("\n✅ Structured output validation passed!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False

    return True

if __name__ == "__main__":
    success = test_structured_queries()
    sys.exit(0 if success else 1)