"""Offline proof of the joined turn observation over real JSONL ledgers.

The usage and prompt-window ledgers are written through the production
recorders into the conftest-isolated usage directory; the inspection dict has
the exact shape ``inspect_turn`` returns from PostgreSQL.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
import json
from typing import Any, Optional
from uuid import uuid4

import pytest

from nexus import cli
from nexus.agents.lore.seat_blocks import influence_role, influence_token_totals
from nexus.telemetry.attempt_manifest import identity_hash, validation_metadata
from nexus.telemetry.prompt_window import PromptWindowRecord
from nexus.telemetry.turn_observation import (
    SCHEMA_VERSION,
    UNKNOWN,
    derive_turn_observation,
    format_turn_summary,
    ledger_days,
    observe_turn,
    read_turn_ledgers,
)
from nexus.telemetry.usage import UsageEvent, record_prompt_window, record_usage_event

# Read once, so a run that straddles UTC midnight keeps one pair of days.
TODAY = datetime.now(timezone.utc).date()
YESTERDAY = TODAY - timedelta(days=1)
READ_AT = datetime.combine(TODAY, time(12), tzinfo=timezone.utc)
WRITER_BLOCKS = {
    "system": 4580,
    "recent narrative": 14031,
    "entity dossier": 2194,
    "user input": 26,
    "writer closer": 30,
    "request framing": -84,
}
GAIA_BLOCKS = {
    "system": 1900,
    "recent narrative": 14031,
    "finished writer output": 164,
    "gaia closer": 40,
    "request framing": -85,
}
REPAIR_NOTES: list[dict[str, Any]] = [
    {
        "repair": "active-extend-expiry",
        "entity_kind": "character",
        "entity_id": 42,
        "entity_name": "private name",
    },
    {"repair": "scene-reset-crossings", "moved": ["private name"], "dropped": []},
]
REJECTION_NOTES: list[dict[str, Any]] = [
    {"rejection": "wire-contract-violation", "error": "private generated prose"}
]


def _window(
    session: str,
    seat: str,
    attempt: int,
    model: str,
    blocks: dict[str, int],
    *,
    roles: bool = True,
    notes: Optional[list[dict[str, Any]]] = None,
) -> PromptWindowRecord:
    tokens = sum(blocks.values())
    return PromptWindowRecord(
        generation_session=session,
        seat=seat,
        attempt=attempt,
        model=model,
        block_tokens=blocks,
        influence_tokens=influence_token_totals(blocks) if roles else {},
        input_tokens=tokens,
        effective_ceiling=71000,
        policy_headroom=4000,
        headroom=71000 - tokens,
        validation_notes=list(notes or []),
    )


def _manifest(
    record: PromptWindowRecord,
    *,
    provider_outcome: Optional[str],
    outcome: Optional[str] = "accepted",
) -> dict[str, Any]:
    """Build one row exactly as ``inspect_turn`` returns it."""
    included = {
        "block_tokens",
        "input_tokens",
        "effective_ceiling",
        "policy_headroom",
        "headroom",
    }
    if record.influence_tokens:
        included.add("influence_tokens")
    return {
        "generation_session_id": record.generation_session,
        "seat": record.seat,
        "attempt": record.attempt,
        "schema_version": 1,
        "blocks": [
            {
                "kind": kind,
                "tokens": tokens,
                "sha256": identity_hash(kind),
                "influence_role": influence_role(kind),
            }
            for kind, tokens in record.block_tokens.items()
        ],
        "window_record": record.model_dump(include=included),
        "retrieval_ids": [51],
        "recall_ids": [162, 163],
        "exposure_ids": [388, 389],
        "model_id": record.model,
        "story_pin": {"model": record.model, "gaia_model": record.model},
        "config_sha256": identity_hash("config"),
        "wire_schema_sha256": identity_hash("wire"),
        "prompt_sha256": identity_hash("prompt"),
        "response_sha256": identity_hash("response") if provider_outcome else None,
        "validation": validation_metadata(record.validation_notes),
        "outcome": outcome,
        "provider_outcome": provider_outcome,
        "created_at": "2026-09-24 21:24:55.0647+00",
        "updated_at": "2026-09-24 21:24:56.197384+00",
    }


def _event(
    session: str,
    ts: str,
    seat: str,
    attempt: int,
    model: str,
    **fields: Any,
) -> UsageEvent:
    anthropic = fields.pop("anthropic", False)
    return UsageEvent(
        ts=ts,
        provider="anthropic" if anthropic else "openai",
        model=model,
        seat=seat,
        slot=4,
        run_id=session,
        attempt=attempt,
        transport="anthropic_messages" if anthropic else "responses",
        **fields,
    )


def _two_pass_turn() -> tuple[dict[str, Any], str, str]:
    """Record a writer pass before UTC midnight and three Gaia attempts after it."""
    session = str(uuid4())
    writer = _window(session, "skald_writer", 1, "writer-model", WRITER_BLOCKS)
    # Gaia 1 is a manifest written before influence roles were declared.
    gaia = [
        _window(session, "gaia", 1, "gaia-model", GAIA_BLOCKS, roles=False),
        _window(session, "gaia", 2, "gaia-model", GAIA_BLOCKS, notes=REJECTION_NOTES),
        _window(session, "gaia", 3, "gaia-model", GAIA_BLOCKS, notes=REPAIR_NOTES),
    ]
    for record in (writer, *gaia):
        record_prompt_window(record)
    other = str(uuid4())
    record_prompt_window(
        _window(other, "skald_writer", 1, "writer-model", {"system": 1})
    )

    record_usage_event(
        _event(
            session,
            f"{YESTERDAY}T23:59:59.500000Z",
            "skald_writer",
            1,
            "writer-model",
            outcome="accepted",
            input_tokens=20777,
            output_tokens=2100,
            total_tokens=22877,
            cached_input_tokens=12288,
            reasoning_tokens=800,
            reasoning_effort="high",
            max_output_tokens=8000,
        )
    )
    # Gaia 1 timed out without a response: the provider reported no usage.
    record_usage_event(
        _event(
            session,
            f"{TODAY}T00:00:05Z",
            "gaia",
            2,
            "gaia-model",
            anthropic=True,
            outcome="rejected_validation",
            input_tokens=3000,
            output_tokens=900,
            total_tokens=3900,
            cached_input_tokens=13000,
            cache_creation_tokens=50,
            max_output_tokens=4000,
        )
    )
    record_usage_event(
        _event(
            session,
            f"{TODAY}T00:00:10Z",
            "gaia",
            3,
            "gaia-model",
            anthropic=True,
            outcome="accepted",
            input_tokens=3100,
            output_tokens=950,
            total_tokens=4050,
            cached_input_tokens=13000,
            cache_creation_tokens=0,
            max_output_tokens=4000,
        )
    )
    record_usage_event(
        _event(
            session,
            f"{TODAY}T00:00:20.200000Z",
            "correspondence_compaction",
            1,
            "compaction-model",
            outcome="accepted",
            input_tokens=5000,
            output_tokens=300,
            total_tokens=5300,
            cached_input_tokens=0,
            reasoning_tokens=0,
            reasoning_effort="low",
            max_output_tokens=2000,
        )
    )
    # Another run on a read day, and this run on a day no phase spans.
    record_usage_event(
        _event(
            other,
            f"{TODAY}T00:00:06Z",
            "gaia",
            1,
            "gaia-model",
            outcome="accepted",
            input_tokens=999999,
            output_tokens=1,
            total_tokens=1000000,
        )
    )
    record_usage_event(
        _event(
            session,
            f"{YESTERDAY - timedelta(days=1)}T12:00:00Z",
            "skald_writer",
            9,
            "writer-model",
            outcome="accepted",
            input_tokens=777,
            output_tokens=1,
            total_tokens=778,
        )
    )
    inspection = {
        "session": {
            "session_id": session,
            "operation": "continue",
            "parent_chunk_id": 50,
            "phase": "complete",
            "terminal_outcome": "accepted",
            "accepted_chunk_id": 51,
            "replaced_by_session_id": None,
            "error_class": None,
        },
        # recorded_at::text as PostgreSQL renders it, including a session in
        # another time zone for the Gaia transition.
        "phases": [
            {"phase": "retrieval", "recorded_at": f"{YESTERDAY} 23:59:30.25+00"},
            {"phase": "assembly", "recorded_at": f"{YESTERDAY} 23:59:38.5+00"},
            {"phase": "writer", "recorded_at": f"{YESTERDAY} 23:59:41+00"},
            {"phase": "gaia", "recorded_at": f"{YESTERDAY} 19:00:11.125-05"},
            {"phase": "staging", "recorded_at": f"{TODAY} 00:00:20+00"},
            {"phase": "complete", "recorded_at": f"{TODAY} 00:00:20.5+00"},
        ],
        "manifests": [
            _manifest(gaia[0], provider_outcome="error"),
            _manifest(gaia[1], provider_outcome="rejected_validation"),
            _manifest(gaia[2], provider_outcome="accepted"),
            _manifest(writer, provider_outcome="accepted"),
        ],
        "jobs": [
            {
                "id": 2,
                "state": "queued",
                "generation_session_id": session,
                "queue": "correspondence_compaction",
            },
            {
                "id": 7,
                "state": "succeeded",
                "generation_session_id": session,
                "queue": "experience_render",
            },
            {
                "id": 8,
                "state": "queued",
                "generation_session_id": session,
                "queue": "experience_render",
            },
            {
                "id": 9,
                "state": "succeeded",
                "generation_session_id": session,
                "queue": "experience_render",
            },
        ],
    }
    return inspection, session, other


def _by_key(observation: dict[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
    return {
        (attempt["seat"], attempt["attempt"]): attempt
        for attempt in observation["attempts"]
    }


def test_observation_joins_each_attempt_with_its_provider_usage() -> None:
    """Manifest windows, validation codes and ledger tokens join per attempt."""
    inspection, session, _ = _two_pass_turn()
    observation = observe_turn(inspection, read_at=READ_AT)

    assert observation["schema_version"] == SCHEMA_VERSION == 1
    assert observation["generation_session"] == session
    assert observation["read_at"] == f"{TODAY}T12:00:00Z"
    assert observation["ledger_days_read"] == [str(YESTERDAY), str(TODAY)]
    assert observation["terminal_outcome"] == "accepted"
    attempts = _by_key(observation)
    # Sorted, stable keys; the run on an unspanned day never joins.
    assert list(attempts) == [
        ("correspondence_compaction", 1),
        ("gaia", 1),
        ("gaia", 2),
        ("gaia", 3),
        ("skald_writer", 1),
    ]
    assert all(row["generation_session"] == session for row in attempts.values())

    writer = attempts[("skald_writer", 1)]
    assert writer["model"] == "writer-model"
    assert (writer["outcome"], writer["provider_outcome"]) == ("accepted", "accepted")
    assert writer["window"] == {
        "provenance": "attempt_manifest",
        "input_tokens": 20777,
        "effective_ceiling": 71000,
        "policy_headroom": 4000,
        "headroom": 50223,
        "block_tokens_total": 20777,
        "block_tokens": WRITER_BLOCKS,
        "influence_tokens": {
            "voice_source": 18611,
            "player_language": 26,
            "canonical_evidence": 2194,
            "authorial_plan": -54,
        },
    }
    assert writer["usage"] == {
        "provenance": "provider_usage_ledger",
        "events": 1,
        "provider": "openai",
        "transport": "responses",
        "outcomes": ["accepted"],
        "input_tokens": 20777,
        "output_tokens": 2100,
        "cached_input_tokens": 12288,
        "cache_creation_tokens": UNKNOWN,
        "reasoning_tokens": 800,
        "reasoning_effort": "high",
        "max_output_tokens": 8000,
    }
    assert writer["validation"] == {
        "provenance": "attempt_manifest",
        "notes": 0,
        "repairs": 0,
        "repair_codes": [],
        "rejections": 0,
        "rejection_codes": [],
    }

    timed_out = attempts[("gaia", 1)]
    assert timed_out["provider_outcome"] == "error"
    assert timed_out["window"]["influence_tokens"] == UNKNOWN
    assert timed_out["window"]["block_tokens_total"] == 16050
    assert timed_out["usage"]["provenance"] == UNKNOWN
    assert timed_out["usage"]["events"] == 0
    assert timed_out["usage"]["input_tokens"] == UNKNOWN

    rejected = attempts[("gaia", 2)]
    assert rejected["provider_outcome"] == "rejected_validation"
    assert rejected["validation"]["rejection_codes"] == ["wire-contract-violation"]
    assert rejected["usage"]["outcomes"] == ["rejected_validation"]
    assert rejected["usage"]["cached_input_tokens"] == 13000
    assert rejected["usage"]["cache_creation_tokens"] == 50
    assert rejected["usage"]["reasoning_tokens"] == UNKNOWN
    assert rejected["usage"]["reasoning_effort"] is None

    repaired = attempts[("gaia", 3)]
    assert repaired["validation"]["repairs"] == 2
    assert repaired["validation"]["repair_codes"] == [
        "active-extend-expiry",
        "scene-reset-crossings",
    ]
    assert repaired["usage"]["cache_creation_tokens"] == 0

    compaction = attempts[("correspondence_compaction", 1)]
    assert compaction["model"] == "compaction-model"
    assert compaction["outcome"] == UNKNOWN
    assert compaction["window"]["provenance"] == UNKNOWN
    assert compaction["validation"]["provenance"] == UNKNOWN
    assert compaction["usage"]["reasoning_effort"] == "low"

    assert json.loads(json.dumps(observation)) == observation
    assert "private" not in json.dumps(observation)


def test_usage_totals_stay_unknown_where_any_attempt_went_unreported() -> None:
    """Totals sum provider truth only; one unreported field makes it unknown."""
    inspection, _, _ = _two_pass_turn()
    observation = observe_turn(inspection, read_at=READ_AT)

    assert observation["usage_totals"] == {
        "provenance": "provider_usage_ledger",
        "events": 4,
        "attempts_without_usage": 1,
        "input_tokens": 20777 + 3000 + 3100 + 5000,
        "output_tokens": 2100 + 900 + 950 + 300,
        "cached_input_tokens": 12288 + 13000 + 13000 + 0,
        "cache_creation_tokens": UNKNOWN,
        "reasoning_tokens": UNKNOWN,
    }
    assert observation["jobs"] == {
        "total": 4,
        "by_queue": {
            "correspondence_compaction": {"queued": 1},
            "experience_render": {"queued": 1, "succeeded": 2},
        },
    }


def test_phase_spans_cross_utc_midnight_and_offsets() -> None:
    """Consecutive transitions become spans; the last one stays open."""
    inspection, _, _ = _two_pass_turn()
    observation = observe_turn(inspection, read_at=READ_AT)

    assert [(span["phase"], span["seconds"]) for span in observation["phases"]] == [
        ("retrieval", 8.25),
        ("assembly", 2.5),
        ("writer", 30.125),
        ("gaia", 8.875),
        ("staging", 0.5),
        ("complete", UNKNOWN),
    ]
    assert observation["phases"][3]["started_at"] == f"{TODAY}T00:00:11.125000Z"
    assert observation["phases"][-1]["ended_at"] is None
    assert observation["wall_time"] == {
        "started_at": f"{YESTERDAY}T23:59:30.250000Z",
        "ended_at": f"{TODAY}T00:00:20.500000Z",
        "seconds": 50.25,
    }


def test_attempts_without_manifests_read_the_window_ledger_safely() -> None:
    """A manifest-less run keeps its latest window snapshot and only safe codes."""
    session = str(uuid4())
    record = _window(session, "gaia", 1, "gaia-model", GAIA_BLOCKS)
    record_prompt_window(record)
    record.validation_notes.extend(REPAIR_NOTES + REJECTION_NOTES)
    record_prompt_window(record)
    inspection = {
        "session": {"session_id": session, "terminal_outcome": None},
        "phases": [{"phase": "retrieval", "recorded_at": f"{TODAY} 00:00:01+00"}],
        "manifests": [],
        "jobs": [],
    }

    observation = observe_turn(inspection, read_at=READ_AT)

    assert observation["terminal_outcome"] is None
    assert observation["ledger_days_read"] == [str(TODAY)]
    assert observation["wall_time"]["seconds"] == UNKNOWN
    (attempt,) = observation["attempts"]
    assert attempt["outcome"] == attempt["provider_outcome"] == UNKNOWN
    assert attempt["window"]["provenance"] == "prompt_window_ledger"
    assert attempt["window"]["input_tokens"] == 16050
    assert attempt["validation"] == {
        "provenance": "prompt_window_ledger",
        "notes": 3,
        "repairs": 2,
        "repair_codes": ["active-extend-expiry", "scene-reset-crossings"],
        "rejections": 1,
        "rejection_codes": ["wire-contract-violation"],
    }
    assert "private" not in json.dumps(observation)
    assert observation["usage_totals"]["provenance"] == UNKNOWN
    assert observation["usage_totals"]["input_tokens"] == UNKNOWN
    assert observation["jobs"] == {"total": 0, "by_queue": {}}


def test_session_without_phases_reads_no_ledger_day() -> None:
    """Without observed transitions nothing names a ledger day to read."""
    session = str(uuid4())
    record = _window(session, "skald_writer", 1, "writer-model", WRITER_BLOCKS)
    inspection = {
        "session": {"session_id": session, "terminal_outcome": "accepted"},
        "phases": [],
        "manifests": [_manifest(record, provider_outcome="accepted")],
        "jobs": [],
    }

    assert ledger_days(inspection) == []
    observation = observe_turn(inspection, read_at=READ_AT)
    assert observation["ledger_days_read"] == []
    assert observation["phases"] == []
    assert observation["wall_time"] == {
        "started_at": UNKNOWN,
        "ended_at": UNKNOWN,
        "seconds": UNKNOWN,
    }
    assert observation["attempts"][0]["usage"]["provenance"] == UNKNOWN


def test_summary_jobs_sharing_an_attempt_number_join_after_midnight() -> None:
    """Episode and season summaries share attempt 1 but not their output cap."""
    session = str(uuid4())
    # The turn completes before UTC midnight; a new_season transition queues an
    # episode and a season summary that the worker runs after it.
    for ts, input_tokens, cap in (
        (f"{TODAY}T00:00:31Z", 41000, 8000),
        (f"{TODAY}T00:00:47Z", 9000, 12000),
    ):
        record_usage_event(
            _event(
                session,
                ts,
                "summaries",
                1,
                "summary-model",
                anthropic=True,
                outcome="accepted",
                input_tokens=input_tokens,
                output_tokens=1500,
                total_tokens=input_tokens + 1500,
                max_output_tokens=cap,
            )
        )
    inspection = {
        "session": {"session_id": session, "terminal_outcome": "accepted"},
        "phases": [
            {"phase": "retrieval", "recorded_at": f"{YESTERDAY} 23:59:40+00"},
            {"phase": "complete", "recorded_at": f"{YESTERDAY} 23:59:58+00"},
        ],
        "manifests": [],
        "jobs": [
            {
                "id": job_id,
                "state": "succeeded",
                "generation_session_id": session,
                "queue": "narrative_summary",
            }
            for job_id in (1, 2)
        ],
    }

    # A read before midnight names only the phases' day; nothing ran yet.
    before = datetime.combine(YESTERDAY, time(23, 59, 59), tzinfo=timezone.utc)
    early = observe_turn(inspection, read_at=before)
    assert early["ledger_days_read"] == [str(YESTERDAY)]
    assert early["attempts"] == []

    observation = observe_turn(inspection, read_at=READ_AT)
    assert observation["ledger_days_read"] == [str(YESTERDAY), str(TODAY)]
    (summaries,) = observation["attempts"]
    assert (summaries["seat"], summaries["attempt"]) == ("summaries", 1)
    assert summaries["model"] == "summary-model"
    usage = summaries["usage"]
    assert usage["events"] == 2
    assert usage["provider"] == "anthropic"
    assert usage["transport"] == "anthropic_messages"
    assert usage["reasoning_effort"] is None
    assert usage["max_output_tokens"] == [8000, 12000]
    assert (usage["input_tokens"], usage["output_tokens"]) == (50000, 3000)
    assert observation["usage_totals"]["input_tokens"] == 50000
    assert json.loads(json.dumps(observation)) == observation
    summary = format_turn_summary(observation)
    assert f"ledger {YESTERDAY} to {TODAY}" in summary.splitlines()[0]
    assert (
        "  usage in 50,000 · cached unknown · cache write unknown · out 3,000 · "
        "reasoning unknown · effort - · max out 8,000/12,000 "
        "[provider_usage_ledger ×2]"
    ) in summary.splitlines()


def test_join_refuses_rows_it_cannot_attribute() -> None:
    """Foreign sessions, unread days, naive clocks, model or provider drift raise."""
    inspection, session, other = _two_pass_turn()
    days = ledger_days(inspection)
    events, windows = read_turn_ledgers(session, days)
    foreign, _ = read_turn_ledgers(other, days)

    with pytest.raises(ValueError, match=f"belongs to run {other}"):
        derive_turn_observation(inspection, events + foreign, windows, ledger_days=days)
    with pytest.raises(ValueError, match="outside the ledger days read"):
        derive_turn_observation(inspection, events, windows, ledger_days=days[1:])
    drifted = [
        (
            event.model_copy(update={"model": "other-model"})
            if event.seat == "skald_writer"
            else event
        )
        for event in events
    ]
    with pytest.raises(ValueError, match="conflicting models"):
        derive_turn_observation(inspection, drifted, windows, ledger_days=days)
    accepted = next(
        event for event in events if (event.seat, event.attempt) == ("gaia", 3)
    )
    rerouted = [*events, accepted.model_copy(update={"provider": "other-provider"})]
    with pytest.raises(ValueError, match="conflicting provider values"):
        derive_turn_observation(inspection, rerouted, windows, ledger_days=days)
    naive = {
        **inspection,
        "phases": [{"phase": "retrieval", "recorded_at": "2026-09-24 21:24:10"}],
    }
    with pytest.raises(ValueError, match="no UTC offset"):
        ledger_days(naive)


def test_summary_renders_one_concise_read_of_the_turn() -> None:
    """The --summary text states freshness, spans, each attempt and totals."""
    inspection, session, _ = _two_pass_turn()
    summary = format_turn_summary(observe_turn(inspection, read_at=READ_AT))
    lines = summary.splitlines()

    assert lines[0] == (
        f"Turn {session} (accepted) · read {TODAY}T12:00:00Z · ledger "
        f"{YESTERDAY} to {TODAY} · schema v1"
    )
    assert lines[1] == (
        "Wall 50.250s: retrieval 8.250s → assembly 2.500s → writer 30.125s → "
        "gaia 8.875s → staging 0.500s → complete"
    )
    writer = lines.index(
        "skald_writer #1 writer-model · outcome accepted · provider accepted"
    )
    assert lines[writer + 1] == (
        "  window 20,777 / 71,000 · headroom 50,223 [attempt_manifest]"
    )
    assert lines[writer + 2] == (
        "  roles voice_source 18,611 · player_language 26 · "
        "canonical_evidence 2,194 · authorial_plan -54"
    )
    assert lines[writer + 3] == (
        "  usage in 20,777 · cached 12,288 · cache write unknown · out 2,100 · "
        "reasoning 800 · effort high · max out 8,000 [provider_usage_ledger ×1]"
    )
    assert (
        "  validation repairs 0 · rejections 1 "
        "(wire-contract-violation) [attempt_manifest]"
    ) in lines
    assert (
        "  validation repairs 2 · rejections 0 "
        "(active-extend-expiry, scene-reset-crossings) [attempt_manifest]"
    ) in lines
    compaction = lines.index(
        "correspondence_compaction #1 compaction-model · outcome unknown · "
        "provider unknown"
    )
    assert lines[compaction + 1 : compaction + 4] == [
        "  window unknown",
        "  usage in 5,000 · cached 0 · cache write unknown · out 300 · "
        "reasoning 0 · effort low · max out 2,000 [provider_usage_ledger ×1]",
        "  validation unknown",
    ]
    timed_out = lines.index("gaia #1 gaia-model · outcome accepted · provider error")
    assert lines[timed_out + 2] == "  usage unknown"
    assert lines[-2] == (
        "Usage in 31,877 · cached 38,288 · cache write unknown · out 4,250 · "
        "reasoning unknown · events 4 · attempts without usage 1"
    )
    assert lines[-1] == (
        "Jobs 4 · correspondence_compaction queued 1 · "
        "experience_render queued 1, succeeded 2"
    )


def test_inspect_turn_accepts_the_summary_flag() -> None:
    """The concise read is an explicit inspect-turn option, off by default."""
    parser = cli.build_parser()
    base = ["inspect-turn", "--slot", "4", "--session", str(uuid4())]

    assert parser.parse_args(base).summary is False
    assert parser.parse_args([*base, "--summary"]).summary is True
