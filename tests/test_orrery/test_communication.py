"""Unit contracts for Orrery communication valence tiers."""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from nexus.agents.orrery.communication import _valence_tier


OLD_VALENCE_RE = re.compile(r"^(?P<magnitude>[+-]?\d+)\|[^|]+$")
PARITY_LITERALS = (
    "+5|devoted",
    "+4|admiring",
    "+3|trusting",
    "+2|friendly",
    "+1|favorable",
    "0|neutral",
    "-1|wary",
    "-2|disapproving",
    "-3|resentful",
    "-4|hostile",
    "-5|hateful",
    "+2|deferential",
    "+3|devoted",
    "-1|beholden",
)


def _old_regex_tier(literal: str) -> str:
    match = OLD_VALENCE_RE.fullmatch(literal)
    assert match is not None
    magnitude = int(match.group("magnitude"))
    if magnitude > 0:
        return "trusting"
    if magnitude < 0:
        return "hostile"
    return "neutral"


@pytest.mark.parametrize("literal", PARITY_LITERALS)
def test_float_sign_tier_matches_retired_regex_tier(literal: str) -> None:
    """All canonical and retired authored labels retain latency semantics."""

    magnitude = int(literal.split("|", maxsplit=1)[0])
    valence_current = Decimal(magnitude) / Decimal("5.5")
    assert _valence_tier(valence_current) == _old_regex_tier(literal)


@pytest.mark.parametrize("invalid", [None, "0.5", True, Decimal("NaN")])
def test_float_sign_tier_rejects_non_numeric_or_non_finite_values(
    invalid: object,
) -> None:
    with pytest.raises(ValueError, match="Unparseable valence_current"):
        _valence_tier(invalid)
