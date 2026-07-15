"""Batch coverage analysis for Orrery packages over historical anchors.

The audit dashboard's health strip and the spec's coverage analyzer are the
same tool (docs/orrery_audit_dashboard_notes.md): run the explained resolver
across a window of historical chunks and aggregate what actually happens —
actors no package ever fires for, packages that never (or always) win,
branches never chosen, the statically dead gate arms, and slot data-quality
findings (NULL bestowal world times, wall-clock backfill epochs).

Honesty: hydration at a historical anchor rewinds only recent events, the
clock, the actor roster, and the need-debt accrual tail; tags, pair tags,
relationships, positions, travel, and routine anchors are **current
projections**. Every payload carries :data:`HYDRATION_HONESTY` verbatim so
the UI can render the per-axis label instead of implying a clean rewind.

Never-chosen branches here mean "never selected across the analyzed window."
That is weaker than "dead behind its gate" (which needs exhaustive branch
traces — branch evaluation stops at the first passing branch) but is the
correct first-order signal for authored-magnitude ladders.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import text

from nexus.agents.orrery.audit import (
    ActorGroupExplanation,
    ExplainedTickReport,
    build_catalog,
    explain_dry_run,
)
from nexus.agents.orrery.explain import StackExplanation
from nexus.agents.orrery.reconstruction import playable_narrative_predicate
from nexus.agents.orrery.substrate import Template

HYDRATION_HONESTY: Mapping[str, Tuple[str, ...]] = {
    "rewound_to_anchor": (
        "recent_events",
        "world_time",
        "time_of_day",
        "actor_roster",
        "need_debt_accrual",
    ),
    "current_projection": (
        "tags",
        "pair_tags",
        "relationships",
        "trust",
        "positions",
        "activities",
        "travel_states",
        "project_states",
        "routine_anchors",
        "faction_memberships",
        "weather",
    ),
}


@dataclass
class _TemplateTally:
    drive_band: str
    arity: str
    branch_labels: Tuple[str, ...]
    evaluated: int = 0
    gate_passed: int = 0
    fired: int = 0
    won: int = 0
    # Present-target pressure stacks tallied separately: their winners are
    # prompt pressures, not resolutions, so they must not blur the
    # resolution-side reconciliation — but a pressure firing is still a
    # firing for never-fired and gap purposes.
    pressure_evaluated: int = 0
    pressure_fired: int = 0
    pressure_won: int = 0

    def __post_init__(self) -> None:
        self.branch_chosen: dict[str, int] = {label: 0 for label in self.branch_labels}


def sample_anchor_ids(
    session: Any,
    *,
    count: int,
    stride: int,
    end_chunk_id: Optional[int] = None,
) -> List[int]:
    """Return player-played chunk ids walking backward from the end.

    Chunk ids may have gaps, so sampling selects every ``stride``-th existing
    playable chunk rather than assuming contiguous ids. Returned ascending.
    """

    if count < 1:
        raise ValueError(f"anchor sample count must be >= 1, got {count}")
    if stride < 1:
        raise ValueError(f"anchor sample stride must be >= 1, got {stride}")
    end_clause = "AND nc.id <= :end_chunk_id" if end_chunk_id is not None else ""
    params: dict[str, Any] = {"stride": stride, "limit": count}
    if end_chunk_id is not None:
        params["end_chunk_id"] = end_chunk_id
    # Stride inside SQL so only `count` ids ever reach Python — a large
    # stride must not scale the fetched row set (review finding on #423).
    rows = session.execute(
        text(
            f"""
            /* orrery_coverage:sample_anchors */
            SELECT id FROM (
                SELECT nc.id,
                       row_number() OVER (ORDER BY nc.id DESC) AS rn
                FROM narrative_chunks nc
                WHERE {playable_narrative_predicate("nc")}
                {end_clause}
            ) ordered
            WHERE mod(rn - 1, :stride) = 0
            ORDER BY id DESC
            LIMIT :limit
            """
        ),
        params,
    ).scalars()
    return sorted(rows)


def _resolution_stacks(
    group: ActorGroupExplanation,
) -> Iterable[StackExplanation]:
    """The stacks whose winners become resolutions (pressure stacks excluded)."""

    yield group.actor_stack
    yield from group.two_party_stacks


def _tally_report(
    report: ExplainedTickReport,
    tallies: dict[str, _TemplateTally],
    gap_counts: dict[int, dict[str, int]],
) -> dict[str, Any]:
    winners_by_band: dict[str, int] = {}
    gap_actor_ids: list[int] = []
    project_gates: list[dict[str, Any]] = []
    resolution_winners: list[dict[str, Any]] = []
    for group in report.actors:
        fired_anywhere = False
        for stack in _resolution_stacks(group):
            for item in stack.templates:
                tally = tallies[item.template_id]
                tally.evaluated += 1
                if item.gate_passed:
                    tally.gate_passed += 1
                if item.fired:
                    fired_anywhere = True
                    tally.fired += 1
                    if item.chosen_branch is not None:
                        tally.branch_chosen[item.chosen_branch] += 1
                if item.template_id == stack.winner_id:
                    tally.won += 1
                    winners_by_band[item.drive_band] = (
                        winners_by_band.get(item.drive_band, 0) + 1
                    )
                    resolution_winners.append(
                        {
                            "actor_entity_id": stack.bindings.get("actor"),
                            "target_entity_id": stack.bindings.get("target"),
                            "template_id": item.template_id,
                            "drive_band": item.drive_band,
                            "promotable": item.promotable,
                        }
                    )
                if item.template_id in {
                    "start_relocation_plan",
                    "advance_relocation_plan",
                }:
                    project_gates.append(
                        {
                            "actor_entity_id": group.actor_entity_id,
                            "template_id": item.template_id,
                            "gate_passed": item.gate_passed,
                            "stack_winner_id": stack.winner_id,
                            "gate_trace": item.gate_trace.to_dict(),
                        }
                    )
        for stack in group.scene_pressure_stacks:
            for item in stack.templates:
                tally = tallies[item.template_id]
                tally.pressure_evaluated += 1
                if item.fired:
                    fired_anywhere = True
                    tally.pressure_fired += 1
                if item.template_id == stack.winner_id:
                    tally.pressure_won += 1
        actor_gaps = gap_counts.setdefault(
            group.actor_entity_id, {"seen_anchors": 0, "gapped_anchors": 0}
        )
        actor_gaps["seen_anchors"] += 1
        if not fired_anywhere:
            actor_gaps["gapped_anchors"] += 1
            gap_actor_ids.append(group.actor_entity_id)

    return {
        "anchor_chunk_id": report.anchor_chunk_id,
        "world_time": (
            report.world_time.isoformat() if report.world_time is not None else None
        ),
        "time_of_day": report.time_of_day,
        "actor_count": report.actor_count,
        "winners_by_band": winners_by_band,
        "gap_actor_ids": gap_actor_ids,
        "need_pressure_count": len(report.need_pressures),
        "project_gates": project_gates,
        "resolution_winners": resolution_winners,
    }


def _data_quality_findings(
    session: Any, *, epoch_min_world_times: int
) -> dict[str, Any]:
    """Slot data-quality findings for the health strip.

    NULL bestowal world times make per-row as-of provenance "unknowable";
    a wall-clock instant carrying many distinct world times is the signature
    of a retrograde backfill epoch (months of world time written at once) —
    the standing reason wall clocks must never be used as chunk proxies.
    """

    null_bestowals = [
        dict(row)
        for row in session.execute(
            text(
                """
                /* orrery_coverage:null_world_time_bestowals */
                SELECT 'entity_tags' AS bestowal_table,
                       source_kind::text AS source_kind,
                       count(*) FILTER (WHERE applied_at_world_time IS NULL)
                           AS null_world_time_rows,
                       count(*) AS active_rows
                FROM entity_tags
                WHERE cleared_at IS NULL
                GROUP BY source_kind
                UNION ALL
                SELECT 'entity_pair_tags',
                       source_kind::text,
                       count(*) FILTER (WHERE applied_at_world_time IS NULL),
                       count(*)
                FROM entity_pair_tags
                WHERE cleared_at IS NULL
                GROUP BY source_kind
                ORDER BY bestowal_table, source_kind
                """
            )
        ).mappings()
    ]

    epochs = [
        {
            "bestowal_table": row["bestowal_table"],
            "wall_clock_instant": row["wall_clock_instant"].isoformat(),
            "rows": row["rows"],
            "distinct_world_times": row["distinct_world_times"],
            "world_time_span": (
                [
                    row["min_world_time"].isoformat(),
                    row["max_world_time"].isoformat(),
                ]
                if row["min_world_time"] is not None
                else None
            ),
        }
        for row in session.execute(
            text(
                """
                /* orrery_coverage:wall_clock_epochs */
                SELECT bestowal_table,
                       wall_clock_instant,
                       rows,
                       distinct_world_times,
                       min_world_time,
                       max_world_time
                FROM (
                    SELECT 'entity_tags' AS bestowal_table,
                           date_trunc('second', applied_at) AS wall_clock_instant,
                           count(*) AS rows,
                           count(DISTINCT applied_at_world_time)
                               AS distinct_world_times,
                           min(applied_at_world_time) AS min_world_time,
                           max(applied_at_world_time) AS max_world_time
                    FROM entity_tags
                    WHERE applied_at_world_time IS NOT NULL
                    GROUP BY 2
                    UNION ALL
                    SELECT 'entity_pair_tags',
                           date_trunc('second', applied_at),
                           count(*),
                           count(DISTINCT applied_at_world_time),
                           min(applied_at_world_time),
                           max(applied_at_world_time)
                    FROM entity_pair_tags
                    WHERE applied_at_world_time IS NOT NULL
                    GROUP BY 2
                ) grouped
                WHERE distinct_world_times >= :epoch_min
                ORDER BY rows DESC
                """
            ),
            {"epoch_min": epoch_min_world_times},
        ).mappings()
    ]

    return {
        "null_world_time_bestowals": null_bestowals,
        "wall_clock_epochs": epochs,
        "epoch_min_world_times": epoch_min_world_times,
    }


def analyze_coverage(
    session: Any,
    templates: Sequence[Template],
    *,
    anchor_chunk_ids: Sequence[int],
    window_chunks: int,
    sunhelm_settings: Optional[Any] = None,
    epoch_min_world_times: int,
    selection_settings: Optional[Any] = None,
    habituation_settings: Optional[Any] = None,
    package_selection_settings: Optional[Any] = None,
    project_settings: Optional[Any] = None,
    fanout_settings: Optional[Any] = None,
) -> dict[str, Any]:
    """Aggregate explained resolution coverage across historical anchors.

    Runs :func:`explain_dry_run` once per anchor (production-parity by
    construction) and aggregates winner/fired/gate statistics per template,
    branch-selection counts, per-actor gap counts, per-anchor band tallies,
    the static dead-gate-arm lint, and slot data-quality findings.
    """

    if not anchor_chunk_ids:
        raise ValueError("analyze_coverage requires at least one anchor chunk id")

    templates_tuple = tuple(templates)
    catalog = build_catalog(templates_tuple)
    arity_by_id = {
        payload["template_id"]: payload["arity"]
        for band in catalog["drive_bands"]
        for payload in band["templates"]
    }
    tallies = {
        template.id: _TemplateTally(
            drive_band=template.drive_band.value,
            arity=arity_by_id[template.id],
            branch_labels=tuple(branch.label for branch in template.branches),
        )
        for template in templates_tuple
    }

    gap_counts: dict[int, dict[str, int]] = {}
    entity_names: dict[int, str] = {}
    anchors: list[dict[str, Any]] = []
    for anchor_chunk_id in anchor_chunk_ids:
        report = explain_dry_run(
            session,
            templates_tuple,
            anchor_chunk_id=anchor_chunk_id,
            window_chunks=window_chunks,
            sunhelm_settings=sunhelm_settings,
            selection_settings=selection_settings,
            habituation_settings=habituation_settings,
            package_selection_settings=package_selection_settings,
            project_settings=project_settings,
            fanout_settings=fanout_settings,
        )
        anchors.append(_tally_report(report, tallies, gap_counts))
        entity_names.update(report.entity_names)

    template_payloads = {
        template_id: {
            "drive_band": tally.drive_band,
            "arity": tally.arity,
            "evaluated": tally.evaluated,
            "gate_passed": tally.gate_passed,
            "fired": tally.fired,
            "won": tally.won,
            "pressure_evaluated": tally.pressure_evaluated,
            "pressure_fired": tally.pressure_fired,
            "pressure_won": tally.pressure_won,
            "branch_chosen": dict(tally.branch_chosen),
            "branch_promotable": {
                branch.label: branch.promotable
                for branch in next(
                    template
                    for template in templates_tuple
                    if template.id == template_id
                ).branches
            },
            "branch_labels_never_chosen": [
                label for label, chosen in tally.branch_chosen.items() if chosen == 0
            ],
        }
        for template_id, tally in tallies.items()
    }

    gap_actors = [
        {
            "entity_id": entity_id,
            "name": entity_names.get(entity_id),
            "seen_anchors": counts["seen_anchors"],
            "gapped_anchors": counts["gapped_anchors"],
        }
        for entity_id, counts in sorted(gap_counts.items())
        if counts["gapped_anchors"] > 0
    ]

    dead_gate_arms = {
        event_type: {
            "consumed_by_gate": entry["consumed_by_gate"],
            "consumed_by_branch": entry["consumed_by_branch"],
        }
        for event_type, entry in sorted(catalog["event_map"].items())
        if entry["exogenous_only"]
    }

    return {
        "anchor_chunk_ids": list(anchor_chunk_ids),
        "window_chunks": window_chunks,
        "anchors": anchors,
        "templates": template_payloads,
        "never_fired": sorted(
            template_id for template_id, tally in tallies.items() if tally.fired == 0
        ),
        "fired_never_won": sorted(
            template_id
            for template_id, tally in tallies.items()
            if tally.fired > 0 and tally.won == 0
        ),
        "always_won_when_fired": sorted(
            template_id
            for template_id, tally in tallies.items()
            if tally.fired > 0 and tally.won == tally.fired
        ),
        "gap_actors": gap_actors,
        "dead_gate_arms": dead_gate_arms,
        "data_quality": _data_quality_findings(
            session, epoch_min_world_times=epoch_min_world_times
        ),
        "hydration_honesty": {
            axis: list(fields) for axis, fields in HYDRATION_HONESTY.items()
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
