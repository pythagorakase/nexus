"""Tests for runtime Retrograde stub maturation (spec decisions 9/10/12).

Offline tests cover the declaration schema, commit-side signal gating, and
event-ref namespacing with recording cursors. PostgreSQL-gated tests run
against save_02 inside transactions that are always rolled back (slot 2 is
the writable working slot and carries migration 062); they are skipped
unless ``NEXUS_RUN_POSTGRES=1`` is set.
"""

from __future__ import annotations

from typing import Any, Iterator, Mapping

import psycopg2
import pytest
from psycopg2.extras import RealDictCursor
from pydantic import ValidationError

import nexus.agents.orrery.retrograde_maturation as retrograde_maturation
from nexus.agents.logon.apex_schema import (
    NewEntityDeclaration,
    StorytellerResponseExtended,
)
from nexus.agents.orrery.retrograde_maturation import (
    MaturationEnqueueResult,
    RetrogradeMaturationVocabularyError,
    _mature_one,
    _load_story_setting,
    _resolve_maturation_weird,
    _slot_label,
    enqueue_declared_entity_maturations,
    namespace_expansion_event_refs,
)
from nexus.api.lore_adapter import extract_new_entities
from nexus.config.settings_models import OrreryRetrogradeMaturationSettings, Settings

SAVE_02_DSN = "postgresql://pythagor@localhost:5432/save_02"


# ============================================================================
# Decision 9 — Declaration Schema
# ============================================================================


def test_new_entity_declaration_minimal() -> None:
    declaration = NewEntityDeclaration(
        kind="place",
        name="The Drowned Atrium",
        summary="A flooded arcology lobby repurposed as a black market.",
    )
    assert declaration.tag_hints == []
    assert declaration.pair_tag_hints == []


def test_new_entity_declaration_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        NewEntityDeclaration(
            kind="item",
            name="Cursed Coin",
            summary="A coin.",
        )


def test_new_entity_declaration_rejects_empty_summary() -> None:
    with pytest.raises(ValidationError):
        NewEntityDeclaration(kind="character", name="Vex", summary="")


def test_new_entity_declaration_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        NewEntityDeclaration.model_validate(
            {
                "kind": "character",
                "name": "Vex",
                "summary": "A fixer.",
                "backstory": "should not be here",
            }
        )


def test_pair_tag_hint_role_validation() -> None:
    declaration = NewEntityDeclaration.model_validate(
        {
            "kind": "character",
            "name": "Vex",
            "summary": "A fixer with old debts.",
            "pair_tag_hints": [
                {
                    "tag": "obligation",
                    "other_entity_name": "Madame Khoroshev",
                    "declared_entity_role": "subject",
                }
            ],
        }
    )
    assert declaration.pair_tag_hints[0].tag == "obligation"
    with pytest.raises(ValidationError):
        NewEntityDeclaration.model_validate(
            {
                "kind": "character",
                "name": "Vex",
                "summary": "A fixer.",
                "pair_tag_hints": [
                    {
                        "tag": "obligation",
                        "other_entity_name": "Madame Khoroshev",
                        "declared_entity_role": "sideways",
                    }
                ],
            }
        )


def test_extended_response_carries_new_entities() -> None:
    response = StorytellerResponseExtended.model_validate(
        {
            "narrative": "A stranger watches from the mezzanine.",
            "choices": ["Approach the stranger.", "Leave quietly."],
            "chunk_metadata": {},
            "referenced_entities": {},
            "state_updates": {},
            "new_entities": [
                {
                    "kind": "character",
                    "name": "The Mezzanine Stranger",
                    "summary": "An observer with an unhealthy interest.",
                }
            ],
        }
    )
    assert response.new_entities[0].name == "The Mezzanine Stranger"
    extracted = extract_new_entities(response)
    assert extracted[0]["kind"] == "character"


def test_extended_response_new_entities_defaults_empty() -> None:
    response = StorytellerResponseExtended.model_validate(
        {
            "narrative": "Nothing new under the neon.",
            "choices": ["Continue.", "Wait."],
            "chunk_metadata": {},
            "referenced_entities": {},
            "state_updates": {},
        }
    )
    assert response.new_entities == []
    assert extract_new_entities(response) == []


# ============================================================================
# Decision 12 — Commit-Side Signal Gating (Offline Recording Cursor)
# ============================================================================


class _RecordingCursor:
    """Minimal cursor double for the enqueue SQL branches."""

    def __init__(
        self,
        *,
        existing_entity_rows: list[tuple[int, int]],
        job_insert_returns: list[Any],
    ) -> None:
        self.existing_entity_rows = existing_entity_rows
        self.job_insert_returns = list(job_insert_returns)
        self.executed: list[tuple[str, Any]] = []
        self._fetchall: list[Any] = []
        self._fetchone: Any = None

    def __enter__(self) -> "_RecordingCursor":
        return self

    def __exit__(self, *_args: Any) -> bool:
        return False

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((sql, params))
        normalized = " ".join(str(sql).split())
        self._fetchall = []
        self._fetchone = None
        if "FROM tag_category_registry" in normalized:
            self._fetchall = [("bodyform",), ("disposition",)]
        elif "FROM tags" in normalized:
            self._fetchone = None
        elif "FROM characters WHERE name" in normalized:
            self._fetchall = self.existing_entity_rows
        elif "INSERT INTO orrery_maturation_jobs" in normalized:
            self._fetchone = self.job_insert_returns.pop(0)

    def fetchall(self) -> list[Any]:
        return self._fetchall

    def fetchone(self) -> Any:
        return self._fetchone


class _RecordingConnection:
    def __init__(self, cursor: _RecordingCursor) -> None:
        self._cursor = cursor

    def cursor(self, *_args: Any, **_kwargs: Any) -> _RecordingCursor:
        return self._cursor


_ENABLED_SETTINGS: Mapping[str, Any] = {
    "orrery": {"retrograde": {"maturation": {"enabled": True}}}
}
_DISABLED_SETTINGS: Mapping[str, Any] = {
    "orrery": {"retrograde": {"maturation": {"enabled": False}}}
}

_DECLARATION = {
    "kind": "character",
    "name": "Sister Anechka",
    "summary": "A street medic who patches up the district's losers.",
}


def test_enqueue_skips_when_disabled() -> None:
    cursor = _RecordingCursor(existing_entity_rows=[], job_insert_returns=[])
    conn = _RecordingConnection(cursor)
    result = enqueue_declared_entity_maturations(
        conn,
        declarations=[_DECLARATION],
        chunk_id=10,
        raw_text="Sister Anechka kneels beside the wounded courier.",
        slot=2,
        settings=_DISABLED_SETTINGS,
    )
    assert result == MaturationEnqueueResult(declared=1, skipped_disabled=1)
    assert cursor.executed == []


def test_enqueue_requires_engagement_signal() -> None:
    """Declared but absent from the committed text -> stub only, no job."""

    cursor = _RecordingCursor(
        existing_entity_rows=[(7, 77)],
        job_insert_returns=[],
    )
    conn = _RecordingConnection(cursor)
    result = enqueue_declared_entity_maturations(
        conn,
        declarations=[_DECLARATION],
        chunk_id=10,
        raw_text="The courier bleeds out alone; nobody comes.",
        slot=2,
        settings=_ENABLED_SETTINGS,
    )
    assert result.declared == 1
    assert result.signal_absent == 1
    assert result.jobs_enqueued == 0
    assert not any(
        "INSERT INTO orrery_maturation_jobs" in sql for sql, _ in cursor.executed
    )


def test_enqueue_inserts_job_when_name_appears() -> None:
    cursor = _RecordingCursor(
        existing_entity_rows=[(7, 77)],
        job_insert_returns=[{"id": 1}],
    )
    conn = _RecordingConnection(cursor)
    result = enqueue_declared_entity_maturations(
        conn,
        declarations=[_DECLARATION],
        chunk_id=10,
        raw_text="sister anechka kneels beside the wounded courier.",
        slot=2,
        settings=_ENABLED_SETTINGS,
    )
    assert result.jobs_enqueued == 1
    assert result.stubs_created == 0
    insert_sql, insert_params = next(
        (sql, params)
        for sql, params in cursor.executed
        if "INSERT INTO orrery_maturation_jobs" in sql
    )
    assert "ON CONFLICT (entity_id) DO NOTHING" in insert_sql
    assert insert_params[0] == 77  # global entity_id
    assert insert_params[5] == 10  # requesting chunk


def test_enqueue_conflict_counts_already_present() -> None:
    cursor = _RecordingCursor(
        existing_entity_rows=[(7, 77)],
        job_insert_returns=[None],
    )
    conn = _RecordingConnection(cursor)
    result = enqueue_declared_entity_maturations(
        conn,
        declarations=[_DECLARATION],
        chunk_id=11,
        raw_text="Sister Anechka again, still stitching.",
        slot=2,
        settings=_ENABLED_SETTINGS,
    )
    assert result.jobs_enqueued == 0
    assert result.jobs_already_present == 1


def test_enqueue_rejects_ambiguous_names() -> None:
    cursor = _RecordingCursor(
        existing_entity_rows=[(7, 77), (8, 88)],
        job_insert_returns=[],
    )
    conn = _RecordingConnection(cursor)
    with pytest.raises(ValueError, match="ambiguous"):
        enqueue_declared_entity_maturations(
            conn,
            declarations=[_DECLARATION],
            chunk_id=10,
            raw_text="Sister Anechka kneels.",
            slot=2,
            settings=_ENABLED_SETTINGS,
        )


def test_enqueue_validates_whole_declaration_batch_before_stub_processing() -> None:
    """The accept-time backstop rejects the turn before any entity mutation."""

    cursor = _RecordingCursor(existing_entity_rows=[], job_insert_returns=[])
    conn = _RecordingConnection(cursor)
    invalid_declaration = {
        "kind": "character",
        "name": "The Hallucinated Clerk",
        "summary": "A clerk carrying an unregistered declaration hint.",
        "tag_hints": ["invented:tag"],
    }

    with pytest.raises(
        RetrogradeMaturationVocabularyError,
        match=r"new_entities\[1\]\.tag_hints",
    ):
        enqueue_declared_entity_maturations(
            conn,
            declarations=[_DECLARATION, invalid_declaration],
            chunk_id=10,
            raw_text="Sister Anechka meets The Hallucinated Clerk.",
            slot=2,
            settings=_ENABLED_SETTINGS,
        )

    assert not any(
        "FROM characters WHERE name" in " ".join(sql.split())
        for sql, _params in cursor.executed
    )
    assert not any(
        "INSERT INTO" in sql or "UPDATE " in sql for sql, _params in cursor.executed
    )


# ============================================================================
# Decision 10 — Event-Ref Namespacing
# ============================================================================


def test_namespace_expansion_event_refs_rewrites_consistently() -> None:
    payload = {
        "selected_seed_ids": ["S1"],
        "event_plan": [
            {"event_ref": "EV1", "seed_ids": ["S1"]},
            {"event_ref": "EV2", "seed_ids": ["S1"]},
        ],
        "thread_plan": [
            {"seed_id": "S1", "status": "woven", "event_refs": ["EV1", "EV2"]}
        ],
        "entity_tag_plan": [{"tag": "vanished", "source_event_ref": "EV1"}],
        "pair_tag_plan": [{"tag": "protects", "source_event_ref": None}],
        "relationship_plan": [
            {"relationship_type": "rival", "source_event_ref": "EV2"}
        ],
        "death_plan": [
            {
                "entity_ref": "Vale",
                "entity_kind": "character",
                "cause_event_ref": "EV1",
            }
        ],
    }
    rewritten = namespace_expansion_event_refs(payload, prefix="maturation_job_42")
    assert rewritten["event_plan"][0]["event_ref"] == "maturation_job_42_EV1"
    assert rewritten["thread_plan"][0]["event_refs"] == [
        "maturation_job_42_EV1",
        "maturation_job_42_EV2",
    ]
    assert (
        rewritten["entity_tag_plan"][0]["source_event_ref"] == "maturation_job_42_EV1"
    )
    assert rewritten["pair_tag_plan"][0]["source_event_ref"] is None
    assert (
        rewritten["relationship_plan"][0]["source_event_ref"] == "maturation_job_42_EV2"
    )
    assert rewritten["death_plan"][0]["cause_event_ref"] == "maturation_job_42_EV1"
    # Original payload untouched.
    assert payload["event_plan"][0]["event_ref"] == "EV1"


def test_namespace_leaves_unknown_source_refs_for_validation() -> None:
    payload = {
        "event_plan": [{"event_ref": "EV1"}],
        "thread_plan": [],
        "entity_tag_plan": [{"tag": "cursed", "source_event_ref": "EV9"}],
        "pair_tag_plan": [],
        "relationship_plan": [],
    }
    rewritten = namespace_expansion_event_refs(payload, prefix="maturation_job_7")
    assert rewritten["entity_tag_plan"][0]["source_event_ref"] == "EV9"


# ============================================================================
# Genre-Banded Maturation Weird (#442)
# ============================================================================


def test_resolve_maturation_weird_contracts_the_genre_band() -> None:
    """entropy(cold_start) > entropy(maturation): same floor, lower ceiling."""

    from nexus.agents.orrery.retrograde_packet import resolve_weird_profile
    from nexus.config import load_settings

    settings = load_settings()
    cfg = settings.orrery.retrograde.maturation
    setting = {"genre": "fantasy", "secondary_genres": ["mystery"]}

    cold = resolve_weird_profile(
        settings=settings,
        setting=setting,
        weird_level=cfg.weird_level,
    )
    maturation = _resolve_maturation_weird(
        settings=settings,
        setting=setting,
        cfg=cfg,
    )

    assert maturation["source"] == "maturation_band"
    assert maturation["genre"] == cold["genre"]
    assert maturation["raw_min"] == cold["raw_min"]
    expected_max = cold["raw_min"] + (cold["raw_max"] - cold["raw_min"]) * float(
        cfg.weird_band_fraction
    )
    assert maturation["raw_max"] == pytest.approx(expected_max)
    # The configured default must actually contract; 1.0 would silently
    # erase the cold-start/maturation entropy distinction.
    assert cfg.weird_band_fraction < 1.0
    assert maturation["raw_max"] < cold["raw_max"]
    # No raw override: the R3 graph builder rolls within the band.
    assert "raw" not in maturation


def test_load_story_setting_raises_on_missing_payload() -> None:
    """A slot without a persisted wizard setting fails loudly, not silently."""

    class _EmptySettingCursor:
        def execute(self, sql: str, params: Any = None) -> None:
            assert "global_variables" in sql

        def fetchone(self) -> Any:
            return {"setting": None}

    with pytest.raises(ValueError, match="global_variables.setting"):
        _load_story_setting(_EmptySettingCursor())


def test_maturation_persistence_uses_injected_epistemics_settings(
    monkeypatch: Any,
) -> None:
    """One drain uses its settings snapshot instead of re-reading nexus.toml."""

    class Cursor:
        def __init__(self) -> None:
            self.executed: list[tuple[str, Any]] = []

        def __enter__(self) -> "Cursor":
            return self

        def __exit__(self, *_args: Any) -> bool:
            return False

        def execute(self, sql: str, params: Any = None) -> None:
            self.executed.append((sql, params))

    class Connection:
        def __init__(self) -> None:
            self.cursor_obj = Cursor()

        def __enter__(self) -> "Connection":
            return self

        def __exit__(self, *_args: Any) -> bool:
            return False

        def cursor(self, *_args: Any, **_kwargs: Any) -> Cursor:
            return self.cursor_obj

    injected_policy = {
        "enabled": True,
        "claim_event_types": ["threat_issued"],
        "aware_roles": ["actor", "target"],
    }
    settings = retrograde_maturation.load_settings_as_dict()
    settings["orrery"]["epistemics"] = injected_policy
    typed_settings = Settings.model_validate(
        {
            key: value
            for key, value in settings.items()
            if key not in {"Agent Settings", "API Settings"}
        }
    )
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        retrograde_maturation,
        "load_settings_as_dict",
        lambda: (_ for _ in ()).throw(AssertionError("unexpected settings reload")),
    )
    monkeypatch.setattr(
        "nexus.api.slot_utils.require_slot_dbname", lambda slot: "save_02"
    )
    monkeypatch.setattr(retrograde_maturation, "_entity_event_count", lambda *_: 0)
    monkeypatch.setattr(
        retrograde_maturation,
        "_load_job_context",
        lambda *_args, **_kwargs: {"entity_summary": "A fixer."},
    )
    monkeypatch.setattr(
        retrograde_maturation,
        "_load_story_setting",
        lambda *_: {"genre": "noir"},
    )
    monkeypatch.setattr(
        "nexus.agents.orrery.retrograde_vocabulary.enumerate_seed_eligible_vocabulary",
        lambda _dbname: object(),
    )
    monkeypatch.setattr(
        retrograde_maturation,
        "build_runtime_maturation_packet",
        lambda **_kwargs: {"packet": True},
    )
    monkeypatch.setattr(
        "nexus.agents.orrery.retrograde_seed_candidates.run_seed_stage",
        lambda **_kwargs: {
            "model": "seed-model",
            "seed_candidate_response": {"selected_seed_ids": ["seed_1"]},
        },
    )
    monkeypatch.setattr(
        "nexus.agents.orrery.retrograde_expansion.generate_expansion_with_skald",
        lambda **_kwargs: {
            "model": "expansion-model",
            "retrograde_expansion_plan": {
                "event_plan": [],
                "thread_plan": [],
                "entity_tag_plan": [],
                "pair_tag_plan": [],
                "relationship_plan": [],
                "death_plan": [],
            },
        },
    )

    def persist(_cur: Any, **kwargs: Any) -> dict[str, Any]:
        captured["epistemics_settings"] = kwargs["epistemics_settings"]
        return {
            "counters": {},
            "commit_readiness": {"event_ref_to_id": {}},
            "retrieval": {"embedding_pending_summary_ids": []},
        }

    monkeypatch.setattr(
        "nexus.agents.orrery.retrograde_persistence.build_retrograde_persistence_plan",
        persist,
    )
    monkeypatch.setattr(
        retrograde_maturation,
        "_finish_embedding",
        lambda _conn, **kwargs: kwargs["manifest"],
    )

    manifest = _mature_one(
        Connection(),
        row={
            "job_id": 7,
            "entity_id": 77,
            "entity_kind": "character",
            "entity_subtype_id": 17,
            "entity_name": "Vex",
            "requesting_chunk_id": 101,
            "declaration": {"summary": "A fixer."},
            "result_manifest": {},
            "slot": "2",
        },
        cfg=OrreryRetrogradeMaturationSettings(),
        settings_dict=settings,
        settings=typed_settings,
        slot=2,
    )

    assert captured["epistemics_settings"] is typed_settings.orrery.epistemics
    assert captured["epistemics_settings"].model_dump() == injected_policy
    assert manifest["persisted"] is True


def test_required_geo_runs_expansion_when_seed_selection_is_empty(
    monkeypatch: Any,
) -> None:
    """A place point is authored even when R5 selects no history seeds."""

    class Cursor:
        def __init__(self) -> None:
            self.executed: list[tuple[str, Any]] = []

        def __enter__(self) -> "Cursor":
            return self

        def __exit__(self, *_args: Any) -> bool:
            return False

        def execute(self, sql: str, params: Any = None) -> None:
            self.executed.append((sql, params))

    class Connection:
        def __init__(self) -> None:
            self.cursor_obj = Cursor()

        def __enter__(self) -> "Connection":
            return self

        def __exit__(self, *_args: Any) -> bool:
            return False

        def cursor(self, *_args: Any, **_kwargs: Any) -> Cursor:
            return self.cursor_obj

    settings = retrograde_maturation.load_settings_as_dict()
    typed_settings = Settings.model_validate(
        {
            key: value
            for key, value in settings.items()
            if key not in {"Agent Settings", "API Settings"}
        }
    )
    expansion_calls: list[dict[str, Any]] = []
    applied_coordinates: list[Mapping[str, Any]] = []

    monkeypatch.setattr(
        "nexus.api.slot_utils.require_slot_dbname", lambda slot: "save_02"
    )
    monkeypatch.setattr(retrograde_maturation, "_entity_event_count", lambda *_: 0)
    monkeypatch.setattr(
        retrograde_maturation,
        "_load_job_context",
        lambda *_args, **_kwargs: {"entity_summary": "A remote station."},
    )
    monkeypatch.setattr(
        retrograde_maturation,
        "_load_story_setting",
        lambda *_: {"genre": "noir"},
    )
    monkeypatch.setattr(
        "nexus.agents.orrery.retrograde_vocabulary.enumerate_seed_eligible_vocabulary",
        lambda _dbname: object(),
    )
    monkeypatch.setattr(
        retrograde_maturation,
        "build_runtime_maturation_packet",
        lambda **_kwargs: {"geo_authoring": {"required": True}},
    )
    monkeypatch.setattr(
        "nexus.agents.orrery.retrograde_seed_candidates.run_seed_stage",
        lambda **_kwargs: {
            "model": "seed-model",
            "seed_candidate_response": {"selected_seed_ids": []},
        },
    )

    def generate_expansion(**kwargs: Any) -> dict[str, Any]:
        expansion_calls.append(kwargs)
        return {
            "model": "expansion-model",
            "retrograde_expansion_plan": {
                "coordinates": {"lat": 50.0, "lon": 50.0},
                "event_plan": [],
                "thread_plan": [],
                "entity_tag_plan": [],
                "pair_tag_plan": [],
                "relationship_plan": [],
                "death_plan": [],
            },
        }

    monkeypatch.setattr(
        "nexus.agents.orrery.retrograde_expansion.generate_expansion_with_skald",
        generate_expansion,
    )
    monkeypatch.setattr(
        retrograde_maturation,
        "_apply_maturation_coordinates",
        lambda _cur, **kwargs: applied_coordinates.append(kwargs["expansion_payload"]),
    )

    manifest = _mature_one(
        Connection(),
        row={
            "job_id": 8,
            "entity_id": 78,
            "entity_kind": "place",
            "entity_subtype_id": 18,
            "entity_name": "Remote Observatory",
            "requesting_chunk_id": 102,
            "declaration": {"summary": "A remote station."},
            "result_manifest": {},
            "slot": "2",
        },
        cfg=OrreryRetrogradeMaturationSettings(),
        settings_dict=settings,
        settings=typed_settings,
        slot=2,
    )

    assert len(expansion_calls) == 1
    assert applied_coordinates[0]["coordinates"] == {"lat": 50.0, "lon": 50.0}
    assert manifest["coordinates_persisted"] is True
    assert manifest["skipped"] == "no_seeds_selected"


# ============================================================================
# PostgreSQL-Gated Queue Tests (save_02, always rolled back)
# ============================================================================


pytestmark_pg = pytest.mark.requires_postgres


@pytest.fixture()
def save_02_conn() -> Iterator[Any]:
    """Open a save_02 connection whose transaction is always rolled back."""

    conn = psycopg2.connect(SAVE_02_DSN)
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.requires_postgres
def test_pg_enqueue_creates_stub_and_job(save_02_conn: Any) -> None:
    declaration = {
        "kind": "character",
        "name": "M8 Test Entity (Rollback)",
        "summary": "A maturation-test stub that never commits.",
    }
    chunk_id = _latest_chunk_id(save_02_conn)
    result = enqueue_declared_entity_maturations(
        save_02_conn,
        declarations=[declaration],
        chunk_id=chunk_id,
        raw_text="The M8 Test Entity (Rollback) appears in this chunk.",
        slot=2,
        settings=_ENABLED_SETTINGS,
    )
    assert result.stubs_created == 1
    assert result.jobs_enqueued == 1

    with save_02_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT j.entity_name, j.state::text AS state, c.summary
            FROM orrery_maturation_jobs j
            JOIN characters c ON c.entity_id = j.entity_id
            WHERE j.entity_name = %s
            """,
            (declaration["name"],),
        )
        row = cur.fetchone()
    assert row is not None
    assert row["state"] == "queued"
    assert row["summary"] == declaration["summary"]


@pytest.mark.requires_postgres
def test_pg_enqueue_is_idempotent_per_entity(save_02_conn: Any) -> None:
    declaration = {
        "kind": "character",
        "name": "M8 Idempotency Entity (Rollback)",
        "summary": "Declared twice, enqueued once.",
    }
    chunk_id = _latest_chunk_id(save_02_conn)
    first = enqueue_declared_entity_maturations(
        save_02_conn,
        declarations=[declaration],
        chunk_id=chunk_id,
        raw_text="M8 Idempotency Entity (Rollback) steps into frame.",
        slot=2,
        settings=_ENABLED_SETTINGS,
    )
    second = enqueue_declared_entity_maturations(
        save_02_conn,
        declarations=[declaration],
        chunk_id=chunk_id,
        raw_text="M8 Idempotency Entity (Rollback) returns.",
        slot=2,
        settings=_ENABLED_SETTINGS,
    )
    assert first.jobs_enqueued == 1
    assert second.jobs_enqueued == 0
    assert second.jobs_already_present == 1
    assert second.stubs_created == 0

    with save_02_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT count(*) AS n FROM orrery_maturation_jobs WHERE entity_name = %s",
            (declaration["name"],),
        )
        assert int(cur.fetchone()["n"]) == 1


@pytest.mark.requires_postgres
def test_pg_unregistered_tag_hint_fails_loudly(save_02_conn: Any) -> None:
    declaration = {
        "kind": "character",
        "name": "M8 Bad Hint Entity (Rollback)",
        "summary": "Carries a hallucinated tag.",
        "tag_hints": ["definitely_not_a_registered_tag_xyz"],
    }
    chunk_id = _latest_chunk_id(save_02_conn)
    with pytest.raises(ValueError):
        enqueue_declared_entity_maturations(
            save_02_conn,
            declarations=[declaration],
            chunk_id=chunk_id,
            raw_text="M8 Bad Hint Entity (Rollback) appears.",
            slot=2,
            settings=_ENABLED_SETTINGS,
        )


@pytest.mark.requires_postgres
def test_pg_unregistered_pair_tag_hint_fails_loudly(save_02_conn: Any) -> None:
    declaration = {
        "kind": "character",
        "name": "M8 Bad Pair Hint Entity (Rollback)",
        "summary": "Carries a hallucinated pair tag.",
        "pair_tag_hints": [
            {
                "tag": "definitely_not_a_pair_tag_xyz",
                "other_entity_name": "Anyone",
                "declared_entity_role": "subject",
            }
        ],
    }
    chunk_id = _latest_chunk_id(save_02_conn)
    with pytest.raises(RetrogradeMaturationVocabularyError):
        enqueue_declared_entity_maturations(
            save_02_conn,
            declarations=[declaration],
            chunk_id=chunk_id,
            raw_text="M8 Bad Pair Hint Entity (Rollback) appears.",
            slot=2,
            settings=_ENABLED_SETTINGS,
        )


def _latest_chunk_id(conn: Any) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT max(id) FROM narrative_chunks")
        return int(cur.fetchone()[0])


# ============================================================================
# Slot Routing — Enqueue Must Fail Loudly When the Slot Is Unresolvable
# ============================================================================


def test_slot_label_resolves_explicit_slot() -> None:
    assert _slot_label(2) == "2"


def test_slot_label_resolves_env_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_SLOT", "3")
    assert _slot_label(None) == "3"


def test_slot_label_raises_when_unresolvable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A job's slot routes the drain worker's DB connection; an
    unresolvable slot must fail at enqueue time, not produce a job no
    drain can ever process."""

    monkeypatch.delenv("NEXUS_SLOT", raising=False)
    with pytest.raises(RuntimeError, match="NEXUS_SLOT"):
        _slot_label(None)
