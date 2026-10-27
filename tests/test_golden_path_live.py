"""Golden-Path Release Gate (M9): one live end-to-end run proves the MVP.

EXPENSIVE, SLOW. This is the backend v1.0 release gate: it creates and
migrates a disposable template clone through the production slot initializer
(``disposable_slot_database`` -> ``initialize_slot_database``), boots the real
API server as a subprocess with ``ROUTED_SLOT`` routed to that clone
(``tests.slot_routed_gateway``), runs the wizard -> narrative transition with a
real Retrograde cold start, then plays live turns through the production HTTP
surface -- every model call is a real frontier call. No numbered owner slot is
reset, read, or written.

Reduced-path note: the wizard CHAT phases are staged from a canned cache
captured from a full manual CLI wizard run (the conversational wizard is
covered by its own live suites); everything from the transition onward --
trait-input derivation, Retrograde generation/persistence/embedding, the
bootstrap, and all play turns -- runs live. The companion full ~10-turn
manual run is documented on the M9 PR.

Stages (ordered; each test asserts one category against the shared run):
  1. Retrograde cold start fired at the transition (world_events
     source='retrograde', embedded per-event summaries, derived trait
     inputs, trait-compiler stubs, decision-8 caps, no duplicate entities).
  2. Live play: scripted turns including one freeform directive, one
     entity-eliciting input, and one explicit time skip (sunhelm needs accrue
     on world time; a fresh world's Orrery wakes through them), then
     adaptive eventful turns until promotion + bleed-offer/prose weave +
     persisted maturation have all occurred (bounded by GOLDEN_PATH_MAX_TURNS).
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
  9. Turn observation (#802): each played turn's observation carries ledger
     usage for every responding attempt, its background jobs settled, and the
     Backstage economics read observes the accepted and the pending turn.

Gating: NEXUS_RUN_LIVE_LLM=1, NEXUS_RUN_POSTGRES=1, and the expensive-run
opt-in NEXUS_GOLDEN_PATH_E2E=1. The ``golden_path`` fixture sets NEXUS_SLOT to
ROUTED_SLOT (4) for the run, so the gateway subprocess starts the SlotScheduler
that owns the clone's deferred work (the only production caller of
``drain_maturation_jobs_sync``, which stage 7 and the adaptive tail need); the
operator's own NEXUS_SLOT is ignored. Staging the wizard cache and booting the
routed gateway are proven without the live opt-in in
``tests/test_live_gate_clones_pg.py``.

Cost and wall clock: measured green run (2026-06-11, gpt-5.5 +
@anthropic.default narration): 20 frontier calls, 14m30s end to end.
Budget ~20-35 calls / 15-30 minutes; the adaptive tail adds turns only
when promotion/bleed-weave/persisted maturation lag. Budget accordingly before CI.

Cleanup: the API server subprocess is terminated on teardown and the clone
is dropped with the module fixture.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
import requests
import tomlkit
from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]

import nexus.telemetry.usage as usage_telemetry
from nexus.agents.orrery.backstage import read_backstage_economics
from nexus.telemetry.attempt_manifest import (
    JOB_TABLES,
    PROVIDER_JOB_SEATS,
    inspect_turn,
)
from nexus.telemetry.turn_observation import observe_turn
from tests import secret_store_guard
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
)
from tests.turn_observation_contract import (
    BOOTSTRAP_SEATS,
    TWO_PASS_SEATS,
    assert_critical_path,
)

# The slot label the clone is routed under, in this process and in the
# gateway subprocess.
ROUTED_SLOT = 4
# The clone of the active run; empty outside the golden_path fixture, so a
# query can never resolve an owner database.
_RUN_DATABASE: List[str] = []
# NARRATIVE_API_PORT lets the gate run beside a live stack (agent worktrees);
# the spawned server subprocess inherits it via env. Without it, the gate and
# its child use the configured operator port ([runtime.gateway].operator_port).


def _default_api_port() -> int:
    """The configured operator port the gate's gateway child binds by default."""
    from nexus.config import load_settings

    runtime = load_settings().runtime
    if runtime is None:
        raise RuntimeError("nexus.toml has no [runtime] section for the gate's port")
    return runtime.gateway.operator_port


API = f"http://localhost:{os.environ.get('NARRATIVE_API_PORT') or _default_api_port()}"
FIXTURE = Path(__file__).parent / "fixtures" / "golden_path_wizard_cache.json"
MODEL_OVERRIDE_ENV = "NEXUS_GOLDEN_MODEL_REF"
RUNTIME_CONFIG_ENV = "NEXUS_RUNTIME_CONFIG"

# Hard ceiling on play turns; the run goes adaptive after the scripted
# opening if promotion/bleed-weave/persisted maturation have not all occurred yet.
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
ADAPTIVE_ENTITY_INPUT = {
    "user_text": (
        "I slow down and ask the nearest unnamed witness for their name, "
        "trade, and what they risk by helping. If there is a new helper, "
        "informer, guard, or neighbor who matters, bring that person "
        "on-screen by name now so I can remember them."
    )
}

GENERATION_POLL_SECONDS = 360
TRANSITION_TIMEOUT_SECONDS = 900

pytestmark = [
    pytest.mark.live,
    pytest.mark.live_llm,
    pytest.mark.requires_postgres,
    pytest.mark.skipif(
        os.environ.get("NEXUS_GOLDEN_PATH_E2E") != "1",
        reason="Set NEXUS_GOLDEN_PATH_E2E=1 to run the expensive golden-path gate.",
    ),
]


def _dbname() -> str:
    """Return the active run's clone; fail loudly outside the fixture."""
    if len(_RUN_DATABASE) != 1:
        raise RuntimeError("No golden-path clone is active")
    return _RUN_DATABASE[0]


def _dsn() -> str:
    """Resolve the run's clone through the shared connection contract."""
    from nexus.database import database_url

    return database_url(_dbname())


def _query(sql: str, params: Any = None) -> List[Dict[str, Any]]:
    conn = connect(_dbname())
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
        self.usage_dir: Optional[Path] = None
        self.transition: Dict[str, Any] = {}
        self.turns: List[Dict[str, Any]] = []
        self.turn_seconds: List[float] = []
        self.prologue_chunk_id: Optional[int] = None
        self.failures: List[str] = []


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _wait_health(api: str = API, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if requests.get(f"{api}/health", timeout=3).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    raise RuntimeError("Stage server-boot: API server never became healthy")


def launch_routed_gateway(
    dbname: str, log_handle: Any, *, store_access: bool
) -> subprocess.Popen:
    """Boot the gateway entry point with ``ROUTED_SLOT`` routed to ``dbname``.

    The child inherits ``NEXUS_SLOT``: the golden path sets it to
    ``ROUTED_SLOT`` so the gateway's scheduler owns the clone's deferred work,
    and the no-opt-in proof unsets it so no scheduler starts (any other slot
    fails at startup). ``store_access`` hands the child the owner's secret store,
    which the live gate's frontier calls need; without it the child runs in
    env-only mode.
    """

    env = {
        **os.environ,
        "NEXUS_ROUTED_SLOT": str(ROUTED_SLOT),
        "NEXUS_ROUTED_SLOT_DATABASE": dbname,
    }
    return subprocess.Popen(
        [sys.executable, "-m", "tests.slot_routed_gateway"],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        # The live gate's server reads provider keys from the owner's
        # Keychain. Without this opt-out the secret-store guard (#963)
        # starts it in env-only mode and its first model call fails with
        # MissingSecretError.
        env=secret_store_guard.store_access_env(env) if store_access else env,
    )


def stage_reset_slot(dbname: str) -> None:
    """Stage the canned, confirmed wizard cache in a fresh routed clone."""
    from nexus.api.db_pool import close_pool
    from nexus.api.save_slots import upsert_slot
    from nexus.api.new_story_cache import write_cache

    cache = json.loads(FIXTURE.read_text())
    write_cache(
        thread_id=cache["thread_id"],
        setting_draft=cache["setting_draft"],
        character_draft=cache["character_draft"],
        selected_seed=cache["selected_seed"],
        layer_draft=cache["layer_draft"],
        zone_draft=cache["zone_draft"],
        initial_location=cache["initial_location"],
        base_timestamp=cache["base_timestamp"],
        target_slot=ROUTED_SLOT,
        dbname=dbname,
    )
    from nexus.api.new_story_cache import read_cache
    from nexus.api.wizard_confirmation import confirm_artifact

    for phase in ("setting", "character"):
        draft = read_cache(dbname)
        confirm_artifact(
            dbname,
            thread_id=draft.thread_id,
            phase=phase,
            artifact_token=draft.artifact_token(phase),
        )
    # A fresh slot stores no model pin (NULL); a real wizard run persists the
    # resolved model in start_setup. Mirror that so the transition engages
    # Retrograde + trait derivation with real frontier calls.
    from nexus.api.config_utils import get_new_story_model

    upsert_slot(ROUTED_SLOT, model=get_new_story_model(), dbname=dbname)
    close_pool(dbname)


def _stage_run_transition(run: GoldenPathRun) -> None:
    response = requests.post(
        f"{API}/api/story/new/transition",
        json={"slot": ROUTED_SLOT},
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
                params={"slot": ROUTED_SLOT},
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
    body: Dict[str, Any] = {
        "slot": ROUTED_SLOT,
        "user_text": payload.get("user_text", ""),
    }
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
            "WHERE state::text = 'succeeded' "
            "AND COALESCE((result_manifest ->> 'persisted')::boolean, false)"
        )
        or 0
    )
    return {
        "promotion": promoted > 0,
        "narration": narrated > 0,
        "bleed_offer": offered > 0,
        "bleed_weave": bool(_bleed_woven_rows()),
        "maturation": matured > 0,
    }


def _bleed_woven_rows() -> List[Dict[str, Any]]:
    return _query(
        """
        SELECT r.id, en.name
        FROM orrery_resolutions r
        JOIN entity_names_v en ON en.id = r.actor_entity_id
        JOIN narrative_chunks nc ON nc.id >= r.first_surfaced_chunk_id
        WHERE r.offer_count > 0
          AND r.first_surfaced_chunk_id IS NOT NULL
          AND position(
              lower(en.name) IN lower(COALESCE(nc.raw_text, nc.storyteller_text, ''))
          ) > 0
        LIMIT 1
        """
    )


def _offered_bleed_actor_needing_weave() -> Optional[str]:
    rows = _query(
        """
        SELECT en.name
        FROM orrery_resolutions r
        JOIN entity_names_v en ON en.id = r.actor_entity_id
        WHERE r.offer_count > 0
          AND r.first_surfaced_chunk_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM narrative_chunks nc
              WHERE nc.id >= r.first_surfaced_chunk_id
                AND position(
                    lower(en.name)
                    IN lower(COALESCE(nc.raw_text, nc.storyteller_text, ''))
                ) > 0
          )
        ORDER BY r.first_surfaced_chunk_id, r.id
        LIMIT 1
        """
    )
    if not rows:
        return None
    return str(rows[0]["name"])


def _has_persisted_maturation() -> bool:
    return bool(
        _scalar(
            "SELECT 1 FROM orrery_maturation_jobs "
            "WHERE state::text = 'succeeded' "
            "AND COALESCE((result_manifest ->> 'persisted')::boolean, false) "
            "LIMIT 1"
        )
    )


def _adaptive_payload() -> Dict[str, Any]:
    actor_name = _offered_bleed_actor_needing_weave()
    if actor_name:
        return {
            "user_text": (
                f"Before leaving this thread, I look for any sign of {actor_name}. "
                f"If {actor_name} is not present, name the trace, rumor, or "
                f"consequence of {actor_name} that reaches me now."
            )
        }
    if not _has_persisted_maturation():
        return dict(ADAPTIVE_ENTITY_INPUT)
    return dict(ADAPTIVE_INPUT)


def _open_provider_jobs() -> int:
    """Count queued or leased jobs on every provider-backed queue."""
    # The table names are module constants (JOB_TABLES), never input.
    return sum(
        int(
            _scalar(
                f"SELECT count(*) FROM {JOB_TABLES[queue]} "
                "WHERE state::text IN ('queued', 'leased')"
            )
            or 0
        )
        for queue in PROVIDER_JOB_SEATS
    )


def _stage_play_turns(run: GoldenPathRun) -> None:
    # Bootstrap chunk 1 of play.
    run.turns.append({"input": "bootstrap"})
    started = time.monotonic()
    run.turns[-1]["session_id"] = _continue_turn({"user_text": ""}).get("session_id")
    run.turn_seconds.append(time.monotonic() - started)

    scripted = list(SCRIPTED_OPENING)
    for turn_index in range(GOLDEN_PATH_MAX_TURNS):
        payload = scripted.pop(0) if scripted else _adaptive_payload()
        run.turns.append({"input": payload})
        started = time.monotonic()
        run.turns[-1]["session_id"] = _continue_turn(payload).get("session_id")
        run.turn_seconds.append(time.monotonic() - started)
        if not scripted and all(_goal_state().values()):
            break

    # Let detached work settle: every provider-backed queue (PROVIDER_JOB_SEATS)
    # drains, and the embedding catch-up runs after the last commit.
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        goals = _goal_state()
        pending_jobs = _open_provider_jobs()
        if all(goals.values()) and pending_jobs == 0:
            break
        time.sleep(5)


def _configure_run_config(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Write the run's runtime config: its own usage ledger directory (802-D9)
    and any golden model override."""

    source = Path(os.environ.get(RUNTIME_CONFIG_ENV, "nexus.toml"))
    document: Any = tomlkit.parse(source.read_text())

    model_ref = os.environ.get(MODEL_OVERRIDE_ENV)
    if model_ref:
        from nexus.config import load_settings

        provider = load_settings().provider_for_model(model_ref)
        if provider not in {"openai", "anthropic"}:
            raise RuntimeError(
                f"{MODEL_OVERRIDE_ENV} provider must be openai or anthropic, got "
                f"{provider!r}"
            )
        document["global"]["model"]["default_model"] = model_ref
        document["wizard"]["default_model"] = model_ref
        document["apex"]["provider"] = provider
        document["apex"]["model"] = model_ref
        if "orrery" in document:
            document["orrery"]["retrograde"]["maturation"]["model_ref"] = model_ref

    usage_dir = tmp_path_factory.mktemp("golden_usage").resolve()
    document["usage"]["usage_dir"] = str(usage_dir)

    path = tmp_path_factory.mktemp("golden_config") / "nexus.toml"
    path.write_text(tomlkit.dumps(document))
    os.environ[RUNTIME_CONFIG_ENV] = str(path)
    return usage_dir


@pytest.fixture(scope="module")
def golden_path(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """Execute the staged golden-path run once; yield shared evidence."""

    original_runtime_config = os.environ.get(RUNTIME_CONFIG_ENV)
    try:
        usage_dir = _configure_run_config(tmp_path_factory)

        api_port = int(os.environ.get("NARRATIVE_API_PORT") or _default_api_port())
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
        run.usage_dir = usage_dir
        with (
            disposable_slot_database("qa640_golden_path", story_pin=None) as dbname,
            pytest.MonkeyPatch.context() as patch,
        ):
            route_slot_to_disposable(patch.setattr, slot=ROUTED_SLOT, dbname=dbname)
            # The gateway child inherits this: its SlotScheduler is the only
            # production drain for maturation (stage 7) and the adaptive tail.
            patch.setenv("NEXUS_SLOT", str(ROUTED_SLOT))
            _RUN_DATABASE.append(dbname)
            try:
                stage_reset_slot(dbname)

                run.log_path = tmp_path_factory.mktemp("golden_path") / "server.log"
                log_handle = run.log_path.open("w")
                run.server = launch_routed_gateway(
                    dbname, log_handle, store_access=True
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
            finally:
                _RUN_DATABASE.clear()
    finally:
        if original_runtime_config is None:
            os.environ.pop(RUNTIME_CONFIG_ENV, None)
        else:
            os.environ[RUNTIME_CONFIG_ENV] = original_runtime_config


def test_stage1_retrograde_cold_start(golden_path: GoldenPathRun) -> None:
    """The transition ran Retrograde with derived trait inputs and stubs."""

    retro = golden_path.transition.get("retrograde") or {}
    assert retro.get("enabled") is True, retro

    trait_inputs = golden_path.transition.get("trait_inputs") or {}
    assert trait_inputs.get("derived") is True, trait_inputs
    assert "patron" in trait_inputs.get("traits", []), trait_inputs
    assert "dependents" in trait_inputs.get("traits", []), trait_inputs

    events = _query(
        "SELECT we.id, rs.id AS summary_id "
        "FROM world_events we "
        "JOIN retrograde_summaries rs ON rs.world_event_id = we.id "
        "WHERE we.source = 'retrograde'"
    )
    assert events, "No retrograde world_events were persisted"
    assert all(row["summary_id"] is not None for row in events)

    # Trait-compiler stubs exist for the fixture's patron and dependents.
    trait_stubs = _query(
        "SELECT name FROM characters "
        "WHERE extra_data ->> 'stub_kind' = 'trait_compiler_target_ref'"
    )
    assert len(trait_stubs) >= 3, trait_stubs

    # Decision-8 cap: the wizard-time expansion stayed within its stub
    # budget. Assert the transition's own accounting -- runtime maturations
    # later in the run legitimately add their own expansion stubs, so an
    # end-of-run table count would conflate the two. First-class stubs
    # (trait targets or seed NPCs without a trait-compiler row) are inserted
    # but not charged, the same rule R6 validation applies.
    from nexus.config import load_settings

    settings = load_settings()
    assert settings.orrery is not None
    cap = settings.orrery.retrograde.wizard.max_new_entity_stubs
    stub_budget = retro["entity_stub_budget"]
    assert stub_budget["max_new_entity_stubs"] == cap, stub_budget
    assert len(stub_budget["charged_stubs"]) <= cap, stub_budget

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
    played = committed - 1  # minus the synthetic prologue anchor
    assert played >= len(golden_path.turns) - 1, (
        f"Expected at least {len(golden_path.turns) - 1} committed played "
        f"chunks, found {played} (committed={committed})"
    )
    pending = _query("SELECT chunk_id FROM incubator")
    assert len(pending) == 1, pending


def test_stage4_embedding_lifecycle(golden_path: GoldenPathRun) -> None:
    """Locked == embedded; only the prologue and the undo buffer stay raw.

    The undo buffer is the newest committed played chunk: it stays mutable
    (and unembedded) until the next turn locks it. The Retrograde prologue
    anchor is intentionally never embedded. Everything else must embed --
    including played chunks separated from their successor by preserved gaps
    from retired summary rows (the M9 id-arithmetic regression).
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
        "SELECT rs.summary_text AS summary, rs.id AS summary_id "
        "FROM retrograde_summaries rs "
        "JOIN world_events we ON we.id = rs.world_event_id "
        "WHERE we.source = 'retrograde'"
    )
    target = max(events, key=lambda row: len(row["summary"] or ""))
    memnon = MEMNON(interface=None, db_url=_dsn())
    search = memnon.query_memory(query=target["summary"], k=10, use_hybrid=True)
    returned = {
        int(item["summary_id"])
        for item in search["results"]
        if item.get("content_type") == "retrograde_summary"
    }
    assert int(target["summary_id"]) in returned, (
        f"MEMNON missed retrograde summary {target['summary_id']}; "
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
    woven = _bleed_woven_rows()
    assert woven, "No offered off-screen actor surfaced in subsequent prose"


def test_stage7_runtime_maturation(golden_path: GoldenPathRun) -> None:
    """A Skald-declared entity matured and its history is retrievable."""

    jobs = _query(
        "SELECT entity_name, state::text AS state, result_manifest "
        "FROM orrery_maturation_jobs"
    )
    succeeded = [
        job
        for job in jobs
        if job["state"] == "succeeded"
        and (job["result_manifest"] or {}).get("persisted") is True
    ]
    assert succeeded, f"No persisted maturation job succeeded; jobs={jobs}"

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

    pending = manifest.get("embedding_pending_summary_ids") or []
    assert pending, "Maturation produced no summaries"
    memnon = MEMNON(interface=None, db_url=_dsn())
    search = memnon.query_memory(query=job["entity_name"], k=15, use_hybrid=True)
    returned = {
        int(item["summary_id"])
        for item in search["results"]
        if item.get("content_type") == "retrograde_summary"
    }
    assert returned & set(map(int, pending)), (
        f"MEMNON did not retrieve matured history for {job['entity_name']}: "
        f"summaries={pending} returned={sorted(returned)}"
    )


def test_stage8_server_log_clean(golden_path: GoldenPathRun) -> None:
    """The full run produced no tracebacks and no ERROR lines.

    The level matcher is coupled to the standard ``- LEVEL -`` log format,
    so a format-detection canary guards against the assertion silently
    becoming a no-op if the logging format ever changes.
    """

    assert golden_path.log_path is not None
    assert_server_log_clean(golden_path.log_path.read_text())


def _classify_background(observation: Dict[str, Any]) -> Dict[str, Any]:
    """Sort a turn's provider-backed jobs by whether their usage is explained.

    ``reported`` jobs carry ledger usage. A job without it is ``without_call``
    only when its row shows that it ended before any provider call (Decision
    802-D7): ``stale_rejected``; a maturation job ``succeeded`` with
    ``skipped: already_connected``; or a compaction job ``succeeded`` with no
    error and no digest for its accepting chunk (``no_compaction_due``: a call
    that returns writes its digest or fails the job). Every other job without
    usage is ``unexplained``: a failed or succeeded row without such a marker
    cannot show that no call was made.
    """
    reported: List[Dict[str, Any]] = []
    without_call: List[Dict[str, Any]] = []
    unexplained: List[Dict[str, Any]] = []
    for entry in observation["jobs"]["entries"]:
        if "usage" not in entry:
            continue
        usage = entry["usage"]
        if usage["provenance"] == "provider_usage_ledger":
            reported.append(
                {
                    "queue": entry["queue"],
                    "id": entry["id"],
                    "state": entry["state"],
                    "seats": usage["seats"],
                    "input_tokens": usage["input_tokens"],
                    "output_tokens": usage["output_tokens"],
                }
            )
            continue
        queue = entry["queue"]
        if queue == "retrograde_maturation":
            sql = (
                "SELECT state::text AS state, last_error, "
                "result_manifest ->> 'skipped' AS skipped "
                "FROM orrery_maturation_jobs WHERE id = %s"
            )
        elif queue == "correspondence_compaction":
            sql = (
                "SELECT j.state::text AS state, j.last_error, NOT EXISTS ("
                "SELECT 1 FROM storyteller_correspondence_digest_versions d "
                "WHERE d.accepting_chunk_id = j.accepting_chunk_id) AS no_digest "
                "FROM correspondence_compaction_jobs j WHERE j.id = %s"
            )
        else:
            # The table names are module constants (JOB_TABLES), never input.
            sql = (
                "SELECT state::text AS state, last_error, NULL::text AS skipped "
                f"FROM {JOB_TABLES[queue]} WHERE id = %s"
            )
        rows = _query(sql, (entry["id"],))
        if len(rows) != 1:
            raise RuntimeError(f"Stage 9: no {queue} row for job {entry['id']}")
        row = rows[0]
        state = row["state"]
        skipped: Optional[str] = row.get("skipped")
        if state == "stale_rejected":
            no_call = True
        elif queue == "retrograde_maturation":
            no_call = state == "succeeded" and skipped == "already_connected"
        elif queue == "correspondence_compaction":
            no_call = (
                state == "succeeded"
                and row["last_error"] is None
                and row["no_digest"] is True
            )
            if no_call:
                skipped = "no_compaction_due"
        else:
            no_call = False
        record = {
            "queue": queue,
            "id": entry["id"],
            "state": state,
            "skipped": skipped,
            "last_error": row["last_error"],
        }
        (without_call if no_call else unexplained).append(record)
    return {
        "jobs_open": observation["usage_totals"]["background"]["jobs_open"],
        "reported": reported,
        "without_call": without_call,
        "unexplained": unexplained,
    }


def test_stage9_turn_observation(
    golden_path: GoldenPathRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each played turn's observation and the Backstage economics read hold on
    real providers (#802)."""

    config = usage_telemetry._load_recorder_config()
    assert config.usage_dir == golden_path.usage_dir, (
        config.usage_dir,
        golden_path.usage_dir,
    )
    monkeypatch.setattr(usage_telemetry, "_config", config)

    sessions = [turn["session_id"] for turn in golden_path.turns]
    assert all(isinstance(session, str) for session in sessions), sessions
    assert len(set(sessions)) == len(sessions), sessions

    turns: List[Dict[str, Any]] = []
    for session in sessions:
        with closing(connect(_dbname())) as conn:
            inspection = inspect_turn(conn, session=session)
        observation = observe_turn(inspection, slot=ROUTED_SLOT)
        turns.append(
            {
                "session": session,
                "parent_chunk_id": inspection["session"]["parent_chunk_id"],
                "observation": observation,
                "background": _classify_background(observation),
            }
        )

    parent = _scalar("SELECT parent_chunk_id FROM incubator")
    with closing(connect(_dbname())) as conn:
        economics = read_backstage_economics(conn, slot=ROUTED_SLOT, chunk_id=parent)
    accepted, pending = economics.accepted, economics.pending

    assert golden_path.log_path is not None
    evidence = {
        "turns": [
            {
                "session": turn["session"],
                "parent_chunk_id": turn["parent_chunk_id"],
                "terminal_outcome": turn["observation"]["terminal_outcome"],
                "attempts": [
                    {
                        "seat": attempt["seat"],
                        "attempt": attempt["attempt"],
                        "model": attempt["model"],
                        "provider_outcome": attempt["provider_outcome"],
                        "provider": attempt["usage"]["provider"],
                        "input_tokens": attempt["usage"]["input_tokens"],
                        "output_tokens": attempt["usage"]["output_tokens"],
                    }
                    for attempt in turn["observation"]["attempts"]
                ],
                "usage_totals": turn["observation"]["usage_totals"],
                "background": turn["background"],
            }
            for turn in turns
        ],
        "economics": {
            "parent_chunk_id": parent,
            "accepted": {
                "status": accepted.status,
                "generation_session": accepted.generation_session,
            },
            "pending": (
                None
                if pending is None
                else {
                    "status": pending.status,
                    "generation_session": pending.generation_session,
                }
            ),
        },
    }
    (golden_path.log_path.parent / "turn_observations.json").write_text(
        json.dumps(evidence, indent=2)
    )

    bootstrap = [turn for turn in turns if turn["parent_chunk_id"] == 0]
    assert bootstrap == turns[:1], [
        (turn["session"], turn["parent_chunk_id"]) for turn in turns
    ]
    for index, turn in enumerate(turns):
        assert_critical_path(
            turn["observation"],
            session=turn["session"],
            terminal_outcome="accepted" if index < len(turns) - 1 else None,
            seats=BOOTSTRAP_SEATS if turn["parent_chunk_id"] == 0 else TWO_PASS_SEATS,
        )
        background = turn["background"]
        assert background["jobs_open"] == 0, (turn["session"], background)
        assert background["unexplained"] == [], (turn["session"], background)
        for job in background["reported"]:
            assert type(job["input_tokens"]) is int, (turn["session"], job)
            assert type(job["output_tokens"]) is int, (turn["session"], job)

    assert accepted.status == "observed", accepted
    assert accepted.generation_session == sessions[-2], accepted
    assert pending is not None
    assert pending.status == "observed", pending
    assert pending.detail is None, pending
    assert pending.generation_session == sessions[-1], pending
    assert accepted.observation is not None and pending.observation is not None
    assert_critical_path(
        accepted.observation,
        session=sessions[-2],
        terminal_outcome="accepted",
        seats=TWO_PASS_SEATS,
    )
    assert_critical_path(
        pending.observation,
        session=sessions[-1],
        terminal_outcome=None,
        seats=TWO_PASS_SEATS,
    )


def assert_server_log_clean(log_text: str) -> None:
    """Fail on a traceback or an ERROR/CRITICAL line in a gateway log."""

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
