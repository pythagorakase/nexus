"""Tests for LOGON prompt formatting."""

from pathlib import Path
from typing import Any

import pytest

from nexus.agents.lore.logon_utility import LogonUtility


PROMPTS_DIR = Path(__file__).parents[2] / "prompts"


class _FakeCursor:
    def __init__(self, row: Any) -> None:
        self.row = row

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> bool:
        return False

    def execute(self, _sql: str) -> None:
        return None

    def fetchone(self) -> Any:
        return self.row


class _FakeConnection:
    def __init__(self, row: Any) -> None:
        self.row = row
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self.row)

    def close(self) -> None:
        self.closed = True


def _patch_setting_row(monkeypatch: pytest.MonkeyPatch, row: Any) -> _FakeConnection:
    fake_conn = _FakeConnection(row)
    monkeypatch.setattr(
        "nexus.api.slot_utils.require_slot_dbname",
        lambda **_kwargs: "save_05",
    )
    monkeypatch.setattr(
        "nexus.agents.lore.logon_utility.format_tag_library_for_prompt",
        lambda _dbname: "",
    )
    monkeypatch.setattr(
        "nexus.agents.lore.logon_utility.psycopg2.connect",
        lambda **_kwargs: fake_conn,
    )
    return fake_conn


def _setting_card() -> dict[str, Any]:
    return {
        "world_name": "Veyra",
        "genre": "fantasy",
        "secondary_genres": ["mystery"],
        "tone": "dark",
        "time_period": "Age of Ash",
        "tech_level": "medieval",
        "magic_exists": True,
        "magic_description": "Oaths become weather.",
        "political_structure": "Fractured baronies under a wounded crown.",
        "major_conflict": "The bells name traitors before they act.",
        "themes": ["loyalty", "guilt"],
        "cultural_notes": "Hospitality is sworn at thresholds.",
        "language_notes": "Names are formal in public.",
        "geographic_scope": "regional",
        "diegetic_artifact": "VERBATIM VEYRAN STYLE BIBLE",
    }


def test_load_system_prompt_renders_setting_card_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persisted SettingCard JSON reaches the system prompt."""

    fake_conn = _patch_setting_row(monkeypatch, (_setting_card(),))

    prompt = LogonUtility({}, dbname="save_05")._load_system_prompt()

    assert fake_conn.closed is True
    assert "## Setting Context: Veyra" in prompt
    assert "VERBATIM VEYRAN STYLE BIBLE" in prompt
    assert "- Genre: fantasy" in prompt
    assert "- Magic Description: Oaths become weather." in prompt
    assert "- Major Conflict: The bells name traitors before they act." in prompt


def test_load_system_prompt_without_setting_row_returns_core_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty slots still use the core storyteller prompt."""

    _patch_setting_row(monkeypatch, None)
    core_prompt = (PROMPTS_DIR / "storyteller_core.md").read_text()

    prompt = LogonUtility({}, dbname="save_05")._load_system_prompt()

    assert prompt == core_prompt
    assert "Setting Context:" not in prompt


def test_load_system_prompt_appends_bootstrap_supplement_only_for_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chunk #1 gets storyteller_bootstrap.md; normal chunks do not."""

    _patch_setting_row(monkeypatch, None)

    normal_prompt = LogonUtility({}, dbname="save_05")._load_system_prompt()
    bootstrap_prompt = LogonUtility(
        {}, dbname="save_05", bootstrap_mode=True
    )._load_system_prompt()

    assert "# Bootstrap Context (Chunk #1 Only)" not in normal_prompt
    assert "# Bootstrap Context (Chunk #1 Only)" in bootstrap_prompt
    assert "First Chunk Responsibilities" in bootstrap_prompt


def test_context_prompt_renders_bootstrap_data() -> None:
    """Opening chunk prompt carries protagonist, place, seed, and secrets."""

    prompt = LogonUtility({})._format_context_prompt(
        {
            "user_input": "Begin the story.",
            "bootstrap_data": {
                "setting": {
                    "world_name": "Veyra",
                    "genre": "fantasy",
                    "tone": "dark",
                },
                "protagonist": {
                    "name": "Dame Varka",
                    "appearance": "A scarred knight in a rain-dark cloak.",
                    "background": "She broke the last oath she ever swore.",
                    "traits": {"obligations": "Bound to the bell tower."},
                },
                "location": {
                    "name": "Kestrelmark Keep",
                    "atmosphere": "Wet stone, guttering rushlight, and iron bells.",
                    "current_status": "The wardens are searching the lower gate.",
                },
                "story_seed": {
                    "title": "The Bell That Names the Traitor",
                    "situation": "The keep bell rings with Varka's true name.",
                    "hook": "Someone has framed her before the court.",
                    "immediate_goal": "Reach the bell tower before the second toll.",
                    "stakes": "Her house will burn if she fails.",
                    "tension_source": "The traitor is already in the keep.",
                    "key_npcs": ["Brother Hal", "Mistress Rowan"],
                    "secrets": "Brother Hal rang the bell to protect her.",
                },
            },
        }
    )

    assert "=== BOOTSTRAP CONTEXT ===" in prompt
    assert "## Setting Snapshot" in prompt
    assert "- World: Veyra" in prompt
    assert "## Protagonist" in prompt
    assert "- Name: Dame Varka" in prompt
    assert "## Starting Location" in prompt
    assert "- Name: Kestrelmark Keep" in prompt
    assert "## Story Seed: The Bell That Names the Traitor" in prompt
    assert "### LLM-Internal Secrets" in prompt
    assert "Do not reveal them directly to the player" in prompt
    assert "Brother Hal rang the bell to protect her." in prompt
    assert "=== USER INPUT ===\nBegin the story." in prompt


def test_context_prompt_without_bootstrap_data_keeps_standard_shape() -> None:
    """Non-bootstrap calls are unchanged when no bootstrap data is present."""

    prompt = LogonUtility({})._format_context_prompt({"user_input": "Continue."})

    assert "=== BOOTSTRAP CONTEXT ===" not in prompt
    assert "\n=== USER INPUT ===\nContinue." in prompt
    assert "\n=== INSTRUCTIONS ===" in prompt
    assert (
        "Continue the narrative based on the provided context and user input." in prompt
    )
    assert (
        "Maintain consistency with established characters, locations, and plot."
        in prompt
    )


def test_context_prompt_includes_orrery_scene_pressure_controls() -> None:
    """Prompt-only Orrery pressures are framed as Storyteller-controlled."""

    prompt = LogonUtility({})._format_context_prompt(
        {
            "user_input": "Continue.",
            "orrery_scene_pressures": [
                {
                    "template_id": "protect_kin",
                    "branch_label": "Travel toward the target's last known location",
                    "prompt_text": "Mara is moving toward Vale.",
                }
            ],
        }
    )

    assert "=== ORRERY SCENE PRESSURE ===" in prompt
    assert (
        "Storyteller-mediated pressures involving current on-screen characters"
        in prompt
    )
    assert "present-character need pressure" in prompt
    assert "You may adapt, delay, ignore, or incorporate them" in prompt
    assert "Do not let Orrery decide what present characters do" in prompt
    assert "Travel toward the target's last known location: Mara is moving" in prompt


def test_context_prompt_includes_orrery_bleed_menu_controls() -> None:
    """Selected Bleed peripherals are framed as optional ambient texture."""

    prompt = LogonUtility({})._format_context_prompt(
        {
            "user_input": "Continue.",
            "orrery_bleed_menu": [
                {
                    "template_id": "evade_pursuers",
                    "channel": "digital",
                    "summary": "street cameras briefly lose Mara",
                    "actor_name": "Mara",
                }
            ],
        }
    )

    assert "=== ORRERY AMBIENT PERIPHERALS ===" in prompt
    assert "optional ambient peripherals from off-screen events" in prompt
    assert "Ignore freely, render subtly" in prompt
    assert "[digital] Mara: street cameras briefly lose Mara" in prompt


def test_system_prompt_includes_runtime_tag_library(monkeypatch) -> None:
    """Storyteller prompt receives the slot's live Orrery tag library."""

    monkeypatch.setattr(
        "nexus.agents.lore.logon_utility.format_tag_library_for_prompt",
        lambda _dbname: "TAG LIBRARY",
    )
    monkeypatch.setattr(
        "nexus.api.slot_utils.require_slot_dbname",
        lambda dbname=None: dbname or "save_05",
    )
    monkeypatch.setattr(
        "nexus.agents.lore.logon_utility.psycopg2.connect",
        lambda **_kwargs: _Conn(),
    )

    prompt = LogonUtility({}, dbname="save_05")._load_system_prompt()

    assert "TAG LIBRARY" in prompt
    assert "## Test Setting" in prompt
    assert "Setting body." in prompt


def test_system_prompt_keeps_setting_when_tag_library_unavailable(monkeypatch) -> None:
    """A missing Orrery registry should not block storyteller prompt loading."""

    def raise_missing_registry(_dbname: str) -> str:
        raise RuntimeError("tag_category_registry missing")

    monkeypatch.setattr(
        "nexus.agents.lore.logon_utility.format_tag_library_for_prompt",
        raise_missing_registry,
    )
    monkeypatch.setattr(
        "nexus.api.slot_utils.require_slot_dbname",
        lambda dbname=None: dbname or "save_05",
    )
    monkeypatch.setattr(
        "nexus.agents.lore.logon_utility.psycopg2.connect",
        lambda **_kwargs: _Conn(),
    )

    prompt = LogonUtility({}, dbname="save_05")._load_system_prompt()

    assert "TAG LIBRARY" not in prompt
    assert "## Test Setting" in prompt
    assert "Setting body." in prompt


class _Conn:
    def cursor(self) -> "_Cursor":
        return _Cursor()

    def close(self) -> None:
        return None


class _Cursor:
    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, _sql: str) -> None:
        return None

    def fetchone(self):
        return ({"title": "Test Setting", "content": "Setting body."},)
