"""Tests for Apex response schema helpers."""

from nexus.agents.logon.apex_schema import create_minimal_response


def test_create_minimal_response_includes_valid_choices() -> None:
    """Minimal fallback responses should satisfy the response schema."""

    response = create_minimal_response("A short narrative beat.")

    assert response.narrative == "A short narrative beat."
    assert response.choices == [
        "Continue.",
        "Wait and observe.",
    ]
