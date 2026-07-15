"""Wizard-time Retrograde orchestration: packet through persistence/embedding.

This module composes the existing Retrograde stage functions (the same core
the ``nexus retrograde-*`` CLI verbs call) into the cold-start pipeline the
new-story wizard fires at the ready -> narrative transition:

1. ``generate_retrograde_history`` runs the non-mutating stages: R1 packet
   assembly from the wizard cache, the R4/R5 Skald seed-candidate call, and
   the R6 Skald expansion call. No canonical rows are written.
2. ``persist_retrograde_history`` joins the caller's transaction cursor and
   executes the persistence plan (events, tags, pair tags, relationships,
   stubs, dedicated summaries). Decision 14: this runs inside the same transaction
   as the wizard transition writes, so a blocked persistence rolls back the
   whole world and the slot stays in wizard-ready for a loud, retryable
   failure -- a history-less world can never silently enter narrative mode.
3. ``embed_retrograde_history_summaries`` runs the summary embedding lifecycle
   for the new rows after the transaction commits.
4. ``build_wizard_history_surface`` projects the persistence manifest into
   the Decision 6 split: core entities and intentional relationships are
   player-visible; event prose, tags, and deferred seeds stay hidden with
   counts only.

Progress states for each stage are published to a process-local registry so
the API can expose them while the transition request is in flight.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field

from nexus.config.settings_models import (
    OrreryRetrogradeRetrievalSettings,
    OrreryRetrogradeWizardSettings,
    Settings,
)

logger = logging.getLogger("nexus.agents.orrery.retrograde_orchestrator")

RETROGRADE_WIZARD_STAGES: tuple[str, ...] = (
    "packet",
    "seed_candidates",
    "expansion",
    "persistence",
    "embedding",
    "done",
)

ProgressCallback = Callable[[str, dict[str, Any]], None]

_PROGRESS_LOCK = threading.Lock()
_PROGRESS_BY_SLOT: dict[int, dict[str, Any]] = {}


class RetrogradePersistenceBlockedError(ValueError):
    """A validated expansion cannot be persisted; surface blockers loudly."""

    def __init__(self, message: str, *, blockers: list[dict[str, Any]]):
        super().__init__(message)
        self.blockers = blockers


class RetrogradeStageTiming(BaseModel):
    """Wall-clock duration of one orchestrated Retrograde stage."""

    model_config = ConfigDict(extra="forbid")

    stage: str
    seconds: float = Field(ge=0.0)


class RetrogradeGenerationBundle(BaseModel):
    """Output of the non-mutating generation stages (R1 packet, R4/R5, R6)."""

    model_config = ConfigDict(extra="forbid")

    slot: int
    dbname: str
    model: str
    weird: dict[str, Any]
    packet: dict[str, Any]
    seed_candidate_response: dict[str, Any]
    expansion_plan: dict[str, Any]
    timings: list[RetrogradeStageTiming]


def record_retrograde_progress(
    slot: int,
    stage: str,
    detail: Optional[Mapping[str, Any]] = None,
) -> None:
    """Publish the current Retrograde stage for one slot's transition run."""

    if stage not in RETROGRADE_WIZARD_STAGES and stage != "failed":
        raise ValueError(f"Unknown Retrograde wizard stage {stage!r}")
    with _PROGRESS_LOCK:
        entry = _PROGRESS_BY_SLOT.setdefault(
            slot,
            {"slot": slot, "stages": []},
        )
        entry["stage"] = stage
        entry["detail"] = dict(detail or {})
        entry["updated_at"] = datetime.now(timezone.utc).isoformat()
        entry["stages"].append(
            {"stage": stage, "at": entry["updated_at"], "detail": entry["detail"]}
        )


def get_retrograde_progress(slot: int) -> Optional[dict[str, Any]]:
    """Return the most recent Retrograde progress entry for a slot, if any."""

    with _PROGRESS_LOCK:
        entry = _PROGRESS_BY_SLOT.get(slot)
        if entry is None:
            return None
        return {
            "slot": entry["slot"],
            "stage": entry["stage"],
            "detail": dict(entry["detail"]),
            "updated_at": entry["updated_at"],
            "stages": [dict(item) for item in entry["stages"]],
        }


def reset_retrograde_progress(slot: int) -> None:
    """Clear the progress registry for a slot before a new transition run."""

    with _PROGRESS_LOCK:
        _PROGRESS_BY_SLOT.pop(slot, None)


def generate_retrograde_history(
    *,
    slot: int,
    dbname: str,
    cache: Any,
    settings: Settings,
    model_name: Optional[str] = None,
    max_tokens: Optional[int] = None,
    weird_level: Optional[str] = None,
    weird_raw: Optional[float] = None,
    progress: Optional[ProgressCallback] = None,
    trait_compile_inputs: Optional[Mapping[str, Any]] = None,
) -> RetrogradeGenerationBundle:
    """Run the non-mutating Retrograde stages from a wizard cache snapshot.

    Builds the R1-R3 dry-run packet, makes the R4/R5 Skald seed-candidate
    call, and makes the R6 Skald expansion call. Writes nothing canonical;
    the returned bundle feeds ``persist_retrograde_history``.
    """

    from nexus.agents.orrery.retrograde_expansion import generate_expansion_with_skald
    from nexus.agents.orrery.retrograde_packet import build_retrograde_dry_run_packet
    from nexus.agents.orrery.retrograde_seed_candidates import run_seed_stage
    from nexus.agents.orrery.retrograde_vocabulary import (
        enumerate_seed_eligible_vocabulary,
    )

    timings: list[RetrogradeStageTiming] = []

    _emit(progress, "packet", {})
    started = time.monotonic()
    packet = build_retrograde_dry_run_packet(
        slot=slot,
        dbname=dbname,
        cache=cache,
        vocabulary=enumerate_seed_eligible_vocabulary(dbname=dbname),
        settings=settings,
        weird_level=weird_level,
        weird_raw=weird_raw,
        trait_compile_inputs=trait_compile_inputs,
    )
    timings.append(
        RetrogradeStageTiming(stage="packet", seconds=time.monotonic() - started)
    )

    _emit(progress, "seed_candidates", {"weird": packet["weird"]["level"]})
    started = time.monotonic()
    seed_generation = run_seed_stage(
        packet=packet,
        model_name=model_name,
        max_tokens=max_tokens,
    )
    timings.append(
        RetrogradeStageTiming(
            stage="seed_candidates", seconds=time.monotonic() - started
        )
    )
    seed_response = seed_generation["seed_candidate_response"]

    _emit(
        progress,
        "expansion",
        {
            "candidates": len(seed_response["candidates"]),
            "selected": len(seed_response["selected_seed_ids"]),
        },
    )
    started = time.monotonic()
    expansion_generation = generate_expansion_with_skald(
        packet=packet,
        seed_candidate_response=seed_response,
        model_name=model_name,
        max_tokens=max_tokens,
    )
    timings.append(
        RetrogradeStageTiming(stage="expansion", seconds=time.monotonic() - started)
    )

    return RetrogradeGenerationBundle(
        slot=slot,
        dbname=dbname,
        model=str(seed_generation["model"]),
        weird=dict(packet["weird"]),
        packet=packet,
        seed_candidate_response=dict(seed_response),
        expansion_plan=dict(expansion_generation["retrograde_expansion_plan"]),
        timings=timings,
    )


def persist_retrograde_history(
    cur: Any,
    *,
    bundle: RetrogradeGenerationBundle,
    settings: Settings,
    recorded_at_chunk_id: Optional[int] = None,
    progress: Optional[ProgressCallback] = None,
) -> dict[str, Any]:
    """Execute the persistence plan on the caller's transaction cursor.

    Runs a read-only planning pass first; if any execute blocker remains or
    the Decision 8 stub cap is exceeded, raises
    ``RetrogradePersistenceBlockedError`` so the enclosing transaction rolls
    back. Otherwise executes canonical writes and returns the manifest.
    """

    from nexus.agents.orrery.retrograde_persistence import (
        build_retrograde_persistence_plan,
    )

    wizard_settings, retrieval_settings = _require_retrograde_settings(settings)
    if settings.orrery is None:
        raise AssertionError("Retrograde settings validation did not require Orrery")
    epistemics_settings = settings.orrery.epistemics

    _emit(progress, "persistence", {})
    dry_manifest = build_retrograde_persistence_plan(
        cur,
        packet=bundle.packet,
        seed_candidate_response=bundle.seed_candidate_response,
        expansion_plan_payload=bundle.expansion_plan,
        slot=bundle.slot,
        dbname=bundle.dbname,
        dry_run=True,
        create_missing_entities=wizard_settings.create_entity_stubs,
        summaries_enabled=retrieval_settings.summaries_enabled,
        recorded_at_chunk_id=recorded_at_chunk_id,
        epistemics_settings=epistemics_settings,
    )

    blockers = list(dry_manifest["execute_blockers"])
    if blockers:
        reasons = "; ".join(blocker["reason"] for blocker in blockers)
        raise RetrogradePersistenceBlockedError(
            "Retrograde expansion succeeded but persistence is blocked: " f"{reasons}",
            blockers=blockers,
        )

    stub_rows = [
        row
        for row in dry_manifest["entity_stub_rows"]
        if row["status"] == "would_insert"
    ]
    if len(stub_rows) > wizard_settings.max_new_entity_stubs:
        listed = ", ".join(
            f"{row['entity_kind']}:{row['entity_ref']}" for row in stub_rows
        )
        raise RetrogradePersistenceBlockedError(
            f"Retrograde expansion would create {len(stub_rows)} new entity "
            "stubs, exceeding orrery.retrograde.wizard.max_new_entity_stubs="
            f"{wizard_settings.max_new_entity_stubs}: {listed}",
            blockers=[
                {
                    "id": "entity_stub_budget_exceeded",
                    "reason": (
                        f"{len(stub_rows)} new stubs exceed the configured cap "
                        f"of {wizard_settings.max_new_entity_stubs}"
                    ),
                }
            ],
        )

    manifest = build_retrograde_persistence_plan(
        cur,
        packet=bundle.packet,
        seed_candidate_response=bundle.seed_candidate_response,
        expansion_plan_payload=bundle.expansion_plan,
        slot=bundle.slot,
        dbname=bundle.dbname,
        dry_run=False,
        create_missing_entities=wizard_settings.create_entity_stubs,
        summaries_enabled=retrieval_settings.summaries_enabled,
        recorded_at_chunk_id=recorded_at_chunk_id,
        epistemics_settings=epistemics_settings,
    )
    logger.info(
        "Retrograde persistence executed for slot %s: %s",
        bundle.slot,
        manifest["counters"],
    )
    return manifest


def embed_retrograde_history_summaries(
    *,
    dbname: str,
    manifest: Mapping[str, Any],
    settings: Settings,
    progress: Optional[ProgressCallback] = None,
) -> list[dict[str, Any]]:
    """Embed pending Retrograde summaries after the apply commit.

    Must run after the persistence transaction commits. The embedding layer
    generates vectors in-process and writes them through a pooled connection.
    Raises ``RuntimeError`` if any summary fails; pending rows stay retryable via
    ``nexus retrograde-embed-history --slot N --execute``.
    """

    from nexus.agents.orrery.retrograde_embedding import (
        embed_retrograde_summaries,
    )

    _, retrieval_settings = _require_retrograde_settings(settings)
    pending_summary_ids = [
        int(summary_id)
        for summary_id in manifest.get("retrieval", {}).get(
            "embedding_pending_summary_ids", []
        )
    ]
    if not retrieval_settings.embed_after_apply or not pending_summary_ids:
        return []
    _emit(progress, "embedding", {"pending_summaries": len(pending_summary_ids)})
    return embed_retrograde_summaries(dbname, pending_summary_ids)


def build_wizard_history_surface(
    *,
    bundle: RetrogradeGenerationBundle,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Project the manifest into the Decision 6 visible/hidden split.

    Visible: the woven entity roster (first-class starting entities the
    expansion touched plus any minimum-viable stubs it introduced) and the
    intentional relationship edges. Hidden: event prose, tag bestowals, and
    deferred seeds -- returned as counts only so the long tail can ambush the
    player later in play.
    """

    counters = dict(manifest["counters"])
    entities = [
        {
            "name": row["entity_ref"],
            "kind": row["entity_kind"],
            "status": row["status"],
        }
        for row in manifest["entity_stub_rows"]
    ]
    relationships = [
        {
            "subject": row["subject_ref"],
            "object": row["object_ref"],
            "relationship_type": row["relationship_type"],
        }
        for row in manifest["relationship_rows"]
        if row["status"] in {"inserted", "already_present", "would_insert"}
    ]
    thread_statuses = [
        str(thread["status"]) for thread in manifest.get("thread_plan", [])
    ]
    hidden_counts = {
        "world_events": counters.get("events_inserted", 0)
        + counters.get("events_already_present", 0)
        + counters.get("events_would_insert", 0),
        "entity_tags": counters.get("entity_tags_inserted", 0)
        + counters.get("entity_tags_already_present", 0)
        + counters.get("entity_tags_would_insert", 0),
        "pair_tags": counters.get("pair_tags_inserted", 0)
        + counters.get("pair_tags_already_present", 0)
        + counters.get("pair_tags_would_insert", 0),
        "woven_seeds": sum(1 for status in thread_statuses if status == "woven"),
        "deferred_seeds": sum(1 for status in thread_statuses if status == "deferred"),
        "rejected_seeds": sum(1 for status in thread_statuses if status == "rejected"),
    }
    return {
        "weird_level": bundle.weird.get("level"),
        "visible": {
            "entities": entities,
            "relationships": relationships,
        },
        "hidden_counts": hidden_counts,
    }


def _require_retrograde_settings(
    settings: Settings,
) -> tuple[OrreryRetrogradeWizardSettings, OrreryRetrogradeRetrievalSettings]:
    """Return wizard/retrieval Retrograde settings or fail loudly."""

    if settings.orrery is None:
        raise ValueError(
            "nexus.toml is missing the [orrery] section required for "
            "Retrograde orchestration"
        )
    retrograde = settings.orrery.retrograde
    return retrograde.wizard, retrograde.retrieval


def _emit(
    progress: Optional[ProgressCallback],
    stage: str,
    detail: dict[str, Any],
) -> None:
    """Send one stage transition to the optional progress callback."""

    logger.info("Retrograde stage: %s %s", stage, detail)
    if progress is not None:
        progress(stage, detail)
