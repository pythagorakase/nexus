"""
Live inference tests for wizard accept_fate constraints.

These tests make real API calls to verify that accept_fate=True
forces tool calls instead of WizardResponse.

Run with:
    pytest tests/test_wizard_live.py -v --tb=short -k live

Or quick validation:
    python tests/test_wizard_live.py
"""

import asyncio
import logging
import os
from typing import Any, Dict, Optional

import pytest
from pydantic_ai.tools import DeferredToolRequests

from nexus.api.wizard_agent import (
    WizardContext,
    get_wizard_agent,
    _character_subphase,
)
from nexus.api.new_story_schemas import WizardResponse
from nexus.api.pydantic_ai_utils import build_pydantic_ai_model

logger = logging.getLogger(__name__)

# =============================================================================
# Test Configuration
# =============================================================================

# Phase configurations for testing
# Note: Phase 3 (traits) is deterministic with accept_fate, so not tested here
PHASE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "setting": {
        "phase": "setting",
        "context_data": None,
        "expected_tool": "submit_world_document",
        "prompt": "Create a dark fantasy world with political intrigue and ancient magic.",
    },
    "concept": {
        "phase": "character",
        "context_data": {
            "setting": {"genre": "fantasy", "world_name": "Valdoria"},
        },
        "expected_tool": "submit_character_concept",
        "prompt": "Create a reluctant hero - a former soldier haunted by past decisions.",
    },
    "wildcard": {
        "phase": "character",
        "context_data": {
            "setting": {"genre": "fantasy", "world_name": "Valdoria"},
            "character_state": {
                "concept": {
                    "name": "Kael Stormwind",
                    "archetype": "Reluctant Hero",
                    "background": "A former soldier who deserted after witnessing atrocities committed by his own side.",
                    "appearance": "Weathered face with a scar across the left cheek, grey-streaked dark hair.",
                    "suggested_traits": ["allies", "enemies", "reputation"],
                    "trait_rationales": {
                        "allies": "Fellow deserters who share his guilt",
                        "enemies": "His former commanding officers",
                        "reputation": "Known as a coward by some, a hero by others",
                    },
                },
                "trait_selection": {
                    "selected_traits": ["allies", "enemies", "reputation"],
                    "trait_rationales": {
                        "allies": "Fellow deserters who share his guilt",
                        "enemies": "His former commanding officers",
                        "reputation": "Known as a coward by some, a hero by others",
                    },
                },
            },
        },
        "expected_tool": "submit_wildcard_trait",
        "prompt": "Create a unique wildcard trait that sets this character apart.",
    },
    "seed": {
        "phase": "seed",
        "context_data": {
            "setting": {"genre": "fantasy", "world_name": "Valdoria"},
            "character": {"name": "Kael Stormwind", "archetype": "Reluctant Hero"},
        },
        "expected_tool": "submit_starting_scenario",
        "prompt": "Create a compelling starting scenario that launches the story.",
    },
}

# Models to test
TEST_MODELS = [
    "gpt-5.1",
    "claude-sonnet-4-5",
]


def make_test_context(
    phase: str,
    accept_fate: bool,
    context_data: Optional[Dict[str, Any]] = None,
) -> WizardContext:
    """Create a WizardContext for testing."""
    return WizardContext(
        slot=5,  # Test slot
        cache=None,  # Will be mocked or not needed for agent tests
        phase=phase,
        thread_id="test-thread",
        model="test",
        context_data=context_data,
        accept_fate=accept_fate,
        dev_mode=False,
        history_len=0,
        user_turns=0,
        assistant_turns=0,
    )


# =============================================================================
# Live Tests (pytest)
# =============================================================================


@pytest.fixture
def mock_db_functions(monkeypatch):
    """Mock all database functions so tests can run without PostgreSQL."""
    import nexus.api.wizard_agent as wizard_module

    # Mock record_drafts (called by all tools)
    monkeypatch.setattr(wizard_module, "record_drafts", lambda *args, **kwargs: None)

    # Mock suggested traits functions (called by concept tool)
    monkeypatch.setattr(wizard_module, "write_suggested_traits", lambda *args, **kwargs: None)
    monkeypatch.setattr(wizard_module, "clear_suggested_traits", lambda *args, **kwargs: None)

    # Mock trait menu functions (called by concept tool)
    class DummyTrait:
        def __init__(self, id, name):
            self.id = id
            self.name = name
            self.description = f"Description for {name}"
            self.is_selected = False
            self.rationale = ""

    dummy_traits = [
        DummyTrait(1, "allies"),
        DummyTrait(2, "contacts"),
        DummyTrait(3, "patron"),
    ]
    monkeypatch.setattr(wizard_module, "get_trait_menu", lambda _: dummy_traits)
    monkeypatch.setattr(wizard_module, "get_selected_trait_count", lambda _: 0)
    monkeypatch.setattr(wizard_module, "slot_dbname", lambda slot: f"save_0{slot}")


@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.parametrize("phase_name", ["setting", "concept", "wildcard", "seed"])
@pytest.mark.parametrize("model_name", TEST_MODELS)
async def test_accept_fate_forces_tool_call(phase_name: str, model_name: str, mock_db_functions):
    """
    Live test: accept_fate=True should result in a tool call, not WizardResponse.

    This test makes real API calls to verify the constraint behavior.
    Database functions are mocked so tests can run without PostgreSQL.
    """
    config = PHASE_CONFIGS[phase_name]
    context = make_test_context(
        phase=config["phase"],
        accept_fate=True,
        context_data=config["context_data"],
    )

    agent = get_wizard_agent(context)
    model = build_pydantic_ai_model(model_name)

    logger.info(f"Testing {phase_name} phase with {model_name}, accept_fate=True")

    result = await agent.run(
        config["prompt"],
        deps=context,
        model=model,
    )

    # The output should be DeferredToolRequests (indicating a tool was called)
    # NOT WizardResponse (which would mean it presented choices)
    assert isinstance(result.output, DeferredToolRequests), (
        f"Expected DeferredToolRequests (tool call), got {type(result.output).__name__}. "
        f"Model {model_name} may have ignored accept_fate constraint."
    )

    # Verify the correct tool was called
    assert context.last_tool_name == config["expected_tool"], (
        f"Expected tool {config['expected_tool']}, got {context.last_tool_name}"
    )

    logger.info(
        f"✓ {phase_name}/{model_name}: Tool '{context.last_tool_name}' called successfully"
    )


@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.parametrize("phase_name", ["setting", "concept", "wildcard", "seed"])
async def test_normal_flow_allows_wizard_response(phase_name: str, mock_db_functions):
    """
    Sanity check: accept_fate=False should allow WizardResponse.

    Uses gpt-5.1 only to minimize API calls for sanity check.
    """
    config = PHASE_CONFIGS[phase_name]
    context = make_test_context(
        phase=config["phase"],
        accept_fate=False,
        context_data=config["context_data"],
    )

    agent = get_wizard_agent(context)
    model = build_pydantic_ai_model("gpt-5.1")

    logger.info(f"Testing {phase_name} phase with accept_fate=False")

    result = await agent.run(
        config["prompt"],
        deps=context,
        model=model,
    )

    # With accept_fate=False, either WizardResponse or tool call is valid
    # (the model may choose to call the tool or present options)
    assert result.output is not None, "Should have some output"

    output_type = type(result.output).__name__
    logger.info(f"✓ {phase_name}/accept_fate=False: Got {output_type}")


# =============================================================================
# Quick Validation Script (run directly)
# =============================================================================


def setup_db_mocks():
    """Apply DB mocks for quick_test (non-pytest context)."""
    import nexus.api.wizard_agent as wizard_module

    # Mock record_drafts (called by all tools)
    wizard_module.record_drafts = lambda *args, **kwargs: None

    # Mock suggested traits functions
    wizard_module.write_suggested_traits = lambda *args, **kwargs: None
    wizard_module.clear_suggested_traits = lambda *args, **kwargs: None

    # Mock trait menu functions
    class DummyTrait:
        def __init__(self, id, name):
            self.id = id
            self.name = name
            self.description = f"Description for {name}"
            self.is_selected = False
            self.rationale = ""

    dummy_traits = [DummyTrait(1, "allies"), DummyTrait(2, "contacts"), DummyTrait(3, "patron")]
    wizard_module.get_trait_menu = lambda _: dummy_traits
    wizard_module.get_selected_trait_count = lambda _: 0
    wizard_module.slot_dbname = lambda slot: f"save_0{slot}"


async def quick_test():
    """
    Quick validation script for manual testing.
    Run with: python tests/test_wizard_live.py

    Note: DB functions are mocked so this can run without PostgreSQL.
    """
    setup_db_mocks()

    print("\n" + "=" * 60)
    print("WIZARD ACCEPT_FATE LIVE TESTS")
    print("=" * 60)

    results = []

    for model_name in TEST_MODELS:
        print(f"\n--- Testing with {model_name} ---")

        for phase_name, config in PHASE_CONFIGS.items():
            context = make_test_context(
                phase=config["phase"],
                accept_fate=True,
                context_data=config["context_data"],
            )

            agent = get_wizard_agent(context)
            model = build_pydantic_ai_model(model_name)

            try:
                result = await agent.run(
                    config["prompt"],
                    deps=context,
                    model=model,
                )

                if isinstance(result.output, DeferredToolRequests):
                    tool_name = context.last_tool_name or "unknown"
                    expected = config["expected_tool"]
                    if tool_name == expected:
                        status = "✓ PASS"
                        print(f"  {phase_name}: {status} - Called {tool_name}")
                    else:
                        status = "✗ WRONG TOOL"
                        print(f"  {phase_name}: {status} - Expected {expected}, got {tool_name}")
                else:
                    status = "✗ FAIL"
                    output_type = type(result.output).__name__
                    print(f"  {phase_name}: {status} - Got {output_type} instead of tool call")

                results.append({
                    "model": model_name,
                    "phase": phase_name,
                    "status": status,
                })

            except Exception as e:
                status = "✗ ERROR"
                print(f"  {phase_name}: {status} - {e}")
                results.append({
                    "model": model_name,
                    "phase": phase_name,
                    "status": f"ERROR: {e}",
                })

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = sum(1 for r in results if "PASS" in r["status"])
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if passed < total:
        print("\nFailed tests:")
        for r in results:
            if "PASS" not in r["status"]:
                print(f"  - {r['model']}/{r['phase']}: {r['status']}")

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(quick_test())
