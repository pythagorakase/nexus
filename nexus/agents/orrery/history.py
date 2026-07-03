"""Adjudication history for the Orrery audit dashboard.

Aggregates the persisted decision ledger — how often Skald defers, replaces,
or voids each package (always faceted by adjudication source: machine-inferred
``structured_state_update`` replaces are not authored rulings), the lifecycle
funnel from committed resolution through promotion to narration, and the
single most diagnostic derived metric: **defer streaks** (how many consecutive
rulings a proposal absorbed before ratification, replacement, void, or its
streak is still open).

Epoch honesty: rows written before migration 063 lack ``actor_entity_id`` /
``bindings`` on the log, and prompt exposures / scene pressures exist only for
ticks committed after 063. The payload's ``epoch`` block quantifies exactly
how much of the ledger is enriched rather than implying full coverage.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import text

from nexus.agents.orrery.resolver import _entity_label, _load_entity_names

_ACTIONS = ("defer", "replace", "void")


def _streaks_for_proposal(
    proposal_id: str,
    template_id: str,
    actor_entity_id: Optional[int],
    timeline: List[tuple[int, str]],
) -> List[dict[str, Any]]:
    """Walk one proposal's merged ruling/commit timeline into defer streaks.

    ``timeline`` is (tick, event) ascending, where event is a log action or
    the synthetic ``committed``. A streak is a run of consecutive ``defer``
    entries; whatever ends it is the outcome, and a run nothing has ended yet
    is ``open``.
    """

    streaks: List[dict[str, Any]] = []
    run_start: Optional[int] = None
    run_end: Optional[int] = None
    run_length = 0
    for tick, event in timeline:
        if event == "defer":
            if run_start is None:
                run_start = tick
            run_end = tick
            run_length += 1
            continue
        if run_length:
            streaks.append(
                {
                    "proposal_id": proposal_id,
                    "template_id": template_id,
                    "actor_entity_id": actor_entity_id,
                    "length": run_length,
                    "start_tick": run_start,
                    "end_tick": run_end,
                    "outcome": "ratified" if event == "committed" else event,
                    "outcome_tick": tick,
                }
            )
            run_start, run_end, run_length = None, None, 0
    if run_length:
        streaks.append(
            {
                "proposal_id": proposal_id,
                "template_id": template_id,
                "actor_entity_id": actor_entity_id,
                "length": run_length,
                "start_tick": run_start,
                "end_tick": run_end,
                "outcome": "open",
                "outcome_tick": None,
            }
        )
    return streaks


def adjudication_history(
    session: Any,
    *,
    template_id: Optional[str] = None,
) -> dict[str, Any]:
    """Return the adjudication-history payload for one slot.

    Read-only. ``template_id`` narrows every block to one package.
    """

    template_clause = "WHERE template_id = :template_id" if template_id else ""
    params: dict[str, Any] = {"template_id": template_id} if template_id else {}

    log_rows = [
        dict(row)
        for row in session.execute(
            text(
                f"""
                /* orrery_history:adjudication_log */
                SELECT tick_chunk_id, proposal_id, template_id, binding_hash,
                       action, adjudication_source, skald_note,
                       applied_resolution_id, actor_entity_id, bindings
                FROM orrery_adjudication_log
                {template_clause}
                ORDER BY proposal_id, tick_chunk_id, id
                """
            ),
            params,
        ).mappings()
    ]

    resolution_rows = [
        dict(row)
        for row in session.execute(
            text(
                f"""
                /* orrery_history:resolutions */
                SELECT tick_chunk_id, template_id, binding_hash,
                       actor_entity_id, promotion_status::text
                           AS promotion_status,
                       narration_status::text AS narration_status
                FROM orrery_resolutions
                {template_clause}
                ORDER BY template_id, binding_hash, tick_chunk_id
                """
            ),
            params,
        ).mappings()
    ]

    exposure_stats = session.execute(
        text(
            f"""
            /* orrery_history:exposures */
            SELECT kind,
                   count(*) AS rows,
                   min(tick_chunk_id) AS earliest_tick
            FROM orrery_prompt_exposures
            {template_clause}
            GROUP BY kind
            """
        ),
        params,
    ).mappings()
    exposures = {
        row["kind"]: {"rows": row["rows"], "earliest_tick": row["earliest_tick"]}
        for row in exposure_stats
    }

    pressure_stats = (
        session.execute(
            text(
                f"""
                /* orrery_history:scene_pressures */
                SELECT count(*) AS rows, min(tick_chunk_id) AS earliest_tick
                FROM orrery_scene_pressures
                {template_clause}
                """
            ),
            params,
        )
        .mappings()
        .one()
    )

    # --- Per-template action and funnel aggregation -------------------------
    templates: dict[str, dict[str, Any]] = {}

    def _template_entry(entry_template_id: str) -> dict[str, Any]:
        return templates.setdefault(
            entry_template_id,
            {
                "actions": {action: {} for action in _ACTIONS},
                "committed": 0,
                "promoted": 0,
                "promotion_skipped": 0,
                "promotion_pending": 0,
                "narrated": 0,
                "replaced_with_delta_committed": 0,
            },
        )

    for row in log_rows:
        entry = _template_entry(row["template_id"])
        sources = entry["actions"][row["action"]]
        sources[row["adjudication_source"]] = (
            sources.get(row["adjudication_source"], 0) + 1
        )
        if row["action"] == "replace" and row["applied_resolution_id"] is not None:
            entry["replaced_with_delta_committed"] += 1

    for row in resolution_rows:
        entry = _template_entry(row["template_id"])
        entry["committed"] += 1
        if row["promotion_status"] == "promoted":
            entry["promoted"] += 1
        elif row["promotion_status"] == "skipped":
            entry["promotion_skipped"] += 1
        else:
            entry["promotion_pending"] += 1
        if row["narration_status"] == "succeeded":
            entry["narrated"] += 1

    for entry in templates.values():
        # Ratification is by omission and leaves no log row; a committed
        # resolution is a ratification unless a replace-with-delta produced it.
        entry["ratified_committed"] = (
            entry["committed"] - entry["replaced_with_delta_committed"]
        )

    # --- Defer streaks -------------------------------------------------------
    commits_by_proposal: dict[str, List[tuple[int, str]]] = {}
    actor_by_proposal: dict[str, Optional[int]] = {}
    for row in resolution_rows:
        proposal_id = f"{row['template_id']}:{row['binding_hash']}"
        commits_by_proposal.setdefault(proposal_id, []).append(
            (row["tick_chunk_id"], "committed")
        )
        if row["actor_entity_id"] is not None:
            actor_by_proposal.setdefault(proposal_id, row["actor_entity_id"])

    timelines: dict[str, List[tuple[int, str]]] = {}
    template_by_proposal: dict[str, str] = {}
    for row in log_rows:
        proposal_id = row["proposal_id"]
        template_by_proposal[proposal_id] = row["template_id"]
        timelines.setdefault(proposal_id, []).append(
            (row["tick_chunk_id"], row["action"])
        )
        if row["actor_entity_id"] is not None:
            actor_by_proposal.setdefault(proposal_id, row["actor_entity_id"])

    defer_streaks: List[dict[str, Any]] = []
    for proposal_id, timeline in timelines.items():
        merged = sorted(
            timeline + commits_by_proposal.get(proposal_id, []),
            key=lambda item: item[0],
        )
        defer_streaks.extend(
            _streaks_for_proposal(
                proposal_id,
                template_by_proposal[proposal_id],
                actor_by_proposal.get(proposal_id),
                merged,
            )
        )
    defer_streaks.sort(key=lambda item: (-item["length"], item["proposal_id"]))

    # --- Names and epoch honesty --------------------------------------------
    entity_ids = {
        actor_id for actor_id in actor_by_proposal.values() if actor_id is not None
    }
    entity_names = _load_entity_names(session, entity_ids) if entity_ids else {}
    for streak in defer_streaks:
        streak["actor_name"] = (
            _entity_label(streak["actor_entity_id"], entity_names)
            if streak["actor_entity_id"] is not None
            else None
        )

    enriched_log_rows = sum(1 for row in log_rows if row["actor_entity_id"] is not None)

    totals_actions: dict[str, int] = {action: 0 for action in _ACTIONS}
    totals_sources: dict[str, int] = {}
    for row in log_rows:
        totals_actions[row["action"]] += 1
        totals_sources[row["adjudication_source"]] = (
            totals_sources.get(row["adjudication_source"], 0) + 1
        )

    return {
        "template_filter": template_id,
        "totals": {
            "log_rows": len(log_rows),
            "actions": totals_actions,
            "sources": totals_sources,
            "committed_resolutions": len(resolution_rows),
        },
        "templates": templates,
        "defer_streaks": defer_streaks,
        "exposures": {
            "resolution": exposures.get(
                "resolution", {"rows": 0, "earliest_tick": None}
            ),
            "scene_pressure": exposures.get(
                "scene_pressure", {"rows": 0, "earliest_tick": None}
            ),
        },
        "scene_pressures": {
            "rows": pressure_stats["rows"],
            "earliest_tick": pressure_stats["earliest_tick"],
        },
        "entity_names": {
            str(entity_id): name for entity_id, name in entity_names.items()
        },
        "epoch": {
            # Pre-063 rows have no subject; consumers must not read absence
            # of actor_entity_id as "no actor".
            "log_rows_with_subject": enriched_log_rows,
            "log_rows_total": len(log_rows),
            "exposure_logging_since_tick": min(
                (
                    block["earliest_tick"]
                    for block in exposures.values()
                    if block["earliest_tick"] is not None
                ),
                default=None,
            ),
            "scene_pressure_logging_since_tick": pressure_stats["earliest_tick"],
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
