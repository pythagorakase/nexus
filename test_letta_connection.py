"""Simple connectivity test for the Letta server.

This script verifies that the Letta server is reachable, can create
an agent, store and retrieve a memory, and that the underlying
PostgreSQL tables are created in the NEXUS database.
"""

from __future__ import annotations

import uuid

import requests
import psycopg2

BASE_URL = "http://localhost:8283/v1"
PG_CONN_INFO = dict(host="localhost", port=5432, user="pythagor", dbname="NEXUS")


def main() -> None:
    # Create a test agent
    agent_name = f"test-agent-{uuid.uuid4().hex[:8]}"
    resp = requests.post(f"{BASE_URL}/agents", json={"name": agent_name})
    resp.raise_for_status()
    agent_id = resp.json()["id"]

    try:
        # Send a message that should be stored in memory
        message_payload = {"messages": [{"role": "user", "content": "remember me"}]}
        msg_resp = requests.post(f"{BASE_URL}/agents/{agent_id}/messages", json=message_payload)
        msg_resp.raise_for_status()

        # Retrieve messages to confirm storage
        history_resp = requests.get(f"{BASE_URL}/agents/{agent_id}/messages")
        history_resp.raise_for_status()
        messages = history_resp.json().get("messages", [])
        assert any(m.get("content") == "remember me" for m in messages), "Memory retrieval failed"
        print("Memory storage and retrieval succeeded.")

        # Verify PostgreSQL tables exist and contain the agent
        with psycopg2.connect(**PG_CONN_INFO) as conn:
            with conn.cursor() as cur:
                # Ensure agents table exists
                cur.execute("SELECT to_regclass('public.agents')")
                if cur.fetchone()[0] is None:
                    raise RuntimeError("Agents table not found in PostgreSQL")
                # Check that our agent was persisted
                cur.execute("SELECT id FROM agents WHERE id = %s", (agent_id,))
                assert cur.fetchone() is not None, "Agent not found in database"
        print("PostgreSQL table verification succeeded.")
    finally:
        # Clean up the test agent
        requests.delete(f"{BASE_URL}/agents/{agent_id}")
        print("Test agent cleaned up.")


if __name__ == "__main__":
    main()
