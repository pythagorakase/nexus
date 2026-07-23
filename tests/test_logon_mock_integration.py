"""Integration test for LogonUtility → mock server routing."""

import psycopg2
import pytest

from scripts.api_openai import OpenAIProvider
from nexus.agents.logon.skald_wire import SkaldTurnWire


def get_slot_model(dbname: str) -> str | None:
    """Query slot model directly from global_variables."""
    conn = psycopg2.connect(host="localhost", database=dbname, user="pythagor")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT model FROM global_variables WHERE id = TRUE")
            result = cur.fetchone()
            return result[0] if result else None
    finally:
        conn.close()


@pytest.mark.requires_postgres
def test_slot_model_detection():
    """Test that we can detect TEST model from slot config."""
    conn = psycopg2.connect(host="localhost", database="save_05", user="pythagor")
    original_model = None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT model FROM global_variables WHERE id = TRUE")
            row = cur.fetchone()
            original_model = row[0] if row else None

            if original_model != "TEST":
                cur.execute(
                    "UPDATE global_variables SET model = %s WHERE id = TRUE", ("TEST",)
                )
                conn.commit()

        model = get_slot_model("save_05")
        assert model == "TEST", f"Expected TEST, got {model}"
    finally:
        try:
            if original_model is not None and original_model != "TEST":
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE global_variables SET model = %s WHERE id = TRUE",
                        (original_model,),
                    )
                    conn.commit()
        finally:
            conn.close()


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
        SkaldTurnWire,
    )

    assert len(response.narrative) > 100, "Narrative too short"
    assert (
        len(response.choices) == 3
    ), f"Expected 3 choices, got {len(response.choices)}"
    assert response.narrative.startswith("[TEST MODE]")
    assert response.orrery_adjudications == []
    assert "deterministic mock control" in response.narrative
