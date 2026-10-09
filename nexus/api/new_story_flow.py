"""
Headless helpers to manage new-story setup per slot.
"""

from __future__ import annotations

from nexus.database import connection_kwargs

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

import psycopg2

from nexus.agents.orrery.retrograde_orchestrator import (
    start_genesis_run,
    record_genesis_failure,
)
from nexus.api.conversations import new_conversation_id
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
from nexus.maintenance.new_story_setup import create_slot_schema_only

if TYPE_CHECKING:
    from nexus.api.new_story_schemas import TransitionData
    from nexus.config.settings_models import Settings
    from nexus.agents.orrery.retrograde_orchestrator import GenesisRunRecord

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
    thread_id = new_conversation_id()
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


def switch_wizard_model(
    slot_number: int,
    *,
    thread_id: Optional[str],
    slot_model: Optional[str],
    model: str,
) -> str:
    """Repoint the slot model; its slot-database conversation does not move."""
    if thread_id is None:
        raise RuntimeError(
            f"Slot {slot_number} has no wizard conversation thread to switch "
            f"to {model!r}; start a new setup"
        )
    if model == slot_model:
        return thread_id
    if not slot_model:
        raise RuntimeError(
            f"Slot {slot_number} has no stamped wizard model; start a new setup"
        )
    repoint_wizard_conversation(
        slot_dbname(slot_number),
        expected_thread_id=thread_id,
        thread_id=thread_id,
        expected_model=slot_model,
        model=model,
    )
    return thread_id


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


class GenesisStageOutputInvalid(RuntimeError):
    """A saved stage is incompatible with its current structured contract."""


class GenesisRunFailed(RuntimeError):
    """The run joined by this request ended with a recorded failure."""


_REUSABLE_GENESIS_STAGES = ("derivation", "packet", "seed_candidates", "expansion")


def genesis_input_fingerprint(
    *,
    transition_data: TransitionData,
    weird_level: WeirdLevel | None,
    model: str,
    settings: Settings,
) -> str:
    """Hash all ruled run inputs before generation mutates the transition data."""
    payload = {
        "version": 1,
        "transition_data": transition_data.model_dump(mode="json"),
        "weird_level": weird_level,
        "model": model,
        "trait_inputs": settings.wizard.trait_inputs.model_dump(mode="json"),
        "wizard_max_retries": settings.wizard.max_retries,
        "orrery": (
            None if settings.orrery is None else settings.orrery.model_dump(mode="json")
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _validate_genesis_output(stage: str, output: Any, run: str) -> Any:
    from nexus.agents.orrery.retrograde_expansion import RetrogradeExpansionPlanResponse
    from nexus.agents.orrery.retrograde_packet import PACKET_SCHEMA_VERSION
    from nexus.agents.orrery.retrograde_seed_candidates import (
        RetrogradeSeedCandidateResponse,
    )
    from nexus.api.trait_compiler_schemas import TraitCompileInputs

    try:
        if stage == "derivation":
            if not isinstance(output, dict) or set(output) != {
                "trait_compile_inputs",
                "outcome",
            }:
                raise ValueError("expected trait_compile_inputs and outcome")
            if output["trait_compile_inputs"] is not None:
                TraitCompileInputs.model_validate(output["trait_compile_inputs"])
            if output["outcome"] is not None and not isinstance(
                output["outcome"], dict
            ):
                raise ValueError("outcome must be a dict or None")
        elif stage == "packet":
            if (
                not isinstance(output, dict)
                or output.get("schema_version") != PACKET_SCHEMA_VERSION
            ):
                raise ValueError(f"expected packet schema {PACKET_SCHEMA_VERSION}")
        elif stage == "seed_candidates":
            RetrogradeSeedCandidateResponse.model_validate(output)
        elif stage == "expansion":
            RetrogradeExpansionPlanResponse.model_validate(output)
        elif stage == "persistence":
            if not isinstance(output, dict):
                raise ValueError("persistence output must be a dict")
            if "counters" not in output or not isinstance(
                output.get("retrograde"), dict
            ):
                raise ValueError("persistence requires counters and retrograde")
            pending = output.get("embedding_pending_summary_ids")
            if not isinstance(pending, list) or any(
                type(item) is not int for item in pending
            ):
                raise ValueError("embedding_pending_summary_ids must be a list of int")
        else:
            raise ValueError(f"Unknown saved genesis stage {stage}")
    except (ValueError, TypeError) as exc:
        raise GenesisStageOutputInvalid(
            f"Saved {stage} output of genesis run {run} no longer validates: {exc}"
        ) from exc
    return output


def reusable_genesis_outputs(
    prior: GenesisRunRecord | None, fingerprint: str
) -> dict[str, Any]:
    """Validate the entire longest reusable prefix before any provider is called."""
    if (
        prior is None
        or prior.status != "failed"
        or prior.input_fingerprint != fingerprint
    ):
        return {}
    persistence = prior.stages.get("persistence")
    if persistence is not None and persistence.output is not None:
        return {}
    blocked = prior.stage == "persistence" and (prior.error or "").startswith(
        "RetrogradePersistenceBlockedError:"
    )
    saved: dict[str, Any] = {}
    for stage in _REUSABLE_GENESIS_STAGES:
        row = prior.stages.get(stage)
        if stage == "derivation" and row is None:
            continue
        if stage == "expansion" and blocked:
            break
        if row is None or row.output is None:
            break
        _validate_genesis_output(stage, row.output, prior.run)
        saved[stage] = row.output
    return saved


def _reuse_genesis_stage(
    slot: int, run: str, prior: GenesisRunRecord, stage: str
) -> None:
    from nexus.agents.orrery.retrograde_orchestrator import (
        record_genesis_stage_output,
        record_retrograde_progress,
    )

    row = prior.stages[stage]
    record_retrograde_progress(
        slot, run, stage, {**row.detail, "reused_from": prior.run}
    )
    record_genesis_stage_output(slot, run, stage, row.output)


def _embedding_retry_message(exc: RuntimeError, slot: int) -> str:
    return (
        f"{exc} -- Retrograde history is committed but not yet embedded; "
        f"retry the transition to finish it (the wizard's Retry, or: "
        f"nexus continue --slot {slot})"
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
       A retry validates and reuses the longest saved prefix when the whole-run
       fingerprint matches. Changed inputs rebuild every stage. The route holds
       a session claim, so repeated POSTs join one run. A history-less world can
       never silently enter narrative mode.
    3. After commit, pending Retrograde summaries are embedded through their
       dedicated lifecycle. An embedding failure surfaces loudly; the rows
       stay pending and a transition retry finishes them from the committed
       ledger without requiring the wizard cache or rebuilding the world.

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
            load_genesis_run,
            persist_retrograde_history,
            record_genesis_input_fingerprint,
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

        fingerprint = genesis_input_fingerprint(
            transition_data=transition_data,
            weird_level=weird_level,
            model=effective_model,
            settings=settings,
        )
        record_genesis_input_fingerprint(slot_number, run, fingerprint)
        prior = load_genesis_run(slot_number, excluding=run)
        saved = reusable_genesis_outputs(prior, fingerprint)
        reused: list[str] = []

        def reuse(stage: str) -> None:
            if prior is None:
                raise RuntimeError("Saved genesis output has no source run")
            _reuse_genesis_stage(slot_number, run, prior, stage)
            reused.append(stage)

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
            if "derivation" in saved:
                from nexus.api.trait_compiler_schemas import TraitCompileInputs

                output = saved["derivation"]
                raw_inputs = output["trait_compile_inputs"]
                transition_data.character.trait_compile_inputs = (
                    None
                    if raw_inputs is None
                    else TraitCompileInputs.model_validate(raw_inputs)
                )
                trait_inputs_outcome = output["outcome"]
                reuse("derivation")
            else:
                # The endpoint owns this sync worker; derivation uses run_sync.
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
                    {
                        "trait_compile_inputs": (
                            derived_inputs.model_dump(mode="json", exclude_none=True)
                            if derived_inputs is not None
                            else None
                        ),
                        "outcome": trait_inputs_outcome,
                    },
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
            result["retrograde"] = {
                "enabled": False,
                "skip_reason": skip_reason,
                "reused_stages": list(reused),
            }
            result["trait_inputs"] = trait_inputs_outcome or {"derived": False}
            result["run"] = run
            result["world_name"] = transition_data.setting.world_name
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
            saved_outputs=saved,
            on_stage_reused=reuse,
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
                    "retrograde": {
                        "enabled": True,
                        "model": bundle.model,
                        "weird": bundle.weird,
                        "surface": build_wizard_history_surface(
                            bundle=bundle, manifest=manifest
                        ),
                        "counters": dict(manifest["counters"]),
                        "entity_stub_budget": dict(manifest["entity_stub_budget"]),
                        "timings": [timing.model_dump() for timing in bundle.timings],
                        "reused_stages": list(reused),
                    },
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
            raise RuntimeError(_embedding_retry_message(exc, slot_number)) from exc

        surface = build_wizard_history_surface(bundle=bundle, manifest=manifest)
        if embedding_results:
            record_genesis_stage_output(
                slot_number,
                run,
                "embedding",
                [entry["summary_id"] for entry in embedding_results],
            )
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
            "reused_stages": reused,
        }
        result["trait_inputs"] = trait_inputs_outcome or {"derived": False}
        result["run"] = run
        result["world_name"] = transition_data.setting.world_name
        return result
    except Exception as exc:
        record_genesis_failure(slot_number, run, f"{type(exc).__name__}: {exc}")
        raise


def transition_result_from_ledger(slot: int, run: str) -> dict[str, Any]:
    """Reconstruct the completed answer without accessing the wizard cache."""
    from nexus.agents.orrery.retrograde_orchestrator import load_genesis_run
    from nexus.api.db_pool import get_connection

    record = load_genesis_run(slot, run)
    if record is None or record.status != "done":
        raise RuntimeError(f"Genesis run {run} is not done")
    with get_connection(slot_dbname(slot)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT g.user_character, c.current_location, p.zone, z.layer, "
            "g.setting->>'world_name' FROM global_variables g "
            "JOIN characters c ON c.id = g.user_character "
            "JOIN places p ON p.id = c.current_location "
            "JOIN zones z ON z.id = p.zone WHERE g.id = TRUE"
        )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"Genesis run {run} has no completed world")
    retrograde: dict[str, Any]
    if record.skip_reason is not None:
        retrograde = {"enabled": False, "skip_reason": record.skip_reason}
    else:
        persistence = record.stages.get("persistence")
        output = None if persistence is None else persistence.output
        output = _validate_genesis_output("persistence", output, record.run)
        embedding = record.stages.get("embedding")
        retrograde = {
            **output["retrograde"],
            "embedded_summary_ids": (
                embedding.output
                if embedding is not None and embedding.output is not None
                else []
            ),
        }
    retrograde["reused_stages"] = [
        stage
        for stage in (*_REUSABLE_GENESIS_STAGES, "persistence")
        if stage in record.stages and "reused_from" in record.stages[stage].detail
    ]
    derivation = record.stages.get("derivation")
    trait_inputs: dict[str, Any] = {"derived": False}
    if derivation is not None and derivation.output is not None:
        _validate_genesis_output("derivation", derivation.output, record.run)
        trait_inputs = derivation.output["outcome"] or trait_inputs
    return {
        "character_id": row[0],
        "place_id": row[1],
        "zone_id": row[2],
        "layer_id": row[3],
        "world_name": row[4],
        "run": record.run,
        "retrograde": retrograde,
        "trait_inputs": trait_inputs,
    }


def resume_committed_genesis_run(slot: int, prior: GenesisRunRecord) -> dict[str, Any]:
    """Finish pending local embedding using an already committed world's ledger."""
    from nexus.agents.orrery.retrograde_orchestrator import (
        embed_retrograde_history_summaries,
        record_genesis_input_fingerprint,
        record_genesis_stage_output,
        record_retrograde_progress,
    )
    from nexus.api.db_pool import get_connection
    from nexus.config import load_settings

    run = start_genesis_run(slot)
    try:
        if prior.input_fingerprint is not None:
            record_genesis_input_fingerprint(slot, run, prior.input_fingerprint)
        persistence = prior.stages.get("persistence")
        output = None if persistence is None else persistence.output
        output = _validate_genesis_output("persistence", output, prior.run)
        stages = (*_REUSABLE_GENESIS_STAGES, "persistence")
        # Validate the full saved set before copying any row or doing embedding.
        for stage in stages:
            saved = prior.stages.get(stage)
            if saved is not None and saved.output is not None:
                _validate_genesis_output(stage, saved.output, prior.run)
        for stage in stages:
            saved = prior.stages.get(stage)
            if saved is not None and saved.output is not None:
                _reuse_genesis_stage(slot, run, prior, stage)
        dbname = slot_dbname(slot)
        with get_connection(dbname) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM retrograde_summaries WHERE id = ANY(%s) "
                "AND embedding_generated_at IS NULL ORDER BY id",
                (output["embedding_pending_summary_ids"],),
            )
            remaining = [row[0] for row in cur.fetchall()]
        settings = load_settings()
        embedding_results: list[dict[str, Any]] = []
        if (
            settings.orrery is not None
            and settings.orrery.retrograde.retrieval.embed_after_apply
            and remaining
        ):
            try:
                embedding_results = embed_retrograde_history_summaries(
                    dbname=dbname,
                    manifest={
                        "retrieval": {"embedding_pending_summary_ids": remaining}
                    },
                    settings=settings,
                    progress=lambda stage, detail: record_retrograde_progress(
                        slot, run, stage, detail
                    ),
                )
            except RuntimeError as exc:
                raise RuntimeError(_embedding_retry_message(exc, slot)) from exc
            if embedding_results:
                record_genesis_stage_output(
                    slot,
                    run,
                    "embedding",
                    [entry["summary_id"] for entry in embedding_results],
                )
        record_retrograde_progress(
            slot, run, "done", {"embedded_summaries": len(embedding_results)}
        )
    except Exception as exc:
        record_genesis_failure(slot, run, f"{type(exc).__name__}: {exc}")
        raise
    return transition_result_from_ledger(slot, run)


def _joined_genesis_result(
    slot: int, record: GenesisRunRecord | None
) -> dict[str, Any] | None:
    from nexus.agents.orrery.retrograde_orchestrator import GENESIS_RUN_INTERRUPTED

    if record is None:
        return None
    if record.status == "done":
        return transition_result_from_ledger(slot, record.run)
    if record.status == "failed" and record.error != GENESIS_RUN_INTERRUPTED:
        raise GenesisRunFailed(f"genesis run {record.run} failed: {record.error}")
    return None


def _own_transition(
    slot: int,
    prepare: Callable[[], tuple[TransitionData, Optional[WeirdLevel]]],
) -> dict[str, Any]:
    from nexus.agents.orrery.retrograde_orchestrator import (
        GENESIS_RUN_INTERRUPTED,
        load_genesis_run,
    )

    latest = load_genesis_run(slot)
    if latest is not None and latest.status == "running":
        record_genesis_failure(slot, latest.run, GENESIS_RUN_INTERRUPTED)
        latest = load_genesis_run(slot, latest.run)
    if latest is not None and latest.status == "failed":
        persistence = latest.stages.get("persistence")
        if persistence is not None and persistence.output is not None:
            return resume_committed_genesis_run(slot, latest)
    data, level = prepare()
    return perform_transition_with_retrograde(slot, data, weird_level=level)


def run_genesis_transition(
    slot: int,
    prepare: Callable[[], tuple[TransitionData, Optional[WeirdLevel]]],
) -> dict[str, Any]:
    """Own one run or join the run that another request started after arrival."""
    from nexus.agents.orrery.retrograde_orchestrator import (
        GENESIS_RUN_INTERRUPTED,
        genesis_slot_claim,
        load_genesis_run,
    )
    from nexus.api.config_utils import get_retrograde_status_poll_interval_seconds

    baseline = load_genesis_run(slot)
    baseline_id = None if baseline is None else baseline.run
    joined = (
        baseline.run if baseline is not None and baseline.status == "running" else None
    )
    while True:
        latest = load_genesis_run(slot)
        if joined is None and latest is not None and latest.run != baseline_id:
            joined = latest.run
        record = load_genesis_run(slot, joined) if joined is not None else None
        if (
            record is not None
            and record.status == "failed"
            and record.error == GENESIS_RUN_INTERRUPTED
            and latest is not None
            and latest.run != record.run
        ):
            joined = latest.run
            record = latest
        result = _joined_genesis_result(slot, record)
        if result is not None:
            return result
        with genesis_slot_claim(slot) as won:
            if won:
                # A previous owner can settle between our read and this claim.
                # Follow that new run instead of preparing the deleted cache.
                latest = load_genesis_run(slot)
                record = load_genesis_run(slot, joined) if joined is not None else None
                if latest is not None and (
                    (joined is None and latest.run != baseline_id)
                    or (
                        record is not None
                        and record.status == "failed"
                        and record.error == GENESIS_RUN_INTERRUPTED
                        and latest.run != record.run
                    )
                ):
                    joined = latest.run
                    record = latest
                result = _joined_genesis_result(slot, record)
                if result is not None:
                    return result
                return _own_transition(slot, prepare)
        time.sleep(get_retrograde_status_poll_interval_seconds())


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
