#!/usr/bin/env python
"""Test script to verify LORE integration with the REST API."""

import asyncio
import logging
import json
from typing import Optional
import httpx

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Silence some verbose loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

API_BASE_URL = "http://localhost:8000"

async def test_lore_integration():
    """Test that LORE can process turns through the REST API."""

    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=120.0) as client:
        try:
            # Step 1: Create a session
            logger.info("Creating story session...")
            response = await client.post(
                "/api/story/session/create",
                json={
                    "session_name": "LORE Integration Test",
                    "initial_context": "A mysterious signal emanates from deep within The Silo."
                }
            )

            if response.status_code != 200:
                logger.error(f"Failed to create session: {response.text}")
                return False

            session_data = response.json()
            session_id = session_data["session_id"]
            logger.info(f"✅ Session created: {session_id}")

            # Step 2: Process a turn with LORE
            logger.info("Processing turn with LORE (this may take a moment)...")
            response = await client.post(
                "/api/story/turn",
                json={
                    "session_id": session_id,
                    "user_input": "Alex investigates the signal's origin.",
                    "options": {"temperature": 0.8}
                }
            )

            if response.status_code != 200:
                logger.error(f"Failed to process turn: {response.text}")
                return False

            turn_response = response.json()

            # Verify we got narrative text
            if "narrative" not in turn_response or "text" not in turn_response["narrative"]:
                logger.error(f"Invalid response structure: {json.dumps(turn_response, indent=2)}")
                return False

            narrative_text = turn_response["narrative"]["text"]
            logger.info(f"✅ LORE generated narrative ({len(narrative_text)} chars)")
            logger.info(f"Narrative preview: {narrative_text[:200]}...")

            # Step 3: Check turn history
            logger.info("Verifying turn was saved...")
            response = await client.get(f"/api/story/history/{session_id}?limit=5&offset=0")

            if response.status_code != 200:
                logger.error(f"Failed to get history: {response.text}")
                return False

            history = response.json()
            if history["total"] < 1:
                logger.error("No turns in history")
                return False

            logger.info(f"✅ Turn saved in history (total: {history['total']})")

            # Step 4: Test regeneration
            logger.info("Testing turn regeneration...")
            response = await client.post(
                "/api/story/regenerate",
                json={
                    "session_id": session_id,
                    "options": {"temperature": 0.9}
                }
            )

            if response.status_code != 200:
                logger.error(f"Failed to regenerate: {response.text}")
                return False

            regen_response = response.json()
            regen_text = regen_response["narrative"]["text"]

            if regen_text == narrative_text:
                logger.warning("⚠️ Regenerated text is identical (may need higher temperature)")
            else:
                logger.info(f"✅ Regeneration produced different narrative")

            # Step 5: Check context was saved (if available)
            logger.info("Checking for saved context...")
            response = await client.get(f"/api/story/context/{session_id}")

            if response.status_code == 200:
                context = response.json()
                logger.info(f"✅ Context saved with {len(context)} keys")
                if "turn_id" in context:
                    logger.info(f"  Turn ID: {context['turn_id']}")
                if "warm_slice" in context:
                    logger.info(f"  Warm slice available")
                if "token_counts" in context:
                    logger.info(f"  Token counts tracked")
            else:
                logger.info("ℹ️ No context available (expected for minimal LORE)")

            # Step 6: Clean up - delete session
            logger.info("Cleaning up test session...")
            response = await client.delete(f"/api/story/session/{session_id}")
            if response.status_code == 200:
                logger.info(f"✅ Session deleted")

            logger.info("\n" + "="*60)
            logger.info("🎉 LORE INTEGRATION TEST PASSED!")
            logger.info("="*60)

            return True

        except httpx.ConnectError:
            logger.error("❌ Could not connect to API server at %s", API_BASE_URL)
            logger.error("Please start the server with: uvicorn nexus.api.storyteller:app")
            return False
        except Exception as e:
            logger.error(f"❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()
            return False

async def main():
    """Main entry point."""
    logger.info("Starting LORE integration test...")
    logger.info("="*60)

    success = await test_lore_integration()

    if not success:
        logger.error("\n❌ LORE integration test failed")
        return 1

    return 0

if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))