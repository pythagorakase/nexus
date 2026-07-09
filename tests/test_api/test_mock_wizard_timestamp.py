"""Tests for deterministic TEST-mode wizard timestamps."""

from nexus.api import mock_openai


def test_mock_seed_declares_fixed_diegetic_timestamp(monkeypatch) -> None:
    """The mock seed must persist a deterministic story date through the tool."""

    monkeypatch.setattr(
        mock_openai,
        "query_wizard_cache",
        lambda: {
            "seed_type": "mystery",
            "seed_title": "The Job You Already Took",
            "seed_situation": "A courier wakes aboard a tram with a sealed satchel.",
            "seed_hook": "The city says the delivery has already happened.",
            "seed_immediate_goal": "Discover where the satchel belongs.",
            "seed_stakes": "Corporate agents are closing in.",
            "seed_tension_source": "The courier cannot trust their own memory.",
            "seed_secrets": "The satchel contains an identity ledger root.",
            "initial_location": {"name": "Rootline Tram 3B"},
            "zone_name": "Rhine-Ruhr Arcology Belt",
            "layer_name": "Neon Palimpsest Earth",
        },
    )

    response = mock_openai.get_cached_phase_response("seed")

    assert response["data"]["seed"]["base_timestamp"] == {
        "year": 2087,
        "month": 11,
        "day": 3,
        "hour": 22,
        "minute": 47,
    }
