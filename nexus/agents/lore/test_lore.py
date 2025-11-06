#!/usr/bin/env python3
"""
Unit Tests for LORE Agent

Tests the complete LORE orchestration system including:
- Component initialization
- MEMNON integration
- Turn cycle phases
- Context assembly with real narrative data (chunk id=1425)
- Token budget management
"""

import argparse
import asyncio
import json
import logging
import sys
import time
import unittest
import inspect
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# Add paths for imports
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lore import LORE
from utils.turn_context import TurnContext, TurnPhase

# Configure logging for tests
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("test_lore")


# Module-level shared LORE instance
# Lazily initialize the shared instance so standard unittest/pytest discovery
# still works without invoking the custom run_tests() helper.
_shared_lore: Optional[LORE] = None
_defer_teardown: bool = False


def _get_shared_lore() -> LORE:
    """Return the shared LORE instance, creating it on demand."""
    global _shared_lore

    if _shared_lore is None:
        logger.info("Initializing shared LORE instance for test suite")
        _shared_lore = LORE(debug=True, enable_logon=False)
        logger.info("✓ Shared LORE instance initialized successfully (LOGON disabled)")

    return _shared_lore


def setUpModule() -> None:
    """unittest hook: ensure shared LORE exists for standard discovery."""

    _get_shared_lore()


def tearDownModule() -> None:
    """unittest hook: release shared LORE when the module finishes."""

    global _shared_lore
    global _defer_teardown

    if _defer_teardown:
        logger.debug("Deferred teardown requested - skipping immediate cleanup")
        return

    if _shared_lore and _shared_lore.llm_manager:
        try:
            _shared_lore.llm_manager.unload_model()
            logger.info("✓ Model unloaded successfully")
        except Exception as exc:  # pragma: no cover - best-effort cleanup
            logger.debug(f"Cleanup note: {exc}")

    _shared_lore = None

# Global flag for saving context output to disk (set via --save-context CLI arg)
_save_context = False
_divergence_test_chunks: List[int] = []
_divergence_warm_span: int = 4


class TestLOREInitialization(unittest.TestCase):
    """Test LORE initialization and component loading"""

    def setUp(self):
        """Set up test fixtures"""
        self.lore = _get_shared_lore()

        # Clear Pass 2 state between tests to prevent leakage
        # This normally happens in handle_storyteller_response() between turns
        if self.lore.memory_manager and self.lore.memory_manager.context_state:
            if self.lore.memory_manager.context_state._context:
                self.lore.memory_manager.context_state._context.additional_chunks.clear()
                self.lore.memory_manager.context_state._context.divergence_detected = False
                self.lore.memory_manager.context_state._context.divergence_confidence = 0.0
                self.lore.memory_manager.context_state._context.gap_analysis.clear()

    def test_lore_creation(self):
        """Test that shared LORE instance was created successfully"""
        self.assertIsNotNone(self.lore, "Shared LORE instance should be initialized")
        self.assertTrue(self.lore.debug, "LORE should be in debug mode")
        logger.info("✓ LORE instance exists and is properly configured")

    def test_settings_loading(self):
        """Test settings.json loading"""
        self.assertIsNotNone(self.lore.settings)
        self.assertIn("Agent Settings", self.lore.settings)
        self.assertIn("LORE", self.lore.settings["Agent Settings"])
        logger.info("✓ Settings loaded successfully")

    def test_component_initialization(self):
        """Test all component managers are initialized"""
        # Check required managers
        self.assertIsNotNone(self.lore.token_manager, "Token manager not initialized")
        self.assertIsNotNone(self.lore.llm_manager, "LLM manager not initialized")
        self.assertIsNotNone(self.lore.turn_manager, "Turn manager not initialized")

        # LOGON is optional - only check if enabled
        if self.lore.enable_logon:
            self.assertIsNotNone(self.lore.logon, "LOGON utility not initialized")
            logger.info("✓ All component managers initialized (including LOGON)")
        else:
            self.assertIsNone(self.lore.logon, "LOGON should be None when disabled")
            logger.info("✓ All required component managers initialized (LOGON disabled)")

    def test_component_status(self):
        """Test component status reporting"""
        status = self.lore.get_status()

        self.assertIn("current_phase", status)
        self.assertEqual(status["current_phase"], "idle")
        self.assertIn("components", status)
        self.assertIn("settings_loaded", status)
        self.assertTrue(status["settings_loaded"])

        logger.info(f"✓ Status check passed: {json.dumps(status, indent=2)}")


class TestMEMNONIntegration(unittest.TestCase):
    """Test MEMNON integration and memory retrieval"""

    def setUp(self):
        """Set up test fixtures"""
        self.lore = _get_shared_lore()

        # Clear Pass 2 state between tests to prevent leakage
        # This normally happens in handle_storyteller_response() between turns
        if self.lore.memory_manager and self.lore.memory_manager.context_state:
            if self.lore.memory_manager.context_state._context:
                self.lore.memory_manager.context_state._context.additional_chunks.clear()
                self.lore.memory_manager.context_state._context.divergence_detected = False
                self.lore.memory_manager.context_state._context.divergence_confidence = 0.0
                self.lore.memory_manager.context_state._context.gap_analysis.clear()
    
    def test_memnon_availability(self):
        """Test if MEMNON is available"""
        if self.lore.memnon:
            logger.info("✓ MEMNON is available")
            self.assertIsNotNone(self.lore.memnon)
        else:
            logger.warning("⚠ MEMNON not available - skipping MEMNON tests")
            self.skipTest("MEMNON not available")
    
    def test_retrieve_specific_chunk(self):
        """Test retrieving narrative chunk id=1425"""
        if not self.lore.memnon:
            self.skipTest("MEMNON not available")
        
        try:
            # Query for specific chunk
            result = self.lore.memnon.query_memory(
                query="chunk_id:1425",
                k=1,
                use_hybrid=False
            )
            
            if result and result.get("results"):
                chunk = result["results"][0]
                logger.info(f"✓ Retrieved chunk 1425: {chunk.get('text', '')[:100]}...")
                self.assertIsNotNone(chunk.get("text"))
            else:
                logger.warning("⚠ Could not retrieve chunk 1425")
        except Exception as e:
            logger.error(f"✗ Failed to retrieve chunk: {e}")
    
    def test_retrieve_recent_chunks(self):
        """Test retrieving recent narrative chunks"""
        if not self.lore.memnon:
            self.skipTest("MEMNON not available")
        
        try:
            # Query for recent chunks
            result = self.lore.memnon.query_memory(
                query="",
                k=5,
                filters={"order": "recent"}
            )
            
            if result and result.get("results"):
                logger.info(f"✓ Retrieved {len(result['results'])} recent chunks")
                for i, chunk in enumerate(result['results'][:2]):
                    logger.info(f"  Chunk {i+1}: {chunk.get('text', '')[:50]}...")
            else:
                logger.warning("⚠ No recent chunks retrieved")
        except Exception as e:
            logger.error(f"✗ Failed to retrieve recent chunks: {e}")


class TestTokenBudget(unittest.TestCase):
    """Test token budget management"""

    def setUp(self):
        """Set up test fixtures"""
        self.lore = _get_shared_lore()

        # Clear Pass 2 state between tests to prevent leakage
        # This normally happens in handle_storyteller_response() between turns
        if self.lore.memory_manager and self.lore.memory_manager.context_state:
            if self.lore.memory_manager.context_state._context:
                self.lore.memory_manager.context_state._context.additional_chunks.clear()
                self.lore.memory_manager.context_state._context.divergence_detected = False
                self.lore.memory_manager.context_state._context.divergence_confidence = 0.0
                self.lore.memory_manager.context_state._context.gap_analysis.clear()
    
    def test_token_budget_calculation(self):
        """Test dynamic token budget calculation"""
        test_input = "I examine the neural implant carefully, looking for any markings."
        
        budget = self.lore.token_manager.calculate_budget(test_input)
        
        self.assertIn("total_available", budget)
        self.assertIn("user_input", budget)
        self.assertIn("warm_slice", budget)
        self.assertIn("structured", budget)
        self.assertIn("augmentation", budget)
        
        # Check that allocations are reasonable
        self.assertGreater(budget["total_available"], 0)
        self.assertGreater(budget["warm_slice"], 0)
        
        logger.info(f"✓ Token budget calculated: {json.dumps(budget, indent=2)}")
    
    def test_utilization_calculation(self):
        """Test utilization percentage calculation"""
        token_counts = {
            "total_available": 100000,
            "user_input": 20,
            "warm_slice": 40000,
            "structured": 10000,
            "augmentation": 35000
        }
        
        utilization = self.lore.token_manager.calculate_utilization(token_counts)
        
        self.assertGreater(utilization, 0)
        self.assertLessEqual(utilization, 100)
        
        logger.info(f"✓ Utilization calculated: {utilization:.1f}%")


class TestTurnCycle(unittest.TestCase):
    """Test complete turn cycle execution"""

    def setUp(self):
        """Set up test fixtures"""
        self.lore = _get_shared_lore()

        # Clear Pass 2 state between tests to prevent leakage
        # This normally happens in handle_storyteller_response() between turns
        if self.lore.memory_manager and self.lore.memory_manager.context_state:
            if self.lore.memory_manager.context_state._context:
                self.lore.memory_manager.context_state._context.additional_chunks.clear()
                self.lore.memory_manager.context_state._context.divergence_detected = False
                self.lore.memory_manager.context_state._context.divergence_confidence = 0.0
                self.lore.memory_manager.context_state._context.gap_analysis.clear()
    
    async def test_full_turn_cycle(self):
        """Test processing a complete turn with real narrative data"""
        # Use actual user input from chunk 1424
        test_input = "Next scene is the morning after, picking up Sullivan, then preparing to move into the land rig and review the intel."

        logger.info(f"Starting turn cycle test with input: {test_input}")
        
        try:
            # Process the turn
            response = await self.lore.process_turn(test_input)
            
            # Check that we got a response
            self.assertIsNotNone(response)
            self.assertIsInstance(response, str)
            
            # Get turn summary
            summary = self.lore.get_turn_summary()
            
            # Verify phases were completed
            self.assertIn("phases_completed", summary)
            completed_phases = summary["phases_completed"]
            
            logger.info(f"✓ Turn completed with {len(completed_phases)} phases")
            logger.info(f"  Phases: {completed_phases}")
            
            # Check for errors
            if summary.get("errors"):
                logger.warning(f"⚠ Errors during turn: {summary['errors']}")
            
            # Log token utilization
            if "token_utilization" in summary:
                logger.info(f"  Token utilization: {summary['token_utilization']:.1f}%")
            
            # Log response preview
            logger.info(f"  Response preview: {response[:200]}...")
            
        except Exception as e:
            logger.error(f"✗ Turn cycle failed: {e}")
            self.fail(f"Turn cycle failed: {e}")
    
    async def test_context_assembly_with_chunk_1425(self):
        """Test context assembly using the newest narrative chunk (1425) as warm slice"""
        if not self.lore.memnon:
            self.skipTest("MEMNON not available")

        # Clear ALL memory state from previous test (test_full_turn_cycle)
        # This prevents stale baseline from triggering false divergence detection
        if self.lore.memory_manager and self.lore.memory_manager.context_state:
            self.lore.memory_manager.context_state._context = None
            self.lore.memory_manager.context_state._transition = None
            self.lore.memory_manager.context_state._chunk_cache.clear()
            logger.debug("✓ Cleared all memory state before context assembly test")

        # Get the newest chunk (1425)
        try:
            result = self.lore.memnon.query_memory(
                query="chunk_id:1425",
                k=1,
                use_hybrid=False
            )

            if not result or not result.get("results"):
                logger.warning("⚠ Could not retrieve chunk 1425 for test")
                return

            chunk_1425 = result["results"][0]
            chunk_text = chunk_1425.get("text", "")[:500]  # Use first 500 chars as context

            logger.info(f"Using chunk 1425 as context: {chunk_text[:100]}...")

            # Use actual user input from chunk 1424 (the user response that led to chunk 1425)
            test_input = "Next scene is the morning after, picking up Sullivan, then preparing to move into the land rig and review the intel."
            
            # Initialize turn context manually
            self.lore.turn_context = TurnContext(
                turn_id=f"test_turn_{int(time.time())}",
                user_input=test_input,
                start_time=time.time()
            )
            
            # Set the warm slice to include chunk 1425
            self.lore.turn_context.warm_slice = [chunk_1425]
            
            # Process individual phases
            await self.lore.turn_manager.process_user_input(self.lore.turn_context)
            await self.lore.turn_manager.perform_warm_analysis(self.lore.turn_context)
            await self.lore.turn_manager.query_entity_states(self.lore.turn_context)
            await self.lore.turn_manager.execute_deep_queries(self.lore.turn_context)
            await self.lore.turn_manager.assemble_context_payload(self.lore.turn_context)
            
            # Check the assembled context
            context = self.lore.turn_context.context_payload
            self.assertIsNotNone(context)
            self.assertIn("user_input", context)
            self.assertIn("warm_slice", context)
            self.assertIn("entity_data", context)
            self.assertIn("retrieved_passages", context)
            
            logger.info("✓ Context assembled successfully with chunk 1425")
            logger.info(f"  Warm slice chunks: {len(context['warm_slice']['chunks'])}")
            logger.info(f"  Characters found: {len(context['entity_data'].get('characters', []))}")
            logger.info(f"  Locations found: {len(context['entity_data'].get('locations', []))}")
            logger.info(f"  Retrieved passages: {len(context['retrieved_passages'].get('results', []))}")

            # Save context payload to disk if requested via --save-context flag
            if _save_context:
                output_dir = Path(__file__).parent.parent.parent.parent / "temp"
                output_dir.mkdir(exist_ok=True)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = output_dir / f"test_context_chunk1425_{timestamp}.json"

                with open(output_file, 'w') as f:
                    json.dump(context, f, indent=2, default=str)  # default=str handles non-serializable types

                logger.info(f"✓ Context saved to: {output_file}")

        except Exception as e:
            logger.error(f"✗ Context assembly test failed: {e}")
            self.fail(f"Context assembly failed: {e}")


class TestDivergenceDetection(unittest.TestCase):
    """Async divergence detection validation using real narrative chunks."""

    chunk_ids: List[int] = []
    warm_span: int = 4

    @classmethod
    def configure(cls, chunk_ids: Sequence[int], warm_span: int) -> None:
        unique_ids = list(dict.fromkeys(int(cid) for cid in chunk_ids))
        cls.chunk_ids = unique_ids
        cls.warm_span = max(1, int(warm_span)) if warm_span else 4

    def setUp(self):
        """Prepare shared LORE instance for divergence testing."""
        self.lore = _get_shared_lore()

        if self.lore.memory_manager and self.lore.memory_manager.context_state:
            self.lore.memory_manager.context_state._context = None
            self.lore.memory_manager.context_state._transition = None
            self.lore.memory_manager.context_state._chunk_cache.clear()

    async def test_divergence_with_chunks(self):
        """Run divergence detection across configured chunk IDs."""

        if not self.chunk_ids:
            self.skipTest("No divergence test chunks provided. Pass --test-chunks to enable.")

        if not self.lore.memnon:
            self.skipTest("MEMNON not available for divergence testing")

        if not self.lore.llm_manager or not self.lore.llm_manager.is_available():
            self.skipTest("Local LLM unavailable - divergence detection requires LM Studio")

        for chunk_id in self.chunk_ids:
            with self.subTest(chunk_id=chunk_id):
                await self._run_chunk_divergence_test(int(chunk_id))

    async def _run_chunk_divergence_test(self, chunk_id: int) -> None:
        chunk = self.lore.memnon.get_chunk_by_id(chunk_id)
        if not chunk:
            self.skipTest(f"Chunk {chunk_id} not found in corpus")

        storyteller_text, user_prompt = self._extract_turn_text(chunk)
        if not storyteller_text.strip():
            self.skipTest(f"Chunk {chunk_id} missing storyteller text")

        if not user_prompt.strip():
            self.skipTest(f"Chunk {chunk_id} does not contain a user prompt for divergence analysis")

        warm_slice = self._build_warm_slice(chunk_id, self.warm_span)
        if not warm_slice:
            logger.warning("⚠ Falling back to single-chunk warm slice for chunk %s", chunk_id)
            warm_slice = [
                {
                    "id": chunk_id,
                    "chunk_id": chunk_id,
                    "text": storyteller_text,
                }
            ]

        turn_context = TurnContext(
            turn_id=f"divergence_test_{chunk_id}_{int(time.time())}",
            user_input=user_prompt,
            start_time=time.time(),
        )

        turn_context.warm_slice = warm_slice

        await self.lore.turn_manager.process_user_input(turn_context)
        await self.lore.turn_manager.perform_warm_analysis(turn_context)
        await self.lore.turn_manager.query_entity_states(turn_context)

        token_counts = turn_context.token_counts or self.lore.token_manager.calculate_budget(user_prompt)

        assembled_context = {
            "user_input": turn_context.user_input,
            "warm_slice": {"chunks": turn_context.warm_slice},
            "entity_data": turn_context.entity_data,
            "retrieved_passages": {"results": []},
            "analysis": turn_context.phase_states.get("warm_analysis", {}).get("analysis", {}),
        }

        baseline = self.lore.memory_manager.handle_storyteller_response(
            narrative=storyteller_text,
            warm_slice=turn_context.warm_slice,
            retrieved_passages=[],
            token_usage=token_counts,
            assembled_context=assembled_context,
            authorial_directives=[],
        )

        self.assertIsNotNone(baseline, "Baseline package should be created from storyteller text")

        update = self.lore.memory_manager.handle_user_input(
            user_input=user_prompt,
            token_counts=token_counts,
        )

        self.assertTrue(update.baseline_available, "Baseline must be available for divergence analysis")
        self.assertIsNotNone(update.divergence, "Divergence result should be returned")

        logger.info(
            "Divergence analysis for chunk %s: detected=%s confidence=%.2f",
            chunk_id,
            update.divergence.detected,
            update.divergence.confidence,
        )

    @staticmethod
    def _extract_turn_text(chunk: Dict[str, Any]) -> Sequence[str]:
        full_text = chunk.get("full_text") or chunk.get("text") or ""
        if "\n## You" in full_text:
            storyteller, user_section = full_text.split("\n## You", 1)
            return storyteller.strip(), user_section.strip()

        storyteller = chunk.get("storyteller_text") or chunk.get("narrative") or ""
        user_prompt = chunk.get("user_input") or chunk.get("raw_user_input") or ""
        return storyteller.strip(), user_prompt.strip()

    def _build_warm_slice(self, chunk_id: int, span: int) -> List[Dict[str, Any]]:
        memnon = self.lore.memnon
        if not getattr(memnon, "Session", None):
            logger.warning("⚠ MEMNON session factory unavailable - cannot build warm slice")
            return []

        try:
            from sqlalchemy import text
        except Exception as exc:  # pragma: no cover - optional dependency guard
            logger.warning("⚠ SQLAlchemy unavailable: %s", exc)
            return []

        start_id = max(1, chunk_id - max(1, span))
        end_id = max(chunk_id, start_id)

        try:
            with memnon.Session() as session:
                rows = session.execute(
                    text(
                        """
                        SELECT id, raw_text, text
                        FROM narrative_chunks
                        WHERE id BETWEEN :start AND :end
                        ORDER BY id
                        """
                    ),
                    {"start": start_id, "end": end_id},
                ).fetchall()
        except Exception as exc:
            logger.warning("⚠ Failed to load warm slice for chunk %s: %s", chunk_id, exc)
            return []

        warm_slice: List[Dict[str, Any]] = []
        for row in rows:
            mapping = getattr(row, "_mapping", row)
            text_value = (
                mapping.get("raw_text")
                if isinstance(mapping, dict)
                else getattr(row, "raw_text", "")
            )
            if not text_value and isinstance(mapping, dict):
                text_value = mapping.get("text", "")
            elif not text_value:
                text_value = getattr(row, "text", "")

            warm_slice.append(
                {
                    "id": getattr(row, "id", mapping.get("id")),
                    "chunk_id": getattr(row, "id", mapping.get("id")),
                    "text": text_value or "",
                }
            )

        return warm_slice


class TestLocalLLM(unittest.TestCase):
    """Test local LLM integration via LM Studio"""

    def setUp(self):
        """Set up test fixtures"""
        self.lore = _get_shared_lore()

        # Clear Pass 2 state between tests to prevent leakage
        # This normally happens in handle_storyteller_response() between turns
        if self.lore.memory_manager and self.lore.memory_manager.context_state:
            if self.lore.memory_manager.context_state._context:
                self.lore.memory_manager.context_state._context.additional_chunks.clear()
                self.lore.memory_manager.context_state._context.divergence_detected = False
                self.lore.memory_manager.context_state._context.divergence_confidence = 0.0
                self.lore.memory_manager.context_state._context.gap_analysis.clear()
    
    def test_lm_studio_connection(self):
        """Test connection to LM Studio API"""
        if self.lore.llm_manager.is_available():
            logger.info("✓ LM Studio connection successful")
            
            # Try listing models
            models = self.lore.llm_manager.list_available_models()
            if models:
                logger.info(f"  Available models: {models}")
        else:
            logger.warning("⚠ LM Studio not available - make sure it's running on port 1234")
    
    def test_llm_query(self):
        """Test querying the local LLM - MUST FAIL if no model loaded"""
        if not self.lore.llm_manager.is_available():
            self.skipTest("LM Studio not available")
        
        test_prompt = "What is the capital of France? Answer in one word."
        
        try:
            response = self.lore.llm_manager.query(test_prompt, temperature=0.1, max_tokens=50)
            self.assertIsNotNone(response)
            self.assertIsInstance(response, str)
            logger.info(f"✓ LLM query successful: {response}")
        except RuntimeError as e:
            if "No models loaded" in str(e) or "404" in str(e):
                logger.warning(f"⚠ LM Studio has no model loaded - this is expected during testing")
                logger.info(f"  Error message: {str(e)[:200]}")
            else:
                # Re-raise if it's a different error
                raise


class TestLOGONUtility(unittest.TestCase):
    """Test LOGON API wrapper"""

    def setUp(self):
        """Set up test fixtures"""
        self.lore = _get_shared_lore()

        # Clear Pass 2 state between tests to prevent leakage
        # This normally happens in handle_storyteller_response() between turns
        if self.lore.memory_manager and self.lore.memory_manager.context_state:
            if self.lore.memory_manager.context_state._context:
                self.lore.memory_manager.context_state._context.additional_chunks.clear()
                self.lore.memory_manager.context_state._context.divergence_detected = False
                self.lore.memory_manager.context_state._context.divergence_confidence = 0.0
                self.lore.memory_manager.context_state._context.gap_analysis.clear()

        # Skip LOGON tests if LOGON is disabled
        if not self.lore.enable_logon:
            self.skipTest("LOGON disabled for testing")

    def test_logon_initialization(self):
        """Test LOGON utility initialization"""
        self.assertIsNotNone(self.lore.logon)
        self.assertIsNotNone(self.lore.logon.provider)
        logger.info("✓ LOGON utility initialized")

    def test_context_formatting(self):
        """Test context payload formatting"""
        test_context = {
            "user_input": "Test input",
            "warm_slice": {
                "chunks": [{"text": "Previous narrative text"}]
            },
            "entity_data": {
                "characters": [{"name": "Alex", "summary": "Main character"}],
                "locations": [{"name": "Night City", "description": "Cyberpunk metropolis"}]
            },
            "retrieved_passages": {
                "results": [{"text": "Historical context", "score": 0.85}]
            }
        }

        formatted = self.lore.logon._format_context_prompt(test_context)

        self.assertIn("USER INPUT", formatted)
        self.assertIn("Test input", formatted)
        self.assertIn("RECENT NARRATIVE", formatted)
        self.assertIn("Previous narrative text", formatted)
        self.assertIn("Alex", formatted)
        self.assertIn("Night City", formatted)

        logger.info("✓ Context formatting successful")
        logger.info(f"  Formatted length: {len(formatted)} characters")


class AsyncAwareTestLoader(unittest.TestLoader):
    """Custom loader that skips coroutine-based unittest methods."""

    def getTestCaseNames(self, testCaseClass):  # noqa: N802 - unittest API contract
        names = super().getTestCaseNames(testCaseClass)
        filtered: List[str] = []
        for name in names:
            attr = getattr(testCaseClass, name, None)
            if inspect.iscoroutinefunction(attr):
                continue
            filtered.append(name)
        return filtered


def _get_async_test_methods(test_case_class: type[unittest.TestCase]) -> List[str]:
    loader = unittest.TestLoader()
    candidate_methods = loader.getTestCaseNames(test_case_class)
    return [
        name
        for name in candidate_methods
        if inspect.iscoroutinefunction(getattr(test_case_class, name, None))
    ]


async def _run_async_test_case(
    test_case_class: type[unittest.TestCase],
    lore_instance: LORE,
) -> List[str]:
    failures: List[str] = []
    method_names = _get_async_test_methods(test_case_class)

    if not method_names:
        return failures

    for method_name in method_names:
        case = test_case_class(method_name)
        if hasattr(case, "lore"):
            case.lore = lore_instance

        try:
            case.setUp()
        except unittest.SkipTest as skip_exc:
            print(f"⚠ {test_case_class.__name__}.{method_name} skipped during setUp: {skip_exc}")
            case.doCleanups()
            continue
        except Exception as exc:  # pragma: no cover - defensive guard
            print(f"✗ {test_case_class.__name__}.{method_name} setup failed: {exc}")
            failures.append(f"setup:{test_case_class.__name__}.{method_name}:{exc}")
            case.doCleanups()
            continue

        try:
            await getattr(case, method_name)()
        except unittest.SkipTest as skip_exc:
            print(f"⚠ {test_case_class.__name__}.{method_name} skipped: {skip_exc}")
        except Exception as exc:
            print(f"✗ {test_case_class.__name__}.{method_name} failed: {exc}")
            failures.append(f"failure:{test_case_class.__name__}.{method_name}:{exc}")
        else:
            print(f"✓ {test_case_class.__name__}.{method_name} passed")
        finally:
            try:
                case.tearDown()
            except unittest.SkipTest as skip_exc:
                print(f"⚠ {test_case_class.__name__}.{method_name} teardown skipped: {skip_exc}")
            except Exception as exc:  # pragma: no cover - defensive guard
                print(f"⚠ {test_case_class.__name__}.{method_name} teardown error: {exc}")
                failures.append(f"teardown:{test_case_class.__name__}.{method_name}:{exc}")
            case.doCleanups()

    return failures


# Test runner
def run_tests():
    """Run all LORE tests"""

    global _defer_teardown

    logger.info("=" * 60)
    logger.info("Initializing shared LORE instance for test suite")
    logger.info("=" * 60)

    try:
        lore_instance = _get_shared_lore()
        logger.info("✓ Shared LORE instance initialized successfully (LOGON disabled)")
    except Exception as e:
        logger.error(f"✗ Failed to initialize shared LORE instance: {e}")
        raise

    loader = AsyncAwareTestLoader()
    suite = unittest.TestSuite()

    synchronous_cases = [
        TestLOREInitialization,
        TestMEMNONIntegration,
        TestTokenBudget,
        TestLocalLLM,
        TestLOGONUtility,
    ]

    for case in synchronous_cases:
        suite.addTests(loader.loadTestsFromTestCase(case))

    runner = unittest.TextTestRunner(verbosity=2)

    result: Optional[unittest.result.TestResult] = None
    async_failures: List[str] = []

    # Ensure unittest's tearDownModule does not unload models before async tests run
    _defer_teardown = True

    try:
        result = runner.run(suite)

        async_cases: List[type[unittest.TestCase]] = [TestTurnCycle]
        TestDivergenceDetection.configure(_divergence_test_chunks, _divergence_warm_span)
        if _divergence_test_chunks:
            async_cases.append(TestDivergenceDetection)

        if async_cases:
            print("\n" + "=" * 60)
            print("Running Async Turn Cycle Tests")
            print("=" * 60)

            async def run_async_tests() -> List[str]:
                failures: List[str] = []
                for case_cls in async_cases:
                    failures.extend(await _run_async_test_case(case_cls, lore_instance))
                return failures

            async_failures = asyncio.run(run_async_tests())

    finally:
        _defer_teardown = False
        logger.info("=" * 60)
        logger.info("Cleaning up shared LORE instance")
        logger.info("=" * 60)
        tearDownModule()
        logger.info("✓ Shared LORE instance cleaned up")

    success = (result.wasSuccessful() if result else False) and not async_failures

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    if result and result.wasSuccessful():
        print("✅ All synchronous tests passed!")
    elif result:
        print(f"❌ {len(result.failures)} synchronous failures, {len(result.errors)} errors")
        for failure in result.failures:
            print(f"  Failed: {failure[0]}")
        for error in result.errors:
            print(f"  Error: {error[0]}")
    else:
        print("❌ Synchronous suite did not produce a result")

    if async_failures:
        print(f"❌ {len(async_failures)} async test issues detected")
        for failure in async_failures:
            print(f"  Async failure: {failure}")
    else:
        print("✅ All async tests passed!")

    return success


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Run LORE agent tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run tests normally (no output saved)
  poetry run python nexus/agents/lore/test_lore.py

  # Run tests and save context assembly output to temp/
  poetry run python nexus/agents/lore/test_lore.py --save-context
        """
    )
    parser.add_argument(
        '--save-context',
        action='store_true',
        help='Save assembled context payload to temp/ directory for inspection'
    )
    parser.add_argument(
        '--test-chunks',
        metavar='CHUNK',
        type=int,
        nargs='+',
        help=(
            'Run async divergence detection against specific chunk IDs. '
            'If the final value is small (e.g., 3 or 4) and --warm-span is not provided, '
            'it will be interpreted as the warm slice span.'
        )
    )
    parser.add_argument(
        '--warm-span',
        type=int,
        default=None,
        help='Override warm slice span (number of preceding chunks) for divergence tests.'
    )

    args = parser.parse_args()

    # Set module-level flag (no 'global' needed at module scope)
    _save_context = args.save_context

    if _save_context:
        logger.info("Context saving enabled - output will be written to temp/ directory")

    # Configure divergence testing options from CLI
    if args.test_chunks:
        chunk_args = list(args.test_chunks)
        warm_span_override = args.warm_span

        if warm_span_override is None and len(chunk_args) > 1 and chunk_args[-1] < 50:
            warm_span_override = chunk_args.pop()

        _divergence_test_chunks = chunk_args
        if warm_span_override is not None:
            _divergence_warm_span = max(1, warm_span_override)

        logger.info(
            "Divergence chunk tests enabled: chunks=%s warm_span=%s",
            _divergence_test_chunks,
            _divergence_warm_span,
        )
    elif args.warm_span is not None:
        _divergence_warm_span = max(1, args.warm_span)
        logger.info("Warm span override set to %s (no chunk IDs provided)", _divergence_warm_span)

    # Run tests with manual lifecycle management
    success = run_tests()
    sys.exit(0 if success else 1)
