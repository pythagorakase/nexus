"""Integration test for LogonUtility → mock server routing."""
import pytest
import psycopg2

from scripts.api_openai import OpenAIProvider
from nexus.agents.logon.apex_schema import StorytellerResponseExtended


def get_slot_model(dbname: str) -> str:
    """Query slot model directly."""
    conn = psycopg2.connect(host="localhost", database=dbname, user="pythagor")
    try:
        with conn.cursor() as cur:
            slot_num = int(dbname.replace("save_", "").lstrip("0") or "0")
            cur.execute("SELECT model FROM assets.save_slots WHERE slot_number = %s", (slot_num,))
            result = cur.fetchone()
            return result[0] if result else None
    finally:
        conn.close()


@pytest.mark.requires_postgres
def test_slot_model_detection():
    """Test that we can detect TEST model from slot config."""
    model = get_slot_model("save_05")
    assert model == "TEST", f"Expected TEST, got {model}"


@pytest.mark.requires_postgres
def test_provider_routes_to_mock_server():
    """Test OpenAI provider routes TEST model to mock server."""
    provider = OpenAIProvider(
        model="TEST",
        base_url="http://localhost:5102/v1",
        api_key="test-dummy-key",
        system_prompt="Test system prompt",
    )
    
    assert provider.model == "TEST"
    assert provider.base_url == "http://localhost:5102/v1"
    
    # Initialize and call mock server
    provider.initialize()
    
    response, llm_response = provider.get_structured_completion(
        "Generate narrative for the story protagonist",
        StorytellerResponseExtended,
    )
    
    assert len(response.narrative) > 100, "Narrative too short"
    assert len(response.choices) == 3, f"Expected 3 choices, got {len(response.choices)}"
    assert "tram" in response.narrative.lower() or "satchel" in response.narrative.lower()
