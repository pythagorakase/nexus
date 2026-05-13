"""Tests for Apex response schema helpers."""

import pytest
from pydantic import ValidationError

from nexus.agents.logon.apex_schema import (
    StorytellerResponseBootstrap,
    create_minimal_response,
)


def test_bootstrap_response_schema_only_accepts_narrative_and_choices() -> None:
    """Bootstrap responses should not request entity metadata."""

    response = StorytellerResponseBootstrap(
        narrative="The story begins.",
        choices=["Step forward.", "Look around."],
    )

    assert response.narrative == "The story begins."
    assert response.choices == ["Step forward.", "Look around."]

    with pytest.raises(ValidationError):
        StorytellerResponseBootstrap(
            narrative="The story begins.",
            choices=["Step forward.", "Look around."],
            referenced_entities={"characters": []},
        )


def test_create_minimal_response_includes_valid_choices() -> None:
    """Minimal fallback responses should satisfy the response schema."""

    response = create_minimal_response("A short narrative beat.")

    assert response.narrative == "A short narrative beat."
    assert response.choices == [
        "Continue.",
        "Wait and observe.",
    ]
