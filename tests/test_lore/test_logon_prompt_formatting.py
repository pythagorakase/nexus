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
    assert "off-screen pressures involving current on-screen characters" in prompt
    assert "You may adapt, delay, ignore, or incorporate them" in prompt
    assert "Do not let Orrery decide what present characters do" in prompt
    assert "Travel toward the target's last known location: Mara is moving" in prompt
