#!/usr/bin/env python3
"""
Live test for StorySeedSubmission schema against real LLMs.

Tests the two-phase seed generation by invoking the wizard agent
with accept_fate=True to force immediate schema submission.

Usage:
    python tests/live_seed_schema_test.py
"""

import asyncio
import json
import logging
import sys
from typing import Any, Dict

from pydantic_ai.tools import DeferredToolRequests

# Configure logging BEFORE imports that use it
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("live_seed_test")

# Reduce noise from other loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

from nexus.api.wizard_agent import WizardContext, get_wizard_agent
from nexus.api.pydantic_ai_utils import build_pydantic_ai_model
from nexus.api.new_story_schemas import StorySeedSubmission, WizardResponse


# Test context data - minimal setting and character to enable seed phase
TEST_CONTEXT = {
    "setting": {
        "genre": "cyberpunk",
        "world_name": "Neon Palimpsest",
        "time_period": "Late 21st century",
        "tech_level": "near_future",
        "tone": "dark",
        "themes": ["memory and identity", "surveillance", "corporate feudalism"],
        "magic_exists": False,
        "political_structure": "Corporate syndicates under hollowed-out international council",
        "major_conflict": "War between surveillance states and ghost networks",
        "cultural_notes": "Multiple overlapping identities, reputation scores matter more than currency",
        "geographic_scope": "continental",
    },
    "character": {
        "name": "Kade Imani",
        "archetype": "Amnesiac data-smuggler",
        "background": "Woke three months ago with no memory and a warning not to trust their own record",
        "appearance": "Medium height, wiry build, neural mesh scars at temples",
        "summary": "A former Syndicate asset turned Ghost operative with no memory of either life",
    },
}

TEST_MODELS = ["gpt-5.1", "claude-sonnet-4-5"]

SEED_PROMPT = """Create a compelling story opening for this cyberpunk setting and character.

The protagonist is Kade Imani, an amnesiac data-smuggler in Neon Palimpsest - a dark
cyberpunk megacity where corporate syndicates war with underground ghost networks over
identity data.

Generate a StorySeedSubmission with:
1. A seed with an engaging opening scenario, stakes, and hidden secrets
2. A location_sketch describing WHERE the story begins - include mood, physical details,
   and an Earth-analog hint for geography (e.g., "like the industrial Rhine-Ruhr region"
   or "think rain-soaked Seattle")

Make it atmospheric and noir. The location should feel lived-in and dangerous."""


def make_test_context(model: str, accept_fate: bool = True) -> WizardContext:
    """Create a WizardContext for seed phase testing."""
    return WizardContext(
        slot=5,
        cache=None,
        phase="seed",
        thread_id="test-live-seed",
        model=model,
        context_data=TEST_CONTEXT,
        accept_fate=accept_fate,
        dev_mode=False,
        history_len=0,
        user_turns=0,
        assistant_turns=0,
    )


def setup_db_mocks():
    """Mock database functions so we don't need PostgreSQL."""
    import nexus.api.wizard_agent as wizard_module

    wizard_module.record_drafts = lambda *args, **kwargs: None
    wizard_module.slot_dbname = lambda slot: f"save_0{slot}"


async def test_model(model_name: str) -> Dict[str, Any]:
    """Test a single model and return results."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Testing {model_name}")
    logger.info(f"{'='*60}")

    context = make_test_context(model_name, accept_fate=True)
    agent = get_wizard_agent(context)
    model = build_pydantic_ai_model(model_name)

    result = {
        "model": model_name,
        "success": False,
        "output_type": None,
        "tool_called": None,
        "error": None,
        "raw_data": None,
    }

    try:
        agent_result = await agent.run(
            SEED_PROMPT,
            deps=context,
            model=model,
        )

        output = agent_result.output
        result["output_type"] = type(output).__name__

        if isinstance(output, DeferredToolRequests):
            result["tool_called"] = context.last_tool_name
            result["raw_data"] = context.last_tool_result

            if context.last_tool_name == "submit_starting_scenario":
                result["success"] = True
                data = context.last_tool_result.get("data", {})

                # Log the generated content
                seed = data.get("seed", {})
                sketch = data.get("location_sketch", "")

                logger.info(f"\n--- SEED ---")
                logger.info(f"Title: {seed.get('title', 'N/A')}")
                logger.info(f"Type: {seed.get('seed_type', 'N/A')}")
                logger.info(f"Situation: {seed.get('situation', 'N/A')[:200]}...")
                logger.info(f"Stakes: {seed.get('stakes', 'N/A')[:150]}...")
                logger.info(f"Secrets length: {len(seed.get('secrets', ''))}")

                logger.info(f"\n--- LOCATION SKETCH ---")
                logger.info(f"{sketch[:500]}...")

                logger.info(f"\n--- VALIDATION ---")
                logger.info(f"requires_set_design: {context.last_tool_result.get('requires_set_design')}")
                logger.info(f"phase_complete: {context.last_tool_result.get('phase_complete')}")
            else:
                result["error"] = f"Wrong tool called: {context.last_tool_name}"
                logger.error(f"Wrong tool: expected submit_starting_scenario, got {context.last_tool_name}")

        elif isinstance(output, WizardResponse):
            result["error"] = "Got WizardResponse instead of tool call (accept_fate should force tool)"
            logger.error(f"WizardResponse returned instead of tool call:")
            logger.error(f"Message: {output.message[:200]}...")
            logger.error(f"Choices: {output.choices}")

        else:
            result["error"] = f"Unexpected output type: {type(output)}"
            logger.error(f"Unexpected output: {output}")

    except Exception as e:
        result["error"] = str(e)
        logger.exception(f"Error testing {model_name}")

    return result


async def main():
    setup_db_mocks()

    logger.info("=" * 60)
    logger.info("LIVE SEED SCHEMA TEST")
    logger.info("Testing StorySeedSubmission against real LLMs")
    logger.info("=" * 60)

    results = []
    for model_name in TEST_MODELS:
        result = await test_model(model_name)
        results.append(result)
        logger.info(f"\n{model_name}: {'PASS' if result['success'] else 'FAIL'}")
        if result["error"]:
            logger.info(f"  Error: {result['error']}")

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)

    passed = sum(1 for r in results if r["success"])
    logger.info(f"Passed: {passed}/{len(results)}")

    for r in results:
        status = "PASS" if r["success"] else "FAIL"
        logger.info(f"  {r['model']}: {status}")
        if r["error"]:
            logger.info(f"    Error: {r['error']}")

    return results


if __name__ == "__main__":
    asyncio.run(main())
