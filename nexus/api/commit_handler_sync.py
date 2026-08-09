"""
Synchronous Commit Handler for Narrative Chunks
================================================

Synchronous version of commit_handler.py using psycopg2 for compatibility
with the existing narrative API.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, cast
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
from nexus.agents.orrery.bleed import record_bleed_uptake_sync
from nexus.agents.orrery.events import commit_orrery_tick_sync
from nexus.agents.orrery.experiences import (
    enqueue_scene_experience_job_sync,
    seed_character_experiences_sync,
)
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
from nexus.api.choice_handling import (
    normalize_choice_object,
    selected_text_from_choice_object,
)
from nexus.api.db_converters import chronology_to_db_values
from nexus.api.summary_triggers import (
    SummaryTask,
    plan_summary_tasks,
    schedule_summary_generation,
)
from nexus.api.lore_adapter import compute_raw_text, split_staged_orrery_payload
from nexus.memory.correspondence import (
    correspondence_settings,
    insert_digest_version,
    load_compaction_system_prompt,
    persist_staged_correspondence,
    plan_correspondence_compaction,
)
from nexus.memory.context_state import (
    bind_pass2_baseline,
    validate_staged_pass2_baseline,
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
                cur.execute("SELECT id FROM places WHERE name = %s", (ref.place_name,))
                result = cur.fetchone()
                if result:
                    place_id = result[0]
                else:
                    logger.warning(
                        "Skipping unresolved place reference %r; provide a canonical "
                        "place_id or place_name to persist place_chunk_references",
                        ref.place_name,
                    )
                    continue

        # Build junction table entry
        resolved_refs.append(
            {
                "place_id": place_id,
                "reference_type": ref.reference_type.value,
                "evidence": ref.evidence,
            }
        )

    return resolved_refs


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
                else:
                    logger.warning(
                        "Skipping unresolved character reference %r; provide a "
                        "canonical character_id or character_name to persist "
                        "chunk_character_references",
                        ref.character_name,
                    )
                    continue

        # Build junction table entry
        resolved_refs.append(
            {"character_id": char_id, "reference": ref.reference_type.value}
        )

    return resolved_refs


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
                else:
                    logger.warning(
                        "Skipping unresolved faction reference %r; provide a "
                        "canonical faction_id or faction_name to persist "
                        "chunk_faction_references",
                        ref.faction_name,
                    )
                    continue

        # Build junction table entry
        resolved_refs.append({"faction_id": faction_id})

    return resolved_refs


def _require_state_update_id_sync(
    conn,
    *,
    kind: str,
    table: str,
    current_id: Optional[int],
    name: Optional[str],
) -> int:
    """Resolve one synchronous state-update identity or fail the transaction."""

    if current_id is not None:
        return current_id
    if not name:
        raise ValueError(f"{kind} state update requires an id or name")
    with conn.cursor() as cur:
        cur.execute(f"SELECT id FROM {table} WHERE name = %s", (name,))
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"Unresolved {kind} state update name {name!r}")
    return _row_value(row, "id", 0)


def resolve_state_update_ids_sync(
    conn,
    state_updates: StateUpdates,
) -> StateUpdates:
    """Resolve all name-addressed state updates to canonical database IDs."""

    resolved = state_updates.model_copy(deep=True)
    for character_update in resolved.characters:
        character_update.character_id = _require_state_update_id_sync(
            conn,
            kind="character",
            table="characters",
            current_id=character_update.character_id,
            name=character_update.character_name,
        )
    for location_update in resolved.locations:
        location_update.place_id = _require_state_update_id_sync(
            conn,
            kind="place",
            table="places",
            current_id=location_update.place_id,
            name=location_update.place_name,
        )
    for faction_update in resolved.factions:
        faction_update.faction_id = _require_state_update_id_sync(
            conn,
            kind="faction",
            table="factions",
            current_id=faction_update.faction_id,
            name=faction_update.faction_name,
        )
    for relationship_update in resolved.relationships:
        relationship_update.character1_id = _require_state_update_id_sync(
            conn,
            kind="relationship character1",
            table="characters",
            current_id=relationship_update.character1_id,
            name=relationship_update.character1_name,
        )
        relationship_update.character2_id = _require_state_update_id_sync(
            conn,
            kind="relationship character2",
            table="characters",
            current_id=relationship_update.character2_id,
            name=relationship_update.character2_name,
        )
    return resolved


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
    state_updates: Optional[StateUpdates] = None

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
                           correspondence_writer_letter,
                           correspondence_gaia_letter,
                           lore_pass_baseline,
                           metadata_updates, entity_updates, reference_updates,
                           llm_response_id, generation_model, status
                    FROM incubator
                    WHERE session_id = %s
                    FOR UPDATE
                """,
                    (session_id,),
                )
                incubator = cur.fetchone()

                if not incubator:
                    raise ValueError(
                        f"No incubator data found for session {session_id}"
                    )
                validate_staged_pass2_baseline(incubator["lore_pass_baseline"])

                logger.info("Processing incubator session %s", session_id)

            # Step 2: Get parent context
            # Bootstrap case: parent_chunk_id=0 has no metadata, use defaults
            is_bootstrap = incubator["parent_chunk_id"] == 0
            parent_meta: Dict[str, Any]
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
                bound_baseline = bind_pass2_baseline(
                    incubator["lore_pass_baseline"], chunk_id
                )
                cur.execute(
                    """
                    INSERT INTO lore_pass_baselines (
                        chunk_id, schema_version, payload
                    ) VALUES (%s, %s, %s::jsonb)
                    """,
                    (
                        chunk_id,
                        bound_baseline.schema_version,
                        json.dumps(bound_baseline.model_dump(mode="json")),
                    ),
                )
                # Attribute trigger-versioned writes in this transaction
                # (relationship_versions) to the committing chunk.
                set_commit_chunk_attribution_sync(cur, chunk_id)
                persist_staged_correspondence(
                    cur,
                    chunk_id=chunk_id,
                    writer_letter=incubator.get("correspondence_writer_letter"),
                    gaia_letter=incubator.get("correspondence_gaia_letter"),
                )

            # Step 5: Process declarations before name-reference resolution.
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

            # Step 6: Resolve references, including same-turn declarations.
            ref_entities = ReferencedEntities(**incubator["reference_updates"])
            character_refs = resolve_character_references_sync(
                ref_entities.characters, conn
            )
            place_refs = resolve_place_references_sync(ref_entities.places, conn)
            faction_refs = resolve_faction_references_sync(ref_entities.factions, conn)
            if incubator.get("entity_updates"):
                state_updates = resolve_state_update_ids_sync(
                    conn,
                    StateUpdates(**incubator["entity_updates"]),
                )

            # Step 7: Insert chunk metadata
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

            # Step 8: Insert junction table references
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

            # Step 9: Update entity states (if provided)
            if state_updates is not None:
                apply_state_updates_sync(conn, state_updates, source_chunk_id=chunk_id)

            # Step 9.5: Commit Orrery proposal inside the accepted-chunk transaction
            orrery_settings = _load_orrery_settings()
            staged_orrery_proposal, bleed_offer_resolution_ids = (
                split_staged_orrery_payload(incubator.get("orrery_proposal"))
            )
            orrery_result = commit_orrery_tick_sync(
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
            bleed_used_count = record_bleed_uptake_sync(
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

            # Step 9.52: deterministic actor-owned experience formation. The
            # provider is deliberately absent from this accepted transaction;
            # a scene reset only enqueues the prior scene's immutable seed set.
            experience_count = seed_character_experiences_sync(
                conn,
                anchor_chunk_id=chunk_id,
                settings=orrery_settings,
            )
            if experience_count:
                logger.info(
                    "Inserted %s character experience seeds for chunk %s",
                    experience_count,
                    chunk_id,
                )
            if metadata_update.scene_boundary and not is_bootstrap:
                enqueued = enqueue_scene_experience_job_sync(
                    conn,
                    boundary_chunk_id=chunk_id,
                    scene_end_chunk_id=int(incubator["parent_chunk_id"]),
                    world_layer=world_layer,
                    slot=slot,
                    settings=orrery_settings,
                )
                if enqueued:
                    logger.info(
                        "Enqueued character experience scene batch at chunk %s",
                        chunk_id,
                    )

            # Step 9.55: interval state checkpoint (reconstruction bar 7c).
            # Fresh cursor: the earlier `with conn.cursor()` blocks have
            # closed theirs by this point (review finding on #428).
            checkpoint_interval = _orrery_checkpoint_interval(orrery_settings)
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

            # Step 10: Clear incubator
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM incubator WHERE session_id = %s", (session_id,)
                )
                if cur.rowcount != 1:
                    raise RuntimeError(
                        "Incubator ownership changed while committing session "
                        f"{session_id}."
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

    if incubator.get("correspondence_writer_letter") is not None:
        _compact_accepted_correspondence_best_effort(
            conn,
            accepting_chunk_id=chunk_id,
        )

    # Post-commit presence-roster drift audit (issue #567): read-only
    # diagnostics over the committed chunk, outside the transaction.
    # raw_text is the committed prose (storyteller text + enacted choice);
    # the parent chunk id enables authored-exit accounting.
    from nexus.api.presence_audit import audit_chunk_presence, presence_audit_enabled

    if presence_audit_enabled():
        audit_chunk_presence(
            conn,
            chunk_id,
            raw_text,
            parent_chunk_id=incubator.get("parent_chunk_id"),
        )

    logger.info("Successfully committed chunk %s from session %s", chunk_id, session_id)
    return chunk_id


def _compact_accepted_correspondence_best_effort(
    conn: Any,
    *,
    accepting_chunk_id: int,
) -> bool:
    """Compact after acceptance without misreporting the durable commit.

    Compaction is derived from the append-only accepted correspondence journal.
    If the provider or persistence step fails, leaving the digest absent is a
    deterministic retry marker: the next accepted correspondence turn plans
    compaction from the same uncompacted exchanges. The accepted narrative and
    cleared incubator must therefore remain a successful commit.
    """

    try:
        return compact_accepted_correspondence_sync(
            conn,
            accepting_chunk_id=accepting_chunk_id,
        )
    except Exception:
        logger.exception(
            "Correspondence compaction failed after chunk %s was durably "
            "accepted; leaving the uncompacted journal intact for retry on "
            "the next accepted correspondence turn",
            accepting_chunk_id,
        )
        return False


def compact_accepted_correspondence_sync(
    conn: Any,
    *,
    accepting_chunk_id: int,
) -> bool:
    """Run and persist post-accept hysteresis compaction when it is due."""

    from nexus.agents.lore.logon_utility import LogonUtility
    from nexus.config import load_settings_as_dict

    settings = load_settings_as_dict()
    config = correspondence_settings(settings)
    floor_turns = int(config["floor_turns"])
    ceiling_turns = int(config["ceiling_turns"])
    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            plan = plan_correspondence_compaction(
                cur,
                accepting_chunk_id=accepting_chunk_id,
                floor_turns=floor_turns,
                ceiling_turns=ceiling_turns,
            )
    if plan is None:
        return False

    model = config["compaction_model"]
    if not isinstance(model, str) or not model:
        raise ValueError(
            "storyteller.correspondence.compaction_model must resolve to a model"
        )
    dbname = getattr(getattr(conn, "info", None), "dbname", None)
    if not isinstance(dbname, str) or not dbname:
        raise RuntimeError("Correspondence compaction requires a slot DB connection")
    max_digest_tokens = int(config["max_digest_tokens"])
    utility = LogonUtility(
        settings,
        dbname=dbname,
        model_override=model,
    )
    digest = utility.compact_correspondence(
        system_prompt=load_compaction_system_prompt(
            max_digest_tokens=max_digest_tokens
        ),
        user_prompt=plan.render_user_prompt(),
        max_digest_tokens=max_digest_tokens,
    )

    # The model call intentionally owns no database transaction. Re-plan after
    # it returns and refuse to apply stale output if accepted state changed.
    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            current_plan = plan_correspondence_compaction(
                cur,
                accepting_chunk_id=accepting_chunk_id,
                floor_turns=floor_turns,
                ceiling_turns=ceiling_turns,
            )
            if current_plan != plan:
                raise RuntimeError(
                    "Accepted correspondence changed during compaction; refusing "
                    "to persist a stale digest"
                )
            insert_digest_version(cur, plan=plan, digest=digest)
    logger.info(
        "Compacted private storyteller correspondence through chunk %s at "
        "accepting chunk %s",
        plan.compacted_through_chunk_id,
        accepting_chunk_id,
    )
    return True


def apply_state_updates_sync(
    conn, state_updates: StateUpdates, source_chunk_id: Optional[int] = None
):
    """Apply entity state updates synchronously"""
    with conn.cursor() as cur:
        # Update character states
        for char_update in state_updates.characters:
            if char_update.character_id is None:
                raise ValueError("Character state update was not resolved before apply")
            updates: List[str] = []
            params: List[Any] = []
            written_fields: List[tuple[str, Any]] = []

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
                    char_entity_id = _row_value(row, "entity_id", 0) if row else None
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
            if bestowal is not None:
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
            if place_update.place_id is None:
                raise ValueError("Place state update was not resolved before apply")
            if place_update.current_conditions:
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
            if bestowal is not None:
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
            if faction_update.faction_id is None:
                raise ValueError("Faction state update was not resolved before apply")
            bestowal = getattr(faction_update, "orrery_tags", None)
            if bestowal is not None:
                _apply_state_tags(
                    cur,
                    kind="faction",
                    subtype_table="factions",
                    subtype_id=faction_update.faction_id,
                    bestowal=bestowal,
                    source_chunk_id=source_chunk_id,
                )

        for relationship_update in state_updates.relationships:
            if (
                relationship_update.character1_id is None
                or relationship_update.character2_id is None
            ):
                raise ValueError(
                    "Relationship state update was not resolved before apply"
                )
            updates = []
            params = []
            relationship_fields = (
                ("relationship_type", relationship_update.relationship_type),
                ("emotional_valence", relationship_update.emotional_valence),
                ("dynamic", relationship_update.dynamic),
                ("recent_events", relationship_update.recent_events),
            )
            for field, value in relationship_fields:
                if value is None:
                    continue
                updates.append(f"{field} = %s")
                params.append(value.value if hasattr(value, "value") else value)
            if updates:
                params.extend(
                    [
                        relationship_update.character1_id,
                        relationship_update.character2_id,
                    ]
                )
                cur.execute(
                    f"""
                    UPDATE character_relationships
                    SET {', '.join(updates)}
                    WHERE character1_id = %s AND character2_id = %s
                    """,
                    params,
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


def _load_orrery_settings() -> Mapping[str, Any]:
    """Load the Orrery configuration once for one accepted-chunk operation."""

    from nexus.config import load_settings_as_dict

    return cast(Mapping[str, Any], load_settings_as_dict().get("orrery") or {})


def _orrery_checkpoint_interval(orrery_settings: Mapping[str, Any]) -> int:
    """[orrery.reconstruction] checkpoint cadence; 0 disables."""

    reconstruction = orrery_settings.get("reconstruction") or {}
    return int(reconstruction.get("checkpoint_interval_chunks", 0))
