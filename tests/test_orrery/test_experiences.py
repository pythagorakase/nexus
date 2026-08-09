"""Focused actor-owned experiential memory unit contracts."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

import pytest

from nexus.agents.logon.skald_wire import (
    CharacterRef,
    PlaceRef,
    PresenceBaseline,
    PresenceDelta,
    SceneReset,
    SkaldTurnWire,
    hydrate_skald_turn,
)
from nexus.agents.orrery import experience_embedding
from nexus.agents.orrery.experiences import (
    ExperienceRecollection,
    ExperienceRenderBatch,
    validate_render_batch,
)
from nexus.api.lore_adapter import response_to_incubator
from nexus.config import load_settings


def test_scene_reset_survives_internal_incubator_staging() -> None:
    """The real wire hydration path retains a queue boundary without a new arm."""
    wire = SkaldTurnWire(
        narrative="Mara entered the observatory.",
        choices=["Wait.", "Follow."],
        presence=PresenceDelta(
            scene_reset=SceneReset(
                place=PlaceRef(kind="place", id=9, name="Copper Observatory"),
                present=[CharacterRef(kind="character", id=7, name="Mara")],
            )
        ),
        letter="Begin the observatory scene.",
    )
    hydrated = hydrate_skald_turn(wire, presence_baseline=PresenceBaseline())
    staged = response_to_incubator(
        hydrated,
        parent_chunk_id=4,
        user_text="Go inside.",
        session_id="experience-boundary",
    )

    assert staged["metadata_updates"]["scene_boundary"] is True
    assert "experiences" not in wire.model_dump(mode="json")


def test_experience_config_resolves_model_and_eligibility() -> None:
    """Shipped tuning is validated and its provider role is resolved."""
    settings = load_settings("nexus.toml")

    assert settings.orrery.experiences.enabled is True
    assert settings.orrery.experiences.model == (
        settings.global_.model.api_models["openai"].roles["gaia"]
    )
    assert settings.orrery.experiences.minimum_dossier_fields == 2
    assert sum(
        (
            settings.orrery.experiences.magnitude_weight,
            settings.orrery.experiences.valence_delta_weight,
            settings.orrery.experiences.presence_duration_weight,
        )
    ) == pytest.approx(1.0)


def _seed_row() -> dict[str, Any]:
    return {
        "id": 41,
        "character_entity_id": 7,
        "world_event_ids": [12],
        "location_id": 9,
        "seed_summary": ("Mara witnessed Orrin open the Copper Observatory door."),
    }


def test_renderer_validator_rejects_entity_invention() -> None:
    """A structured response cannot name a person absent from its source scene."""
    batch = ExperienceRenderBatch(
        recollections=[
            ExperienceRecollection(
                experience_id=41,
                experience_text=(
                    "I watched Orrin open the door. Then Selene warned me to run."
                ),
            )
        ]
    )

    with pytest.raises(ValueError, match="absent from its source scene.*Selene"):
        validate_render_batch(
            [_seed_row()],
            batch,
            names_by_experience={41: ({"Mara", "Orrin", "Selene"}, {"Mara", "Orrin"})},
        )


def test_renderer_validator_accepts_complete_first_person_batch() -> None:
    """Every seed is returned exactly once in bounded first-person prose."""
    batch = ExperienceRenderBatch(
        recollections=[
            ExperienceRecollection(
                experience_id=41,
                experience_text=(
                    "I watched Orrin open the door. I felt the cold air reach me."
                ),
            )
        ]
    )

    assert validate_render_batch(
        [_seed_row()],
        batch,
        names_by_experience={41: ({"Mara", "Orrin"}, {"Mara", "Orrin"})},
    ) == {41: "I watched Orrin open the door. I felt the cold air reach me."}


class _EmbeddingCursor:
    def __init__(self, *, read: bool) -> None:
        self.read = read
        self.executions: list[tuple[str, Any]] = []
        self._rows: list[dict[str, Any]] = []

    def __enter__(self) -> "_EmbeddingCursor":
        return self

    def __exit__(self, *_args: Any) -> bool:
        return False

    def execute(self, statement: str, params: Any = None) -> None:
        normalized = " ".join(statement.split())
        self.executions.append((normalized, params))
        if self.read:
            self._rows = [
                {"id": 11, "experience_text": "I remembered eleven."},
                {"id": 22, "experience_text": "I remembered twenty-two."},
            ]
        elif normalized.startswith("UPDATE character_experiences"):
            stamp = datetime(2196, 1, 1, tzinfo=timezone.utc)
            self._rows = [
                {"id": 11, "embedding_generated_at": stamp},
                {"id": 22, "embedding_generated_at": stamp},
            ]
        else:
            self._rows = []

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _EmbeddingConnection:
    def __init__(self, cursor: _EmbeddingCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _EmbeddingCursor:
        return self._cursor


def test_embedding_upsert_binds_each_correct_experience_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for the stale-loop-id bug class fixed in PR #671."""
    read_cursor = _EmbeddingCursor(read=True)
    write_cursor = _EmbeddingCursor(read=False)
    connections = iter(
        [_EmbeddingConnection(read_cursor), _EmbeddingConnection(write_cursor)]
    )

    @contextmanager
    def fake_connection(*_args: Any, **_kwargs: Any) -> Iterator[Any]:
        yield next(connections)

    class FakeManager:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def get_available_models(self) -> list[str]:
            return ["test-embed"]

        def generate_embedding(self, text: str, _model: str) -> list[float]:
            return [float(len(text)), 1.0]

    monkeypatch.setattr(
        "nexus.api.db_pool.get_connection",
        fake_connection,
    )
    monkeypatch.setattr(
        "nexus.agents.memnon.utils.embedding_manager.EmbeddingManager",
        FakeManager,
    )
    monkeypatch.setattr(
        "nexus.agents.orrery.retrograde_embedding."
        "active_memnon_embedding_model_dimensions",
        lambda: {"test-embed": 2},
    )
    monkeypatch.setattr(
        experience_embedding, "_memnon_settings", lambda: {"models": {}}
    )
    monkeypatch.setattr(
        experience_embedding,
        "ensure_character_experience_embedding_table",
        lambda _cursor, _dimensions: "character_experience_embeddings_0002d",
    )

    result = experience_embedding.embed_character_experiences("qa677", [11, 22])

    inserts = [
        params
        for sql, params in write_cursor.executions
        if sql.startswith("INSERT INTO character_experience_embeddings_0002d")
    ]
    assert [params[0] for params in inserts] == [11, 22]
    assert [row["experience_id"] for row in result] == [11, 22]
