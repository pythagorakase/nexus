"""Critical-path assertions shared by the TEST-provider turn and the golden path.

One contract over a turn observation (``nexus.telemetry.turn_observation``):
the free TEST-provider turn (``tests/test_api/test_attempt_manifest_pg.py``)
and stage 9 of the paid golden-path gate (``tests/test_golden_path_live.py``)
assert the same critical-path facts, so the real-provider proof (#802) and the
free proof cannot drift apart.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from nexus.telemetry.turn_observation import SCHEMA_VERSION

# Provider outcomes that show the provider returned a response (migration 124);
# ``error`` and a null outcome (before ``finish_attempt``) show none.
RESPONSE_OUTCOMES = frozenset({"accepted", "rejected_validation"})
# A played turn under ``turn_pipeline = "two_pass"`` (nexus.toml).
TWO_PASS_SEATS = frozenset({"skald_writer", "gaia"})
# The bootstrap turn is single-pass: its response model is not ``SkaldTurnWire``.
BOOTSTRAP_SEATS = frozenset({"skald_single_pass"})


def assert_critical_path(
    observation: Mapping[str, Any],
    *,
    session: str,
    terminal_outcome: Optional[str],
    seats: frozenset[str],
) -> None:
    """Assert one turn observation's critical path against its usage ledger.

    Every attempt whose ``provider_outcome`` shows a response carries ledger
    usage with integer tokens, and ``attempts_without_usage`` counts exactly
    the attempts without a response (Decision 802-D10). The critical-path
    token sums and provider list are recomputed from the responding attempts.
    """
    assert observation["schema_version"] == SCHEMA_VERSION, (
        f"{session}: schema_version {observation['schema_version']!r}, "
        f"expected {SCHEMA_VERSION}"
    )
    assert observation["generation_session"] == session, (
        f"{session}: observation names session "
        f"{observation['generation_session']!r}"
    )
    assert observation["terminal_outcome"] == terminal_outcome, (
        f"{session}: terminal_outcome {observation['terminal_outcome']!r}, "
        f"expected {terminal_outcome!r}"
    )
    ledger_days = observation["ledger_days_read"]
    assert (
        isinstance(ledger_days, list) and ledger_days
    ), f"{session}: ledger_days_read is empty or not a list: {ledger_days!r}"

    assert isinstance(
        observation["choice_ready_at"], str
    ), f"{session}: choice_ready_at {observation['choice_ready_at']!r}"
    seconds = observation["seconds_to_choice_ready"]
    assert isinstance(seconds, (int, float)) and not isinstance(
        seconds, bool
    ), f"{session}: seconds_to_choice_ready {seconds!r} is not a number"
    assert seconds > 0, f"{session}: seconds_to_choice_ready {seconds!r}"

    attempts = observation["attempts"]
    observed_seats = {attempt["seat"] for attempt in attempts}
    assert seats <= observed_seats, (
        f"{session}: attempt seats {sorted(observed_seats)} lack "
        f"{sorted(seats - observed_seats)}"
    )
    foreign = [
        attempt["generation_session"]
        for attempt in attempts
        if attempt["generation_session"] != session
    ]
    assert not foreign, f"{session}: attempts name other sessions {foreign}"

    responding = [
        attempt
        for attempt in attempts
        if attempt["provider_outcome"] in RESPONSE_OUTCOMES
    ]
    for attempt in responding:
        usage = attempt["usage"]
        key = f"{attempt['seat']} #{attempt['attempt']}"
        assert usage["provenance"] == "provider_usage_ledger", (
            f"{session}: {key} received a response "
            f"({attempt['provider_outcome']}) but has no ledger usage: {usage!r}"
        )
        for field in ("input_tokens", "output_tokens"):
            assert (
                type(usage[field]) is int
            ), f"{session}: {key} {field} is {usage[field]!r}, not an integer"

    critical_path = observation["usage_totals"]["critical_path"]
    without_response = len(attempts) - len(responding)
    assert critical_path["attempts_without_usage"] == without_response, (
        f"{session}: attempts_without_usage "
        f"{critical_path['attempts_without_usage']!r}, but {without_response} "
        "attempts received no response"
    )
    for field in ("input_tokens", "output_tokens"):
        expected = sum(attempt["usage"][field] for attempt in responding)
        assert critical_path[field] == expected, (
            f"{session}: critical_path {field} {critical_path[field]!r}, "
            f"responding attempts sum to {expected}"
        )
    providers = sorted({attempt["usage"]["provider"] for attempt in responding})
    assert critical_path["providers"] == providers, (
        f"{session}: critical_path providers {critical_path['providers']!r}, "
        f"responding attempts name {providers}"
    )
    assert critical_path["comparable"] is (len(providers) <= 1), (
        f"{session}: critical_path comparable {critical_path['comparable']!r} "
        f"for providers {providers}"
    )
