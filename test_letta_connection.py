'''Basic connectivity test for Letta server configured with PostgreSQL.'''
import json
import sys

BASE_URL = "http://localhost:8283"


def main() -> None:
    try:
        import requests
    except Exception as e:  # pragma: no cover - missing dependency
        print("requests library not available", e)
        sys.exit(1)

    try:
        import letta_client
        from letta_client import Letta, CreateBlock
    except Exception as e:  # pragma: no cover - missing dependency
        print("letta_client not available", e)
        return

    # Check server health
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        resp.raise_for_status()
    except Exception as e:
        print("Letta server not reachable", e)
        return

    client = Letta(base_url=BASE_URL)

    agent = client.agents.create(
        name="letta_test_agent",
        memory_blocks=[
            CreateBlock(label="human", value="Test User"),
            CreateBlock(label="persona", value="Test Persona"),
        ],
        model="openai/gpt-4o-mini",
        embedding="openai/text-embedding-3-small",
    )

    # Update and verify memory
    client.agents.blocks.update(
        agent_id=agent.id,
        block_id="human",
        value="Updated User",
    )
    refreshed = client.agents.retrieve(agent_id=agent.id)
    success = any(b.label == "human" and b.value == "Updated User" for b in refreshed.memory.blocks)
    print("Memory write/read successful:", success)

    # Confirm PostgreSQL tables
    try:
        import psycopg
        with psycopg.connect("host=localhost port=5432 dbname=NEXUS user=pythagor") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='agents');"
                )
                exists = cur.fetchone()[0]
                print("Agents table present:", exists)
                cur.execute("DELETE FROM agents WHERE name='letta_test_agent';")
                conn.commit()
    except Exception as e:
        print("PostgreSQL check failed", e)

    client.agents.delete(agent_id=agent.id)
    print("Cleanup complete")


if __name__ == "__main__":
    main()

