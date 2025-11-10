#!/usr/bin/env python3
"""Test structured output from Storyteller API"""

import json
import httpx
import time

# Configuration
API_BASE = "http://localhost:8000"
TIMEOUT = 30.0  # Shorter timeout for testing

def test_structured_output():
    """Test that the API returns proper structured output"""

    print("=" * 60)
    print("STRUCTURED OUTPUT TEST")
    print("=" * 60)

    with httpx.Client(base_url=API_BASE, timeout=TIMEOUT) as client:
        # 1. Create session
        print("\n1. Creating session...")
        response = client.post("/api/story/session/create", json={})
        response.raise_for_status()
        session_data = response.json()
        session_id = session_data["session_id"]
        print(f"   ✓ Session created: {session_id}")

        # 2. Send a turn with short input to get faster response
        print("\n2. Sending turn to LORE...")
        turn_data = {
            "session_id": session_id,
            "user_input": "Continue."  # Minimal input for faster processing
        }

        start_time = time.time()
        response = client.post("/api/story/turn", json=turn_data)
        elapsed = time.time() - start_time

        print(f"   Response time: {elapsed:.2f}s")
        print(f"   Status code: {response.status_code}")

        # 3. Analyze the response
        if response.status_code == 200:
            data = response.json()
            print("\n3. Response structure:")
            print(f"   Top-level keys: {list(data.keys())}")

            # Check for structured response fields
            if "narrative" in data:
                narrative = data["narrative"]
                print(f"\n   Narrative keys: {list(narrative.keys()) if isinstance(narrative, dict) else 'string'}")
                if isinstance(narrative, dict):
                    text = narrative.get("text", "")
                    print(f"   Narrative length: {len(text)} characters")
                else:
                    print(f"   Narrative length: {len(narrative)} characters")

            if "metadata" in data:
                metadata = data["metadata"]
                print(f"\n   Metadata keys: {list(metadata.keys())}")
                print(f"   Scene marker: {metadata.get('scene_marker', {})}")
                print(f"   Word count: {metadata.get('word_count', 'N/A')}")
                print(f"   Processing time: {metadata.get('processing_time_ms', 'N/A')}ms")

            if "referenced_entities" in data:
                entities = data["referenced_entities"]
                print(f"\n   Referenced entities:")
                for entity_type, entity_list in entities.items():
                    if entity_list:
                        print(f"     {entity_type}: {len(entity_list)} items")

            if "state_updates" in data:
                updates = data["state_updates"]
                print(f"\n   State updates: {len(updates)} updates")

            if "operations" in data:
                ops = data["operations"]
                print(f"\n   Operations: {len(ops)} operations")

            # Show if this looks like a minimal response
            if len(data.keys()) == 1 and "narrative" in data and isinstance(data["narrative"], str):
                print("\n⚠️  This appears to be a MINIMAL response (plain text only)")
            elif "metadata" in data and "referenced_entities" in data:
                print("\n✅ This appears to be a FULL structured response")

        else:
            print(f"\n✗ Error: {response.status_code}")
            print(f"  Response: {response.text}")

        return response

if __name__ == "__main__":
    try:
        response = test_structured_output()
        print("\n" + "=" * 60)
        print("TEST COMPLETE")
        print("=" * 60)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()