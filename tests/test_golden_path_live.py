"""Golden-Path Release Gate (M9): one live end-to-end run proves the MVP.

DESTRUCTIVE, EXPENSIVE, SLOW. This is the backend v1.0 release gate: it drops
and recreates the save_05 database (slot 5, the designated dev slot), boots
the real API server as a subprocess, runs the wizard -> narrative transition
with a real Retrograde cold start, then plays live turns through the
production HTTP surface -- every model call is a real frontier call.

Reduced-path note: the wizard CHAT phases are staged from a canned cache
captured from a full manual CLI wizard run (the conversational wizard is
covered by its own live suites); everything from the transition onward --
trait-input derivation, Retrograde generation/persistence/embedding, the
bootstrap, and all play turns -- runs live. The companion full ~10-turn
manual run is documented on the M9 PR.

Stages (ordered; each test asserts one category against the shared run):
  1. Retrograde cold start fired at the transition (world_events
     source='retrograde', embedded per-event summary chunks, derived trait
     inputs, trait-compiler stubs, decision-8 caps, no duplicate entities).
  2. Live play: scripted turns including one freeform directive, one
     entity-eliciting input, and one explicit time skip (sunhelm needs accrue
     on world time; a fresh world's Orrery wakes through them), then
     adaptive eventful turns until promotion + bleed-offer + maturation have
     all occurred (bounded by GOLDEN_PATH_MAX_TURNS).
  3. Chunk persistence + incubator lifecycle (one pending chunk, committed
     chunks finalized).
  4. Embedding lifecycle: every locked chunk embedded except the Retrograde
     prologue anchor (intentionally unembedded) and the newest committed
     chunk (the undo buffer).
  5. MEMNON retrieves Retrograde-sourced history for an event-specific query.
  6. Orrery promotions occurred, narrations landed, and at least one
     narrated off-screen event was offered to (and surfaced for) a
     subsequent chunk's generation (Bleed).
  7. Runtime maturation fired for a Skald-declared entity; its generated
     history persisted, embedded, and became retrievable.
  8. Server log scan: no tracebacks, no ERROR lines.

Gating: NEXUS_RUN_LIVE_LLM=1, NEXUS_RUN_POSTGRES=1, and the destructive
opt-in NEXUS_GOLDEN_PATH_E2E=1.

Cost and wall clock: measured green run (2026-06-11, gpt-5.5 +
@anthropic.default narration): 20 frontier calls, 14m30s end to end.
Budget ~20-35 calls / 15-30 minutes; the adaptive tail adds turns only
when promotion/bleed/maturation lag. Budget accordingly before CI.

Cleanup: the API server subprocess is terminated on teardown. Slot 5 is
deliberately left with the run's data for post-mortem inspection; rerun
``python scripts/new_story_setup.py --slot 5 --force`` to reset it.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2  # type: ignore[import-untyped]
import pytest
import requests
from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]

SLOT = 5
DBNAME = "save_05"
DSN = f"postgresql://pythagor@localhost:5432/{DBNAME}"
# NARRATIVE_API_PORT lets the gate run beside a live dev stack on 8002
# (agent worktrees); the spawned server subprocess inherits it via env.
API = f"http://localhost:{os.environ.get('NARRATIVE_API_PORT', '8002')}"
FIXTURE = Path(__file__).parent / "fixtures" / "golden_path_wizard_cache.json"

# Hard ceiling on play turns; the run goes adaptive after the scripted
# opening if promotion/bleed/maturation have not all occurred yet.
GOLDEN_PATH_MAX_TURNS = 10
SCRIPTED_OPENING: List[Dict[str, Any]] = [
    {"choice": 1},
    {
        "user_text": (
            "Before anything else, I find the nearest bystander who saw what "
            "happened, ask their name, who they work for, and what they saw "
            "tonight - everyone in this city has a story, and I want theirs."
        )
    },
    {"choice": 1},
    {
        "user_text": (
            "I disengage and go home the long way. I check on my people, hide "
            "what I am carrying, and sleep until the next evening tide. I want "
            "a full day to pass in the world before I act again - everyone in "
            "this story needs food, water, and rest, and so do I."
        )
    },
]
ADAPTIVE_INPUT = {"choice": 1}

GENERATION_POLL_SECONDS = 360
TRANSITION_TIMEOUT_SECONDS = 900

pytestmark = [
    pytest.mark.live,
    pytest.mark.live_llm,
    pytest.mark.requires_postgres,
    pytest.mark.skipif(
        os.environ.get("NEXUS_GOLDEN_PATH_E2E") != "1",
        reason=(
            "Set NEXUS_GOLDEN_PATH_E2E=1 to run the destructive slot-5 "
            "golden-path release gate (30-60 live frontier calls)."
        ),
    ),
]


def _query(sql: str, params: Any = None) -> List[Dict[str, Any]]:
    conn = psycopg2.connect(DSN)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())
    finally:
        conn.close()


def _scalar(sql: str, params: Any = None) -> Any:
    rows = _query(sql, params)
    return next(iter(rows[0].values())) if rows else None


class GoldenPathRun:
    """Shared state captured by the staged run for the assertion tests."""

    def __init__(self) -> None:
        self.server: Optional[subprocess.Popen] = None
        self.log_path: Optional[Path] = None
        self.transition: Dict[str, Any] = {}
        self.turns: List[Dict[str, Any]] = []
        self.turn_seconds: List[float] = []
        self.prologue_chunk_id: Optional[int] = None
        self.failures: List[str] = []


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _wait_health(timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if requests.get(f"{API}/health", timeout=3).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    raise RuntimeError("Stage server-boot: API server never became healthy")


def _stage_reset_slot() -> None:
    from nexus.api.db_pool import close_pool
    from nexus.api.save_slots import upsert_slot
    from nexus.api.new_story_cache import write_cache
    from scripts.new_story_setup import create_slot_schema_only

    close_pool(DBNAME)
    create_slot_schema_only(SLOT, source_db="NEXUS_template", force=True)

    cache = json.loads(FIXTURE.read_text())
    write_cache(
        thread_id=cache["thread_id"],
        setting_draft=cache["setting_draft"],
        character_draft=cache["character_draft"],
        selected_seed=cache["selected_seed"],
        layer_draft=cache["layer_draft"],
        zone_draft=cache["zone_draft"],
        initial_location=cache["initial_location"],
        target_slot=SLOT,
        dbname=DBNAME,
    )
    # Fresh slots default to the mock TEST model; a real wizard run persists
    # the real model in start_setup. Mirror that so the transition engages
    # Retrograde + trait derivation with real frontier calls.
    from nexus.api.config_utils import get_new_story_model

    upsert_slot(SLOT, model=get_new_story_model(), dbname=DBNAME)
    close_pool(DBNAME)


def _stage_run_transition(run: GoldenPathRun) -> None:
    response = requests.post(
        f"{API}/api/story/new/transition",
        json={"slot": SLOT},
        timeout=TRANSITION_TIMEOUT_SECONDS,
    )
    if not response.ok:
        raise RuntimeError(f"Stage transition: {response.status_code} {response.text}")
    run.transition = response.json()


def _poll_generation(session_id: str) -> None:
    deadline = time.monotonic() + GENERATION_POLL_SECONDS
    while time.monotonic() < deadline:
        try:
            status = requests.get(
                f"{API}/api/narrative/status/{session_id}",
                params={"slot": SLOT},
                timeout=60,
            )
        except requests.RequestException:
            # The single-worker server shares its host with in-process
            # embedding inference; a slow status read is expected under
            # load. The status GET is idempotent -- keep polling until the
            # overall deadline.
            time.sleep(2)
            continue
        if status.ok:
            state = status.json().get("status")
            if state in {
                "complete",
                "completed",
                "provisional",
                "approved",
                "committed",
            }:
                return
            if state == "error":
                raise RuntimeError(
                    f"Stage play: generation session {session_id} errored: "
                    f"{status.json()}"
                )
        time.sleep(2)
    raise RuntimeError(f"Stage play: generation session {session_id} timed out")


def _continue_turn(payload: Dict[str, Any]) -> Dict[str, Any]:
    body: Dict[str, Any] = {"slot": SLOT, "user_text": payload.get("user_text", "")}
    if payload.get("choice") is not None:
        body["choice"] = payload["choice"]
    response = requests.post(f"{API}/api/narrative/continue", json=body, timeout=120)
    if not response.ok:
        raise RuntimeError(
            f"Stage play: continue failed {response.status_code}: {response.text}"
        )
    data = response.json()
    session_id = data.get("session_id")
    if session_id:
        _poll_generation(session_id)
    return data


def _goal_state() -> Dict[str, bool]:
    promoted = int(
        _scalar(
            "SELECT count(*) FROM orrery_resolutions "
            "WHERE promotion_status = 'promoted'"
        )
        or 0
    )
    narrated = int(_scalar("SELECT count(*) FROM offscreen_narrations") or 0)
    offered = int(
        _scalar("SELECT count(*) FROM orrery_resolutions WHERE offer_count > 0") or 0
    )
    matured = int(
        _scalar(
            "SELECT count(*) FROM orrery_maturation_jobs "
            "WHERE state::text = 'succeeded'"
        )
        or 0
    )
    return {
        "promotion": promoted > 0,
        "narration": narrated > 0,
        "bleed_offer": offered > 0,
        "maturation": matured > 0,
    }


def _stage_play_turns(run: GoldenPathRun) -> None:
    # Bootstrap chunk 1 of play.
    run.turns.append({"input": "bootstrap"})
    started = time.monotonic()
    _continue_turn({"user_text": ""})
    run.turn_seconds.append(time.monotonic() - started)

    scripted = list(SCRIPTED_OPENING)
    for turn_index in range(GOLDEN_PATH_MAX_TURNS):
        payload = scripted.pop(0) if scripted else dict(ADAPTIVE_INPUT)
        run.turns.append({"input": payload})
        started = time.monotonic()
        _continue_turn(payload)
        run.turn_seconds.append(time.monotonic() - started)
        if not scripted and all(_goal_state().values()):
            break

    # Let detached work settle: the maturation drain and the embedding
    # catch-up both run after the last commit.
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        goals = _goal_state()
        pending_jobs = int(
            _scalar(
                "SELECT count(*) FROM orrery_maturation_jobs "
                "WHERE state::text IN ('pending', 'leased')"
            )
            or 0
        )
        if all(goals.values()) and pending_jobs == 0:
            break
        time.sleep(5)


@pytest.fixture(scope="module")
def golden_path(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """Execute the staged golden-path run once; yield shared evidence."""

    api_port = int(os.environ.get("NARRATIVE_API_PORT", "8002"))
    if not _port_free(api_port):
        raise RuntimeError(
            f"Port {api_port} is occupied; stop the running NEXUS API server "
            "before the golden-path gate (it boots its own instance), or set "
            "NARRATIVE_API_PORT to a free port."
        )

    from nexus.config import load_settings

    settings = load_settings()
    assert settings.orrery is not None and settings.orrery.enabled
    assert settings.orrery.retrograde.wizard.enabled
    assert settings.orrery.retrograde.maturation.enabled

    run = GoldenPathRun()
    _stage_reset_slot()

    run.log_path = tmp_path_factory.mktemp("golden_path") / "server.log"
    log_handle = run.log_path.open("w")
    run.server = subprocess.Popen(
        [sys.executable, "-m", "nexus.api.narrative"],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        env=os.environ.copy(),
    )
    try:
        _wait_health()
        _stage_run_transition(run)
        run.prologue_chunk_id = _scalar(
            "SELECT id FROM narrative_chunks "
            "WHERE authorial_directives @> %s::jsonb",
            (json.dumps(["orrery:retrograde_prologue_anchor"]),),
        )
        _stage_play_turns(run)
        yield run
    finally:
        if run.server is not None:
            run.server.terminate()
            try:
                run.server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                run.server.kill()
        log_handle.close()


def test_stage1_retrograde_cold_start(golden_path: GoldenPathRun) -> None:
    """The transition ran Retrograde with derived trait inputs and stubs."""

    retro = golden_path.transition.get("retrograde") or {}
    assert retro.get("enabled") is True, retro

    trait_inputs = golden_path.transition.get("trait_inputs") or {}
    assert trait_inputs.get("derived") is True, trait_inputs
    assert "patron" in trait_inputs.get("traits", []), trait_inputs
    assert "dependents" in trait_inputs.get("traits", []), trait_inputs

    events = _query(
        "SELECT id, payload ->> 'retrograde_summary_chunk_id' AS cid "
        "FROM world_events WHERE source = 'retrograde'"
    )
    assert events, "No retrograde world_events were persisted"
    assert all(row["cid"] is not None for row in events)

    # Trait-compiler stubs exist for the fixture's patron and dependents.
    trait_stubs = _query(
        "SELECT name FROM characters "
        "WHERE extra_data ->> 'stub_kind' = 'trait_compiler_target_ref'"
    )
    assert len(trait_stubs) >= 3, trait_stubs

    # Decision-8 cap: the wizard-time expansion stayed within its stub
    # budget. Assert the transition's own counter -- runtime maturations
    # later in the run legitimately add their own expansion stubs, so an
    # end-of-run table count would conflate the two.
    from nexus.config import load_settings

    settings = load_settings()
    assert settings.orrery is not None
    cap = settings.orrery.retrograde.wizard.max_new_entity_stubs
    counters = retro.get("counters") or {}
    assert int(counters.get("entity_stubs_inserted", 0)) <= cap, counters

    # The duplicate-stub regression: one canonical row per character name.
    duplicates = _query(
        "SELECT lower(name) AS name, count(*) AS n FROM characters "
        "GROUP BY lower(name) HAVING count(*) > 1"
    )
    assert not duplicates, f"Duplicate canonical characters: {duplicates}"


def test_stage2_turns_played(golden_path: GoldenPathRun) -> None:
    """The scripted opening plus adaptive turns all completed."""

    assert len(golden_path.turns) >= len(SCRIPTED_OPENING) + 1
    assert all(seconds > 0 for seconds in golden_path.turn_seconds)


def test_stage3_chunk_persistence_and_incubator(golden_path: GoldenPathRun) -> None:
    """Committed chunks exist and exactly one provisional chunk is pending."""

    committed = int(_scalar("SELECT count(*) FROM narrative_chunks"))
    summary_chunks = int(
        _scalar(
            "SELECT count(*) FROM narrative_chunks "
            "WHERE authorial_directives @> %s::jsonb",
            (json.dumps(["orrery:retrograde_event_summary"]),),
        )
    )
    played = committed - summary_chunks - 1  # minus prologue anchor
    assert played >= len(golden_path.turns) - 1, (
        f"Expected at least {len(golden_path.turns) - 1} committed played "
        f"chunks, found {played} (committed={committed}, "
        f"summaries={summary_chunks})"
    )
    pending = _query("SELECT chunk_id FROM incubator")
    assert len(pending) == 1, pending


def test_stage4_embedding_lifecycle(golden_path: GoldenPathRun) -> None:
    """Locked == embedded; only the prologue and the undo buffer stay raw.

    The undo buffer is the newest committed played chunk: it stays mutable
    (and unembedded) until the next turn locks it. The Retrograde prologue
    anchor is intentionally never embedded. Everything else must embed --
    including played chunks separated from their successor by interleaved
    summary chunks (the M9 id-arithmetic regression).
    """

    deadline = time.monotonic() + 180
    pending: List[int] = []
    while time.monotonic() < deadline:
        unembedded = [
            row["id"]
            for row in _query(
                "SELECT id FROM narrative_chunks "
                "WHERE embedding_generated_at IS NULL ORDER BY id"
            )
        ]
        pending = [
            chunk_id
            for chunk_id in unembedded
            if chunk_id != golden_path.prologue_chunk_id
        ]
        if len(pending) <= 1:
            break
        time.sleep(5)
    assert len(pending) <= 1, (
        f"Locked chunks missing embeddings: {pending[:-1]} "
        "(embedded == ironman is the contract; only the newest committed "
        "chunk may remain unembedded)"
    )


def test_stage5_retrograde_history_retrievable(golden_path: GoldenPathRun) -> None:
    """MEMNON returns Retrograde history for an event-specific query."""

    from nexus.agents.memnon.memnon import MEMNON

    events = _query(
        "SELECT payload ->> 'summary' AS summary, "
        "payload ->> 'retrograde_summary_chunk_id' AS cid "
        "FROM world_events WHERE source = 'retrograde' "
        "AND payload ->> 'retrograde_summary_chunk_id' IS NOT NULL"
    )
    target = max(events, key=lambda row: len(row["summary"] or ""))
    memnon = MEMNON(interface=None, db_url=DSN)
    search = memnon.query_memory(query=target["summary"], k=10, use_hybrid=True)
    returned = {
        int(chunk.get("chunk_id") or chunk["id"]) for chunk in search["results"]
    }
    assert int(target["cid"]) in returned, (
        f"MEMNON missed retrograde summary chunk {target['cid']}; "
        f"returned={sorted(returned)}"
    )


def test_stage6_orrery_promotion_narration_bleed(golden_path: GoldenPathRun) -> None:
    """Off-screen resolutions promoted, narrated, and offered as Bleed."""

    promoted = _query(
        "SELECT id, template_id, first_surfaced_chunk_id, offer_count "
        "FROM orrery_resolutions WHERE promotion_status = 'promoted'"
    )
    assert promoted, "No Orrery resolution promoted during the run"

    narrations = _query("SELECT resolution_id, text FROM offscreen_narrations")
    assert narrations, "Promotion occurred but no narration landed"

    offered = [row for row in promoted if (row["offer_count"] or 0) > 0]
    assert offered, "No narrated resolution was offered to the Storyteller"

    # Bleed-into-prose heuristic: a committed chunk at or after the first
    # surfacing references the offered resolution's actor by name. (The
    # definitive prose-weave reading is part of the manual gate evidence.)
    surfaced = [row for row in offered if row["first_surfaced_chunk_id"]]
    assert surfaced, "Offered resolutions never recorded a surfacing chunk"
    woven = _query(
        """
        SELECT r.id
        FROM orrery_resolutions r
        JOIN entity_names_v en ON en.id = r.actor_entity_id
        JOIN narrative_chunks nc ON nc.id >= r.first_surfaced_chunk_id
        WHERE r.offer_count > 0
          AND position(
              en.name IN COALESCE(nc.raw_text, nc.storyteller_text, '')
          ) > 0
        LIMIT 1
        """
    )
    assert woven, "No offered off-screen actor surfaced in subsequent prose"


def test_stage7_runtime_maturation(golden_path: GoldenPathRun) -> None:
    """A Skald-declared entity matured and its history is retrievable."""

    jobs = _query(
        "SELECT entity_name, state::text AS state, result_manifest "
        "FROM orrery_maturation_jobs"
    )
    succeeded = [job for job in jobs if job["state"] == "succeeded"]
    assert succeeded, f"No maturation job succeeded; jobs={jobs}"

    job = succeeded[0]
    manifest = job["result_manifest"]
    assert manifest["persisted"] is True
    event_ids = list(manifest["world_event_ids"].values())
    assert event_ids, "Maturation persisted no world events"
    count = _scalar(
        "SELECT count(*) FROM world_events "
        "WHERE id = ANY(%s) AND source = 'retrograde'::event_source_kind",
        (event_ids,),
    )
    assert int(count) == len(event_ids)

    from nexus.agents.memnon.memnon import MEMNON

    pending = manifest.get("embedding_pending_chunk_ids") or []
    assert pending, "Maturation produced no summary chunks"
    memnon = MEMNON(interface=None, db_url=DSN)
    search = memnon.query_memory(query=job["entity_name"], k=15, use_hybrid=True)
    returned = {
        int(chunk.get("chunk_id") or chunk["id"]) for chunk in search["results"]
    }
    assert returned & set(map(int, pending)), (
        f"MEMNON did not retrieve matured history for {job['entity_name']}: "
        f"chunks={pending} returned={sorted(returned)}"
    )


def test_stage8_server_log_clean(golden_path: GoldenPathRun) -> None:
    """The full run produced no tracebacks and no ERROR lines.

    The level matcher is coupled to the standard ``- LEVEL -`` log format,
    so a format-detection canary guards against the assertion silently
    becoming a no-op if the logging format ever changes.
    """

    assert golden_path.log_path is not None
    log_text = golden_path.log_path.read_text()
    assert " - INFO - " in log_text, (
        "Log format canary failed: no ' - INFO - ' lines found, so the "
        "ERROR matcher below cannot be trusted. Update both matchers to "
        "the current logging format."
    )
    assert "Traceback (most recent call last)" not in log_text
    error_lines = [
        line
        for line in log_text.splitlines()
        if " - ERROR - " in line or " - CRITICAL - " in line
    ]
    assert not error_lines, "Server log contains errors:\n" + "\n".join(
        error_lines[:20]
    )
