"""
Synchronous Commit Handler for Narrative Chunks
================================================

Synchronous version of commit_handler.py using psycopg2 for compatibility
with the existing narrative API.
"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
import psycopg2
from psycopg2.extras import RealDictCursor

from nexus.agents.logon.apex_schema import (
    ChronologyUpdate,
    ReferencedEntities,
    PlaceReference,
    CharacterReference,
    FactionReference,
    StateUpdates,
)
from nexus.agents.orrery.events import commit_orrery_tick_sync
from nexus.agents.orrery.retrograde_maturation import (
    enqueue_declared_entity_maturations,
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
    """Create a new place synchronously"""
    # Insert place
    cur.execute(
        """
        INSERT INTO places (
            name, type, summary, history, current_status, secrets,
            extra_data
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, entity_id
    """,
        (
            new_place.name,
            new_place.type.value if new_place.type else None,
            new_place.summary,
            new_place.history,
            new_place.current_status,
            new_place.secrets,
            _json_dumps_model(new_place.extra_data),
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
                f"Place ID {new_faction.primary_location} not found for faction location"
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
                           COALESCE(authorial_directives, '[]'::jsonb) AS authorial_directives,
                           COALESCE(new_entities, '[]'::jsonb) AS new_entities,
                           metadata_updates, entity_updates, reference_updates,
                           llm_response_id, status
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
                            f"No metadata found for parent chunk {incubator['parent_chunk_id']}"
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
                        raw_text, storyteller_text, choice_object, choice_text,
                        authorial_directives
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                """,
                    (
                        raw_text,
                        storyteller_text,
                        json.dumps(choice_object) if choice_object else None,
                        choice_text,
                        json.dumps(incubator.get("authorial_directives") or []),
                    ),
                )
                chunk_id = cur.fetchone()[0]
                if chunk_id is None:
                    raise ValueError("Failed to obtain chunk_id after insert")
                logger.info("Created narrative chunk %s", chunk_id)

            # Step 6: Insert chunk metadata
            with conn.cursor() as cur:
                # Generate slug (e.g., "S05E06_001")
                slug = f"S{db_meta['season']:02d}E{db_meta['episode']:02d}_{db_meta['scene']:03d}"

                cur.execute(
                    """
                    INSERT INTO chunk_metadata (
                        chunk_id, season, episode, scene, world_layer,
                        time_delta, generation_date, slug
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        chunk_id,
                        db_meta["season"],
                        db_meta["episode"],
                        db_meta["scene"],
                        world_layer,
                        db_meta["time_delta"],
                        datetime.utcnow(),
                        slug,
                    ),
                )
                logger.info("Created metadata for chunk %s: %s", chunk_id, slug)

            # Step 7: Insert junction table references
            # Insert place references
            if place_refs:
                with conn.cursor() as cur:
                    for ref in place_refs:
                        cur.execute(
                            """
                            INSERT INTO place_chunk_references (place_id, chunk_id, reference_type, evidence)
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
                        f"Inserted {len(place_refs)} place references for chunk {chunk_id}"
                    )

            # Insert character references
            if character_refs:
                with conn.cursor() as cur:
                    for ref in character_refs:
                        cur.execute(
                            """
                            INSERT INTO chunk_character_references (chunk_id, character_id, reference)
                            VALUES (%s, %s, %s)
                        """,
                            (chunk_id, ref["character_id"], ref["reference"]),
                        )
                    logger.info(
                        f"Inserted {len(character_refs)} character references for chunk {chunk_id}"
                    )

            # Insert faction references
            if faction_refs:
                with conn.cursor() as cur:
                    for ref in faction_refs:
                        cur.execute(
                            """
                            INSERT INTO chunk_faction_references (chunk_id, faction_id)
                            VALUES (%s, %s)
                        """,
                            (chunk_id, ref["faction_id"]),
                        )
                    logger.info(
                        f"Inserted {len(faction_refs)} faction references for chunk {chunk_id}"
                    )

            # Step 8: Update entity states (if provided)
            if incubator.get("entity_updates"):
                state_updates = StateUpdates(**incubator["entity_updates"])
                apply_state_updates_sync(conn, state_updates)

            # Step 8.5: Commit Orrery proposal inside the accepted-chunk transaction
            orrery_result = commit_orrery_tick_sync(
                conn,
                incubator.get("orrery_proposal"),
                tick_chunk_id=chunk_id,
                slot=slot,
                world_layer=world_layer,
                adjudications=incubator.get("orrery_adjudications"),
                storyteller_state_updates=incubator.get("entity_updates"),
            )
            if (
                orrery_result.resolution_count
                or orrery_result.skipped_existing_count
                or orrery_result.adjudication_count
                or orrery_result.cleared_tag_count
            ):
                logger.info(
                    "Committed Orrery tick for chunk %s: %s resolutions, %s events, "
                    "%s tag mutations, %s cleared tags, %s existing skipped, "
                    "%s adjudications (%s deferred, %s voided, %s replaced)",
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


def apply_state_updates_sync(conn, state_updates: StateUpdates):
    """Apply entity state updates synchronously"""
    with conn.cursor() as cur:
        # Update character states
        for char_update in state_updates.characters:
            if char_update.character_id:
                updates = []
                params = []

                if char_update.emotional_state:
                    updates.append("emotional_state = %s")
                    params.append(char_update.emotional_state)

                if char_update.current_activity:
                    updates.append("current_activity = %s")
                    params.append(char_update.current_activity)

                if char_update.current_location:
                    updates.append("current_location = %s")
                    params.append(char_update.current_location)

                if updates:
                    params.append(char_update.character_id)
                    cur.execute(
                        f"UPDATE characters SET {', '.join(updates)} WHERE id = %s",
                        params,
                    )
                    logger.info(f"Updated character {char_update.character_id}")

                bestowal = getattr(char_update, "orrery_tags", None)
                if char_update.character_id and bestowal is not None:
                    _apply_state_tags(
                        cur,
                        kind="character",
                        subtype_table="characters",
                        subtype_id=char_update.character_id,
                        bestowal=bestowal,
                    )

        # Update place states
        for place_update in state_updates.locations:
            if place_update.place_id and place_update.current_status:
                cur.execute(
                    "UPDATE places SET current_status = %s WHERE id = %s",
                    (place_update.current_status, place_update.place_id),
                )
                logger.info(f"Updated place {place_update.place_id}")

            bestowal = getattr(place_update, "orrery_tags", None)
            if place_update.place_id and bestowal is not None:
                _apply_state_tags(
                    cur,
                    kind="place",
                    subtype_table="places",
                    subtype_id=place_update.place_id,
                    bestowal=bestowal,
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
                )


def _apply_state_tags(cur, *, kind, subtype_table, subtype_id, bestowal) -> None:
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
    )
    if any(counters.values()):
        logger.info(f"Tag bestowal {kind}/{subtype_id}: {counters}")
