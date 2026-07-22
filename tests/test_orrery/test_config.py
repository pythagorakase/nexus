"""Tests for Orrery configuration loading."""

import subprocess
import tomllib
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from nexus.config import load_settings
from nexus.api.new_story_schemas import Genre
from nexus.config.settings_models import (
    OrreryBleedSettings,
    OrreryContagionSettings,
    OrreryDashboardSettings,
    OrreryDistortionSettings,
    OrreryDriftSettings,
    OrreryEpistemicsSettings,
    OrreryKnowledgeSettings,
    OrreryMoodSettings,
    OrreryPromoteSettings,
    OrreryRevealSettings,
    OrrerySettings,
    OrreryRetrogradeMaturationSettings,
    OrreryRetrogradeProjectSettings,
    OrreryRetrogradeWeirdGenreBands,
    OrreryRetrogradeWeirdSettings,
    OrrerySunhelmSettings,
)


def test_dev_dashboard_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """NEXUS_DEV_DASHBOARD=1 enables the dashboard without editing the file
    — the escape hatch that keeps the committed flag false."""

    monkeypatch.setenv("NEXUS_DEV_DASHBOARD", "1")
    settings = load_settings("nexus.toml")
    assert settings.orrery.dashboard.enabled is True


def test_orrery_settings_resolve_model_reference() -> None:
    """Orrery narration config resolves provider role references at load time."""

    settings = load_settings("nexus.toml")

    assert settings.orrery is not None
    assert settings.orrery.enabled is True
    assert settings.orrery.binding.window_chunks == 30
    assert settings.orrery.contagion.dyad_tiers.trusting == timedelta(hours=24)
    assert settings.orrery.contagion.dyad_tiers.neutral == timedelta(hours=96)
    assert settings.orrery.contagion.dyad_tiers.hostile is None
    assert settings.orrery.contagion.dyad_overrides["captor"].forward is None
    assert settings.orrery.contagion.dyad_overrides["captor"].reverse == timedelta(
        hours=24
    )
    assert settings.orrery.contagion.channels["status:*"].min_level == "junior"
    assert settings.orrery.contagion.culture_profiles["cellular_clandestine"] == 4.0
    assert settings.orrery.contagion.guards.age_horizon == timedelta(days=14)
    assert settings.orrery.distortion.enabled is True
    assert settings.orrery.mood.enabled is True
    assert settings.orrery.mood.duration_hours == 12.0
    expected_model = settings.global_.model.api_models["anthropic"].roles["default"]
    assert settings.orrery.narration.model_ref == expected_model
    assert settings.orrery.promote.provider is None
    assert settings.orrery.promote.priority_threshold == 30.0
    assert settings.orrery.promote.magnitude_threshold == 0.35
    assert settings.orrery.promote.perceptual_summary_max_chars == 240
    assert settings.orrery.sunhelm.accrual_rates == {
        "sleep": 1.0,
        "hunger": 1.0,
        "thirst": 1.0,
        "socialize": 1.0,
        "intimacy": 1.0,
    }
    assert settings.orrery.sunhelm.severity_thresholds["sleep"].moderate == 30.0
    assert settings.orrery.sunhelm.severity_thresholds["socialize"].severe == 168.0
    assert settings.orrery.sunhelm.severity_thresholds["intimacy"].critical == 720.0
    assert settings.orrery.sunhelm.priorities == {
        "sleep": 25,
        "thirst": 24,
        "hunger": 22,
        "socialize": 18,
        "intimacy": 16,
    }
    assert settings.orrery.sunhelm.pressure.min_severity_level == 2
    assert "min_accrual_hours_per_chunk" not in settings.orrery.sunhelm.model_dump()
    assert settings.orrery.package_selection.mode == "stochastic"
    assert settings.orrery.package_selection.window_points == 6.0
    assert settings.orrery.package_selection.temperature == 2.0
    assert settings.orrery.package_selection.exempt_bands == ["crisis_constraint"]
    assert settings.orrery.projects.advance_interval_hours == 24.0
    assert settings.orrery.projects.max_active_per_character == 1
    assert settings.orrery.projects.stall_abandon_threshold == 3
    assert settings.orrery.projects.abandon_after_stalled_world_hours == 168.0
    assert settings.orrery.projects.milestone_magnitude == 0.40
    assert settings.orrery.projects.coverage_distribution_tolerance == 0.05
    assert settings.orrery.drift.enabled is True
    assert settings.orrery.drift.copresence_rate_per_hour == Decimal("0.001")
    assert settings.orrery.drift.copresence_max_hours_per_tick == Decimal("12.0")
    assert settings.orrery.drift.project_milestone_delta == Decimal("0.03")
    assert settings.orrery.drift.hostile_events["retaliation_executed"] == Decimal(
        "-0.06"
    )
    assert settings.orrery.drift.cooperative_events[
        "protective_intervention"
    ] == Decimal("0.04")
    assert settings.orrery.reveal.enabled is True
    assert settings.orrery.knowledge.enabled is True
    assert settings.orrery.knowledge.max_entries == 12
    assert settings.orrery.knowledge.recent_reveal_window_chunks == 5
    assert "relationship_drift_milestone" in (
        settings.orrery.epistemics.claim_event_types
    )
    # The ship-off invariant applies to the COMMITTED config: flipping the
    # dashboard on locally is a documented workflow (nexus.toml comment,
    # issue #415), and asserting the working tree here trains developers to
    # commit the flag just to green the suite — which is how it leaked in
    # 4917cfc9. CI runs on committed trees, so the gate still blocks commits.
    committed_toml = subprocess.run(
        ["git", "show", "HEAD:nexus.toml"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    committed_dashboard = tomllib.loads(committed_toml)["orrery"]["dashboard"]
    assert committed_dashboard["enabled"] is False, (
        "[orrery.dashboard] enabled must ship false: the gateway has no "
        "auth and binds 0.0.0.0 (see the nexus.toml comment). Flip it "
        "locally only — never commit it."
    )
    assert settings.orrery.dashboard.coverage_max_anchors == 50
    assert settings.orrery.dashboard.coverage_epoch_min_world_times == 10
    weird = settings.orrery.retrograde.weird
    assert weird.default_level == "medium"
    assert weird.dev.cli_flag == "--weird"
    assert weird.dev.min == 0.0
    assert weird.dev.max == 1.0
    assert set(weird.bands_by_genre) == {genre.value for genre in Genre}
    assert weird.bands_by_genre["cyberpunk"].medium.min == 0.36
    assert weird.bands_by_genre["historical"].medium.min == 0.12


def test_sunhelm_rejects_retired_story_time_accrual_floor() -> None:
    """Stale configs fail loudly instead of reviving narrative-clock accrual."""

    with pytest.raises(ValidationError, match="min_accrual_hours_per_chunk"):
        OrrerySunhelmSettings(
            min_accrual_hours_per_chunk={"socialize": 0.5}  # type: ignore[call-arg]
        )


def test_contagion_rejects_malformed_duration() -> None:
    """World-time latencies fail at settings validation, never at traversal."""

    with pytest.raises(ValidationError, match="malformed duration"):
        OrreryContagionSettings(
            dyad_tiers={
                "trusting": "tomorrow",
                "neutral": "96h",
                "hostile": "never",
            }
        )


def test_contagion_rejects_nonpositive_culture_multiplier() -> None:
    """Culture profiles may slow or accelerate channels but never erase them."""

    with pytest.raises(ValidationError, match="greater than zero"):
        OrreryContagionSettings(culture_profiles={"covert": 0.0})


def test_epistemics_rejects_claim_propagated_as_claim_producer() -> None:
    """The propagation ledger cannot recursively create a new claim."""

    with pytest.raises(ValidationError, match="claim_propagated cannot appear"):
        OrreryEpistemicsSettings(claim_event_types=["claim_propagated"])


def test_drift_rejects_nonnegative_hostile_delta() -> None:
    """Hostile classification mistakes fail during config validation."""

    with pytest.raises(ValidationError, match="strictly negative"):
        OrreryDriftSettings(hostile_events={"threat_issued": 0})


def test_drift_event_maps_must_be_disjoint() -> None:
    """The same event type in both maps would double-apply its deltas."""

    with pytest.raises(ValidationError, match="must be disjoint"):
        OrreryDriftSettings(
            hostile_events={"threat_issued": Decimal("-0.02")},
            cooperative_events={"threat_issued": Decimal("0.02")},
        )


def test_drift_rejects_nonpositive_cooperative_delta() -> None:
    """Cooperative classification mistakes fail during config validation."""

    with pytest.raises(ValidationError, match="strictly positive"):
        OrreryDriftSettings(cooperative_events={"welfare_check": -0.1})


def test_drift_defaults_off_when_block_is_absent() -> None:
    """Legacy configs cannot silently opt into relationship drift."""

    assert OrreryDriftSettings().enabled is False
    payload = load_settings("nexus.toml").orrery.model_dump()
    payload.pop("drift")
    assert OrrerySettings.model_validate(payload).drift.enabled is False


def test_mood_defaults_off_and_requires_positive_duration() -> None:
    """Legacy configs cannot silently opt in and invalid expiry is loud."""

    assert OrreryMoodSettings().enabled is False
    payload = load_settings("nexus.toml").orrery.model_dump()
    payload.pop("mood")
    assert OrrerySettings.model_validate(payload).mood.enabled is False
    with pytest.raises(ValidationError, match="greater than 0"):
        OrreryMoodSettings(duration_hours=0)


def test_reveal_defaults_off_when_block_is_absent() -> None:
    """Legacy configs cannot silently opt into backstory reveals."""

    assert OrreryRevealSettings().enabled is False
    payload = load_settings("nexus.toml").orrery.model_dump()
    payload.pop("reveal")
    assert OrrerySettings.model_validate(payload).reveal.enabled is False


def test_knowledge_defaults_off_and_requires_positive_windows() -> None:
    """Legacy configs stay off and invalid digest bounds fail validation."""

    assert OrreryKnowledgeSettings().enabled is False
    payload = load_settings("nexus.toml").orrery.model_dump()
    payload.pop("knowledge")
    assert OrrerySettings.model_validate(payload).knowledge.enabled is False
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        OrreryKnowledgeSettings(max_entries=0)
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        OrreryKnowledgeSettings(recent_reveal_window_chunks=0)


def test_distortion_defaults_off_when_block_is_absent() -> None:
    """Legacy configs cannot silently opt into authored account distortion."""

    assert OrreryDistortionSettings().enabled is False
    payload = load_settings("nexus.toml").orrery.model_dump()
    payload.pop("distortion")
    assert OrrerySettings.model_validate(payload).distortion.enabled is False


def test_drift_rejects_project_delta_at_or_above_one() -> None:
    with pytest.raises(ValidationError, match="less than 1"):
        OrreryDriftSettings(project_milestone_delta=1)


def test_drift_rejects_hostile_delta_magnitude_at_or_above_one() -> None:
    with pytest.raises(ValidationError, match="magnitudes must be < 1"):
        OrreryDriftSettings(hostile_events={"threat_issued": -1})


def test_drift_rejects_cooperative_delta_magnitude_at_or_above_one() -> None:
    with pytest.raises(ValidationError, match="magnitudes must be < 1"):
        OrreryDriftSettings(cooperative_events={"welfare_check": 1})


def test_drift_rejects_copresence_tick_delta_at_or_above_one() -> None:
    with pytest.raises(ValidationError, match=r"copresence_rate_per_hour \*"):
        OrreryDriftSettings(
            copresence_rate_per_hour=Decimal("0.1"),
            copresence_max_hours_per_tick=Decimal("10"),
        )


@pytest.mark.parametrize(
    "field",
    [
        "copresence_rate_per_hour",
        "copresence_max_hours_per_tick",
        "project_milestone_delta",
    ],
)
def test_drift_rejects_nonpositive_rates(field: str) -> None:
    """All relationship-drift rates must remain strictly positive."""

    with pytest.raises(ValidationError, match="greater than 0"):
        OrreryDriftSettings.model_validate({field: 0})


def test_project_milestones_cannot_fall_below_promotion_floor() -> None:
    """Configured stage changes must remain eligible for promotion."""

    payload = load_settings("nexus.toml").orrery.model_dump()
    payload["projects"]["milestone_magnitude"] = 0.34

    with pytest.raises(ValidationError, match="milestone_magnitude must be >="):
        OrrerySettings.model_validate(payload)


def test_orrery_dashboard_defaults_to_disabled() -> None:
    """Fresh checkouts must not expose the dev audit router implicitly."""

    assert OrreryDashboardSettings().enabled is False


def test_orrery_bleed_accepts_deprecated_selection_keys() -> None:
    """Old Bleed config keys should still validate but stay out of dumps."""

    settings = OrreryBleedSettings(
        latency_budget_ms=2000,
        candidate_pool_multiplier=4,
    )

    assert settings.max_candidates == 3
    assert settings.near_distance_max == 2
    assert settings.reserved_remote_slots == 1
    dumped = settings.model_dump()
    assert "latency_budget_ms" not in dumped
    assert "candidate_pool_multiplier" not in dumped


def test_orrery_bleed_reserved_remote_slots_must_fit_menu() -> None:
    """A remote reservation cannot consume the entire Bleed menu."""

    with pytest.raises(ValidationError, match="must be < max_candidates"):
        OrreryBleedSettings(max_candidates=2, reserved_remote_slots=2)


def test_disabled_orrery_bleed_requires_zero_remote_reservation() -> None:
    """Implicit defaults adapt to small menus; explicit contradictions raise.

    PR #522 review: a legacy config setting only max_candidates must stay
    bootable — the DEFAULT reservation clamps — while an explicitly
    contradictory reservation still fails loudly.
    """

    adapted = OrreryBleedSettings(max_candidates=0)
    assert adapted.reserved_remote_slots == 0

    single = OrreryBleedSettings(max_candidates=1)
    assert single.reserved_remote_slots == 0

    with pytest.raises(ValidationError, match="must be 0"):
        OrreryBleedSettings(max_candidates=0, reserved_remote_slots=1)

    with pytest.raises(ValidationError, match="must be < max_candidates"):
        OrreryBleedSettings(max_candidates=1, reserved_remote_slots=1)

    settings = OrreryBleedSettings(
        max_candidates=0,
        reserved_remote_slots=0,
    )
    assert settings.max_candidates == 0


def test_orrery_promote_accepts_deprecated_provider_key() -> None:
    """Old promotion config should validate but stay out of dumps."""

    settings = OrreryPromoteSettings(provider="local")

    assert settings.provider == "local"
    dumped = settings.model_dump()
    assert dumped["priority_threshold"] == 30.0
    assert dumped["magnitude_threshold"] == 0.35
    assert dumped["perceptual_summary_max_chars"] == 240
    assert "provider" not in dumped


def test_orrery_retrograde_weird_rejects_overlapping_bands() -> None:
    """Genre remaps must preserve low -> medium -> high ordering."""

    with pytest.raises(ValidationError, match="low <= medium <= high"):
        OrreryRetrogradeWeirdGenreBands(
            low={"min": 0.0, "max": 0.5},
            medium={"min": 0.4, "max": 0.7},
            high={"min": 0.7, "max": 1.0},
        )


def test_orrery_retrograde_weird_rejects_non_contiguous_bands() -> None:
    """Genre remaps should cover a continuous raw-float band per genre."""

    with pytest.raises(ValidationError, match="must be contiguous"):
        OrreryRetrogradeWeirdGenreBands(
            low={"min": 0.0, "max": 0.3},
            medium={"min": 0.4, "max": 0.7},
            high={"min": 0.7, "max": 1.0},
        )


def test_orrery_retrograde_weird_rejects_unknown_genre_keys() -> None:
    """Typos in per-genre weird bands should fail at config load time."""

    payload = deepcopy(load_settings("nexus.toml").orrery.retrograde.weird.model_dump())
    payload["bands_by_genre"]["sci_fi"] = payload["bands_by_genre"].pop("scifi")

    with pytest.raises(ValidationError, match="must define exactly"):
        OrreryRetrogradeWeirdSettings(**payload)


def test_orrery_retrograde_weird_rejects_bands_outside_dev_range() -> None:
    """Per-genre raw bands must stay within the configured dev float surface."""

    payload = deepcopy(load_settings("nexus.toml").orrery.retrograde.weird.model_dump())
    payload["dev"]["min"] = 0.2

    with pytest.raises(ValidationError, match="within the dev raw range"):
        OrreryRetrogradeWeirdSettings(**payload)


def test_orrery_maturation_rejects_selection_exceeding_generation() -> None:
    """R5 cannot be asked to select more seeds than R4 generates."""

    with pytest.raises(ValidationError, match="generate_candidates must be >="):
        OrreryRetrogradeMaturationSettings(generate_candidates=1, select_target=4)


def test_orrery_maturation_accepts_equal_generation_and_selection() -> None:
    """generate_candidates == select_target is a legal (1x) budget."""

    settings = OrreryRetrogradeMaturationSettings(
        generate_candidates=2, select_target=2
    )
    assert settings.generate_candidates == 2


def test_retrograde_projects_default_off_and_require_positive_cap() -> None:
    assert OrreryRetrogradeProjectSettings().enabled is False
    with pytest.raises(ValidationError):
        OrreryRetrogradeProjectSettings(max_seeded_projects=0)


def test_shipped_retrograde_projects_are_enabled() -> None:
    settings = load_settings("nexus.toml")
    assert settings.orrery is not None
    assert settings.orrery.retrograde.projects.enabled is True
    assert settings.orrery.retrograde.projects.max_seeded_projects == 3
