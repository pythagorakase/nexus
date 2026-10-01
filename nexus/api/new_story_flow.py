"""
Headless helpers to manage new-story setup per slot.
"""

from __future__ import annotations

from nexus.database import AmbiguousCommit, connection_kwargs

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

import psycopg2

from nexus.agents.orrery.retrograde_orchestrator import (
    start_genesis_run,
    record_genesis_failure,
)
from nexus.api.conversations import ConversationsClient, conversation_store_mode
from nexus.api.narrative_schemas import WeirdLevel
from nexus.api.new_story_cache import (
    WizardCache,
    clear_cache,
    init_cache,
    read_cache,
    read_cache_raw,
    repoint_wizard_conversation,
    write_cache,
)
from nexus.api.new_story_schemas import StorySeed
from nexus.api.save_slots import clear_active, get_slot_model, upsert_slot
from nexus.api.slot_utils import slot_dbname, all_slots
from scripts.new_story_setup import create_slot_schema_only

if TYPE_CHECKING:
    from nexus.api.new_story_schemas import TransitionData

logger = logging.getLogger("nexus.api.new_story_flow")


def build_transition_data_from_cache(cache: Any) -> "TransitionData":
    """Hydrate the canonical transition package through wizard-cache adapters."""

    from nexus.api.new_story_schemas import (
        CharacterCreationState,
        CharacterSheet,
        LayerDefinition,
        PlaceProfile,
        SettingCard,
        StorySeed,
        TransitionData,
        ZoneDefinition,
    )

    character_draft = cache.get_character_dict()
    setting_draft = cache.get_setting_dict()
    seed_draft = cache.get_seed_dict()
    layer_draft = cache.get_layer_dict()
    zone_draft = cache.get_zone_dict()
    location_draft = cache.get_initial_location()
    if any(
        value is None
        for value in (
            character_draft,
            setting_draft,
            seed_draft,
            layer_draft,
            zone_draft,
            location_draft,
            cache.base_timestamp,
        )
    ):
        raise ValueError("Wizard cache is incomplete for transition hydration")

    character_state = CharacterCreationState.model_validate(character_draft)
    character_sheet = character_state.to_character_sheet()
    return TransitionData.model_validate(
        {
            "setting": SettingCard.model_validate(setting_draft),
            "character": CharacterSheet.model_validate(character_sheet.model_dump()),
            "seed": StorySeed.model_validate(seed_draft),
            "layer": LayerDefinition.model_validate(layer_draft),
            "zone": ZoneDefinition.model_validate(zone_draft),
            "location": PlaceProfile.model_validate(location_draft),
            "base_timestamp": cache.base_timestamp,
            "thread_id": cache.thread_id or "",
        }
    )


def resolve_setup_model(
    slot_model: Optional[str],
    *,
    setup_started: bool,
    default_slot_model: str,
    wizard_default_model: str,
) -> str:
    """Resolve an omitted model when a new-story setup starts.

    Preserve a slot model when it differs from the fresh-slot placeholder or
    when an existing wizard-cache row proves setup already locked that model.
    Only a genuinely fresh slot falls back to the wizard roster default.
    """
    if slot_model and (setup_started or slot_model != default_slot_model):
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
        conn = psycopg2.connect(**connection_kwargs(dbname))
        conn.close()
    except psycopg2.OperationalError:
        logger.info("Database %s does not exist. Creating...", dbname)
        # NEXUS_template is the schema template database (empty tables, latest schema).
        # New slot databases are created by cloning this template's structure.
        create_slot_schema_only(slot_number, source_db="NEXUS_template")

    from nexus.config import load_settings
    from nexus.config.story_model import StorySettings, resolve_story_model

    settings = load_settings()
    slot_model = get_slot_model(slot_number, dbname=dbname)
    if (
        slot_model == settings.global_.model.default_slot_model
        and read_cache_raw(dbname) is None
    ):
        slot_model = None
    model_to_use = resolve_story_model(
        "wizard",
        settings=settings,
        story=StorySettings(skald_model=slot_model),
        override=model,
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


class WizardConversationMoveError(RuntimeError):
    """A wizard thread could not be moved into the requested model's store."""


def _remove_partial_copy(
    target: ConversationsClient, thread_id: str, message_ids: list[str]
) -> None:
    """Delete a failed move's copied messages, then its thread.

    Hosted conversations retain their items after the conversation is deleted,
    so each copied item goes first. A thread whose items could not all be
    deleted is kept, and logged, so its remaining items stay reachable.
    """
    remaining: list[str] = []
    for message_id in reversed(message_ids):
        try:
            target.delete_message(thread_id, message_id)
        except Exception:
            remaining.append(message_id)
            logger.exception(
                "Removing copied message %s from partial wizard thread %s failed",
                message_id,
                thread_id,
            )
    if remaining:
        logger.error(
            "Partial wizard thread %s remains in %s storage with messages %s",
            thread_id,
            target.store_mode,
            remaining,
        )
        return
    try:
        removed = target.delete_thread(thread_id)
    except Exception:
        removed = False
        logger.exception("Removing partial wizard thread %s failed", thread_id)
    if not removed:
        logger.error(
            "Partial wizard thread %s remains in %s storage",
            thread_id,
            target.store_mode,
        )


def switch_wizard_model(
    slot_number: int,
    *,
    thread_id: Optional[str],
    slot_model: Optional[str],
    model: str,
) -> str:
    """Persist a requested wizard model and keep its conversation readable.

    A model whose provider uses another conversation store (hosted OpenAI,
    local files, or TEST memory) cannot read the current thread. Its messages
    are copied, in order, into a new thread of the requested store, and the
    new thread ID and model are saved in one transaction. Any failure before
    that save leaves the slot model and cached thread ID unchanged and removes
    the partial copy. An ambiguous commit keeps the copy, because the save may
    have landed and the slot may already name the new thread.

    Args:
        slot_number: Target save slot (1-5).
        thread_id: The wizard's current thread ID.
        slot_model: The slot's stamped model, whose store holds the thread.
        model: The explicitly requested wizard model.

    Returns:
        The thread ID the wizard continues in.

    Raises:
        RuntimeError: If the wizard has no thread, or no stamped slot model to
            locate it.
        WizardConversationMoveError: If the current store cannot be read.
        WizardStateConflict: If the thread or slot model changed meanwhile.
        AmbiguousCommit: If the save's outcome is unknown; the copy is kept.
    """
    if thread_id is None:
        raise RuntimeError(
            f"Slot {slot_number} has no wizard conversation thread to switch "
            f"to {model!r}; start a new setup"
        )
    if model == slot_model:
        return thread_id
    if not slot_model:
        raise RuntimeError(
            f"Slot {slot_number} has no stamped wizard model, so the store "
            f"holding thread {thread_id!r} is unknown; start a new setup"
        )
    from nexus.config import load_settings

    dbname = slot_dbname(slot_number)
    settings = load_settings()
    source_mode = conversation_store_mode(
        settings.provider_for_model(slot_model), settings
    )
    target = ConversationsClient(model=model)
    if source_mode == target.store_mode:
        repoint_wizard_conversation(
            dbname,
            expected_thread_id=thread_id,
            thread_id=thread_id,
            expected_model=slot_model,
            model=model,
        )
        return thread_id

    try:
        messages = ConversationsClient(model=slot_model).list_messages(
            thread_id, limit=0
        )
    except Exception as exc:
        raise WizardConversationMoveError(
            f"Cannot move wizard thread {thread_id!r} of slot {slot_number} from "
            f"{source_mode} storage ({slot_model!r}) to {target.store_mode} "
            f"storage ({model!r}): reading the {source_mode} store failed: {exc}"
        ) from exc

    new_thread_id = target.create_thread()
    copied: list[str] = []
    try:
        # list_messages is newest first; replay oldest first with provenance.
        for message in reversed(messages):
            copied.append(
                target.add_message(
                    new_thread_id,
                    message["role"],
                    message["content"],
                    origin=message.get("origin"),
                )
            )
        repoint_wizard_conversation(
            dbname,
            expected_thread_id=thread_id,
            thread_id=new_thread_id,
            expected_model=slot_model,
            model=model,
        )
    except AmbiguousCommit:
        # The save may have committed, so deleting the copy could leave the slot
        # pointing at a missing thread. Keep it; the next read settles the state.
        logger.error(
            "Wizard thread move for slot %s ended in an ambiguous commit; "
            "keeping %s in %s storage until the slot's thread ID is read back",
            slot_number,
            new_thread_id,
            target.store_mode,
        )
        raise
    except BaseException:
        # The original failure propagates; only the partial copy is removed.
        _remove_partial_copy(target, new_thread_id, copied)
        raise
    logger.info(
        "Moved wizard thread %s (%s storage) to %s (%s storage) for slot %s",
        thread_id,
        source_mode,
        new_thread_id,
        target.store_mode,
        slot_number,
    )
    return new_thread_id


def resume_setup(slot_number: int) -> Optional[WizardCache]:
    """
    Resume setup by returning cache contents for the slot.

    Args:
        slot_number: Target save slot (1-5)

    Returns:
        Cached setup data, or None if no cache exists
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
    if seed is not None:
        accepted_seed_timestamp = StorySeed.model_validate(seed).get_base_datetime()
        if base_timestamp is None:
            raise ValueError(
                "A seed draft requires its accepted base_timestamp for persistence"
            )
        persisted_timestamp = datetime.fromisoformat(base_timestamp)
        if persisted_timestamp.tzinfo is None:
            raise ValueError("Seed base_timestamp must be timezone-aware")
        if persisted_timestamp.astimezone(timezone.utc) != accepted_seed_timestamp:
            raise ValueError(
                "Persisted base_timestamp must equal the accepted seed "
                f"base_timestamp ({accepted_seed_timestamp.isoformat()})"
            )

    dbname = slot_dbname(slot_number)
    cache = read_cache(dbname)

    # Build args for legacy write_cache, preserving existing data
    write_cache(
        invalidate_phase=(
            "setting"
            if setting is not None
            else "character" if character is not None else None
        ),
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


def _record_genesis_weird(
    cur: Any,
    weird: Optional[Dict[str, Any]],
    *,
    selected_level: Optional[WeirdLevel],
) -> None:
    """Write the story's genesis strangeness provenance on the transition cursor.

    ``weird`` is the profile Retrograde resolved (level, genre, band source,
    raw bounds), or None for a story that began without Retrograde history;
    None also replaces an earlier story's provenance on an overwritten slot.
    ``selected_level`` is the level the wizard cache carried into the
    transition, None when the player never chose one (the resolved ``level``
    is then [orrery.retrograde.weird].default_level); it is stored beside the
    profile so a choice can be told apart from the default.

    Raises:
        RuntimeError: If the slot has no global_variables row to record it on.
    """
    provenance = None if weird is None else {**weird, "selected_level": selected_level}
    cur.execute(
        "UPDATE global_variables SET genesis_weird = %s::jsonb WHERE id = TRUE",
        (json.dumps(provenance) if provenance is not None else None,),
    )
    if cur.rowcount != 1:
        raise RuntimeError(
            "The transition found no global_variables row for the genesis "
            "strangeness provenance"
        )


def perform_transition_with_retrograde(
    slot_number: int,
    transition_data: "TransitionData",
    *,
    model: Optional[str] = None,
    weird_level: Optional[WeirdLevel] = None,
) -> Dict[str, Any]:
    """
    Run the wizard -> narrative transition with Retrograde cold-start history.

    Composition (spec decision 14, M4):

    1. Non-mutating Retrograde generation runs first from the wizard cache:
       R1 packet assembly, the R4/R5 seed-candidate Skald call, and the R6
       expansion Skald call. Nothing canonical is written yet.
    2. ``perform_transition`` then writes the world (protagonist, location
       hierarchy, trait compilation with stubs) and Retrograde persistence
       joins the same transaction via the in_transaction hook. A blocked persistence
       raises and rolls back everything: the slot keeps its wizard cache and stays
       in wizard-ready, and the run is recorded as failed at its stage in genesis_runs.
       A retry starts a new run and repeats every stage; resuming from saved stage
       outputs is 776-S1b. A history-less world can never silently enter narrative mode.
    3. After commit, pending Retrograde summaries are embedded through their
       dedicated lifecycle. An embedding failure surfaces loudly; the rows
       stay pending and retryable via
       ``nexus retrograde-embed-history --slot N --execute``.

    The resolved strangeness profile, with the selected level beside it, is
    recorded as ``global_variables.genesis_weird`` in the world's
    transaction; a story that begins without Retrograde history records none.

    Retrograde is skipped (plain transition) when the [orrery] section is
    disabled, when [orrery.retrograde.wizard].enabled is false, or when the
    slot's wizard model belongs to the TEST provider.

    Args:
        slot_number: Target save slot (1-5)
        transition_data: Validated transition package built from the cache
        model: Optional model override for the Retrograde Skald calls
            (defaults to the slot's configured model, then the wizard default)
        weird_level: The player's genesis strangeness (low, medium, or high)
            as the wizard cache carried it. None resolves to
            [orrery.retrograde.weird].default_level when Retrograde maps it
            onto the story genre's band, and is recorded as the provenance's
            ``selected_level`` either way.

    Returns:
        Dictionary with created IDs plus a "retrograde" outcome block
    """
    run = start_genesis_run(slot_number)
    try:
        from nexus.agents.orrery.retrograde_orchestrator import (
            build_wizard_history_surface,
            embed_retrograde_history_summaries,
            finish_genesis_persistence,
            finish_skipped_genesis_run,
            generate_retrograde_history,
            persist_retrograde_history,
            record_genesis_stage_output,
            record_retrograde_progress,
        )
        from nexus.api.new_story_db_mapper import NewStoryDatabaseMapper
        from nexus.api.save_slots import get_slot_model
        from nexus.config import load_settings

        dbname = slot_dbname(slot_number)
        mapper = NewStoryDatabaseMapper(dbname=dbname)
        settings = load_settings()
        orrery_settings = settings.orrery

        from nexus.config.story_model import StorySettings, resolve_story_model

        effective_model = resolve_story_model(
            "wizard",
            settings=settings,
            story=StorySettings(skald_model=get_slot_model(slot_number, dbname=dbname)),
            override=model,
        )

        # Derive typed trait-compiler inputs before any world writes so the
        # compiler can create stub entities and relationship rows (M9). TEST-provider
        # wizards stay hermetic: no trait derivation and no Retrograde calls.
        trait_inputs_outcome: Optional[Dict[str, Any]] = None
        trait_inputs_settings = settings.wizard.trait_inputs
        if (
            not settings.is_test_model(effective_model)
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
            record_retrograde_progress(slot_number, run, "derivation", {})
            trait_inputs_outcome = ensure_trait_compile_inputs(
                transition_data,
                slot=slot_number,
                model_name=effective_model,
                max_tokens=trait_inputs_settings.max_tokens,
                retries=settings.wizard.max_retries,
            )

            derived_inputs = transition_data.character.trait_compile_inputs
            record_genesis_stage_output(
                slot_number,
                run,
                "derivation",
                (
                    derived_inputs.model_dump(mode="json", exclude_none=True)
                    if derived_inputs is not None
                    else None
                ),
            )

        if orrery_settings is None or not orrery_settings.enabled:
            skip_reason = "orrery_disabled"
        elif not orrery_settings.retrograde.wizard.enabled:
            skip_reason = "retrograde_wizard_disabled"
        elif settings.is_test_model(effective_model):
            skip_reason = "mock_wizard_model"
        else:
            skip_reason = None

        if skip_reason is not None:
            logger.info(
                "Skipping Retrograde cold start for slot %s (%s)",
                slot_number,
                skip_reason,
            )

            def _skip_hook(cur: Any) -> None:
                _record_genesis_weird(cur, None, selected_level=None)
                finish_skipped_genesis_run(cur, run=run, skip_reason=skip_reason)

            result: Dict[str, Any] = dict(
                mapper.perform_transition(
                    transition_data,
                    in_transaction=_skip_hook,
                )
            )
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

        def _progress(stage: str, detail: Dict[str, Any]) -> None:
            record_retrograde_progress(slot_number, run, stage, detail)

        derived_inputs = transition_data.character.trait_compile_inputs
        bundle = generate_retrograde_history(
            slot=slot_number,
            dbname=dbname,
            cache=cache,
            settings=settings,
            model_name=effective_model,
            max_tokens=orrery_settings.retrograde.wizard.max_tokens,
            weird_level=weird_level,
            progress=_progress,
            on_stage_output=lambda stage, output: record_genesis_stage_output(
                slot_number, run, stage, output
            ),
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
            )
            # Provenance commits with the history it describes, or not at all.
            _record_genesis_weird(cur, bundle.weird, selected_level=weird_level)
            manifest = manifest_holder["manifest"]
            finish_genesis_persistence(
                cur,
                run=run,
                output={
                    "counters": manifest["counters"],
                    "embedding_pending_summary_ids": manifest["retrieval"][
                        "embedding_pending_summary_ids"
                    ],
                },
            )

        record_retrograde_progress(slot_number, run, "persistence", {})
        result = dict(
            mapper.perform_transition(transition_data, in_transaction=_persist_hook)
        )

        manifest = manifest_holder["manifest"]
        try:
            embedding_results = embed_retrograde_history_summaries(
                dbname=dbname,
                manifest=manifest,
                settings=settings,
                progress=_progress,
            )
        except RuntimeError as exc:
            raise RuntimeError(
                f"{exc} -- Retrograde history is committed but not yet embedded; "
                f"run: nexus retrograde-embed-history --slot {slot_number} --execute"
            ) from exc

        surface = build_wizard_history_surface(bundle=bundle, manifest=manifest)
        record_retrograde_progress(
            slot_number,
            run,
            "done",
            {"embedded_summaries": len(embedding_results)},
        )
        result["retrograde"] = {
            "enabled": True,
            "model": bundle.model,
            "weird": bundle.weird,
            "surface": surface,
            "counters": dict(manifest["counters"]),
            "entity_stub_budget": dict(manifest["entity_stub_budget"]),
            "embedded_summary_ids": [
                entry["summary_id"] for entry in embedding_results
            ],
            "timings": [timing.model_dump() for timing in bundle.timings],
        }
        result["trait_inputs"] = trait_inputs_outcome or {"derived": False}
        return result
    except Exception as exc:
        record_genesis_failure(slot_number, run, f"{type(exc).__name__}: {exc}")
        raise


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
    from nexus.api.db_pool import dispose_database
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
    dispose_database(dbname)

    # Drop and recreate from template - handles all tables automatically
    create_slot_schema_only(slot_number, source_db="NEXUS_template", force=True)

    # Mark slot as inactive after reset
    upsert_slot(slot_number, is_active=False, dbname=dbname)
    dispose_database(dbname)
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
