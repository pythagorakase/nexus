"""Tests for the NEXUS CLI helpers."""

import sys
from argparse import Namespace
from typing import Any

from nexus import cli
from nexus.cli import GENERATION_POLL_SECONDS, _is_terminal_generation_status


class DummyResponse:
    """Minimal requests.Response double for CLI tests."""

    def __init__(
        self, payload: dict[str, Any], ok: bool = True, text: str = ""
    ) -> None:
        self.payload = payload
        self.ok = ok
        self.text = text

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


def test_generation_poll_window_covers_live_reasoning_models() -> None:
    """CLI polling should outlast slow structured generation calls."""

    assert GENERATION_POLL_SECONDS >= 180


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
    """Cursor double; missing compiler inputs do not require SQL."""

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
