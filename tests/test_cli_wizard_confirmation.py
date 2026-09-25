"""CLI confirmation and revision protocol regressions; no providers or slots."""

from argparse import Namespace
from typing import Any

import pytest
import requests

from nexus import cli


class Response:
    """Small gateway response carrying explicit HTTP status and JSON data."""

    def __init__(self, data: Any, status: int = 200) -> None:
        self.data = data
        self.status_code = status
        self.ok = 200 <= status < 400
        self.text = str(data)

    def json(self) -> Any:
        return self.data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)


def arguments(**overrides: Any) -> Namespace:
    """Use the public continue command's defaults unless explicitly changed."""
    return Namespace(
        **dict(
            slot=4,
            model=None,
            user_text=None,
            choice=None,
            accept_fate=False,
            dev=False,
        )
        | overrides
    )


def artifact(phase: str) -> dict[str, Any]:
    """A complete persisted artifact awaiting deterministic confirmation."""
    return {
        "phase": phase,
        "thread_id": "saved-conversation",
        "pending_confirmation": phase,
        "artifact_token": "current-artifact-token",
        "phase_complete": True,
        "artifact_type": f"submit_{phase}",
        "data": {"name": "Saved draft"},
    }


def confirmed(phase: str) -> dict[str, str]:
    """Mirror the deterministic confirm endpoint's response contract."""
    return {
        "status": "confirmed",
        "phase": phase,
        "next_phase": "character" if phase == "setting" else "seed",
        "thread_id": "saved-conversation",
    }


def gateway(monkeypatch, state, responses):
    """Reject unexpected POSTs, making accidental inference immediately visible."""
    calls = []

    def get(url, **kwargs):
        assert url.endswith("/api/slot/4/state")
        return Response({"is_empty": False, "is_wizard_mode": True, **state})

    def post(url, *, json, **kwargs):
        calls.append((url.split("/api/")[-1], json))
        assert responses, f"Unexpected request {url}"
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(cli, "_api_get", get)
    monkeypatch.setattr(cli, "_api_post", post)
    return calls


@pytest.mark.parametrize("phase", ["setting", "character"])
@pytest.mark.parametrize("resumed", [False, True])
def test_confirm_precedes_next_phase_inference(monkeypatch, phase, resumed):
    data = artifact(phase)
    next_phase = confirmed(phase)["next_phase"]
    responses = ([] if resumed else [Response(data)]) + [
        Response(confirmed(phase)),
        Response(
            {
                "message": "The next phase begins.",
                "choices": ["A quiet start"],
                "phase": next_phase,
            }
        ),
    ]
    calls = gateway(monkeypatch, data if resumed else {"phase": phase}, responses)
    result = cli.run_continue(
        arguments(user_text=None if resumed else "My decision", model="explicit-model")
    )
    assert result["success"] is True
    assert result["phase"] == next_phase
    assert result["next_phase_intro"] == "The next phase begins."
    assert result["pending_confirmation"] is None
    assert [path for path, _ in calls] == ([] if resumed else ["story/new/chat"]) + [
        "story/new/setup/confirm",
        "story/new/chat",
    ]
    assert calls[-2][1] == {
        "slot": 4,
        "thread_id": "saved-conversation",
        "phase": phase,
        "artifact_token": "current-artifact-token",
    }
    assert calls[-1][1]["thread_id"] == "saved-conversation"
    assert calls[-1][1]["current_phase"] == next_phase
    assert calls[-1][1]["model"] == "explicit-model"
    if not resumed:
        assert result["artifact_data"] == {"name": "Saved draft"}


@pytest.mark.parametrize(
    "failure",
    [
        Response({"detail": "Changed"}, 409),
        Response({}, 503),
        Response({}, 300),
        requests.Timeout("Unknown acceptance"),
    ],
)
def test_confirmation_failure_never_advances_or_requests_intro(monkeypatch, failure):
    calls = gateway(monkeypatch, artifact("character"), [failure])
    result = cli.run_continue(arguments())
    assert result["success"] is False
    assert result["phase"] == "character"
    assert result["pending_confirmation"] == "character"
    assert len(calls) == 1
    assert calls[0][0] == "story/new/setup/confirm"
    assert result["recovery_command"] == "nexus load --slot 4"


def test_replayed_confirm_rejection_never_introduces_the_phase_twice(monkeypatch):
    calls = gateway(
        monkeypatch,
        artifact("setting"),
        [
            Response(confirmed("setting")),
            Response({"message": "Choose a character.", "phase": "character"}),
            Response({"detail": "This artifact was already confirmed."}, 409),
        ],
    )
    assert cli.run_continue(arguments())["success"] is True
    assert cli.run_continue(arguments())["success"] is False
    assert [path for path, _ in calls] == [
        "story/new/setup/confirm",
        "story/new/chat",
        "story/new/setup/confirm",
    ]


@pytest.mark.parametrize(
    "missing", ["thread_id", "artifact_token", "pending_confirmation"]
)
def test_incomplete_phase_response_never_schedules_confirmation_or_intro(
    monkeypatch, missing
):
    data = artifact("setting")
    data.pop(missing)
    calls = gateway(monkeypatch, {"phase": "setting"}, [Response(data)])
    result = cli.run_continue(arguments(user_text="My setting"))
    assert result["success"] is False
    assert len(calls) == 1
    assert calls[0][0] == "story/new/chat"


@pytest.mark.parametrize(
    "change",
    [
        {"status": "unknown"},
        {"phase": "setting"},
        {"next_phase": "ready"},
        {"thread_id": "replacement"},
    ],
)
def test_mismatched_confirmation_acknowledgement_never_requests_intro(
    monkeypatch, change
):
    calls = gateway(
        monkeypatch, artifact("character"), [Response(confirmed("character") | change)]
    )
    result = cli.run_continue(arguments())
    assert result["success"] is False
    assert len(calls) == 1


def test_pending_character_text_enters_revision_before_chat(monkeypatch):
    calls = gateway(
        monkeypatch,
        artifact("character"),
        [
            Response(
                {
                    "status": "revision_started",
                    "phase": "character",
                    "thread_id": "saved-conversation",
                }
            ),
            Response(
                {
                    "phase": "character",
                    "message": "The revised concept is saved.",
                    "phase_complete": False,
                }
            ),
        ],
    )
    result = cli.run_continue(
        arguments(user_text="She is fifty-four, not thirty-eight.")
    )
    assert result["success"] is True
    assert [path for path, _ in calls] == [
        "story/new/setup/character/revise",
        "story/new/chat",
    ]
    assert calls[0][1] == {
        "slot": 4,
        "thread_id": "saved-conversation",
        "artifact_token": "current-artifact-token",
    }
    assert calls[1][1]["thread_id"] == "saved-conversation"
    assert calls[1][1]["message"] == "She is fifty-four, not thirty-eight."


@pytest.mark.parametrize(
    "failure",
    [
        Response({}, 409),
        Response({}, 503),
        Response(
            {"status": "revision_started", "phase": "character", "thread_id": "wrong"}
        ),
        requests.Timeout("Unknown revision"),
    ],
)
def test_revision_start_failure_never_sends_player_text(monkeypatch, failure):
    calls = gateway(monkeypatch, artifact("character"), [failure])
    result = cli.run_continue(arguments(user_text="Revise the character."))
    assert result["success"] is False
    assert len(calls) == 1
    assert calls[0][0] == "story/new/setup/character/revise"


def test_pending_setting_text_revises_directly_without_confirmation(monkeypatch):
    calls = gateway(
        monkeypatch,
        artifact("setting"),
        [
            Response(
                {
                    "phase": "setting",
                    "message": "Tell me more.",
                    "phase_complete": False,
                }
            )
        ],
    )
    result = cli.run_continue(arguments(user_text="Make the harbor quieter."))
    assert result["success"] is True
    assert len(calls) == 1
    assert calls[0][0] == "story/new/chat"
    assert calls[0][1]["thread_id"] == "saved-conversation"


def test_intro_failure_does_not_repeat_confirmation_or_inference(monkeypatch):
    calls = gateway(
        monkeypatch,
        artifact("setting"),
        [Response(confirmed("setting")), Response({}, 503)],
    )
    result = cli.run_continue(arguments())
    assert result["success"] is False
    assert result["phase"] == "character"
    assert result["pending_confirmation"] is None
    assert "Artifact confirmed" in result["error"]
    assert len(calls) == 2


def test_plain_continue_cannot_confirm_an_unfinished_revision(monkeypatch):
    calls = gateway(
        monkeypatch, {"phase": "character", "character_revision_pending": True}, []
    )
    result = cli.run_continue(arguments())
    assert result["success"] is False
    assert calls == []


def test_load_exposes_pending_confirmation_without_mutating_it(monkeypatch):
    calls = gateway(monkeypatch, artifact("character"), [])
    result = cli.run_load(arguments())
    assert result["pending_confirmation"] == "character"
    assert result["artifact_token"] == "current-artifact-token"
    assert result["thread_id"] == "saved-conversation"
    assert "nexus continue --slot 4" in result["message"]
    assert calls == []


def test_load_explains_an_unfinished_revision_without_confirming(monkeypatch):
    calls = gateway(
        monkeypatch, {"phase": "character", "character_revision_pending": True}, []
    )
    result = cli.run_load(arguments())
    assert result["character_revision_pending"] is True
    assert "unfinished" in result["message"]
    assert calls == []
