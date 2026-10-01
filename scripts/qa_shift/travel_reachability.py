"""Read-only travel reachability probe for issue 785.

For every active character in each database, the probe traces the package gate
and the branch conditions of every branch that starts travel (plus the
relocation project rows that hand off to travel) against a production-parity
hydrated world state, and reports which predicates block each row. It drives
no tick and writes nothing: every database is read through one session whose
transactions are read-only by ``default_transaction_read_only=on``.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
import json
import logging
from typing import Any, Iterator, Mapping, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from nexus.agents.orrery.epistemics import (
    coerce_epistemics_policy,
    load_epistemics_policy,
)
from nexus.agents.orrery.evidence import resolve_evidence
from nexus.agents.orrery.explain import (
    ConditionTrace,
    StackExplanation,
    explain_stack,
    trace_condition,
)
from nexus.agents.orrery.needs import coerce_need_tuning
from nexus.agents.orrery.reconstruction import playable_narrative_predicate
from nexus.agents.orrery.resolver import compose_actor_bindings, hydrate_world_state
from nexus.agents.orrery.substrate import (
    Bindings,
    Branch,
    CompoundCondition,
    Condition,
    Slot,
    Template,
    WorldState,
    coerce_branch_selection,
    coerce_habituation,
    coerce_package_selection,
    coerce_project_policy,
    configure_project_magnitudes,
)
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
from nexus.config import load_settings_as_dict
from nexus.database import create_slot_engine

logger = logging.getLogger(__name__)

# The nine probed rows, written from work order 785-S1a rather than read from
# the code: the derivation in ``probed_rows`` must reproduce them exactly.
EXPECTED_PROBED_ROWS: tuple[tuple[str, str], ...] = (
    ("routine_commute", "Commute to the scheduled workplace"),
    ("routine_commute", "Commute home after the day's obligations"),
    ("travel", "Charter private transport"),
    ("travel", "Slip out along covert routes"),
    ("travel", "Depart toward the planned destination"),
    ("socialize", "Seek company after extended isolation"),
    ("socialize", "Set out toward public company"),
    ("advance_relocation_plan", "Commit to the road"),
    ("start_relocation_plan", "Begin putting something aside"),
)

# The destination classes the social travel branches look for.
SOCIAL_DESTINATION_CLASSES: frozenset[str] = frozenset(
    {"commerce", "entertainment", "meeting", "place_open"}
)

_READ_ONLY_OPTIONS = (
    "-c default_transaction_read_only=on "
    "-c default_transaction_isolation=repeatable\\ read"
)
_SOCIALIZE_DEBT_PREFIX = "has_need_debt_at_or_above(socialize,"
_ACTOR_ONLY_SLOTS: tuple[Slot, ...] = (Slot.ACTOR,)


@contextmanager
def read_only_session(dbname: str) -> Iterator[Session]:
    """Yield one read-only, repeatable-read session on ``dbname``.

    The engine carries ``default_transaction_read_only=on`` in its connection
    options, so every transaction the session opens refuses writes. Before it
    yields, the first statement proves the transaction is read-only and that
    the connection reached the requested database; either check failing
    raises. The engine is disposed on exit.
    """

    engine = create_slot_engine(dbname, connect_args={"options": _READ_ONLY_OPTIONS})
    try:
        with Session(engine) as session:
            row = (
                session.execute(
                    text(
                        "SELECT current_setting('transaction_read_only') AS read_only, "
                        "current_database() AS dbname"
                    )
                )
                .mappings()
                .one()
            )
            if row["read_only"] != "on":
                raise RuntimeError(
                    f"travel_reachability requires a read-only transaction on "
                    f"{dbname!r}; transaction_read_only={row['read_only']!r}"
                )
            if row["dbname"] != dbname:
                raise RuntimeError(
                    f"travel_reachability connected to {row['dbname']!r}, "
                    f"not the requested {dbname!r}"
                )
            yield session
    finally:
        engine.dispose()


def _template_by_id(templates: Sequence[Template], template_id: str) -> Template:
    """Return the one template with ``template_id``; raise when absent."""

    matches = [template for template in templates if template.id == template_id]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one template {template_id!r}; found {len(matches)}"
        )
    return matches[0]


def _branch_by_label(template: Template, label: str) -> Branch:
    """Return the one branch of ``template`` labelled ``label``."""

    matches = [branch for branch in template.branches if branch.label == label]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one branch {label!r} in {template.id!r}; found {len(matches)}"
        )
    return matches[0]


def probed_rows(templates: Sequence[Template]) -> list[tuple[str, str]]:
    """Derive the probed ``(template_id, label)`` rows from ``templates``.

    The rows are every branch whose ``state_delta`` starts travel, in template
    and branch order; then the relocation project's completion branch, which
    hands off to travel; then the branch that starts a ``plan_relocation``
    project, as the upstream row. Raises when the derivation drifts from
    :data:`EXPECTED_PROBED_ROWS`.
    """

    rows: list[tuple[str, str]] = [
        (template.id, branch.label)
        for template in templates
        for branch in template.branches
        if "travel.start" in branch.state_delta
    ]
    advance = _template_by_id(templates, "advance_relocation_plan")
    rows.extend(
        (advance.id, branch.label)
        for branch in advance.branches
        if "project.complete" in branch.state_delta
    )
    start = _template_by_id(templates, "start_relocation_plan")
    rows.extend(
        (start.id, branch.label)
        for branch in start.branches
        if isinstance(branch.state_delta.get("project.start"), Mapping)
        and branch.state_delta["project.start"].get("project_type") == "plan_relocation"
    )
    if tuple(rows) != EXPECTED_PROBED_ROWS:
        raise RuntimeError(
            "The travel-starting branches drifted from the probe's expected rows: "
            f"derived {rows!r}, expected {list(EXPECTED_PROBED_ROWS)!r}"
        )
    return rows


def _true_leaf_raws(trace: ConditionTrace) -> list[str]:
    """Return the raw names of every True leaf under ``trace``, in order."""

    if trace.is_leaf:
        return [trace.raw] if trace.result else []
    return [raw for child in trace.children for raw in _true_leaf_raws(child)]


def blocking_predicates(trace: ConditionTrace) -> list[str]:
    """Return the predicates that make a False trace node False.

    A leaf gives its own name; ``AND`` concatenates the blockers of its False
    children; ``OR`` concatenates the blockers of all its children; ``NOT``
    over a leaf gives the ``NOT`` node's own name, and over a compound child
    gives ``NOT(`` plus the True leaves under that child joined by ``|`` plus
    ``)``. Duplicates are removed, keeping the first occurrence.
    """

    if trace.result:
        raise ValueError(
            f"blocking_predicates needs a False node; {trace.raw!r} is True"
        )
    if trace.is_leaf:
        found = [trace.raw]
    elif trace.op == "AND":
        found = [
            raw
            for child in trace.children
            if not child.result
            for raw in blocking_predicates(child)
        ]
    elif trace.op == "OR":
        found = [raw for child in trace.children for raw in blocking_predicates(child)]
    elif trace.op == "NOT":
        child = trace.children[0]
        if child.is_leaf:
            found = [trace.raw]
        else:
            found = ["NOT(" + "|".join(_true_leaf_raws(child)) + ")"]
    else:
        raise ValueError(f"Unknown condition trace op {trace.op!r}")
    return list(dict.fromkeys(found))


def _leaves(condition: Condition) -> Iterator[Condition]:
    """Yield the leaf predicates of a condition tree in order."""

    if isinstance(condition, CompoundCondition):
        for child in condition.children:
            yield from _leaves(child)
    else:
        yield condition


def socialize_gate_threshold(templates: Sequence[Template], state: WorldState) -> float:
    """Read the socialize package gate's need-debt threshold from its leaf."""

    socialize = _template_by_id(templates, "socialize")
    leaves = [
        leaf
        for leaf in _leaves(socialize.package_gate)
        if getattr(leaf, "__name__", "").startswith(_SOCIALIZE_DEBT_PREFIX)
    ]
    if len(leaves) != 1:
        raise RuntimeError(
            "Expected exactly one socialize need-debt leaf in the socialize "
            f"package gate; found {len(leaves)}"
        )
    evidence = resolve_evidence(leaves[0].__name__, state, {})
    return float(evidence["params"]["threshold"])


@dataclass(frozen=True)
class _OrrerySettings:
    """The ``[orrery]`` sections the audit dashboard passes to hydration."""

    sections: Mapping[str, Any]

    @property
    def window_chunks(self) -> int:
        """Return ``[orrery.binding] window_chunks``."""

        return int(self.sections["binding"]["window_chunks"])

    def get(self, name: str) -> Any:
        """Return one ``[orrery]`` subsection, or ``None`` when absent."""

        return self.sections.get(name)


def _load_orrery_settings() -> _OrrerySettings:
    """Read ``[orrery]`` from ``nexus.toml`` as the audit endpoints do."""

    orrery = load_settings_as_dict().get("orrery")
    if not orrery:
        raise RuntimeError(
            "nexus.toml has no [orrery] section; the travel reachability probe "
            "cannot hydrate without binding and sunhelm configuration"
        )
    return _OrrerySettings(orrery)


def _default_anchor_chunk_id(session: Session) -> int:
    """Return the newest playable chunk id, as the audit dashboard does."""

    row = (
        session.execute(
            text(
                "SELECT max(nc.id) AS max_id FROM narrative_chunks nc WHERE "
                + playable_narrative_predicate("nc")
            )
        )
        .mappings()
        .first()
    )
    if row is None or row["max_id"] is None:
        raise RuntimeError("The database has no playable narrative chunk to anchor on")
    return int(row["max_id"])


def _scalar(session: Session, sql: str) -> int:
    """Return one integer from a read-only aggregate query."""

    return int(session.execute(text(sql)).scalar_one())


def _active_characters(session: Session) -> list[tuple[int, str]]:
    """Return every active character entity as ``(entity_id, name)``."""

    rows = session.execute(
        text(
            """
            SELECT c.entity_id, c.name
            FROM characters c
            JOIN entities e ON e.id = c.entity_id
            WHERE e.is_active
            ORDER BY c.entity_id
            """
        )
    ).mappings()
    return [(int(row["entity_id"]), str(row["name"])) for row in rows]


def _social_class_place_count(state: WorldState) -> int:
    """Count places whose hydrated classes include a social destination class."""

    place_ids = set(state.location_classes) | set(state.location_class)
    count = 0
    for place_id in place_ids:
        classes = set(state.location_classes.get(place_id, frozenset()))
        primary = state.location_class.get(place_id)
        if primary is not None:
            classes.add(primary)
        if SOCIAL_DESTINATION_CLASSES & classes:
            count += 1
    return count


def _substrate(
    session: Session,
    state: WorldState,
    templates: Sequence[Template],
    actors: Sequence[tuple[int, str]],
    roster_size: int,
) -> dict[str, Any]:
    """Return the per-database substrate summary of item 4."""

    travel_rows_by_status = {
        str(row["status"]): int(row["count"])
        for row in session.execute(
            text(
                """
                SELECT status::text AS status, count(*) AS count
                FROM character_travel_states
                GROUP BY status
                ORDER BY status
                """
            )
        ).mappings()
    }
    socialize_debts = [
        float(score)
        for (_, need), score in state.need_debt_scores.items()
        if need == "socialize"
    ]
    return {
        "active_characters": len(actors),
        "with_current_location": sum(
            1 for entity_id, _ in actors if entity_id in state.locations
        ),
        "places": _scalar(session, "SELECT count(*) FROM places"),
        "social_class_places": _social_class_place_count(state),
        "routine_anchors": _scalar(
            session, "SELECT count(*) FROM character_routine_anchors"
        ),
        "travel_rows_by_status": travel_rows_by_status,
        "open_plan_relocation_projects": _scalar(
            session,
            """
            SELECT count(*) FROM character_project_states
            WHERE project_type = 'plan_relocation'
              AND status IN ('active', 'paused', 'stalled')
            """,
        ),
        "max_socialize_debt": max(socialize_debts) if socialize_debts else None,
        "socialize_gate_threshold": socialize_gate_threshold(templates, state),
        "roster_size": roster_size,
    }


def probe_database(dbname: str, anchor_chunk_id: Optional[int]) -> dict[str, Any]:
    """Probe one database in one read-only snapshot and return its report."""

    orrery = _load_orrery_settings()
    window_chunks = orrery.window_chunks
    need_tuning = coerce_need_tuning(orrery.get("sunhelm"))
    selection = coerce_branch_selection(orrery.get("selection"))
    habituation = coerce_habituation(orrery.get("habituation"))
    package_selection = coerce_package_selection(orrery.get("package_selection"))
    project_policy = coerce_project_policy(orrery.get("projects"))
    epistemics_settings = orrery.get("epistemics")
    epistemics_policy = (
        load_epistemics_policy()
        if epistemics_settings is None
        else coerce_epistemics_policy(epistemics_settings)
    )
    templates = tuple(configure_project_magnitudes(BUILTIN_TEMPLATES, project_policy))
    rows = probed_rows(templates)
    actor_only_templates = [
        template
        for template in templates
        if template.required_slots == _ACTOR_ONLY_SLOTS
    ]

    with read_only_session(dbname) as session:
        anchor = (
            anchor_chunk_id
            if anchor_chunk_id is not None
            else _default_anchor_chunk_id(session)
        )
        logger.info("Probing %s at anchor chunk %s", dbname, anchor)
        state = hydrate_world_state(
            session,
            anchor_chunk_id=anchor,
            window_chunks=window_chunks,
            need_tuning=need_tuning,
            world_time_override=None,
            win_history_window=habituation.window_ticks if habituation.enabled else 0,
            project_settings=orrery.get("projects"),
            epistemics_settings=epistemics_policy,
            contagion_settings=orrery.get("contagion"),
            weather_settings=orrery.get("weather"),
            mood_settings=orrery.get("mood"),
            resolver_settings=orrery.get("resolver"),
        )
        roster = compose_actor_bindings(
            session, anchor_chunk_id=anchor, window_chunks=window_chunks
        )
        roster_bindings: dict[int, Bindings] = {
            int(bindings[Slot.ACTOR]): bindings for bindings in roster
        }
        actors = _active_characters(session)
        unknown = set(roster_bindings) - {entity_id for entity_id, _ in actors}
        if unknown:
            raise RuntimeError(
                f"The roster of {dbname!r} holds entities that are not active "
                f"characters: {sorted(unknown)!r}"
            )
        substrate = _substrate(session, state, templates, actors, len(roster))

        actor_reports: list[dict[str, Any]] = []
        for entity_id, name in actors:
            bindings = roster_bindings.get(entity_id, {Slot.ACTOR: entity_id})
            stack: Optional[StackExplanation] = None
            row_reports: list[dict[str, Any]] = []
            for template_id, label in rows:
                template = _template_by_id(templates, template_id)
                branch = _branch_by_label(template, label)
                gate = trace_condition(template.package_gate, state, bindings)
                branch_trace = trace_condition(branch.conditions, state, bindings)
                winner_id: Optional[str] = None
                window_ids: Optional[list[str]] = None
                if gate.result and branch_trace.result:
                    if stack is None:
                        stack = explain_stack(
                            actor_only_templates,
                            state,
                            bindings,
                            selection,
                            habituation,
                            package_selection,
                        )
                    winner_id = stack.winner_id
                    window_ids = list(stack.selection_window_ids)
                row_reports.append(
                    {
                        "template_id": template_id,
                        "label": label,
                        "gate_passed": gate.result,
                        "branch_passed": branch_trace.result,
                        "gate_blockers": (
                            [] if gate.result else blocking_predicates(gate)
                        ),
                        "branch_blockers": (
                            []
                            if branch_trace.result
                            else blocking_predicates(branch_trace)
                        ),
                        "winner_id": winner_id,
                        "selection_window_ids": window_ids,
                    }
                )
            actor_reports.append(
                {
                    "entity_id": entity_id,
                    "name": name,
                    "in_roster": entity_id in roster_bindings,
                    "rows": row_reports,
                }
            )

    return {
        "dbname": dbname,
        "anchor_chunk_id": anchor,
        "anchor_world_time": (
            state.world_time.isoformat() if state.world_time is not None else None
        ),
        "substrate": substrate,
        "rows": [{"template_id": tid, "label": label} for tid, label in rows],
        "actors": actor_reports,
    }


def _ranked(counter: Counter[str]) -> str:
    """Render ``name (n)`` entries by count descending, then name."""

    ordered = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return "; ".join(f"{name} ({count})" for name, count in ordered)


def _cell(value: str) -> str:
    """Escape a Markdown table cell."""

    return value.replace("|", "\\|")


def _format_debt(value: Optional[float]) -> str:
    """Render a debt in hours, or ``none`` when no debt was hydrated."""

    return "none" if value is None else f"{value:.2f}"


def render_markdown(report: Mapping[str, Any]) -> str:
    """Render the probe report as Markdown, roster actors only."""

    sections: list[str] = []
    for database in report["databases"]:
        substrate = database["substrate"]
        travel = substrate["travel_rows_by_status"]
        travel_text = (
            ", ".join(f"{status} {count}" for status, count in travel.items())
            if travel
            else "0"
        )
        substrate_line = "; ".join(
            [
                f"anchor chunk: {database['anchor_chunk_id']} "
                f"({database['anchor_world_time']})",
                f"active characters: {substrate['active_characters']}",
                f"with current_location: {substrate['with_current_location']}",
                f"places: {substrate['places']}",
                f"social-class places: {substrate['social_class_places']}",
                f"routine anchors: {substrate['routine_anchors']}",
                f"travel rows: {travel_text}",
                "open plan_relocation projects: "
                f"{substrate['open_plan_relocation_projects']}",
                "max socialize debt: "
                f"{_format_debt(substrate['max_socialize_debt'])} "
                f"(gate {substrate['socialize_gate_threshold']:g})",
                f"roster: {substrate['roster_size']}",
            ]
        )
        lines = [
            f"### {database['dbname']}",
            "",
            substrate_line,
            "",
            "| Row | Roster actors | Gate passes | Branch passes | Both pass "
            "| Blocking predicates | Winners when both pass |",
            "|---|---|---|---|---|---|---|",
        ]
        roster_actors = [actor for actor in database["actors"] if actor["in_roster"]]
        for index, row in enumerate(database["rows"]):
            gate_passes = branch_passes = both_pass = 0
            blockers: Counter[str] = Counter()
            winners: Counter[str] = Counter()
            for actor in roster_actors:
                actor_row = actor["rows"][index]
                gate_passes += int(actor_row["gate_passed"])
                branch_passes += int(actor_row["branch_passed"])
                if actor_row["gate_passed"] and actor_row["branch_passed"]:
                    both_pass += 1
                    winners[str(actor_row["winner_id"])] += 1
                blockers.update(
                    dict.fromkeys(
                        actor_row["gate_blockers"] + actor_row["branch_blockers"], 1
                    )
                )
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(f"{row['template_id']} / {row['label']}"),
                        str(len(roster_actors)),
                        str(gate_passes),
                        str(branch_passes),
                        str(both_pass),
                        _cell(_ranked(blockers)),
                        _cell(_ranked(winners)),
                    ]
                )
                + " |"
            )
        sections.append("\n".join(lines))
    return "\n\n".join(sections) + "\n"


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    """Parse and validate the command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dbname",
        action="append",
        required=True,
        help="Database to probe; repeat for several.",
    )
    parser.add_argument(
        "--anchor-chunk-id",
        type=int,
        help="Anchor chunk id (only with a single --dbname); default newest playable.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print one JSON document instead of Markdown.",
    )
    args = parser.parse_args(argv)
    if args.anchor_chunk_id is not None and len(args.dbname) != 1:
        parser.error("--anchor-chunk-id is allowed only with one --dbname")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Probe every requested database and print the report to stdout."""

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args(argv)
    report = {
        "databases": [
            probe_database(dbname, args.anchor_chunk_id) for dbname in args.dbname
        ]
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
