"""Regression pins for the response→incubator metadata extraction path.

Every Skald response field must survive `extract_metadata_updates` or its
database column is write-only-NULL in production regardless of what the
model returned (the scene_weather dead-path found in PR #541 review).
"""

from types import SimpleNamespace

from nexus.api.lore_adapter import extract_metadata_updates


def _response(**metadata_fields):
    metadata = SimpleNamespace(**metadata_fields)
    return SimpleNamespace(chunk_metadata=metadata)


def test_scene_weather_survives_extraction() -> None:
    updates = extract_metadata_updates(
        _response(world_layer="primary", scene_weather="rain")
    )
    assert updates["scene_weather"] == "rain"


def test_absent_scene_weather_emits_no_key() -> None:
    updates = extract_metadata_updates(_response(world_layer="primary"))
    assert "scene_weather" not in updates
