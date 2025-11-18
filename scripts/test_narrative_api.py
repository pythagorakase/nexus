#!/usr/bin/env python3
"""
Test script for the narrative API endpoints
"""

import requests
import json
import time
import argparse
from typing import Dict, Any

API_BASE = "http://localhost:8002"

def test_health():
    """Test health endpoint"""
    print("Testing /health endpoint...")
    response = requests.get(f"{API_BASE}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    return response.status_code == 200

def test_continue_narrative(chunk_id: int = 1425, user_text: str = "Continue."):
    """Test narrative continuation endpoint"""
    print(f"\nTesting /api/narrative/continue endpoint...")
    print(f"Chunk ID: {chunk_id}, User text: '{user_text}'")

    payload = {
        "chunk_id": chunk_id,
        "user_text": user_text,
        "test_mode": True
    }

    response = requests.post(
        f"{API_BASE}/api/narrative/continue",
        json=payload
    )

    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"Session ID: {data['session_id']}")
        print(f"Status: {data['status']}")
        print(f"Message: {data['message']}")
        return data['session_id']
    else:
        print(f"Error: {response.text}")
        return None

def test_status(session_id: str):
    """Test status endpoint"""
    print(f"\nTesting /api/narrative/status/{session_id} endpoint...")

    # Poll for completion
    for i in range(10):
        response = requests.get(f"{API_BASE}/api/narrative/status/{session_id}")

        if response.status_code == 200:
            data = response.json()
            print(f"Attempt {i+1}: Status = {data['status']}")

            if data['status'] == 'complete':
                print("Generation complete!")
                print(f"Chunk ID: {data.get('chunk_id')}")
                return True
            elif data['status'] == 'error':
                print(f"Error: {data.get('error')}")
                return False
        else:
            print(f"Error getting status: {response.status_code}")
            return False

        time.sleep(1)

    print("Timeout waiting for completion")
    return False

def test_incubator():
    """Test incubator view endpoint"""
    print("\nTesting /api/narrative/incubator endpoint...")

    response = requests.get(f"{API_BASE}/api/narrative/incubator")

    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        if 'message' in data and data['message'] == 'Incubator is empty':
            print("Incubator is empty")
        else:
            print("Incubator contents:")
            print(f"  Chunk ID: {data.get('chunk_id')}")
            print(f"  Parent Chunk ID: {data.get('parent_chunk_id')}")
            print(f"  Status: {data.get('status')}")
            print(f"  Session ID: {data.get('session_id')}")
            if data.get('storyteller_text'):
                print(f"  Storyteller text preview: {data['storyteller_text'][:100]}...")
        return True
    else:
        print(f"Error: {response.text}")
        return False

def test_clear_incubator():
    """Test incubator clear endpoint"""
    print("\nTesting DELETE /api/narrative/incubator endpoint...")

    response = requests.delete(f"{API_BASE}/api/narrative/incubator")

    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"Message: {data.get('message')}")
        return True
    else:
        print(f"Error: {response.text}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Test narrative API endpoints")
    parser.add_argument("--full", action="store_true",
                       help="Run full test sequence")
    parser.add_argument("--health", action="store_true",
                       help="Test health endpoint only")
    parser.add_argument("--continue", action="store_true", dest="continue_narrative",
                       help="Test narrative continuation")
    parser.add_argument("--incubator", action="store_true",
                       help="View incubator contents")
    parser.add_argument("--clear", action="store_true",
                       help="Clear incubator")
    parser.add_argument("--chunk-id", type=int, default=1425,
                       help="Chunk ID to continue from")
    parser.add_argument("--user-text", type=str, default="Continue.",
                       help="User text for continuation")

    args = parser.parse_args()

    # Default to full test if no specific test selected
    if not any([args.health, args.continue_narrative, args.incubator, args.clear]):
        args.full = True

    try:
        if args.health or args.full:
            if not test_health():
                print("\n❌ Health check failed. Is the server running?")
                print("Start it with: poetry run honcho start -f Procfile.dev")
                return

        if args.clear:
            test_clear_incubator()

        if args.continue_narrative or args.full:
            session_id = test_continue_narrative(args.chunk_id, args.user_text)
            if session_id and args.full:
                # Wait for completion and check status
                time.sleep(2)
                test_status(session_id)

        if args.incubator or args.full:
            test_incubator()

        print("\n✅ API tests completed!")

    except requests.exceptions.ConnectionError:
        print("\n❌ Cannot connect to API server.")
        print("Start the server with: poetry run honcho start -f Procfile.dev")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")

if __name__ == "__main__":
    main()