"""Offline place-point requirements at the storyteller declaration boundary."""

import pytest
from pydantic import ValidationError

from nexus.agents.logon.apex_schema import NewEntityDeclaration


@pytest.mark.parametrize("coordinates", [{}, {"coordinates": None}])
def test_place_declaration_requires_point(coordinates: dict[str, None]) -> None:
    """Omitted and explicit null points both refuse a new place declaration."""

    with pytest.raises(
        ValidationError, match="coordinates are required for place declarations"
    ):
        NewEntityDeclaration.model_validate(
            {
                "kind": "place",
                "name": "Shutter Hall",
                "summary": "A gathering hall above the valley.",
                **coordinates,
            }
        )


def test_place_declaration_preserves_authored_point() -> None:
    """A valid declaration carries the producer's point without replacement."""

    point = {"lat": 50.0, "lon": 50.0}
    declaration = NewEntityDeclaration.model_validate(
        {
            "kind": "place",
            "name": "Shutter Hall",
            "summary": "A gathering hall above the valley.",
            "coordinates": point,
        }
    )

    assert declaration.coordinates is not None
    assert declaration.coordinates.model_dump(mode="json") == point


@pytest.mark.parametrize("kind", ["character", "faction"])
def test_non_place_declaration_refuses_point(kind: str) -> None:
    """Requiring place points does not admit GIS data on other entity kinds."""

    with pytest.raises(
        ValidationError, match="coordinates are only valid for place declarations"
    ):
        NewEntityDeclaration.model_validate(
            {
                "kind": kind,
                "name": "The Watch",
                "summary": "A recurring figure in the valley's affairs.",
                "coordinates": {"lat": 50.0, "lon": 50.0},
            }
        )
