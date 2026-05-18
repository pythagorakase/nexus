#!/usr/bin/env python
"""
Simple test to demonstrate generic local LLM delegation with visible logging.
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from nexus.agents.lore.utils.local_llm import LocalLLMManager


def main():
    print("=" * 70)
    print("LORE LOCAL LLM DELEGATION - VISIBLE LOGGING TEST")
    print("=" * 70)

    # Load settings
    with open("tests/test_lore/lore_test_settings.json") as f:
        settings = json.load(f)

    prompt_path = (
        Path(__file__).parent.parent.parent
        / "nexus"
        / "agents"
        / "lore"
        / "lore_system_prompt.md"
    )
    with open(prompt_path, "r") as f:
        system_prompt = f.read()

    # Create manager
    manager = LocalLLMManager(settings, system_prompt=system_prompt)
    print(f"\n✅ Connected to LM Studio")
    print(f"   Model: {manager.loaded_model_id}")

    # Test 1: Simple semantic query
    print("\n" + "=" * 70)
    print("TEST 1: SEMANTIC DELEGATION")
    print("=" * 70)

    prompt = """You are analyzing a narrative. The user asks: "What happened when Victor betrayed Alex?"

Based on this query, identify:
1. Key entities to search for
2. The narrative context type 
3. Natural language queries to find relevant content

Respond in natural language."""

    print("\nPROMPT SENT TO LLM:")
    print("-" * 40)
    print(prompt)
    print("-" * 40)

    response = manager.query(prompt, temperature=0.7, max_tokens=300)

    print("\nLLM RESPONSE:")
    print("-" * 40)
    if response:
        # Clean up any channel markers if present
        clean_response = (
            response.replace("<|channel|>", "[")
            .replace("<|message|>", "] ")
            .replace("<|end|>", "\n")
        )
        print(clean_response[:500])
    else:
        print("No response received")
    print("-" * 40)

    print("\nLocal retrieval query generation has been removed from this manager.")


if __name__ == "__main__":
    main()
