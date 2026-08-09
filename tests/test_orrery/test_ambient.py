"""Current-turn typed ambient-scene seed acceptance tests."""

from __future__ import annotations

from typing import Any

import pytest

import nexus.agents.orrery.events as orrery_events
from nexus.agents.lore.logon_utility import LogonUtility
from nexus.agents.orrery.ambient import (
    AMBIENT_EXPOSURE_TEMPLATE_ID,
    AmbientSceneSeed,
)
from nexus.agents.orrery.events import commit_orrery_tick_sync
from nexus.agents.orrery.propagation import PropagationDrainResult
from nexus.agents.orrery.resolver import OrreryTickProposal, resolve_dry_run
from nexus.agents.orrery.reveal import RevealDrainResult
from nexus.config.settings_models import OrreryAmbientSettings
from test_orrery.test_resolver import FakeResult, FakeSession


AMBIENT_SETTINGS = {
    "max_seeds": 2,
    "per_dyad_cooldown_turns": 3,
    "expiry_turns": 2,
    "line_budget": 4,
    "turn_budget": 2,
}


class AmbientFakeSession(FakeSession):
    """Resolver fake extended only for the ambient read-side ledgers."""

    def __init__(
        self,
        *,
        claim_acquisition_rows: list[dict[str, Any]] | None = None,
        committed_resolution_rows: list[dict[str, Any]] | None = None,
        exposure_rows: list[dict[str, Any]] | None = None,
        possessed_claim_rows: list[dict[str, Any]] | None = None,
        relationship_rows: list[dict[str, Any]] | None = None,
        present_actor_rows: list[dict[str, Any]] | None = None,
        location_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        active_rows = [{"id": value} for value in (1, 2, 3, 99)]
        super().__init__(
            active_entity_rows=active_rows,
            relationship_rows=relationship_rows or [],
            present_actor_rows=present_actor_rows
            or [{"entity_id": value} for value in (1, 2, 3, 99)],
            location_rows=location_rows
            or [
                {"entity_id": value, "current_location": 10} for value in (1, 2, 3, 99)
            ],
            activity_rows=[
                {"entity_id": value, "current_activity": "idle"}
                for value in (1, 2, 3, 99)
            ],
            chunk_ref_actor_rows=[],
            entity_name_rows=[
                {"id": 1, "name": "Mara"},
                {"id": 2, "name": "Vale"},
                {"id": 3, "name": "Iris"},
                {"id": 99, "name": "Protagonist"},
            ],
        )
        self.claim_acquisition_rows = claim_acquisition_rows or []
        self.committed_resolution_rows = committed_resolution_rows or []
        self.exposure_rows = exposure_rows or []
        self.possessed_claim_rows = possessed_claim_rows or []

    def execute(self, statement: Any, params: Any = None) -> FakeResult:
        sql = str(statement)
        if "/* orrery:ambient_protagonist */" in sql:
            self.executed_sql.append(sql)
            return FakeResult([{"entity_id": 99}])
        if "/* orrery:ambient_claim_acquisitions */" in sql:
            self.executed_sql.append(sql)
            return FakeResult(self.claim_acquisition_rows)
        if "/* orrery:ambient_committed_resolutions */" in sql:
            self.executed_sql.append(sql)
            return FakeResult(self.committed_resolution_rows)
        if "/* orrery:ambient_exposure_cooldown */" in sql:
            self.executed_sql.append(sql)
            return FakeResult(self.exposure_rows)
        if "/* orrery:ambient_possessed_claims */" in sql:
            self.executed_sql.append(sql)
            return FakeResult(self.possessed_claim_rows)
        return super().execute(statement, params)


def _relationship_rows() -> list[dict[str, Any]]:
    return [
        {
            "source_entity_id": 1,
            "target_entity_id": 2,
            "relationship_type": "rival",
            "valence_magnitude": -2,
        },
        {
            "source_entity_id": 2,
            "target_entity_id": 1,
            "relationship_type": "colleague",
            "valence_magnitude": 1,
        },
        {
            "source_entity_id": 1,
            "target_entity_id": 3,
            "relationship_type": "friend",
            "valence_magnitude": 2,
        },
        {
            "source_entity_id": 2,
            "target_entity_id": 3,
            "relationship_type": "neighbor",
            "valence_magnitude": 0,
        },
        {
            "source_entity_id": 99,
            "target_entity_id": 1,
            "relationship_type": "ally",
            "valence_magnitude": 3,
        },
    ]


def _resolve(
    session: AmbientFakeSession,
    *,
    anchor_chunk_id: int = 100,
    settings: dict[str, int] | None = None,
) -> OrreryTickProposal:
    return resolve_dry_run(
        session,
        (),
        anchor_chunk_id=anchor_chunk_id,
        window_chunks=30,
        ambient_settings=settings or AMBIENT_SETTINGS,
        ambient_pacing_allowed=True,
    )


def test_resolver_builds_deterministic_bounded_state_free_seeds() -> None:
    """The genuine resolver returns replay-identical seeds and performs no writes."""

    first_session = AmbientFakeSession(relationship_rows=_relationship_rows())
    second_session = AmbientFakeSession(relationship_rows=_relationship_rows())

    first = _resolve(first_session)
    second = _resolve(second_session)

    assert first.ambient_scene_seeds == second.ambient_scene_seeds
    assert len(first.ambient_scene_seeds) == 2
    assert all(seed.silence_ok is True for seed in first.ambient_scene_seeds)
    assert all(seed.line_budget == 4 for seed in first.ambient_scene_seeds)
    assert all(seed.turn_budget == 2 for seed in first.ambient_scene_seeds)
    assert all(
        99 not in {participant.entity_id for participant in seed.participants}
        for seed in first.ambient_scene_seeds
    )
    for sql in first_session.executed_sql:
        normalized = sql.lstrip().upper()
        assert normalized.startswith(("SELECT", "WITH", "/*"))
        assert "INSERT INTO" not in normalized
        assert "UPDATE " not in normalized
        assert "DELETE FROM" not in normalized


def test_proposal_round_trip_preserves_typed_ambient_seed() -> None:
    """Incubator JSON retains the complete seed contract without state authority."""

    proposal = _resolve(AmbientFakeSession(relationship_rows=_relationship_rows()[:2]))

    payload = proposal.to_dict()
    hydrated = OrreryTickProposal.from_dict(payload)

    assert hydrated == proposal
    assert "state_delta" not in payload["ambient_scene_seeds"][0]
    assert payload["ambient_scene_seeds"][0]["silence_ok"] is True


def test_per_dyad_exposure_cooldown_suppresses_repeat_offer() -> None:
    """An exposure inside the configured cooldown prevents the dyad re-offer."""

    first = _resolve(AmbientFakeSession(relationship_rows=_relationship_rows()[:2]))
    dedup_key = first.ambient_scene_seeds[0].dedup_key
    repeated = _resolve(
        AmbientFakeSession(
            relationship_rows=_relationship_rows()[:2],
            exposure_rows=[{"binding_hash": dedup_key}],
        ),
        anchor_chunk_id=101,
    )

    assert repeated.ambient_scene_seeds == ()


def test_expired_signal_does_not_become_current_turn_seed() -> None:
    """A claim-acquisition signal at the expiry boundary is not eligible."""

    proposal = _resolve(
        AmbientFakeSession(
            claim_acquisition_rows=[
                {
                    "acquisition_id": 501,
                    "claim_id": 601,
                    "knower_entity_id": 1,
                    "immediate_source_entity_id": 2,
                    "source_chunk_id": 98,
                    "summary": "The archive door was opened.",
                    "scope": "bounded",
                }
            ]
        ),
        anchor_chunk_id=100,
    )

    assert proposal.ambient_scene_seeds == ()


def test_entitlements_include_only_each_participant_possessed_claim_ids() -> None:
    """Sibling and other actors' accounts cannot cross the ownership boundary."""

    proposal = _resolve(
        AmbientFakeSession(
            relationship_rows=_relationship_rows()[:2],
            possessed_claim_rows=[
                {"knower_entity_id": 1, "claim_id": 10},
                {"knower_entity_id": 1, "claim_id": 11},
                {"knower_entity_id": 2, "claim_id": 20},
                {"knower_entity_id": 3, "claim_id": 30},
            ],
        )
    )
    seed = proposal.ambient_scene_seeds[0]
    entitlements = {
        item.participant_entity_id: item.claim_ids for item in seed.entitlements
    }

    assert entitlements == {1: (10, 11), 2: (20,)}
    assert 30 not in {
        claim_id for values in entitlements.values() for claim_id in values
    }


def test_writer_render_is_compact_optional_and_absent_from_gaia_context() -> None:
    """Ambient seeds render one line for the writer and never enter pass two."""

    seed = _resolve(
        AmbientFakeSession(relationship_rows=_relationship_rows()[:2])
    ).ambient_scene_seeds[0]
    context = {
        "user_input": "Continue.",
        "orrery_ambient_scene_seeds": [seed.model_dump(mode="json")],
    }

    writer_prompt = LogonUtility({})._format_context_prompt(context)
    gaia_prompt = LogonUtility({})._format_context_prompt(
        context, include_ambient_scene_seeds=False
    )

    assert "=== ORRERY AMBIENT SCENE SEEDS ===" in writer_prompt
    assert (
        "Ambient cues are optional; adapt, delay, or ignore them freely, and let "
        "silence stand when the scene wants it."
    ) in writer_prompt
    assert writer_prompt.count(f"- {seed.seed_id} ") == 1
    assert "claims=" in writer_prompt
    assert seed.seed_id not in gaia_prompt
    assert "Ambient cues are optional" not in gaia_prompt


class _ExposureCursor:
    """Record the isolated ambient commit surface."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, Any]] = []
        self._fetchone: Any = None

    def __enter__(self) -> "_ExposureCursor":
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> bool:
        return False

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((sql, params))
        self._fetchone = (
            {"id": len(self.executed)}
            if "INSERT INTO orrery_prompt_exposures" in sql
            else None
        )

    def fetchone(self) -> Any:
        return self._fetchone


class _ExposureConnection:
    def __init__(self, cursor: _ExposureCursor) -> None:
        self.cursor_obj = cursor

    def cursor(self) -> _ExposureCursor:
        return self.cursor_obj


def test_commit_logs_seed_exposure_without_seed_state_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve-to-commit materializes only the seed's existing exposure idiom."""

    proposal = _resolve(AmbientFakeSession(relationship_rows=_relationship_rows()[:2]))
    monkeypatch.setattr(
        orrery_events, "_sweep_expired_entity_tags_sync", lambda *_args, **_kwargs: 0
    )
    monkeypatch.setattr(
        orrery_events,
        "drain_claim_propagation_sync",
        lambda *_args, **_kwargs: PropagationDrainResult(),
    )
    monkeypatch.setattr(
        orrery_events,
        "drain_relationship_drift_sync",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        orrery_events,
        "drain_backstory_reveals_sync",
        lambda *_args, **_kwargs: RevealDrainResult(),
    )
    cursor = _ExposureCursor()

    result = commit_orrery_tick_sync(
        _ExposureConnection(cursor),
        proposal,
        tick_chunk_id=101,
    )

    assert result.prompt_exposure_count == 1
    assert result.resolution_count == 0
    assert result.event_count == 0
    assert len(cursor.executed) == 1
    sql, params = cursor.executed[0]
    assert "INSERT INTO orrery_prompt_exposures" in sql
    assert params[1] == "scene_pressure"
    assert params[2].startswith(f"{AMBIENT_EXPOSURE_TEMPLATE_ID}:")
    assert params[3] == AMBIENT_EXPOSURE_TEMPLATE_ID
    assert params[4] == proposal.ambient_scene_seeds[0].dedup_key


def test_ambient_settings_reject_unbounded_or_invalid_values() -> None:
    """All adjustable ambient limits are validated by the config model."""

    with pytest.raises(ValueError, match="max_seeds"):
        OrreryAmbientSettings(max_seeds=-1)
    with pytest.raises(ValueError, match="expiry_turns"):
        OrreryAmbientSettings(expiry_turns=0)
    with pytest.raises(ValueError, match="line_budget"):
        OrreryAmbientSettings(line_budget=0)
    with pytest.raises(ValueError, match="turn_budget"):
        OrreryAmbientSettings(turn_budget=0)


def test_seed_contract_rejects_silence_false() -> None:
    """The typed contract cannot authorize compulsive non-silent output."""

    seed = _resolve(
        AmbientFakeSession(relationship_rows=_relationship_rows()[:2])
    ).ambient_scene_seeds[0]
    payload = seed.model_dump(mode="json")
    payload["silence_ok"] = False

    with pytest.raises(ValueError, match="silence_ok"):
        AmbientSceneSeed.model_validate(payload)
