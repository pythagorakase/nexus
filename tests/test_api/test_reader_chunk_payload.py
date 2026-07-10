"""Focused wire-format tests for the reader chunk serializer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import pytest

from nexus.api.reader_endpoints import _chunk_payload


def _row(**overrides: Any) -> Dict[str, Any]:
    """Build one complete chunk query row for serializer tests."""
    row: Dict[str, Any] = {
        "id": 448,
        "raw_text": "Clean prose.",
        "storyteller_text": "Clean prose.",
        "choice_object": None,
        "choice_text": None,
        "created_at": datetime(2026, 7, 10, tzinfo=timezone.utc),
        "chunk_id": 448,
        "season": 5,
        "episode": 6,
        "scene": 13,
        "world_layer": "primary",
        "world_time": None,
        "time_delta": "00:15:00",
        "generation_date": datetime(2026, 7, 10),
        "slug": "S05E06_013",
    }
    row.update(overrides)
    return row


def test_chunk_payload_serializes_world_time() -> None:
    """A populated world clock is emitted as an ISO 8601 string."""
    world_time = datetime(2087, 11, 3, 22, 47, tzinfo=timezone.utc)

    payload = _chunk_payload(_row(world_time=world_time))

    assert payload["metadata"]["worldTime"] == "2087-11-03T22:47:00+00:00"


def test_chunk_payload_preserves_null_world_time() -> None:
    """An unknown world clock remains JSON-null-compatible None."""
    payload = _chunk_payload(_row(world_time=None))

    assert payload["metadata"]["worldTime"] is None


@pytest.mark.parametrize(
    ("raw_text", "expected"),
    [
        (
            "<!-- SCENE BREAK: S03E14_014 (storyteller heading) -->\n# Scene",
            True,
        ),
        ("Clean prose with no embedded scene marker.", False),
        (
            "Opening prose.\n<!-- SCENE BREAK: S03E14_014 " "(episode heading) -->",
            False,
        ),
    ],
)
def test_chunk_payload_detects_only_anchored_legacy_scene_markup(
    raw_text: str, expected: bool
) -> None:
    """Only an exact byte-zero legacy scene-break marker enables suppression."""
    payload = _chunk_payload(_row(raw_text=raw_text))

    assert payload["hasInlineSceneMarkup"] is expected
