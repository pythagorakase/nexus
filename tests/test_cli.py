"""Tests for the NEXUS CLI helpers."""

import json
from pathlib import Path
import sys
from argparse import Namespace
from typing import Any, cast

import pytest
import requests
import tomlkit

from nexus import cli
from nexus.cli import _is_terminal_generation_status


REPO_CONFIG = Path(__file__).resolve().parents[1] / "nexus.toml"
LOG_LINE_COUNT_ERROR = "Log line count must be a positive integer"


def _write_runtime_log_config(tmp_path: Path, lines: list[str]) -> Path:
    """Write an isolated runtime config and its captured gateway log."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "gateway.log").write_text(
        "".join(f"{line}\n" for line in lines), encoding="utf-8"
    )

    document = tomlkit.parse(REPO_CONFIG.read_text(encoding="utf-8"))
    runtime = cast(Any, document["runtime"])
    runtime["state_dir"] = str(state_dir)
    config_path = tmp_path / "nexus.toml"
    config_path.write_text(tomlkit.dumps(document), encoding="utf-8")
    return config_path


class DummyResponse:
    """Minimal requests.Response double for CLI tests."""

    def __init__(
        self,
        payload: dict[str, Any],
        ok: bool = True,
        text: str = "",
        status_code: int = 200,
    ) -> None:
        self.payload = payload
        self.ok = ok
        self.text = text
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        """Return response JSON."""
        return self.payload

    def raise_for_status(self) -> None:
        """Mimic a successful HTTP response."""
        return None


def test_terminal_generation_statuses_include_api_and_incubator_values() -> None:
    """CLI polling should accept both progress and incubator completion states."""

    assert _is_terminal_generation_status("complete")
    assert _is_terminal_generation_status("completed")
    assert _is_terminal_generation_status("provisional")
    assert _is_terminal_generation_status("approved")
    assert _is_terminal_generation_status("committed")
    assert not _is_terminal_generation_status("processing")
    assert not _is_terminal_generation_status("error")


@pytest.mark.parametrize("day", ["02-30-2026", "2026-02-30", "2026-2-3"])
@pytest.mark.parametrize("as_json", [False, True])
def test_usage_invalid_day_exits_with_one_concise_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    day: str,
    as_json: bool,
) -> None:
    """Invalid usage days must not leak a traceback through the public CLI."""

    argv = ["nexus"]
    if as_json:
        argv.append("--json")
    argv.extend(["usage", "--day", day])
    monkeypatch.setattr(sys, "argv", argv)

    assert cli.main() == 1

    captured = capsys.readouterr()
    message = f"Usage day must be YYYY-MM-DD, got {day!r}"
    assert captured.out == ""
    if as_json:
        assert captured.err == json.dumps({"error": message}) + "\n"
    else:
        assert captured.err == f"Error: {message}\n"
    assert "Traceback" not in captured.out + captured.err


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("run_args", [[], ["--run", "isolated-run"]])
def test_usage_valid_empty_day_keeps_success_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    as_json: bool,
    run_args: list[str],
) -> None:
    """Valid usage queries read only the test-isolated empty ledger."""

    argv = ["nexus"]
    if as_json:
        argv.append("--json")
    argv.extend(["usage", "--day", "2026-02-28", *run_args])
    monkeypatch.setattr(sys, "argv", argv)

    assert cli.main() == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    if as_json:
        assert json.loads(captured.out) == {
            "success": True,
            "usage": {
                "allowance": {
                    "openai": {
                        "allowance": 2_500_000,
                        "remaining": 2_500_000,
                        "unknown_usage_events": 0,
                        "used": 0,
                    }
                },
                "day": "2026-02-28",
                "events": [],
                "openai_day_total": {
                    "total_tokens": 0,
                    "unknown_usage_events": 0,
                },
                "providers": {},
                "seats": {},
            },
        }
    else:
        assert captured.out == (
            "OpenAI API-reported tokens (UTC day 2026-02-28): 0\n"
            "openai allowance: 0 / 2,500,000 (remaining 2,500,000; "
            "unknown events 0)\n"
            "\n"
            "Providers:\n"
            "  (none)\n"
            "\n"
            "Seats:\n"
            "  (none)\n"
        )


def test_generation_poll_window_covers_live_reasoning_models() -> None:
    """The configured elapsed-time budget covers slow reasoning models."""

    assert cli._generation_timeout_seconds() >= 180


@pytest.mark.parametrize("count", (-2, -1, 0))
@pytest.mark.parametrize("as_json", (False, True), ids=("human", "json"))
def test_logs_rejects_non_positive_line_counts_before_reading_logs(
    count: int,
    as_json: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Invalid public counts fail before supervisor construction or log reads."""
    config_path = _write_runtime_log_config(tmp_path, ["must-not-be-emitted"])
    argv = ["nexus"]
    if as_json:
        argv.append("--json")
    argv.extend(
        ["logs", "gateway", "--config", str(config_path), "--lines", str(count)]
    )
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(
        cli,
        "_runtime_supervisor",
        lambda _args: pytest.fail("invalid count constructed the supervisor"),
    )

    assert cli.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "must-not-be-emitted" not in captured.err
    if as_json:
        assert json.loads(captured.err) == {"error": LOG_LINE_COUNT_ERROR}
    else:
        assert captured.err == f"Error: {LOG_LINE_COUNT_ERROR}\n"


@pytest.mark.parametrize("as_json", (False, True), ids=("human", "json"))
@pytest.mark.parametrize(
    "count,expected_count",
    ((1, 1), (None, 100), (5_000, 4_096)),
    ids=("one", "default", "larger-than-window"),
)
def test_logs_returns_requested_lines_within_retained_read_bound(
    count: int | None,
    expected_count: int,
    as_json: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Valid public counts retain exact tail and 256 KiB read-bound behavior."""
    log_lines = [f"log-{index:04d}".ljust(63, ".") for index in range(5_000)]
    config_path = _write_runtime_log_config(tmp_path, log_lines)
    argv = ["nexus"]
    if as_json:
        argv.append("--json")
    argv.extend(["logs", "gateway", "--config", str(config_path)])
    if count is not None:
        argv.extend(["--lines", str(count)])
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.delenv("NEXUS_GATEWAY_PORT", raising=False)

    assert cli.main() == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    if as_json:
        output_lines = json.loads(captured.out)["lines"]
    else:
        output_lines = captured.out.splitlines()
    assert output_lines == log_lines[-expected_count:]


def test_continue_posts_choice_to_backend_without_preapproving(
    monkeypatch,
) -> None:
    """The CLI should let /api/narrative/continue record and approve atomically."""
    posts: list[tuple[str, dict[str, Any]]] = []

    def fake_get(url: str, **kwargs: Any) -> DummyResponse:
        if url.endswith("/api/slot/5/state"):
            return DummyResponse(
                {
                    "is_empty": False,
                    "is_wizard_mode": False,
                    "has_pending": True,
                    "choices": ["Cross the street.", "Stay hidden."],
                    "model": None,
                }
            )
        if "/api/narrative/status/" in url:
            return DummyResponse({"status": "completed", "chunk_id": 2})
        raise AssertionError(f"Unexpected GET {url}")

    def fake_post(url: str, json: dict[str, Any], **kwargs: Any) -> DummyResponse:
        posts.append((url, json))
        if url.endswith("/api/narrative/approve"):
            raise AssertionError("CLI should not pre-approve pending narrative")
        if url.endswith("/api/narrative/continue"):
            return DummyResponse({"session_id": "session-2"})
        raise AssertionError(f"Unexpected POST {url}")

    monkeypatch.setattr(cli.requests, "get", fake_get)
    monkeypatch.setattr(cli.requests, "post", fake_post)
    monkeypatch.setattr(
        cli,
        "run_load",
        lambda args: {"message": "Next chunk", "choices": ["Continue."]},
    )

    result = cli.run_continue(
        Namespace(
            slot=5,
            model=None,
            user_text=None,
            choice=1,
            accept_fate=False,
            dev=False,
        )
    )

    assert result["success"] is True
    assert len(posts) == 1
    url, payload = posts[0]
    assert url.endswith("/api/narrative/continue")
    assert payload["choice"] == 1
    assert payload["accept_fate"] is False
    assert payload["user_text"] == ""


def test_free_text_trait_confirmation_exposes_wildcard_intro(monkeypatch) -> None:
    """Free-text trait submission should immediately return the next action."""
    posts: list[dict[str, Any]] = []

    def fake_get(url: str, **kwargs: Any) -> DummyResponse:
        assert url.endswith("/api/slot/5/state")
        return DummyResponse(
            {
                "is_empty": False,
                "is_wizard_mode": True,
                "phase": "character",
                "subphase": "traits",
                "trait_menu": [{"id": 1, "name": "allies"}],
                "can_confirm": True,
            }
        )

    def fake_post(url: str, json: dict[str, Any], **kwargs: Any) -> DummyResponse:
        assert url.endswith("/api/story/new/chat")
        posts.append(json)
        if len(posts) == 1:
            return DummyResponse(
                {
                    "message": "Generating artifact...",
                    "phase": "character",
                    "subphase": "wildcard",
                    "subphase_complete": True,
                    "phase_complete": False,
                    "artifact_type": "submit_trait_selection",
                }
            )
        return DummyResponse(
            {
                "message": "What singular gift or burden defines Mara?",
                "choices": ["A storm answers her anger."],
                "phase": "character",
            }
        )

    monkeypatch.setattr(cli.requests, "get", fake_get)
    monkeypatch.setattr(cli.requests, "post", fake_post)

    result = cli.run_continue(
        Namespace(
            slot=5,
            model=None,
            user_text="Exactly those three: 1, 2, 3.",
            choice=None,
            accept_fate=False,
            dev=False,
        )
    )

    assert result["success"] is True
    assert result["subphase_complete"] is True
    assert result["subphase"] == "wildcard"
    assert result["next_phase_intro"] == "What singular gift or burden defines Mara?"
    assert result["choices"] == ["A storm answers her anger."]
    assert len(posts) == 2
    assert posts[0]["message"] == "Exactly those three: 1, 2, 3."
    assert "Proceeding to wildcard" in posts[1]["message"]


def test_deterministic_trait_confirmation_exposes_wildcard_intro(monkeypatch) -> None:
    """Choice-based trait confirmation should retain its wildcard transition."""
    posts: list[dict[str, Any]] = []

    def fake_get(url: str, **kwargs: Any) -> DummyResponse:
        assert url.endswith("/api/slot/5/state")
        return DummyResponse(
            {
                "is_empty": False,
                "is_wizard_mode": True,
                "phase": "character",
                "subphase": "traits",
                "trait_menu": [{"id": 1, "name": "allies"}],
                "can_confirm": True,
            }
        )

    def fake_post(url: str, json: dict[str, Any], **kwargs: Any) -> DummyResponse:
        assert url.endswith("/api/story/new/chat")
        posts.append(json)
        if len(posts) == 1:
            return DummyResponse(
                {
                    "message": "Traits confirmed. Moving to wildcard definition.",
                    "phase": "character",
                    "subphase": "wildcard",
                    "subphase_complete": True,
                }
            )
        return DummyResponse(
            {
                "message": "Name the exception that makes Mara unforgettable.",
                "choices": ["She remembers futures that never happened."],
                "phase": "character",
            }
        )

    monkeypatch.setattr(cli.requests, "get", fake_get)
    monkeypatch.setattr(cli.requests, "post", fake_post)

    result = cli.run_continue(
        Namespace(
            slot=5,
            model=None,
            user_text=None,
            choice=0,
            accept_fate=False,
            dev=False,
        )
    )

    assert result["success"] is True
    assert result["subphase_complete"] is True
    assert result["subphase"] == "wildcard"
    assert result["next_phase_intro"] == (
        "Name the exception that makes Mara unforgettable."
    )
    assert result["choices"] == ["She remembers futures that never happened."]
    assert len(posts) == 2
    assert posts[0]["message"] == ""
    assert posts[0]["trait_choice"] == 0
    assert "Proceeding to wildcard" in posts[1]["message"]


def test_trait_confirmation_intro_failure_exposes_recovery(monkeypatch) -> None:
    """A failed wildcard intro must preserve success and name a retry command."""
    posts: list[dict[str, Any]] = []

    def fake_get(url: str, **kwargs: Any) -> DummyResponse:
        assert url.endswith("/api/slot/5/state")
        return DummyResponse(
            {
                "is_empty": False,
                "is_wizard_mode": True,
                "phase": "character",
                "subphase": "traits",
                "trait_menu": [{"id": 1, "name": "allies"}],
                "can_confirm": True,
            }
        )

    def fake_post(url: str, json: dict[str, Any], **kwargs: Any) -> DummyResponse:
        assert url.endswith("/api/story/new/chat")
        posts.append(json)
        if len(posts) == 1:
            return DummyResponse(
                {
                    "message": "Generating artifact...",
                    "phase": "character",
                    "subphase": "wildcard",
                    "subphase_complete": True,
                    "phase_complete": False,
                    "artifact_type": "submit_trait_selection",
                }
            )
        return DummyResponse(
            {},
            ok=False,
            text='{"detail":"Wildcard intro unavailable"}',
            status_code=503,
        )

    monkeypatch.setattr(cli.requests, "get", fake_get)
    monkeypatch.setattr(cli.requests, "post", fake_post)

    result = cli.run_continue(
        Namespace(
            slot=5,
            model=None,
            user_text="Exactly those three: 1, 2, 3.",
            choice=None,
            accept_fate=False,
            dev=False,
        )
    )

    recovery_command = (
        'nexus continue --slot 5 --user-text "Continue to the wildcard step."'
    )
    assert result["success"] is True
    assert result["intro_error"] == {
        "detail": '{"detail":"Wildcard intro unavailable"}',
        "status_code": 503,
    }
    assert result["intro_recovery_command"] == recovery_command
    assert "Traits were saved" in result["message"]
    assert recovery_command in result["message"]
    assert len(posts) == 2


def _stub_seed_completion_requests(
    monkeypatch,
    transition_response: DummyResponse | requests.exceptions.Timeout,
) -> None:
    """Stub the gateway boundary for a public seed-completion CLI command."""

    def fake_get(url: str, **kwargs: Any) -> DummyResponse:
        assert url.endswith("/api/slot/5/state")
        return DummyResponse(
            {
                "is_empty": False,
                "is_wizard_mode": True,
                "phase": "seed",
                "choices": ["Commit the final seed."],
            }
        )

    def fake_post(url: str, json: dict[str, Any], **kwargs: Any) -> DummyResponse:
        if url.endswith("/api/story/new/chat"):
            assert json["message"] == "Commit the final seed."
            return DummyResponse(
                {
                    "message": "The seed is saved.",
                    "phase": "seed",
                    "artifact_type": "story_seed",
                    "data": {"title": "The Glass Orchard"},
                    "phase_complete": True,
                }
            )
        if url.endswith("/api/story/new/transition"):
            if isinstance(transition_response, requests.exceptions.Timeout):
                raise transition_response
            return transition_response
        if url.endswith("/api/narrative/continue"):
            return DummyResponse(
                {
                    "storyteller_text": "Rain needles the orchard glass.",
                    "choices": ["Enter the gate."],
                    "chunk_id": 1,
                }
            )
        raise AssertionError(f"Unexpected POST {url}")

    monkeypatch.setattr(cli.requests, "get", fake_get)
    monkeypatch.setattr(cli.requests, "post", fake_post)


@pytest.mark.parametrize(
    "status_code,requests_ok", [(300, True), (400, False), (422, False), (500, False)]
)
def test_seed_completion_transition_http_failure_exits_nonzero_with_retry(
    monkeypatch, capsys, status_code: int, requests_ok: bool
) -> None:
    """A persisted seed cannot make a failed atomic transition look successful.

    requests.Response.ok is True for any status < 400, so a 3xx must fail
    the strict 2xx contract even while ok=True.
    """
    detail = f'{{"detail":"Atomic transition failed with {status_code}"}}'
    _stub_seed_completion_requests(
        monkeypatch,
        DummyResponse({}, ok=requests_ok, text=detail, status_code=status_code),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["nexus", "--json", "continue", "--slot", "5", "--choice", "1"],
    )

    assert cli.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["success"] is False
    assert payload["phase_complete"] is True
    assert payload["artifact_type"] == "story_seed"
    assert payload["artifact_data"] == {"title": "The Glass Orchard"}
    assert payload["transition_error"] == {
        "status": "http_error",
        "status_code": status_code,
        "detail": detail,
    }
    assert payload["retry_command"] == "nexus continue --slot 5"
    assert payload["retry_command"] in payload["error"]


def test_seed_completion_transition_timeout_exits_nonzero_with_retry(
    monkeypatch, capsys
) -> None:
    """A transition timeout reports the saved seed and an explicit retry."""
    _stub_seed_completion_requests(
        monkeypatch,
        requests.exceptions.Timeout("Transition timed out after 900 seconds."),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["nexus", "--json", "continue", "--slot", "5", "--choice", "1"],
    )

    assert cli.main() == 1

    payload = json.loads(capsys.readouterr().err)
    assert payload["success"] is False
    assert payload["phase_complete"] is True
    assert payload["artifact_data"] == {"title": "The Glass Orchard"}
    assert payload["transition_error"] == {
        "status": "timeout",
        "status_code": None,
        "detail": "Transition timed out after 900 seconds.",
    }
    assert payload["retry_command"] == "nexus continue --slot 5"


def test_seed_completion_success_transitions_and_bootstraps_narrative(
    monkeypatch, capsys
) -> None:
    """A successful transition retains the seed and reports narrative success."""
    _stub_seed_completion_requests(
        monkeypatch,
        DummyResponse({"retrograde": {"status": "complete"}}),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["nexus", "--json", "continue", "--slot", "5", "--choice", "1"],
    )

    assert cli.main() == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["success"] is True
    assert payload["phase_complete"] is True
    assert payload["artifact_data"] == {"title": "The Glass Orchard"}
    assert payload["retrograde"] == {"status": "complete"}
    assert payload["narrative_bootstrap"] is True
    assert payload["next_phase_intro"] == "Rain needles the orchard glass."
    assert payload["phase"] is None


@pytest.mark.parametrize("confirmation_path", ["free-text", "deterministic"])
def test_plain_continue_after_trait_confirmation_stays_local(
    monkeypatch, confirmation_path: str
) -> None:
    """Neither trait-confirmation route may lead to an empty provider message."""

    def fake_get(url: str, **kwargs: Any) -> DummyResponse:
        assert url.endswith("/api/slot/5/state")
        return DummyResponse(
            {
                "is_empty": False,
                "is_wizard_mode": True,
                "phase": "character",
                "subphase": "wildcard",
                "choices": ["Define Mara's impossible inheritance."],
                "confirmation_path": confirmation_path,
            }
        )

    def fail_post(*args: Any, **kwargs: Any) -> DummyResponse:
        raise AssertionError("Plain wizard continue must not make an API POST")

    monkeypatch.setattr(cli.requests, "get", fake_get)
    monkeypatch.setattr(cli.requests, "post", fail_post)

    result = cli.run_continue(
        Namespace(
            slot=5,
            model=None,
            user_text=None,
            choice=None,
            accept_fate=False,
            dev=False,
        )
    )

    assert result == {
        "success": False,
        "error": "Wizard continue requires non-empty text, --choice, or --accept-fate.",
    }


class FakeWizardCache:
    """Wizard cache double with a complete character draft."""

    def get_character_dict(self) -> dict[str, Any]:
        """Return enough character data to assemble a CharacterSheet."""

        return {
            "concept": {
                "name": "Mara",
                "archetype": "wary operator with complicated loyalties",
                "background": (
                    "Mara has survived by cultivating favors and avoiding "
                    "easy debts in a city that records every promise."
                ),
                "appearance": (
                    "Lean, watchful, and dressed for quick departures from "
                    "dangerous rooms."
                ),
                "suggested_traits": ["resources", "status", "allies"],
                "trait_rationales": {
                    "resources": "Her money opens doors but paints a target.",
                    "status": "Her badge matters in one narrow hierarchy.",
                    "allies": "Her old crew still answers when she calls.",
                },
            },
            "trait_selection": {
                "selected_traits": ["resources", "status", "allies"],
                "trait_rationales": {
                    "resources": "Her money opens doors but paints a target.",
                    "status": "Her badge matters in one narrow hierarchy.",
                    "allies": "Her old crew still answers when she calls.",
                },
                "suggested_by_llm": ["resources", "status", "allies"],
            },
            "wildcard": {
                "wildcard_name": "Storm Marked",
                "wildcard_description": (
                    "Lightning follows her in ways nobody can explain, "
                    "turning quiet rooms into omens."
                ),
            },
        }


class FakeRetrogradeWizardCache:
    """Wizard cache double with complete Retrograde packet inputs."""

    def current_phase(self) -> str:
        return "ready"

    def get_setting_dict(self) -> dict[str, Any]:
        return {
            "genre": "cyberpunk",
            "secondary_genres": [],
            "world_name": "Glass District",
        }

    def get_character_dict(self) -> dict[str, Any]:
        return {
            "concept": {
                "name": "Mara",
                "archetype": "wary operator",
                "background": "Mara survives by tracking debts.",
            },
            "trait_selection": {
                "selected_traits": ["resources"],
                "trait_rationales": {"resources": "Money opens doors."},
            },
            "wildcard": {
                "wildcard_name": "Storm Marked",
                "wildcard_description": "Weather notices her.",
            },
        }

    def get_seed_dict(self) -> dict[str, Any]:
        return {
            "seed_type": "inciting pressure",
            "title": "The Ledger Wakes",
            "situation": "An old debt becomes active.",
            "hook": "A message arrives in a dead person's voice.",
            "immediate_goal": "Find who sent it.",
            "stakes": "Mara's safe names may burn.",
            "tension_source": "A sponsor wants the secret first.",
            "key_npcs": ["Vale"],
            "secrets": "The debt was never hers.",
        }

    def get_layer_dict(self) -> dict[str, Any]:
        return {"name": "Night City", "type": "urban"}

    def get_zone_dict(self) -> dict[str, Any]:
        return {"name": "The Mall", "summary": "Commerce and surveillance."}

    def get_initial_location(self) -> dict[str, Any]:
        return {"name": "Shutter Hall", "description": "A quiet mall corridor."}


class FakeConnection:
    """Context-manager connection double for dry-run compiler tests."""

    def __enter__(self) -> "FakeConnection":
        """Enter connection context."""

        return self

    def __exit__(self, *args: Any) -> None:
        """Exit connection context."""

        return None

    def cursor(self) -> "FakeCursor":
        """Return a context-manager cursor double."""

        return FakeCursor()


class FakeCursor:
    """Cursor double for remainder-only compiler paths."""

    # All traits in FakeWizardCache hit remainder paths before SQL. If that
    # changes, this double needs an execute() stub or a real trait cursor fake.

    def __enter__(self) -> "FakeCursor":
        """Enter cursor context."""

        return self

    def __exit__(self, *args: Any) -> None:
        """Exit cursor context."""

        return None


def test_trait_audit_reports_prose_only_remainders(monkeypatch) -> None:
    """The CLI audit should expose dry-run compiler remainders from cache."""

    from nexus.api import db_pool, new_story_cache

    monkeypatch.setattr(new_story_cache, "read_cache", lambda dbname: FakeWizardCache())
    monkeypatch.setattr(db_pool, "get_connection", lambda dbname: FakeConnection())

    result = cli.run_trait_audit(
        Namespace(
            slot=5,
            trait_inputs=None,
            character_id=0,
            character_entity_id=0,
            fail_on_remainders=False,
        )
    )

    assert result["success"] is True
    assert result["character_name"] == "Mara"
    assert result["traits"] == ["resources", "status", "allies"]
    assert result["trait_audit"]["dry_run"] is True
    assert result["trait_audit"]["counters"]["prose_only_remainders"] == 3
    assert result["failed_policy"] is False


def test_trait_audit_rejects_non_object_trait_inputs() -> None:
    """Trait input overrides must be a JSON object."""

    result = cli.run_trait_audit(
        Namespace(
            slot=5,
            trait_inputs="[1, 2, 3]",
            character_id=0,
            character_entity_id=0,
            fail_on_remainders=False,
        )
    )

    assert result["success"] is False
    assert "--trait-inputs must be a JSON object" in result["error"]


def test_trait_audit_fail_on_remainders_sets_policy_failure(monkeypatch) -> None:
    """Automation loops can request a nonzero status on prose-only fallback."""

    from nexus.api import db_pool, new_story_cache

    monkeypatch.setattr(new_story_cache, "read_cache", lambda dbname: FakeWizardCache())
    monkeypatch.setattr(db_pool, "get_connection", lambda dbname: FakeConnection())

    result = cli.run_trait_audit(
        Namespace(
            slot=5,
            trait_inputs=None,
            character_id=0,
            character_entity_id=0,
            fail_on_remainders=True,
        )
    )

    assert result["success"] is True
    assert result["failed_policy"] is True


def test_main_trait_audit_policy_failure_keeps_output(monkeypatch, capsys) -> None:
    """Policy failures should still print the audit payload for callers."""

    monkeypatch.setattr(
        sys,
        "argv",
        ["nexus", "trait-audit", "--slot", "5", "--fail-on-remainders"],
    )
    monkeypatch.setattr(
        cli,
        "run_trait_audit",
        lambda args: {
            "success": True,
            "message": "Trait compiler audit for slot 5 (dry run).",
            "traits": ["resources"],
            "trait_audit": {
                "counters": {
                    "applied_single_entity_tags": 0,
                    "applied_pair_tags": 0,
                    "created_entities": 0,
                    "created_relationships": 0,
                    "prose_only_remainders": 1,
                },
                "prose_only_remainders": [
                    {
                        "trait": "resources",
                        "reason_code": "missing_structured_trait_input",
                        "message": "Missing input.",
                    }
                ],
            },
            "failed_policy": True,
        },
    )

    assert cli.main() == 1
    captured = capsys.readouterr()
    assert "Trait compiler audit for slot 5" in captured.out
    assert "resources: missing_structured_trait_input" in captured.out


def test_print_trait_audit_renders_pending_stub_endpoints(capsys) -> None:
    """Dry-run rows with pending stubs print names instead of null ids."""

    cli._print_trait_audit(
        {
            "character_name": "Mara",
            "traits": ["domain", "patron", "dependents"],
            "trait_audit": {
                "counters": {
                    "applied_single_entity_tags": 0,
                    "applied_pair_tags": 2,
                    "created_entities": 2,
                    "created_relationships": 1,
                    "prose_only_remainders": 0,
                },
                "applied_pair_tags": [
                    {
                        "trait": "domain",
                        "tag": "claims",
                        "subject_entity_id": 501,
                        "object_entity_id": None,
                        "object_name": "Hollow Spire",
                    },
                    {
                        "trait": "patron",
                        "tag": "sponsors",
                        "subject_entity_id": None,
                        "subject_name": "Magistrate Hale",
                        "object_entity_id": 501,
                    },
                ],
                "created_entities": [
                    {
                        "trait": "domain",
                        "entity_kind": "place",
                        "entity_id": None,
                        "name": "Hollow Spire",
                    },
                    {
                        "trait": "patron",
                        "entity_kind": "character",
                        "entity_id": 1042,
                        "name": "Magistrate Hale",
                    },
                ],
                "created_relationships": [
                    {
                        "trait": "patron",
                        "character1_id": 1,
                        "character2_id": None,
                        "character2_name": "Magistrate Hale",
                        "relationship_type": "patron",
                        "emotional_valence": "+2|friendly",
                    }
                ],
            },
        }
    )

    captured = capsys.readouterr()
    assert "domain: claims 501 -> (pending stub) Hollow Spire" in captured.out
    assert "patron: sponsors (pending stub) Magistrate Hale -> 501" in captured.out
    assert "domain: place entity pending (Hollow Spire)" in captured.out
    assert "patron: character entity 1042 (Magistrate Hale)" in captured.out
    assert (
        "patron: character 1 -> (pending stub) Magistrate Hale "
        "(patron, +2|friendly)" in captured.out
    )


def test_retrograde_packet_writes_dry_run_packet(monkeypatch, tmp_path) -> None:
    """The CLI Retrograde packet command is read-only except optional output JSON."""

    from nexus.agents.orrery import retrograde_vocabulary
    from nexus.api import new_story_cache

    real_enumerator = retrograde_vocabulary.enumerate_seed_eligible_vocabulary
    output_path = tmp_path / "retrograde_packet.json"
    monkeypatch.setattr(
        new_story_cache,
        "read_cache",
        lambda dbname: FakeRetrogradeWizardCache(),
    )
    monkeypatch.setattr(
        retrograde_vocabulary,
        "enumerate_seed_eligible_vocabulary",
        lambda dbname: real_enumerator(),
    )

    result = cli.run_retrograde_packet(
        Namespace(
            slot=5,
            weird="medium",
            weird_raw=None,
            output=output_path,
        )
    )

    packet = json.loads(output_path.read_text(encoding="utf-8"))

    assert result["success"] is True
    assert result["packet_output"] == str(output_path)
    assert packet["dry_run"] is True
    assert packet["mutation_policy"]["writes"] == "none"
    assert packet["weird"]["level"] == "medium"
    assert packet["seed_generation_request"]["mutation_policy"]["writes"] == "none"
    assert "candidate_response_schema" in packet["seed_generation_request"]
    assert "RETROGRADE_SEED_GENERATION_REQUEST" in packet["seed_generation_prompt"]


def test_retrograde_seed_candidates_reads_packet_and_writes_response(
    monkeypatch,
    tmp_path,
) -> None:
    """The Skald seed command can run from a saved packet without slot cache."""

    from nexus.agents.orrery import retrograde_seed_candidates

    packet_path = tmp_path / "packet.json"
    output_path = tmp_path / "seed_candidates.json"
    packet = {
        "seed_generation_request": {"budget": {"select_target": 1}},
        "seed_eligible_vocabulary": {
            "entity_kinds": ["character", "place"],
            "registered_single_entity_tags": [],
            "registered_tags_by_seed_policy": {},
            "multi_entity_tag_definitions": [],
            "event_types": [],
            "relationship_types": [],
        },
        "seed_generation_prompt": "prompt",
    }
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    calls = []

    def fake_generate(
        *,
        packet: dict[str, Any],
        model_name: str | None,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        calls.append((packet, model_name, max_tokens))
        return {
            "model": model_name,
            "prompt_chars": 6,
            "seed_candidate_response": {
                "schema_version": "orrery_retrograde_seed_candidates.v0",
                "candidates": [],
                "selected_seed_ids": [],
                "rejected_seed_ids": [],
            },
        }

    monkeypatch.setattr(
        retrograde_seed_candidates,
        "run_seed_stage",
        fake_generate,
    )

    result = cli.run_retrograde_seed_candidates(
        Namespace(
            slot=None,
            packet=packet_path,
            weird=None,
            weird_raw=None,
            packet_output=None,
            model="TEST",
            max_tokens=12000,
            output=output_path,
        )
    )

    written = json.loads(output_path.read_text(encoding="utf-8"))

    assert result["success"] is True
    assert result["packet_input"] == str(packet_path)
    assert result["packet_output"] is None
    assert result["candidate_output"] == str(output_path)
    assert calls == [(packet, "TEST", 12000)]
    assert written["model"] == "TEST"


def test_retrograde_expand_seeds_reads_inputs_and_writes_response(
    monkeypatch,
    tmp_path,
) -> None:
    """The R6 expansion command can run from saved packet/candidate artifacts."""

    from nexus.agents.orrery import retrograde_expansion

    packet_path = tmp_path / "packet.json"
    candidates_path = tmp_path / "seed_candidates.json"
    output_path = tmp_path / "expansion.json"
    packet = {
        "seed_generation_request": {"budget": {"select_target": 1}},
        "seed_eligible_vocabulary": {
            "entity_kinds": ["character", "place"],
            "registered_single_entity_tags": [],
            "registered_tags_by_seed_policy": {},
            "multi_entity_tag_definitions": [],
            "event_types": [],
            "relationship_types": [],
        },
    }
    candidates = {
        "seed_candidate_response": {
            "schema_version": "orrery_retrograde_seed_candidates.v0",
            "candidates": [],
            "selected_seed_ids": [],
            "rejected_seed_ids": [],
        }
    }
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
    calls = []

    def fake_generate(
        *,
        packet: dict[str, Any],
        seed_candidate_response: dict[str, Any],
        model_name: str | None,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        calls.append((packet, seed_candidate_response, model_name, max_tokens))
        return {
            "model": model_name,
            "prompt_chars": 8,
            "retrograde_expansion_plan": {
                "schema_version": "orrery_retrograde_expansion_plan.v0",
                "selected_seed_ids": ["seed_001"],
                "event_plan": [],
                "entity_tag_plan": [],
                "pair_tag_plan": [],
                "relationship_plan": [],
                "thread_plan": [],
                "coverage_notes": [],
                "commit_readiness": {"writes": "none"},
            },
        }

    monkeypatch.setattr(
        retrograde_expansion,
        "generate_expansion_with_skald",
        fake_generate,
    )

    result = cli.run_retrograde_expand_seeds(
        Namespace(
            packet=packet_path,
            seed_candidates=candidates_path,
            model="TEST",
            max_tokens=12000,
            output=output_path,
        )
    )

    written = json.loads(output_path.read_text(encoding="utf-8"))

    assert result["success"] is True
    assert result["packet_input"] == str(packet_path)
    assert result["candidate_input"] == str(candidates_path)
    assert result["expansion_output"] == str(output_path)
    assert calls == [
        (
            packet,
            candidates["seed_candidate_response"],
            "TEST",
            12000,
        )
    ]
    assert written["model"] == "TEST"


class FakeApplyCursor:
    """Cursor double for apply-style CLI commands."""

    def __enter__(self) -> "FakeApplyCursor":
        """Enter cursor context."""

        return self

    def __exit__(self, *args: Any) -> None:
        """Exit cursor context."""

        return None

    def execute(self, sql: str, *args: Any) -> None:
        """Accept read-only transaction setup."""

        if "SET TRANSACTION READ ONLY" not in sql:
            raise AssertionError(f"Unexpected SQL: {sql}")


class FakeApplyConnection:
    """Connection double with an apply-capable cursor."""

    def __enter__(self) -> "FakeApplyConnection":
        """Enter connection context."""

        return self

    def __exit__(self, *args: Any) -> None:
        """Exit connection context."""

        return None

    def cursor(self) -> FakeApplyCursor:
        """Return a cursor double."""

        return FakeApplyCursor()


def test_retrograde_apply_expansion_dry_runs_saved_artifacts(
    monkeypatch,
    tmp_path,
) -> None:
    """The persistence command forwards the dedicated-summary contract."""

    from nexus.agents.orrery import retrograde_persistence
    from nexus.api import db_pool

    packet_path = tmp_path / "packet.json"
    candidates_path = tmp_path / "seed_candidates.json"
    expansion_path = tmp_path / "expansion.json"
    output_path = tmp_path / "persistence.json"
    packet = {"seed_generation_request": {"budget": {"select_target": 1}}}
    candidates = {
        "seed_candidate_response": {
            "schema_version": "orrery_retrograde_seed_candidates.v0",
            "candidates": [],
            "selected_seed_ids": [],
            "rejected_seed_ids": [],
        }
    }
    expansion = {
        "retrograde_expansion_generation": {
            "retrograde_expansion_plan": {
                "schema_version": "orrery_retrograde_expansion_plan.v0",
                "selected_seed_ids": [],
                "event_plan": [],
                "entity_tag_plan": [],
                "pair_tag_plan": [],
                "relationship_plan": [],
                "thread_plan": [],
            }
        }
    }
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
    expansion_path.write_text(json.dumps(expansion), encoding="utf-8")
    calls = []

    def fake_build(
        cur: Any,
        *,
        packet: dict[str, Any],
        seed_candidate_response: dict[str, Any],
        expansion_plan_payload: dict[str, Any],
        slot: int,
        dbname: str,
        dry_run: bool,
        create_missing_entities: bool,
        summaries_enabled: bool,
        recorded_at_chunk_id: int,
        epistemics_settings: Any,
    ) -> dict[str, Any]:
        calls.append(
            (
                packet,
                seed_candidate_response,
                expansion_plan_payload,
                slot,
                dbname,
                dry_run,
                create_missing_entities,
                summaries_enabled,
                recorded_at_chunk_id,
                epistemics_settings.enabled,
            )
        )
        return {
            "schema_version": "orrery_retrograde_persistence_plan.v0",
            "dry_run": dry_run,
            "slot": slot,
            "dbname": dbname,
            "counters": {"events_would_insert": 0},
            "execute_blockers": [],
            "retrieval": {"embedding_pending_summary_ids": []},
        }

    monkeypatch.setattr(
        db_pool, "get_connection", lambda *args, **kwargs: FakeApplyConnection()
    )
    monkeypatch.setattr(
        retrograde_persistence,
        "build_retrograde_persistence_plan",
        fake_build,
    )
    monkeypatch.setattr(
        retrograde_persistence,
        "find_latest_playable_chunk_id",
        lambda cur: 147,
    )

    result = cli.run_retrograde_apply_expansion(
        Namespace(
            slot=5,
            packet=packet_path,
            seed_candidates=candidates_path,
            expansion=expansion_path,
            execute=False,
            create_stubs=True,
            output=output_path,
        )
    )

    written = json.loads(output_path.read_text(encoding="utf-8"))

    assert result["success"] is True
    assert result["persistence_output"] == str(output_path)
    assert result["retrograde_persistence"]["dry_run"] is True
    assert written["schema_version"] == "orrery_retrograde_persistence_plan.v0"
    assert calls == [
        (
            packet,
            candidates["seed_candidate_response"],
            expansion["retrograde_expansion_generation"]["retrograde_expansion_plan"],
            5,
            "save_05",
            True,
            True,
            True,
            147,
            True,
        )
    ]


def test_retrograde_embed_history_executes_and_embeds(monkeypatch) -> None:
    """Execute mode creates and embeds pending dedicated summaries."""

    from nexus.agents.orrery import retrograde_embedding, retrograde_persistence
    from nexus.api import db_pool

    plan_calls = []
    embed_calls = []
    summary_rows = [
        {
            "event_ref": "r6_e01",
            "world_event_id": 107,
            "source_status": "persisted",
            "status": "inserted",
            "summary_id": 72,
            "embedding_pending": True,
        },
        {
            "event_ref": "r6_e02",
            "world_event_id": 108,
            "source_status": "persisted",
            "status": "already_present",
            "summary_id": 73,
            "embedding_pending": False,
        },
    ]

    def fake_plan(cur: Any, *, dry_run: bool) -> Any:
        plan_calls.append(dry_run)
        return summary_rows

    def fake_embed(dbname: str, summary_ids: Any) -> Any:
        embed_calls.append((dbname, list(summary_ids)))
        return [{"summary_id": 72, "job_id": "embed_72_test"}]

    monkeypatch.setattr(
        db_pool, "get_connection", lambda *args, **kwargs: FakeApplyConnection()
    )
    monkeypatch.setattr(
        retrograde_persistence,
        "plan_retrograde_summaries",
        fake_plan,
    )
    monkeypatch.setattr(
        retrograde_embedding,
        "embed_retrograde_summaries",
        fake_embed,
    )

    result = cli.run_retrograde_embed_history(Namespace(slot=5, execute=True))

    assert result["success"] is True
    sync = result["retrograde_embed_history"]
    assert sync["dry_run"] is False
    assert sync["embedding_pending_summary_ids"] == [72]
    assert sync["embedding_results"] == [{"summary_id": 72, "job_id": "embed_72_test"}]
    assert plan_calls == [False]
    assert embed_calls == [("save_05", [72])]


def test_retrograde_embed_history_dry_run_skips_embedding(monkeypatch) -> None:
    """Dry-run mode never reaches the summary embedding lifecycle."""

    from nexus.agents.orrery import retrograde_embedding, retrograde_persistence
    from nexus.api import db_pool

    def fake_plan(cur: Any, *, dry_run: bool) -> Any:
        return [
            {
                "event_ref": "r6_e01",
                "world_event_id": 107,
                "source_status": "persisted",
                "status": "would_insert",
                "summary_id": None,
                "embedding_pending": True,
            }
        ]

    def fail_embed(dbname: str, summary_ids: Any) -> Any:
        raise AssertionError("dry run must not embed")

    monkeypatch.setattr(
        db_pool, "get_connection", lambda *args, **kwargs: FakeApplyConnection()
    )
    monkeypatch.setattr(
        retrograde_persistence,
        "plan_retrograde_summaries",
        fake_plan,
    )
    monkeypatch.setattr(
        retrograde_embedding,
        "embed_retrograde_summaries",
        fail_embed,
    )

    result = cli.run_retrograde_embed_history(Namespace(slot=5, execute=False))

    assert result["success"] is True
    sync = result["retrograde_embed_history"]
    assert sync["dry_run"] is True
    assert sync["embedding_pending_summary_ids"] == []
    assert sync["embedding_results"] == []


def test_retrograde_embed_history_reports_planner_runtime_error(monkeypatch) -> None:
    """Planner RuntimeErrors surface as structured results, not tracebacks."""

    from nexus.agents.orrery import retrograde_persistence
    from nexus.api import db_pool

    def fail_plan(cur: Any, *, dry_run: bool) -> Any:
        raise RuntimeError("No active MEMNON embedding models are configured")

    monkeypatch.setattr(
        db_pool, "get_connection", lambda *args, **kwargs: FakeApplyConnection()
    )
    monkeypatch.setattr(
        retrograde_persistence,
        "plan_retrograde_summaries",
        fail_plan,
    )

    result = cli.run_retrograde_embed_history(Namespace(slot=5, execute=False))

    assert result == {
        "success": False,
        "error": "No active MEMNON embedding models are configured",
    }


def test_retrograde_persistence_formatter_uses_summary_identity(capsys) -> None:
    """The persistence formatter renders dedicated summary identities."""

    cli._print_retrograde_persistence(
        {
            "retrograde_persistence": {
                "dry_run": False,
                "source_kind": "retrograde",
                "prologue_anchor": {"status": "already_present", "chunk_id": 1},
                "counters": {"summaries_inserted": 2},
                "execute_blockers": [],
                "retrieval": {
                    "summaries_enabled": True,
                    "embedding_pending_summary_ids": [72, 73],
                },
            },
            "retrograde_embedding": [
                {
                    "summary_id": 72,
                    "models": ["embedding/test"],
                    "dimensions": [768],
                    "embedding_generated_at": "2026-07-15T01:02:03+00:00",
                }
            ],
        }
    )

    output = capsys.readouterr().out
    assert "summaries_inserted: 2" in output
    assert "embedding_pending_summary_ids: [72, 73]" in output
    assert "summary 72" in output
    assert "models=['embedding/test']" in output
    assert "dimensions=[768]" in output
    assert "job_id" not in output
    assert "summary_chunks" not in output


def test_retrograde_history_formatter_uses_summary_rows(capsys) -> None:
    """The history formatter never presents generated summaries as chunks."""

    cli._print_retrograde_embed_history(
        {
            "retrograde_embed_history": {
                "dry_run": True,
                "summary_rows": [
                    {
                        "event_ref": "r6_e01",
                        "status": "would_insert",
                        "summary_id": None,
                        "embedding_pending": True,
                    }
                ],
                "embedding_pending_summary_ids": [],
                "embedding_results": [],
            }
        }
    )

    output = capsys.readouterr().out
    assert "summary_rows: 1" in output
    assert "no summary" in output
    assert "embedding_pending_summary_ids: []" in output
    assert "summary_chunk" not in output
