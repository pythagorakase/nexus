"""Dry-run and apply Retrograde expansion plans into canonical Orrery tables."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Mapping, Optional, Sequence

from nexus.agents.orrery.retrograde_expansion import (
    RetrogradeExpansionEventPlan,
    RetrogradeExpansionParticipant,
    RetrogradeExpansionPlanResponse,
    validate_expansion_plan,
)

RETROGRADE_PERSISTENCE_SCHEMA_VERSION = "orrery_retrograde_persistence_plan.v0"
RETROGRADE_SOURCE_KIND = "retrograde"
RETROGRADE_PROLOGUE_MARKER = "orrery:retrograde_prologue_anchor"
RETROGRADE_PROLOGUE_RAW_TEXT = (
    "[Retrograde prologue anchor: generated setup history before the first "
    "narrated scene.]"
)
RETROGRADE_PROLOGUE_STORYTELLER_TEXT = (
    "Retrograde generated setup history exists before the opening scene. This "
    "synthetic chunk anchors canonical world_events without adding narrated "
    "prose to player-visible continuity."
)
EVENT_ROLE_KINDS = frozenset({"actor", "target", "observer", "beneficiary", "witness"})


@dataclass(frozen=True, slots=True)
class _EntityRecord:
    entity_id: int
    entity_kind: str
    name: str
    character_id: Optional[int]
    faction_id: Optional[int]
    place_id: Optional[int]

    @property
    def subtype_id(self) -> Optional[int]:
        if self.entity_kind == "character":
            return self.character_id
        if self.entity_kind == "faction":
            return self.faction_id
        if self.entity_kind == "place":
            return self.place_id
        return None


def build_retrograde_persistence_plan(
    cur: Any,
    *,
    packet: Mapping[str, Any],
    seed_candidate_response: Mapping[str, Any],
    expansion_plan_payload: Mapping[str, Any],
    slot: int,
    dbname: str,
    dry_run: bool = True,
    create_missing_entities: bool = False,
) -> dict[str, Any]:
    """Build or apply a canonical persistence plan for a Retrograde expansion.

    Dry-run mode performs only reads and returns row-shaped operations. Execute
    mode writes the prologue anchor, world_events, entity_tags, and
    entity_pair_tags when every planned reference resolves and no unsupported
    relationship rows remain.
    """

    expansion = validate_expansion_plan(
        payload=expansion_plan_payload,
        packet=packet,
        seed_candidate_response=seed_candidate_response,
    )
    existing_prologue_id = _find_prologue_chunk_id(cur)
    entity_index = _load_entity_index(cur)
    event_types = _load_event_types(cur)
    tag_ids = _load_tag_ids(cur)
    pair_tag_ids = _load_pair_tag_ids(cur)
    source_blockers = _source_kind_blockers(cur)
    world_time = _load_world_time(cur)

    manifest = _build_plan(
        cur,
        expansion=expansion,
        slot=slot,
        dbname=dbname,
        dry_run=True,
        prologue_chunk_id=existing_prologue_id,
        entity_index=entity_index,
        event_types=event_types,
        tag_ids=tag_ids,
        pair_tag_ids=pair_tag_ids,
        source_blockers=source_blockers,
        world_time=world_time,
        create_missing_entities=create_missing_entities,
        inserted_stub_keys=frozenset(),
    )
    if dry_run:
        return manifest

    blockers = list(manifest["execute_blockers"])
    if blockers:
        formatted = "; ".join(blocker["reason"] for blocker in blockers)
        raise ValueError(f"Retrograde expansion is not safe to execute: {formatted}")

    inserted_stub_keys = _insert_missing_entity_stubs(
        cur,
        entity_stub_rows=manifest["entity_stub_rows"],
        create_missing_entities=create_missing_entities,
    )
    if inserted_stub_keys:
        entity_index = _load_entity_index(cur)

    prologue_chunk_id = existing_prologue_id or _insert_prologue_chunk(cur)
    _ensure_prologue_metadata(cur, prologue_chunk_id=prologue_chunk_id)
    return _build_plan(
        cur,
        expansion=expansion,
        slot=slot,
        dbname=dbname,
        dry_run=False,
        prologue_chunk_id=prologue_chunk_id,
        entity_index=entity_index,
        event_types=event_types,
        tag_ids=tag_ids,
        pair_tag_ids=pair_tag_ids,
        source_blockers=source_blockers,
        world_time=world_time,
        create_missing_entities=create_missing_entities,
        inserted_stub_keys=inserted_stub_keys,
    )


def _build_plan(
    cur: Any,
    *,
    expansion: RetrogradeExpansionPlanResponse,
    slot: int,
    dbname: str,
    dry_run: bool,
    prologue_chunk_id: Optional[int],
    entity_index: Mapping[tuple[str, str], Sequence[_EntityRecord]],
    event_types: set[str],
    tag_ids: Mapping[str, int],
    pair_tag_ids: Mapping[str, int],
    source_blockers: list[dict[str, str]],
    world_time: Any,
    create_missing_entities: bool,
    inserted_stub_keys: frozenset[tuple[str, str]],
) -> dict[str, Any]:
    counters: Counter[str] = Counter()
    reference_issues: list[dict[str, Any]] = []
    vocabulary_issues: list[dict[str, Any]] = []
    execute_blockers: list[dict[str, str]] = list(source_blockers)
    event_ref_to_id: dict[str, int] = {}
    event_source_available = not any(
        blocker["id"] == "event_source_kind_retrograde" for blocker in source_blockers
    )
    entity_stub_rows = _plan_entity_stubs(
        expansion=expansion,
        entity_index=entity_index,
        create_missing_entities=create_missing_entities,
        inserted_stub_keys=inserted_stub_keys,
    )
    creatable_refs = frozenset(
        (row["entity_kind"], _normalize_ref(row["entity_ref"]))
        for row in entity_stub_rows
        if row["status"] in {"would_insert", "inserted"}
    )
    for stub_row in entity_stub_rows:
        counters[f"entity_stubs_{stub_row['status']}"] += 1

    event_rows = []
    for event in expansion.event_plan:
        planned = _plan_event_row(
            cur,
            event,
            dry_run=dry_run,
            prologue_chunk_id=prologue_chunk_id,
            entity_index=entity_index,
            event_types=event_types,
            event_source_available=event_source_available,
            creatable_refs=creatable_refs,
        )
        event_rows.append(planned)
        counters[f"events_{planned['status']}"] += 1
        if planned.get("world_event_id") is not None:
            event_ref_to_id[event.event_ref] = int(planned["world_event_id"])
        reference_issues.extend(planned.pop("_reference_issues"))
        vocabulary_issues.extend(planned.pop("_vocabulary_issues"))

    entity_tag_rows = []
    for tag_plan in expansion.entity_tag_plan:
        planned = _plan_entity_tag_row(
            cur,
            tag_plan=tag_plan.model_dump(mode="json"),
            dry_run=dry_run,
            entity_index=entity_index,
            tag_ids=tag_ids,
            world_time=world_time,
            creatable_refs=creatable_refs,
        )
        entity_tag_rows.append(planned)
        counters[f"entity_tags_{planned['status']}"] += 1
        reference_issues.extend(planned.pop("_reference_issues"))
        vocabulary_issues.extend(planned.pop("_vocabulary_issues"))

    pair_tag_rows = []
    for pair_plan in expansion.pair_tag_plan:
        planned = _plan_pair_tag_row(
            cur,
            pair_plan=pair_plan.model_dump(mode="json"),
            dry_run=dry_run,
            entity_index=entity_index,
            pair_tag_ids=pair_tag_ids,
            world_time=world_time,
            creatable_refs=creatable_refs,
        )
        pair_tag_rows.append(planned)
        counters[f"pair_tags_{planned['status']}"] += 1
        reference_issues.extend(planned.pop("_reference_issues"))
        vocabulary_issues.extend(planned.pop("_vocabulary_issues"))

    relationship_rows = [
        {
            **relationship.model_dump(mode="json"),
            "status": "planned_only",
            "reason": (
                "Retrograde relationship writes need a dedicated writer because "
                "character, faction, and faction-character relationships have "
                "different required columns and valence semantics."
            ),
        }
        for relationship in expansion.relationship_plan
    ]
    if relationship_rows:
        counters["relationships_planned_only"] = len(relationship_rows)
        execute_blockers.append(
            {
                "id": "relationship_writer_not_available",
                "reason": (
                    "relationship_plan contains rows, but Retrograde does not "
                    "yet have a canonical relationship writer"
                ),
            }
        )

    _append_reference_blockers(execute_blockers, reference_issues)
    _append_vocabulary_blockers(execute_blockers, vocabulary_issues)

    for key in (
        "events_would_insert",
        "events_inserted",
        "events_already_present",
        "events_blocked",
        "entity_tags_would_insert",
        "entity_tags_inserted",
        "entity_tags_already_present",
        "entity_tags_blocked",
        "pair_tags_would_insert",
        "pair_tags_inserted",
        "pair_tags_already_present",
        "pair_tags_blocked",
        "relationships_planned_only",
        "entity_stubs_would_insert",
        "entity_stubs_inserted",
        "entity_stubs_already_present",
        "entity_stubs_ambiguous_existing",
    ):
        counters.setdefault(key, 0)

    return {
        "schema_version": RETROGRADE_PERSISTENCE_SCHEMA_VERSION,
        "dry_run": dry_run,
        "slot": slot,
        "dbname": dbname,
        "source_kind": RETROGRADE_SOURCE_KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prologue_anchor": _prologue_anchor_plan(
            dry_run=dry_run,
            prologue_chunk_id=prologue_chunk_id,
        ),
        "counters": dict(counters),
        "execute_blockers": execute_blockers,
        "reference_issues": reference_issues,
        "vocabulary_issues": vocabulary_issues,
        "entity_stub_rows": entity_stub_rows,
        "event_rows": event_rows,
        "entity_tag_rows": entity_tag_rows,
        "pair_tag_rows": pair_tag_rows,
        "relationship_rows": relationship_rows,
        "thread_plan": [
            thread.model_dump(mode="json") for thread in expansion.thread_plan
        ],
        "coverage_notes": list(expansion.coverage_notes),
        "commit_readiness": {
            "requested_writes": "canonical" if not dry_run else "none",
            "can_execute": not execute_blockers,
            "event_ref_to_id": event_ref_to_id,
        },
    }


def _plan_event_row(
    cur: Any,
    event: RetrogradeExpansionEventPlan,
    *,
    dry_run: bool,
    prologue_chunk_id: Optional[int],
    entity_index: Mapping[tuple[str, str], Sequence[_EntityRecord]],
    event_types: set[str],
    event_source_available: bool,
    creatable_refs: frozenset[tuple[str, str]],
) -> dict[str, Any]:
    reference_issues: list[dict[str, Any]] = []
    vocabulary_issues: list[dict[str, Any]] = []
    participant_results = []
    actor_entity_id = None
    target_entity_id = None

    for participant in event.participants:
        resolved = _resolve_participant(
            participant,
            entity_index,
            creatable_refs=creatable_refs,
        )
        participant_results.append(resolved)
        if resolved["resolution"] not in {"resolved", "stub_pending"}:
            reference_issues.append(resolved)
            continue
        if (
            resolved["resolution"] == "resolved"
            and participant.role == "actor"
            and actor_entity_id is None
        ):
            actor_entity_id = resolved["entity_id"]
        if (
            resolved["resolution"] == "resolved"
            and participant.role == "target"
            and target_entity_id is None
        ):
            target_entity_id = resolved["entity_id"]

    location = None
    location_id = None
    if event.location_ref:
        location = _resolve_entity(
            event.location_ref,
            "place",
            entity_index,
            role="location",
            creatable_refs=creatable_refs,
        )
        if location["resolution"] == "resolved":
            location_id = location["place_id"]
        elif location["resolution"] != "stub_pending":
            reference_issues.append(location)

    if event.event_type not in event_types:
        vocabulary_issues.append(
            {
                "kind": "event_type",
                "event_ref": event.event_ref,
                "value": event.event_type,
                "reason": "event_type is not registered in this slot",
            }
        )

    existing_id = (
        _existing_retrograde_event_id(cur, event.event_ref)
        if event_source_available
        else None
    )
    base = {
        "event_ref": event.event_ref,
        "seed_ids": list(event.seed_ids),
        "event_type": event.event_type,
        "summary": event.summary,
        "chronology": event.chronology,
        "changed_fields": list(event.changed_fields),
        "magnitude": event.magnitude,
        "actor_entity_id": actor_entity_id,
        "target_entity_id": target_entity_id,
        "location_id": location_id,
        "location": location,
        "participant_resolutions": participant_results,
        "world_layer": "primary",
        "tick_chunk_id": prologue_chunk_id,
        "_reference_issues": reference_issues,
        "_vocabulary_issues": vocabulary_issues,
    }
    if existing_id is not None:
        return {**base, "status": "already_present", "world_event_id": existing_id}
    if reference_issues or vocabulary_issues or prologue_chunk_id is None:
        status = "would_insert" if dry_run and not reference_issues else "blocked"
        return {**base, "status": status, "world_event_id": None}
    if dry_run:
        return {**base, "status": "would_insert", "world_event_id": None}

    world_event_id = _insert_world_event(
        cur,
        event=event,
        tick_chunk_id=prologue_chunk_id,
        actor_entity_id=actor_entity_id,
        target_entity_id=target_entity_id,
        location_id=location_id,
        participant_results=participant_results,
    )
    return {**base, "status": "inserted", "world_event_id": world_event_id}


def _plan_entity_tag_row(
    cur: Any,
    *,
    tag_plan: Mapping[str, Any],
    dry_run: bool,
    entity_index: Mapping[tuple[str, str], Sequence[_EntityRecord]],
    tag_ids: Mapping[str, int],
    world_time: Any,
    creatable_refs: frozenset[tuple[str, str]],
) -> dict[str, Any]:
    reference_issues: list[dict[str, Any]] = []
    vocabulary_issues: list[dict[str, Any]] = []
    entity = _resolve_entity(
        str(tag_plan["entity_ref"]),
        str(tag_plan["entity_kind"]),
        entity_index,
        role="entity_tag",
        creatable_refs=creatable_refs,
    )
    if entity["resolution"] not in {"resolved", "stub_pending"}:
        reference_issues.append(entity)
    tag = str(tag_plan["tag"])
    tag_id = tag_ids.get(tag)
    if tag_id is None:
        vocabulary_issues.append(
            {
                "kind": "single_entity_tag",
                "entity_ref": tag_plan["entity_ref"],
                "value": tag,
                "reason": "tag is not registered in this slot",
            }
        )

    base = {
        **dict(tag_plan),
        "entity": entity,
        "entity_id": entity.get("entity_id"),
        "tag_id": tag_id,
        "source_kind": RETROGRADE_SOURCE_KIND,
        "template_id": _source_event_template_id(tag_plan.get("source_event_ref")),
        "_reference_issues": reference_issues,
        "_vocabulary_issues": vocabulary_issues,
    }
    if reference_issues or vocabulary_issues:
        return {**base, "status": "blocked", "entity_tag_id": None}
    if tag_id is None:
        raise AssertionError("tag_id is required after vocabulary validation")
    if entity["resolution"] == "stub_pending":
        if dry_run:
            return {**base, "status": "would_insert", "entity_tag_id": None}
        raise AssertionError("stub_pending must be resolved before execute writes")

    existing_id = _active_entity_tag_id(cur, int(entity["entity_id"]), int(tag_id))
    if existing_id is not None:
        return {**base, "status": "already_present", "entity_tag_id": existing_id}
    if dry_run:
        return {**base, "status": "would_insert", "entity_tag_id": None}

    entity_tag_id = _insert_entity_tag(
        cur,
        entity_id=int(entity["entity_id"]),
        tag_id=int(tag_id),
        template_id=base["template_id"],
        world_time=world_time,
    )
    return {**base, "status": "inserted", "entity_tag_id": entity_tag_id}


def _plan_pair_tag_row(
    cur: Any,
    *,
    pair_plan: Mapping[str, Any],
    dry_run: bool,
    entity_index: Mapping[tuple[str, str], Sequence[_EntityRecord]],
    pair_tag_ids: Mapping[str, int],
    world_time: Any,
    creatable_refs: frozenset[tuple[str, str]],
) -> dict[str, Any]:
    reference_issues: list[dict[str, Any]] = []
    vocabulary_issues: list[dict[str, Any]] = []
    subject = _resolve_entity(
        str(pair_plan["subject_ref"]),
        str(pair_plan["subject_kind"]),
        entity_index,
        role="pair_subject",
        creatable_refs=creatable_refs,
    )
    object_entity = _resolve_entity(
        str(pair_plan["object_ref"]),
        str(pair_plan["object_kind"]),
        entity_index,
        role="pair_object",
        creatable_refs=creatable_refs,
    )
    for resolved in (subject, object_entity):
        if resolved["resolution"] not in {"resolved", "stub_pending"}:
            reference_issues.append(resolved)
    tag = str(pair_plan["tag"])
    pair_tag_id = pair_tag_ids.get(tag)
    if pair_tag_id is None:
        vocabulary_issues.append(
            {
                "kind": "pair_tag",
                "subject_ref": pair_plan["subject_ref"],
                "object_ref": pair_plan["object_ref"],
                "value": tag,
                "reason": "pair_tag is not registered in this slot",
            }
        )

    if (
        subject.get("resolution") == "resolved"
        and object_entity.get("resolution") == "resolved"
        and subject.get("entity_id") == object_entity.get("entity_id")
    ):
        reference_issues.append(
            {
                "entity_ref": pair_plan["subject_ref"],
                "entity_kind": pair_plan["subject_kind"],
                "resolution": "self_edge",
                "role": "pair_tag",
                "reason": "entity_pair_tags requires distinct endpoints",
            }
        )

    base = {
        **dict(pair_plan),
        "subject": subject,
        "object": object_entity,
        "subject_entity_id": subject.get("entity_id"),
        "object_entity_id": object_entity.get("entity_id"),
        "pair_tag_id": pair_tag_id,
        "source_kind": RETROGRADE_SOURCE_KIND,
        "template_id": _source_event_template_id(pair_plan.get("source_event_ref")),
        "_reference_issues": reference_issues,
        "_vocabulary_issues": vocabulary_issues,
    }
    if reference_issues or vocabulary_issues:
        return {**base, "status": "blocked", "entity_pair_tag_id": None}
    if pair_tag_id is None:
        raise AssertionError("pair_tag_id is required after vocabulary validation")
    if subject["resolution"] == "stub_pending" or object_entity["resolution"] == (
        "stub_pending"
    ):
        if dry_run:
            return {**base, "status": "would_insert", "entity_pair_tag_id": None}
        raise AssertionError("stub_pending must be resolved before execute writes")

    existing_id = _active_pair_tag_id(
        cur,
        subject_entity_id=int(subject["entity_id"]),
        object_entity_id=int(object_entity["entity_id"]),
        pair_tag_id=int(pair_tag_id),
    )
    if existing_id is not None:
        return {
            **base,
            "status": "already_present",
            "entity_pair_tag_id": existing_id,
        }
    if dry_run:
        return {**base, "status": "would_insert", "entity_pair_tag_id": None}

    entity_pair_tag_id = _insert_pair_tag(
        cur,
        subject_entity_id=int(subject["entity_id"]),
        object_entity_id=int(object_entity["entity_id"]),
        pair_tag_id=int(pair_tag_id),
        template_id=base["template_id"],
        world_time=world_time,
    )
    return {
        **base,
        "status": "inserted",
        "entity_pair_tag_id": entity_pair_tag_id,
    }


def _insert_world_event(
    cur: Any,
    *,
    event: RetrogradeExpansionEventPlan,
    tick_chunk_id: int,
    actor_entity_id: Optional[int],
    target_entity_id: Optional[int],
    location_id: Optional[int],
    participant_results: Sequence[Mapping[str, Any]],
) -> int:
    payload = {
        "source": RETROGRADE_SOURCE_KIND,
        "retrograde_event_ref": event.event_ref,
        "seed_ids": list(event.seed_ids),
        "summary": event.summary,
        "chronology": event.chronology,
        "participants": [
            result
            for result in participant_results
            if result.get("resolution") == "resolved"
        ],
        "location_ref": event.location_ref,
        "payload": event.payload,
    }
    cur.execute(
        """
        /* orrery:retrograde:insert_world_event */
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id, target_entity_id,
            location_id, world_layer, source, changed_fields, magnitude,
            payload
        ) VALUES (
            %s, %s, %s, %s, %s, 'primary'::world_layer_type,
            'retrograde'::event_source_kind, %s, %s, %s::jsonb
        )
        RETURNING id
        """,
        (
            event.event_type,
            tick_chunk_id,
            actor_entity_id,
            target_entity_id,
            location_id,
            list(event.changed_fields),
            event.magnitude,
            json.dumps(payload),
        ),
    )
    world_event_id = int(_row_value(cur.fetchone(), "id", 0))
    for participant in participant_results:
        if participant.get("resolution") != "resolved":
            continue
        role = str(participant.get("role") or "observer")
        if role not in EVENT_ROLE_KINDS:
            role = "observer"
        cur.execute(
            """
            /* orrery:retrograde:insert_world_event_entity */
            INSERT INTO world_event_entities (event_id, role, entity_id)
            VALUES (%s, %s::event_role_kind, %s)
            ON CONFLICT DO NOTHING
            """,
            (world_event_id, role, participant["entity_id"]),
        )
    return world_event_id


def _insert_entity_tag(
    cur: Any,
    *,
    entity_id: int,
    tag_id: int,
    template_id: Optional[str],
    world_time: Any,
) -> Optional[int]:
    cur.execute(
        """
        /* orrery:retrograde:insert_entity_tag */
        INSERT INTO entity_tags (
            entity_id, tag_id, applied_at_world_time, template_id, source_kind
        )
        VALUES (%s, %s, %s, %s, 'retrograde'::entity_tag_source_kind)
        ON CONFLICT (entity_id, tag_id)
          WHERE cleared_at IS NULL
          DO NOTHING
        RETURNING id
        """,
        (entity_id, tag_id, world_time, template_id),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return int(_row_value(row, "id", 0))


def _insert_pair_tag(
    cur: Any,
    *,
    subject_entity_id: int,
    object_entity_id: int,
    pair_tag_id: int,
    template_id: Optional[str],
    world_time: Any,
) -> Optional[int]:
    cur.execute(
        """
        /* orrery:retrograde:insert_pair_tag */
        INSERT INTO entity_pair_tags (
            subject_entity_id, object_entity_id, pair_tag_id,
            applied_at_world_time, source_kind, template_id
        )
        VALUES (
            %s, %s, %s, %s, 'retrograde'::entity_tag_source_kind, %s
        )
        ON CONFLICT (subject_entity_id, object_entity_id, pair_tag_id)
          WHERE cleared_at IS NULL
          DO NOTHING
        RETURNING id
        """,
        (
            subject_entity_id,
            object_entity_id,
            pair_tag_id,
            world_time,
            template_id,
        ),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return int(_row_value(row, "id", 0))


def _insert_prologue_chunk(cur: Any) -> int:
    cur.execute(
        """
        /* orrery:retrograde:insert_prologue_chunk */
        INSERT INTO narrative_chunks (
            raw_text, storyteller_text, choice_object, choice_text,
            authorial_directives, state, finalized_at
        )
        VALUES (%s, %s, NULL, NULL, %s::jsonb, 'finalized', now())
        RETURNING id
        """,
        (
            RETROGRADE_PROLOGUE_RAW_TEXT,
            RETROGRADE_PROLOGUE_STORYTELLER_TEXT,
            json.dumps([RETROGRADE_PROLOGUE_MARKER]),
        ),
    )
    return int(_row_value(cur.fetchone(), "id", 0))


def _ensure_prologue_metadata(cur: Any, *, prologue_chunk_id: int) -> None:
    cur.execute(
        """
        /* orrery:retrograde:prologue_metadata_exists */
        SELECT id FROM chunk_metadata WHERE chunk_id = %s
        """,
        (prologue_chunk_id,),
    )
    if cur.fetchone() is not None:
        return
    cur.execute(
        """
        /* orrery:retrograde:insert_prologue_metadata */
        INSERT INTO chunk_metadata (
            chunk_id, season, episode, scene, world_layer, time_delta,
            generation_date, slug, world_time
        )
        VALUES (
            %s, 0, 0, 0, 'primary'::world_layer_type,
            interval '0 seconds', now(), 'RETROGRADE_PROLOGUE',
            COALESCE(
                (
                    SELECT min(world_time) - interval '1 second'
                    FROM chunk_metadata
                    WHERE world_time IS NOT NULL
                ),
                now()
            )
        )
        """,
        (prologue_chunk_id,),
    )


def _find_prologue_chunk_id(cur: Any) -> Optional[int]:
    cur.execute(
        """
        /* orrery:retrograde:prologue_chunk */
        SELECT id
        FROM narrative_chunks
        WHERE authorial_directives @> %s::jsonb
        ORDER BY id
        LIMIT 1
        """,
        (json.dumps([RETROGRADE_PROLOGUE_MARKER]),),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return int(_row_value(row, "id", 0))


def _existing_retrograde_event_id(cur: Any, event_ref: str) -> Optional[int]:
    cur.execute(
        """
        /* orrery:retrograde:existing_world_event */
        SELECT id
        FROM world_events
        WHERE source = 'retrograde'::event_source_kind
          AND payload ->> 'retrograde_event_ref' = %s
        ORDER BY id
        LIMIT 1
        """,
        (event_ref,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return int(_row_value(row, "id", 0))


def _active_entity_tag_id(cur: Any, entity_id: int, tag_id: int) -> Optional[int]:
    cur.execute(
        """
        /* orrery:retrograde:active_entity_tag */
        SELECT id
        FROM entity_tags
        WHERE entity_id = %s AND tag_id = %s AND cleared_at IS NULL
        ORDER BY id
        LIMIT 1
        """,
        (entity_id, tag_id),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return int(_row_value(row, "id", 0))


def _active_pair_tag_id(
    cur: Any,
    *,
    subject_entity_id: int,
    object_entity_id: int,
    pair_tag_id: int,
) -> Optional[int]:
    cur.execute(
        """
        /* orrery:retrograde:active_pair_tag */
        SELECT id
        FROM entity_pair_tags
        WHERE subject_entity_id = %s
          AND object_entity_id = %s
          AND pair_tag_id = %s
          AND cleared_at IS NULL
        ORDER BY id
        LIMIT 1
        """,
        (subject_entity_id, object_entity_id, pair_tag_id),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return int(_row_value(row, "id", 0))


def _load_entity_index(cur: Any) -> dict[tuple[str, str], list[_EntityRecord]]:
    cur.execute(
        """
        /* orrery:retrograde:entity_catalog */
        SELECT
            env.id AS entity_id,
            env.kind::text AS entity_kind,
            env.name,
            c.id AS character_id,
            f.id AS faction_id,
            p.id AS place_id
        FROM entity_names_v env
        LEFT JOIN characters c ON c.entity_id = env.id
        LEFT JOIN factions f ON f.entity_id = env.id
        LEFT JOIN places p ON p.entity_id = env.id
        ORDER BY env.kind::text, env.name, env.id
        """
    )
    index: dict[tuple[str, str], list[_EntityRecord]] = {}
    for row in cur.fetchall():
        record = _EntityRecord(
            entity_id=int(_row_value(row, "entity_id", 0)),
            entity_kind=str(_row_value(row, "entity_kind", 1)),
            name=str(_row_value(row, "name", 2)),
            character_id=_optional_int(_row_value(row, "character_id", 3)),
            faction_id=_optional_int(_row_value(row, "faction_id", 4)),
            place_id=_optional_int(_row_value(row, "place_id", 5)),
        )
        index.setdefault(
            (record.entity_kind, _normalize_ref(record.name)),
            [],
        ).append(record)
    return index


def _load_event_types(cur: Any) -> set[str]:
    cur.execute(
        """
        /* orrery:retrograde:event_types */
        SELECT type FROM event_types WHERE deprecated = false
        """
    )
    return {str(_row_value(row, "type", 0)) for row in cur.fetchall()}


def _load_tag_ids(cur: Any) -> dict[str, int]:
    cur.execute(
        """
        /* orrery:retrograde:single_entity_tags */
        SELECT id, tag
        FROM tags
        WHERE deprecated = false AND synonym_for IS NULL
        """
    )
    return {
        str(_row_value(row, "tag", 1)): int(_row_value(row, "id", 0))
        for row in cur.fetchall()
    }


def _load_pair_tag_ids(cur: Any) -> dict[str, int]:
    cur.execute(
        """
        /* orrery:retrograde:pair_tags */
        SELECT id, tag FROM pair_tags WHERE deprecated = false
        """
    )
    return {
        str(_row_value(row, "tag", 1)): int(_row_value(row, "id", 0))
        for row in cur.fetchall()
    }


def _load_world_time(cur: Any) -> Any:
    cur.execute(
        """
        /* orrery:retrograde:world_time */
        SELECT max(world_time) AS world_time FROM chunk_metadata
        """
    )
    row = cur.fetchone()
    if row is None:
        return None
    return _row_value(row, "world_time", 0)


def _plan_entity_stubs(
    *,
    expansion: RetrogradeExpansionPlanResponse,
    entity_index: Mapping[tuple[str, str], Sequence[_EntityRecord]],
    create_missing_entities: bool,
    inserted_stub_keys: frozenset[tuple[str, str]],
) -> list[dict[str, Any]]:
    refs = _collect_expansion_entity_refs(expansion)
    rows = []
    for key, ref in sorted(refs.items()):
        matches = list(entity_index.get(key, []))
        if key in inserted_stub_keys:
            status = "inserted"
        elif len(matches) == 1:
            status = "already_present"
        elif len(matches) > 1:
            status = "ambiguous_existing"
        elif create_missing_entities:
            status = "would_insert"
        else:
            continue
        row = {
            "entity_ref": ref["entity_ref"],
            "entity_kind": ref["entity_kind"],
            "status": status,
            "sources": ref["sources"],
        }
        if matches:
            row["candidates"] = [_entity_record_json(match) for match in matches]
        rows.append(row)
    return rows


def _collect_expansion_entity_refs(
    expansion: RetrogradeExpansionPlanResponse,
) -> dict[tuple[str, str], dict[str, Any]]:
    refs: dict[tuple[str, str], dict[str, Any]] = {}

    def add_ref(
        entity_ref: Optional[str],
        entity_kind: Optional[str],
        *,
        source: Mapping[str, Any],
    ) -> None:
        if not entity_ref or not entity_kind:
            return
        key = (str(entity_kind), _normalize_ref(str(entity_ref)))
        entry = refs.setdefault(
            key,
            {
                "entity_ref": str(entity_ref),
                "entity_kind": str(entity_kind),
                "sources": [],
            },
        )
        entry["sources"].append(dict(source))

    for event in expansion.event_plan:
        for participant in event.participants:
            add_ref(
                participant.entity_ref,
                participant.entity_kind,
                source={
                    "plan": "event_plan",
                    "event_ref": event.event_ref,
                    "role": participant.role,
                },
            )
        add_ref(
            event.location_ref,
            "place",
            source={
                "plan": "event_plan",
                "event_ref": event.event_ref,
                "role": "location",
            },
        )

    for tag_plan in expansion.entity_tag_plan:
        add_ref(
            tag_plan.entity_ref,
            tag_plan.entity_kind,
            source={
                "plan": "entity_tag_plan",
                "tag": tag_plan.tag,
                "source_event_ref": tag_plan.source_event_ref,
            },
        )

    for pair_plan in expansion.pair_tag_plan:
        add_ref(
            pair_plan.subject_ref,
            pair_plan.subject_kind,
            source={
                "plan": "pair_tag_plan",
                "tag": pair_plan.tag,
                "role": "subject",
            },
        )
        add_ref(
            pair_plan.object_ref,
            pair_plan.object_kind,
            source={
                "plan": "pair_tag_plan",
                "tag": pair_plan.tag,
                "role": "object",
            },
        )

    for relationship in expansion.relationship_plan:
        add_ref(
            relationship.subject_ref,
            relationship.subject_kind,
            source={
                "plan": "relationship_plan",
                "relationship_type": relationship.relationship_type,
                "role": "subject",
            },
        )
        add_ref(
            relationship.object_ref,
            relationship.object_kind,
            source={
                "plan": "relationship_plan",
                "relationship_type": relationship.relationship_type,
                "role": "object",
            },
        )

    return refs


def _insert_missing_entity_stubs(
    cur: Any,
    *,
    entity_stub_rows: Sequence[Mapping[str, Any]],
    create_missing_entities: bool,
) -> frozenset[tuple[str, str]]:
    if not create_missing_entities:
        return frozenset()

    inserted: set[tuple[str, str]] = set()
    for row in entity_stub_rows:
        if row.get("status") != "would_insert":
            continue
        entity_ref = str(row["entity_ref"])
        entity_kind = str(row["entity_kind"])
        if entity_kind == "character":
            _insert_character_stub(cur, entity_ref=entity_ref, sources=row["sources"])
        elif entity_kind == "place":
            _insert_place_stub(cur, entity_ref=entity_ref, sources=row["sources"])
        elif entity_kind == "faction":
            _insert_faction_stub(cur, entity_ref=entity_ref, sources=row["sources"])
        else:
            raise ValueError(f"Unsupported Retrograde stub entity kind {entity_kind!r}")
        inserted.add((entity_kind, _normalize_ref(entity_ref)))
    return frozenset(inserted)


def _insert_character_stub(
    cur: Any,
    *,
    entity_ref: str,
    sources: Any,
) -> None:
    cur.execute(
        """
        /* orrery:retrograde:insert_character_stub */
        INSERT INTO characters (
            name, summary, background, current_activity, extra_data
        )
        VALUES (%s, %s, %s, %s, %s::jsonb)
        """,
        (
            entity_ref,
            _stub_summary(entity_ref, "character"),
            "Retrograde-generated stub; details intentionally sparse until play.",
            "latent in generated backstory",
            json.dumps(_stub_extra_data(sources)),
        ),
    )


def _insert_place_stub(
    cur: Any,
    *,
    entity_ref: str,
    sources: Any,
) -> None:
    cur.execute(
        """
        /* orrery:retrograde:insert_place_stub */
        INSERT INTO places (
            name, type, summary, current_status, extra_data
        )
        VALUES (%s, 'other'::place_type, %s, %s, %s::jsonb)
        """,
        (
            entity_ref,
            _stub_summary(entity_ref, "place"),
            "latent in generated backstory",
            json.dumps(_stub_extra_data(sources)),
        ),
    )


def _insert_faction_stub(
    cur: Any,
    *,
    entity_ref: str,
    sources: Any,
) -> None:
    cur.execute("LOCK TABLE factions IN SHARE ROW EXCLUSIVE MODE")
    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 AS id FROM factions")
    faction_id = int(_row_value(cur.fetchone(), "id", 0))
    cur.execute(
        """
        /* orrery:retrograde:insert_faction_stub */
        INSERT INTO factions (
            id, name, summary, current_activity, extra_data
        )
        VALUES (%s, %s, %s, %s, %s::jsonb)
        """,
        (
            faction_id,
            entity_ref,
            _stub_summary(entity_ref, "faction"),
            "latent in generated backstory",
            json.dumps(_stub_extra_data(sources)),
        ),
    )


def _stub_summary(entity_ref: str, entity_kind: str) -> str:
    return (
        f"Retrograde-generated {entity_kind} stub for {entity_ref}. "
        "Created so Skald-selected setup history can resolve to canonical rows."
    )


def _stub_extra_data(sources: Any) -> dict[str, Any]:
    return {
        "source": RETROGRADE_SOURCE_KIND,
        "stub_kind": "retrograde_expansion_ref",
        "sources": sources,
    }


def _source_kind_blockers(cur: Any) -> list[dict[str, str]]:
    blockers = []
    if RETROGRADE_SOURCE_KIND not in _load_enum_values(cur, "event_source_kind"):
        blockers.append(
            {
                "id": "event_source_kind_retrograde",
                "reason": "event_source_kind does not include 'retrograde'",
            }
        )
    if RETROGRADE_SOURCE_KIND not in _load_enum_values(cur, "entity_tag_source_kind"):
        blockers.append(
            {
                "id": "entity_tag_source_kind_retrograde",
                "reason": "entity_tag_source_kind does not include 'retrograde'",
            }
        )
    return blockers


def _load_enum_values(cur: Any, type_name: str) -> set[str]:
    cur.execute(
        """
        /* orrery:retrograde:enum_values */
        SELECT enumlabel
        FROM pg_enum
        WHERE enumtypid = %s::regtype
        """,
        (type_name,),
    )
    return {str(_row_value(row, "enumlabel", 0)) for row in cur.fetchall()}


def _resolve_participant(
    participant: RetrogradeExpansionParticipant,
    entity_index: Mapping[tuple[str, str], Sequence[_EntityRecord]],
    *,
    creatable_refs: frozenset[tuple[str, str]],
) -> dict[str, Any]:
    return _resolve_entity(
        participant.entity_ref,
        participant.entity_kind,
        entity_index,
        role=participant.role,
        creatable_refs=creatable_refs,
    )


def _resolve_entity(
    entity_ref: str,
    entity_kind: str,
    entity_index: Mapping[tuple[str, str], Sequence[_EntityRecord]],
    *,
    role: str,
    creatable_refs: frozenset[tuple[str, str]],
) -> dict[str, Any]:
    key = (entity_kind, _normalize_ref(entity_ref))
    matches = list(entity_index.get(key, []))
    base = {
        "entity_ref": entity_ref,
        "entity_kind": entity_kind,
        "role": role,
    }
    if not matches:
        if key in creatable_refs:
            return {
                **base,
                "resolution": "stub_pending",
                "reason": (
                    "No entity with this exact name/kind exists yet; "
                    "Retrograde stub creation is enabled"
                ),
            }
        return {
            **base,
            "resolution": "unresolved",
            "reason": "No entity with this exact name/kind exists in the slot",
        }
    if len(matches) > 1:
        return {
            **base,
            "resolution": "ambiguous",
            "reason": "Multiple entities share this exact name/kind",
            "candidates": [_entity_record_json(match) for match in matches],
        }
    record = matches[0]
    return {
        **base,
        "resolution": "resolved",
        **_entity_record_json(record),
    }


def _entity_record_json(record: _EntityRecord) -> dict[str, Any]:
    return {
        "entity_id": record.entity_id,
        "entity_kind": record.entity_kind,
        "name": record.name,
        "character_id": record.character_id,
        "faction_id": record.faction_id,
        "place_id": record.place_id,
        "subtype_id": record.subtype_id,
    }


def _prologue_anchor_plan(
    *,
    dry_run: bool,
    prologue_chunk_id: Optional[int],
) -> dict[str, Any]:
    if prologue_chunk_id is not None:
        status = "already_present"
    elif dry_run:
        status = "would_insert"
    else:
        status = "inserted"
    return {
        "status": status,
        "chunk_id": prologue_chunk_id,
        "marker": RETROGRADE_PROLOGUE_MARKER,
        "raw_text": RETROGRADE_PROLOGUE_RAW_TEXT,
    }


def _append_reference_blockers(
    execute_blockers: list[dict[str, str]],
    reference_issues: Sequence[Mapping[str, Any]],
) -> None:
    if not reference_issues:
        return
    unresolved_count = sum(
        1
        for issue in reference_issues
        if issue.get("resolution") in {"unresolved", "ambiguous", "self_edge"}
    )
    if unresolved_count:
        execute_blockers.append(
            {
                "id": "unresolved_or_ambiguous_entity_refs",
                "reason": (
                    f"{unresolved_count} entity references must resolve before "
                    "Retrograde can write canonical rows"
                ),
            }
        )


def _append_vocabulary_blockers(
    execute_blockers: list[dict[str, str]],
    vocabulary_issues: Sequence[Mapping[str, Any]],
) -> None:
    if not vocabulary_issues:
        return
    execute_blockers.append(
        {
            "id": "missing_slot_vocabulary",
            "reason": (
                f"{len(vocabulary_issues)} planned vocabulary entries are not "
                "registered in this slot"
            ),
        }
    )


def _source_event_template_id(source_event_ref: Any) -> Optional[str]:
    if not source_event_ref:
        return None
    return f"retrograde:{source_event_ref}"


def _normalize_ref(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    return int(value)


def _row_value(row: Any, key: str, index: int) -> Any:
    if hasattr(row, "get"):
        return row[key]
    return row[index]
