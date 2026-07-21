"""Dry-run and apply Retrograde expansion plans into canonical Orrery tables."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any, Mapping, Optional, Sequence

from nexus.agents.orrery.epistemics import (
    ClaimParticipant,
    coerce_epistemics_policy,
    mechanical_claim_summary,
    mint_claim_for_event,
)
from nexus.agents.orrery.retrograde_expansion import (
    RetrogradeExpansionDeathPlan,
    RetrogradeExpansionEventPlan,
    RetrogradeExpansionParticipant,
    RetrogradeExpansionPlanResponse,
    RetrogradeExpansionRelationshipPlan,
    validate_expansion_plan,
)
from nexus.agents.orrery.retrograde_markers import (
    RETROGRADE_PROLOGUE_MARKER,
)
from nexus.agents.orrery.retrograde_vocabulary import normalize_entity_ref
from nexus.agents.orrery.status_family import STATUS_TAGS, level_from_status_tag
from nexus.agents.orrery.tag_writer import apply_status_pair_tag_bestowal

RETROGRADE_PERSISTENCE_SCHEMA_VERSION = "orrery_retrograde_persistence_plan.v1"
RETROGRADE_SOURCE_KIND = "retrograde"
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
MATURATION_EVENT_REF_PATTERN = re.compile(r"^maturation_job_(?P<job_id>[1-9]\d*)_")


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


@dataclass(frozen=True, slots=True)
class _TagRecord:
    tag_id: int
    category: str
    entity_kinds: frozenset[str]


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
    summaries_enabled: bool = True,
    recorded_at_chunk_id: Optional[int] = None,
    epistemics_settings: Optional[Any] = None,
) -> dict[str, Any]:
    """Build or apply a canonical persistence plan for a Retrograde expansion.

    Dry-run mode performs only reads and returns row-shaped operations. Execute
    mode writes the prologue anchor, world_events, entity_tags, and
    entity_pair_tags when every planned reference resolves and no unsupported
    relationship rows remain. When ``summaries_enabled`` is true, execute mode
    also writes one dedicated summary row per persisted Retrograde world event;
    the returned manifest lists summary ids still pending embedding.

    ``recorded_at_chunk_id`` identifies the accepted narrative boundary that
    caused this history to be generated. Wizard-time history defaults to the
    synthetic prologue anchor; runtime maturation must pass its requesting
    accepted chunk explicitly.
    """

    expansion = validate_expansion_plan(
        payload=expansion_plan_payload,
        packet=packet,
        seed_candidate_response=seed_candidate_response,
    )
    existing_prologue_id = _find_prologue_chunk_id(cur)
    entity_index = _load_entity_index(cur)
    event_types = _load_event_types(cur)
    tag_records = _load_tag_records(cur)
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
        tag_records=tag_records,
        pair_tag_ids=pair_tag_ids,
        source_blockers=source_blockers,
        world_time=world_time,
        create_missing_entities=create_missing_entities,
        inserted_stub_keys=frozenset(),
        prologue_was_inserted=False,
        summaries_enabled=summaries_enabled,
        recorded_at_chunk_id=recorded_at_chunk_id,
        pair_tag_source_chunk_id=recorded_at_chunk_id,
        epistemics_settings=epistemics_settings,
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

    prologue_was_inserted = existing_prologue_id is None
    prologue_chunk_id = existing_prologue_id or _insert_prologue_chunk(cur)
    _ensure_prologue_metadata(cur, prologue_chunk_id=prologue_chunk_id)
    effective_recorded_at_chunk_id = recorded_at_chunk_id or prologue_chunk_id
    return _build_plan(
        cur,
        expansion=expansion,
        slot=slot,
        dbname=dbname,
        dry_run=False,
        prologue_chunk_id=prologue_chunk_id,
        entity_index=entity_index,
        event_types=event_types,
        tag_records=tag_records,
        pair_tag_ids=pair_tag_ids,
        source_blockers=source_blockers,
        world_time=world_time,
        create_missing_entities=create_missing_entities,
        inserted_stub_keys=inserted_stub_keys,
        prologue_was_inserted=prologue_was_inserted,
        summaries_enabled=summaries_enabled,
        recorded_at_chunk_id=effective_recorded_at_chunk_id,
        pair_tag_source_chunk_id=recorded_at_chunk_id,
        epistemics_settings=epistemics_settings,
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
    tag_records: Mapping[str, _TagRecord],
    pair_tag_ids: Mapping[str, int],
    source_blockers: list[dict[str, str]],
    world_time: Any,
    create_missing_entities: bool,
    inserted_stub_keys: frozenset[tuple[str, str]],
    prologue_was_inserted: bool,
    summaries_enabled: bool,
    recorded_at_chunk_id: Optional[int],
    pair_tag_source_chunk_id: Optional[int],
    epistemics_settings: Optional[Any],
) -> dict[str, Any]:
    counters: Counter[str] = Counter()
    reference_issues: list[dict[str, Any]] = []
    vocabulary_issues: list[dict[str, Any]] = []
    relationship_issues: list[dict[str, Any]] = []
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
        (row["entity_kind"], normalize_entity_ref(row["entity_ref"]))
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
            recorded_at_chunk_id=recorded_at_chunk_id,
            epistemics_settings=epistemics_settings,
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
            tag_records=tag_records,
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
            recorded_at_chunk_id=pair_tag_source_chunk_id,
        )
        pair_tag_rows.append(planned)
        counters[f"pair_tags_{planned['status']}"] += 1
        reference_issues.extend(planned.pop("_reference_issues"))
        vocabulary_issues.extend(planned.pop("_vocabulary_issues"))

    relationship_rows = []
    for relationship in expansion.relationship_plan:
        planned = _plan_relationship_row(
            cur,
            relationship=relationship,
            dry_run=dry_run,
            entity_index=entity_index,
            creatable_refs=creatable_refs,
        )
        relationship_rows.append(planned)
        counters[f"relationships_{planned['status']}"] += 1
        reference_issues.extend(planned.pop("_reference_issues"))
        relationship_issues.extend(planned.pop("_relationship_issues"))

    # Deaths plan after events so cause_world_event_id can link to freshly
    # inserted world_events rows on execute.
    death_rows = []
    death_issues: list[dict[str, Any]] = []
    for death in expansion.death_plan:
        planned = _plan_death_row(
            cur,
            death=death,
            dry_run=dry_run,
            entity_index=entity_index,
            event_ref_to_id=event_ref_to_id,
            creatable_refs=creatable_refs,
            inserted_stub_keys=inserted_stub_keys,
        )
        death_rows.append(planned)
        counters[f"deaths_{planned['status']}"] += 1
        reference_issues.extend(planned.pop("_reference_issues"))
        death_issues.extend(planned.pop("_death_issues"))

    summary_rows: list[dict[str, Any]] = []
    if summaries_enabled:
        summary_rows = plan_retrograde_summaries(
            cur,
            dry_run=dry_run,
            recorded_at_chunk_id=recorded_at_chunk_id,
            event_sources=[
                {
                    "event_ref": str(row["event_ref"]),
                    "summary": str(row["summary"]),
                    "chronology": str(row["chronology"]),
                    "world_event_id": row.get("world_event_id"),
                    "source_status": str(row["status"]),
                }
                for row in event_rows
            ],
        )
        for summary_row in summary_rows:
            counters[f"summaries_{summary_row['status']}"] += 1

    _append_reference_blockers(execute_blockers, reference_issues)
    _append_vocabulary_blockers(execute_blockers, vocabulary_issues)
    _append_relationship_blockers(execute_blockers, relationship_issues)
    _append_death_blockers(execute_blockers, death_issues)

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
        "pair_tags_would_skip_existing_active_status",
        "pair_tags_skipped_existing_active_status",
        "pair_tags_blocked",
        "relationships_would_insert",
        "relationships_inserted",
        "relationships_already_present",
        "relationships_blocked",
        "entity_stubs_would_insert",
        "entity_stubs_inserted",
        "entity_stubs_already_present",
        "entity_stubs_ambiguous_existing",
        "deaths_would_deactivate",
        "deaths_deactivated",
        "deaths_already_inactive",
        "deaths_blocked",
        "summaries_would_insert",
        "summaries_inserted",
        "summaries_already_present",
        "summaries_blocked",
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
            prologue_was_inserted=prologue_was_inserted,
        ),
        "counters": dict(counters),
        "execute_blockers": execute_blockers,
        "reference_issues": reference_issues,
        "vocabulary_issues": vocabulary_issues,
        "relationship_issues": relationship_issues,
        "death_issues": death_issues,
        "entity_stub_rows": entity_stub_rows,
        "event_rows": event_rows,
        "entity_tag_rows": entity_tag_rows,
        "pair_tag_rows": pair_tag_rows,
        "relationship_rows": relationship_rows,
        "death_rows": death_rows,
        "summary_rows": summary_rows,
        "retrieval": {
            "summaries_enabled": summaries_enabled,
            "embedding_pending_summary_ids": [
                int(row["summary_id"])
                for row in summary_rows
                if row["embedding_pending"] and row["summary_id"] is not None
            ],
        },
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
    recorded_at_chunk_id: Optional[int] = None,
    epistemics_settings: Optional[Any] = None,
) -> dict[str, Any]:
    reference_issues: list[dict[str, Any]] = []
    vocabulary_issues: list[dict[str, Any]] = []
    participant_results = []
    actor_entity_id = None
    target_entity_id = None
    claim_source_chunk_id = recorded_at_chunk_id or prologue_chunk_id

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
        claim_result = None
        if not dry_run:
            claim_result = _mint_retrograde_event_claim(
                cur,
                world_event_id=existing_id,
                event_type=event.event_type,
                participant_results=participant_results,
                source_chunk_id=claim_source_chunk_id,
                epistemics_settings=epistemics_settings,
            )
        return {
            **base,
            "status": "already_present",
            "world_event_id": existing_id,
            "claim_id": claim_result.claim_id if claim_result else None,
            "claim_awareness_ids": (
                list(claim_result.awareness_ids) if claim_result else []
            ),
        }
    if reference_issues or vocabulary_issues:
        return {**base, "status": "blocked", "world_event_id": None}
    if prologue_chunk_id is None:
        status = "would_insert" if dry_run else "blocked"
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
    claim_result = _mint_retrograde_event_claim(
        cur,
        world_event_id=world_event_id,
        event_type=event.event_type,
        participant_results=participant_results,
        source_chunk_id=claim_source_chunk_id,
        epistemics_settings=epistemics_settings,
    )
    return {
        **base,
        "status": "inserted",
        "world_event_id": world_event_id,
        "claim_id": claim_result.claim_id if claim_result else None,
        "claim_awareness_ids": list(claim_result.awareness_ids) if claim_result else [],
    }


def _plan_entity_tag_row(
    cur: Any,
    *,
    tag_plan: Mapping[str, Any],
    dry_run: bool,
    entity_index: Mapping[tuple[str, str], Sequence[_EntityRecord]],
    tag_records: Mapping[str, _TagRecord],
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
    tag_record = tag_records.get(tag)
    tag_id = tag_record.tag_id if tag_record is not None else None
    if tag_record is None:
        vocabulary_issues.append(
            {
                "kind": "single_entity_tag",
                "entity_ref": tag_plan["entity_ref"],
                "value": tag,
                "reason": "tag is not registered in this slot",
            }
        )
    else:
        entity_kind = str(entity.get("entity_kind") or tag_plan["entity_kind"])
        if entity_kind not in tag_record.entity_kinds:
            vocabulary_issues.append(
                {
                    "kind": "single_entity_tag",
                    "entity_ref": tag_plan["entity_ref"],
                    "entity_kind": entity_kind,
                    "value": tag,
                    "category": tag_record.category,
                    "allowed_entity_kinds": sorted(tag_record.entity_kinds),
                    "reason": ("tag category is not registered for this entity kind"),
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
    if entity_tag_id is None:
        existing_id = _active_entity_tag_id(cur, int(entity["entity_id"]), int(tag_id))
        return {**base, "status": "already_present", "entity_tag_id": existing_id}
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
    recorded_at_chunk_id: Optional[int],
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

    if tag in STATUS_TAGS:
        active_status_id = _active_status_pair_tag_id(
            cur,
            subject_entity_id=int(subject["entity_id"]),
            object_entity_id=int(object_entity["entity_id"]),
        )
        if active_status_id is not None:
            return {
                **base,
                "status": (
                    "would_skip_existing_active_status"
                    if dry_run
                    else "skipped_existing_active_status"
                ),
                "entity_pair_tag_id": active_status_id,
            }

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

    if tag in STATUS_TAGS:
        inserted = apply_status_pair_tag_bestowal(
            cur,
            subject_entity_id=int(subject["entity_id"]),
            scope_faction_entity_id=int(object_entity["entity_id"]),
            subject_kind=str(pair_plan["subject_kind"]),
            level=level_from_status_tag(tag),
            source_kind=RETROGRADE_SOURCE_KIND,
            world_time=world_time,
            source_chunk_id=recorded_at_chunk_id,
            template_id=base["template_id"],
        )
        entity_pair_tag_id = _active_pair_tag_id(
            cur,
            subject_entity_id=int(subject["entity_id"]),
            object_entity_id=int(object_entity["entity_id"]),
            pair_tag_id=int(pair_tag_id),
        )
        if inserted and entity_pair_tag_id is None:
            raise RuntimeError(
                "Retrograde status bestowal inserted no discoverable active row"
            )
    else:
        entity_pair_tag_id = _insert_pair_tag(
            cur,
            subject_entity_id=int(subject["entity_id"]),
            object_entity_id=int(object_entity["entity_id"]),
            pair_tag_id=int(pair_tag_id),
            template_id=base["template_id"],
            world_time=world_time,
        )
    if entity_pair_tag_id is None:
        existing_id = _active_pair_tag_id(
            cur,
            subject_entity_id=int(subject["entity_id"]),
            object_entity_id=int(object_entity["entity_id"]),
            pair_tag_id=int(pair_tag_id),
        )
        return {
            **base,
            "status": "already_present",
            "entity_pair_tag_id": existing_id,
        }
    return {
        **base,
        "status": "inserted",
        "entity_pair_tag_id": entity_pair_tag_id,
    }


def _plan_relationship_row(
    cur: Any,
    *,
    relationship: RetrogradeExpansionRelationshipPlan,
    dry_run: bool,
    entity_index: Mapping[tuple[str, str], Sequence[_EntityRecord]],
    creatable_refs: frozenset[tuple[str, str]],
) -> dict[str, Any]:
    reference_issues: list[dict[str, Any]] = []
    relationship_issues: list[dict[str, Any]] = []
    subject = _resolve_entity(
        relationship.subject_ref,
        relationship.subject_kind,
        entity_index,
        role="relationship_subject",
        creatable_refs=creatable_refs,
    )
    object_entity = _resolve_entity(
        relationship.object_ref,
        relationship.object_kind,
        entity_index,
        role="relationship_object",
        creatable_refs=creatable_refs,
    )
    for resolved in (subject, object_entity):
        if resolved["resolution"] not in {"resolved", "stub_pending"}:
            reference_issues.append(resolved)

    if (
        subject.get("resolution") == "resolved"
        and object_entity.get("resolution") == "resolved"
        and subject.get("entity_id") == object_entity.get("entity_id")
    ):
        relationship_issues.append(
            {
                "relationship_type": relationship.relationship_type,
                "subject_ref": relationship.subject_ref,
                "object_ref": relationship.object_ref,
                "resolution": "self_edge",
                "reason": "relationship rows require distinct endpoints",
            }
        )

    base = {
        **relationship.model_dump(mode="json"),
        "subject": subject,
        "object": object_entity,
        "subject_entity_id": subject.get("entity_id"),
        "object_entity_id": object_entity.get("entity_id"),
        "template_id": _source_event_template_id(relationship.source_event_ref),
        "_reference_issues": reference_issues,
        "_relationship_issues": relationship_issues,
    }
    if subject["entity_kind"] != "character" or object_entity["entity_kind"] != (
        "character"
    ):
        relationship_issues.append(
            {
                "relationship_type": relationship.relationship_type,
                "subject_ref": relationship.subject_ref,
                "subject_kind": relationship.subject_kind,
                "object_ref": relationship.object_ref,
                "object_kind": relationship.object_kind,
                "resolution": "unsupported_relationship_surface",
                "reason": (
                    "Retrograde can currently write only character-character "
                    "relationship_plan rows; use events or pair tags for "
                    "faction/place mechanics"
                ),
            }
        )

    if reference_issues or relationship_issues:
        return {**base, "status": "blocked"}
    if subject["resolution"] == "stub_pending" or object_entity["resolution"] == (
        "stub_pending"
    ):
        if dry_run:
            return {**base, "status": "would_insert"}
        raise AssertionError("stub_pending must be resolved before execute writes")

    subject_character_id = subject.get("character_id")
    object_character_id = object_entity.get("character_id")
    if subject_character_id is None or object_character_id is None:
        raise AssertionError("character relationship endpoints require character ids")

    existing = _existing_character_relationship(
        cur,
        character1_id=int(subject_character_id),
        character2_id=int(object_character_id),
    )
    if existing is not None:
        return {**base, "status": "already_present", "existing": existing}
    if dry_run:
        return {**base, "status": "would_insert"}

    _insert_character_relationship(
        cur,
        relationship=relationship,
        character1_id=int(subject_character_id),
        character2_id=int(object_character_id),
    )
    return {**base, "status": "inserted"}


def _plan_death_row(
    cur: Any,
    *,
    death: RetrogradeExpansionDeathPlan,
    dry_run: bool,
    entity_index: Mapping[tuple[str, str], Sequence[_EntityRecord]],
    event_ref_to_id: Mapping[str, int],
    creatable_refs: frozenset[tuple[str, str]],
    inserted_stub_keys: frozenset[tuple[str, str]],
) -> dict[str, Any]:
    """Plan or execute one entities.is_active=false flip for an asserted death.

    Deactivation is the complete Orrery kill switch: actor discovery and
    hydration filter on is_active everywhere, so a dead entity stops being
    animated the moment this row executes.

    Deaths may only target backstory figures this plan itself stages as
    stubs (``creatable_refs`` on dry-run, ``inserted_stub_keys`` on
    execute). A death naming a pre-existing active entity is blocked: a
    runtime maturation pass must never deactivate an entity that is live
    in the story. The flip is idempotent — re-running a plan against an
    already-dead entity reports ``already_inactive`` instead of writing.
    """

    reference_issues: list[dict[str, Any]] = []
    death_issues: list[dict[str, Any]] = []
    entity = _resolve_entity(
        death.entity_ref,
        death.entity_kind,
        entity_index,
        role="death",
        creatable_refs=creatable_refs,
    )
    if entity["resolution"] not in {"resolved", "stub_pending"}:
        reference_issues.append(entity)
    base = {
        **death.model_dump(mode="json"),
        "entity": entity,
        "entity_id": entity.get("entity_id"),
        "cause_world_event_id": (
            event_ref_to_id.get(death.cause_event_ref)
            if death.cause_event_ref
            else None
        ),
        "_reference_issues": reference_issues,
        "_death_issues": death_issues,
    }
    if reference_issues:
        return {**base, "status": "blocked"}
    if entity["resolution"] == "stub_pending":
        if dry_run:
            return {**base, "status": "would_deactivate"}
        raise AssertionError("stub_pending must be resolved before execute writes")

    entity_id = int(entity["entity_id"])
    if not _entity_is_active(cur, entity_id):
        return {**base, "status": "already_inactive"}
    death_key = (death.entity_kind, normalize_entity_ref(death.entity_ref))
    if death_key not in inserted_stub_keys:
        death_issues.append(
            {
                "entity_ref": death.entity_ref,
                "entity_kind": death.entity_kind,
                "entity_id": entity_id,
                "reason": (
                    "death targets a pre-existing active entity; deaths may "
                    "only target backstory stubs staged by this same plan"
                ),
            }
        )
        return {**base, "status": "blocked"}
    if dry_run:
        return {**base, "status": "would_deactivate"}
    _deactivate_entity(cur, entity_id)
    return {**base, "status": "deactivated"}


def _entity_is_active(cur: Any, entity_id: int) -> bool:
    cur.execute(
        """
        /* orrery:retrograde:entity_is_active */
        SELECT is_active FROM entities WHERE id = %s
        """,
        (entity_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(
            f"entities row {entity_id} resolved during planning but is missing"
        )
    return bool(_row_value(row, "is_active", 0))


def _deactivate_entity(cur: Any, entity_id: int) -> None:
    cur.execute(
        """
        /* orrery:retrograde:deactivate_entity */
        UPDATE entities SET is_active = false WHERE id = %s
        """,
        (entity_id,),
    )


def plan_retrograde_summaries(
    cur: Any,
    *,
    dry_run: bool,
    recorded_at_chunk_id: Optional[int] = None,
    event_sources: Optional[Sequence[Mapping[str, Any]]] = None,
) -> list[dict[str, Any]]:
    """Ensure one dedicated summary row per Retrograde world event.

    ``retrograde_summaries.world_event_id`` is the idempotency boundary. A
    repeated write with identical summary content, chronology, and recording
    boundary reports ``already_present``; a divergent reapply raises instead
    of quietly accepting conflicting generated history. Embedding is performed
    after the caller's transaction commits.

    Args:
        cur: An open database cursor owned by the caller's transaction.
        dry_run: When true, perform only reads and report planned statuses.
        recorded_at_chunk_id: Accepted narrative boundary at which the history
            was generated. Required for new rows unless each loaded persisted
            event supplies its own boundary.
        event_sources: Event descriptors with a ``world_event_id`` or the
            ``event_ref``, ``summary``, and ``chronology`` needed to plan an
            unpersisted event. Persisted fields are derived from the canonical
            world-event payload; any supplied copies must match it exactly.
            Defaults to every persisted Retrograde world event in the slot.

    Returns:
        Row-shaped plan entries, one per source event.
    """

    if event_sources is None:
        event_sources = _load_persisted_retrograde_event_sources(cur)

    rows: list[dict[str, Any]] = []
    for source in event_sources:
        source_status = str(source.get("source_status") or "persisted")
        world_event_id = _optional_int(source.get("world_event_id"))
        canonical_source = (
            _load_canonical_retrograde_event_source(
                cur,
                world_event_id=world_event_id,
            )
            if world_event_id is not None
            else None
        )
        if canonical_source is not None:
            divergent_fields = [
                field
                for field in ("event_ref", "summary", "chronology")
                if field in source
                and str(source[field]) != str(canonical_source[field])
            ]
            if divergent_fields:
                raise ValueError(
                    f"Retrograde world event {world_event_id} incoming source "
                    "diverges from canonical world_events.payload fields: "
                    + ", ".join(divergent_fields)
                )
            event_ref = str(canonical_source["event_ref"])
            summary = str(canonical_source["summary"])
            chronology = str(canonical_source["chronology"])
        else:
            event_ref = str(source.get("event_ref") or "").strip()
            if not event_ref:
                raise ValueError("Retrograde event source has no event_ref")
            summary = str(source.get("summary") or "").strip()
            chronology = str(source.get("chronology") or "").strip()

        boundary_value = source.get("recorded_at_chunk_id")
        if boundary_value is None:
            boundary_value = recorded_at_chunk_id
        source_recorded_at_chunk_id = _optional_int(boundary_value)
        base = {
            "event_ref": event_ref,
            "world_event_id": world_event_id,
            "recorded_at_chunk_id": source_recorded_at_chunk_id,
            "source_status": source_status,
        }
        if source_status == "blocked":
            rows.append(
                {
                    **base,
                    "status": "blocked",
                    "summary_id": None,
                    "embedding_pending": False,
                }
            )
            continue

        if not summary:
            raise ValueError(
                f"Retrograde event {event_ref!r} has no summary text; cannot "
                "build a retrievable summary"
            )
        if chronology not in {"deep_past", "recent_past", "opening_pressure"}:
            raise ValueError(
                f"Retrograde event {event_ref!r} has invalid chronology "
                f"{chronology!r}"
            )

        existing = (
            _find_retrograde_summary(cur, world_event_id=world_event_id)
            if world_event_id is not None
            else None
        )
        if existing is not None:
            divergent_fields = []
            if existing["summary_text"] != summary:
                divergent_fields.append("summary_text")
            if existing["chronology"] != chronology:
                divergent_fields.append("chronology")
            if (
                source_recorded_at_chunk_id is not None
                and existing["recorded_at_chunk_id"] != source_recorded_at_chunk_id
            ):
                divergent_fields.append("recorded_at_chunk_id")
            if divergent_fields:
                raise ValueError(
                    f"Retrograde world event {world_event_id} already has "
                    "divergent summary fields: " + ", ".join(divergent_fields)
                )
            rows.append(
                {
                    **base,
                    "status": "already_present",
                    "summary_id": existing["summary_id"],
                    "embedding_pending": existing["embedding_generated_at"] is None,
                }
            )
            continue

        if dry_run:
            rows.append(
                {
                    **base,
                    "status": "would_insert",
                    "summary_id": None,
                    "embedding_pending": True,
                }
            )
            continue

        if world_event_id is None:
            raise ValueError(
                f"Retrograde event {event_ref!r} has no persisted world-event id"
            )
        if source_recorded_at_chunk_id is None:
            raise ValueError(
                f"Retrograde event {event_ref!r} has no recorded narrative boundary"
            )
        summary_id = _insert_retrograde_summary(
            cur,
            world_event_id=world_event_id,
            recorded_at_chunk_id=source_recorded_at_chunk_id,
            chronology=chronology,
            summary=summary,
        )
        rows.append(
            {
                **base,
                "status": "inserted",
                "summary_id": summary_id,
                "embedding_pending": True,
            }
        )
    return rows


def _load_canonical_retrograde_event_source(
    cur: Any,
    *,
    world_event_id: int,
) -> dict[str, str]:
    """Load and validate summary identity from the canonical world event."""

    cur.execute(
        """
        /* orrery:retrograde:canonical_world_event_source */
        SELECT
            source::text AS source_kind,
            payload ->> 'retrograde_event_ref' AS event_ref,
            payload ->> 'summary' AS summary,
            payload ->> 'chronology' AS chronology
        FROM world_events
        WHERE id = %s
        """,
        (world_event_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(
            f"Retrograde summary names missing world event {world_event_id}"
        )

    source_kind = str(_row_value(row, "source_kind", 0))
    if source_kind != RETROGRADE_SOURCE_KIND:
        raise ValueError(
            f"Retrograde summary source mismatch for world event "
            f"{world_event_id}: expected {RETROGRADE_SOURCE_KIND!r}, got "
            f"{source_kind!r}"
        )

    canonical: dict[str, str] = {}
    for index, field in enumerate(("event_ref", "summary", "chronology"), start=1):
        value = _row_value(row, field, index)
        if value is None or not str(value).strip():
            if field == "summary":
                raise ValueError(
                    f"Retrograde world event {world_event_id} has no summary "
                    "text in canonical payload"
                )
            raise ValueError(
                f"Retrograde world event {world_event_id} is missing "
                f"payload.{field}"
            )
        canonical[field] = str(value)

    chronology = canonical["chronology"]
    if chronology not in {"deep_past", "recent_past", "opening_pressure"}:
        raise ValueError(
            f"Retrograde world event {world_event_id} has invalid canonical "
            f"payload.chronology {chronology!r}"
        )
    return canonical


def _load_persisted_retrograde_event_sources(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        /* orrery:retrograde:persisted_retrograde_events */
        SELECT
            we.id AS world_event_id,
            we.payload ->> 'retrograde_event_ref' AS event_ref,
            we.payload ->> 'summary' AS summary,
            we.payload ->> 'chronology' AS chronology,
            rs.recorded_at_chunk_id AS existing_recorded_at_chunk_id
        FROM world_events AS we
        LEFT JOIN retrograde_summaries AS rs ON rs.world_event_id = we.id
        WHERE we.source = 'retrograde'::event_source_kind
        ORDER BY we.id
        """
    )
    sources = []
    for row in cur.fetchall():
        world_event_id = int(_row_value(row, "world_event_id", 0))
        event_ref = _row_value(row, "event_ref", 1)
        summary = _row_value(row, "summary", 2)
        chronology = _row_value(row, "chronology", 3)
        existing_recorded_at_chunk_id = _optional_int(
            _row_value(row, "existing_recorded_at_chunk_id", 4)
        )
        if not event_ref:
            raise ValueError(
                f"Retrograde world event {world_event_id} is missing "
                "payload.retrograde_event_ref"
            )
        recorded_at_chunk_id = existing_recorded_at_chunk_id
        if recorded_at_chunk_id is None:
            recorded_at_chunk_id = _derive_recording_boundary(
                cur,
                event_ref=str(event_ref),
            )
        sources.append(
            {
                "event_ref": str(event_ref),
                "summary": summary,
                "chronology": chronology,
                "world_event_id": world_event_id,
                "recorded_at_chunk_id": recorded_at_chunk_id,
                "source_status": "persisted",
            }
        )
    return sources


def _derive_recording_boundary(cur: Any, *, event_ref: str) -> int:
    """Resolve a missing summary's accepted narrative recording boundary."""

    maturation_match = MATURATION_EVENT_REF_PATTERN.match(event_ref)
    if maturation_match is not None:
        job_id = int(maturation_match.group("job_id"))
        cur.execute(
            """
            /* orrery:retrograde:maturation_recording_boundary */
            SELECT requesting_chunk_id
            FROM orrery_maturation_jobs
            WHERE id = %s
            """,
            (job_id,),
        )
        job_row = cur.fetchone()
        if job_row is None:
            raise ValueError(
                f"Runtime Retrograde event {event_ref!r} names missing "
                f"maturation job {job_id}; cannot derive its recording boundary"
            )
        return int(_row_value(job_row, "requesting_chunk_id", 0))

    prologue_chunk_id = _find_prologue_chunk_id(cur)
    if prologue_chunk_id is None:
        raise ValueError(
            f"Wizard Retrograde event {event_ref!r} has no prologue anchor; "
            "cannot derive its recording boundary"
        )
    return prologue_chunk_id


def find_latest_playable_chunk_id(cur: Any) -> Optional[int]:
    """Return the latest accepted played-narrative boundary, if one exists."""

    from nexus.agents.orrery.reconstruction import playable_narrative_predicate

    cur.execute(
        """
        /* orrery:retrograde:latest_playable_recording_boundary */
        SELECT nc.id
        FROM narrative_chunks AS nc
        WHERE nc.state::text = 'finalized'
          AND btrim(COALESCE(nc.storyteller_text, nc.raw_text, '')) <> ''
          AND """
        + playable_narrative_predicate("nc")
        + """
        ORDER BY nc.id DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if row is None:
        return None
    return int(_row_value(row, "id", 0))


def _find_retrograde_summary(
    cur: Any, *, world_event_id: int
) -> Optional[dict[str, Any]]:
    cur.execute(
        """
        /* orrery:retrograde:summary_lookup */
        SELECT
            id,
            recorded_at_chunk_id,
            chronology,
            summary_text,
            embedding_generated_at
        FROM retrograde_summaries
        WHERE world_event_id = %s
        """,
        (world_event_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "summary_id": int(_row_value(row, "id", 0)),
        "recorded_at_chunk_id": int(_row_value(row, "recorded_at_chunk_id", 1)),
        "chronology": str(_row_value(row, "chronology", 2)),
        "summary_text": str(_row_value(row, "summary_text", 3)),
        "embedding_generated_at": _row_value(row, "embedding_generated_at", 4),
    }


def _insert_retrograde_summary(
    cur: Any,
    *,
    world_event_id: int,
    recorded_at_chunk_id: int,
    chronology: str,
    summary: str,
) -> int:
    cur.execute(
        """
        /* orrery:retrograde:insert_summary */
        INSERT INTO retrograde_summaries (
            world_event_id,
            recorded_at_chunk_id,
            chronology,
            summary_text
        )
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (world_event_id, recorded_at_chunk_id, chronology, summary),
    )
    return int(_row_value(cur.fetchone(), "id", 0))


def _mint_retrograde_event_claim(
    cur: Any,
    *,
    world_event_id: int,
    event_type: str,
    participant_results: Sequence[Mapping[str, Any]],
    source_chunk_id: Optional[int],
    epistemics_settings: Optional[Any],
) -> Any:
    """Mint the canonical account through the shared tuple-conflict writer."""

    policy = coerce_epistemics_policy(epistemics_settings)
    if not policy.enabled or event_type not in policy.claim_event_types:
        return None
    participants = []
    for result in participant_results:
        if result.get("resolution") != "resolved":
            continue
        role = str(result["role"])
        participants.append(
            ClaimParticipant(
                entity_id=int(result["entity_id"]),
                role=role,
                name=str(result["name"]),
                entity_kind=str(result["entity_kind"]),
            )
        )
    if not participants:
        return None
    return mint_claim_for_event(
        cur,
        world_event_id=world_event_id,
        event_type=event_type,
        summary=mechanical_claim_summary(event_type, participants),
        participants=participants,
        source_chunk_id=source_chunk_id,
        source_resolution_id=None,
        settings=policy,
    )


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
        "payload": {entry.key: entry.value for entry in event.payload},
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


def _insert_character_relationship(
    cur: Any,
    *,
    relationship: RetrogradeExpansionRelationshipPlan,
    character1_id: int,
    character2_id: int,
) -> None:
    cur.execute(
        """
        /* orrery:retrograde:insert_character_relationship */
        INSERT INTO character_relationships (
            character1_id, character2_id, relationship_type, emotional_valence,
            dynamic, recent_events, history, extra_data
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (character1_id, character2_id) DO NOTHING
        """,
        (
            character1_id,
            character2_id,
            relationship.relationship_type,
            _default_emotional_valence(relationship.relationship_type),
            "latent in generated backstory",
            _relationship_recent_events(relationship),
            _relationship_history(relationship),
            json.dumps(_relationship_extra_data(relationship)),
        ),
    )


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
    # slug and world_time are derived by the chunk metadata triggers.
    cur.execute(
        """
        /* orrery:retrograde:insert_prologue_metadata */
        INSERT INTO chunk_metadata (
            chunk_id, season, episode, scene, world_layer, time_delta,
            generation_date
        )
        VALUES (
            %s, 0, 0, 0, 'retrograde'::world_layer_type,
            interval '0 seconds', now()
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


def _active_status_pair_tag_id(
    cur: Any,
    *,
    subject_entity_id: int,
    object_entity_id: int,
) -> Optional[int]:
    cur.execute(
        """
        /* orrery:retrograde:active_status_pair_tag */
        SELECT ept.id
        FROM entity_pair_tags ept
        JOIN pair_tags pt ON pt.id = ept.pair_tag_id
        WHERE ept.subject_entity_id = %s
          AND ept.object_entity_id = %s
          AND pt.tag LIKE 'status:%%'
          AND ept.cleared_at IS NULL
        ORDER BY ept.id
        LIMIT 1
        """,
        (subject_entity_id, object_entity_id),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return int(_row_value(row, "id", 0))


def _existing_character_relationship(
    cur: Any,
    *,
    character1_id: int,
    character2_id: int,
) -> Optional[dict[str, Any]]:
    cur.execute(
        """
        /* orrery:retrograde:existing_character_relationship */
        SELECT relationship_type, emotional_valence, dynamic, recent_events, history
        FROM character_relationships
        WHERE character1_id = %s AND character2_id = %s
        LIMIT 1
        """,
        (character1_id, character2_id),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "relationship_type": str(_row_value(row, "relationship_type", 0)),
        "emotional_valence": str(_row_value(row, "emotional_valence", 1)),
        "dynamic": str(_row_value(row, "dynamic", 2)),
        "recent_events": str(_row_value(row, "recent_events", 3)),
        "history": str(_row_value(row, "history", 4)),
    }


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
            (record.entity_kind, normalize_entity_ref(record.name)),
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


def _load_tag_records(cur: Any) -> dict[str, _TagRecord]:
    cur.execute(
        """
        /* orrery:retrograde:single_entity_tags */
        SELECT
            t.id,
            t.tag,
            t.category,
            r.entity_kind::text AS entity_kind
        FROM tags t
        LEFT JOIN tag_category_registry r ON r.category = t.category
        WHERE t.deprecated = false AND t.synonym_for IS NULL
        ORDER BY t.tag, r.entity_kind::text
        """
    )
    rows_by_tag: dict[str, dict[str, Any]] = {}
    for row in cur.fetchall():
        tag = str(_row_value(row, "tag", 1))
        entry = rows_by_tag.setdefault(
            tag,
            {
                "tag_id": int(_row_value(row, "id", 0)),
                "category": str(_row_value(row, "category", 2)),
                "entity_kinds": set(),
            },
        )
        entity_kind = _row_value(row, "entity_kind", 3)
        if entity_kind is not None:
            entry["entity_kinds"].add(str(entity_kind))
    return {
        tag: _TagRecord(
            tag_id=int(entry["tag_id"]),
            category=str(entry["category"]),
            entity_kinds=frozenset(entry["entity_kinds"]),
        )
        for tag, entry in rows_by_tag.items()
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
        key = (str(entity_kind), normalize_entity_ref(str(entity_ref)))
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

    for death in expansion.death_plan:
        add_ref(
            death.entity_ref,
            death.entity_kind,
            source={
                "plan": "death_plan",
                "cause_event_ref": death.cause_event_ref,
                "role": "deceased",
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
        inserted.add((entity_kind, normalize_entity_ref(entity_ref)))
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
    # factions.current_activity was retired by migration 058; faction stub
    # state lives in summary and extra_data only.
    cur.execute(
        """
        /* orrery:retrograde:insert_faction_stub */
        INSERT INTO factions (
            id, name, summary, extra_data
        )
        VALUES (%s, %s, %s, %s::jsonb)
        """,
        (
            faction_id,
            entity_ref,
            _stub_summary(entity_ref, "faction"),
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


def _relationship_recent_events(
    relationship: RetrogradeExpansionRelationshipPlan,
) -> str:
    if relationship.source_event_ref:
        return f"Established by Retrograde event {relationship.source_event_ref}."
    return "Established by Retrograde setup history."


def _relationship_history(
    relationship: RetrogradeExpansionRelationshipPlan,
) -> str:
    if relationship.rationale:
        return relationship.rationale
    return (
        "Retrograde-generated setup relationship between "
        f"{relationship.subject_ref} and {relationship.object_ref}."
    )


def _relationship_extra_data(
    relationship: RetrogradeExpansionRelationshipPlan,
) -> dict[str, Any]:
    return {
        "source": RETROGRADE_SOURCE_KIND,
        "retrograde_relationship": True,
        "relationship_type": relationship.relationship_type,
        "subject_ref": relationship.subject_ref,
        "subject_kind": relationship.subject_kind,
        "object_ref": relationship.object_ref,
        "object_kind": relationship.object_kind,
        "source_event_ref": relationship.source_event_ref,
        "rationale": relationship.rationale,
    }


def _default_emotional_valence(relationship_type: str) -> str:
    positive = {
        "ally",
        "chosen_kin",
        "companion",
        "family",
        "friend",
        "guardian",
        "mentor",
        "romantic",
        "ward",
    }
    negative = {"captor", "enemy", "rival"}
    if relationship_type in positive:
        return "+3|trusting"
    if relationship_type in negative:
        return "-3|resentful"
    return "0|neutral"


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
    key = (entity_kind, normalize_entity_ref(entity_ref))
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
    prologue_was_inserted: bool,
) -> dict[str, Any]:
    if prologue_was_inserted:
        status = "inserted"
    elif prologue_chunk_id is not None:
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


_BLOCKER_DETAIL_LIMIT = 8


def _blocker_details(parts: list[str]) -> str:
    """Join blocker item details, truncating very long lists."""

    shown = parts[:_BLOCKER_DETAIL_LIMIT]
    suffix = "" if len(parts) <= _BLOCKER_DETAIL_LIMIT else ", ..."
    return ", ".join(shown) + suffix


def _append_reference_blockers(
    execute_blockers: list[dict[str, str]],
    reference_issues: Sequence[Mapping[str, Any]],
) -> None:
    if not reference_issues:
        return
    unresolved = [
        issue
        for issue in reference_issues
        if issue.get("resolution") in {"unresolved", "ambiguous", "self_edge"}
    ]
    if unresolved:
        details = _blocker_details(
            [
                f"{issue.get('entity_kind')}:{issue.get('entity_ref')} "
                f"({issue.get('resolution')})"
                for issue in unresolved
            ]
        )
        execute_blockers.append(
            {
                "id": "unresolved_or_ambiguous_entity_refs",
                "reason": (
                    f"{len(unresolved)} entity references must resolve before "
                    f"Retrograde can write canonical rows: {details}"
                ),
            }
        )


def _append_death_blockers(
    execute_blockers: list[dict[str, str]],
    death_issues: Sequence[Mapping[str, Any]],
) -> None:
    if not death_issues:
        return
    details = _blocker_details(
        [
            f"{issue.get('entity_kind')}:{issue.get('entity_ref')}"
            for issue in death_issues
        ]
    )
    execute_blockers.append(
        {
            "id": "death_targets_preexisting_entity",
            "reason": (
                f"{len(death_issues)} death plans target pre-existing active "
                f"entities; deaths may only target backstory stubs staged by "
                f"this same plan: {details}"
            ),
        }
    )


def _append_vocabulary_blockers(
    execute_blockers: list[dict[str, str]],
    vocabulary_issues: Sequence[Mapping[str, Any]],
) -> None:
    if not vocabulary_issues:
        return
    details = _blocker_details(
        [
            f"{issue.get('kind')}:{issue.get('value')} ({issue.get('reason')})"
            for issue in vocabulary_issues
        ]
    )
    execute_blockers.append(
        {
            "id": "missing_slot_vocabulary",
            "reason": (
                f"{len(vocabulary_issues)} planned vocabulary entries are not "
                f"registered in this slot: {details}"
            ),
        }
    )


def _append_relationship_blockers(
    execute_blockers: list[dict[str, str]],
    relationship_issues: Sequence[Mapping[str, Any]],
) -> None:
    if not relationship_issues:
        return
    details = _blocker_details(
        [
            f"{issue.get('subject_ref')}-[{issue.get('relationship_type')}]->"
            f"{issue.get('object_ref')} ({issue.get('reason')})"
            for issue in relationship_issues
        ]
    )
    execute_blockers.append(
        {
            "id": "unsupported_relationship_rows",
            "reason": (
                f"{len(relationship_issues)} relationship_plan rows cannot be "
                f"written to canonical relationship tables: {details}"
            ),
        }
    )


def _source_event_template_id(source_event_ref: Any) -> Optional[str]:
    if not source_event_ref:
        return None
    return f"retrograde:{source_event_ref}"


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    return int(value)


def _row_value(row: Any, key: str, index: int) -> Any:
    if hasattr(row, "get"):
        return row[key]
    return row[index]
