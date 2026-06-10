"""Tests for the NEXUS CLI helpers."""

import json
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
                        "emotional_valence": "+2|deferential",
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
        "(patron, +2|deferential)" in captured.out
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
        "generate_seed_candidates_with_skald",
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
    """The persistence command mirrors manifest apply grammar."""

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
            )
        )
        return {
            "schema_version": "orrery_retrograde_persistence_plan.v0",
            "dry_run": dry_run,
            "slot": slot,
            "dbname": dbname,
            "counters": {"events_would_insert": 0},
            "execute_blockers": [],
        }

    monkeypatch.setattr(
        db_pool, "get_connection", lambda *args, **kwargs: FakeApplyConnection()
    )
    monkeypatch.setattr(
        retrograde_persistence,
        "build_retrograde_persistence_plan",
        fake_build,
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
        )
    ]
