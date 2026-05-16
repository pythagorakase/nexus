"""Canonical Orrery event writer.

The resolver is allowed to compute proposals during preview. This module is the
only place that materializes those proposals into canonical Orrery tables.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import json
from typing import Any, Mapping, Optional

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
    }
)


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
) -> CommitOrreryTickResult:
    """Materialize a preview proposal inside the accepted-chunk transaction."""

    coerced = coerce_proposal(proposal)
    if coerced is None or not coerced.resolutions:
        return CommitOrreryTickResult()

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
) -> CommitOrreryTickResult:
    """Async parity wrapper for tests and non-production commit callers."""

    coerced = coerce_proposal(proposal)
    if coerced is None or not coerced.resolutions:
        return CommitOrreryTickResult()

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
) -> int:
    if not draft.state_delta:
        return 0
    if actor_entity_id is None:
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
    return tag_mutations


async def _apply_state_delta_async(
    conn: Any,
    draft: OrreryResolutionDraft,
    *,
    actor_entity_id: Optional[int],
    target_entity_id: Optional[int],
    source_chunk_id: int,
) -> int:
    if not draft.state_delta:
        return 0
    if actor_entity_id is None:
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
    return tag_mutations


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


def _affected_count(status: str) -> int:
    try:
        return int(status.rsplit(" ", 1)[1])
    except (IndexError, ValueError):
        return 0
