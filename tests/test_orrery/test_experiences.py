"""Focused actor-owned experiential memory unit contracts."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Iterator, Literal

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
from nexus.agents.orrery.epistemics import CLAIM_BIRTH_ROLE_POLICY
from nexus.agents.orrery.experiences import (
    ExperienceRecollection,
    ExperienceRenderBatch,
    validate_render_batch,
)
from nexus.api.lore_adapter import response_to_incubator
from nexus.config import load_settings
from nexus.memory.manager import empty_pass2_baseline


ROOT = Path(__file__).parents[2]


def test_migration_role_policy_matches_runtime_source_of_truth() -> None:
    """Migration receipt roles cannot drift from runtime formation policy."""

    migration_sql = (
        ROOT / "migrations" / "110_experience_formation_sweep.sql"
    ).read_text()
    match = re.search(
        r"SELECT '(?P<policy>\{.*?\})'::jsonb AS roles_by_event_type",
        migration_sql,
        flags=re.DOTALL,
    )
    assert match is not None
    migration_policy = {
        event_type: frozenset(roles)
        for event_type, roles in json.loads(match.group("policy")).items()
    }

    assert migration_policy == dict(CLAIM_BIRTH_ROLE_POLICY)


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
        lore_pass_baseline=empty_pass2_baseline({}),
    )

    assert staged["metadata_updates"]["scene_boundary"] is True
    assert "experiences" not in wire.model_dump(mode="json")


def test_experience_config_resolves_model_and_eligibility() -> None:
    """Shipped tuning is validated and its provider role is resolved."""
    settings = load_settings("nexus.toml")
    assert settings.orrery is not None
    experiences = settings.orrery.experiences

    assert experiences.enabled is True
    assert experiences.include_player_character is False
    assert experiences.model == (
        settings.global_.model.api_models["openai"].roles["gaia"]
    )
    assert experiences.minimum_dossier_fields == 2
    assert experiences.max_seeds_per_render == 12
    assert (
        experiences.magnitude_weight
        + experiences.valence_delta_weight
        + experiences.presence_duration_weight
    ) == pytest.approx(1.0)


def _seed_row() -> dict[str, Any]:
    return {
        "id": 41,
        "character_entity_id": 7,
        "world_event_ids": [12],
        "basis": "witness",
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

    validation = validate_render_batch(
        [_seed_row()],
        batch,
        names_by_experience={41: ({"Mara", "Orrin", "Selene"}, {"Mara", "Orrin"})},
    )

    assert validation.validated == {}
    assert "Selene" in validation.rejected[41]


def test_renderer_validator_rejects_sentence_initial_novel_name() -> None:
    """Sentence-initial proper nouns are validated instead of skipped."""
    batch = ExperienceRenderBatch(
        recollections=[
            ExperienceRecollection(
                experience_id=41,
                experience_text=(
                    "Zorblax warned me to leave. I remembered Orrin at the door."
                ),
            )
        ]
    )

    validation = validate_render_batch(
        [_seed_row()],
        batch,
        names_by_experience={41: ({"Mara", "Orrin"}, {"Mara", "Orrin"})},
    )

    assert validation.validated == {}
    assert "Zorblax" in validation.rejected[41]


def test_repeated_sentence_initial_invented_name_is_still_rejected() -> None:
    """A hallucinated name that opens two sentences must not vouch for itself."""
    batch = ExperienceRenderBatch(
        recollections=[
            ExperienceRecollection(
                experience_id=41,
                experience_text=(
                    "Zorblax warned me to leave. Zorblax told me I should run."
                ),
            )
        ]
    )

    validation = validate_render_batch(
        [_seed_row()],
        batch,
        names_by_experience={41: ({"Mara", "Orrin"}, {"Mara", "Orrin"})},
    )

    assert 41 in validation.rejected
    assert "Zorblax" in validation.rejected[41]


def test_lowercase_occurrence_in_text_exempts_a_sentence_start() -> None:
    """A lowercase use elsewhere vouches for an ordinary sentence-start word."""
    batch = ExperienceRenderBatch(
        recollections=[
            ExperienceRecollection(
                experience_id=41,
                experience_text=(
                    "Silence held the corridor while I waited for Orrin. "
                    "I remember the silence more than the door."
                ),
            )
        ]
    )

    validation = validate_render_batch(
        [_seed_row()],
        batch,
        names_by_experience={41: ({"Mara", "Orrin"}, {"Mara", "Orrin"})},
    )

    assert validation.rejected == {}
    assert 41 in validation.validated


def test_acquisition_validator_requires_telling_perspective() -> None:
    """Acquisitions remember receiving an account, never seeing its incident."""
    row = {**_seed_row(), "basis": "acquisition"}
    witnessing = ExperienceRenderBatch(
        recollections=[
            ExperienceRecollection(
                experience_id=41,
                experience_text=(
                    "I witnessed Orrin open the door. I learned why it mattered."
                ),
            )
        ]
    )
    no_receipt = ExperienceRenderBatch(
        recollections=[
            ExperienceRecollection(
                experience_id=41,
                experience_text=(
                    "I considered Orrin's choice. I distrusted the conclusion."
                ),
            )
        ]
    )

    witnessing_validation = validate_render_batch([row], witnessing)
    receipt_validation = validate_render_batch([row], no_receipt)

    assert "must not describe witnessing" in witnessing_validation.rejected[41]
    assert "receiving or learning" in receipt_validation.rejected[41]


def test_acquisition_validator_accepts_delivered_account_perspective() -> None:
    """A first-person memory of hearing the delivered account is valid."""
    row = {**_seed_row(), "basis": "acquisition"}
    batch = ExperienceRenderBatch(
        recollections=[
            ExperienceRecollection(
                experience_id=41,
                experience_text=(
                    "I heard Orrin tell me about the door. I doubted his account."
                ),
            )
        ]
    )

    validation = validate_render_batch(
        [row],
        batch,
        names_by_experience={41: ({"Mara", "Orrin"}, {"Mara", "Orrin"})},
    )

    assert validation.validated == {
        41: "I heard Orrin tell me about the door. I doubted his account."
    }
    assert validation.rejected == {}


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

    validation = validate_render_batch(
        [_seed_row()],
        batch,
        names_by_experience={41: ({"Mara", "Orrin"}, {"Mara", "Orrin"})},
    )

    assert validation.validated == {
        41: "I watched Orrin open the door. I felt the cold air reach me."
    }
    assert validation.rejected == {}


@pytest.mark.parametrize(
    ("text", "allowed"),
    [
        (
            "I watched Dr. Sera Vey cross the room. I kept close behind her.",
            {"Dr. Sera Vey"},
        ),
        (
            "Sitting still, I watched Orrin open the door. I waited for him.",
            {"Orrin"},
        ),
        ('"Nothing," I said. "Run." I stayed near Orrin.', {"Orrin"}),
        ("I'd waited by the door. We're safer beside Orrin now.", {"Orrin"}),
        ("I followed Mira-Kell through the arch. I trusted her pace.", {"Mira-Kell"}),
        ("I caught Orrin's hand. I pulled him away from the door.", {"Orrin"}),
        ("I heard Orrin speak. Nothing Orrin said surprised me.", {"Orrin"}),
    ],
)
def test_renderer_validator_accepts_names_and_ordinary_sentence_starts(
    text: str, allowed: set[str]
) -> None:
    """Punctuation and sentence position do not invent source-scene entities."""
    row = {
        **_seed_row(),
        "seed_summary": "Mara was sitting still while Orrin watched the door.",
    }
    batch = ExperienceRenderBatch(
        recollections=[ExperienceRecollection(experience_id=41, experience_text=text)]
    )
    known = {"Mara", "Orrin", "Dr. Sera Vey", "Mira-Kell"}

    validation = validate_render_batch(
        [row], batch, names_by_experience={41: (known, {"Mara", *allowed})}
    )

    assert validation.validated == {41: text}
    assert validation.rejected == {}


def test_renderer_validator_rejects_genuinely_invented_mid_sentence_name() -> None:
    """An unknown capitalized person remains invalid away from a sentence edge."""
    text = "I watched Orrin open the door. Then I saw Selene cross the room."
    batch = ExperienceRenderBatch(
        recollections=[ExperienceRecollection(experience_id=41, experience_text=text)]
    )

    validation = validate_render_batch(
        [_seed_row()],
        batch,
        names_by_experience={41: ({"Mara", "Orrin"}, {"Mara", "Orrin"})},
    )

    assert "Selene" in validation.rejected[41]


def test_renderer_validator_matches_disallowed_known_name_case_sensitively() -> None:
    """A proper-name Dawn is rejected without colliding with lowercase dawn."""
    known = {"Mara", "Orrin", "Dawn"}
    allowed = {"Mara", "Orrin"}
    exact = ExperienceRenderBatch(
        recollections=[
            ExperienceRecollection(
                experience_id=41,
                experience_text="I watched Dawn cross the room. I stayed by Orrin.",
            )
        ]
    )
    homograph = ExperienceRenderBatch(
        recollections=[
            ExperienceRecollection(
                experience_id=41,
                experience_text="I watched the dawn through glass. I stayed by Orrin.",
            )
        ]
    )

    rejected = validate_render_batch(
        [_seed_row()], exact, names_by_experience={41: (known, allowed)}
    )
    accepted = validate_render_batch(
        [_seed_row()], homograph, names_by_experience={41: (known, allowed)}
    )

    assert "Dawn" in rejected.rejected[41]
    assert accepted.validated == {41: homograph.recollections[0].experience_text}


def test_renderer_validator_isolates_content_errors_within_batch() -> None:
    """One invalid recollection does not hide a valid batch sibling."""
    rows = [_seed_row(), {**_seed_row(), "id": 42}]
    valid_text = "I watched Orrin open the door. I remembered the cold air."
    batch = ExperienceRenderBatch(
        recollections=[
            ExperienceRecollection(experience_id=41, experience_text=valid_text),
            ExperienceRecollection(
                experience_id=42,
                experience_text="I watched Orrin open the door. Selene followed me.",
            ),
        ]
    )
    names = {
        experience_id: ({"Mara", "Orrin"}, {"Mara", "Orrin"})
        for experience_id in (41, 42)
    }

    validation = validate_render_batch(rows, batch, names_by_experience=names)

    assert validation.validated == {41: valid_text}
    assert "Selene" in validation.rejected[42]


class _EmbeddingCursor:
    def __init__(self, *, read: bool) -> None:
        self.read = read
        self.executions: list[tuple[str, Any]] = []
        self._rows: list[dict[str, Any]] = []

    def __enter__(self) -> "_EmbeddingCursor":
        return self

    def __exit__(self, *_args: Any) -> Literal[False]:
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
