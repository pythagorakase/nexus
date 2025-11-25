import requests
import json
import sys
import time

BASE_URL = "http://localhost:5001"

def test_setup_flow(slot_number):
    print(f"Testing setup flow for slot {slot_number}...")
    
    # 1. Start Setup
    print("1. Starting setup...")
    try:
        start_res = requests.post(
            f"{BASE_URL}/api/story/new/setup/start",
            json={"slot": slot_number}
        )
        start_res.raise_for_status()
        start_data = start_res.json()
        thread_id = start_data["thread_id"]
        print(f"   Setup started. Thread ID: {thread_id}")
    except Exception as e:
        print(f"   FAILED to start setup: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"   Response: {e.response.text}")
        return

    # 2. Send Setting Input
    print("2. Sending setting input ('default fantasy')...")
    try:
        chat_res = requests.post(
            f"{BASE_URL}/api/story/new/chat",
            json={
                "slot": slot_number,
                "thread_id": thread_id,
                "message": "A high fantasy world called Aethelgard. Magic is common. The tone is epic and adventurous. Tech level is medieval.",
                "current_phase": "setting",
                "context_data": {}
            },
            timeout=60 # Set a timeout to catch hangs
        )
        chat_res.raise_for_status()
        chat_data = chat_res.json()
        print("   Chat response received.")
        print(f"   Message: {chat_data.get('message', '')[:100]}...")
        if chat_data.get("phase_complete"):
            print("   Phase complete!")
            print(f"   Artifact type: {chat_data.get('artifact_type')}")
        else:
            print("   Phase NOT complete. Sending follow-up...")
            # 3. Send Follow-up
            time.sleep(1)
            followup_res = requests.post(
                f"{BASE_URL}/api/story/new/chat",
                json={
                    "slot": slot_number,
                    "thread_id": thread_id,
                    "message": "Just make it a standard high fantasy setting with elves and dwarves. No special twists.",
                    "current_phase": "setting",
                    "context_data": {}
                },
                timeout=60
            )
            followup_res.raise_for_status()
            followup_data = followup_res.json()
            print("   Follow-up response received.")
            if followup_data.get("phase_complete"):
                print("   Phase complete!")
                print(f"   Artifact type: {followup_data.get('artifact_type')}")
            else:
                print("   Phase STILL NOT complete.")
                print(f"   Message: {followup_data.get('message', '')[:100]}...")
            
    except Exception as e:
        print(f"   FAILED to send message: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"   Response: {e.response.text}")

if __name__ == "__main__":
    # Test slot 3 as it exists
    test_setup_flow(3)
