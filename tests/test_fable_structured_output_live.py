"""Issue #845 probe: the Fable structured-output flake on the production path.

PAID, OPT-IN, NEVER IN A DEFAULT GATE. The module carries the ``live``,
``live_llm``, ``requires_postgres`` and ``requires_corpus`` markers and is
skipped unless ``NEXUS_845_PROBE=1``. It runs once, by the coordinator, after
845-S1 and 845-S2 land (845-S3, Decision 845-D9), with ``NEXUS_RUN_LIVE_LLM=1
NEXUS_RUN_POSTGRES=1 NEXUS_RUN_CORPUS=1 NEXUS_845_PROBE=1`` and
``NEXUS_GATEWAY_PORT`` set to the lane the coordinator assigns
(``NEXUS_API_URL``, ``NEXUS_SLOT`` and ``NEXUS_RUNTIME_CONFIG`` unset).

What it runs (Decisions 845-D1, D2, D3, D5): only the shipped production
path. A disposable data clone of ``save_04`` is pinned to
``claude-fable-5-1`` with no Gaia pin, routed under slot 4, and served by the
real routed gateway on the assigned lane with the owner's secret store. Twelve
two-pass turns are played through the routed CLI (``nexus --json continue``),
eight numbered choices and four freeform inputs. With the shipped
``nexus.toml`` the writer seat runs the native extractor and the Gaia seat
the prompted one, both on Fable.

Cost bound: at most ``CALL_CAP`` (30) Anthropic calls on Fable for the run
(Decision 845-D9). Before each turn the probe counts the Fable events in the
usage ledger and stops when the worst case of one more turn
(``2 * (structured_output_retries + 1)``) would pass the cap. Follow-story
Fable calls (experiences, correspondence compaction, summaries) that start
during a turn are counted at the next check but cannot be refused, so a run
can end above the cap only by those calls; ``summary.md`` reports any excess.
OpenAI calls the clone's frozen jobs make are outside the cap and recorded in
``ledger_all.jsonl``.

What the verdict means: ``reproduced`` when any Fable attempt shows the
Decision 845-D1 symptom (an empty native response on any seat, an empty
prompted response on the Gaia seat, or a ``max_tokens`` or ``refusal`` stop
that left the extractor nothing to read); ``null`` when twelve turns
completed without it, which closes the issue; ``incomplete`` otherwise. The
test asserts ``null``. Evidence (``attempts.jsonl``, ``turns.jsonl``,
``ledger_all.jsonl``, ``summary.md``, ``gateway.log``) lands in a pytest
temporary directory that the run prints as ``845 probe evidence: <dir>``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import pytest
import requests  # type: ignore[import-untyped]

from nexus.config import load_settings
from nexus.config.settings_models import Settings
from nexus.telemetry import usage as usage_telemetry
from nexus.telemetry.usage import UsageEvent
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    routed_slot_environment,
)
from tests.test_golden_path_live import (
    ROUTED_SLOT,
    _wait_health,
    launch_routed_gateway,
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.live_llm,
    pytest.mark.requires_postgres,
    pytest.mark.requires_corpus,
    pytest.mark.skipif(
        os.environ.get("NEXUS_845_PROBE") != "1",
        reason="Set NEXUS_845_PROBE=1 to run the paid #845 Fable probe.",
    ),
]

MODEL_UNDER_TEST = "claude-fable-5-1"  # pin: #845 Decision 845-D3 probes this snapshot
TURN_COUNT = 12
CALL_CAP = 30
# The owner's runtime: the player listener 8002 and the operator listener 8003
# (#824); NEXUS_GATEWAY_PORT names a lane's operator listener.
OWNER_GATEWAY_PORTS = frozenset({8002, 8003})
TURN_INPUTS: list[dict[str, Any]] = [
    {"choice": 1},
    {
        "text": (
            "I stop and ask the nearest person what they saw here, and who they "
            "answer to."
        )
    },
    {"choice": 1},
    {"choice": 1},
    {
        "text": (
            "I keep my voice low and tell the person beside me what I suspect, "
            "then wait for an answer."
        )
    },
    {"choice": 1},
    {"choice": 1},
    {
        "text": (
            "I search this place carefully for anything that was moved or left "
            "behind."
        )
    },
    {"choice": 1},
    {"choice": 1},
    {"text": "I let an hour pass while I rest and watch who comes and goes."},
    {"choice": 1},
]

REPO_ROOT = Path(__file__).resolve().parents[1]

_REJECTION_LINE = re.compile(
    r"structured-output rejected "
    r"transport=(?P<transport>\S+) "
    rf"model={re.escape(MODEL_UNDER_TEST)} "
    r"seat=(?P<seat>\S+) "
    r"attempt=(?P<attempt>\d+) "
    r"exception=(?P<exception>\S+) "
    r"stop_reason=(?P<stop_reason>\S+) "
    r"block_types=(?P<block_types>\S+) "
    r"output_tokens=(?P<output_tokens>\S+) "
    r"error=(?P<error>.*)$"
)

# Error-message prefixes, from scripts/api_anthropic.py, in match order.
_ERROR_CLASSES: tuple[tuple[str, str], ...] = (
    ("Anthropic structured response did not include JSON output", "empty_native"),
    (
        "Anthropic prompted structured response did not include text output",
        "empty_prompted",
    ),
    ("Anthropic tool-envelope response did not include", "missing_tool"),
    (
        "Anthropic structured response stopped at the output-token limit",
        "max_tokens",
    ),
    ("Anthropic structured response was a refusal", "refusal"),
)


@dataclass(frozen=True)
class Rejection:
    """One Fable ``structured-output rejected`` gateway log line."""

    transport: str
    seat: str
    attempt: int
    exception: str
    stop_reason: str
    block_types: str
    output_tokens: str
    error: str


@dataclass(frozen=True)
class TurnWindow:
    """The UTC wall-clock window of one probe turn."""

    index: int
    start: datetime
    end: datetime


def probe_lane() -> int:
    """Return the gateway lane from ``NEXUS_GATEWAY_PORT``; never a default.

    Raises ``RuntimeError`` when the variable is unset, not an integer, or one
    of the owner's runtime ports, 8002 (player) and 8003 (operator).
    """

    raw = os.environ.get("NEXUS_GATEWAY_PORT")
    if raw is None or not raw.strip():
        raise RuntimeError(
            "NEXUS_GATEWAY_PORT is unset; the #845 probe runs only on the lane "
            "the coordinator assigns"
        )
    try:
        lane = int(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"NEXUS_GATEWAY_PORT={raw!r} is not an integer port"
        ) from exc
    if lane in OWNER_GATEWAY_PORTS:
        raise RuntimeError(
            f"NEXUS_GATEWAY_PORT={lane} is the owner's runtime port; the #845 "
            "probe never binds it"
        )
    return lane


def preflight(settings: Settings, lane: int) -> None:
    """Refuse the run, before any clone or paid call, off the shipped arm.

    Each failed condition raises ``RuntimeError`` naming it.
    """

    if os.environ.get("NEXUS_RUNTIME_CONFIG"):
        raise RuntimeError(
            "NEXUS_RUNTIME_CONFIG is set; the #845 arm is the shipped nexus.toml"
        )
    apex = settings.apex
    if apex.turn_pipeline != "two_pass":
        raise RuntimeError(
            f"apex.turn_pipeline is {apex.turn_pipeline!r}, not 'two_pass'"
        )
    if apex.anthropic_storyteller_transport != "prompted":
        raise RuntimeError(
            "apex.anthropic_storyteller_transport is "
            f"{apex.anthropic_storyteller_transport!r}, not 'prompted'"
        )
    if apex.gaia_model is not None:
        raise RuntimeError(
            f"apex.gaia_model is {apex.gaia_model!r}; Gaia must follow the slot"
        )
    provider = settings.provider_for_model(MODEL_UNDER_TEST)
    if provider != "anthropic":
        raise RuntimeError(
            f"{MODEL_UNDER_TEST} resolves to provider {provider!r}, not 'anthropic'"
        )
    if not settings.usage.enabled:
        raise RuntimeError(
            "usage.enabled is false; the probe counts calls from the usage ledger"
        )
    check = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{lane}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
    )
    if check.returncode != 1:
        raise RuntimeError(
            f"lane {lane} is busy or lsof failed (exit {check.returncode}): "
            f"{check.stdout}{check.stderr}"
        )


def parse_rejection_lines(text: str) -> list[Rejection]:
    """Parse every Fable ``structured-output rejected`` line in ``text``.

    A line carrying both markers that the format regex does not match raises
    ``RuntimeError``: the log format and the parser have drifted apart.
    """

    rejections: list[Rejection] = []
    for line in text.splitlines():
        if (
            "structured-output rejected transport=" not in line
            or f"model={MODEL_UNDER_TEST}" not in line
        ):
            continue
        match = _REJECTION_LINE.search(line)
        if match is None:
            raise RuntimeError(f"Unparseable rejection line: {line!r}")
        rejections.append(
            Rejection(
                transport=match["transport"],
                seat=match["seat"],
                attempt=int(match["attempt"]),
                exception=match["exception"],
                stop_reason=match["stop_reason"],
                block_types=match["block_types"],
                output_tokens=match["output_tokens"],
                error=match["error"],
            )
        )
    return rejections


def _parse_ts(event: UsageEvent) -> datetime:
    return datetime.fromisoformat(event.ts.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def read_ledger(usage_dir: Path, since: datetime, until: datetime) -> list[UsageEvent]:
    """Read every usage event, of every provider and model, since ``since``.

    Reads ``usage-<day>.jsonl`` for each UTC day from ``since`` to ``until``
    and validates each line with ``UsageEvent``; a day without a file has no
    events.
    """

    events: list[UsageEvent] = []
    day = since.astimezone(timezone.utc).date()
    last = until.astimezone(timezone.utc).date()
    while day <= last:
        path = usage_dir / f"usage-{day.isoformat()}.jsonl"
        if path.exists():
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                event = UsageEvent.model_validate(json.loads(line))
                if _parse_ts(event) >= since:
                    events.append(event)
        day += timedelta(days=1)
    return events


def fable_events(events: Iterable[UsageEvent]) -> list[UsageEvent]:
    """Keep the Anthropic events on the model under test."""

    return [
        event
        for event in events
        if event.provider == "anthropic" and event.model == MODEL_UNDER_TEST
    ]


def _block_types(rejection: Rejection) -> set[str]:
    if rejection.block_types == "none":
        return set()
    return set(rejection.block_types.split(","))


def error_class(error: str) -> str:
    """Classify one rejection's error text by its message family."""

    for prefix, name in _ERROR_CLASSES:
        if error.startswith(prefix):
            return name
    return "validation"


def is_flake(rejection: Rejection, klass: str) -> bool:
    """Whether a rejection shows the Decision 845-D1 symptom.

    (a) an empty native response on any seat; (b) an empty prompted response
    on the Gaia seat; (c) a ``max_tokens`` or ``refusal`` stop only where the
    extractor would have said "did not include" before 845-S1: native with
    neither a ``text`` nor a ``tool_use`` block, on any seat, or prompted
    with no ``text`` block, on the Gaia seat.
    """

    if klass == "empty_native":
        return True
    if klass == "empty_prompted":
        return rejection.seat == "gaia"
    if klass in ("max_tokens", "refusal"):
        blocks = _block_types(rejection)
        if rejection.transport == "native":
            return "text" not in blocks and "tool_use" not in blocks
        if rejection.transport == "prompted":
            return rejection.seat == "gaia" and "text" not in blocks
    return False


def is_text_bearing_stop(rejection: Rejection, klass: str) -> bool:
    """A ``max_tokens`` or ``refusal`` rejection carrying text or a tool call."""

    return klass in ("max_tokens", "refusal") and bool(
        _block_types(rejection) & {"text", "tool_use"}
    )


def _turn_for(ts: datetime, turn_windows: Sequence[TurnWindow]) -> Optional[int]:
    for window in turn_windows:
        if window.start <= ts <= window.end:
            return window.index
    return None


def join_attempts(
    events: Iterable[UsageEvent],
    rejections: Sequence[Rejection],
    turn_windows: Sequence[TurnWindow],
) -> list[dict[str, Any]]:
    """Join the Fable ledger events with the rejection lines, per seat.

    Per seat, the k-th ``rejected_validation`` event pairs with the k-th
    rejection line; unequal counts raise ``RuntimeError`` naming the seat.
    """

    fable = fable_events(events)
    rejected_events: dict[str, int] = Counter(
        event.seat for event in fable if event.outcome == "rejected_validation"
    )
    lines_by_seat: dict[str, list[Rejection]] = {}
    for rejection in rejections:
        lines_by_seat.setdefault(rejection.seat, []).append(rejection)
    for seat in sorted(set(rejected_events) | set(lines_by_seat)):
        event_count = rejected_events.get(seat, 0)
        line_count = len(lines_by_seat.get(seat, []))
        if event_count != line_count:
            raise RuntimeError(
                f"seat {seat}: {event_count} rejected_validation ledger events "
                f"but {line_count} rejection log lines"
            )

    taken: Counter[str] = Counter()
    attempts: list[dict[str, Any]] = []
    for event in fable:
        ts = _parse_ts(event)
        record: dict[str, Any] = {
            "turn": _turn_for(ts, turn_windows),
            "seat": event.seat,
            "attempt": event.attempt,
            "outcome": event.outcome,
            "input_tokens": event.input_tokens,
            "output_tokens": event.output_tokens,
            "ts": event.ts,
            "request_id": event.request_id,
            "transport": None,
            "stop_reason": None,
            "block_types": None,
            "exception": None,
            "error_class": None,
            "text_bearing_stop": False,
            "flake": False,
        }
        if event.outcome == "rejected_validation":
            rejection = lines_by_seat[event.seat][taken[event.seat]]
            taken[event.seat] += 1
            klass = error_class(rejection.error)
            record.update(
                transport=rejection.transport,
                stop_reason=rejection.stop_reason,
                block_types=rejection.block_types,
                exception=rejection.exception,
                error_class=klass,
                text_bearing_stop=is_text_bearing_stop(rejection, klass),
                flake=is_flake(rejection, klass),
            )
        attempts.append(record)
    return attempts


def completed_turns(turns: Iterable[dict[str, Any]]) -> int:
    """Count the turns whose CLI exited 0 and reported success."""

    return sum(
        1 for turn in turns if turn["exit_code"] == 0 and turn["success"] is True
    )


def verdict(attempts: Sequence[dict[str, Any]], turns_completed: int) -> str:
    """``reproduced``, ``null`` or ``incomplete`` (Decision 845-D1)."""

    if any(attempt["flake"] for attempt in attempts):
        return "reproduced"
    if turns_completed >= TURN_COUNT:
        return "null"
    return "incomplete"


def _table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append(
            "| " + " | ".join("" if cell is None else str(cell) for cell in row) + " |"
        )
    return lines


def _count_section(title: str, counts: Counter[Any]) -> list[str]:
    lines = [f"### {title}", ""]
    if not counts:
        return lines + ["None.", ""]
    rows = sorted(counts.items(), key=lambda item: str(item[0]))
    return lines + _table(["Key", "Count"], rows) + [""]


def write_evidence(
    evidence: Path,
    *,
    events_all: Sequence[UsageEvent],
    rejections: Sequence[Rejection],
    turns: Sequence[dict[str, Any]],
    turn_windows: Sequence[TurnWindow],
    stop_reason: str,
    worst: int,
) -> str:
    """Write the evidence files and return the verdict."""

    with (evidence / "ledger_all.jsonl").open("w") as handle:
        for event in events_all:
            handle.write(json.dumps(event.model_dump(mode="json")) + "\n")
    with (evidence / "turns.jsonl").open("w") as handle:
        for turn in turns:
            handle.write(json.dumps(turn) + "\n")
    attempts = join_attempts(events_all, rejections, turn_windows)
    with (evidence / "attempts.jsonl").open("w") as handle:
        for attempt in attempts:
            handle.write(json.dumps(attempt) + "\n")

    done = completed_turns(turns)
    result = verdict(attempts, done)
    fable_by_ts = sorted(fable_events(events_all), key=_parse_ts)
    fable_count = len(fable_by_ts)
    rejected = [a for a in attempts if a["outcome"] == "rejected_validation"]

    lines = [
        "# Issue #845 Fable Probe Summary",
        "",
        f"- Verdict: `{result}`",
        f"- Stop reason: `{stop_reason}`",
        f"- Turns completed: {done} of {TURN_COUNT}",
        f"- Worst case per turn (`worst`): {worst}",
        f"- Fable calls: {fable_count} against `CALL_CAP` {CALL_CAP}",
        f"- Excess over `CALL_CAP`: {max(0, fable_count - CALL_CAP)}",
        "",
        "## Turns",
        "",
    ]
    lines += _table(
        ["Turn", "Input", "Exit", "Success", "Code", "Session", "Seconds"],
        (
            (
                t["index"],
                t["input_kind"],
                t["exit_code"],
                t["success"],
                t["code"],
                t["session_id"],
                t["seconds"],
            )
            for t in turns
        ),
    )
    lines += ["", "## Fable Attempts", ""]
    lines += _table(
        [
            "Turn",
            "Seat",
            "Attempt",
            "Outcome",
            "In",
            "Out",
            "Transport",
            "Stop",
            "Blocks",
            "Exception",
            "Class",
            "Flake",
            "ts",
        ],
        (
            (
                a["turn"],
                a["seat"],
                a["attempt"],
                a["outcome"],
                a["input_tokens"],
                a["output_tokens"],
                a["transport"],
                a["stop_reason"],
                a["block_types"],
                a["exception"],
                a["error_class"],
                a["flake"],
                a["ts"],
            )
            for a in attempts
        ),
    )
    lines += ["", "## Counts", ""]
    lines += _count_section(
        "Fable Attempts by Seat and Outcome",
        Counter((a["seat"], a["outcome"]) for a in attempts),
    )
    lines += _count_section(
        "Fable Calls by Seat Outside Turn Windows",
        Counter(a["seat"] for a in attempts if a["turn"] is None),
    )
    lines += _count_section(
        "Fable Calls Beyond CALL_CAP by Seat",
        Counter(event.seat for event in fable_by_ts[CALL_CAP:]),
    )
    lines += _count_section(
        "Rejections by Error Class", Counter(a["error_class"] for a in rejected)
    )
    lines += _count_section(
        "Rejections by Flake", Counter(a["flake"] for a in rejected)
    )
    lines += _count_section(
        "Rejections by Stop Reason and Block Types",
        Counter((a["stop_reason"], a["block_types"]) for a in rejected),
    )
    lines += _count_section(
        "Text-Bearing max_tokens or refusal Rejections by Seat (Outside the Verdict)",
        Counter(a["seat"] for a in rejected if a["text_bearing_stop"]),
    )
    per_model: dict[tuple[str, str], list[int]] = {}
    for event in events_all:
        totals = per_model.setdefault((event.provider, event.model), [0, 0, 0])
        totals[0] += 1
        totals[1] += event.input_tokens or 0
        totals[2] += event.output_tokens or 0
    lines += ["### All Ledger Events by Provider and Model", ""]
    lines += _table(
        ["Provider", "Model", "Events", "Input tokens", "Output tokens"],
        (
            (provider, model, *totals)
            for (provider, model), totals in sorted(per_model.items())
        ),
    )
    lines.append("")
    (evidence / "summary.md").write_text("\n".join(lines))
    return result


def _json_object(text: str) -> dict[str, Any]:
    """The JSON object ``text`` holds, or the last indented one it ends with.

    The CLI prints its envelope with ``indent=2``, so it starts on a line that
    is exactly ``{``; log lines a failing child wrote to stderr come before it.
    """

    candidates = [text]
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line == "{"]
    if starts:
        candidates.append("\n".join(lines[starts[-1] :]))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def turn_outcome(exit_code: Optional[int], stdout: str, stderr: str) -> dict[str, Any]:
    """The ``success``, CLI ``code`` and ``session_id`` of one ``continue --json``.

    A successful run prints its result on stdout; a failed run prints the
    failure envelope on stderr (``nexus.cli.emit_error``). Only ``success``,
    ``code`` and ``session_id`` (or ``partial.session_id``) are kept, never
    ``error``, prose or choices. A timed-out run (exit code ``None``) has none.
    """

    if exit_code is None:
        return {"success": None, "code": None, "session_id": None}
    payload = _json_object(stdout if exit_code == 0 else stderr)
    session_id = payload.get("session_id")
    partial = payload.get("partial")
    if session_id is None and isinstance(partial, dict):
        session_id = partial.get("session_id")
    return {
        "success": payload.get("success"),
        "code": payload.get("code"),
        "session_id": session_id,
    }


def _clone_story_pins(dbname: str) -> tuple[Any, Any]:
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute("SELECT model, gaia_model FROM global_variables WHERE id = TRUE")
        row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"{dbname} has no global_variables row")
    return row[0], row[1]


def _run_turn(
    index: int,
    turn_input: dict[str, Any],
    *,
    dbname: str,
    timeout: float,
) -> tuple[dict[str, Any], TurnWindow]:
    argv = [
        sys.executable,
        "-m",
        "tests.slot_routed_cli",
        "--json",
        "continue",
        "--slot",
        str(ROUTED_SLOT),
    ]
    if "choice" in turn_input:
        argv += ["--choice", str(turn_input["choice"])]
        input_kind = "choice"
    else:
        argv += ["--text", turn_input["text"]]
        input_kind = "text"
    start = datetime.now(timezone.utc)
    started = time.monotonic()
    exit_code: Optional[int]
    stdout = stderr = ""
    try:
        completed = subprocess.run(
            argv,
            env={**os.environ, **routed_slot_environment(ROUTED_SLOT, dbname)},
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        exit_code = None
    else:
        exit_code = completed.returncode
        stdout, stderr = completed.stdout, completed.stderr
    seconds = round(time.monotonic() - started, 3)
    end = datetime.now(timezone.utc)
    record = {
        "index": index,
        "input_kind": input_kind,
        "exit_code": exit_code,
        **turn_outcome(exit_code, stdout, stderr),
        "seconds": seconds,
    }
    return record, TurnWindow(index=index, start=start, end=end)


def test_fable_two_pass_production_probe(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Play twelve Fable two-pass turns through the routed production gateway."""

    lane = probe_lane()
    settings = load_settings()
    preflight(settings, lane)
    worst = 2 * (settings.apex.structured_output_retries + 1)
    if settings.runtime is None:
        raise RuntimeError("nexus.toml has no [runtime] section")
    turn_timeout = (
        settings.runtime.cli.turn_request_timeout_seconds
        + settings.apex.generation_timeout_seconds
    )
    # The gateway child's own ledger directory; this process's recorder
    # config is patched to tmp_path by tests/conftest.py.
    usage_dir = usage_telemetry._load_recorder_config().usage_dir
    evidence = tmp_path_factory.mktemp("fable_845")
    print(f"845 probe evidence: {evidence}")
    api = f"http://127.0.0.1:{lane}"

    turns: list[dict[str, Any]] = []
    windows: list[TurnWindow] = []
    # Only a turn loop that runs to its end without a break completes the
    # run; a setup failure or an exception leaves an aborted label.
    stop_reason = "aborted"
    with disposable_slot_database(
        "qa640_845",
        source_db="save_04",
        include_data=True,
        story_pin=MODEL_UNDER_TEST,
    ) as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=ROUTED_SLOT, dbname=dbname)
        monkeypatch.setenv("NEXUS_SLOT", str(ROUTED_SLOT))
        monkeypatch.setenv("NARRATIVE_API_PORT", str(lane))
        monkeypatch.setenv("NEXUS_API_URL", api)
        model, gaia_model = _clone_story_pins(dbname)
        assert model == MODEL_UNDER_TEST, f"{evidence}: clone pins {model!r}"
        assert gaia_model is None, f"{evidence}: clone pins Gaia {gaia_model!r}"

        started_at = datetime.now(timezone.utc)
        log_path = evidence / "gateway.log"
        log_handle = log_path.open("w")
        server: Optional[subprocess.Popen] = None
        result = "incomplete"
        try:
            server = launch_routed_gateway(dbname, log_handle, store_access=True)
            _wait_health(api)
            state = requests.get(f"{api}/api/slot/{ROUTED_SLOT}/state", timeout=30)
            state.raise_for_status()
            state_body = state.json()
            if state_body["is_empty"] or state_body["is_wizard_mode"]:
                raise RuntimeError(
                    f"{evidence}: the clone is not a narrative story "
                    f"(is_empty={state_body['is_empty']}, "
                    f"is_wizard_mode={state_body['is_wizard_mode']})"
                )
            status = requests.get(
                f"{api}/api/story/new/retrograde/status",
                params={"slot": ROUTED_SLOT},
                timeout=30,
            )
            status.raise_for_status()
            run_status = status.json()["run_status"]
            if run_status not in (None, "done"):
                raise RuntimeError(
                    f"{evidence}: genesis run_status is {run_status!r}; "
                    "continue would make a transition call"
                )

            for index, turn_input in enumerate(TURN_INPUTS, start=1):
                spent = len(
                    fable_events(
                        read_ledger(usage_dir, started_at, datetime.now(timezone.utc))
                    )
                )
                if spent + worst > CALL_CAP:
                    stop_reason = "call_cap"
                    break
                record, window = _run_turn(
                    index, turn_input, dbname=dbname, timeout=turn_timeout
                )
                turns.append(record)
                windows.append(window)
                if record["exit_code"] is None:
                    stop_reason = "turn_timeout"
                    break
                if record["exit_code"] != 0 or record["success"] is not True:
                    stop_reason = "turn_failed"
                    break
            else:
                stop_reason = "completed"
        except BaseException as exc:
            stop_reason = f"aborted:{type(exc).__name__}"
            raise
        finally:
            if server is not None:
                server.terminate()
                try:
                    server.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    server.kill()
            log_handle.close()
            ended_at = datetime.now(timezone.utc)
            result = write_evidence(
                evidence,
                events_all=read_ledger(usage_dir, started_at, ended_at),
                rejections=parse_rejection_lines(log_path.read_text()),
                turns=turns,
                turn_windows=windows,
                stop_reason=stop_reason,
                worst=worst,
            )
            print(f"845 probe evidence: {evidence}")

    assert result == "null", (
        f"845 probe verdict {result!r} (stop_reason={stop_reason}); "
        f"evidence: {evidence}"
    )
