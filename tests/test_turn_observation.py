"""Offline proof of the joined turn observation over real JSONL ledgers.

The usage and prompt-window ledgers are written through the production
recorders into the conftest-isolated usage directory; the inspection dict has
the exact shape ``inspect_turn`` returns from PostgreSQL. The compaction proof
calls the repository's TEST provider over HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import json
from typing import Any, Optional
from uuid import uuid4

import pytest

from nexus import cli
from nexus.agents.lore.seat_blocks import influence_role, influence_token_totals
from nexus.telemetry.attempt_manifest import (
    PROVIDER_JOB_SEATS,
    identity_hash,
    validation_metadata,
)
from nexus.telemetry.prompt_window import PromptWindowRecord
from nexus.telemetry.turn_observation import (
    BACKGROUND_SEAT_QUEUES,
    LEGACY_SESSION_KEYED_CUTOFF,
    SCHEMA_VERSION,
    UNKNOWN,
    derive_turn_observation,
    format_turn_summary,
    ledger_days,
    observe_turn,
    read_turn_ledgers,
)
from nexus.telemetry import usage as usage_ledger
from nexus.telemetry.usage import (
    UsageEvent,
    record_prompt_window,
    record_usage_event,
    summarize_usage,
)
from tests.test_logon_mock_integration import mock_openai_server  # noqa: F401

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


@dataclass
class _LedgerClock:
    """The instant the ledger writers read as now; a test may move it."""

    now: datetime

    @property
    def today(self) -> date:
        return self.now.date()

    @property
    def yesterday(self) -> date:
        return self.today - timedelta(days=1)

    @property
    def read_at(self) -> datetime:
        return datetime.combine(self.today, time(12), tzinfo=timezone.utc)

    @property
    def enqueued(self) -> str:
        """The accepting transaction's job enqueue time (timestamptz::text)."""
        return f"{self.today} 00:00:20.4+00"


@pytest.fixture(autouse=True)
def ledger_clock(monkeypatch: pytest.MonkeyPatch) -> _LedgerClock:
    """Pin the usage and prompt-window writers' clock to one settable instant.

    The instant is read from the writer's own clock when each test starts, and
    every day a test writes or reads derives from it, so a run that straddles
    UTC midnight still writes each record into the day the observation reads.
    """
    clock = _LedgerClock(usage_ledger.datetime.now(timezone.utc))

    class _FrozenLedgerClock(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
            if tz is None:
                return clock.now.astimezone().replace(tzinfo=None)
            return clock.now.astimezone(tz)

    monkeypatch.setattr(usage_ledger, "datetime", _FrozenLedgerClock)
    return clock


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
    estimated: Optional[int] = None,
    reported: Optional[int] = None,
) -> dict[str, Any]:
    """Build one row exactly as ``inspect_turn`` returns it.

    ``estimated`` and ``reported`` add the counts ``record_token_counts``
    merges into ``window_record`` with jsonb ``||``.
    """
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
        "window_record": {
            **record.model_dump(include=included),
            **(
                {}
                if estimated is None and reported is None
                else {
                    "estimated_input_tokens": estimated,
                    "reported_input_tokens": reported,
                }
            ),
        },
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
    run_id: str,
    ts: str,
    seat: str,
    attempt: int,
    model: str,
    *,
    slot: int = 4,
    **fields: Any,
) -> UsageEvent:
    anthropic = fields.pop("anthropic", False)
    return UsageEvent(
        ts=ts,
        provider="anthropic" if anthropic else "openai",
        model=model,
        seat=seat,
        slot=slot,
        run_id=run_id,
        attempt=attempt,
        transport="anthropic_messages" if anthropic else "responses",
        **fields,
    )


def _job(
    session: str,
    queue: str,
    job_id: int,
    state: str,
    created_at: Optional[str],
    updated_at: Optional[str],
) -> dict[str, Any]:
    """Build one job row exactly as ``inspect_turn`` returns it."""
    return {
        "id": job_id,
        "state": state,
        "generation_session_id": session,
        "created_at": created_at,
        "updated_at": updated_at,
        "queue": queue,
    }


def _two_pass_turn(
    ledger_clock: _LedgerClock,
) -> tuple[dict[str, Any], str, str]:
    """Record a writer pass before UTC midnight, Gaia after it, and its jobs."""
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
            f"{ledger_clock.yesterday}T23:59:59.500000Z",
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
            f"{ledger_clock.today}T00:00:05Z",
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
            f"{ledger_clock.today}T00:00:10Z",
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
    # Background workers record under their numeric job id, after acceptance.
    record_usage_event(
        _event(
            "2",
            f"{ledger_clock.today}T00:00:28Z",
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
    record_usage_event(
        _event(
            "7",
            f"{ledger_clock.today}T00:00:45Z",
            "experience_renderer",
            1,
            "experience-model",
            anthropic=True,
            outcome="accepted",
            input_tokens=2400,
            output_tokens=600,
            total_tokens=3000,
            cached_input_tokens=0,
            cache_creation_tokens=1200,
            max_output_tokens=4000,
        )
    )
    # Maturation job 7 shares its number with experience job 7; seats tell.
    for ts, seat, input_tokens, output_tokens in (
        ("00:01:10", "retrograde_seed_candidates", 8000, 1200),
        ("00:01:20", "retrograde_seed_selection", 3000, 200),
        ("00:01:50", "retrograde_expansion", 9000, 2500),
    ):
        record_usage_event(
            _event(
                "7",
                f"{ledger_clock.today}T{ts}Z",
                seat,
                1,
                "maturation-model",
                outcome="accepted",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                cached_input_tokens=0,
                reasoning_tokens=100,
                reasoning_effort="medium",
                max_output_tokens=6000,
            )
        )
    record_usage_event(
        _event(
            "1",
            f"{ledger_clock.today}T00:02:40Z",
            "summaries",
            1,
            "summary-model",
            anthropic=True,
            outcome="accepted",
            input_tokens=41000,
            output_tokens=1500,
            total_tokens=42500,
            cached_input_tokens=0,
            cache_creation_tokens=0,
            max_output_tokens=8000,
        )
    )
    # Not this turn's: another slot's job 7, a job 7 that ran before a slot
    # reset recycled the id, and compaction job 1 (not summary job 1).
    for run_id, ts, seat, slot in (
        ("7", "00:00:46", "experience_renderer", 5),
        ("7", "00:00:05", "experience_renderer", 4),
        ("1", "00:02:00", "correspondence_compaction", 4),
    ):
        record_usage_event(
            _event(
                run_id,
                f"{ledger_clock.today}T{ts}Z",
                seat,
                1,
                "noise-model",
                slot=slot,
                outcome="accepted",
                input_tokens=888888,
                output_tokens=1,
                total_tokens=888889,
            )
        )
    # Another run on a read day, and this run on a day no phase spans.
    record_usage_event(
        _event(
            other,
            f"{ledger_clock.today}T00:00:06Z",
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
            f"{ledger_clock.yesterday - timedelta(days=1)}T12:00:00Z",
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
            {
                "phase": "retrieval",
                "recorded_at": f"{ledger_clock.yesterday} 23:59:30.25+00",
            },
            {
                "phase": "assembly",
                "recorded_at": f"{ledger_clock.yesterday} 23:59:38.5+00",
            },
            {"phase": "writer", "recorded_at": f"{ledger_clock.yesterday} 23:59:41+00"},
            {
                "phase": "gaia",
                "recorded_at": f"{ledger_clock.yesterday} 19:00:11.125-05",
            },
            {"phase": "staging", "recorded_at": f"{ledger_clock.today} 00:00:20+00"},
            {"phase": "complete", "recorded_at": f"{ledger_clock.today} 00:00:20.5+00"},
        ],
        "manifests": [
            _manifest(gaia[0], provider_outcome="error"),
            _manifest(gaia[1], provider_outcome="rejected_validation"),
            # Gaia 3's reported input is the Anthropic normalisation of its
            # usage: 3,100 + 13,000 cache reads + 0 cache writes. Gaia 1 had no
            # response to estimate; Gaia 2's estimate failed and was logged.
            _manifest(
                gaia[2], provider_outcome="accepted", estimated=15980, reported=16100
            ),
            _manifest(
                writer, provider_outcome="accepted", estimated=20412, reported=20777
            ),
        ],
        # The order inspect_turn reads the queues in.
        "jobs": [
            _job(
                session,
                "experience_render",
                7,
                "succeeded",
                ledger_clock.enqueued,
                f"{ledger_clock.today} 00:01:00+00",
            ),
            _job(
                session,
                "experience_render",
                8,
                "queued",
                ledger_clock.enqueued,
                ledger_clock.enqueued,
            ),
            _job(
                session,
                "experience_render",
                9,
                "succeeded",
                ledger_clock.enqueued,
                f"{ledger_clock.today} 00:01:30+00",
            ),
            _job(
                session,
                "retrograde_maturation",
                7,
                "succeeded",
                ledger_clock.enqueued,
                f"{ledger_clock.today} 00:02:00+00",
            ),
            _job(
                session,
                "correspondence_compaction",
                2,
                "succeeded",
                ledger_clock.enqueued,
                f"{ledger_clock.today} 00:00:30+00",
            ),
            _job(
                session,
                "narration",
                3,
                "succeeded",
                ledger_clock.enqueued,
                f"{ledger_clock.today} 00:00:31+00",
            ),
            _job(
                session,
                "narrative_summary",
                1,
                "succeeded",
                ledger_clock.enqueued,
                f"{ledger_clock.today} 00:03:00+00",
            ),
            _job(session, "relationship_milestone", 88, "pending", None, None),
        ],
    }
    return inspection, session, other


def _by_key(observation: dict[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
    return {
        (attempt["seat"], attempt["attempt"]): attempt
        for attempt in observation["attempts"]
    }


def _jobs(observation: dict[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
    return {
        (entry["queue"], entry["id"]): entry for entry in observation["jobs"]["entries"]
    }


def test_observation_joins_each_attempt_with_its_provider_usage(
    ledger_clock: _LedgerClock,
) -> None:
    """Manifest windows, validation codes and ledger tokens join per attempt."""
    inspection, session, _ = _two_pass_turn(ledger_clock)
    observation = observe_turn(inspection, slot=4, read_at=ledger_clock.read_at)

    assert observation["schema_version"] == SCHEMA_VERSION == 2
    assert observation["generation_session"] == session
    assert observation["read_at"] == f"{ledger_clock.today}T12:00:00Z"
    assert observation["ledger_days_read"] == [
        str(ledger_clock.yesterday),
        str(ledger_clock.today),
    ]
    assert observation["terminal_outcome"] == "accepted"
    attempts = _by_key(observation)
    # Sorted, stable keys; the run on an unspanned day never joins, and no
    # background job's work joins the critical path.
    assert list(attempts) == [
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
        "removed_block_tokens": UNKNOWN,
        "removed_tokens_total": UNKNOWN,
        "input_tokens": 20777,
        "estimated_input_tokens": 20412,
        "reported_input_tokens": 20777,
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
        "provider_completed_at": f"{ledger_clock.yesterday}T23:59:59.500000Z",
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

    assert json.loads(json.dumps(observation)) == observation
    assert "private" not in json.dumps(observation)


def test_background_jobs_carry_the_usage_recorded_under_their_job_ids(
    ledger_clock: _LedgerClock,
) -> None:
    """Summary, maturation, experience and compaction spend follow the job rows."""
    inspection, session, _ = _two_pass_turn(ledger_clock)
    observation = observe_turn(inspection, slot=4, read_at=ledger_clock.read_at)
    jobs = _jobs(observation)

    # Sorted by queue and id; every row keeps its identity and UTC times.
    assert list(jobs) == [
        ("correspondence_compaction", 2),
        ("experience_render", 7),
        ("experience_render", 8),
        ("experience_render", 9),
        ("narration", 3),
        ("narrative_summary", 1),
        ("relationship_milestone", 88),
        ("retrograde_maturation", 7),
    ]
    compaction = jobs[("correspondence_compaction", 2)]
    assert {key: compaction[key] for key in compaction if key != "usage"} == {
        "queue": "correspondence_compaction",
        "id": 2,
        "state": "succeeded",
        "terminal": True,
        "created_at": f"{ledger_clock.today}T00:00:20.400000Z",
        "updated_at": f"{ledger_clock.today}T00:00:30Z",
    }
    assert compaction["usage"] == {
        "run_id": "2",
        "ledger_days": [str(ledger_clock.today)],
        "provenance": "provider_usage_ledger",
        "events": 1,
        "seats": ["correspondence_compaction"],
        "model": "compaction-model",
        "provider": "openai",
        "transport": "responses",
        "outcomes": ["accepted"],
        "input_tokens": 5000,
        "output_tokens": 300,
        "cached_input_tokens": 0,
        "cache_creation_tokens": UNKNOWN,
        "reasoning_tokens": 0,
        "reasoning_effort": "low",
        "max_output_tokens": 2000,
    }
    # Only its own slot's calls after its enqueue, not the recycled id's.
    experience = jobs[("experience_render", 7)]["usage"]
    assert experience["events"] == 1
    assert experience["seats"] == ["experience_renderer"]
    assert (experience["provider"], experience["transport"]) == (
        "anthropic",
        "anthropic_messages",
    )
    assert (experience["input_tokens"], experience["output_tokens"]) == (2400, 600)
    assert experience["cache_creation_tokens"] == 1200
    assert experience["reasoning_effort"] is None
    maturation = jobs[("retrograde_maturation", 7)]["usage"]
    assert maturation["run_id"] == "7"
    assert maturation["events"] == 3
    assert maturation["seats"] == sorted(PROVIDER_JOB_SEATS["retrograde_maturation"])
    assert maturation["model"] == "maturation-model"
    assert maturation["outcomes"] == ["accepted"] * 3
    assert (maturation["input_tokens"], maturation["output_tokens"]) == (20000, 3900)
    assert maturation["reasoning_tokens"] == 300
    summary = jobs[("narrative_summary", 1)]["usage"]
    assert (summary["run_id"], summary["seats"]) == ("1", ["summaries"])
    assert (summary["input_tokens"], summary["output_tokens"]) == (41000, 1500)
    assert summary["max_output_tokens"] == 8000
    # A seat names exactly one queue, so a shared job number cannot mix spend.
    seats = [seat for queue in PROVIDER_JOB_SEATS.values() for seat in queue]
    assert len(seats) == len(set(seats))
    assert "noise-model" not in json.dumps(observation)
    assert all(attempt["seat"] not in seats for attempt in observation["attempts"])


def test_usage_totals_split_the_critical_path_from_background_work(
    ledger_clock: _LedgerClock,
) -> None:
    """Critical-path and background sums stay apart; overall adds the two."""
    inspection, _, _ = _two_pass_turn(ledger_clock)
    observation = observe_turn(inspection, slot=4, read_at=ledger_clock.read_at)

    totals = observation["usage_totals"]
    assert totals["critical_path"] == {
        "provenance": "provider_usage_ledger",
        "events": 3,
        "attempts_without_usage": 1,
        "input_tokens": 20777 + 3000 + 3100,
        "output_tokens": 2100 + 900 + 950,
        "cached_input_tokens": 12288 + 13000 + 13000,
        "cache_creation_tokens": UNKNOWN,
        "reasoning_tokens": UNKNOWN,
    }
    assert totals["background"] == {
        "provenance": "provider_usage_ledger",
        "events": 6,
        "jobs": 6,
        "jobs_open": 1,
        "jobs_without_usage": 1,
        "input_tokens": 5000 + 2400 + 20000 + 41000,
        "output_tokens": 300 + 600 + 3900 + 1500,
        "cached_input_tokens": 0,
        # Compaction reported no cache writes; the renderer no reasoning.
        "cache_creation_tokens": UNKNOWN,
        "reasoning_tokens": UNKNOWN,
        "legacy_session_keyed": None,
    }
    assert totals["overall"] == {
        "provenance": "provider_usage_ledger",
        "events": 9,
        "input_tokens": 26877 + 68400,
        "output_tokens": 3950 + 6300,
        "cached_input_tokens": 38288,
        "cache_creation_tokens": UNKNOWN,
        "reasoning_tokens": UNKNOWN,
    }
    assert observation["jobs"]["total"] == 8
    assert observation["jobs"]["by_queue"] == {
        "correspondence_compaction": {"succeeded": 1},
        "experience_render": {"queued": 1, "succeeded": 2},
        "narration": {"succeeded": 1},
        "narrative_summary": {"succeeded": 1},
        "relationship_milestone": {"pending": 1},
        "retrograde_maturation": {"succeeded": 1},
    }


def test_unfound_provider_usage_reads_unknown_and_other_queues_spend_nothing(
    ledger_clock: _LedgerClock,
) -> None:
    """A finished provider-backed job without usage is unknown, never zero."""
    inspection, _, _ = _two_pass_turn(ledger_clock)
    jobs = _jobs(observe_turn(inspection, slot=4, read_at=ledger_clock.read_at))

    finished = jobs[("experience_render", 9)]
    assert finished["terminal"] is True
    assert finished["usage"]["provenance"] == UNKNOWN
    assert finished["usage"]["events"] == 0
    assert finished["usage"]["ledger_days"] == [str(ledger_clock.today)]
    assert all(
        finished["usage"][field] == UNKNOWN
        for field in ("seats", "model", "outcomes", "input_tokens", "output_tokens")
    )
    queued = jobs[("experience_render", 8)]
    assert (queued["state"], queued["terminal"]) == ("queued", False)
    assert queued["usage"]["provenance"] == UNKNOWN
    # Queues that never call a provider carry no spend field at all.
    assert "usage" not in jobs[("narration", 3)]
    milestone = jobs[("relationship_milestone", 88)]
    assert "usage" not in milestone
    assert (milestone["created_at"], milestone["terminal"]) == (None, False)

    # A turn whose jobs never call a provider spent nothing in the background.
    session = str(uuid4())
    quiet = {
        "session": {"session_id": session, "terminal_outcome": "accepted"},
        "phases": [
            {"phase": "retrieval", "recorded_at": f"{ledger_clock.today} 00:00:01+00"}
        ],
        "manifests": [],
        "jobs": [
            _job(
                session,
                "narration",
                4,
                "succeeded",
                ledger_clock.enqueued,
                ledger_clock.enqueued,
            ),
            _job(
                session,
                "narrative_embedding",
                5,
                "queued",
                ledger_clock.enqueued,
                ledger_clock.enqueued,
            ),
        ],
    }
    observation = observe_turn(quiet, slot=4, read_at=ledger_clock.read_at)
    background = observation["usage_totals"]["background"]
    assert background == {
        "provenance": None,
        "events": 0,
        "jobs": 0,
        "jobs_open": 0,
        "jobs_without_usage": 0,
        "legacy_session_keyed": None,
        **dict.fromkeys(
            (
                "input_tokens",
                "output_tokens",
                "cached_input_tokens",
                "cache_creation_tokens",
                "reasoning_tokens",
            ),
            0,
        ),
    }
    assert all("usage" not in entry for entry in observation["jobs"]["entries"])
    assert format_turn_summary(observation).splitlines()[-2] == "Background none"


def test_phase_spans_cross_utc_midnight_and_offsets(ledger_clock: _LedgerClock) -> None:
    """Consecutive transitions become spans; the last one stays open."""
    inspection, _, _ = _two_pass_turn(ledger_clock)
    observation = observe_turn(inspection, slot=4, read_at=ledger_clock.read_at)

    assert [(span["phase"], span["seconds"]) for span in observation["phases"]] == [
        ("retrieval", 8.25),
        ("assembly", 2.5),
        ("writer", 30.125),
        ("gaia", 8.875),
        ("staging", 0.5),
        ("complete", UNKNOWN),
    ]
    assert (
        observation["phases"][3]["started_at"]
        == f"{ledger_clock.today}T00:00:11.125000Z"
    )
    assert observation["phases"][-1]["ended_at"] is None
    assert observation["wall_time"] == {
        "started_at": f"{ledger_clock.yesterday}T23:59:30.250000Z",
        "ended_at": f"{ledger_clock.today}T00:00:20.500000Z",
        "seconds": 50.25,
    }


def test_choice_readiness_is_the_complete_phase_row(
    ledger_clock: _LedgerClock,
) -> None:
    """Readiness is the server's one ``complete`` row, never the wall's end."""
    inspection, session, _ = _two_pass_turn(ledger_clock)

    def observe(**changes: Any) -> dict[str, Any]:
        return observe_turn(
            {**inspection, **changes}, slot=4, read_at=ledger_clock.read_at
        )

    observation = observe()
    assert observation["choice_ready_at"] == f"{ledger_clock.today}T00:00:20.500000Z"
    assert observation["seconds_to_choice_ready"] == 50.25
    # The keys follow wall_time directly.
    keys = list(observation)
    assert keys[keys.index("wall_time") + 1 : keys.index("wall_time") + 3] == [
        "choice_ready_at",
        "seconds_to_choice_ready",
    ]

    # A staged draft later superseded: every phase stays, the session's own
    # fields change. The choices were still ready at the complete row.
    superseded = observe(
        session={
            **inspection["session"],
            "terminal_outcome": "superseded",
            "phase": "staging",
        }
    )
    assert superseded["choice_ready_at"] == f"{ledger_clock.today}T00:00:20.500000Z"
    assert superseded["seconds_to_choice_ready"] == 50.25

    # Failed at Gaia: the wall ends at the Gaia row, yet no choice is ready.
    # The session row's own phase stays "complete" here: it is never read.
    failed = observe(
        session={**inspection["session"], "terminal_outcome": "error"},
        phases=inspection["phases"][:4],
    )
    assert failed["wall_time"]["ended_at"] == f"{ledger_clock.today}T00:00:11.125000Z"
    assert failed["choice_ready_at"] is None
    assert failed["seconds_to_choice_ready"] is None
    assert (
        format_turn_summary(failed)
        .splitlines()[1]
        .endswith("→ gaia · choices not ready")
    )

    # Still generating: phases through the writer, no terminal outcome.
    in_flight = observe(
        session={**inspection["session"], "terminal_outcome": None},
        phases=inspection["phases"][:3],
    )
    assert (in_flight["choice_ready_at"], in_flight["seconds_to_choice_ready"]) == (
        None,
        None,
    )

    # No phase observed (a session from before migration 124): no source.
    unrecorded = observe(phases=[])
    assert unrecorded["choice_ready_at"] == UNKNOWN
    assert unrecorded["seconds_to_choice_ready"] == UNKNOWN
    assert format_turn_summary(unrecorded).splitlines()[1] == (
        "Wall unknown: no phases observed · choices unknown"
    )

    # The complete row is the first observed row: ready, time unknown.
    only = observe(phases=inspection["phases"][-1:])
    assert only["choice_ready_at"] == f"{ledger_clock.today}T00:00:20.500000Z"
    assert only["seconds_to_choice_ready"] == UNKNOWN
    assert format_turn_summary(only).splitlines()[1] == (
        "Wall unknown: complete · choices ready unknown"
    )

    twice = [
        *inspection["phases"],
        {"phase": "complete", "recorded_at": f"{ledger_clock.today} 00:00:21+00"},
    ]
    with pytest.raises(ValueError) as refused:
        observe(phases=twice)
    assert str(refused.value) == (
        f"Generation session {session} records 2 'complete' phases; choice "
        "readiness is ambiguous"
    )


def test_provider_completion_is_each_attempts_latest_usage_event(
    ledger_clock: _LedgerClock,
) -> None:
    """Each attempt's usage names when its latest response arrived."""
    inspection, _, _ = _two_pass_turn(ledger_clock)
    observation = observe_turn(inspection, slot=4, read_at=ledger_clock.read_at)
    attempts = _by_key(observation)

    assert (
        attempts[("skald_writer", 1)]["usage"]["provider_completed_at"]
        == f"{ledger_clock.yesterday}T23:59:59.500000Z"
    )
    assert (
        attempts[("gaia", 3)]["usage"]["provider_completed_at"]
        == f"{ledger_clock.today}T00:00:10Z"
    )
    # Gaia 1 timed out: no response arrived, so no source recorded the time.
    assert attempts[("gaia", 1)]["usage"]["provider_completed_at"] == UNKNOWN
    # Provider completion is not readiness.
    assert observation["choice_ready_at"] == f"{ledger_clock.today}T00:00:20.500000Z"
    # Jobs and totals carry no completion time.
    assert all(
        "provider_completed_at" not in entry["usage"]
        for entry in observation["jobs"]["entries"]
        if "usage" in entry
    )
    assert all(
        "provider_completed_at" not in totals
        for totals in observation["usage_totals"].values()
    )

    # A seat without a manifest numbers two calls attempt 1: the later wins.
    session = str(uuid4())
    for ts in ("00:00:03.25", "00:00:09.75"):
        record_usage_event(
            _event(
                session,
                f"{ledger_clock.today}T{ts}Z",
                "skald",
                1,
                "skald-model",
                outcome="accepted",
                input_tokens=100,
                output_tokens=10,
                total_tokens=110,
            )
        )
    manifestless = {
        "session": {"session_id": session, "terminal_outcome": "accepted"},
        "phases": [
            {"phase": "retrieval", "recorded_at": f"{ledger_clock.today} 00:00:01+00"},
            {"phase": "complete", "recorded_at": f"{ledger_clock.today} 00:00:12+00"},
        ],
        "manifests": [],
        "jobs": [],
    }
    (attempt,) = observe_turn(manifestless, slot=4, read_at=ledger_clock.read_at)[
        "attempts"
    ]
    assert attempt["usage"]["events"] == 2
    assert (
        attempt["usage"]["provider_completed_at"]
        == f"{ledger_clock.today}T00:00:09.750000Z"
    )


def test_window_projects_estimated_and_reported_input(
    ledger_clock: _LedgerClock,
) -> None:
    """The manifest's estimate and normalised reported input reach each window."""
    inspection, _, _ = _two_pass_turn(ledger_clock)
    attempts = _by_key(observe_turn(inspection, slot=4, read_at=ledger_clock.read_at))

    def counts(key: tuple[str, int]) -> tuple[Any, Any]:
        window = attempts[key]["window"]
        return window["estimated_input_tokens"], window["reported_input_tokens"]

    assert counts(("skald_writer", 1)) == (20412, 20777)
    assert counts(("gaia", 3)) == (15980, 16100)
    # The ledger keeps Anthropic's raw input; the window has the normalised one.
    assert attempts[("gaia", 3)]["usage"]["input_tokens"] == 3100
    # No estimate was attempted for Gaia 1; Gaia 2's estimate failed.
    assert counts(("gaia", 1)) == (UNKNOWN, UNKNOWN)
    assert counts(("gaia", 2)) == (UNKNOWN, UNKNOWN)

    # A window-ledger record never carries either count.
    ledger_only = _by_key(
        observe_turn(
            {**inspection, "manifests": []}, slot=4, read_at=ledger_clock.read_at
        )
    )
    writer = ledger_only[("skald_writer", 1)]["window"]
    assert writer["provenance"] == "prompt_window_ledger"
    assert (writer["estimated_input_tokens"], writer["reported_input_tokens"]) == (
        UNKNOWN,
        UNKNOWN,
    )


def test_phases_recorded_out_of_order_refuse_the_join(
    ledger_clock: _LedgerClock,
) -> None:
    """A later phase recorded before its predecessor never yields negative time."""
    inspection, session, _ = _two_pass_turn(ledger_clock)
    phases = [dict(row) for row in inspection["phases"]]
    # Staging stamped a second before the Gaia transition it follows.
    phases[4]["recorded_at"] = f"{ledger_clock.today} 00:00:10.125+00"
    reordered = {**inspection, "phases": phases}

    with pytest.raises(
        ValueError,
        match=(
            f"Phase staging of {session} was recorded at "
            f"{ledger_clock.today}T00:00:10.125000Z, before the preceding "
            f"phase gaia at {ledger_clock.today}T00:00:11.125000Z"
        ),
    ):
        observe_turn(reordered, slot=4, read_at=ledger_clock.read_at)
    # Equal stamps are a zero-length span, not a disorder.
    phases[4]["recorded_at"] = f"{ledger_clock.yesterday} 19:00:11.125-05"
    spans = observe_turn(
        {**inspection, "phases": phases}, slot=4, read_at=ledger_clock.read_at
    )["phases"]
    assert spans[3]["seconds"] == 0.0


def test_attempts_without_manifests_read_the_window_ledger_safely(
    ledger_clock: _LedgerClock,
) -> None:
    """A manifest-less run keeps its latest window snapshot and only safe codes."""
    session = str(uuid4())
    record = _window(session, "gaia", 1, "gaia-model", GAIA_BLOCKS)
    record_prompt_window(record)
    record.validation_notes.extend(REPAIR_NOTES + REJECTION_NOTES)
    record_prompt_window(record)
    inspection = {
        "session": {"session_id": session, "terminal_outcome": None},
        "phases": [
            {"phase": "retrieval", "recorded_at": f"{ledger_clock.today} 00:00:01+00"}
        ],
        "manifests": [],
        "jobs": [],
    }

    observation = observe_turn(inspection, slot=4, read_at=ledger_clock.read_at)

    assert observation["terminal_outcome"] is None
    assert observation["ledger_days_read"] == [str(ledger_clock.today)]
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
    critical_path = observation["usage_totals"]["critical_path"]
    assert critical_path["provenance"] == UNKNOWN
    assert critical_path["input_tokens"] == UNKNOWN
    assert observation["usage_totals"]["overall"]["input_tokens"] == UNKNOWN
    assert observation["jobs"] == {"total": 0, "by_queue": {}, "entries": []}


def test_a_turn_straddling_utc_midnight_writes_and_joins_both_days(
    ledger_clock: _LedgerClock,
) -> None:
    """The writer records before UTC midnight, Gaia after; both join the turn."""
    session = str(uuid4())
    ledger_clock.now = datetime.combine(
        ledger_clock.today, time(23, 59, 59, 900000), tzinfo=timezone.utc
    )
    first_day = ledger_clock.today
    writer = _window(session, "skald_writer", 1, "writer-model", WRITER_BLOCKS)
    record_prompt_window(writer)
    # The event takes its timestamp from the writer's clock, as in production.
    record_usage_event(
        UsageEvent(
            provider="openai",
            model="writer-model",
            seat="skald_writer",
            slot=4,
            run_id=session,
            attempt=1,
            outcome="accepted",
            transport="responses",
            input_tokens=20777,
            output_tokens=2100,
            total_tokens=22877,
        )
    )

    ledger_clock.now += timedelta(milliseconds=200)
    second_day = ledger_clock.today
    assert second_day == first_day + timedelta(days=1)
    gaia = _window(session, "gaia", 1, "gaia-model", GAIA_BLOCKS)
    record_prompt_window(gaia)
    record_usage_event(
        UsageEvent(
            provider="openai",
            model="gaia-model",
            seat="gaia",
            slot=4,
            run_id=session,
            attempt=1,
            outcome="accepted",
            transport="responses",
            input_tokens=16050,
            output_tokens=900,
            total_tokens=16950,
        )
    )

    # Each record sits in the ledger of the day it was written.
    for day, seat in ((first_day, "skald_writer"), (second_day, "gaia")):
        windows = usage_ledger.read_prompt_windows(session, str(day))
        assert [record.seat for record in windows] == [seat]
        events = summarize_usage(day=str(day), run_id=session)["events"]
        assert [event["seat"] for event in events] == [seat]
        assert events[0]["quota_day"] == str(day)

    inspection = {
        "session": {"session_id": session, "terminal_outcome": "accepted"},
        "phases": [
            {"phase": "writer", "recorded_at": f"{first_day} 23:59:59.85+00"},
            {"phase": "gaia", "recorded_at": f"{second_day} 00:00:00.05+00"},
            {"phase": "complete", "recorded_at": f"{second_day} 00:00:00.2+00"},
        ],
        "manifests": [],
        "jobs": [],
    }
    observation = observe_turn(inspection, slot=4, read_at=ledger_clock.now)

    assert observation["ledger_days_read"] == [str(first_day), str(second_day)]
    attempts = _by_key(observation)
    assert list(attempts) == [("gaia", 1), ("skald_writer", 1)]
    for key, input_tokens in ((("gaia", 1), 16050), (("skald_writer", 1), 20777)):
        attempt = attempts[key]
        assert attempt["window"]["provenance"] == "prompt_window_ledger"
        assert attempt["window"]["input_tokens"] == input_tokens
        assert attempt["usage"]["events"] == 1
        assert attempt["usage"]["input_tokens"] == input_tokens


def test_jobs_read_their_own_ledger_days_without_turn_phases(
    ledger_clock: _LedgerClock,
) -> None:
    """Summary jobs that finish after UTC midnight are read from their own days."""
    session = str(uuid4())
    record = _window(session, "skald_writer", 1, "writer-model", WRITER_BLOCKS)
    enqueued = f"{ledger_clock.yesterday} 23:59:58+00"
    # A new_season transition queues an episode and a season summary that the
    # worker runs after midnight; each records under its own job id.
    for job_id, ts, input_tokens, cap in (
        (1, f"{ledger_clock.today}T00:00:31Z", 41000, 8000),
        (2, f"{ledger_clock.today}T00:00:47Z", 9000, 12000),
    ):
        record_usage_event(
            _event(
                str(job_id),
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
        "phases": [],
        "manifests": [_manifest(record, provider_outcome="accepted")],
        "jobs": [
            _job(
                session,
                "narrative_summary",
                1,
                "succeeded",
                enqueued,
                f"{ledger_clock.today} 00:00:32+00",
            ),
            _job(
                session,
                "narrative_summary",
                2,
                "succeeded",
                enqueued,
                f"{ledger_clock.today} 00:00:48+00",
            ),
        ],
    }

    assert ledger_days(inspection) == []
    observation = observe_turn(inspection, slot=4, read_at=ledger_clock.read_at)
    # No phase names a day for the turn; the jobs' own days are still read.
    assert observation["ledger_days_read"] == [
        str(ledger_clock.yesterday),
        str(ledger_clock.today),
    ]
    assert observation["phases"] == []
    assert observation["wall_time"] == {
        "started_at": UNKNOWN,
        "ended_at": UNKNOWN,
        "seconds": UNKNOWN,
    }
    assert observation["attempts"][0]["usage"]["provenance"] == UNKNOWN
    jobs = _jobs(observation)
    episode = jobs[("narrative_summary", 1)]["usage"]
    season = jobs[("narrative_summary", 2)]["usage"]
    assert (
        episode["ledger_days"]
        == season["ledger_days"]
        == [
            str(ledger_clock.yesterday),
            str(ledger_clock.today),
        ]
    )
    assert (episode["input_tokens"], episode["max_output_tokens"]) == (41000, 8000)
    assert (season["input_tokens"], season["max_output_tokens"]) == (9000, 12000)
    assert observation["usage_totals"]["background"]["input_tokens"] == 50000
    assert observation["usage_totals"]["overall"]["input_tokens"] == UNKNOWN
    assert json.loads(json.dumps(observation)) == observation
    summary = format_turn_summary(observation).splitlines()
    assert f"ledger {ledger_clock.yesterday} to {ledger_clock.today}" in summary[0]
    assert summary[
        summary.index("narrative_summary #2 summary-model · succeeded") + 1
    ] == (
        "  usage in 9,000 · cached unknown · cache write unknown · out 1,500 · "
        "reasoning unknown · effort - · max out 12,000 [provider_usage_ledger ×1]"
    )


def test_session_keyed_background_usage_joins_as_legacy(
    ledger_clock: _LedgerClock,
) -> None:
    """Summary spend recorded under the session before #802 stays visible."""
    ledger_clock.now = LEGACY_SESSION_KEYED_CUTOFF - timedelta(hours=12)
    session = str(uuid4())
    writer = _window(session, "skald_writer", 1, "writer-model", WRITER_BLOCKS)
    record_prompt_window(writer)
    record_usage_event(
        _event(
            session,
            f"{ledger_clock.today}T00:00:12Z",
            "skald_writer",
            1,
            "writer-model",
            outcome="accepted",
            input_tokens=20777,
            output_tokens=2100,
            total_tokens=22877,
            cached_input_tokens=12288,
            reasoning_tokens=800,
        )
    )
    # The old convention: the episode and season summaries of a new_season
    # turn both recorded (summaries, 1) under the generation session.
    for ts, input_tokens, cap in (
        (f"{ledger_clock.today}T00:00:31Z", 41000, 8000),
        (f"{ledger_clock.today}T00:00:47Z", 9000, 12000),
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
                cached_input_tokens=0,
                cache_creation_tokens=0,
                max_output_tokens=cap,
            )
        )
    inspection = {
        "session": {"session_id": session, "terminal_outcome": "accepted"},
        "phases": [
            {"phase": "writer", "recorded_at": f"{ledger_clock.today} 00:00:01+00"},
            {"phase": "complete", "recorded_at": f"{ledger_clock.today} 00:00:20+00"},
        ],
        "manifests": [_manifest(writer, provider_outcome="accepted")],
        "jobs": [
            _job(
                session,
                "narrative_summary",
                job_id,
                "succeeded",
                ledger_clock.enqueued,
                f"{ledger_clock.today} 00:00:48+00",
            )
            for job_id in (1, 2)
        ],
    }

    observation = observe_turn(inspection, slot=4, read_at=ledger_clock.read_at)

    # Kept off the critical path, and never guessed onto a job.
    assert [(row["seat"], row["attempt"]) for row in observation["attempts"]] == [
        ("skald_writer", 1)
    ]
    totals = observation["usage_totals"]
    assert totals["critical_path"]["events"] == 1
    assert totals["critical_path"]["input_tokens"] == 20777
    jobs = _jobs(observation)
    assert all(
        jobs[("narrative_summary", job_id)]["usage"]["provenance"] == UNKNOWN
        for job_id in (1, 2)
    )
    legacy = {
        "recorded_before": (
            "Recorded under the generation session before background workers "
            "recorded under their job id (#802); not attributable to one job."
        ),
        "events": 2,
        "seats": ["summaries"],
        "ledger_days": [str(ledger_clock.today)],
        "input_tokens": 50000,
        "output_tokens": 3000,
        "cached_input_tokens": 0,
        "cache_creation_tokens": 0,
        "reasoning_tokens": UNKNOWN,
    }
    assert totals["background"] == {
        "provenance": "provider_usage_ledger",
        "events": 2,
        "input_tokens": 50000,
        "output_tokens": 3000,
        "cached_input_tokens": 0,
        "cache_creation_tokens": 0,
        "reasoning_tokens": UNKNOWN,
        "jobs": 2,
        "jobs_open": 0,
        "jobs_without_usage": 2,
        "legacy_session_keyed": legacy,
    }
    assert totals["overall"]["events"] == 3
    assert totals["overall"]["input_tokens"] == 20777 + 50000
    assert totals["overall"]["output_tokens"] == 2100 + 3000
    assert json.loads(json.dumps(observation)) == observation
    lines = format_turn_summary(observation).splitlines()
    legacy_line = lines.index(
        "Background legacy (session-keyed) in 50,000 · cached 0 · cache write 0 "
        "· out 3,000 · reasoning unknown · events 2 · seats summaries"
    )
    assert lines[legacy_line + 1] == (
        "Background in 50,000 · cached 0 · cache write 0 · out 3,000 · reasoning "
        "unknown · events 2 · jobs 2 · open 0 · without usage 2"
    )
    # A turn without legacy events renders no legacy line.
    fresh, _, _ = _two_pass_turn(ledger_clock)
    assert "legacy" not in format_turn_summary(
        observe_turn(fresh, slot=4, read_at=ledger_clock.read_at)
    )


@pytest.mark.parametrize("seat", sorted(BACKGROUND_SEAT_QUEUES))
@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-09-26T23:41:17Z",
        "2026-09-26T23:41:17.000001Z",
        "2026-09-26T19:41:17-04:00",
    ],
)
def test_session_keyed_background_usage_at_or_after_cutoff_raises(
    ledger_clock: _LedgerClock, seat: str, timestamp: str
) -> None:
    """Every background seat respects the exact, offset-aware convention boundary."""
    ledger_clock.now = LEGACY_SESSION_KEYED_CUTOFF
    session = str(uuid4())
    inspection = {
        "session": {"session_id": session, "terminal_outcome": "accepted"},
        "phases": [
            {"phase": "writer", "recorded_at": "2026-09-26 23:39:17+00"},
            {"phase": "complete", "recorded_at": "2026-09-26 23:40:17+00"},
        ],
        "manifests": [],
        "jobs": [],
    }
    record_usage_event(
        _event(
            session,
            "2026-09-26T23:41:16.999999Z",
            seat,
            1,
            "background-model",
            outcome="accepted",
            input_tokens=100,
            output_tokens=10,
            total_tokens=110,
        )
    )
    read_at = LEGACY_SESSION_KEYED_CUTOFF + timedelta(minutes=1)
    observation = observe_turn(inspection, slot=4, read_at=read_at)
    assert observation["attempts"] == []
    legacy = observation["usage_totals"]["background"]["legacy_session_keyed"]
    assert legacy["events"] == 1
    assert legacy["seats"] == [seat]
    assert legacy["input_tokens"] == 100
    assert legacy["output_tokens"] == 10
    assert observation["jobs"]["entries"] == []

    record_usage_event(
        _event(
            session,
            timestamp,
            seat,
            1,
            "background-model",
            outcome="accepted",
            input_tokens=100,
            output_tokens=10,
            total_tokens=110,
        )
    )
    with pytest.raises(ValueError) as error:
        observe_turn(inspection, slot=4, read_at=read_at)
    assert str(error.value) == (
        f"Background seat {seat} recorded usage under session run {session} at "
        f"{timestamp}, on or after 2026-09-26T23:41:17Z, when background workers "
        "began recording under their job id (#802)"
    )


def test_join_refuses_rows_it_cannot_attribute(ledger_clock: _LedgerClock) -> None:
    """Foreign runs, unread days, naive clocks, drift and stray seats raise."""
    from nexus.telemetry.turn_observation import job_ledger_days, read_job_ledgers

    ledger_clock.now = LEGACY_SESSION_KEYED_CUTOFF + timedelta(days=1)
    inspection, session, other = _two_pass_turn(ledger_clock)
    days = ledger_days(inspection)
    events, windows = read_turn_ledgers(session, days)
    foreign, _ = read_turn_ledgers(other, days)
    job_events = read_job_ledgers(
        job_ledger_days(inspection, read_at=ledger_clock.read_at)
    )

    def derive(usage: list[UsageEvent], background: list[UsageEvent]) -> None:
        derive_turn_observation(
            inspection,
            usage,
            windows,
            ledger_days=days,
            job_events=background,
            slot=4,
            read_at=ledger_clock.read_at,
        )

    derive(events, job_events)
    with pytest.raises(ValueError, match=f"belongs to run {other}"):
        derive(events + foreign, job_events)
    with pytest.raises(ValueError, match="outside the ledger days read"):
        derive_turn_observation(
            inspection, events, windows, ledger_days=days[1:], slot=4
        )
    drifted = [
        (
            event.model_copy(update={"model": "other-model"})
            if event.seat == "skald_writer"
            else event
        )
        for event in events
    ]
    with pytest.raises(ValueError, match="conflicting models"):
        derive(drifted, job_events)
    accepted = next(
        event for event in events if (event.seat, event.attempt) == ("gaia", 3)
    )
    rerouted = [*events, accepted.model_copy(update={"provider": "other-provider"})]
    with pytest.raises(ValueError, match="conflicting provider values"):
        derive(rerouted, job_events)
    # Post-cutoff background work under the session's run id is a worker defect.
    legacy = accepted.model_copy(update={"seat": "summaries", "attempt": 1})
    with pytest.raises(ValueError, match="recorded usage under session run"):
        derive([*events, legacy], job_events)
    # A call under a listed job's id and slot must name a seat of some queue.
    stray = job_events[0].model_copy(update={"seat": "skald_writer"})
    with pytest.raises(ValueError, match="seat skald_writer under job run"):
        derive(events, [*job_events, stray])
    with pytest.raises(ValueError, match="not a provider-backed job"):
        derive(events, [*job_events, foreign[0]])
    unread = job_events[0].model_copy(
        update={"ts": f"{ledger_clock.yesterday - timedelta(days=1)}T12:00:00Z"}
    )
    with pytest.raises(ValueError, match="outside the job ledger days read"):
        derive(events, [*job_events, UsageEvent.model_validate(unread.model_dump())])
    naive = {
        **inspection,
        "phases": [{"phase": "retrieval", "recorded_at": "2026-09-24 21:24:10"}],
    }
    with pytest.raises(ValueError, match="no UTC offset"):
        ledger_days(naive)


def test_summary_renders_one_concise_read_of_the_turn(
    ledger_clock: _LedgerClock,
) -> None:
    """The --summary text states freshness, spans, attempts, jobs and totals."""
    inspection, session, _ = _two_pass_turn(ledger_clock)
    summary = format_turn_summary(
        observe_turn(inspection, slot=4, read_at=ledger_clock.read_at)
    )
    lines = summary.splitlines()

    assert lines[0] == (
        f"Turn {session} (accepted) · read {ledger_clock.today}T12:00:00Z · ledger "
        f"{ledger_clock.yesterday} to {ledger_clock.today} · schema v2"
    )
    assert lines[1] == (
        "Wall 50.250s: retrieval 8.250s → assembly 2.500s → writer 30.125s → "
        "gaia 8.875s → staging 0.500s → complete · choices ready 50.250s"
    )
    writer = lines.index(
        "skald_writer #1 writer-model · outcome accepted · provider accepted"
    )
    assert lines[writer + 1] == (
        "  window 20,777 / 71,000 · headroom 50,223 · estimated 20,412 · "
        "reported 20,777 [attempt_manifest]"
    )
    assert lines[writer + 2] == (
        "  roles voice_source 18,611 · player_language 26 · "
        "canonical_evidence 2,194 · authorial_plan -54"
    )
    assert lines[writer + 3] == "  removed unknown"
    assert lines[writer + 4] == (
        "  usage in 20,777 · cached 12,288 · cache write unknown · out 2,100 · "
        "reasoning 800 · effort high · max out 8,000 · completed "
        f"{ledger_clock.yesterday}T23:59:59.500000Z [provider_usage_ledger ×1]"
    )
    assert (
        "  validation repairs 0 · rejections 1 "
        "(wire-contract-violation) [attempt_manifest]"
    ) in lines
    assert (
        "  validation repairs 2 · rejections 0 "
        "(active-extend-expiry, scene-reset-crossings) [attempt_manifest]"
    ) in lines
    timed_out = lines.index("gaia #1 gaia-model · outcome accepted · provider error")
    assert lines[timed_out + 3] == "  usage unknown"
    assert lines[writer + 6 :] == [
        "Critical path in 26,877 · cached 38,288 · cache write unknown · out "
        "3,950 · reasoning unknown · events 3 · attempts without usage 1",
        "correspondence_compaction #2 compaction-model · succeeded",
        "  usage in 5,000 · cached 0 · cache write unknown · out 300 · reasoning 0 "
        "· effort low · max out 2,000 [provider_usage_ledger ×1]",
        "experience_render #7 experience-model · succeeded",
        "  usage in 2,400 · cached 0 · cache write 1,200 · out 600 · reasoning "
        "unknown · effort - · max out 4,000 [provider_usage_ledger ×1]",
        "experience_render #8 · queued",
        "  usage unknown",
        "experience_render #9 · succeeded",
        "  usage unknown",
        "narrative_summary #1 summary-model · succeeded",
        "  usage in 41,000 · cached 0 · cache write 0 · out 1,500 · reasoning "
        "unknown · effort - · max out 8,000 [provider_usage_ledger ×1]",
        "retrograde_maturation #7 maturation-model · succeeded",
        "  usage in 20,000 · cached 0 · cache write unknown · out 3,900 · "
        "reasoning 300 · effort medium · max out 6,000 [provider_usage_ledger ×3]",
        "Background in 68,400 · cached 0 · cache write unknown · out 6,300 · "
        "reasoning unknown · events 6 · jobs 6 · open 1 · without usage 1",
        "Overall in 95,277 · cached 38,288 · cache write unknown · out 10,250 · "
        "reasoning unknown · events 9",
        "Jobs 8 · correspondence_compaction succeeded 1 · experience_render "
        "queued 1, succeeded 2 · narration succeeded 1 · narrative_summary "
        "succeeded 1 · relationship_milestone pending 1 · retrograde_maturation "
        "succeeded 1",
    ]


def test_compaction_records_usage_under_its_job_id(
    request: pytest.FixtureRequest,
) -> None:
    """A compaction call through the TEST provider joins its job, not the turn."""
    from nexus.jobs.compaction import compaction_usage
    from nexus.memory.correspondence import (
        CorrespondenceDigestWire,
        load_compaction_system_prompt,
    )
    from scripts.api_openai import OpenAIProvider

    session = str(uuid4())
    # The seat comes from the job's usage identity, as drain_compaction sets it.
    provider = OpenAIProvider(
        model="TEST",
        api_key="test-key",
        base_url=request.getfixturevalue("mock_openai_server"),
        system_prompt=load_compaction_system_prompt(max_digest_tokens=2000),
        usage_provider_name="test",
        structured_output_retries=0,
    )
    # Read the day from the writer's clock, which stamps the usage event.
    days = {usage_ledger.datetime.now(timezone.utc).date().isoformat()}
    try:
        with compaction_usage(12, slot=4):
            digest, _ = provider.get_structured_completion(
                "Aging exchanges.", CorrespondenceDigestWire
            )
    finally:
        provider.client.close()
    assert isinstance(digest, CorrespondenceDigestWire) and digest.digest

    days.add(usage_ledger.datetime.now(timezone.utc).date().isoformat())
    (event,) = [
        event for day in sorted(days) for event in summarize_usage(day=day)["events"]
    ]
    assert (event["seat"], event["run_id"], event["slot"]) == (
        "correspondence_compaction",
        "12",
        4,
    )
    assert event["seat"] in PROVIDER_JOB_SEATS["correspondence_compaction"]
    assert (event["provider"], event["model"]) == ("test", "TEST")
    recorded_at = datetime.fromisoformat(event["ts"])
    enqueued = (recorded_at - timedelta(seconds=5)).isoformat()
    finished = (recorded_at + timedelta(seconds=1)).isoformat()
    inspection = {
        "session": {"session_id": session, "terminal_outcome": "accepted"},
        "phases": [{"phase": "complete", "recorded_at": enqueued}],
        "manifests": [],
        "jobs": [
            _job(
                session,
                "correspondence_compaction",
                12,
                "succeeded",
                enqueued,
                finished,
            )
        ],
    }
    observation = observe_turn(
        inspection, slot=4, read_at=recorded_at + timedelta(seconds=2)
    )
    assert observation["attempts"] == []
    (job,) = observation["jobs"]["entries"]
    usage = job["usage"]
    assert (usage["provenance"], usage["events"]) == ("provider_usage_ledger", 1)
    # The TEST Responses mock reports exact counts and no cache details.
    assert (usage["input_tokens"], usage["output_tokens"]) == (1000, 800)
    assert observation["usage_totals"]["background"]["input_tokens"] == 1000
    assert "correspondence_compaction #12 TEST · succeeded" in format_turn_summary(
        observation
    )


def test_inspect_turn_accepts_the_summary_flag() -> None:
    """The concise read is an explicit inspect-turn option, off by default."""
    parser = cli.build_parser()
    base = ["inspect-turn", "--slot", "4", "--session", str(uuid4())]

    assert parser.parse_args(base).summary is False
    assert parser.parse_args([*base, "--summary"]).summary is True


@pytest.mark.parametrize(
    "source", ["manifest", "ledger", "conflicting", "legacy", "zero", "none"]
)
def test_removed_tokens_follow_manifest_precedence_and_preserve_unknown(
    ledger_clock: _LedgerClock,
    source: str,
) -> None:
    """The authoritative window distinguishes missing accounting from recorded zero."""
    from nexus.agents.lore.seat_blocks import TRIMMABLE_BLOCKS

    session = str(uuid4())
    record = _window(session, "skald_writer", 1, "TEST", WRITER_BLOCKS)
    removed: dict[str, int] = dict(zip(TRIMMABLE_BLOCKS, (7, 11, 13)))
    if source == "zero":
        removed = {str(kind): 0 for kind in TRIMMABLE_BLOCKS}
    record.removed_block_tokens = removed if source != "legacy" else {}
    if source != "none":
        record_prompt_window(record)
    manifests = []
    if source in {"manifest", "conflicting", "legacy", "zero"}:
        manifest = _manifest(record, provider_outcome="accepted")
        if source in {"manifest", "zero"}:
            manifest["window_record"]["removed_block_tokens"] = removed
        manifests.append(manifest)
    if source == "none":
        record_usage_event(
            _event(
                session,
                ledger_clock.now.isoformat(),
                "skald_writer",
                1,
                "TEST",
                input_tokens=100,
                outcome="accepted",
            )
        )
    inspection = {
        "session": {"session_id": session, "terminal_outcome": "accepted"},
        "phases": [{"phase": "complete", "recorded_at": ledger_clock.now.isoformat()}],
        "manifests": manifests,
        "jobs": [],
    }
    observation = observe_turn(inspection, slot=4, read_at=ledger_clock.read_at)
    window = observation["attempts"][0]["window"]
    known = source in {"manifest", "ledger", "zero"}
    assert window["removed_block_tokens"] == (removed if known else UNKNOWN)
    assert window["removed_tokens_total"] == (
        sum(removed.values()) if known else UNKNOWN
    )
    if source != "none":
        assert window["block_tokens_total"] == window["input_tokens"]
    assert json.loads(json.dumps(observation))["attempts"][0]["window"] == window
    summary = format_turn_summary(observation)
    assert (
        f"removed {sum(removed.values())}" if known else "removed unknown"
    ) in summary
    if known:
        assert all(f"{kind} {tokens}" in summary for kind, tokens in removed.items())
