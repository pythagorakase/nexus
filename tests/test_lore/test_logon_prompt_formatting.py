"""Tests for LOGON prompt formatting."""

from nexus.agents.lore.logon_utility import LogonUtility


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
