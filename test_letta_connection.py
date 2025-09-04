import requests

try:
    import psycopg2
except ImportError:  # pragma: no cover - dependency optional for test
    psycopg2 = None

BASE_URL = "http://localhost:8283/v1"


def main() -> None:
    # Create a test agent
    resp = requests.post(f"{BASE_URL}/agents", json={"agent": {"name": "test-agent"}})
    resp.raise_for_status()
    agent = resp.json()
    agent_id = agent["id"]

    try:
        # Store memory
        mem_resp = requests.post(
            f"{BASE_URL}/agents/{agent_id}/archival-memory", json={"text": "integration test"}
        )
        mem_resp.raise_for_status()
        mem_id = mem_resp.json()[0]["id"]

        # Retrieve memory
        list_resp = requests.get(f"{BASE_URL}/agents/{agent_id}/archival-memory")
        list_resp.raise_for_status()
        memories = list_resp.json()
        assert any(m["id"] == mem_id for m in memories), "Stored memory not found"
        print("Memory round-trip successful")

        # Confirm tables created in PostgreSQL
        if psycopg2 is not None:
            conn = psycopg2.connect(host="localhost", port=5432, dbname="NEXUS", user="pythagor")
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.agents')")
                assert cur.fetchone()[0] is not None, "Letta tables missing in database"
            conn.close()
            print("PostgreSQL tables verified")
        else:
            print("psycopg2 not installed; skipping database verification")
    finally:
        # Clean up test data
        try:
            requests.delete(f"{BASE_URL}/agents/{agent_id}")
        except Exception:
            pass


if __name__ == "__main__":
    main()
