"""Canonical Orrery event writer.

The resolver is allowed to compute proposals during preview. This module is the
only place that materializes those proposals into canonical Orrery tables.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
import json
from typing import Any, Mapping, Optional

from nexus.agents.orrery.needs import (
    NeedTuning,
    coerce_need_tuning,
    severity_tag_for_debt,
    severity_tags_for_need,
    normalize_need_type,
)
from nexus.agents.orrery.resolver import (
    OrreryResolutionDraft,
    OrreryTickProposal,
)


ENTITY_BINDING_SLOTS = frozenset({"actor", "target", "targets", "faction"})
SUPPORTED_STATE_DELTA_KEYS = frozenset(
    {
        "character.current_activity",
        "entity_tags.add",
        "entity_tags.remove",
        "entity_tags_target.add",
        "entity_tags_target.remove",
        "need.fulfill",
        "travel.start",
        "travel.advance",
        "travel.arrive",
        "travel.delay",
    }
)

TRAVEL_MODE_DETOUR_FACTOR = {
    "walking": 1.35,
    "vehicle": 1.25,
    "rail": 1.15,
    "water": 1.40,
    "air": 1.05,
    "covert": 1.80,
    "mixed": 1.40,
}
TRAVEL_MODE_SPEED_KMH = {
    "walking": 5.0,
    "vehicle": 45.0,
    "rail": 75.0,
    "water": 25.0,
    "air": 450.0,
    "covert": 3.5,
    "mixed": 25.0,
}


@dataclass(frozen=True, slots=True)
class CommitOrreryTickResult:
    """Summary of a canonical Orrery commit."""

    resolution_count: int = 0
    event_count: int = 0
    tag_mutation_count: int = 0
    cleared_tag_count: int = 0
    skipped_existing_count: int = 0


def coerce_proposal(proposal: Any) -> Optional[OrreryTickProposal]:
    """Coerce incubator JSONB data into an Orrery proposal."""

    if proposal is None:
        return None
    if isinstance(proposal, OrreryTickProposal):
        return proposal
    if isinstance(proposal, str):
        proposal = json.loads(proposal)
    if isinstance(proposal, Mapping):
        return OrreryTickProposal.from_dict(proposal)
    raise TypeError(f"Unsupported Orrery proposal payload: {type(proposal).__name__}")


def commit_orrery_tick_sync(
    conn: Any,
    proposal: Any,
    *,
    tick_chunk_id: int,
    slot: Optional[int] = None,
    world_layer: Optional[str] = "primary",
    sunhelm_settings: Optional[Any] = None,
) -> CommitOrreryTickResult:
    """Materialize a preview proposal inside the accepted-chunk transaction."""

    coerced = coerce_proposal(proposal)
    if coerced is None or not coerced.resolutions:
        return CommitOrreryTickResult()

    need_tuning = coerce_need_tuning(sunhelm_settings)
    _validate_proposal(coerced)
    with conn.cursor() as cur:
        entity_ids = _entity_ids_from_proposal(coerced)
        _validate_entity_ids_sync(cur, entity_ids)
        entity_names = _entity_names_sync(cur, entity_ids)

        resolution_count = 0
        event_count = 0
        tag_mutation_count = 0
        cleared_tag_count = 0
        skipped_existing_count = 0

        for draft in coerced.resolutions:
            actor_entity_id = _scalar_entity_binding(draft.bindings, "actor")
            target_entity_id = _scalar_entity_binding(draft.bindings, "target")
            brief = _render_brief(draft, entity_names)
            resolution_id = _insert_resolution_sync(
                cur,
                draft,
                tick_chunk_id=tick_chunk_id,
                actor_entity_id=actor_entity_id,
                brief=brief,
            )
            if resolution_id is None:
                skipped_existing_count += 1
                continue

            resolution_count += 1
            tag_mutation_count += _apply_state_delta_sync(
                cur,
                draft,
                actor_entity_id=actor_entity_id,
                target_entity_id=target_entity_id,
                source_chunk_id=tick_chunk_id,
                need_tuning=need_tuning,
            )
            event_id = _emit_world_event_sync(
                cur,
                draft,
                tick_chunk_id=tick_chunk_id,
                resolution_id=resolution_id,
                actor_entity_id=actor_entity_id,
                target_entity_id=target_entity_id,
                world_layer=world_layer,
            )
            if event_id is not None:
                event_count += 1
                _update_resolution_events_sync(cur, resolution_id, [event_id])
                if actor_entity_id is not None:
                    cleared_tag_count += _clear_event_tags_sync(
                        cur,
                        entity_id=actor_entity_id,
                        event_type=str(draft.event_type),
                        triggering_event_id=event_id,
                        source_chunk_id=tick_chunk_id,
                    )

    return CommitOrreryTickResult(
        resolution_count=resolution_count,
        event_count=event_count,
        tag_mutation_count=tag_mutation_count,
        cleared_tag_count=cleared_tag_count,
        skipped_existing_count=skipped_existing_count,
    )


async def commit_orrery_tick_async(
    conn: Any,
    proposal: Any,
    *,
    tick_chunk_id: int,
    slot: Optional[int] = None,
    world_layer: Optional[str] = "primary",
    sunhelm_settings: Optional[Any] = None,
) -> CommitOrreryTickResult:
    """Async parity wrapper for tests and non-production commit callers."""

    coerced = coerce_proposal(proposal)
    if coerced is None or not coerced.resolutions:
        return CommitOrreryTickResult()

    need_tuning = coerce_need_tuning(sunhelm_settings)
    _validate_proposal(coerced)
    entity_ids = _entity_ids_from_proposal(coerced)
    await _validate_entity_ids_async(conn, entity_ids)
    entity_names = await _entity_names_async(conn, entity_ids)

    resolution_count = 0
    event_count = 0
    tag_mutation_count = 0
    cleared_tag_count = 0
    skipped_existing_count = 0

    for draft in coerced.resolutions:
        actor_entity_id = _scalar_entity_binding(draft.bindings, "actor")
        target_entity_id = _scalar_entity_binding(draft.bindings, "target")
        brief = _render_brief(draft, entity_names)
        resolution_id = await _insert_resolution_async(
            conn,
            draft,
            tick_chunk_id=tick_chunk_id,
            actor_entity_id=actor_entity_id,
            brief=brief,
        )
        if resolution_id is None:
            skipped_existing_count += 1
            continue

        resolution_count += 1
        tag_mutation_count += await _apply_state_delta_async(
            conn,
            draft,
            actor_entity_id=actor_entity_id,
            target_entity_id=target_entity_id,
            source_chunk_id=tick_chunk_id,
            need_tuning=need_tuning,
        )
        event_id = await _emit_world_event_async(
            conn,
            draft,
            tick_chunk_id=tick_chunk_id,
            resolution_id=resolution_id,
            actor_entity_id=actor_entity_id,
            target_entity_id=target_entity_id,
            world_layer=world_layer,
        )
        if event_id is not None:
            event_count += 1
            await _update_resolution_events_async(conn, resolution_id, [event_id])
            if actor_entity_id is not None:
                cleared_tag_count += await _clear_event_tags_async(
                    conn,
                    entity_id=actor_entity_id,
                    event_type=str(draft.event_type),
                    triggering_event_id=event_id,
                    source_chunk_id=tick_chunk_id,
                )

    return CommitOrreryTickResult(
        resolution_count=resolution_count,
        event_count=event_count,
        tag_mutation_count=tag_mutation_count,
        cleared_tag_count=cleared_tag_count,
        skipped_existing_count=skipped_existing_count,
    )


def _validate_proposal(proposal: OrreryTickProposal) -> None:
    for draft in proposal.resolutions:
        unsupported = set(draft.state_delta) - SUPPORTED_STATE_DELTA_KEYS
        if unsupported:
            raise ValueError(
                "Unsupported Orrery state_delta keys for "
                f"{draft.template_id}: {', '.join(sorted(unsupported))}"
            )


def _entity_ids_from_proposal(proposal: OrreryTickProposal) -> set[int]:
    entity_ids: set[int] = set()
    for draft in proposal.resolutions:
        for slot, value in draft.bindings.items():
            if slot not in ENTITY_BINDING_SLOTS:
                continue
            if (
                slot == "targets"
                and isinstance(value, Iterable)
                and not isinstance(value, (str, bytes))
            ):
                entity_ids.update(
                    _coerce_int(item, label=f"{slot} binding") for item in value
                )
            elif value is not None:
                entity_ids.add(_coerce_int(value, label=f"{slot} binding"))
    return entity_ids


def _validate_entity_ids_sync(cur: Any, entity_ids: set[int]) -> None:
    if not entity_ids:
        return
    cur.execute(
        "SELECT id FROM entities WHERE id = ANY(%s)",
        (sorted(entity_ids),),
    )
    found = {_row_get(row, "id", 0) for row in cur.fetchall()}
    missing = entity_ids - found
    if missing:
        raise ValueError(
            f"Orrery proposal references missing entities: {sorted(missing)}"
        )


async def _validate_entity_ids_async(conn: Any, entity_ids: set[int]) -> None:
    if not entity_ids:
        return
    rows = await conn.fetch(
        "SELECT id FROM entities WHERE id = ANY($1::bigint[])",
        sorted(entity_ids),
    )
    found = {_row_get(row, "id", 0) for row in rows}
    missing = entity_ids - found
    if missing:
        raise ValueError(
            f"Orrery proposal references missing entities: {sorted(missing)}"
        )


def _entity_names_sync(cur: Any, entity_ids: set[int]) -> dict[int, str]:
    if not entity_ids:
        return {}
    cur.execute(
        "SELECT id, name FROM entity_names_v WHERE id = ANY(%s)",
        (sorted(entity_ids),),
    )
    return {_row_get(row, "id", 0): _row_get(row, "name", 1) for row in cur.fetchall()}


async def _entity_names_async(conn: Any, entity_ids: set[int]) -> dict[int, str]:
    if not entity_ids:
        return {}
    rows = await conn.fetch(
        "SELECT id, name FROM entity_names_v WHERE id = ANY($1::bigint[])",
        sorted(entity_ids),
    )
    return {_row_get(row, "id", 0): _row_get(row, "name", 1) for row in rows}


def _render_brief(draft: OrreryResolutionDraft, entity_names: Mapping[int, str]) -> str:
    values: dict[str, str] = {}
    for slot, value in draft.bindings.items():
        if isinstance(value, list):
            values[slot] = ", ".join(
                _entity_label(item, entity_names) for item in value
            )
        else:
            values[slot] = _entity_label(value, entity_names)
    try:
        rendered = draft.narrative_stub.format(**values)
    except KeyError as exc:
        missing_key = exc.args[0]
        raise ValueError(
            "Orrery template "
            f"{draft.template_id!r} narrative_stub references missing binding "
            f"{missing_key!r}"
        ) from exc
    return " ".join(rendered.split())


def _entity_label(value: Any, entity_names: Mapping[int, str]) -> str:
    if value is None:
        return "unknown"
    try:
        entity_id = int(value)
    except (TypeError, ValueError):
        return str(value)
    return entity_names.get(entity_id, f"entity {entity_id}")


def _insert_resolution_sync(
    cur: Any,
    draft: OrreryResolutionDraft,
    *,
    tick_chunk_id: int,
    actor_entity_id: Optional[int],
    brief: str,
) -> Optional[int]:
    cur.execute(
        """
        INSERT INTO orrery_resolutions (
            tick_chunk_id, template_id, binding_hash, actor_entity_id,
            priority, magnitude, state_delta, brief
        ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (tick_chunk_id, template_id, binding_hash) DO NOTHING
        RETURNING id
        """,
        (
            tick_chunk_id,
            draft.template_id,
            draft.binding_hash,
            actor_entity_id,
            draft.priority,
            draft.magnitude,
            json.dumps(draft.state_delta),
            brief,
        ),
    )
    row = cur.fetchone()
    if not row:
        return None
    return _row_get(row, "id", 0)


async def _insert_resolution_async(
    conn: Any,
    draft: OrreryResolutionDraft,
    *,
    tick_chunk_id: int,
    actor_entity_id: Optional[int],
    brief: str,
) -> Optional[int]:
    return await conn.fetchval(
        """
        INSERT INTO orrery_resolutions (
            tick_chunk_id, template_id, binding_hash, actor_entity_id,
            priority, magnitude, state_delta, brief
        ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
        ON CONFLICT (tick_chunk_id, template_id, binding_hash) DO NOTHING
        RETURNING id
        """,
        tick_chunk_id,
        draft.template_id,
        draft.binding_hash,
        actor_entity_id,
        draft.priority,
        draft.magnitude,
        json.dumps(draft.state_delta),
        brief,
    )


def _apply_state_delta_sync(
    cur: Any,
    draft: OrreryResolutionDraft,
    *,
    actor_entity_id: Optional[int],
    target_entity_id: Optional[int],
    source_chunk_id: int,
    need_tuning: NeedTuning,
) -> int:
    if not draft.state_delta:
        return 0
    if actor_entity_id is None:
        if "need.fulfill" in draft.state_delta:
            raise ValueError(
                f"need.fulfill in template {draft.template_id!r} "
                "requires an actor binding"
            )
        raise ValueError(f"Orrery draft {draft.template_id} has no actor binding")

    tag_mutations = 0
    if "character.current_activity" in draft.state_delta:
        cur.execute(
            "UPDATE characters SET current_activity = %s WHERE entity_id = %s",
            (draft.state_delta["character.current_activity"], actor_entity_id),
        )
        rowcount = getattr(cur, "rowcount", None)
        if rowcount is None or rowcount < 0:
            raise ValueError("Unable to verify Orrery character update rowcount")
        if rowcount == 0:
            raise ValueError(
                f"Orrery actor entity {actor_entity_id} has no character row"
            )

    for tag in draft.state_delta.get("entity_tags.add", ()) or ():
        if _add_entity_tag_sync(cur, actor_entity_id, str(tag), draft.template_id):
            tag_mutations += 1
    for tag in draft.state_delta.get("entity_tags.remove", ()) or ():
        tag_mutations += _remove_entity_tag_sync(
            cur,
            actor_entity_id,
            str(tag),
            draft.template_id,
            source_chunk_id=source_chunk_id,
            delta_key="entity_tags.remove",
        )

    if (
        draft.state_delta.get("entity_tags_target.add")
        or draft.state_delta.get("entity_tags_target.remove")
    ) and target_entity_id is None:
        raise ValueError(f"Orrery draft {draft.template_id} has no target binding")

    for tag in draft.state_delta.get("entity_tags_target.add", ()) or ():
        if _add_entity_tag_sync(cur, target_entity_id, str(tag), draft.template_id):
            tag_mutations += 1
    for tag in draft.state_delta.get("entity_tags_target.remove", ()) or ():
        tag_mutations += _remove_entity_tag_sync(
            cur,
            target_entity_id,
            str(tag),
            draft.template_id,
            source_chunk_id=source_chunk_id,
            delta_key="entity_tags_target.remove",
        )
    if "need.fulfill" in draft.state_delta:
        tag_mutations += _apply_need_fulfillment_sync(
            cur,
            actor_entity_id=actor_entity_id,
            fulfillment=draft.state_delta["need.fulfill"],
            template_id=draft.template_id,
            source_chunk_id=source_chunk_id,
            need_tuning=need_tuning,
        )
    if "travel.start" in draft.state_delta:
        _apply_travel_start_sync(
            cur,
            actor_entity_id=actor_entity_id,
            payload=draft.state_delta["travel.start"],
            source_chunk_id=source_chunk_id,
        )
    if "travel.advance" in draft.state_delta:
        _apply_travel_advance_sync(
            cur,
            actor_entity_id=actor_entity_id,
            payload=draft.state_delta["travel.advance"],
            source_chunk_id=source_chunk_id,
        )
    if "travel.delay" in draft.state_delta:
        _apply_travel_delay_sync(
            cur,
            actor_entity_id=actor_entity_id,
            payload=draft.state_delta["travel.delay"],
            source_chunk_id=source_chunk_id,
        )
    if "travel.arrive" in draft.state_delta:
        _apply_travel_arrive_sync(
            cur,
            actor_entity_id=actor_entity_id,
            payload=draft.state_delta["travel.arrive"],
            source_chunk_id=source_chunk_id,
        )
    return tag_mutations


async def _apply_state_delta_async(
    conn: Any,
    draft: OrreryResolutionDraft,
    *,
    actor_entity_id: Optional[int],
    target_entity_id: Optional[int],
    source_chunk_id: int,
    need_tuning: NeedTuning,
) -> int:
    if not draft.state_delta:
        return 0
    if actor_entity_id is None:
        if "need.fulfill" in draft.state_delta:
            raise ValueError(
                f"need.fulfill in template {draft.template_id!r} "
                "requires an actor binding"
            )
        raise ValueError(f"Orrery draft {draft.template_id} has no actor binding")

    tag_mutations = 0
    if "character.current_activity" in draft.state_delta:
        status = await conn.execute(
            "UPDATE characters SET current_activity = $1 WHERE entity_id = $2",
            draft.state_delta["character.current_activity"],
            actor_entity_id,
        )
        if _affected_count(status) == 0:
            raise ValueError(
                f"Orrery actor entity {actor_entity_id} has no character row"
            )

    for tag in draft.state_delta.get("entity_tags.add", ()) or ():
        if await _add_entity_tag_async(
            conn, actor_entity_id, str(tag), draft.template_id
        ):
            tag_mutations += 1
    for tag in draft.state_delta.get("entity_tags.remove", ()) or ():
        tag_mutations += await _remove_entity_tag_async(
            conn,
            actor_entity_id,
            str(tag),
            draft.template_id,
            source_chunk_id=source_chunk_id,
            delta_key="entity_tags.remove",
        )

    if (
        draft.state_delta.get("entity_tags_target.add")
        or draft.state_delta.get("entity_tags_target.remove")
    ) and target_entity_id is None:
        raise ValueError(f"Orrery draft {draft.template_id} has no target binding")

    for tag in draft.state_delta.get("entity_tags_target.add", ()) or ():
        if await _add_entity_tag_async(
            conn, target_entity_id, str(tag), draft.template_id
        ):
            tag_mutations += 1
    for tag in draft.state_delta.get("entity_tags_target.remove", ()) or ():
        tag_mutations += await _remove_entity_tag_async(
            conn,
            target_entity_id,
            str(tag),
            draft.template_id,
            source_chunk_id=source_chunk_id,
            delta_key="entity_tags_target.remove",
        )
    if "need.fulfill" in draft.state_delta:
        tag_mutations += await _apply_need_fulfillment_async(
            conn,
            actor_entity_id=actor_entity_id,
            fulfillment=draft.state_delta["need.fulfill"],
            template_id=draft.template_id,
            source_chunk_id=source_chunk_id,
            need_tuning=need_tuning,
        )
    if "travel.start" in draft.state_delta:
        await _apply_travel_start_async(
            conn,
            actor_entity_id=actor_entity_id,
            payload=draft.state_delta["travel.start"],
            source_chunk_id=source_chunk_id,
        )
    if "travel.advance" in draft.state_delta:
        await _apply_travel_advance_async(
            conn,
            actor_entity_id=actor_entity_id,
            payload=draft.state_delta["travel.advance"],
            source_chunk_id=source_chunk_id,
        )
    if "travel.delay" in draft.state_delta:
        await _apply_travel_delay_async(
            conn,
            actor_entity_id=actor_entity_id,
            payload=draft.state_delta["travel.delay"],
            source_chunk_id=source_chunk_id,
        )
    if "travel.arrive" in draft.state_delta:
        await _apply_travel_arrive_async(
            conn,
            actor_entity_id=actor_entity_id,
            payload=draft.state_delta["travel.arrive"],
            source_chunk_id=source_chunk_id,
        )
    return tag_mutations


def _coerce_need_fulfillment(raw: Any) -> dict[str, Any]:
    """Normalize a template's typed need-fulfillment effect."""

    if isinstance(raw, str):
        payload: dict[str, Any] = {"type": raw}
    elif isinstance(raw, Mapping):
        payload = dict(raw)
    else:
        raise ValueError("need.fulfill must be a string or mapping")

    raw_need_type = payload.get("type") or payload.get("need")
    if raw_need_type is None:
        raise ValueError("need.fulfill must include a 'type' or 'need' field")

    need_type = normalize_need_type(str(raw_need_type))
    discharge = payload.get("discharge_debt", payload.get("discharge", 9999.0))
    try:
        payload["discharge_debt"] = float(discharge)
    except (TypeError, ValueError) as exc:
        raise ValueError("need.fulfill discharge_debt must be numeric") from exc
    payload["type"] = need_type
    return payload


def _apply_need_fulfillment_sync(
    cur: Any,
    *,
    actor_entity_id: Optional[int],
    fulfillment: Any,
    template_id: str,
    source_chunk_id: int,
    need_tuning: NeedTuning,
) -> int:
    if actor_entity_id is None:
        raise ValueError(
            f"need.fulfill in template {template_id!r} requires an actor binding"
        )

    payload = _coerce_need_fulfillment(fulfillment)
    need_type = payload["type"]
    world_time = _tick_world_time_sync(cur, source_chunk_id)
    current_debt = _load_or_create_need_debt_sync(
        cur,
        actor_entity_id=actor_entity_id,
        need_type=need_type,
        world_time=world_time,
        need_tuning=need_tuning,
    )
    new_debt = max(0.0, current_debt - float(payload["discharge_debt"]))
    cur.execute(
        """
        UPDATE character_need_states
        SET debt_score = %s,
            last_evaluated_at = %s,
            last_fulfilled_at = %s,
            updated_at = now(),
            metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
        WHERE character_entity_id = %s
          AND need_type = %s::character_need_type
        """,
        (
            new_debt,
            world_time,
            world_time,
            json.dumps({"last_fulfillment": payload}),
            actor_entity_id,
            need_type,
        ),
    )
    return _sync_need_severity_tags_sync(
        cur,
        actor_entity_id=actor_entity_id,
        need_type=need_type,
        debt_score=new_debt,
        template_id=template_id,
        source_chunk_id=source_chunk_id,
        need_tuning=need_tuning,
    )


async def _apply_need_fulfillment_async(
    conn: Any,
    *,
    actor_entity_id: Optional[int],
    fulfillment: Any,
    template_id: str,
    source_chunk_id: int,
    need_tuning: NeedTuning,
) -> int:
    if actor_entity_id is None:
        raise ValueError(
            f"need.fulfill in template {template_id!r} requires an actor binding"
        )

    payload = _coerce_need_fulfillment(fulfillment)
    need_type = payload["type"]
    world_time = await _tick_world_time_async(conn, source_chunk_id)
    current_debt = await _load_or_create_need_debt_async(
        conn,
        actor_entity_id=actor_entity_id,
        need_type=need_type,
        world_time=world_time,
        need_tuning=need_tuning,
    )
    new_debt = max(0.0, current_debt - float(payload["discharge_debt"]))
    await conn.execute(
        """
        UPDATE character_need_states
        SET debt_score = $1,
            last_evaluated_at = $2,
            last_fulfilled_at = $3,
            updated_at = now(),
            metadata = COALESCE(metadata, '{}'::jsonb) || $4::jsonb
        WHERE character_entity_id = $5
          AND need_type = $6::character_need_type
        """,
        new_debt,
        world_time,
        world_time,
        json.dumps({"last_fulfillment": payload}),
        actor_entity_id,
        need_type,
    )
    return await _sync_need_severity_tags_async(
        conn,
        actor_entity_id=actor_entity_id,
        need_type=need_type,
        debt_score=new_debt,
        template_id=template_id,
        source_chunk_id=source_chunk_id,
        need_tuning=need_tuning,
    )


def _coerce_travel_payload(raw: Any) -> dict[str, Any]:
    """Normalize a template's typed travel effect."""

    if raw is None or raw is True:
        return {}
    if isinstance(raw, Mapping):
        return dict(raw)
    raise ValueError("travel state_delta values must be mappings or true")


def _travel_mode(payload: Mapping[str, Any], fallback: str = "mixed") -> str:
    mode = str(payload.get("mode") or payload.get("travel_mode") or fallback)
    if mode not in TRAVEL_MODE_DETOUR_FACTOR:
        raise ValueError(f"Unsupported Orrery travel mode: {mode!r}")
    return mode


def _travel_risk(payload: Mapping[str, Any], fallback: str = "low") -> str:
    risk = str(payload.get("risk") or fallback)
    if risk not in {"low", "moderate", "high", "extreme"}:
        raise ValueError(f"Unsupported Orrery travel risk: {risk!r}")
    return risk


def _apply_travel_start_sync(
    cur: Any,
    *,
    actor_entity_id: Optional[int],
    payload: Any,
    source_chunk_id: int,
) -> None:
    if actor_entity_id is None:
        raise ValueError("travel.start requires an actor binding")
    data = _coerce_travel_payload(payload)
    mode = _travel_mode(data)
    risk = _travel_risk(data)
    world_time = _tick_world_time_sync(cur, source_chunk_id)
    origin_place_id = data.get("origin_place_id") or _actor_location_sync(
        cur, actor_entity_id
    )
    destination_place_id = data.get("destination_place_id")
    if destination_place_id is None:
        destination_place_id = _planned_destination_sync(cur, actor_entity_id)
    if origin_place_id is None or destination_place_id is None:
        raise ValueError("travel.start requires origin and destination places")

    route = _select_route_sync(
        cur,
        origin_place_id=int(origin_place_id),
        destination_place_id=int(destination_place_id),
        mode=mode,
        risk=risk,
    )
    eta = _eta(world_time, route["duration_minutes"])
    progress = float(data.get("initial_progress", 0.0))
    cur.execute(
        """
        INSERT INTO character_travel_states (
            character_entity_id, status, anchor_place_id,
            origin_place_id, destination_place_id,
            route_method, travel_mode, risk, progress_ratio,
            estimated_distance_m, estimated_duration_minutes,
            started_at_world_time, updated_at_world_time, eta_world_time,
            route_metadata
        ) VALUES (
            %s, 'in_transit', %s,
            %s, %s,
            %s::orrery_travel_route_method,
            %s::orrery_travel_mode, %s::orrery_travel_risk, %s,
            %s, %s,
            %s, %s, %s,
            %s::jsonb
        )
        ON CONFLICT (character_entity_id) DO UPDATE SET
            status = EXCLUDED.status,
            anchor_place_id = EXCLUDED.anchor_place_id,
            origin_place_id = EXCLUDED.origin_place_id,
            destination_place_id = EXCLUDED.destination_place_id,
            route_method = EXCLUDED.route_method,
            travel_mode = EXCLUDED.travel_mode,
            risk = EXCLUDED.risk,
            progress_ratio = EXCLUDED.progress_ratio,
            estimated_distance_m = EXCLUDED.estimated_distance_m,
            estimated_duration_minutes = EXCLUDED.estimated_duration_minutes,
            started_at_world_time = EXCLUDED.started_at_world_time,
            updated_at_world_time = EXCLUDED.updated_at_world_time,
            eta_world_time = EXCLUDED.eta_world_time,
            route_metadata = EXCLUDED.route_metadata,
            updated_at = now()
        """,
        (
            actor_entity_id,
            origin_place_id,
            origin_place_id,
            destination_place_id,
            route["route_method"],
            route["travel_mode"],
            route["risk"],
            progress,
            route["distance_m"],
            route["duration_minutes"],
            world_time,
            world_time,
            eta,
            json.dumps(route["metadata"]),
        ),
    )


async def _apply_travel_start_async(
    conn: Any,
    *,
    actor_entity_id: Optional[int],
    payload: Any,
    source_chunk_id: int,
) -> None:
    if actor_entity_id is None:
        raise ValueError("travel.start requires an actor binding")
    data = _coerce_travel_payload(payload)
    mode = _travel_mode(data)
    risk = _travel_risk(data)
    world_time = await _tick_world_time_async(conn, source_chunk_id)
    origin_place_id = data.get("origin_place_id") or await _actor_location_async(
        conn, actor_entity_id
    )
    destination_place_id = data.get("destination_place_id")
    if destination_place_id is None:
        destination_place_id = await _planned_destination_async(conn, actor_entity_id)
    if origin_place_id is None or destination_place_id is None:
        raise ValueError("travel.start requires origin and destination places")

    route = await _select_route_async(
        conn,
        origin_place_id=int(origin_place_id),
        destination_place_id=int(destination_place_id),
        mode=mode,
        risk=risk,
    )
    eta = _eta(world_time, route["duration_minutes"])
    progress = float(data.get("initial_progress", 0.0))
    await conn.execute(
        """
        INSERT INTO character_travel_states (
            character_entity_id, status, anchor_place_id,
            origin_place_id, destination_place_id,
            route_method, travel_mode, risk, progress_ratio,
            estimated_distance_m, estimated_duration_minutes,
            started_at_world_time, updated_at_world_time, eta_world_time,
            route_metadata
        ) VALUES (
            $1, 'in_transit', $2,
            $3, $4,
            $5::orrery_travel_route_method,
            $6::orrery_travel_mode, $7::orrery_travel_risk, $8,
            $9, $10,
            $11, $12, $13,
            $14::jsonb
        )
        ON CONFLICT (character_entity_id) DO UPDATE SET
            status = EXCLUDED.status,
            anchor_place_id = EXCLUDED.anchor_place_id,
            origin_place_id = EXCLUDED.origin_place_id,
            destination_place_id = EXCLUDED.destination_place_id,
            route_method = EXCLUDED.route_method,
            travel_mode = EXCLUDED.travel_mode,
            risk = EXCLUDED.risk,
            progress_ratio = EXCLUDED.progress_ratio,
            estimated_distance_m = EXCLUDED.estimated_distance_m,
            estimated_duration_minutes = EXCLUDED.estimated_duration_minutes,
            started_at_world_time = EXCLUDED.started_at_world_time,
            updated_at_world_time = EXCLUDED.updated_at_world_time,
            eta_world_time = EXCLUDED.eta_world_time,
            route_metadata = EXCLUDED.route_metadata,
            updated_at = now()
        """,
        actor_entity_id,
        origin_place_id,
        origin_place_id,
        destination_place_id,
        route["route_method"],
        route["travel_mode"],
        route["risk"],
        progress,
        route["distance_m"],
        route["duration_minutes"],
        world_time,
        world_time,
        eta,
        json.dumps(route["metadata"]),
    )


def _apply_travel_advance_sync(
    cur: Any,
    *,
    actor_entity_id: Optional[int],
    payload: Any,
    source_chunk_id: int,
) -> None:
    if actor_entity_id is None:
        raise ValueError("travel.advance requires an actor binding")
    data = _coerce_travel_payload(payload)
    progress_delta = float(data.get("progress_delta", 0.35))
    world_time = _tick_world_time_sync(cur, source_chunk_id)
    current = _current_travel_progress_sync(cur, actor_entity_id)
    new_progress = min(1.0, max(0.0, current + progress_delta))
    cur.execute(
        """
        UPDATE character_travel_states
        SET progress_ratio = %s,
            updated_at_world_time = %s,
            updated_at = now()
        WHERE character_entity_id = %s
          AND status = 'in_transit'
        """,
        (new_progress, world_time, actor_entity_id),
    )
    if getattr(cur, "rowcount", 0) == 0:
        raise ValueError(f"Orrery actor entity {actor_entity_id} is not in transit")


async def _apply_travel_advance_async(
    conn: Any,
    *,
    actor_entity_id: Optional[int],
    payload: Any,
    source_chunk_id: int,
) -> None:
    if actor_entity_id is None:
        raise ValueError("travel.advance requires an actor binding")
    data = _coerce_travel_payload(payload)
    progress_delta = float(data.get("progress_delta", 0.35))
    world_time = await _tick_world_time_async(conn, source_chunk_id)
    current = await _current_travel_progress_async(conn, actor_entity_id)
    new_progress = min(1.0, max(0.0, current + progress_delta))
    status = await conn.execute(
        """
        UPDATE character_travel_states
        SET progress_ratio = $1,
            updated_at_world_time = $2,
            updated_at = now()
        WHERE character_entity_id = $3
          AND status = 'in_transit'
        """,
        new_progress,
        world_time,
        actor_entity_id,
    )
    if _affected_count(status) == 0:
        raise ValueError(f"Orrery actor entity {actor_entity_id} is not in transit")


def _apply_travel_delay_sync(
    cur: Any,
    *,
    actor_entity_id: Optional[int],
    payload: Any,
    source_chunk_id: int,
) -> None:
    if actor_entity_id is None:
        raise ValueError("travel.delay requires an actor binding")
    data = _coerce_travel_payload(payload)
    world_time = _tick_world_time_sync(cur, source_chunk_id)
    risk = data.get("risk")
    if risk is not None:
        risk = _travel_risk(data)
    cur.execute(
        """
        UPDATE character_travel_states
        SET risk = COALESCE(%s::orrery_travel_risk, risk),
            updated_at_world_time = %s,
            route_metadata = route_metadata || %s::jsonb,
            updated_at = now()
        WHERE character_entity_id = %s
          AND status = 'in_transit'
        """,
        (
            risk,
            world_time,
            json.dumps({"last_delay": data}),
            actor_entity_id,
        ),
    )
    if getattr(cur, "rowcount", 0) == 0:
        raise ValueError(f"Orrery actor entity {actor_entity_id} is not in transit")


async def _apply_travel_delay_async(
    conn: Any,
    *,
    actor_entity_id: Optional[int],
    payload: Any,
    source_chunk_id: int,
) -> None:
    if actor_entity_id is None:
        raise ValueError("travel.delay requires an actor binding")
    data = _coerce_travel_payload(payload)
    world_time = await _tick_world_time_async(conn, source_chunk_id)
    risk = data.get("risk")
    if risk is not None:
        risk = _travel_risk(data)
    status = await conn.execute(
        """
        UPDATE character_travel_states
        SET risk = COALESCE($1::orrery_travel_risk, risk),
            updated_at_world_time = $2,
            route_metadata = route_metadata || $3::jsonb,
            updated_at = now()
        WHERE character_entity_id = $4
          AND status = 'in_transit'
        """,
        risk,
        world_time,
        json.dumps({"last_delay": data}),
        actor_entity_id,
    )
    if _affected_count(status) == 0:
        raise ValueError(f"Orrery actor entity {actor_entity_id} is not in transit")


def _apply_travel_arrive_sync(
    cur: Any,
    *,
    actor_entity_id: Optional[int],
    payload: Any,
    source_chunk_id: int,
) -> None:
    if actor_entity_id is None:
        raise ValueError("travel.arrive requires an actor binding")
    data = _coerce_travel_payload(payload)
    world_time = _tick_world_time_sync(cur, source_chunk_id)
    destination_place_id = data.get("destination_place_id")
    if destination_place_id is None:
        destination_place_id = _active_destination_sync(cur, actor_entity_id)
    if destination_place_id is None:
        raise ValueError("travel.arrive requires a destination place")
    cur.execute(
        "UPDATE characters SET current_location = %s WHERE entity_id = %s",
        (destination_place_id, actor_entity_id),
    )
    if getattr(cur, "rowcount", 0) == 0:
        raise ValueError(f"Orrery actor entity {actor_entity_id} has no character row")
    cur.execute(
        """
        UPDATE character_travel_states
        SET status = 'at_place',
            anchor_place_id = %s,
            origin_place_id = NULL,
            destination_place_id = NULL,
            progress_ratio = 0,
            estimated_distance_m = NULL,
            estimated_duration_minutes = NULL,
            started_at_world_time = NULL,
            updated_at_world_time = %s,
            eta_world_time = NULL,
            route_metadata = route_metadata || %s::jsonb,
            updated_at = now()
        WHERE character_entity_id = %s
        """,
        (
            destination_place_id,
            world_time,
            json.dumps({"last_arrived_place_id": destination_place_id}),
            actor_entity_id,
        ),
    )
    if getattr(cur, "rowcount", 0) == 0:
        raise ValueError(
            f"Orrery actor entity {actor_entity_id} has no travel state row"
        )


async def _apply_travel_arrive_async(
    conn: Any,
    *,
    actor_entity_id: Optional[int],
    payload: Any,
    source_chunk_id: int,
) -> None:
    if actor_entity_id is None:
        raise ValueError("travel.arrive requires an actor binding")
    data = _coerce_travel_payload(payload)
    world_time = await _tick_world_time_async(conn, source_chunk_id)
    destination_place_id = data.get("destination_place_id")
    if destination_place_id is None:
        destination_place_id = await _active_destination_async(conn, actor_entity_id)
    if destination_place_id is None:
        raise ValueError("travel.arrive requires a destination place")
    status = await conn.execute(
        "UPDATE characters SET current_location = $1 WHERE entity_id = $2",
        destination_place_id,
        actor_entity_id,
    )
    if _affected_count(status) == 0:
        raise ValueError(f"Orrery actor entity {actor_entity_id} has no character row")
    status = await conn.execute(
        """
        UPDATE character_travel_states
        SET status = 'at_place',
            anchor_place_id = $1,
            origin_place_id = NULL,
            destination_place_id = NULL,
            progress_ratio = 0,
            estimated_distance_m = NULL,
            estimated_duration_minutes = NULL,
            started_at_world_time = NULL,
            updated_at_world_time = $2,
            eta_world_time = NULL,
            route_metadata = route_metadata || $3::jsonb,
            updated_at = now()
        WHERE character_entity_id = $4
        """,
        destination_place_id,
        world_time,
        json.dumps({"last_arrived_place_id": destination_place_id}),
        actor_entity_id,
    )
    if _affected_count(status) == 0:
        raise ValueError(
            f"Orrery actor entity {actor_entity_id} has no travel state row"
        )


def _tick_world_time_sync(cur: Any, source_chunk_id: int) -> Any:
    cur.execute(
        "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s",
        (source_chunk_id,),
    )
    row = cur.fetchone()
    if row and _row_get(row, "world_time", 0) is not None:
        return _row_get(row, "world_time", 0)
    cur.execute("SELECT now() AS world_time")
    return _row_get(cur.fetchone(), "world_time", 0)


async def _tick_world_time_async(conn: Any, source_chunk_id: int) -> Any:
    world_time = await conn.fetchval(
        "SELECT world_time FROM chunk_metadata WHERE chunk_id = $1",
        source_chunk_id,
    )
    if world_time is not None:
        return world_time
    return await conn.fetchval("SELECT now()")


def _load_or_create_need_debt_sync(
    cur: Any,
    *,
    actor_entity_id: int,
    need_type: str,
    world_time: Any,
    need_tuning: NeedTuning,
) -> float:
    cur.execute(
        """
        INSERT INTO character_need_states (
            character_entity_id, need_type, debt_score, last_evaluated_at
        ) VALUES (
            %s, %s::character_need_type, 0, %s
        )
        ON CONFLICT (character_entity_id, need_type) DO NOTHING
        """,
        (actor_entity_id, need_type, world_time),
    )
    cur.execute(
        """
        SELECT debt_score, last_evaluated_at
        FROM character_need_states
        WHERE character_entity_id = %s
          AND need_type = %s::character_need_type
        """,
        (actor_entity_id, need_type),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(
            f"Orrery need state missing for actor {actor_entity_id} {need_type}"
        )
    debt_score = float(_row_get(row, "debt_score", 0) or 0.0)
    last_evaluated_at = _row_get(row, "last_evaluated_at", 1)
    elapsed = (world_time - last_evaluated_at).total_seconds() / 3600.0
    if elapsed <= 0:
        return max(0.0, debt_score)
    return max(0.0, debt_score + elapsed * need_tuning.accrual_rates[need_type])


async def _load_or_create_need_debt_async(
    conn: Any,
    *,
    actor_entity_id: int,
    need_type: str,
    world_time: Any,
    need_tuning: NeedTuning,
) -> float:
    await conn.execute(
        """
        INSERT INTO character_need_states (
            character_entity_id, need_type, debt_score, last_evaluated_at
        ) VALUES (
            $1, $2::character_need_type, 0, $3
        )
        ON CONFLICT (character_entity_id, need_type) DO NOTHING
        """,
        actor_entity_id,
        need_type,
        world_time,
    )
    row = await conn.fetchrow(
        """
        SELECT debt_score, last_evaluated_at
        FROM character_need_states
        WHERE character_entity_id = $1
          AND need_type = $2::character_need_type
        """,
        actor_entity_id,
        need_type,
    )
    if row is None:
        raise ValueError(
            f"Orrery need state missing for actor {actor_entity_id} {need_type}"
        )
    debt_score = float(_row_get(row, "debt_score", 0) or 0.0)
    last_evaluated_at = _row_get(row, "last_evaluated_at", 1)
    elapsed = (world_time - last_evaluated_at).total_seconds() / 3600.0
    if elapsed <= 0:
        return max(0.0, debt_score)
    return max(0.0, debt_score + elapsed * need_tuning.accrual_rates[need_type])


def _sync_need_severity_tags_sync(
    cur: Any,
    *,
    actor_entity_id: int,
    need_type: str,
    debt_score: float,
    template_id: str,
    source_chunk_id: int,
    need_tuning: NeedTuning,
) -> int:
    mutations = 0
    desired = severity_tag_for_debt(need_type, debt_score, tuning=need_tuning)
    current_tags = _current_need_severity_tags_sync(
        cur,
        actor_entity_id=actor_entity_id,
        need_type=need_type,
    )
    for tag in current_tags:
        if tag == desired:
            continue
        mutations += _remove_entity_tag_sync(
            cur,
            actor_entity_id,
            tag,
            template_id,
            source_chunk_id=source_chunk_id,
            delta_key="need.fulfill",
        )
    if (
        desired
        and desired not in current_tags
        and _add_entity_tag_sync(cur, actor_entity_id, desired, template_id)
    ):
        mutations += 1
    return mutations


async def _sync_need_severity_tags_async(
    conn: Any,
    *,
    actor_entity_id: int,
    need_type: str,
    debt_score: float,
    template_id: str,
    source_chunk_id: int,
    need_tuning: NeedTuning,
) -> int:
    mutations = 0
    desired = severity_tag_for_debt(need_type, debt_score, tuning=need_tuning)
    current_tags = await _current_need_severity_tags_async(
        conn,
        actor_entity_id=actor_entity_id,
        need_type=need_type,
    )
    for tag in current_tags:
        if tag == desired:
            continue
        mutations += await _remove_entity_tag_async(
            conn,
            actor_entity_id,
            tag,
            template_id,
            source_chunk_id=source_chunk_id,
            delta_key="need.fulfill",
        )
    if (
        desired
        and desired not in current_tags
        and await _add_entity_tag_async(conn, actor_entity_id, desired, template_id)
    ):
        mutations += 1
    return mutations


def _current_need_severity_tags_sync(
    cur: Any,
    *,
    actor_entity_id: int,
    need_type: str,
) -> frozenset[str]:
    tags = severity_tags_for_need(need_type)
    cur.execute(
        """
        SELECT t.tag
        FROM entity_tags et
        JOIN tags t ON t.id = et.tag_id
        WHERE et.entity_id = %s
          AND t.tag = ANY(%s)
          AND et.cleared_at IS NULL
        """,
        (actor_entity_id, list(tags)),
    )
    return frozenset(str(_row_get(row, "tag", 0)) for row in cur.fetchall())


async def _current_need_severity_tags_async(
    conn: Any,
    *,
    actor_entity_id: int,
    need_type: str,
) -> frozenset[str]:
    tags = severity_tags_for_need(need_type)
    rows = await conn.fetch(
        """
        SELECT t.tag
        FROM entity_tags et
        JOIN tags t ON t.id = et.tag_id
        WHERE et.entity_id = $1
          AND t.tag = ANY($2::text[])
          AND et.cleared_at IS NULL
        """,
        actor_entity_id,
        list(tags),
    )
    return frozenset(str(_row_get(row, "tag", 0)) for row in rows)


def _add_entity_tag_sync(
    cur: Any,
    entity_id: int,
    tag: str,
    template_id: str,
) -> bool:
    tag_id = _registered_tag_id_sync(cur, tag)

    cur.execute(
        """
        INSERT INTO entity_tags (entity_id, tag_id, template_id, source_kind)
        VALUES (%s, %s, %s, 'template')
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        (entity_id, tag_id, template_id),
    )
    return cur.fetchone() is not None


def _registered_tag_id_sync(cur: Any, tag: str) -> int:
    cur.execute(
        """
        SELECT id
        FROM tags
        WHERE tag = %s
          AND deprecated = false
          AND synonym_for IS NULL
        """,
        (tag,),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Orrery tag {tag!r} is not registered")
    return _row_get(row, "id", 0)


async def _add_entity_tag_async(
    conn: Any,
    entity_id: int,
    tag: str,
    template_id: str,
) -> bool:
    tag_id = await _registered_tag_id_async(conn, tag)

    inserted_id = await conn.fetchval(
        """
        INSERT INTO entity_tags (entity_id, tag_id, template_id, source_kind)
        VALUES ($1, $2, $3, 'template')
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        entity_id,
        tag_id,
        template_id,
    )
    return inserted_id is not None


async def _registered_tag_id_async(conn: Any, tag: str) -> int:
    tag_id = await conn.fetchval(
        """
        SELECT id
        FROM tags
        WHERE tag = $1
          AND deprecated = false
          AND synonym_for IS NULL
        """,
        tag,
    )
    if tag_id is None:
        raise ValueError(f"Orrery tag {tag!r} is not registered")
    return tag_id


def _remove_entity_tag_sync(
    cur: Any,
    entity_id: int,
    tag: str,
    template_id: str,
    *,
    source_chunk_id: int,
    delta_key: str,
) -> int:
    tag_id = _registered_tag_id_sync(cur, tag)
    cur.execute(
        """
        SELECT et.id
        FROM entity_tags et
        WHERE et.entity_id = %s
          AND et.tag_id = %s
          AND et.cleared_at IS NULL
        """,
        (entity_id, tag_id),
    )
    entity_tag_ids = [_row_get(row, "id", 0) for row in cur.fetchall()]
    for entity_tag_id in entity_tag_ids:
        cur.execute(
            "UPDATE entity_tags SET cleared_at = now() WHERE id = %s",
            (entity_tag_id,),
        )
        cur.execute(
            """
            INSERT INTO tag_clearance_log (
                entity_tag_id, mechanism, justification, source_chunk_id
            ) VALUES (%s, 'authored', %s::jsonb, %s)
            """,
            (
                entity_tag_id,
                json.dumps({"template_id": template_id, "state_delta": delta_key}),
                source_chunk_id,
            ),
        )
    return len(entity_tag_ids)


async def _remove_entity_tag_async(
    conn: Any,
    entity_id: int,
    tag: str,
    template_id: str,
    *,
    source_chunk_id: int,
    delta_key: str,
) -> int:
    tag_id = await _registered_tag_id_async(conn, tag)
    rows = await conn.fetch(
        """
        SELECT et.id
        FROM entity_tags et
        WHERE et.entity_id = $1
          AND et.tag_id = $2
          AND et.cleared_at IS NULL
        """,
        entity_id,
        tag_id,
    )
    entity_tag_ids = [_row_get(row, "id", 0) for row in rows]
    for entity_tag_id in entity_tag_ids:
        await conn.execute(
            "UPDATE entity_tags SET cleared_at = now() WHERE id = $1",
            entity_tag_id,
        )
        await conn.execute(
            """
            INSERT INTO tag_clearance_log (
                entity_tag_id, mechanism, justification, source_chunk_id
            ) VALUES ($1, 'authored', $2::jsonb, $3)
            """,
            entity_tag_id,
            json.dumps({"template_id": template_id, "state_delta": delta_key}),
            source_chunk_id,
        )
    return len(entity_tag_ids)


def _emit_world_event_sync(
    cur: Any,
    draft: OrreryResolutionDraft,
    *,
    tick_chunk_id: int,
    resolution_id: int,
    actor_entity_id: Optional[int],
    target_entity_id: Optional[int],
    world_layer: Optional[str],
) -> Optional[int]:
    if not draft.event_type:
        return None

    _ensure_event_type_sync(cur, draft.event_type)
    location_id = _actor_location_sync(cur, actor_entity_id)
    payload = {
        "template_id": draft.template_id,
        "binding_hash": draft.binding_hash,
        "bindings": dict(draft.bindings),
        "branch_label": draft.branch_label,
        "narrative_stub": draft.narrative_stub,
    }
    cur.execute(
        """
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id, target_entity_id, location_id,
            world_layer, source, changed_fields, magnitude, resolution_id,
            payload
        ) VALUES (%s, %s, %s, %s, %s, %s, 'resolver', %s, %s, %s, %s::jsonb)
        RETURNING id
        """,
        (
            draft.event_type,
            tick_chunk_id,
            actor_entity_id,
            target_entity_id,
            location_id,
            world_layer,
            list(draft.changed_fields),
            draft.magnitude,
            resolution_id,
            json.dumps(payload),
        ),
    )
    event_id = _row_get(cur.fetchone(), "id", 0)
    if actor_entity_id is not None:
        cur.execute(
            """
            INSERT INTO world_event_entities (event_id, role, entity_id)
            VALUES (%s, 'actor', %s)
            ON CONFLICT DO NOTHING
            """,
            (event_id, actor_entity_id),
        )
    if target_entity_id is not None:
        cur.execute(
            """
            INSERT INTO world_event_entities (event_id, role, entity_id)
            VALUES (%s, 'target', %s)
            ON CONFLICT DO NOTHING
            """,
            (event_id, target_entity_id),
        )
    return event_id


async def _emit_world_event_async(
    conn: Any,
    draft: OrreryResolutionDraft,
    *,
    tick_chunk_id: int,
    resolution_id: int,
    actor_entity_id: Optional[int],
    target_entity_id: Optional[int],
    world_layer: Optional[str],
) -> Optional[int]:
    if not draft.event_type:
        return None

    await _ensure_event_type_async(conn, draft.event_type)
    location_id = await _actor_location_async(conn, actor_entity_id)
    payload = {
        "template_id": draft.template_id,
        "binding_hash": draft.binding_hash,
        "bindings": dict(draft.bindings),
        "branch_label": draft.branch_label,
        "narrative_stub": draft.narrative_stub,
    }
    event_id = await conn.fetchval(
        """
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id, target_entity_id, location_id,
            world_layer, source, changed_fields, magnitude, resolution_id,
            payload
        ) VALUES (
            $1, $2, $3, $4, $5, $6::world_layer_type, 'resolver',
            $7::text[], $8, $9, $10::jsonb
        )
        RETURNING id
        """,
        draft.event_type,
        tick_chunk_id,
        actor_entity_id,
        target_entity_id,
        location_id,
        world_layer,
        list(draft.changed_fields),
        draft.magnitude,
        resolution_id,
        json.dumps(payload),
    )
    if actor_entity_id is not None:
        await conn.execute(
            """
            INSERT INTO world_event_entities (event_id, role, entity_id)
            VALUES ($1, 'actor', $2)
            ON CONFLICT DO NOTHING
            """,
            event_id,
            actor_entity_id,
        )
    if target_entity_id is not None:
        await conn.execute(
            """
            INSERT INTO world_event_entities (event_id, role, entity_id)
            VALUES ($1, 'target', $2)
            ON CONFLICT DO NOTHING
            """,
            event_id,
            target_entity_id,
        )
    return event_id


def _ensure_event_type_sync(cur: Any, event_type: str) -> None:
    cur.execute(
        "SELECT type FROM event_types WHERE type = %s AND deprecated = false",
        (event_type,),
    )
    if not cur.fetchone():
        raise ValueError(f"Orrery event type {event_type!r} is not registered")


async def _ensure_event_type_async(conn: Any, event_type: str) -> None:
    exists = await conn.fetchval(
        "SELECT type FROM event_types WHERE type = $1 AND deprecated = false",
        event_type,
    )
    if exists is None:
        raise ValueError(f"Orrery event type {event_type!r} is not registered")


def _actor_location_sync(cur: Any, actor_entity_id: Optional[int]) -> Optional[int]:
    if actor_entity_id is None:
        return None
    cur.execute(
        "SELECT current_location FROM characters WHERE entity_id = %s",
        (actor_entity_id,),
    )
    row = cur.fetchone()
    return _row_get(row, "current_location", 0) if row else None


async def _actor_location_async(
    conn: Any, actor_entity_id: Optional[int]
) -> Optional[int]:
    if actor_entity_id is None:
        return None
    return await conn.fetchval(
        "SELECT current_location FROM characters WHERE entity_id = $1",
        actor_entity_id,
    )


def _planned_destination_sync(cur: Any, actor_entity_id: int) -> Optional[int]:
    # Only explicit planned rows start travel. Completed at_place rows keep
    # destination NULL so stale arrivals cannot silently start a new route.
    cur.execute(
        """
        SELECT destination_place_id
        FROM character_travel_states
        WHERE character_entity_id = %s
          AND status = 'planned'
        """,
        (actor_entity_id,),
    )
    row = cur.fetchone()
    return _row_get(row, "destination_place_id", 0) if row else None


async def _planned_destination_async(conn: Any, actor_entity_id: int) -> Optional[int]:
    return await conn.fetchval(
        """
        SELECT destination_place_id
        FROM character_travel_states
        WHERE character_entity_id = $1
          AND status = 'planned'
        """,
        actor_entity_id,
    )


def _active_destination_sync(cur: Any, actor_entity_id: int) -> Optional[int]:
    cur.execute(
        """
        SELECT destination_place_id
        FROM character_travel_states
        WHERE character_entity_id = %s
          AND status = 'in_transit'
        """,
        (actor_entity_id,),
    )
    row = cur.fetchone()
    return _row_get(row, "destination_place_id", 0) if row else None


async def _active_destination_async(conn: Any, actor_entity_id: int) -> Optional[int]:
    return await conn.fetchval(
        """
        SELECT destination_place_id
        FROM character_travel_states
        WHERE character_entity_id = $1
          AND status = 'in_transit'
        """,
        actor_entity_id,
    )


def _current_travel_progress_sync(cur: Any, actor_entity_id: int) -> float:
    cur.execute(
        """
        SELECT progress_ratio
        FROM character_travel_states
        WHERE character_entity_id = %s
          AND status = 'in_transit'
        """,
        (actor_entity_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Orrery actor entity {actor_entity_id} is not in transit")
    return float(_row_get(row, "progress_ratio", 0) or 0.0)


async def _current_travel_progress_async(conn: Any, actor_entity_id: int) -> float:
    progress = await conn.fetchval(
        """
        SELECT progress_ratio
        FROM character_travel_states
        WHERE character_entity_id = $1
          AND status = 'in_transit'
        """,
        actor_entity_id,
    )
    if progress is None:
        raise ValueError(f"Orrery actor entity {actor_entity_id} is not in transit")
    return float(progress or 0.0)


def _select_route_sync(
    cur: Any,
    *,
    origin_place_id: int,
    destination_place_id: int,
    mode: str,
    risk: str,
) -> dict[str, Any]:
    edge = _authored_route_edge_sync(
        cur,
        origin_place_id=origin_place_id,
        destination_place_id=destination_place_id,
        mode=mode,
    )
    if edge is not None:
        row, reversed_edge = edge
        return _route_from_authored_edge(
            row,
            origin_place_id=origin_place_id,
            destination_place_id=destination_place_id,
            requested_mode=mode,
            reversed_edge=reversed_edge,
        )
    return _estimate_route_sync(
        cur,
        origin_place_id=origin_place_id,
        destination_place_id=destination_place_id,
        mode=mode,
        risk=risk,
    )


async def _select_route_async(
    conn: Any,
    *,
    origin_place_id: int,
    destination_place_id: int,
    mode: str,
    risk: str,
) -> dict[str, Any]:
    edge = await _authored_route_edge_async(
        conn,
        origin_place_id=origin_place_id,
        destination_place_id=destination_place_id,
        mode=mode,
    )
    if edge is not None:
        row, reversed_edge = edge
        return _route_from_authored_edge(
            row,
            origin_place_id=origin_place_id,
            destination_place_id=destination_place_id,
            requested_mode=mode,
            reversed_edge=reversed_edge,
        )
    return await _estimate_route_async(
        conn,
        origin_place_id=origin_place_id,
        destination_place_id=destination_place_id,
        mode=mode,
        risk=risk,
    )


def _authored_route_edge_sync(
    cur: Any,
    *,
    origin_place_id: int,
    destination_place_id: int,
    mode: str,
) -> Optional[tuple[Any, bool]]:
    cur.execute(
        """
        SELECT id,
               from_place_id,
               to_place_id,
               route_method::text AS route_method,
               travel_mode::text AS travel_mode,
               risk::text AS risk,
               bidirectional,
               distance_m,
               duration_minutes,
               ST_AsGeoJSON(route_geometry) AS route_geometry_geojson,
               source,
               metadata
        FROM orrery_travel_edges
        WHERE from_place_id = %s
          AND to_place_id = %s
          AND route_method = 'authored_edge'
          AND travel_mode = %s::orrery_travel_mode
        ORDER BY id
        LIMIT 1
        """,
        (origin_place_id, destination_place_id, mode),
    )
    row = cur.fetchone()
    if row is not None:
        return row, False

    cur.execute(
        """
        SELECT id,
               from_place_id,
               to_place_id,
               route_method::text AS route_method,
               travel_mode::text AS travel_mode,
               risk::text AS risk,
               bidirectional,
               distance_m,
               duration_minutes,
               ST_AsGeoJSON(route_geometry) AS route_geometry_geojson,
               source,
               metadata
        FROM orrery_travel_edges
        WHERE from_place_id = %s
          AND to_place_id = %s
          AND route_method = 'authored_edge'
          AND travel_mode = %s::orrery_travel_mode
          AND bidirectional = true
        ORDER BY id
        LIMIT 1
        """,
        (destination_place_id, origin_place_id, mode),
    )
    row = cur.fetchone()
    if row is not None:
        return row, True
    return None


async def _authored_route_edge_async(
    conn: Any,
    *,
    origin_place_id: int,
    destination_place_id: int,
    mode: str,
) -> Optional[tuple[Any, bool]]:
    row = await conn.fetchrow(
        """
        SELECT id,
               from_place_id,
               to_place_id,
               route_method::text AS route_method,
               travel_mode::text AS travel_mode,
               risk::text AS risk,
               bidirectional,
               distance_m,
               duration_minutes,
               ST_AsGeoJSON(route_geometry) AS route_geometry_geojson,
               source,
               metadata
        FROM orrery_travel_edges
        WHERE from_place_id = $1
          AND to_place_id = $2
          AND route_method = 'authored_edge'
          AND travel_mode = $3::orrery_travel_mode
        ORDER BY id
        LIMIT 1
        """,
        origin_place_id,
        destination_place_id,
        mode,
    )
    if row is not None:
        return row, False

    row = await conn.fetchrow(
        """
        SELECT id,
               from_place_id,
               to_place_id,
               route_method::text AS route_method,
               travel_mode::text AS travel_mode,
               risk::text AS risk,
               bidirectional,
               distance_m,
               duration_minutes,
               ST_AsGeoJSON(route_geometry) AS route_geometry_geojson,
               source,
               metadata
        FROM orrery_travel_edges
        WHERE from_place_id = $1
          AND to_place_id = $2
          AND route_method = 'authored_edge'
          AND travel_mode = $3::orrery_travel_mode
          AND bidirectional = true
        ORDER BY id
        LIMIT 1
        """,
        destination_place_id,
        origin_place_id,
        mode,
    )
    if row is not None:
        return row, True
    return None


def _route_from_authored_edge(
    row: Any,
    *,
    origin_place_id: int,
    destination_place_id: int,
    requested_mode: str,
    reversed_edge: bool,
) -> dict[str, Any]:
    edge_id = int(_row_get(row, "id", 0))
    edge_from_place_id = int(_row_get(row, "from_place_id", 1))
    edge_to_place_id = int(_row_get(row, "to_place_id", 2))
    travel_mode = str(_row_get(row, "travel_mode", 4))
    risk = str(_row_get(row, "risk", 5))
    route_geometry = _decode_json_value(
        _row_get_optional(row, "route_geometry_geojson", 9)
    )
    metadata = {
        "route_method": "authored_edge",
        "origin_place_id": origin_place_id,
        "destination_place_id": destination_place_id,
        "requested_travel_mode": requested_mode,
        "travel_mode": travel_mode,
        "risk": risk,
        "route_edge_id": edge_id,
        "edge_from_place_id": edge_from_place_id,
        "edge_to_place_id": edge_to_place_id,
        "bidirectional": bool(_row_get(row, "bidirectional", 6)),
        "reversed": reversed_edge,
        "source": _row_get_optional(row, "source", 10),
        "edge_metadata": _decode_json_value(_row_get_optional(row, "metadata", 11))
        or {},
    }
    if route_geometry is not None:
        metadata["route_geometry"] = route_geometry
    return {
        "route_method": "authored_edge",
        "travel_mode": travel_mode,
        "risk": risk,
        "distance_m": _float_or_none(_row_get(row, "distance_m", 7)),
        "duration_minutes": _float_or_none(_row_get(row, "duration_minutes", 8)),
        "metadata": metadata,
    }


def _estimate_route_sync(
    cur: Any,
    *,
    origin_place_id: int,
    destination_place_id: int,
    mode: str,
    risk: str,
) -> dict[str, Any]:
    cur.execute(
        """
        SELECT ST_Distance(o.coordinates, d.coordinates) AS geodesic_distance_m
        FROM places o
        JOIN places d ON d.id = %s
        WHERE o.id = %s
          AND o.coordinates IS NOT NULL
          AND d.coordinates IS NOT NULL
        """,
        (destination_place_id, origin_place_id),
    )
    row = cur.fetchone()
    geodesic_distance_m = _row_get(row, "geodesic_distance_m", 0) if row else None
    return _route_estimate_from_distance(
        geodesic_distance_m,
        origin_place_id=origin_place_id,
        destination_place_id=destination_place_id,
        mode=mode,
        risk=risk,
    )


async def _estimate_route_async(
    conn: Any,
    *,
    origin_place_id: int,
    destination_place_id: int,
    mode: str,
    risk: str,
) -> dict[str, Any]:
    geodesic_distance_m = await conn.fetchval(
        """
        SELECT ST_Distance(o.coordinates, d.coordinates) AS geodesic_distance_m
        FROM places o
        JOIN places d ON d.id = $1
        WHERE o.id = $2
          AND o.coordinates IS NOT NULL
          AND d.coordinates IS NOT NULL
        """,
        destination_place_id,
        origin_place_id,
    )
    return _route_estimate_from_distance(
        geodesic_distance_m,
        origin_place_id=origin_place_id,
        destination_place_id=destination_place_id,
        mode=mode,
        risk=risk,
    )


def _route_estimate_from_distance(
    geodesic_distance_m: Any,
    *,
    origin_place_id: int,
    destination_place_id: int,
    mode: str,
    risk: str,
) -> dict[str, Any]:
    detour_factor = TRAVEL_MODE_DETOUR_FACTOR[mode]
    speed_kmh = TRAVEL_MODE_SPEED_KMH[mode]
    if geodesic_distance_m is None:
        distance_m = None
        duration_minutes = None
    else:
        distance_m = max(0.0, float(geodesic_distance_m) * detour_factor)
        duration_minutes = (distance_m / 1000.0) / speed_kmh * 60.0
    metadata = {
        "route_method": "estimated",
        "origin_place_id": origin_place_id,
        "destination_place_id": destination_place_id,
        "travel_mode": mode,
        "risk": risk,
        "geodesic_distance_m": (
            float(geodesic_distance_m) if geodesic_distance_m is not None else None
        ),
        "detour_factor": detour_factor,
        "speed_kmh": speed_kmh,
    }
    return {
        "route_method": "estimated",
        "travel_mode": mode,
        "risk": risk,
        "distance_m": distance_m,
        "duration_minutes": duration_minutes,
        "metadata": metadata,
    }


def _eta(world_time: Any, duration_minutes: Optional[float]) -> Any:
    if world_time is None or duration_minutes is None:
        return None
    return world_time + timedelta(minutes=float(duration_minutes))


def _update_resolution_events_sync(
    cur: Any, resolution_id: int, event_ids: list[int]
) -> None:
    cur.execute(
        "UPDATE orrery_resolutions SET event_ids = %s WHERE id = %s",
        (event_ids, resolution_id),
    )


async def _update_resolution_events_async(
    conn: Any, resolution_id: int, event_ids: list[int]
) -> None:
    await conn.execute(
        "UPDATE orrery_resolutions SET event_ids = $1::bigint[] WHERE id = $2",
        event_ids,
        resolution_id,
    )


def _clear_event_tags_sync(
    cur: Any,
    *,
    entity_id: int,
    event_type: str,
    triggering_event_id: int,
    source_chunk_id: int,
) -> int:
    cur.execute(
        """
        SELECT et.id
        FROM entity_tags et
        JOIN tags t ON t.id = et.tag_id
        WHERE et.entity_id = %s
          AND et.cleared_at IS NULL
          AND t.clearance_kind = 'event'
          AND t.clear_on IS NOT NULL
          AND t.clear_on -> 'event_types' ? %s
        """,
        (entity_id, event_type),
    )
    tag_ids = [_row_get(row, "id", 0) for row in cur.fetchall()]
    for entity_tag_id in tag_ids:
        cur.execute(
            "UPDATE entity_tags SET cleared_at = now() WHERE id = %s", (entity_tag_id,)
        )
        cur.execute(
            """
            INSERT INTO tag_clearance_log (
                entity_tag_id, mechanism, triggering_event_id,
                justification, source_chunk_id
            ) VALUES (%s, 'event', %s, %s::jsonb, %s)
            """,
            (
                entity_tag_id,
                triggering_event_id,
                json.dumps({"event_type": event_type}),
                source_chunk_id,
            ),
        )
    return len(tag_ids)


async def _clear_event_tags_async(
    conn: Any,
    *,
    entity_id: int,
    event_type: str,
    triggering_event_id: int,
    source_chunk_id: int,
) -> int:
    rows = await conn.fetch(
        """
        SELECT et.id
        FROM entity_tags et
        JOIN tags t ON t.id = et.tag_id
        WHERE et.entity_id = $1
          AND et.cleared_at IS NULL
          AND t.clearance_kind = 'event'
          AND t.clear_on IS NOT NULL
          AND t.clear_on -> 'event_types' ? $2
        """,
        entity_id,
        event_type,
    )
    tag_ids = [_row_get(row, "id", 0) for row in rows]
    for entity_tag_id in tag_ids:
        await conn.execute(
            "UPDATE entity_tags SET cleared_at = now() WHERE id = $1",
            entity_tag_id,
        )
        await conn.execute(
            """
            INSERT INTO tag_clearance_log (
                entity_tag_id, mechanism, triggering_event_id,
                justification, source_chunk_id
            ) VALUES ($1, 'event', $2, $3::jsonb, $4)
            """,
            entity_tag_id,
            triggering_event_id,
            json.dumps({"event_type": event_type}),
            source_chunk_id,
        )
    return len(tag_ids)


def _scalar_entity_binding(bindings: Mapping[str, Any], slot: str) -> Optional[int]:
    value = bindings.get(slot)
    if value is None:
        return None
    return _coerce_int(value, label=f"{slot} binding")


def _coerce_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Orrery {label} must be an integer entity id")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Orrery {label} must be an integer entity id") from exc


def _row_get(row: Any, key: str, index: int) -> Any:
    if isinstance(row, Mapping):
        return row[key]
    return row[index]


def _row_get_optional(row: Any, key: str, index: int, default: Any = None) -> Any:
    try:
        return _row_get(row, key, index)
    except (KeyError, IndexError):
        return default


def _float_or_none(value: Any) -> Optional[float]:
    return None if value is None else float(value)


def _decode_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _affected_count(status: str) -> int:
    try:
        return int(status.rsplit(" ", 1)[1])
    except (IndexError, ValueError):
        return 0
