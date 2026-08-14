"""
Commit Handler for Narrative Chunks
====================================

Handles the complete flow of committing narrative chunks from incubator
to production tables. Includes entity creation, reference resolution,
and transaction management.
"""

import json
import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, cast

import asyncpg  # type: ignore[import-untyped]

from nexus.agents.logon.apex_schema import (
    ChunkMetadataUpdate,
    ChronologyUpdate,
    ReferencedEntities,
    StateUpdates,
)
from nexus.agents.orrery.bleed import record_bleed_uptake_async
from nexus.agents.orrery.events import commit_orrery_tick_async
from nexus.agents.orrery.reconstruction import (
    capture_state_checkpoint_async,
    interval_checkpoint_due,
    log_state_delta_async,
    playable_narrative_ordinal_async,
    set_commit_chunk_attribution_async,
)
from nexus.agents.orrery.tag_writer import apply_tag_bestowal_async
from nexus.api.db_converters import (
    chronology_to_db_values,
    create_declared_entity_stubs,
    lookup_character_by_name,
    lookup_faction_by_name,
    lookup_place_by_name,
    resolve_character_references,
    resolve_faction_references,
    resolve_place_references,
)
from nexus.api.summary_triggers import (
    SummaryTask,
    plan_summary_tasks,
    schedule_summary_generation,
)
from nexus.api.choice_handling import (
    normalize_choice_object,
    selected_text_from_choice_object,
)
from nexus.api.lore_adapter import compute_raw_text, split_staged_orrery_payload
from nexus.memory.context_state import (
    bind_pass2_baseline,
    validate_staged_pass2_baseline,
)

logger = logging.getLogger("nexus.api.commit_handler")


# ============================================================================
# Database Query Functions
# ============================================================================


async def fetch_incubator_data(
    conn: asyncpg.Connection, session_id: str
) -> Dict[str, Any]:
    """
    Fetch data from incubator table for a given session.
    """
    row = await conn.fetchrow(
        """
        SELECT chunk_id, parent_chunk_id, user_text, storyteller_text,
               choice_object, choice_text, orrery_proposal,
               COALESCE(orrery_adjudications, '[]'::jsonb) AS orrery_adjudications,
               COALESCE(new_entities, '[]'::jsonb) AS new_entities,
               lore_pass_baseline,
               metadata_updates, entity_updates, reference_updates,
               llm_response_id, generation_model, status
        FROM incubator
        WHERE session_id = $1
        """,
        session_id,
    )

    if not row:
        raise ValueError(f"No incubator data found for session {session_id}")

    return dict(row)


async def fetch_chunk_metadata(
    conn: asyncpg.Connection, chunk_id: int
) -> Dict[str, Any]:
    """
    Fetch metadata for an existing chunk.
    """
    row = await conn.fetchrow(
        """
        SELECT season, episode, scene, world_layer, time_delta, world_time
        FROM chunk_metadata
        WHERE chunk_id = $1
        """,
        chunk_id,
    )

    if not row:
        raise ValueError(f"No metadata found for chunk {chunk_id}")

    return dict(row)


async def _require_chunk_world_time(
    conn: asyncpg.Connection, chunk_id: int
) -> datetime:
    """Return the trigger-authored world time for an inserted chunk."""

    world_time = await conn.fetchval(
        "SELECT world_time FROM chunk_metadata WHERE chunk_id = $1",
        chunk_id,
    )
    if not isinstance(world_time, datetime):
        raise ValueError(
            f"Chunk {chunk_id} has no trigger-authored world_time after insertion"
        )
    return world_time


async def _require_state_update_id(
    conn: asyncpg.Connection,
    *,
    kind: str,
    current_id: Optional[int],
    name: Optional[str],
    lookup: Callable[[asyncpg.Connection, str], Awaitable[Optional[int]]],
) -> int:
    """Resolve one state-update identity or fail the commit transaction."""

    if current_id is not None:
        return current_id
    if not name:
        raise ValueError(f"{kind} state update requires an id or name")
    resolved_id = await lookup(conn, name)
    if resolved_id is None:
        raise ValueError(f"Unresolved {kind} state update name {name!r}")
    return resolved_id


async def resolve_state_update_ids(
    conn: asyncpg.Connection,
    state_updates: StateUpdates,
) -> StateUpdates:
    """Resolve all name-addressed state updates to canonical database IDs."""

    resolved = state_updates.model_copy(deep=True)
    for character_update in resolved.characters:
        character_update.character_id = await _require_state_update_id(
            conn,
            kind="character",
            current_id=character_update.character_id,
            name=character_update.character_name,
            lookup=lookup_character_by_name,
        )
    for location_update in resolved.locations:
        location_update.place_id = await _require_state_update_id(
            conn,
            kind="place",
            current_id=location_update.place_id,
            name=location_update.place_name,
            lookup=lookup_place_by_name,
        )
    for faction_update in resolved.factions:
        faction_update.faction_id = await _require_state_update_id(
            conn,
            kind="faction",
            current_id=faction_update.faction_id,
            name=faction_update.faction_name,
            lookup=lookup_faction_by_name,
        )
    for relationship_update in resolved.relationships:
        relationship_update.character1_id = await _require_state_update_id(
            conn,
            kind="relationship character1",
            current_id=relationship_update.character1_id,
            name=relationship_update.character1_name,
            lookup=lookup_character_by_name,
        )
        relationship_update.character2_id = await _require_state_update_id(
            conn,
            kind="relationship character2",
            current_id=relationship_update.character2_id,
            name=relationship_update.character2_name,
            lookup=lookup_character_by_name,
        )
    return resolved


# ============================================================================
# Insert Functions
# ============================================================================


async def insert_narrative_chunk(
    conn: asyncpg.Connection,
    raw_text: str,
    storyteller_text: Optional[str],
    choice_object: Optional[Dict[str, Any]],
    choice_text: Optional[str],
) -> int:
    """
    Insert a new narrative chunk and return its ID.

    Note: season/episode are stored in chunk_metadata, not narrative_chunks.
    """
    chunk_id = await conn.fetchval(
        """
        INSERT INTO narrative_chunks (
            raw_text, storyteller_text, choice_object, choice_text
        )
        VALUES ($1, $2, $3::jsonb, $4)
        RETURNING id
        """,
        raw_text,
        storyteller_text,
        json.dumps(choice_object) if choice_object else None,
        choice_text,
    )
    logger.info(f"Created narrative chunk {chunk_id}")
    # Attribute trigger-versioned writes in this transaction
    # (relationship_versions) to the committing chunk.
    await set_commit_chunk_attribution_async(conn, chunk_id)
    return chunk_id


async def insert_chunk_metadata(
    conn: asyncpg.Connection,
    chunk_id: int,
    season: int,
    episode: int,
    scene: int,
    world_layer: str,
    time_delta: Optional[Any],
    generation_date: Optional[datetime] = None,
    generation_model: Optional[str] = None,
    scene_weather: Optional[str] = None,
) -> None:
    """
    Insert metadata for a chunk.
    """
    # Generate slug (e.g., "S05E06_001")
    slug = f"S{season:02d}E{episode:02d}_{scene:03d}"
    generation_timestamp = generation_date or datetime.utcnow()

    if scene_weather is None:
        await conn.execute(
            """
            INSERT INTO chunk_metadata (
                chunk_id, season, episode, scene, world_layer,
                time_delta, generation_date, slug, generation_model
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            chunk_id,
            season,
            episode,
            scene,
            world_layer,
            time_delta,
            generation_timestamp,
            slug,
            generation_model,
        )
    else:
        await conn.execute(
            """
            INSERT INTO chunk_metadata (
                chunk_id, season, episode, scene, world_layer,
                time_delta, generation_date, slug, generation_model,
                scene_weather
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            chunk_id,
            season,
            episode,
            scene,
            world_layer,
            time_delta,
            generation_timestamp,
            slug,
            generation_model,
            scene_weather,
        )
    logger.info(f"Created metadata for chunk {chunk_id}: {slug}")


async def insert_place_references(
    conn: asyncpg.Connection, chunk_id: int, place_refs: list
) -> None:
    """
    Insert place-chunk references into junction table.
    """
    if not place_refs:
        return

    for ref in place_refs:
        await conn.execute(
            """
            INSERT INTO place_chunk_references (
                place_id, chunk_id, reference_type, evidence
            )
            VALUES ($1, $2, $3, $4)
            """,
            ref["place_id"],
            chunk_id,
            ref["reference_type"],
            ref.get("evidence"),
        )
    logger.info(f"Inserted {len(place_refs)} place references for chunk {chunk_id}")


async def insert_character_references(
    conn: asyncpg.Connection, chunk_id: int, char_refs: list
) -> None:
    """
    Insert character-chunk references into junction table.
    """
    if not char_refs:
        return

    for ref in char_refs:
        await conn.execute(
            """
            INSERT INTO chunk_character_references (chunk_id, character_id, reference)
            VALUES ($1, $2, $3)
            ON CONFLICT (chunk_id, character_id) DO UPDATE
            SET reference = 'present'
            WHERE 'present' IN (
                chunk_character_references.reference,
                EXCLUDED.reference
            )
            """,
            chunk_id,
            ref["character_id"],
            ref["reference"],
        )
    logger.info(f"Inserted {len(char_refs)} character references for chunk {chunk_id}")


async def insert_faction_references(
    conn: asyncpg.Connection, chunk_id: int, faction_refs: list
) -> None:
    """
    Insert faction-chunk references into junction table.
    """
    if not faction_refs:
        return

    for ref in faction_refs:
        await conn.execute(
            """
            INSERT INTO chunk_faction_references (chunk_id, faction_id)
            VALUES ($1, $2)
            ON CONFLICT (chunk_id, faction_id) DO NOTHING
            """,
            chunk_id,
            ref["faction_id"],
        )
    logger.info(f"Inserted {len(faction_refs)} faction references for chunk {chunk_id}")


# ============================================================================
# State Update Functions
# ============================================================================


async def apply_state_updates(
    conn: asyncpg.Connection,
    state_updates: StateUpdates,
    source_chunk_id: Optional[int] = None,
    anchor_world_time: Optional[datetime] = None,
) -> None:
    """
    Apply entity state updates from the LLM response.

    This updates scalar state for characters and places. Faction semantics are
    intentionally not written to legacy faction prose columns; use Orrery tag
    deltas / pair-tags and world events instead. ``anchor_world_time`` is the
    accepting child's trigger-authored clock for tag writes;
    ``source_chunk_id`` remains that child for provenance.
    """
    # Update character states
    for char_update in state_updates.characters:
        if char_update.character_id is None:
            raise ValueError("Character state update was not resolved before apply")
        updates: List[str] = []
        params: List[Any] = []
        param_count = 1
        written_fields: List[tuple[str, Any]] = []

        if char_update.emotional_state:
            updates.append(f"emotional_state = ${param_count}")
            params.append(char_update.emotional_state)
            param_count += 1
            written_fields.append(
                ("characters.emotional_state", char_update.emotional_state)
            )

        if char_update.current_activity:
            updates.append(f"current_activity = ${param_count}")
            params.append(char_update.current_activity)
            param_count += 1
            written_fields.append(
                ("characters.current_activity", char_update.current_activity)
            )

        if char_update.current_location:
            updates.append(f"current_location = ${param_count}")
            params.append(char_update.current_location)
            param_count += 1
            written_fields.append(
                ("characters.current_location", char_update.current_location)
            )

        if updates:
            params.append(char_update.character_id)
            await conn.execute(
                f"""
                UPDATE characters
                SET {', '.join(updates)}
                WHERE id = ${param_count}
                """,
                *params,
            )
            logger.info(f"Updated character {char_update.character_id}")
            if source_chunk_id is not None:
                char_entity_id = await conn.fetchval(
                    "SELECT entity_id FROM characters WHERE id = $1",
                    char_update.character_id,
                )
                for field, value in written_fields:
                    await log_state_delta_async(
                        conn,
                        source_chunk_id=source_chunk_id,
                        writer="skald_state_update",
                        entity_id=char_entity_id,
                        field=field,
                        new_value=value,
                    )

        bestowal = getattr(char_update, "orrery_tags", None)
        if bestowal is not None:
            await apply_state_tags_async(
                conn,
                kind="character",
                subtype_table="characters",
                subtype_id=char_update.character_id,
                bestowal=bestowal,
                source_chunk_id=source_chunk_id,
                anchor_world_time=anchor_world_time,
            )

    # Update place states. The schema field is current_conditions
    # (LocationStateUpdate); it persists to the places.current_status
    # column (M9 gate finding: the old attribute read crashed commits).
    for place_update in state_updates.locations:
        if place_update.place_id is None:
            raise ValueError("Place state update was not resolved before apply")
        if place_update.current_conditions:
            await conn.execute(
                """
                UPDATE places
                SET current_status = $1
                WHERE id = $2
                """,
                place_update.current_conditions,
                place_update.place_id,
            )
            logger.info(f"Updated place {place_update.place_id}")
            if source_chunk_id is not None:
                await log_state_delta_async(
                    conn,
                    source_chunk_id=source_chunk_id,
                    writer="skald_state_update",
                    entity_id=await conn.fetchval(
                        "SELECT entity_id FROM places WHERE id = $1",
                        place_update.place_id,
                    ),
                    field="places.current_status",
                    new_value=place_update.current_conditions,
                )

        bestowal = getattr(place_update, "orrery_tags", None)
        if bestowal is not None:
            await apply_state_tags_async(
                conn,
                kind="place",
                subtype_table="places",
                subtype_id=place_update.place_id,
                bestowal=bestowal,
                source_chunk_id=source_chunk_id,
                anchor_world_time=anchor_world_time,
            )

    for faction_update in state_updates.factions:
        if faction_update.faction_id is None:
            raise ValueError("Faction state update was not resolved before apply")
        bestowal = getattr(faction_update, "orrery_tags", None)
        if bestowal is not None:
            await apply_state_tags_async(
                conn,
                kind="faction",
                subtype_table="factions",
                subtype_id=faction_update.faction_id,
                bestowal=bestowal,
                source_chunk_id=source_chunk_id,
                anchor_world_time=anchor_world_time,
            )

    for relationship_update in state_updates.relationships:
        if (
            relationship_update.character1_id is None
            or relationship_update.character2_id is None
        ):
            raise ValueError("Relationship state update was not resolved before apply")
        updates = []
        params = []
        param_count = 1
        relationship_fields = (
            ("relationship_type", relationship_update.relationship_type),
            ("emotional_valence", relationship_update.emotional_valence),
            ("dynamic", relationship_update.dynamic),
            ("recent_events", relationship_update.recent_events),
        )
        for field, value in relationship_fields:
            if value is None:
                continue
            updates.append(f"{field} = ${param_count}")
            params.append(value.value if hasattr(value, "value") else value)
            param_count += 1
        if updates:
            params.extend(
                [
                    relationship_update.character1_id,
                    relationship_update.character2_id,
                ]
            )
            await conn.execute(
                f"""
                UPDATE character_relationships
                SET {', '.join(updates)}
                WHERE character1_id = ${param_count}
                  AND character2_id = ${param_count + 1}
                """,
                *params,
            )


async def apply_state_tags_async(
    conn: asyncpg.Connection,
    *,
    kind: str,
    subtype_table: str,
    subtype_id: int,
    bestowal: Any,
    source_chunk_id: Optional[int] = None,
    anchor_world_time: Optional[datetime] = None,
) -> None:
    """Look up the entity_id for a subtype row and apply Skald-bestowed tags."""

    row = await conn.fetchrow(
        f"SELECT entity_id FROM {subtype_table} WHERE id = $1",
        subtype_id,
    )
    if row is None:
        logger.warning(f"Skipping tag bestowal: no {kind} row for id={subtype_id}")
        return

    counters = await apply_tag_bestowal_async(
        conn,
        entity_id=row["entity_id"],
        entity_kind=kind,
        bestowal=bestowal,
        source_kind="skald_inline",
        world_time=anchor_world_time,
        world_time_is_authoritative=True,
        source_chunk_id=source_chunk_id,
    )
    if any(counters.values()):
        logger.info(f"Tag bestowal {kind}/{subtype_id}: {counters}")


async def clear_incubator(
    conn: asyncpg.Connection, session_id: Optional[str] = None
) -> None:
    """
    Clear incubator after successful commit.
    If session_id is provided, only clear that session.
    Otherwise, clear all (for singleton incubator).
    """
    if session_id:
        await conn.execute("DELETE FROM incubator WHERE session_id = $1", session_id)
        logger.info(f"Cleared incubator for session {session_id}")
    else:
        await conn.execute("DELETE FROM incubator")
        logger.info("Cleared all incubator data")


# ============================================================================
# Main Commit Function
# ============================================================================


async def commit_incubator_to_database(
    conn: asyncpg.Connection, session_id: str, slot: Optional[int] = None
) -> int:
    """
    Complete commit flow from incubator to production tables.

    Transaction steps:
    1. Read and validate incubator data
    2. Get parent chunk context (season/episode/scene)
    3. Convert metadata (time, episode transitions)
    4. Insert narrative chunk
    5. Create declaration stubs
    6. Resolve entity references
    7. Insert chunk metadata
    8. Insert junction table references
    9. Update entity states and commit the Orrery tick
    10. Clear incubator

    Returns:
        New chunk ID

    Raises:
        ValueError: If data is missing or invalid
        asyncpg.PostgresError: If database operation fails
    """
    summary_tasks: List[SummaryTask] = []
    chunk_id: Optional[int] = None
    state_updates: Optional[StateUpdates] = None

    async with conn.transaction():
        try:
            # Step 1: Get incubator data
            incubator = await fetch_incubator_data(conn, session_id)
            validate_staged_pass2_baseline(incubator["lore_pass_baseline"])
            logger.info("Processing incubator session %s", session_id)

            # Step 2: Get parent context. Bootstrap has no validation/read
            # anchor; its inserted child metadata still supplies the write clock.
            parent_meta: Dict[str, Any]
            if incubator["parent_chunk_id"] == 0:
                parent_meta = {
                    "season": 1,
                    "episode": 1,
                    "scene": 0,
                    "world_layer": "primary",
                    "time_delta": 0,
                    "world_time": None,
                }
                logger.info("Bootstrap chunk - using default metadata (S1E1 scene 1)")
            else:
                parent_meta = await fetch_chunk_metadata(
                    conn, incubator["parent_chunk_id"]
                )
                logger.info(
                    "Parent chunk %s: S%sE%s scene %s",
                    incubator["parent_chunk_id"],
                    parent_meta["season"],
                    parent_meta["episode"],
                    parent_meta["scene"],
                )

            # Step 3: Convert metadata
            metadata_update = ChunkMetadataUpdate(**incubator["metadata_updates"])
            chronology_data = incubator["metadata_updates"].get("chronology", {})
            chronology = ChronologyUpdate(**chronology_data)
            db_meta = chronology_to_db_values(
                chronology,
                current_season=parent_meta["season"],
                current_episode=parent_meta["episode"],
            )
            summary_tasks = plan_summary_tasks(
                chronology.episode_transition,
                parent_meta["season"],
                parent_meta["episode"],
            )

            # Increment scene number
            db_meta["scene"] = parent_meta["scene"] + 1

            # Get world_layer
            world_layer = incubator["metadata_updates"].get("world_layer", "primary")

            # Step 4: Insert narrative chunk
            choice_object = incubator.get("choice_object")
            storyteller_text = incubator.get("storyteller_text") or ""
            choice_text = incubator.get("choice_text")
            if choice_object:
                if not choice_text:
                    choice_text = selected_text_from_choice_object(choice_object)
                choice_object = normalize_choice_object(choice_object)

            raw_text = compute_raw_text(storyteller_text, choice_object, choice_text)
            chunk_id = await insert_narrative_chunk(
                conn,
                raw_text=raw_text,
                storyteller_text=storyteller_text,
                choice_object=choice_object,
                choice_text=choice_text,
            )
            if chunk_id is None:
                raise ValueError("Failed to obtain chunk_id after insert")
            bound_baseline = bind_pass2_baseline(
                incubator["lore_pass_baseline"], chunk_id
            )
            await conn.execute(
                """
                INSERT INTO lore_pass_baselines (chunk_id, schema_version, payload)
                VALUES ($1, $2, $3::text::jsonb)
                """,
                chunk_id,
                bound_baseline.schema_version,
                json.dumps(bound_baseline.model_dump(mode="json")),
            )

            # Step 5: Create declaration stubs before name-reference resolution.
            await create_declared_entity_stubs(
                incubator.get("new_entities") or [], conn
            )

            # Step 6: Resolve entity references, including same-turn declarations.
            ref_entities = ReferencedEntities(**incubator["reference_updates"])
            character_refs = await resolve_character_references(
                ref_entities.characters, conn
            )
            place_refs = await resolve_place_references(ref_entities.places, conn)
            faction_refs = await resolve_faction_references(ref_entities.factions, conn)
            if incubator.get("entity_updates"):
                state_updates = await resolve_state_update_ids(
                    conn,
                    StateUpdates(**incubator["entity_updates"]),
                )

            # Step 7: Insert chunk metadata
            await insert_chunk_metadata(
                conn,
                chunk_id=chunk_id,
                season=db_meta["season"],
                episode=db_meta["episode"],
                scene=db_meta["scene"],
                world_layer=world_layer,
                time_delta=db_meta["time_delta"],
                generation_model=incubator.get("generation_model"),
                scene_weather=metadata_update.scene_weather,
            )

            # Step 8: Insert junction table references
            await insert_place_references(conn, chunk_id, place_refs)
            await insert_character_references(conn, chunk_id, character_refs)
            await insert_faction_references(conn, chunk_id, faction_refs)

            # Step 9: Update entity states (if provided)
            if state_updates is not None:
                accepting_world_time = await _require_chunk_world_time(conn, chunk_id)
                # Two-time contract: Gaia validated activity at the parent anchor,
                # while a first application becomes true at the accepting child.
                # Thread the trigger-authored child clock into writes, never the
                # parent clock used to validate the model-visible state.
                await apply_state_updates(
                    conn,
                    state_updates,
                    source_chunk_id=chunk_id,
                    anchor_world_time=accepting_world_time,
                )

            # Step 9.5: Commit Orrery proposal inside the accepted-chunk transaction
            orrery_settings = _load_orrery_settings()
            staged_orrery_proposal, bleed_offer_resolution_ids = (
                split_staged_orrery_payload(incubator.get("orrery_proposal"))
            )
            orrery_result = await commit_orrery_tick_async(
                conn,
                staged_orrery_proposal,
                tick_chunk_id=chunk_id,
                slot=slot,
                world_layer=world_layer,
                adjudications=incubator.get("orrery_adjudications"),
                storyteller_state_updates=incubator.get("entity_updates"),
                prompt_settings=orrery_settings.get("prompt"),
                ecology_settings=orrery_settings.get("ecology"),
                project_settings=orrery_settings.get("projects"),
                mood_settings=orrery_settings.get("mood"),
                epistemics_settings=(
                    orrery_settings.get("epistemics")
                    if staged_orrery_proposal is None
                    else None
                ),
                contagion_settings=orrery_settings.get("contagion"),
                distortion_settings=orrery_settings.get("distortion"),
                drift_settings=orrery_settings.get("drift"),
                reveal_settings=orrery_settings.get("reveal"),
            )
            bleed_used_count = await record_bleed_uptake_async(
                conn,
                resolution_ids=bleed_offer_resolution_ids,
                accepted_chunk_id=chunk_id,
                accepted_text=storyteller_text,
            )
            if bleed_used_count:
                logger.info(
                    "Stamped %s Orrery Bleed uptake rows for chunk %s",
                    bleed_used_count,
                    chunk_id,
                )
            if (
                orrery_result.resolution_count
                or orrery_result.skipped_existing_count
                or orrery_result.adjudication_count
                or orrery_result.cleared_tag_count
                or orrery_result.scene_pressure_count
                or orrery_result.prompt_exposure_count
                or orrery_result.propagation_count
                or orrery_result.reveal_count
            ):
                logger.info(
                    "Committed Orrery tick for chunk %s: %s resolutions, %s events, "
                    "%s tag mutations, %s cleared tags, %s existing skipped, "
                    "%s adjudications (%s deferred, %s voided, %s replaced), "
                    "%s scene pressures, %s prompt exposures, %s propagations, "
                    "%s reveals",
                    chunk_id,
                    orrery_result.resolution_count,
                    orrery_result.event_count,
                    orrery_result.tag_mutation_count,
                    orrery_result.cleared_tag_count,
                    orrery_result.skipped_existing_count,
                    orrery_result.adjudication_count,
                    orrery_result.deferred_count,
                    orrery_result.voided_count,
                    orrery_result.replaced_count,
                    orrery_result.scene_pressure_count,
                    orrery_result.prompt_exposure_count,
                    orrery_result.propagation_count,
                    orrery_result.reveal_count,
                )

            # Step 9.55: interval state checkpoint (reconstruction bar 7c)
            checkpoint_interval = _orrery_checkpoint_interval(orrery_settings)
            if checkpoint_interval:
                playable_ordinal = await playable_narrative_ordinal_async(conn)
                if interval_checkpoint_due(
                    playable_ordinal=playable_ordinal,
                    interval=checkpoint_interval,
                ):
                    checkpoint_id = await capture_state_checkpoint_async(
                        conn, chunk_id=chunk_id, label="interval"
                    )
                    if checkpoint_id is not None:
                        logger.info(
                            "State checkpoint %s taken at playable chunk %s "
                            "(narrative_chunks.id=%s)",
                            checkpoint_id,
                            playable_ordinal,
                            chunk_id,
                        )

            # Step 10: Clear incubator
            await clear_incubator(conn, session_id)

        except Exception as e:
            logger.error("Failed to commit incubator session %s: %s", session_id, e)
            raise

    if summary_tasks:
        try:
            schedule_summary_generation(summary_tasks)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(
                "Failed to schedule summaries for session %s: %s", session_id, exc
            )

    # Post-commit presence-roster drift audit (issue #567): read-only
    # diagnostics over the committed chunk, outside the transaction.
    # raw_text is the committed prose (storyteller text + enacted choice);
    # the parent chunk id enables authored-exit accounting.
    from nexus.api.presence_audit import (
        audit_chunk_presence_async,
        presence_audit_enabled,
    )

    if presence_audit_enabled():
        await audit_chunk_presence_async(
            conn,
            chunk_id,
            raw_text,
            parent_chunk_id=incubator.get("parent_chunk_id"),
        )

    logger.info("Successfully committed chunk %s from session %s", chunk_id, session_id)
    return chunk_id


def _load_orrery_settings() -> Mapping[str, Any]:
    """Load the Orrery configuration once for one accepted-chunk operation."""

    from nexus.config import load_settings_as_dict

    return cast(Mapping[str, Any], load_settings_as_dict().get("orrery") or {})


def _orrery_checkpoint_interval(orrery_settings: Mapping[str, Any]) -> int:
    """[orrery.reconstruction] checkpoint cadence; 0 disables."""

    reconstruction = orrery_settings.get("reconstruction") or {}
    return int(reconstruction.get("checkpoint_interval_chunks", 0))
