"""
Synchronous Commit Handler for Narrative Chunks
================================================

Synchronous version of commit_handler.py using psycopg2 for compatibility
with the existing narrative API.
"""

import json
import logging
from datetime import datetime
from typing import Optional, Any, List
from psycopg2.extras import RealDictCursor

from nexus.agents.logon.apex_schema import (
    ChunkMetadataUpdate,
    ChronologyUpdate,
    ReferencedEntities,
    PlaceReference,
    CharacterReference,
    FactionReference,
    StateUpdates,
)
from nexus.agents.orrery.events import commit_orrery_tick_sync
from nexus.agents.orrery.geo import resolve_zone_for_point, story_active_zone
from nexus.agents.orrery.retrograde_maturation import (
    enqueue_declared_entity_maturations,
)
from nexus.agents.orrery.reconstruction import (
    capture_state_checkpoint_sync,
    interval_checkpoint_due,
    log_state_delta_sync,
    playable_narrative_ordinal_sync,
    set_commit_chunk_attribution_sync,
)
from nexus.agents.orrery.tag_writer import _row_value, apply_tag_bestowal
from nexus.api.db_converters import chronology_to_db_values
from nexus.api.summary_triggers import (
    SummaryTask,
    plan_summary_tasks,
    schedule_summary_generation,
)
from nexus.api.lore_adapter import compute_raw_text
from nexus.api.choice_handling import (
    normalize_choice_object,
    selected_text_from_choice_object,
)

logger = logging.getLogger("nexus.api.commit_handler_sync")


def insert_chunk_metadata_sync(
    cur: Any,
    *,
    chunk_id: int,
    season: int,
    episode: int,
    scene: int,
    world_layer: str,
    time_delta: Optional[Any],
    generation_date: datetime,
    slug: str,
    generation_model: Optional[str],
    scene_weather: Optional[str],
) -> None:
    """Insert chunk metadata, including a non-null scene weather override."""

    metadata_values = (
        chunk_id,
        season,
        episode,
        scene,
        world_layer,
        time_delta,
        generation_date,
        slug,
        generation_model,
    )
    if scene_weather is None:
        cur.execute(
            """
            INSERT INTO chunk_metadata (
                chunk_id, season, episode, scene, world_layer,
                time_delta, generation_date, slug, generation_model
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            metadata_values,
        )
    else:
        cur.execute(
            """
            INSERT INTO chunk_metadata (
                chunk_id, season, episode, scene, world_layer,
                time_delta, generation_date, slug, generation_model,
                scene_weather
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (*metadata_values, scene_weather),
        )


def _json_dumps_model(value: Any) -> Optional[str]:
    """Serialize dicts or Pydantic models for JSONB columns."""

    if value is None:
        return None
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", exclude_none=True)
    return json.dumps(value)


# ============================================================================
# Entity Resolution Functions (Synchronous)
# ============================================================================


def resolve_place_references_sync(
    place_references: List[PlaceReference], conn
) -> List[dict]:
    """Synchronous version of resolve_place_references"""
    resolved_refs = []

    for ref in place_references:
        place_id = None

        with conn.cursor() as cur:
            if ref.place_id:
                place_id = ref.place_id
            elif ref.place_name:
                # Look up existing place by name
                cur.execute("SELECT id FROM places WHERE name = %s", (ref.place_name,))
                result = cur.fetchone()
                if result:
                    place_id = result[0]
                elif ref.new_place:
                    place_id = create_new_place_sync(cur, ref.new_place)
                else:
                    logger.warning(
                        "Skipping unresolved place reference %r; provide place_id "
                        "or new_place to persist place_chunk_references",
                        ref.place_name,
                    )
                    continue
            elif ref.new_place:
                # Create new place and get ID
                place_id = create_new_place_sync(cur, ref.new_place)

        # Build junction table entry
        resolved_refs.append(
            {
                "place_id": place_id,
                "reference_type": ref.reference_type.value,
                "evidence": ref.evidence,
            }
        )

    return resolved_refs


def create_new_place_sync(cur, new_place):
    """Create a new place with the shared real-Earth GIS invariant."""

    place_type = new_place.type.value if new_place.type else None
    coordinates = None if place_type == "virtual" else new_place.coordinates
    if coordinates is None:
        zone_id = story_active_zone(cur)
    else:
        zone_id = resolve_zone_for_point(
            cur,
            longitude=coordinates.lon,
            latitude=coordinates.lat,
        )

    cur.execute(
        """
        INSERT INTO places (
            name, type, summary, history, current_status, secrets,
            extra_data, zone, coordinates
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s,
            CASE
                WHEN %s IS NULL THEN NULL
                ELSE ST_SetSRID(
                    ST_MakePoint(%s, %s, 0, 0), 4326
                )::geography
            END
        )
        RETURNING id, entity_id
    """,
        (
            new_place.name,
            place_type,
            new_place.summary,
            new_place.history,
            new_place.current_status,
            new_place.secrets,
            _json_dumps_model(new_place.extra_data),
            zone_id,
            coordinates.lon if coordinates else None,
            coordinates.lon if coordinates else None,
            coordinates.lat if coordinates else None,
        ),
    )

    place_id, entity_id = cur.fetchone()
    apply_tag_bestowal(
        cur,
        entity_id=entity_id,
        entity_kind="place",
        bestowal=getattr(new_place, "orrery_tags", None),
        source_kind="skald_inline",
    )
    return place_id


def resolve_character_references_sync(
    character_references: List[CharacterReference], conn
) -> List[dict]:
    """Synchronous version of resolve_character_references"""
    resolved_refs = []

    for ref in character_references:
        char_id = None

        with conn.cursor() as cur:
            if ref.character_id:
                char_id = ref.character_id
            elif ref.character_name:
                cur.execute(
                    "SELECT id FROM characters WHERE name = %s", (ref.character_name,)
                )
                result = cur.fetchone()
                if result:
                    char_id = result[0]
                elif ref.new_character:
                    char_id = create_new_character_sync(cur, ref.new_character)
                else:
                    logger.warning(
                        "Skipping unresolved character reference %r; provide "
                        "character_id or new_character to persist "
                        "chunk_character_references",
                        ref.character_name,
                    )
                    continue
            elif ref.new_character:
                char_id = create_new_character_sync(cur, ref.new_character)

        # Build junction table entry
        resolved_refs.append(
            {"character_id": char_id, "reference": ref.reference_type.value}
        )

    return resolved_refs


def create_new_character_sync(cur, new_char):
    """Create a new character synchronously"""
    # Validate location exists
    if new_char.current_location:
        cur.execute("SELECT id FROM places WHERE id = %s", (new_char.current_location,))
        if not cur.fetchone():
            raise ValueError(
                f"Place ID {new_char.current_location} not found for character location"
            )

    # Insert character
    cur.execute(
        """
        INSERT INTO characters (
            name, summary, appearance, background, personality,
            emotional_state, current_activity, current_location, extra_data
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, entity_id
    """,
        (
            new_char.name,
            new_char.summary,
            new_char.appearance,
            new_char.background,
            new_char.personality,
            new_char.emotional_state,
            new_char.current_activity,
            new_char.current_location,
            _json_dumps_model(new_char.extra_data),
        ),
    )

    char_id, entity_id = cur.fetchone()
    apply_tag_bestowal(
        cur,
        entity_id=entity_id,
        entity_kind="character",
        bestowal=getattr(new_char, "orrery_tags", None),
        source_kind="skald_inline",
    )
    return char_id


def resolve_faction_references_sync(
    faction_references: List[FactionReference], conn
) -> List[dict]:
    """Synchronous version of resolve_faction_references"""
    resolved_refs = []

    for ref in faction_references:
        faction_id = None

        with conn.cursor() as cur:
            if ref.faction_id:
                faction_id = ref.faction_id
            elif ref.faction_name:
                cur.execute(
                    "SELECT id FROM factions WHERE name = %s", (ref.faction_name,)
                )
                result = cur.fetchone()
                if result:
                    faction_id = result[0]
                elif ref.new_faction:
                    faction_id = create_new_faction_sync(cur, ref.new_faction)
                else:
                    logger.warning(
                        "Skipping unresolved faction reference %r; provide "
                        "faction_id or new_faction to persist "
                        "chunk_faction_references",
                        ref.faction_name,
                    )
                    continue
            elif ref.new_faction:
                faction_id = create_new_faction_sync(cur, ref.new_faction)

        # Build junction table entry
        resolved_refs.append({"faction_id": faction_id})

    return resolved_refs


def create_new_faction_sync(cur, new_faction):
    """Create a new faction synchronously"""
    # Validate primary_location exists
    if new_faction.primary_location:
        cur.execute(
            "SELECT id FROM places WHERE id = %s", (new_faction.primary_location,)
        )
        if not cur.fetchone():
            raise ValueError(
                f"Place ID {new_faction.primary_location} not found for "
                "faction location"
            )

    cur.execute("LOCK TABLE factions IN SHARE ROW EXCLUSIVE MODE")
    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM factions")
    faction_id = cur.fetchone()[0]

    # Insert faction
    cur.execute(
        """
        INSERT INTO factions (
            id, name, summary, primary_location, extra_data
        ) VALUES (%s, %s, %s, %s, %s)
        RETURNING id, entity_id
    """,
        (
            faction_id,
            new_faction.name,
            new_faction.summary,
            new_faction.primary_location,
            _json_dumps_model(new_faction.extra_data),
        ),
    )

    inserted_faction_id, entity_id = cur.fetchone()
    apply_tag_bestowal(
        cur,
        entity_id=entity_id,
        entity_kind="faction",
        bestowal=getattr(new_faction, "orrery_tags", None),
        source_kind="skald_inline",
    )
    return inserted_faction_id


# ============================================================================
# Main Synchronous Commit Function
# ============================================================================


def commit_incubator_to_database_sync(
    conn, session_id: str, slot: Optional[int] = None
) -> int:
    """
    Synchronous version of commit flow from incubator to production tables.

    Uses psycopg2 connection with transaction management.

    Returns:
        New chunk ID
    """
    summary_tasks: List[SummaryTask] = []
    chunk_id: Optional[int] = None

    try:
        # Start transaction
        with conn:  # This creates a transaction context
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Step 1: Get incubator data
                cur.execute(
                    """
                    SELECT chunk_id, parent_chunk_id, user_text, storyteller_text,
                           choice_object, choice_text, orrery_proposal,
                           COALESCE(orrery_adjudications, '[]'::jsonb)
                               AS orrery_adjudications,
                           COALESCE(new_entities, '[]'::jsonb) AS new_entities,
                           metadata_updates, entity_updates, reference_updates,
                           llm_response_id, generation_model, status
                    FROM incubator
                    WHERE session_id = %s
                """,
                    (session_id,),
                )
                incubator = cur.fetchone()

                if not incubator:
                    raise ValueError(
                        f"No incubator data found for session {session_id}"
                    )

                logger.info("Processing incubator session %s", session_id)

            # Step 2: Get parent context
            # Bootstrap case: parent_chunk_id=0 has no metadata, use defaults
            is_bootstrap = incubator["parent_chunk_id"] == 0
            if is_bootstrap:
                parent_meta = {
                    "season": 1,
                    "episode": 1,
                    "scene": 0,  # Will be incremented to 1
                    "world_layer": "primary",
                    "time_delta": 0,
                }
                logger.info("Bootstrap chunk - using default metadata (S1E1 scene 1)")
            else:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT season, episode, scene, world_layer, time_delta
                        FROM chunk_metadata
                        WHERE chunk_id = %s
                    """,
                        (incubator["parent_chunk_id"],),
                    )
                    parent_meta = cur.fetchone()

                    if not parent_meta:
                        raise ValueError(
                            "No metadata found for parent chunk "
                            f"{incubator['parent_chunk_id']}"
                        )

                    logger.info(
                        "Parent chunk %s: S%sE%s scene %s",
                        incubator["parent_chunk_id"],
                        parent_meta["season"],
                        parent_meta["episode"],
                        parent_meta["scene"],
                    )

            # Step 3: Resolve entity references
            # Parse referenced entities from JSONB
            ref_entities = ReferencedEntities(**incubator["reference_updates"])

            # Create new entities and resolve all to IDs
            character_refs = resolve_character_references_sync(
                ref_entities.characters, conn
            )
            place_refs = resolve_place_references_sync(ref_entities.places, conn)
            faction_refs = resolve_faction_references_sync(ref_entities.factions, conn)

            # Step 4: Convert metadata
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

            # Step 5: Insert narrative chunk
            # Compute finalized text based on any choice selection made in the incubator
            choice_object = incubator.get("choice_object")
            storyteller_text = incubator.get("storyteller_text") or ""
            choice_text: Optional[str] = incubator.get("choice_text")

            if choice_object:
                if not choice_text:
                    choice_text = selected_text_from_choice_object(choice_object)
                choice_object = normalize_choice_object(choice_object)

            raw_text = compute_raw_text(storyteller_text, choice_object, choice_text)

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO narrative_chunks (
                        raw_text, storyteller_text, choice_object, choice_text
                    )
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """,
                    (
                        raw_text,
                        storyteller_text,
                        json.dumps(choice_object) if choice_object else None,
                        choice_text,
                    ),
                )
                chunk_id = cur.fetchone()[0]
                if chunk_id is None:
                    raise ValueError("Failed to obtain chunk_id after insert")
                logger.info("Created narrative chunk %s", chunk_id)
                # Attribute trigger-versioned writes in this transaction
                # (relationship_versions) to the committing chunk.
                set_commit_chunk_attribution_sync(cur, chunk_id)

            # Step 6: Insert chunk metadata
            with conn.cursor() as cur:
                # Generate slug (e.g., "S05E06_001")
                slug = (
                    f"S{db_meta['season']:02d}E{db_meta['episode']:02d}_"
                    f"{db_meta['scene']:03d}"
                )

                insert_chunk_metadata_sync(
                    cur,
                    chunk_id=chunk_id,
                    season=db_meta["season"],
                    episode=db_meta["episode"],
                    scene=db_meta["scene"],
                    world_layer=world_layer,
                    time_delta=db_meta["time_delta"],
                    generation_date=datetime.utcnow(),
                    slug=slug,
                    generation_model=incubator.get("generation_model"),
                    scene_weather=metadata_update.scene_weather,
                )
                logger.info("Created metadata for chunk %s: %s", chunk_id, slug)

            # Step 7: Insert junction table references
            # Insert place references
            if place_refs:
                with conn.cursor() as cur:
                    for ref in place_refs:
                        cur.execute(
                            """
                            INSERT INTO place_chunk_references (
                                place_id, chunk_id, reference_type, evidence
                            )
                            VALUES (%s, %s, %s, %s)
                        """,
                            (
                                ref["place_id"],
                                chunk_id,
                                ref["reference_type"],
                                ref.get("evidence"),
                            ),
                        )
                    logger.info(
                        "Inserted %s place references for chunk %s",
                        len(place_refs),
                        chunk_id,
                    )

            # Insert character references
            if character_refs:
                with conn.cursor() as cur:
                    for ref in character_refs:
                        cur.execute(
                            """
                            INSERT INTO chunk_character_references (
                                chunk_id, character_id, reference
                            )
                            VALUES (%s, %s, %s)
                            ON CONFLICT (chunk_id, character_id) DO UPDATE
                            SET reference = 'present'
                            WHERE 'present' IN (
                                chunk_character_references.reference,
                                EXCLUDED.reference
                            )
                        """,
                            (chunk_id, ref["character_id"], ref["reference"]),
                        )
                    logger.info(
                        "Inserted %s character references for chunk %s",
                        len(character_refs),
                        chunk_id,
                    )

            # Insert faction references
            if faction_refs:
                with conn.cursor() as cur:
                    for ref in faction_refs:
                        cur.execute(
                            """
                            INSERT INTO chunk_faction_references (chunk_id, faction_id)
                            VALUES (%s, %s)
                            ON CONFLICT (chunk_id, faction_id) DO NOTHING
                        """,
                            (chunk_id, ref["faction_id"]),
                        )
                    logger.info(
                        "Inserted %s faction references for chunk %s",
                        len(faction_refs),
                        chunk_id,
                    )

            # Step 8: Update entity states (if provided)
            if incubator.get("entity_updates"):
                state_updates = StateUpdates(**incubator["entity_updates"])
                apply_state_updates_sync(conn, state_updates, source_chunk_id=chunk_id)

            # Step 8.5: Commit Orrery proposal inside the accepted-chunk transaction
            orrery_result = commit_orrery_tick_sync(
                conn,
                incubator.get("orrery_proposal"),
                tick_chunk_id=chunk_id,
                slot=slot,
                world_layer=world_layer,
                adjudications=incubator.get("orrery_adjudications"),
                storyteller_state_updates=incubator.get("entity_updates"),
                prompt_settings=_orrery_prompt_settings(),
                ecology_settings=_orrery_ecology_settings(),
                project_settings=_orrery_project_settings(),
                epistemics_settings=(
                    _orrery_epistemics_settings()
                    if incubator.get("orrery_proposal") is None
                    else None
                ),
                contagion_settings=_orrery_contagion_settings(),
                distortion_settings=_orrery_distortion_settings(),
                drift_settings=_orrery_drift_settings(),
                reveal_settings=_orrery_reveal_settings(),
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

            # Step 8.55: interval state checkpoint (reconstruction bar 7c).
            # Fresh cursor: the earlier `with conn.cursor()` blocks have
            # closed theirs by this point (review finding on #428).
            checkpoint_interval = _orrery_checkpoint_interval()
            if checkpoint_interval:
                with conn.cursor() as checkpoint_cur:
                    playable_ordinal = playable_narrative_ordinal_sync(checkpoint_cur)
                    if interval_checkpoint_due(
                        playable_ordinal=playable_ordinal,
                        interval=checkpoint_interval,
                    ):
                        checkpoint_id = capture_state_checkpoint_sync(
                            checkpoint_cur, chunk_id=chunk_id, label="interval"
                        )
                        if checkpoint_id is not None:
                            logger.info(
                                "State checkpoint %s taken at playable chunk "
                                "%s (narrative_chunks.id=%s)",
                                checkpoint_id,
                                playable_ordinal,
                                chunk_id,
                            )

            # Step 8.6: Process Skald new-entity declarations inside the
            # commit transaction (Retrograde stub maturation outbox, spec
            # decisions 9/10/12): validate hints, create stubs, and enqueue
            # durable maturation jobs for declared entities that appear in
            # the committed chunk.
            maturation_result = enqueue_declared_entity_maturations(
                conn,
                declarations=incubator.get("new_entities") or [],
                chunk_id=chunk_id,
                raw_text=raw_text,
                slot=slot,
            )
            if maturation_result.declared:
                logger.info(
                    "Processed %s new-entity declarations for chunk %s: "
                    "%s stubs created, %s jobs enqueued, %s already present, "
                    "%s without engagement signal, %s skipped (disabled)",
                    maturation_result.declared,
                    chunk_id,
                    maturation_result.stubs_created,
                    maturation_result.jobs_enqueued,
                    maturation_result.jobs_already_present,
                    maturation_result.signal_absent,
                    maturation_result.skipped_disabled,
                )

            # Step 9: Clear incubator
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM incubator WHERE session_id = %s", (session_id,)
                )
                logger.info("Cleared incubator for session %s", session_id)

    except Exception as e:
        logger.error("Failed to commit incubator session %s: %s", session_id, e)
        conn.rollback()  # Explicit rollback on error
        raise

    if summary_tasks:
        try:
            schedule_summary_generation(summary_tasks, slot=slot)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(
                "Failed to schedule summaries for session %s: %s", session_id, exc
            )

    logger.info("Successfully committed chunk %s from session %s", chunk_id, session_id)
    return chunk_id


def apply_state_updates_sync(
    conn, state_updates: StateUpdates, source_chunk_id: Optional[int] = None
):
    """Apply entity state updates synchronously"""
    with conn.cursor() as cur:
        # Update character states
        for char_update in state_updates.characters:
            if char_update.character_id:
                updates = []
                params = []
                written_fields = []

                if char_update.emotional_state:
                    updates.append("emotional_state = %s")
                    params.append(char_update.emotional_state)
                    written_fields.append(
                        ("characters.emotional_state", char_update.emotional_state)
                    )

                if char_update.current_activity:
                    updates.append("current_activity = %s")
                    params.append(char_update.current_activity)
                    written_fields.append(
                        ("characters.current_activity", char_update.current_activity)
                    )

                if char_update.current_location:
                    updates.append("current_location = %s")
                    params.append(char_update.current_location)
                    written_fields.append(
                        ("characters.current_location", char_update.current_location)
                    )

                if updates:
                    params.append(char_update.character_id)
                    cur.execute(
                        f"UPDATE characters SET {', '.join(updates)} WHERE id = %s",
                        params,
                    )
                    logger.info(f"Updated character {char_update.character_id}")
                    if source_chunk_id is not None:
                        cur.execute(
                            "SELECT entity_id FROM characters WHERE id = %s",
                            (char_update.character_id,),
                        )
                        row = cur.fetchone()
                        char_entity_id = (
                            _row_value(row, "entity_id", 0) if row else None
                        )
                        for field, value in written_fields:
                            log_state_delta_sync(
                                cur,
                                source_chunk_id=source_chunk_id,
                                writer="skald_state_update",
                                entity_id=char_entity_id,
                                field=field,
                                new_value=value,
                            )

                bestowal = getattr(char_update, "orrery_tags", None)
                if char_update.character_id and bestowal is not None:
                    _apply_state_tags(
                        cur,
                        kind="character",
                        subtype_table="characters",
                        subtype_id=char_update.character_id,
                        bestowal=bestowal,
                        source_chunk_id=source_chunk_id,
                    )

        # Update place states. The schema field is current_conditions
        # (LocationStateUpdate); it persists to the places.current_status
        # column (M9 gate finding: the old attribute read crashed commits).
        for place_update in state_updates.locations:
            if place_update.place_id and place_update.current_conditions:
                cur.execute(
                    "UPDATE places SET current_status = %s WHERE id = %s",
                    (place_update.current_conditions, place_update.place_id),
                )
                logger.info(f"Updated place {place_update.place_id}")
                if source_chunk_id is not None:
                    cur.execute(
                        "SELECT entity_id FROM places WHERE id = %s",
                        (place_update.place_id,),
                    )
                    row = cur.fetchone()
                    log_state_delta_sync(
                        cur,
                        source_chunk_id=source_chunk_id,
                        writer="skald_state_update",
                        entity_id=_row_value(row, "entity_id", 0) if row else None,
                        field="places.current_status",
                        new_value=place_update.current_conditions,
                    )

            bestowal = getattr(place_update, "orrery_tags", None)
            if place_update.place_id and bestowal is not None:
                _apply_state_tags(
                    cur,
                    kind="place",
                    subtype_table="places",
                    subtype_id=place_update.place_id,
                    bestowal=bestowal,
                    source_chunk_id=source_chunk_id,
                )

        # Update faction states
        for faction_update in state_updates.factions:
            bestowal = getattr(faction_update, "orrery_tags", None)
            if faction_update.faction_id and bestowal is not None:
                _apply_state_tags(
                    cur,
                    kind="faction",
                    subtype_table="factions",
                    subtype_id=faction_update.faction_id,
                    bestowal=bestowal,
                    source_chunk_id=source_chunk_id,
                )


def _apply_state_tags(
    cur,
    *,
    kind,
    subtype_table,
    subtype_id,
    bestowal,
    source_chunk_id: Optional[int] = None,
) -> None:
    """Look up the entity_id for a subtype row and apply Skald-bestowed tags."""
    cur.execute(
        f"SELECT entity_id FROM {subtype_table} WHERE id = %s",
        (subtype_id,),
    )
    row = cur.fetchone()
    if row is None:
        logger.warning(f"Skipping tag bestowal: no {kind} row for id={subtype_id}")
        return
    entity_id = _row_value(row, "entity_id", 0)
    counters = apply_tag_bestowal(
        cur,
        entity_id=entity_id,
        entity_kind=kind,
        bestowal=bestowal,
        source_kind="skald_inline",
        source_chunk_id=source_chunk_id,
    )
    if any(counters.values()):
        logger.info(f"Tag bestowal {kind}/{subtype_id}: {counters}")


def _orrery_ecology_settings() -> Any:
    """[orrery.ecology] signal-detection policy for branch signal emissions."""

    from nexus.config import load_settings_as_dict

    return (load_settings_as_dict().get("orrery") or {}).get("ecology")


def _orrery_prompt_settings() -> Any:
    """[orrery.prompt] render caps, so the prompt-exposure log matches what
    logon_utility actually rendered for this tick."""

    from nexus.config import load_settings_as_dict

    return (load_settings_as_dict().get("orrery") or {}).get("prompt")


def _orrery_project_settings() -> Any:
    """[orrery.projects] cadence and abandonment policy."""

    from nexus.config import load_settings_as_dict

    return (load_settings_as_dict().get("orrery") or {}).get("projects")


def _orrery_contagion_settings() -> Any:
    """[orrery.contagion] frontier and communication policy."""

    from nexus.config import load_settings_as_dict

    return (load_settings_as_dict().get("orrery") or {}).get("contagion")


def _orrery_distortion_settings() -> Any:
    """[orrery.distortion] authored hop-depth account selection policy."""

    from nexus.config import load_settings_as_dict

    return (load_settings_as_dict().get("orrery") or {}).get("distortion")


def _orrery_epistemics_settings() -> Any:
    """[orrery.epistemics] claim-minting and awareness policy."""

    from nexus.config import load_settings_as_dict

    return (load_settings_as_dict().get("orrery") or {}).get("epistemics")


def _orrery_drift_settings() -> Any:
    """[orrery.drift] continuous relationship-valence policy."""

    from nexus.config import load_settings_as_dict

    return (load_settings_as_dict().get("orrery") or {}).get("drift")


def _orrery_reveal_settings() -> Any:
    """[orrery.reveal] template-authored backstory reveal policy."""

    from nexus.config import load_settings_as_dict

    return (load_settings_as_dict().get("orrery") or {}).get("reveal")


def _orrery_checkpoint_interval() -> int:
    """[orrery.reconstruction] checkpoint cadence; 0 disables."""

    from nexus.config import load_settings_as_dict

    orrery = load_settings_as_dict().get("orrery") or {}
    reconstruction = orrery.get("reconstruction") or {}
    return int(reconstruction.get("checkpoint_interval_chunks", 0))
