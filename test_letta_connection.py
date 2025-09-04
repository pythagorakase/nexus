#!/usr/bin/env python3
"""Simple connectivity test for the Letta server and PostgreSQL backend."""
import os

from letta_client import CreateBlock, Letta as LettaSDKClient
from letta_client.types import AgentState
import psycopg2

SERVER_URL = os.getenv("LETTA_SERVER_URL", "http://localhost:8283")


def main() -> None:
    client = LettaSDKClient(base_url=SERVER_URL, token=None)

    # Create an agent with a test memory block
    agent: AgentState = client.agents.create(
        memory_blocks=[CreateBlock(label="test", value="remember this")],
        model="openai/gpt-4o-mini",
        embedding="openai/text-embedding-3-small",
    )

    # Retrieve the agent to verify the memory block was stored
    fetched = client.agents.get(agent.id)
    assert any(block.value == "remember this" for block in fetched.memory_blocks)

    # Clean up
    client.agents.delete(agent.id)

    # Verify PostgreSQL tables exist
    conn = psycopg2.connect(host="localhost", port=5432, user="pythagor", dbname="NEXUS")
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_name='agents';")
    assert cur.fetchone(), "Letta tables not found in PostgreSQL"
    cur.close()
    conn.close()

    print("Letta connection test completed successfully.")


if __name__ == "__main__":
    main()

