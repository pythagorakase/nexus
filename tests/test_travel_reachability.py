"""Offline contract of the issue 785 travel reachability probe.

The blocker walk runs over hand-built ``ConditionTrace`` trees, which are plain
data records; the probed-row derivation runs over the real builtin catalog.
"""

from __future__ import annotations

from nexus.agents.orrery.explain import ConditionTrace
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
from scripts.qa_shift.travel_reachability import blocking_predicates, probed_rows


def _leaf(raw: str, result: bool) -> ConditionTrace:
    """Return a leaf trace node."""

    return ConditionTrace(raw=raw, prose=raw, result=result)


def _node(op: str, raw: str, result: bool, *children: ConditionTrace) -> ConditionTrace:
    """Return a compound trace node."""

    return ConditionTrace(
        raw=raw, prose=op.lower(), result=result, op=op, children=children
    )


def test_blocking_predicates_walk() -> None:
    """Each compound shape reports exactly the predicates that block it."""

    and_trace = _node(
        "AND",
        "AND(2)",
        False,
        _leaf("blocked(@actor)", False),
        _leaf("fine(@actor)", True),
    )
    assert blocking_predicates(and_trace) == ["blocked(@actor)"]

    or_trace = _node(
        "OR",
        "OR(2)",
        False,
        _leaf("first(@actor)", False),
        _leaf("second(@actor)", False),
    )
    assert blocking_predicates(or_trace) == ["first(@actor)", "second(@actor)"]

    not_leaf = _node(
        "NOT", "NOT(present(@actor))", False, _leaf("present(@actor)", True)
    )
    assert blocking_predicates(not_leaf) == ["NOT(present(@actor))"]

    not_compound = _node(
        "NOT",
        "NOT(OR(2))",
        False,
        _node(
            "OR",
            "OR(2)",
            True,
            _leaf("quiet(@actor)", False),
            _leaf("thirsty(@actor)", True),
        ),
    )
    assert blocking_predicates(not_compound) == ["NOT(thirsty(@actor))"]

    nested = _node(
        "AND",
        "AND(3)",
        False,
        and_trace,
        or_trace,
        _node("OR", "OR(2)", False, _leaf("blocked(@actor)", False), not_leaf),
    )
    assert blocking_predicates(nested) == [
        "blocked(@actor)",
        "first(@actor)",
        "second(@actor)",
        "NOT(present(@actor))",
    ]


def test_probed_rows_match_templates() -> None:
    """The derivation over the builtin catalog yields the nine probed rows."""

    assert probed_rows(BUILTIN_TEMPLATES) == [
        ("routine_commute", "Commute to the scheduled workplace"),
        ("routine_commute", "Commute home after the day's obligations"),
        ("travel", "Charter private transport"),
        ("travel", "Slip out along covert routes"),
        ("travel", "Depart toward the planned destination"),
        ("socialize", "Seek company after extended isolation"),
        ("socialize", "Set out toward public company"),
        ("advance_relocation_plan", "Commit to the road"),
        ("start_relocation_plan", "Begin putting something aside"),
    ]
