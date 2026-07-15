"""
Headless helpers to manage new-story setup per slot.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

import psycopg2

from nexus.api.conversations import ConversationsClient
from nexus.api.new_story_cache import read_cache, write_cache, clear_cache, init_cache
from nexus.api.save_slots import clear_active, get_slot_model, upsert_slot
from nexus.api.slot_utils import slot_dbname, all_slots
from scripts.new_story_setup import create_slot_schema_only

if TYPE_CHECKING:
    from nexus.api.new_story_schemas import TransitionData

logger = logging.getLogger("nexus.api.new_story_flow")

# Mock wizard model: the transition must stay hermetic, so Retrograde's real
# frontier calls are skipped when the slot ran the wizard against the mock.
MOCK_WIZARD_MODEL = "TEST"


def resolve_setup_model(
    requested_model: Optional[str],
    slot_model: Optional[str],
    *,
    default_slot_model: str,
    wizard_default_model: str,
) -> str:
    """Resolve the model locked in when a new-story setup starts.

    An explicit request is authoritative. Otherwise, preserve an operator-set
    slot model, identified by a value other than the configured fresh-slot
    placeholder. Only an unset/fresh slot falls back to the wizard roster
    default.
    """
    if requested_model:
        return requested_model
    if slot_model and slot_model != default_slot_model:
        return slot_model
    return wizard_default_model


def start_setup(slot_number: int, model: Optional[str] = None) -> str:
    """
    Start a new setup conversation for a slot.

    - Clears cache in the slot DB
    - Creates a conversations thread and stores thread_id
    - Marks slot as active (and clears other actives)

    Args:
        slot_number: Target save slot (1-5)
        model: Optional explicit model override. When omitted, an existing
            operator-set slot model is preserved; only an unset/fresh slot
            uses the configured wizard default.

    Returns:
        Thread ID for the new conversation
    """
    dbname = slot_dbname(slot_number)

    # Ensure database exists
    try:
        conn = psycopg2.connect(database=dbname)
        conn.close()
    except psycopg2.OperationalError:
        logger.info("Database %s does not exist. Creating...", dbname)
        # NEXUS_template is the schema template database (empty tables, latest schema).
        # New slot databases are created by cloning this template's structure.
        create_slot_schema_only(slot_number, source_db="NEXUS_template")

    if model:
        # Preserve the explicit-override path without requiring config or a
        # metadata read: it is authoritative by definition.
        model_to_use = model
    else:
        from nexus.config import load_settings

        settings = load_settings()
        model_to_use = resolve_setup_model(
            None,
            get_slot_model(slot_number, dbname=dbname),
            default_slot_model=settings.global_.model.default_slot_model,
            wizard_default_model=settings.wizard.default_model,
        )

    clear_cache(dbname)
    client = ConversationsClient(model=model_to_use)
    thread_id = client.create_thread()
    init_cache(dbname, thread_id=thread_id, target_slot=slot_number)
    clear_active(dbname)
    # Persist model to save_slots so bootstrap/narrative can use it
    upsert_slot(slot_number, is_active=True, model=model_to_use, dbname=dbname)
    logger.info(
        "Started setup for slot %s with thread %s (model=%s)",
        slot_number,
        thread_id,
        model_to_use,
    )
    return thread_id


def resume_setup(slot_number: int) -> Optional[Dict]:
    """
    Resume setup by returning cache contents for the slot.

    Args:
        slot_number: Target save slot (1-5)

    Returns:
        Dictionary containing cached setup data, or None if no cache exists
    """
    dbname = slot_dbname(slot_number)
    cache = read_cache(dbname)
    if cache:
        logger.info("Resuming setup for slot %s", slot_number)
    else:
        logger.info("No setup cache found for slot %s", slot_number)
    return cache


def record_drafts(
    slot_number: int,
    *,
    setting: Optional[Dict] = None,
    character: Optional[Dict] = None,
    seed: Optional[Dict] = None,
    layer: Optional[Dict] = None,
    zone: Optional[Dict] = None,
    location: Optional[Dict] = None,
    base_timestamp: Optional[str] = None,
) -> None:
    """
    Persist current drafts to the slot cache.

    Uses the legacy write_cache function which handles translation
    from JSONB dict format to normalized columns.

    Args:
        slot_number: Target save slot (1-5)
        setting: Optional setting draft dictionary
        character: Optional character draft dictionary
        seed: Optional seed selection dictionary
        layer: Optional layer definition dictionary
        zone: Optional zone definition dictionary
        location: Optional initial location dictionary
        base_timestamp: Optional ISO timestamp string
    """
    dbname = slot_dbname(slot_number)
    cache = read_cache(dbname)

    # Build args for legacy write_cache, preserving existing data
    write_cache(
        thread_id=cache.thread_id if cache else None,
        setting_draft=setting or (cache.get_setting_dict() if cache else None),
        character_draft=character or (cache.get_character_dict() if cache else None),
        selected_seed=seed or (cache.get_seed_dict() if cache else None),
        layer_draft=layer or (cache.get_layer_dict() if cache else None),
        zone_draft=zone or (cache.get_zone_dict() if cache else None),
        initial_location=location or (cache.get_initial_location() if cache else None),
        base_timestamp=base_timestamp
        or (str(cache.base_timestamp) if cache and cache.base_timestamp else None),
        target_slot=slot_number,
        dbname=dbname,
    )
    logger.info("Updated drafts for slot %s", slot_number)


def perform_transition_with_retrograde(
    slot_number: int,
    transition_data: "TransitionData",
    *,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the wizard -> narrative transition with Retrograde cold-start history.

    Composition (spec decision 14, M4):

    1. Non-mutating Retrograde generation runs first from the wizard cache:
       R1 packet assembly, the R4/R5 seed-candidate Skald call, and the R6
       expansion Skald call. Nothing canonical is written yet.
    2. ``perform_transition`` then writes the world (protagonist, location
       hierarchy, trait compilation with stubs) and Retrograde persistence
       joins the same transaction via the in_transaction hook. A blocked
       persistence raises, rolling back everything: the slot keeps its wizard
       cache, stays in wizard-ready, and the retry re-runs the pipeline from
       the clean-slate preamble. A history-less world can never silently
       enter narrative mode.
    3. After commit, pending Retrograde summary chunks are embedded through
       the standard chunk lifecycle. An embedding failure surfaces loudly;
       the chunks stay pending and retryable via
       ``nexus retrograde-embed-history --slot N --execute``.

    Retrograde is skipped (plain transition) when the [orrery] section is
    disabled, when [orrery.retrograde.wizard].enabled is false, or when the
    slot ran the wizard against the mock TEST model.

    Args:
        slot_number: Target save slot (1-5)
        transition_data: Validated transition package built from the cache
        model: Optional model override for the Retrograde Skald calls
            (defaults to the slot's configured model, then the wizard default)

    Returns:
        Dictionary with created IDs plus a "retrograde" outcome block
    """
    from nexus.agents.orrery.retrograde_orchestrator import (
        build_wizard_history_surface,
        embed_retrograde_history_chunks,
        generate_retrograde_history,
        persist_retrograde_history,
        record_retrograde_progress,
        reset_retrograde_progress,
    )
    from nexus.api.new_story_db_mapper import NewStoryDatabaseMapper
    from nexus.api.save_slots import get_slot_model
    from nexus.config import load_settings

    dbname = slot_dbname(slot_number)
    mapper = NewStoryDatabaseMapper(dbname=dbname)
    settings = load_settings()
    orrery_settings = settings.orrery

    effective_model = model or get_slot_model(slot_number, dbname=dbname)

    # Derive typed trait-compiler inputs before any world writes so the
    # compiler can create stub entities and relationship rows (M9). Runs for
    # real models only; the mock TEST wizard stays hermetic.
    trait_inputs_outcome: Optional[Dict[str, Any]] = None
    trait_inputs_settings = settings.wizard.trait_inputs
    if (
        effective_model != MOCK_WIZARD_MODEL
        and trait_inputs_settings.derive_at_transition
    ):
        from nexus.api.trait_input_derivation import ensure_trait_compile_inputs

        if effective_model is None:
            raise ValueError(
                f"Slot {slot_number} has no configured model; cannot derive "
                "trait compile inputs at the transition"
            )
        # Sync context only: the transition endpoint runs this whole
        # function via asyncio.to_thread, and the deriver uses
        # agent.run_sync, which would deadlock inside a running event loop.
        trait_inputs_outcome = ensure_trait_compile_inputs(
            transition_data,
            slot=slot_number,
            model_name=effective_model,
            max_tokens=trait_inputs_settings.max_tokens,
            retries=settings.wizard.max_retries,
        )

    if orrery_settings is None or not orrery_settings.enabled:
        skip_reason = "orrery_disabled"
    elif not orrery_settings.retrograde.wizard.enabled:
        skip_reason = "retrograde_wizard_disabled"
    elif effective_model == MOCK_WIZARD_MODEL:
        skip_reason = "mock_wizard_model"
    else:
        skip_reason = None

    if skip_reason is not None:
        logger.info(
            "Skipping Retrograde cold start for slot %s (%s)",
            slot_number,
            skip_reason,
        )
        result: Dict[str, Any] = dict(mapper.perform_transition(transition_data))
        result["retrograde"] = {"enabled": False, "skip_reason": skip_reason}
        result["trait_inputs"] = trait_inputs_outcome or {"derived": False}
        return result

    # Narrowing only: orrery_settings None always sets skip_reason above.
    assert orrery_settings is not None

    cache = read_cache(dbname)
    if cache is None:
        raise ValueError(
            f"Slot {slot_number} has no wizard cache; cannot run Retrograde "
            "cold-start generation"
        )

    reset_retrograde_progress(slot_number)

    def _progress(stage: str, detail: Dict[str, Any]) -> None:
        record_retrograde_progress(slot_number, stage, detail)

    derived_inputs = transition_data.character.trait_compile_inputs
    bundle = generate_retrograde_history(
        slot=slot_number,
        dbname=dbname,
        cache=cache,
        settings=settings,
        model_name=effective_model,
        max_tokens=orrery_settings.retrograde.wizard.max_tokens,
        progress=_progress,
        trait_compile_inputs=(
            derived_inputs.model_dump(mode="json", exclude_none=True)
            if derived_inputs is not None
            else None
        ),
    )

    manifest_holder: Dict[str, Any] = {}

    def _persist_hook(cur: Any) -> None:
        manifest_holder["manifest"] = persist_retrograde_history(
            cur,
            bundle=bundle,
            settings=settings,
            progress=_progress,
        )

    try:
        result = dict(
            mapper.perform_transition(transition_data, in_transaction=_persist_hook)
        )
    except Exception:
        record_retrograde_progress(slot_number, "failed", {"stage": "persistence"})
        raise

    manifest = manifest_holder["manifest"]
    try:
        embedding_results = embed_retrograde_history_chunks(
            dbname=dbname,
            manifest=manifest,
            settings=settings,
            progress=_progress,
        )
    except RuntimeError as exc:
        record_retrograde_progress(slot_number, "failed", {"stage": "embedding"})
        raise RuntimeError(
            f"{exc} -- Retrograde history is committed but not yet embedded; "
            f"run: nexus retrograde-embed-history --slot {slot_number} --execute"
        ) from exc

    surface = build_wizard_history_surface(bundle=bundle, manifest=manifest)
    record_retrograde_progress(
        slot_number,
        "done",
        {"embedded_chunks": len(embedding_results)},
    )
    result["retrograde"] = {
        "enabled": True,
        "model": bundle.model,
        "weird": bundle.weird,
        "surface": surface,
        "counters": dict(manifest["counters"]),
        "embedded_chunk_ids": [entry["chunk_id"] for entry in embedding_results],
        "timings": [timing.model_dump() for timing in bundle.timings],
    }
    result["trait_inputs"] = trait_inputs_outcome or {"derived": False}
    return result


def reset_setup(slot_number: int) -> None:
    """
    Clear all slot state for a completely fresh start.

    Drops and recreates the slot database from the NEXUS template,
    ensuring a clean schema with no leftover data.

    Args:
        slot_number: Target save slot (1-5)

    Raises:
        ValueError: If the slot is locked
    """
    from nexus.api.db_pool import close_pool
    from nexus.api.save_slots import is_slot_locked

    dbname = slot_dbname(slot_number)

    # Check lock before any destructive operation
    if is_slot_locked(slot_number, dbname=dbname):
        raise ValueError(
            f"Slot {slot_number} is locked. Unlock it first with: nexus unlock --slot {slot_number}"
        )

    logger.info("Resetting slot %s by recreating from NEXUS_template", slot_number)

    # Close the connection pool BEFORE dropping the database
    # Otherwise pg_terminate_backend kills connections but the pool reconnects immediately
    close_pool(dbname)

    # Drop and recreate from template - handles all tables automatically
    create_slot_schema_only(slot_number, source_db="NEXUS_template", force=True)

    # Mark slot as inactive after reset
    upsert_slot(slot_number, is_active=False, dbname=dbname)
    logger.info("Reset complete for slot %s", slot_number)


def activate_slot(target_slot: int) -> Dict[str, str]:
    """
    Mark a slot as active and clear active flags in other slots.

    Skips slots whose databases do not exist.

    Args:
        target_slot: Slot number to activate (1-5)

    Returns:
        Dictionary mapping slot numbers to status strings ("active", "cleared", "unavailable")
    """
    results = {}
    for slot in all_slots():
        dbname = slot_dbname(slot)
        try:
            if slot == target_slot:
                upsert_slot(slot, is_active=True, dbname=dbname)
                results[slot] = "active"
            else:
                clear_active(dbname)
                results[slot] = "cleared"
        except (
            psycopg2.Error,
            OSError,
        ) as exc:  # pragma: no cover - defensive cross-db handling
            logger.warning("Slot %s DB not available: %s", slot, exc)
            results[slot] = "unavailable"
    return results
