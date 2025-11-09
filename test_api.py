#!/usr/bin/env python
"""Test script to verify the REST API can start and handle basic requests."""

import asyncio
import logging
from fastapi.testclient import TestClient
import sys

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    """Test the API endpoints."""
    try:
        # Import the app
        from nexus.api.storyteller import app

        # Create test client
        client = TestClient(app)

        # Test 1: Create session
        logger.info("Testing session creation...")
        response = client.post(
            "/api/story/session/create",
            json={
                "session_name": "Test Session",
                "initial_context": "This is a test story"
            }
        )
        if response.status_code != 200:
            logger.error(f"Session creation failed: {response.text}")
            return False

        session_data = response.json()
        session_id = session_data.get("session_id")
        logger.info(f"Session created: {session_id}")

        # Test 2: List sessions
        logger.info("Testing list sessions...")
        response = client.get("/api/story/sessions")
        assert response.status_code == 200
        sessions = response.json()
        assert len(sessions) > 0
        logger.info(f"Found {len(sessions)} sessions")

        logger.info("✅ All tests passed!")
        return True

    except ImportError as e:
        logger.error(f"Failed to import API: {e}")
        return False
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)