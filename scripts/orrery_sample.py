"""Dry-run sample Orrery's resolver at an arbitrary chunk anchor.

Captures the full evaluation ledger including pertinent negatives
(gate-fails, no-branch-matches, priority-losses) that the production
resolver discards. Used for tire-kicking and bug hunts against slot 2.

Usage:
    python scripts/orrery_sample.py --slot 2 --anchor 100
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.orrery.resolver import (
    compose_actor_bindings,
    compose_actor_target_bindings,
    hydrate_world_state,
)
from nexus.agents.orrery.substrate import PresentTargetPolicy, Slot, evaluate
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
from nexus.api.slot_utils import get_slot_db_url
from nexus.config import load_settings_as_dict


ACTOR_ONLY_SLOTS = (Slot.ACTOR,)
ACTOR_TARGET_SLOTS = (Slot.ACTOR, Slot.TARGET)


@dataclass
class LedgerEntry:
    template_id: str
    priority: int
    outcome: str  # 'fired' | 'priority_loss' | 'no_branch_match' | 'gate_fail'
    branch_label: Optional[str] = None
    narrative_stub: Optional[str] = None
    state_delta: Optional[dict] = None
    event_type: Optional[str] = None
    magnitude: float = 0.0


@dataclass
class BindingReport:
    bindings: dict
    slot_kind: str  # 'actor_only' | 'actor_target'
    ledger: list[LedgerEntry] = field(default_factory=list)


def categorize_results(templates, state, bindings) -> list[LedgerEntry]:
    """Evaluate each template against bindings; return full ledger.

    Templates are processed in priority-descending order. The first passer
    is 'fired'; subsequent passers are 'priority_loss'. Non-passers are
    disambiguated as 'gate_fail' (package_gate False) or 'no_branch_match'
    (gate True but no branch's conditions matched).
    """
    ledger: list[LedgerEntry] = []
    has_fired = False
    for template in sorted(templates, key=lambda t: t.priority, reverse=True):
        resolution = evaluate(template, state, bindings)
        if resolution.passes:
            if not has_fired:
                ledger.append(
                    LedgerEntry(
                        template_id=template.id,
                        priority=template.priority,
                        outcome="fired",
                        branch_label=resolution.branch_label,
                        narrative_stub=resolution.narrative_stub,
                        state_delta=dict(resolution.state_delta),
                        event_type=resolution.event_type,
                        magnitude=resolution.magnitude,
                    )
                )
                has_fired = True
            else:
                ledger.append(
                    LedgerEntry(
                        template_id=template.id,
                        priority=template.priority,
                        outcome="priority_loss",
                        branch_label=resolution.branch_label,
                        narrative_stub=resolution.narrative_stub,
                        magnitude=resolution.magnitude,
                    )
                )
        else:
            if template.package_gate(state, bindings):
                ledger.append(
                    LedgerEntry(
                        template_id=template.id,
                        priority=template.priority,
                        outcome="no_branch_match",
                    )
                )
            else:
                ledger.append(
                    LedgerEntry(
                        template_id=template.id,
                        priority=template.priority,
                        outcome="gate_fail",
                    )
                )
    return ledger


def fetch_entity_names(session: Session, entity_ids: set[int]) -> dict[int, str]:
    if not entity_ids:
        return {}
    rows = session.execute(
        text(
            """
            SELECT e.id,
                   COALESCE(c.name, p.name, f.name, 'entity_' || e.id::text) AS name,
                   e.kind
            FROM entities e
            LEFT JOIN characters c ON c.entity_id = e.id
            LEFT JOIN places p ON p.entity_id = e.id
            LEFT JOIN factions f ON f.entity_id = e.id
            WHERE e.id = ANY(:ids)
            """
        ),
        {"ids": list(entity_ids)},
    ).mappings()
    return {row["id"]: f"{row['name']} ({row['kind']})" for row in rows}


def fetch_actor_sources(
    session: Session,
    *,
    anchor_chunk_id: int,
    window_chunks: int,
    actor_ids: set[int],
) -> dict[int, list[str]]:
    """Reconstruct which of the three selection heuristics pulled each actor in."""
    if not actor_ids:
        return {}
    sources: dict[int, list[str]] = {aid: [] for aid in actor_ids}
    lower_bound = max(0, anchor_chunk_id - window_chunks + 1)

    for row in session.execute(
        text(
            """
            SELECT DISTINCT cer.entity_id
            FROM chunk_entity_references_v cer
            WHERE cer.entity_id = ANY(:ids)
              AND cer.reference_type IS DISTINCT FROM 'present'
              AND cer.chunk_id BETWEEN :lower_bound AND :anchor_chunk_id
            """
        ),
        {
            "ids": list(actor_ids),
            "lower_bound": lower_bound,
            "anchor_chunk_id": anchor_chunk_id,
        },
    ).mappings():
        sources[row["entity_id"]].append("chunk-ref")

    for row in session.execute(
        text(
            """
            SELECT DISTINCT candidate.entity_id
            FROM (
                SELECT actor_entity_id AS entity_id FROM world_events
                WHERE tick_chunk_id BETWEEN :lower_bound AND :anchor_chunk_id
                  AND (world_layer IS NULL OR world_layer = 'primary')
                  AND superseded_by_event_id IS NULL
                UNION
                SELECT target_entity_id AS entity_id FROM world_events
                WHERE tick_chunk_id BETWEEN :lower_bound AND :anchor_chunk_id
                  AND (world_layer IS NULL OR world_layer = 'primary')
                  AND superseded_by_event_id IS NULL
            ) candidate
            WHERE candidate.entity_id = ANY(:ids)
            """
        ),
        {
            "ids": list(actor_ids),
            "lower_bound": lower_bound,
            "anchor_chunk_id": anchor_chunk_id,
        },
    ).mappings():
        sources[row["entity_id"]].append("event")

    for row in session.execute(
        text(
            """
            SELECT DISTINCT etc.entity_id, etc.tag
            FROM entity_tags_current etc
            JOIN entity_tags et ON et.id = etc.entity_tag_id
            WHERE etc.entity_id = ANY(:ids)
              AND etc.is_ephemeral = true
              AND (
                  (SELECT max(world_time) FROM chunk_metadata) IS NULL
                  OR et.expires_at_world_time IS NULL
                  OR et.expires_at_world_time > (
                      SELECT max(world_time) FROM chunk_metadata
                  )
              )
            """
        ),
        {"ids": list(actor_ids)},
    ).mappings():
        sources[row["entity_id"]].append(f"ephemeral:{row['tag']}")

    for row in session.execute(
        text(
            """
            SELECT DISTINCT cra.character_entity_id AS entity_id,
                   cra.anchor_type::text AS anchor_type
            FROM character_routine_anchors cra
            WHERE cra.character_entity_id = ANY(:ids)
              AND cra.mobility_policy NOT IN ('none', 'nomadic')
            """
        ),
        {"ids": list(actor_ids)},
    ).mappings():
        sources[row["entity_id"]].append(f"routine:{row['anchor_type']}")

    return sources


def fetch_first_reference_chunk(
    session: Session, entity_ids: set[int]
) -> dict[int, int]:
    """Earliest chunk_id where each entity appears in chunk_entity_references_v.

    Used by the dry-run harness to simulate historical entity-existence: an
    entity whose first reference is at chunk > anchor did not yet exist in
    the narrative at that anchor, even though the backfilled DB knows about
    it. Production Orrery never sees this asymmetry — entities are registered
    as they're introduced, not pre-loaded. The test harness has to simulate
    that property by filtering candidates whose first appearance postdates
    the anchor.

    Entities with no row at all in chunk_entity_references_v are treated as
    "never appeared in narrative" and filtered out conservatively (they
    won't be in the returned dict, so caller's `in existed_at_anchor` check
    will exclude them).
    """
    if not entity_ids:
        return {}
    rows = session.execute(
        text(
            """
            SELECT entity_id, MIN(chunk_id) AS first_chunk
            FROM chunk_entity_references_v
            WHERE entity_id = ANY(:ids)
            GROUP BY entity_id
            """
        ),
        {"ids": list(entity_ids)},
    ).mappings()
    return {row["entity_id"]: row["first_chunk"] for row in rows}


def fetch_chunk_context(session: Session, anchor_chunk_id: int) -> Optional[dict]:
    row = (
        session.execute(
            text(
                """
            SELECT id AS chunk_id, world_time, LEFT(raw_text, 320) AS preview
            FROM narrative_view
            WHERE id = :chunk_id
            """
            ),
            {"chunk_id": anchor_chunk_id},
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def parse_location_overrides(raw_values: list[str]) -> list[tuple[str, str]]:
    """Parse CHARACTER=PLACE override specs for test harness dry-runs."""

    overrides = []
    for raw in raw_values:
        if "=" not in raw:
            raise ValueError(
                "--override-location must use CHARACTER=PLACE, got " f"{raw!r}"
            )
        character, place = raw.split("=", 1)
        character = character.strip()
        place = place.strip()
        if not character or not place:
            raise ValueError(
                "--override-location must include both CHARACTER and PLACE, "
                f"got {raw!r}"
            )
        overrides.append((character, place))
    return overrides


def resolve_location_overrides(
    session: Session,
    overrides: list[tuple[str, str]],
) -> tuple[dict[int, int], list[str]]:
    """Resolve parsed location override names to read-side state ids."""

    resolved: dict[int, int] = {}
    labels: list[str] = []
    for character_name, place_name in overrides:
        rows = list(
            session.execute(
                text(
                    """
                    SELECT c.entity_id AS character_entity_id,
                           c.name AS character_name,
                           p.id AS place_id,
                           p.name AS place_name
                    FROM characters c
                    CROSS JOIN places p
                    WHERE lower(c.name) = lower(:character_name)
                      AND lower(p.name) = lower(:place_name)
                    LIMIT 2
                    """
                ),
                {
                    "character_name": character_name,
                    "place_name": place_name,
                },
            ).mappings()
        )
        if not rows:
            raise ValueError(
                "Could not resolve --override-location "
                f"{character_name!r}={place_name!r}"
            )
        if len(rows) > 1:
            raise ValueError(
                "Ambiguous --override-location " f"{character_name!r}={place_name!r}"
            )
        row = rows[0]
        resolved[row["character_entity_id"]] = row["place_id"]
        labels.append(f"{row['character_name']} → {row['place_name']}")
    return resolved, labels


def render_stub(stub: Optional[str], bindings: dict, names: dict[int, str]) -> str:
    if not stub:
        return ""
    s = stub
    actor_id = bindings.get(Slot.ACTOR)
    target_id = bindings.get(Slot.TARGET)
    if actor_id is not None:
        s = s.replace(
            "{actor}", names.get(actor_id, f"entity_{actor_id}").split(" (")[0]
        )
    if target_id is not None:
        s = s.replace(
            "{target}", names.get(target_id, f"entity_{target_id}").split(" (")[0]
        )
    return s


def name_for(entity_id: Optional[int], names: dict[int, str]) -> str:
    if entity_id is None:
        return "—"
    return names.get(entity_id, f"entity_{entity_id}")


def render_markdown(
    *,
    slot: int,
    anchor_chunk_id: int,
    window_chunks: int,
    chunk_ctx: Optional[dict],
    world_time_override: Optional[datetime],
    binding_reports: list[BindingReport],
    sources: dict[int, list[str]],
    names: dict[int, str],
    template_counts: dict[str, int],
    raw_candidate_count: int,
    filtered_out_actor_ids: list[int],
    first_chunks: dict[int, int],
    location_override_labels: list[str],
) -> str:
    lines = []
    lines.append(f"# Orrery Dry Run — chunk_{anchor_chunk_id:04d}")
    lines.append("")
    lines.append(f"- **Slot**: {slot}")
    lines.append(f"- **Anchor chunk**: {anchor_chunk_id}")
    world_time = world_time_override or (chunk_ctx["world_time"] if chunk_ctx else None)
    lines.append(f"- **World time**: {world_time if world_time else 'unknown'}")
    if world_time_override is not None:
        lines.append("- **World time source**: command-line override")
    if location_override_labels:
        lines.append("- **Location overrides**: " + "; ".join(location_override_labels))
    lines.append(
        f"- **Window**: {window_chunks} chunks "
        f"({max(0, anchor_chunk_id - window_chunks + 1)} → {anchor_chunk_id})"
    )
    surviving_actor_count = sum(
        1 for b in binding_reports if b.slot_kind == "actor_only"
    )
    surviving_at_count = sum(
        1 for b in binding_reports if b.slot_kind == "actor_target"
    )
    scene_pressure_count = sum(
        1 for b in binding_reports if b.slot_kind == "scene_pressure"
    )
    lines.append(
        f"- **Candidate actors (raw → after existence filter)**: "
        f"{raw_candidate_count} → {surviving_actor_count} "
        f"({len(filtered_out_actor_ids)} filtered as not-yet-existing)"
    )
    lines.append(
        f"- **Bindings evaluated**: "
        f"{surviving_actor_count} actor-only + "
        f"{surviving_at_count} actor-target (off-screen) + "
        f"{scene_pressure_count} scene-pressure (present-target)"
    )
    lines.append(f"- **Templates available**: {len(BUILTIN_TEMPLATES)}")
    lines.append("")

    # Filtered-out actors
    if filtered_out_actor_ids:
        lines.append(f"## Filtered as not-yet-existing ({len(filtered_out_actor_ids)})")
        lines.append("")
        lines.append(
            "Actors whose first appearance in `chunk_entity_references_v` "
            f"postdates anchor chunk {anchor_chunk_id}. These would not exist "
            "in production Orrery at this point in the narrative; they only "
            "appear in our candidate set because slot 2 is a backfilled "
            "corpus where every entity is pre-loaded."
        )
        lines.append("")
        lines.append("| Actor | First-reference chunk | Sources (would-have-been) |")
        lines.append("|---|---|---|")
        for aid in filtered_out_actor_ids:
            first = first_chunks.get(aid, "(never)")
            srcs = ", ".join(sources.get(aid, [])) or "(none recorded)"
            lines.append(f"| {name_for(aid, names)} | {first} | {srcs} |")
        lines.append("")

    if chunk_ctx:
        lines.append("## Scene context (first ~320 chars)")
        lines.append("")
        lines.append("> " + (chunk_ctx["preview"] or "").replace("\n", " ").strip())
        lines.append("")

    # Candidate actors
    actor_ids = sorted({br.bindings[Slot.ACTOR] for br in binding_reports})
    lines.append(f"## Candidate actors ({len(actor_ids)})")
    lines.append("")
    lines.append("| Actor | Sources |")
    lines.append("|---|---|")
    for aid in actor_ids:
        srcs = ", ".join(sources.get(aid, [])) or "(none recorded)"
        lines.append(f"| {name_for(aid, names)} | {srcs} |")
    lines.append("")

    # Fired — split into off-screen (actor_only + actor_target) and scene-pressure
    # (present-target) since they answer different questions and the production
    # resolver tracks them as separate output lists (drafts vs scene_pressure_results).
    offscreen_fired = [
        (br, e)
        for br in binding_reports
        for e in br.ledger
        if e.outcome == "fired" and br.slot_kind in ("actor_only", "actor_target")
    ]
    scene_pressure_fired = [
        (br, e)
        for br in binding_reports
        for e in br.ledger
        if e.outcome == "fired" and br.slot_kind == "scene_pressure"
    ]

    lines.append(f"## Fired — off-screen activity ({len(offscreen_fired)})")
    lines.append("")
    if offscreen_fired:
        lines.append(
            "| Actor | Target | Template | Pri | Branch | Rendered stub | "
            "event_type | mag |"
        )
        lines.append("|---|---|---|---|---|---|---|---|")
        for br, e in sorted(offscreen_fired, key=lambda x: -x[1].priority):
            actor = name_for(br.bindings.get(Slot.ACTOR), names)
            target = (
                name_for(br.bindings.get(Slot.TARGET), names)
                if Slot.TARGET in br.bindings
                else "—"
            )
            stub = render_stub(e.narrative_stub, br.bindings, names)
            lines.append(
                f"| {actor} | {target} | `{e.template_id}` | {e.priority} | "
                f"{e.branch_label or '—'} | {stub} | "
                f"{e.event_type or '—'} | {e.magnitude:.2f} |"
            )
        lines.append("")
        lines.append("### State deltas for fired resolutions")
        lines.append("")
        for br, e in sorted(offscreen_fired, key=lambda x: -x[1].priority):
            actor = name_for(br.bindings.get(Slot.ACTOR), names)
            lines.append(f"- **{actor} / `{e.template_id}`**: `{e.state_delta or {}}`")
        lines.append("")
    else:
        lines.append("(none)")
        lines.append("")

    lines.append(
        f"## Fired — scene pressures (present-target) ({len(scene_pressure_fired)})"
    )
    lines.append("")
    if scene_pressure_fired:
        lines.append(
            "Pressure-policy templates fired against on-screen targets. These don't "
            "appear in `orrery_resolutions` like off-screen drafts; production routes "
            "them as Storyteller-facing scene pressures."
        )
        lines.append("")
        lines.append(
            "| Actor | Present target | Template | Pri | Branch | Rendered stub | "
            "event_type | mag |"
        )
        lines.append("|---|---|---|---|---|---|---|---|")
        for br, e in sorted(scene_pressure_fired, key=lambda x: -x[1].priority):
            actor = name_for(br.bindings.get(Slot.ACTOR), names)
            target = (
                name_for(br.bindings.get(Slot.TARGET), names)
                if Slot.TARGET in br.bindings
                else "—"
            )
            stub = render_stub(e.narrative_stub, br.bindings, names)
            lines.append(
                f"| {actor} | {target} | `{e.template_id}` | {e.priority} | "
                f"{e.branch_label or '—'} | {stub} | "
                f"{e.event_type or '—'} | {e.magnitude:.2f} |"
            )
        lines.append("")
    else:
        lines.append(
            "(none — either no pressure-policy templates eligible, or no "
            "on-screen targets at this anchor)"
        )
        lines.append("")

    # Priority-loss
    pl = [
        (br, e)
        for br in binding_reports
        for e in br.ledger
        if e.outcome == "priority_loss"
    ]
    lines.append(f"## Priority-loss ({len(pl)})")
    lines.append("")
    if pl:
        lines.append("| Actor | Target | Template | Pri | Would-fire branch | Stub |")
        lines.append("|---|---|---|---|---|---|")
        for br, e in sorted(pl, key=lambda x: -x[1].priority):
            actor = name_for(br.bindings.get(Slot.ACTOR), names)
            target = (
                name_for(br.bindings.get(Slot.TARGET), names)
                if Slot.TARGET in br.bindings
                else "—"
            )
            stub = render_stub(e.narrative_stub, br.bindings, names)
            lines.append(
                f"| {actor} | {target} | `{e.template_id}` | {e.priority} | "
                f"{e.branch_label or '—'} | {stub} |"
            )
        lines.append("")
    else:
        lines.append("(none)")
        lines.append("")

    # No-branch-match
    nbm = [
        (br, e)
        for br in binding_reports
        for e in br.ledger
        if e.outcome == "no_branch_match"
    ]
    lines.append(f"## No-branch-match ({len(nbm)})")
    lines.append("")
    if nbm:
        lines.append("Template gate passed but no branch's conditions matched.")
        lines.append("")
        lines.append("| Actor | Target | Template | Pri |")
        lines.append("|---|---|---|---|")
        for br, e in sorted(nbm, key=lambda x: -x[1].priority):
            actor = name_for(br.bindings.get(Slot.ACTOR), names)
            target = (
                name_for(br.bindings.get(Slot.TARGET), names)
                if Slot.TARGET in br.bindings
                else "—"
            )
            lines.append(f"| {actor} | {target} | `{e.template_id}` | {e.priority} |")
        lines.append("")
    else:
        lines.append("(none)")
        lines.append("")

    # Gate-fail summary (aggregated by template)
    gf_by_template: dict[str, int] = defaultdict(int)
    for br in binding_reports:
        for e in br.ledger:
            if e.outcome == "gate_fail":
                gf_by_template[e.template_id] += 1
    total_gf = sum(gf_by_template.values())
    lines.append(
        f"## Gate-fail summary ({total_gf} total, top 10 templates by frequency)"
    )
    lines.append("")
    if gf_by_template:
        lines.append("| Template | Bindings rejected |")
        lines.append("|---|---|")
        for tid, count in sorted(gf_by_template.items(), key=lambda x: -x[1])[:10]:
            lines.append(f"| `{tid}` | {count} |")
        lines.append("")
    else:
        lines.append("(none)")
        lines.append("")

    # No-candidate-template actors
    actor_to_outcomes: dict[int, set[str]] = defaultdict(set)
    for br in binding_reports:
        aid = br.bindings.get(Slot.ACTOR)
        if aid is None:
            continue
        for e in br.ledger:
            actor_to_outcomes[aid].add(e.outcome)

    no_candidate = sorted(
        aid
        for aid, outcomes in actor_to_outcomes.items()
        if "fired" not in outcomes
        and "priority_loss" not in outcomes
        and "no_branch_match" not in outcomes
    )
    lines.append(f"## No-candidate actors ({len(no_candidate)})")
    lines.append("")
    lines.append(
        "Actors who survived candidate selection but had zero gate-passing templates."
    )
    lines.append("")
    if no_candidate:
        lines.append("| Actor | Sources |")
        lines.append("|---|---|")
        for aid in no_candidate:
            srcs = ", ".join(sources.get(aid, [])) or "(none recorded)"
            lines.append(f"| {name_for(aid, names)} | {srcs} |")
        lines.append("")
    else:
        lines.append("(none — every candidate actor had at least one template apply)")
        lines.append("")

    return "\n".join(lines)


def sample_anchor(
    slot: int,
    anchor_chunk_id: int,
    window_chunks: int,
    output_dir: Path,
    *,
    world_time_override: Optional[datetime] = None,
    location_overrides: Optional[list[tuple[str, str]]] = None,
) -> Path:
    orrery_settings = load_settings_as_dict()["orrery"]
    engine = create_engine(get_slot_db_url(slot=slot))
    with Session(engine) as session:
        actor_only_templates = [
            t for t in BUILTIN_TEMPLATES if t.required_slots == ACTOR_ONLY_SLOTS
        ]
        actor_target_templates = [
            t for t in BUILTIN_TEMPLATES if t.required_slots == ACTOR_TARGET_SLOTS
        ]

        state = hydrate_world_state(
            session,
            anchor_chunk_id=anchor_chunk_id,
            window_chunks=window_chunks,
            need_tuning=None,
            project_settings=orrery_settings.get("projects"),
            epistemics_settings=orrery_settings.get("epistemics"),
            weather_settings=orrery_settings.get("weather"),
            world_time_override=world_time_override,
        )
        override_locations, override_labels = resolve_location_overrides(
            session,
            location_overrides or [],
        )
        if override_locations:
            state = replace(
                state,
                locations={**state.locations, **override_locations},
                travel_states={
                    entity_id: travel_state
                    for entity_id, travel_state in state.travel_states.items()
                    if entity_id not in override_locations
                },
            )

        raw_actor_bindings = compose_actor_bindings(
            session,
            anchor_chunk_id=anchor_chunk_id,
            window_chunks=window_chunks,
        )
        raw_actor_ids = {b[Slot.ACTOR] for b in raw_actor_bindings}
        raw_actor_target_bindings = compose_actor_target_bindings(
            session,
            anchor_chunk_id=anchor_chunk_id,
            window_chunks=window_chunks,
            actor_ids=raw_actor_ids,
            target_presence="offscreen",
        )

        # Existed-at-anchor filter: simulate historical entity existence by
        # filtering out candidates whose first appearance in any chunk
        # postdates the anchor. Production Orrery never sees future entities
        # because they're registered only when Skald introduces them.
        all_binding_entity_ids: set[int] = set()
        for b in raw_actor_bindings:
            all_binding_entity_ids.add(b[Slot.ACTOR])
        for b in raw_actor_target_bindings:
            all_binding_entity_ids.add(b[Slot.ACTOR])
            all_binding_entity_ids.add(b[Slot.TARGET])
        first_chunks = fetch_first_reference_chunk(session, all_binding_entity_ids)
        existed_at_anchor: set[int] = {
            eid
            for eid in all_binding_entity_ids
            if first_chunks.get(eid, 10**9) <= anchor_chunk_id
        }

        actor_bindings = tuple(
            b for b in raw_actor_bindings if b[Slot.ACTOR] in existed_at_anchor
        )
        actor_ids = {b[Slot.ACTOR] for b in actor_bindings}
        actor_target_bindings = tuple(
            b
            for b in raw_actor_target_bindings
            if b[Slot.ACTOR] in existed_at_anchor
            and b[Slot.TARGET] in existed_at_anchor
        )
        filtered_out_actor_ids = sorted(
            {b[Slot.ACTOR] for b in raw_actor_bindings} - actor_ids
        )

        binding_reports: list[BindingReport] = []
        for b in actor_bindings:
            binding_reports.append(
                BindingReport(
                    bindings=dict(b),
                    slot_kind="actor_only",
                    ledger=categorize_results(actor_only_templates, state, b),
                )
            )
        for b in actor_target_bindings:
            binding_reports.append(
                BindingReport(
                    bindings=dict(b),
                    slot_kind="actor_target",
                    ledger=categorize_results(actor_target_templates, state, b),
                )
            )

        # Scene-pressure path: templates with STORYTELLER_PRESSURE policy are
        # evaluated against actor↔present-target bindings (target is an on-screen
        # character at the anchor). Mirrors the production resolver path at
        # nexus/agents/orrery/resolver.py — without this, the sampler is
        # misleading for anchors with on-screen targets because pressure
        # templates would never appear to fire.
        pressure_templates = [
            t
            for t in actor_target_templates
            if t.present_target_policy is PresentTargetPolicy.STORYTELLER_PRESSURE
        ]
        if pressure_templates:
            raw_present_target_bindings = compose_actor_target_bindings(
                session,
                anchor_chunk_id=anchor_chunk_id,
                window_chunks=window_chunks,
                actor_ids=raw_actor_ids,
                target_presence="present",
            )
            # Apply the existence filter to present-target bindings too. Present
            # targets are on-screen at the anchor so they'll generally pass, but
            # the actor side still needs the filter.
            for b in raw_present_target_bindings:
                all_binding_entity_ids.add(b[Slot.ACTOR])
                all_binding_entity_ids.add(b[Slot.TARGET])
            # Refresh first_chunks / existed_at_anchor with the new ids.
            new_ids = (
                {b[Slot.ACTOR] for b in raw_present_target_bindings}
                | {b[Slot.TARGET] for b in raw_present_target_bindings}
            ) - set(first_chunks.keys())
            if new_ids:
                first_chunks.update(fetch_first_reference_chunk(session, new_ids))
                existed_at_anchor |= {
                    eid
                    for eid in new_ids
                    if first_chunks.get(eid, 10**9) <= anchor_chunk_id
                }
            present_target_bindings = tuple(
                b
                for b in raw_present_target_bindings
                if b[Slot.ACTOR] in existed_at_anchor
                and b[Slot.TARGET] in existed_at_anchor
            )
            for b in present_target_bindings:
                binding_reports.append(
                    BindingReport(
                        bindings=dict(b),
                        slot_kind="scene_pressure",
                        ledger=categorize_results(pressure_templates, state, b),
                    )
                )

        # Fetch names for every entity that touched a binding, surviving or
        # filtered, so the report can render filtered actors by name too.
        names = fetch_entity_names(session, all_binding_entity_ids)

        # Sources for surviving actors AND filtered-out actors (so the
        # filtered-out report can show why each was a candidate before filter).
        sources = fetch_actor_sources(
            session,
            anchor_chunk_id=anchor_chunk_id,
            window_chunks=window_chunks,
            actor_ids=actor_ids | set(filtered_out_actor_ids),
        )

        chunk_ctx = fetch_chunk_context(session, anchor_chunk_id)

        template_counts = {
            "actor_only": len(actor_only_templates),
            "actor_target": len(actor_target_templates),
        }

        md = render_markdown(
            slot=slot,
            anchor_chunk_id=anchor_chunk_id,
            window_chunks=window_chunks,
            chunk_ctx=chunk_ctx,
            world_time_override=world_time_override,
            binding_reports=binding_reports,
            sources=sources,
            names=names,
            template_counts=template_counts,
            raw_candidate_count=len(raw_actor_bindings),
            filtered_out_actor_ids=filtered_out_actor_ids,
            first_chunks=first_chunks,
            location_override_labels=override_labels,
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"chunk_{anchor_chunk_id:04d}.md"
        out_path.write_text(md)

        return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot", type=int, required=True)
    parser.add_argument("--anchor", type=int, required=True)
    parser.add_argument("--window-chunks", type=int, default=30)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/orrery_dry_runs"),
    )
    parser.add_argument(
        "--world-time",
        type=datetime.fromisoformat,
        default=None,
        help="Override anchor world_time for schedule/need dry-runs.",
    )
    parser.add_argument(
        "--override-location",
        action="append",
        default=[],
        metavar="CHARACTER=PLACE",
        help=(
            "Override a character's current place in the dry-run state only. "
            "May be repeated."
        ),
    )
    args = parser.parse_args()

    out = sample_anchor(
        args.slot,
        args.anchor,
        args.window_chunks,
        args.output_dir,
        world_time_override=args.world_time,
        location_overrides=parse_location_overrides(args.override_location),
    )
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
