"""Canonical Orrery event writer.

The resolver is allowed to compute proposals during preview. This module is the
only place that materializes those proposals into canonical Orrery tables.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from hashlib import sha256
from datetime import timedelta
import json
from typing import Any, Mapping, Optional

from nexus.agents.orrery.needs import (
    NeedTuning,
    coerce_need_tuning,
    need_applies_to_tags,
    normalize_need_type,
    severity_tag_for_debt,
    severity_tags_for_need,
)
from nexus.agents.orrery.resolver import (
    LOCATION_CLASS_TAG_CATEGORIES,
    OrreryResolutionDraft,
    OrreryTickProposal,
)
from nexus.agents.orrery.routing import (
    DEFAULT_ROUTE_GRAPH_MAX_EDGES_PER_QUERY,
    ROUTE_GRAPH_MODES,
    RouteGraphEdge,
    shortest_route,
)
from nexus.agents.orrery.substrate import SUPPORTED_TRAVEL_PURPOSES


ENTITY_BINDING_SLOTS = frozenset({"actor", "target", "targets", "faction"})
SUPPORTED_STATE_DELTA_KEYS = frozenset(
    {
        "character.current_activity",
        "entity_tags.add",
        "entity_tags.remove",
        "entity_tags_target.add",
        "entity_tags_target.remove",
        "entity_pair_tags.add_outbound",
        "entity_pair_tags_target.clear_inbound",
        "need.fulfill",
        "travel.start",
        "travel.advance",
        "travel.arrive",
        "travel.delay",
    }
)
ADJUDICATION_ACTIONS = frozenset({"defer", "replace", "void"})
ADJUDICATION_SOURCES = frozenset({"explicit", "structured_state_update"})
REPLACEMENT_STATE_DELTA_ALIASES = {
    "character_current_activity": "character.current_activity",
    "entity_tags_add": "entity_tags.add",
    "entity_tags_remove": "entity_tags.remove",
    "entity_tags_target_add": "entity_tags_target.add",
    "entity_tags_target_remove": "entity_tags_target.remove",
    "entity_pair_tags_add_outbound": "entity_pair_tags.add_outbound",
    "entity_pair_tags_target_clear_inbound": ("entity_pair_tags_target.clear_inbound"),
}


@dataclass(frozen=True)
class SignalDetection:
    """Deterministic detection policy for branch signal emissions.

    A branch's signal_event_type only lands as a world_events row (and so
    only feeds other packages' gates) when a hash roll over (template,
    actor, target, tick, event type) clears the configured percent. The
    default policy detects everything — filtering is opt-in via
    [orrery.ecology] in nexus.toml.
    """

    default_pct: int = 100
    rates: Mapping[str, int] = field(default_factory=dict)

    def outcome(
        self,
        *,
        template_id: str,
        actor_entity_id: Optional[int],
        target_entity_id: Optional[int],
        tick_chunk_id: int,
        event_type: str,
    ) -> dict[str, Any]:
        threshold = int(self.rates.get(event_type, self.default_pct))
        material = (
            f"{template_id}:{actor_entity_id}:{target_entity_id}"
            f":{tick_chunk_id}:{event_type}"
        )
        roll = int(sha256(material.encode("utf-8")).hexdigest(), 16) % 100
        return {
            "event_type": event_type,
            "roll": roll,
            "threshold": threshold,
            "detected": roll < threshold,
        }


def coerce_signal_detection(raw: Any) -> SignalDetection:
    """[orrery.ecology] settings payload -> SignalDetection policy."""

    if raw is None:
        return SignalDetection()
    if hasattr(raw, "signal_detection_default"):
        return SignalDetection(
            default_pct=int(raw.signal_detection_default),
            rates=dict(raw.signal_detection),
        )
    if isinstance(raw, Mapping):
        return SignalDetection(
            default_pct=int(raw.get("signal_detection_default", 100)),
            rates=dict(raw.get("signal_detection") or {}),
        )
    raise ValueError(f"Unsupported orrery ecology settings: {type(raw)!r}")


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
ROUTE_GRAPH_DEFAULT_KEY = "default"


@dataclass(frozen=True, slots=True)
class CommitOrreryTickResult:
    """Summary of a canonical Orrery commit."""

    resolution_count: int = 0
    event_count: int = 0
    tag_mutation_count: int = 0
    cleared_tag_count: int = 0
    skipped_existing_count: int = 0
    adjudication_count: int = 0
    deferred_count: int = 0
    voided_count: int = 0
    replaced_count: int = 0
    scene_pressure_count: int = 0
    prompt_exposure_count: int = 0


def _coerce_prompt_limits(prompt_settings: Any) -> tuple[int, int]:
    """Resolve the storyteller render caps for prompt-exposure logging.

    Accepts the [orrery.prompt] mapping (or the Pydantic model); ``None``
    resolves to the model defaults. Must agree with the render slice in
    nexus/agents/lore/logon_utility.py or the recorded shown set lies.
    """

    from nexus.config.settings_models import OrreryPromptSettings

    if prompt_settings is None:
        prompt_settings = OrreryPromptSettings()
    if isinstance(prompt_settings, OrreryPromptSettings):
        return (
            prompt_settings.max_rendered_proposals,
            prompt_settings.max_rendered_pressures,
        )
    return (
        int(prompt_settings["max_rendered_proposals"]),
        int(prompt_settings["max_rendered_pressures"]),
    )


@dataclass(frozen=True, slots=True)
class OrreryAdjudicationDecision:
    """Skald's structured ruling for one Orrery proposal."""

    proposal_id: str
    action: str
    note: Optional[str] = None
    replacement_state_delta: Optional[Mapping[str, Any]] = None
    replacement_event_type: Optional[str] = None


@dataclass(frozen=True, slots=True)
class StateUpdateIndex:
    """Structured Storyteller state writes indexed by Orrery entity id."""

    character_fields_by_entity: Mapping[int, frozenset[str]]


@dataclass(frozen=True, slots=True)
class AdjudicatedDraft:
    """Pure adjudication result before sync/async commit writes diverge."""

    adjudication: Optional[OrreryAdjudicationDecision]
    adjudication_source: str
    draft_to_commit: Optional[OrreryResolutionDraft]
    brief: str


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


def coerce_adjudications(adjudications: Any) -> dict[str, OrreryAdjudicationDecision]:
    """Coerce Skald adjudications into a proposal-id keyed mapping."""

    if adjudications is None:
        return {}
    if isinstance(adjudications, str):
        adjudications = json.loads(adjudications)
    if hasattr(adjudications, "model_dump"):
        adjudications = adjudications.model_dump(mode="json", exclude_none=True)
    if isinstance(adjudications, Mapping):
        if "orrery_adjudications" in adjudications:
            adjudications = adjudications["orrery_adjudications"]
        elif "adjudications" in adjudications:
            adjudications = adjudications["adjudications"]
        else:
            raise TypeError("Orrery adjudications must be a list")
    if not isinstance(adjudications, Iterable) or isinstance(
        adjudications, (str, bytes)
    ):
        raise TypeError(
            "Orrery adjudications must be a list of structured adjudication objects"
        )

    coerced: dict[str, OrreryAdjudicationDecision] = {}
    for item in adjudications:
        adjudication = _coerce_adjudication(item)
        if adjudication.proposal_id in coerced:
            raise ValueError(
                f"Duplicate Orrery adjudication for {adjudication.proposal_id!r}"
            )
        coerced[adjudication.proposal_id] = adjudication
    return coerced


def _coerce_adjudication(item: Any) -> OrreryAdjudicationDecision:
    if hasattr(item, "model_dump"):
        item = item.model_dump(mode="json", exclude_none=True)
    if not isinstance(item, Mapping):
        raise TypeError("Orrery adjudication entries must be objects")

    proposal_id = str(item.get("proposal_id") or "").strip()
    if not proposal_id:
        raise ValueError("Orrery adjudication is missing proposal_id")
    action = str(item.get("action") or "").strip()
    if action not in ADJUDICATION_ACTIONS:
        raise ValueError(
            "Orrery adjudication action must be one of "
            f"{', '.join(sorted(ADJUDICATION_ACTIONS))}"
        )

    note = item.get("note")
    replacement_state_delta = _normalize_replacement_state_delta(
        item.get("replacement_state_delta")
    )
    replacement_event_type = item.get("replacement_event_type")
    return OrreryAdjudicationDecision(
        proposal_id=proposal_id,
        action=action,
        note=str(note).strip() if note else None,
        replacement_state_delta=replacement_state_delta or None,
        replacement_event_type=(
            str(replacement_event_type).strip() if replacement_event_type else None
        ),
    )


def _normalize_replacement_state_delta(raw: Any) -> dict[str, Any]:
    """Map Skald-facing replacement delta field names to canonical Orrery keys."""

    if raw is None:
        return {}
    if isinstance(raw, str):
        raw = json.loads(raw)
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump(mode="json", exclude_none=True)
    if not isinstance(raw, Mapping):
        raise TypeError("replacement_state_delta must be an object")

    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        if value is None or value == [] or value == {}:
            continue
        canonical_key = REPLACEMENT_STATE_DELTA_ALIASES.get(str(key), str(key))
        if canonical_key not in SUPPORTED_STATE_DELTA_KEYS:
            raise ValueError(f"Unsupported Orrery replacement_state_delta key: {key!r}")
        normalized[canonical_key] = value
    return normalized


def commit_orrery_tick_sync(
    conn: Any,
    proposal: Any,
    *,
    tick_chunk_id: int,
    slot: Optional[int] = None,
    world_layer: Optional[str] = "primary",
    sunhelm_settings: Optional[Any] = None,
    adjudications: Any = None,
    storyteller_state_updates: Any = None,
    prompt_settings: Optional[Any] = None,
    ecology_settings: Optional[Any] = None,
) -> CommitOrreryTickResult:
    """Materialize a preview proposal inside the accepted-chunk transaction."""

    signal_detection = coerce_signal_detection(ecology_settings)
    coerced = coerce_proposal(proposal)
    has_resolutions = coerced is not None and bool(coerced.resolutions)
    if has_resolutions:
        adjudication_map = coerce_adjudications(adjudications)
        need_tuning = coerce_need_tuning(sunhelm_settings)
        _validate_proposal(coerced)
        _validate_adjudications(coerced, adjudication_map)
    else:
        adjudication_map = {}

    with conn.cursor() as cur:
        expired_tag_count = _sweep_expired_entity_tags_sync(
            cur,
            source_chunk_id=tick_chunk_id,
        )
        # Pressures and exposures persist even on resolution-free ticks —
        # a tick can carry scene pressure with zero off-screen resolutions.
        scene_pressure_count = 0
        prompt_exposure_count = 0
        if coerced is not None:
            max_proposals, max_pressures = _coerce_prompt_limits(prompt_settings)
            scene_pressure_count = _insert_scene_pressures_sync(
                cur, coerced, tick_chunk_id=tick_chunk_id
            )
            prompt_exposure_count = _insert_prompt_exposures_sync(
                cur,
                coerced,
                tick_chunk_id=tick_chunk_id,
                max_proposals=max_proposals,
                max_pressures=max_pressures,
            )
        if not has_resolutions:
            return CommitOrreryTickResult(
                cleared_tag_count=expired_tag_count,
                scene_pressure_count=scene_pressure_count,
                prompt_exposure_count=prompt_exposure_count,
            )

        assert coerced is not None
        entity_ids = _entity_ids_from_proposal(coerced)
        _validate_entity_ids_sync(cur, entity_ids)
        entity_names = _entity_names_sync(cur, entity_ids)
        state_update_index = _state_update_index_sync(cur, storyteller_state_updates)

        resolution_count = 0
        event_count = 0
        tag_mutation_count = 0
        cleared_tag_count = expired_tag_count
        skipped_existing_count = 0
        adjudication_count = 0
        deferred_count = 0
        voided_count = 0
        replaced_count = 0

        for draft in coerced.resolutions:
            adjudicated = _adjudicate_draft(
                draft,
                adjudication_map,
                state_update_index,
                entity_names,
            )
            actor_entity_id = _scalar_entity_binding(draft.bindings, "actor")
            target_entity_id = _scalar_entity_binding(draft.bindings, "target")

            if adjudicated.adjudication is not None:
                adjudication_count += 1
                if adjudicated.adjudication.action == "defer":
                    deferred_count += 1
                    _insert_adjudication_log_sync(
                        cur,
                        draft,
                        adjudicated.adjudication,
                        tick_chunk_id=tick_chunk_id,
                        adjudication_source=adjudicated.adjudication_source,
                    )
                    continue
                if adjudicated.adjudication.action == "void":
                    voided_count += 1
                    _insert_adjudication_log_sync(
                        cur,
                        draft,
                        adjudicated.adjudication,
                        tick_chunk_id=tick_chunk_id,
                        adjudication_source=adjudicated.adjudication_source,
                    )
                    continue
                if (
                    adjudicated.adjudication.action == "replace"
                    and adjudicated.draft_to_commit is None
                ):
                    replaced_count += 1
                    _insert_adjudication_log_sync(
                        cur,
                        draft,
                        adjudicated.adjudication,
                        tick_chunk_id=tick_chunk_id,
                        adjudication_source=adjudicated.adjudication_source,
                    )
                    continue

            if adjudicated.draft_to_commit is None:
                raise RuntimeError("Orrery adjudication produced no draft to commit")

            resolution_id = _insert_resolution_sync(
                cur,
                adjudicated.draft_to_commit,
                tick_chunk_id=tick_chunk_id,
                actor_entity_id=actor_entity_id,
                brief=adjudicated.brief,
            )
            if resolution_id is None:
                skipped_existing_count += 1
                # A replace-with-delta ruling must reach the history log even
                # when the resolution row already exists (idempotent
                # re-commit): resolve the existing id instead of silently
                # dropping the ruling. The log has no unique key, so guard
                # against duplicate rows on repeated re-commits.
                if (
                    adjudicated.adjudication is not None
                    and not _replace_already_logged_sync(
                        cur, draft, tick_chunk_id=tick_chunk_id
                    )
                ):
                    if adjudicated.adjudication.action == "replace":
                        replaced_count += 1
                    _insert_adjudication_log_sync(
                        cur,
                        draft,
                        adjudicated.adjudication,
                        tick_chunk_id=tick_chunk_id,
                        adjudication_source=adjudicated.adjudication_source,
                        applied_resolution_id=_existing_resolution_id_sync(
                            cur, draft, tick_chunk_id=tick_chunk_id
                        ),
                    )
                continue

            if adjudicated.adjudication is not None:
                if adjudicated.adjudication.action == "replace":
                    replaced_count += 1
                _insert_adjudication_log_sync(
                    cur,
                    draft,
                    adjudicated.adjudication,
                    tick_chunk_id=tick_chunk_id,
                    adjudication_source=adjudicated.adjudication_source,
                    applied_resolution_id=resolution_id,
                )

            resolution_count += 1
            tag_mutation_count += _apply_state_delta_sync(
                cur,
                adjudicated.draft_to_commit,
                actor_entity_id=actor_entity_id,
                target_entity_id=target_entity_id,
                source_chunk_id=tick_chunk_id,
                need_tuning=need_tuning,
            )
            event_id = _emit_world_event_sync(
                cur,
                adjudicated.draft_to_commit,
                tick_chunk_id=tick_chunk_id,
                resolution_id=resolution_id,
                actor_entity_id=actor_entity_id,
                target_entity_id=target_entity_id,
                world_layer=world_layer,
                signal_detection=signal_detection,
            )
            if event_id is not None:
                event_count += 1
                _update_resolution_events_sync(cur, resolution_id, [event_id])
                if actor_entity_id is not None:
                    cleared_tag_count += _clear_event_tags_sync(
                        cur,
                        entity_id=actor_entity_id,
                        event_type=str(adjudicated.draft_to_commit.event_type),
                        triggering_event_id=event_id,
                        source_chunk_id=tick_chunk_id,
                    )

    return CommitOrreryTickResult(
        resolution_count=resolution_count,
        event_count=event_count,
        tag_mutation_count=tag_mutation_count,
        cleared_tag_count=cleared_tag_count,
        skipped_existing_count=skipped_existing_count,
        adjudication_count=adjudication_count,
        deferred_count=deferred_count,
        voided_count=voided_count,
        replaced_count=replaced_count,
        scene_pressure_count=scene_pressure_count,
        prompt_exposure_count=prompt_exposure_count,
    )


async def commit_orrery_tick_async(
    conn: Any,
    proposal: Any,
    *,
    tick_chunk_id: int,
    slot: Optional[int] = None,
    world_layer: Optional[str] = "primary",
    sunhelm_settings: Optional[Any] = None,
    adjudications: Any = None,
    storyteller_state_updates: Any = None,
    prompt_settings: Optional[Any] = None,
    ecology_settings: Optional[Any] = None,
) -> CommitOrreryTickResult:
    """Async parity wrapper for tests and non-production commit callers."""

    signal_detection = coerce_signal_detection(ecology_settings)
    coerced = coerce_proposal(proposal)
    has_resolutions = coerced is not None and bool(coerced.resolutions)
    if has_resolutions:
        adjudication_map = coerce_adjudications(adjudications)
        need_tuning = coerce_need_tuning(sunhelm_settings)
        _validate_proposal(coerced)
        _validate_adjudications(coerced, adjudication_map)
    else:
        adjudication_map = {}

    expired_tag_count = await _sweep_expired_entity_tags_async(
        conn,
        source_chunk_id=tick_chunk_id,
    )
    # Pressures and exposures persist even on resolution-free ticks — a tick
    # can carry scene pressure with zero off-screen resolutions.
    scene_pressure_count = 0
    prompt_exposure_count = 0
    if coerced is not None:
        max_proposals, max_pressures = _coerce_prompt_limits(prompt_settings)
        scene_pressure_count = await _insert_scene_pressures_async(
            conn, coerced, tick_chunk_id=tick_chunk_id
        )
        prompt_exposure_count = await _insert_prompt_exposures_async(
            conn,
            coerced,
            tick_chunk_id=tick_chunk_id,
            max_proposals=max_proposals,
            max_pressures=max_pressures,
        )
    if not has_resolutions:
        return CommitOrreryTickResult(
            cleared_tag_count=expired_tag_count,
            scene_pressure_count=scene_pressure_count,
            prompt_exposure_count=prompt_exposure_count,
        )

    assert coerced is not None
    entity_ids = _entity_ids_from_proposal(coerced)
    await _validate_entity_ids_async(conn, entity_ids)
    entity_names = await _entity_names_async(conn, entity_ids)
    state_update_index = await _state_update_index_async(
        conn, storyteller_state_updates
    )

    resolution_count = 0
    event_count = 0
    tag_mutation_count = 0
    cleared_tag_count = expired_tag_count
    skipped_existing_count = 0
    adjudication_count = 0
    deferred_count = 0
    voided_count = 0
    replaced_count = 0

    for draft in coerced.resolutions:
        adjudicated = _adjudicate_draft(
            draft,
            adjudication_map,
            state_update_index,
            entity_names,
        )
        actor_entity_id = _scalar_entity_binding(draft.bindings, "actor")
        target_entity_id = _scalar_entity_binding(draft.bindings, "target")

        if adjudicated.adjudication is not None:
            adjudication_count += 1
            if adjudicated.adjudication.action == "defer":
                deferred_count += 1
                await _insert_adjudication_log_async(
                    conn,
                    draft,
                    adjudicated.adjudication,
                    tick_chunk_id=tick_chunk_id,
                    adjudication_source=adjudicated.adjudication_source,
                )
                continue
            if adjudicated.adjudication.action == "void":
                voided_count += 1
                await _insert_adjudication_log_async(
                    conn,
                    draft,
                    adjudicated.adjudication,
                    tick_chunk_id=tick_chunk_id,
                    adjudication_source=adjudicated.adjudication_source,
                )
                continue
            if (
                adjudicated.adjudication.action == "replace"
                and adjudicated.draft_to_commit is None
            ):
                replaced_count += 1
                await _insert_adjudication_log_async(
                    conn,
                    draft,
                    adjudicated.adjudication,
                    tick_chunk_id=tick_chunk_id,
                    adjudication_source=adjudicated.adjudication_source,
                )
                continue

        if adjudicated.draft_to_commit is None:
            raise RuntimeError("Orrery adjudication produced no draft to commit")

        resolution_id = await _insert_resolution_async(
            conn,
            adjudicated.draft_to_commit,
            tick_chunk_id=tick_chunk_id,
            actor_entity_id=actor_entity_id,
            brief=adjudicated.brief,
        )
        if resolution_id is None:
            skipped_existing_count += 1
            # Same idempotent-re-commit guarantee as the sync twin: the
            # replace ruling reaches the log with the existing resolution id,
            # guarded against duplicate rows on repeated re-commits.
            if (
                adjudicated.adjudication is not None
                and not await _replace_already_logged_async(
                    conn, draft, tick_chunk_id=tick_chunk_id
                )
            ):
                if adjudicated.adjudication.action == "replace":
                    replaced_count += 1
                await _insert_adjudication_log_async(
                    conn,
                    draft,
                    adjudicated.adjudication,
                    tick_chunk_id=tick_chunk_id,
                    adjudication_source=adjudicated.adjudication_source,
                    applied_resolution_id=await _existing_resolution_id_async(
                        conn, draft, tick_chunk_id=tick_chunk_id
                    ),
                )
            continue

        if adjudicated.adjudication is not None:
            if adjudicated.adjudication.action == "replace":
                replaced_count += 1
            await _insert_adjudication_log_async(
                conn,
                draft,
                adjudicated.adjudication,
                tick_chunk_id=tick_chunk_id,
                adjudication_source=adjudicated.adjudication_source,
                applied_resolution_id=resolution_id,
            )

        resolution_count += 1
        tag_mutation_count += await _apply_state_delta_async(
            conn,
            adjudicated.draft_to_commit,
            actor_entity_id=actor_entity_id,
            target_entity_id=target_entity_id,
            source_chunk_id=tick_chunk_id,
            need_tuning=need_tuning,
        )
        event_id = await _emit_world_event_async(
            conn,
            adjudicated.draft_to_commit,
            tick_chunk_id=tick_chunk_id,
            resolution_id=resolution_id,
            actor_entity_id=actor_entity_id,
            target_entity_id=target_entity_id,
            world_layer=world_layer,
            signal_detection=signal_detection,
        )
        if event_id is not None:
            event_count += 1
            await _update_resolution_events_async(conn, resolution_id, [event_id])
            if actor_entity_id is not None:
                cleared_tag_count += await _clear_event_tags_async(
                    conn,
                    entity_id=actor_entity_id,
                    event_type=str(adjudicated.draft_to_commit.event_type),
                    triggering_event_id=event_id,
                    source_chunk_id=tick_chunk_id,
                )

    return CommitOrreryTickResult(
        resolution_count=resolution_count,
        event_count=event_count,
        tag_mutation_count=tag_mutation_count,
        cleared_tag_count=cleared_tag_count,
        skipped_existing_count=skipped_existing_count,
        adjudication_count=adjudication_count,
        deferred_count=deferred_count,
        voided_count=voided_count,
        replaced_count=replaced_count,
        scene_pressure_count=scene_pressure_count,
        prompt_exposure_count=prompt_exposure_count,
    )


def _validate_proposal(proposal: OrreryTickProposal) -> None:
    for draft in proposal.resolutions:
        unsupported = set(draft.state_delta) - SUPPORTED_STATE_DELTA_KEYS
        if unsupported:
            raise ValueError(
                "Unsupported Orrery state_delta keys for "
                f"{draft.template_id}: {', '.join(sorted(unsupported))}"
            )


def _validate_adjudications(
    proposal: OrreryTickProposal,
    adjudications: Mapping[str, OrreryAdjudicationDecision],
) -> None:
    proposal_ids = {draft.proposal_id for draft in proposal.resolutions}
    unknown = set(adjudications) - proposal_ids
    if unknown:
        raise ValueError(
            "Orrery adjudication references unknown proposal_id(s): "
            + ", ".join(sorted(unknown))
        )


def _adjudicate_draft(
    draft: OrreryResolutionDraft,
    adjudication_map: Mapping[str, OrreryAdjudicationDecision],
    state_update_index: StateUpdateIndex,
    entity_names: Mapping[int, str],
) -> AdjudicatedDraft:
    """Resolve Skald's authority decision without performing database writes."""

    adjudication = adjudication_map.get(draft.proposal_id)
    adjudication_source = "explicit"
    if adjudication is None and _replaced_by_storyteller_state(
        draft, state_update_index
    ):
        adjudication = OrreryAdjudicationDecision(
            proposal_id=draft.proposal_id,
            action="replace",
            note=(
                "Storyteller state_updates touched the same "
                "character field; skipped the original Orrery delta."
            ),
        )
        adjudication_source = "structured_state_update"

    brief = _render_brief(draft, entity_names)
    if adjudication is None:
        return AdjudicatedDraft(
            adjudication=None,
            adjudication_source=adjudication_source,
            draft_to_commit=draft,
            brief=brief,
        )
    if adjudication.action in {"defer", "void"}:
        return AdjudicatedDraft(
            adjudication=adjudication,
            adjudication_source=adjudication_source,
            draft_to_commit=None,
            brief=brief,
        )
    if adjudication.action == "replace":
        if not adjudication.replacement_state_delta:
            return AdjudicatedDraft(
                adjudication=adjudication,
                adjudication_source=adjudication_source,
                draft_to_commit=None,
                brief=brief,
            )
        draft_to_commit = replace(
            draft,
            state_delta=dict(adjudication.replacement_state_delta),
            changed_fields=tuple(adjudication.replacement_state_delta.keys()),
            event_type=adjudication.replacement_event_type,
        )
        return AdjudicatedDraft(
            adjudication=adjudication,
            adjudication_source=adjudication_source,
            draft_to_commit=draft_to_commit,
            brief=adjudication.note or _render_brief(draft_to_commit, entity_names),
        )
    raise ValueError(f"Unsupported Orrery adjudication action {adjudication.action!r}")


def _coerce_state_updates_payload(raw: Any) -> Mapping[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        raw = json.loads(raw)
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump(mode="json", exclude_none=True)
    if isinstance(raw, Mapping):
        return raw
    raise TypeError("Storyteller state_updates must be a structured object")


def _character_state_touches(raw: Any) -> dict[int, set[str]]:
    payload = _coerce_state_updates_payload(raw)
    touches: dict[int, set[str]] = {}
    for item in payload.get("characters") or ():
        if hasattr(item, "model_dump"):
            item = item.model_dump(mode="json", exclude_none=True)
        if not isinstance(item, Mapping) or not item.get("character_id"):
            continue
        character_id = _coerce_int(item["character_id"], label="character_id")
        fields = touches.setdefault(character_id, set())
        if item.get("current_activity"):
            fields.add("current_activity")
        if item.get("current_location"):
            fields.add("current_location")
    return touches


def _state_update_index_sync(cur: Any, raw_state_updates: Any) -> StateUpdateIndex:
    touches_by_character_id = _character_state_touches(raw_state_updates)
    if not touches_by_character_id:
        return StateUpdateIndex(character_fields_by_entity={})

    cur.execute(
        "SELECT id, entity_id FROM characters WHERE id = ANY(%s)",
        (sorted(touches_by_character_id),),
    )
    character_to_entity = {
        _row_get(row, "id", 0): _row_get(row, "entity_id", 1) for row in cur.fetchall()
    }
    touches_by_entity: dict[int, frozenset[str]] = {}
    for character_id, fields in touches_by_character_id.items():
        entity_id = character_to_entity.get(character_id)
        if entity_id is not None:
            touches_by_entity[int(entity_id)] = frozenset(fields)
    return StateUpdateIndex(character_fields_by_entity=touches_by_entity)


async def _state_update_index_async(
    conn: Any, raw_state_updates: Any
) -> StateUpdateIndex:
    touches_by_character_id = _character_state_touches(raw_state_updates)
    if not touches_by_character_id:
        return StateUpdateIndex(character_fields_by_entity={})

    rows = await conn.fetch(
        "SELECT id, entity_id FROM characters WHERE id = ANY($1::bigint[])",
        sorted(touches_by_character_id),
    )
    character_to_entity = {
        _row_get(row, "id", 0): _row_get(row, "entity_id", 1) for row in rows
    }
    touches_by_entity: dict[int, frozenset[str]] = {}
    for character_id, fields in touches_by_character_id.items():
        entity_id = character_to_entity.get(character_id)
        if entity_id is not None:
            touches_by_entity[int(entity_id)] = frozenset(fields)
    return StateUpdateIndex(character_fields_by_entity=touches_by_entity)


def _replaced_by_storyteller_state(
    draft: OrreryResolutionDraft,
    state_update_index: StateUpdateIndex,
) -> bool:
    actor_entity_id = _scalar_entity_binding(draft.bindings, "actor")
    if actor_entity_id is None:
        return False
    touched_fields = state_update_index.character_fields_by_entity.get(
        actor_entity_id, frozenset()
    )
    if not touched_fields:
        return False

    delta_keys = set(draft.state_delta)
    changed_fields = set(draft.changed_fields)
    touches_travel_state = any(key.startswith("travel.") for key in delta_keys) or any(
        field.startswith("character_travel_states.") for field in changed_fields
    )
    if "current_activity" in touched_fields and (
        "character.current_activity" in delta_keys
        or "character.current_activity" in changed_fields
    ):
        return True
    if "current_location" in touched_fields and (
        "character.current_location" in changed_fields or touches_travel_state
    ):
        return True
    return False


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


def _insert_adjudication_log_sync(
    cur: Any,
    draft: OrreryResolutionDraft,
    adjudication: OrreryAdjudicationDecision,
    *,
    tick_chunk_id: int,
    adjudication_source: str,
    applied_resolution_id: Optional[int] = None,
) -> None:
    if adjudication_source not in ADJUDICATION_SOURCES:
        raise ValueError(
            f"Unsupported Orrery adjudication source {adjudication_source!r}"
        )
    cur.execute(
        """
        INSERT INTO orrery_adjudication_log (
            tick_chunk_id, proposal_id, template_id, binding_hash, action,
            adjudication_source, skald_note, original_state_delta,
            replacement_state_delta, replacement_event_type,
            applied_resolution_id, actor_entity_id, bindings
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s,
                  %s, %s::jsonb)
        """,
        (
            tick_chunk_id,
            adjudication.proposal_id,
            draft.template_id,
            draft.binding_hash,
            adjudication.action,
            adjudication_source,
            adjudication.note,
            json.dumps(draft.state_delta),
            (
                json.dumps(adjudication.replacement_state_delta)
                if adjudication.replacement_state_delta
                else None
            ),
            adjudication.replacement_event_type,
            applied_resolution_id,
            _scalar_entity_binding(draft.bindings, "actor"),
            json.dumps(dict(draft.bindings)),
        ),
    )


async def _insert_adjudication_log_async(
    conn: Any,
    draft: OrreryResolutionDraft,
    adjudication: OrreryAdjudicationDecision,
    *,
    tick_chunk_id: int,
    adjudication_source: str,
    applied_resolution_id: Optional[int] = None,
) -> None:
    if adjudication_source not in ADJUDICATION_SOURCES:
        raise ValueError(
            f"Unsupported Orrery adjudication source {adjudication_source!r}"
        )
    await conn.execute(
        """
        INSERT INTO orrery_adjudication_log (
            tick_chunk_id, proposal_id, template_id, binding_hash, action,
            adjudication_source, skald_note, original_state_delta,
            replacement_state_delta, replacement_event_type,
            applied_resolution_id, actor_entity_id, bindings
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10, $11,
                  $12, $13::jsonb)
        """,
        tick_chunk_id,
        adjudication.proposal_id,
        draft.template_id,
        draft.binding_hash,
        adjudication.action,
        adjudication_source,
        adjudication.note,
        json.dumps(draft.state_delta),
        (
            json.dumps(adjudication.replacement_state_delta)
            if adjudication.replacement_state_delta
            else None
        ),
        adjudication.replacement_event_type,
        applied_resolution_id,
        _scalar_entity_binding(draft.bindings, "actor"),
        json.dumps(dict(draft.bindings)),
    )


def _replace_already_logged_sync(
    cur: Any,
    draft: OrreryResolutionDraft,
    *,
    tick_chunk_id: int,
) -> bool:
    cur.execute(
        """
        SELECT 1 FROM orrery_adjudication_log
        WHERE tick_chunk_id = %s AND proposal_id = %s AND action = 'replace'
        LIMIT 1
        """,
        (tick_chunk_id, draft.proposal_id),
    )
    return cur.fetchone() is not None


async def _replace_already_logged_async(
    conn: Any,
    draft: OrreryResolutionDraft,
    *,
    tick_chunk_id: int,
) -> bool:
    return (
        await conn.fetchval(
            """
            SELECT 1 FROM orrery_adjudication_log
            WHERE tick_chunk_id = $1 AND proposal_id = $2 AND action = 'replace'
            LIMIT 1
            """,
            tick_chunk_id,
            draft.proposal_id,
        )
        is not None
    )


def _existing_resolution_id_sync(
    cur: Any,
    draft: OrreryResolutionDraft,
    *,
    tick_chunk_id: int,
) -> Optional[int]:
    cur.execute(
        """
        SELECT id FROM orrery_resolutions
        WHERE tick_chunk_id = %s AND template_id = %s AND binding_hash = %s
        """,
        (tick_chunk_id, draft.template_id, draft.binding_hash),
    )
    row = cur.fetchone()
    if not row:
        return None
    return _row_get(row, "id", 0)


async def _existing_resolution_id_async(
    conn: Any,
    draft: OrreryResolutionDraft,
    *,
    tick_chunk_id: int,
) -> Optional[int]:
    return await conn.fetchval(
        """
        SELECT id FROM orrery_resolutions
        WHERE tick_chunk_id = $1 AND template_id = $2 AND binding_hash = $3
        """,
        tick_chunk_id,
        draft.template_id,
        draft.binding_hash,
    )


def _insert_scene_pressures_sync(cur: Any, proposal: Any, *, tick_chunk_id: int) -> int:
    count = 0
    for pressure in proposal.scene_pressures:
        cur.execute(
            """
            INSERT INTO orrery_scene_pressures (
                tick_chunk_id, template_id, binding_hash, actor_entity_id,
                target_entity_id, priority, magnitude, branch_label,
                pressure_stub, prompt_text, bindings
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (tick_chunk_id, template_id, binding_hash) DO NOTHING
            RETURNING id
            """,
            (
                tick_chunk_id,
                pressure.template_id,
                pressure.binding_hash,
                _scalar_entity_binding(pressure.bindings, "actor"),
                _scalar_entity_binding(pressure.bindings, "target"),
                pressure.priority,
                pressure.magnitude,
                pressure.branch_label,
                pressure.pressure_stub,
                pressure.prompt_text,
                json.dumps(dict(pressure.bindings)),
            ),
        )
        if cur.fetchone():
            count += 1
    return count


async def _insert_scene_pressures_async(
    conn: Any, proposal: Any, *, tick_chunk_id: int
) -> int:
    count = 0
    for pressure in proposal.scene_pressures:
        inserted = await conn.fetchval(
            """
            INSERT INTO orrery_scene_pressures (
                tick_chunk_id, template_id, binding_hash, actor_entity_id,
                target_entity_id, priority, magnitude, branch_label,
                pressure_stub, prompt_text, bindings
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb)
            ON CONFLICT (tick_chunk_id, template_id, binding_hash) DO NOTHING
            RETURNING id
            """,
            tick_chunk_id,
            pressure.template_id,
            pressure.binding_hash,
            _scalar_entity_binding(pressure.bindings, "actor"),
            _scalar_entity_binding(pressure.bindings, "target"),
            pressure.priority,
            pressure.magnitude,
            pressure.branch_label,
            pressure.pressure_stub,
            pressure.prompt_text,
            json.dumps(dict(pressure.bindings)),
        )
        if inserted is not None:
            count += 1
    return count


def _prompt_exposure_rows(
    proposal: Any, *, max_proposals: int, max_pressures: int
) -> list[tuple[str, str, str, int]]:
    """(kind, template_id, binding_hash, position) for the rendered slice.

    Mirrors the render slices in logon_utility's storyteller prompt: the
    first N proposals and first N pressures in proposal order.
    """

    rows: list[tuple[str, str, str, int]] = []
    for position, draft in enumerate(proposal.resolutions[:max_proposals]):
        rows.append(("resolution", draft.template_id, draft.binding_hash, position))
    for position, pressure in enumerate(proposal.scene_pressures[:max_pressures]):
        rows.append(
            ("scene_pressure", pressure.template_id, pressure.binding_hash, position)
        )
    return rows


def _insert_prompt_exposures_sync(
    cur: Any,
    proposal: Any,
    *,
    tick_chunk_id: int,
    max_proposals: int,
    max_pressures: int,
) -> int:
    count = 0
    for kind, template_id, binding_hash, position in _prompt_exposure_rows(
        proposal, max_proposals=max_proposals, max_pressures=max_pressures
    ):
        cur.execute(
            """
            INSERT INTO orrery_prompt_exposures (
                tick_chunk_id, kind, proposal_id, template_id, binding_hash,
                position
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (tick_chunk_id, kind, template_id, binding_hash)
                DO NOTHING
            RETURNING id
            """,
            (
                tick_chunk_id,
                kind,
                f"{template_id}:{binding_hash}",
                template_id,
                binding_hash,
                position,
            ),
        )
        if cur.fetchone():
            count += 1
    return count


async def _insert_prompt_exposures_async(
    conn: Any,
    proposal: Any,
    *,
    tick_chunk_id: int,
    max_proposals: int,
    max_pressures: int,
) -> int:
    count = 0
    for kind, template_id, binding_hash, position in _prompt_exposure_rows(
        proposal, max_proposals=max_proposals, max_pressures=max_pressures
    ):
        inserted = await conn.fetchval(
            """
            INSERT INTO orrery_prompt_exposures (
                tick_chunk_id, kind, proposal_id, template_id, binding_hash,
                position
            ) VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (tick_chunk_id, kind, template_id, binding_hash)
                DO NOTHING
            RETURNING id
            """,
            tick_chunk_id,
            kind,
            f"{template_id}:{binding_hash}",
            template_id,
            binding_hash,
            position,
        )
        if inserted is not None:
            count += 1
    return count


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
        if _add_entity_tag_sync(
            cur,
            actor_entity_id,
            str(tag),
            draft.template_id,
            source_chunk_id=source_chunk_id,
        ):
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

    target_tag_adds = draft.state_delta.get("entity_tags_target.add", ()) or ()
    target_tag_removes = draft.state_delta.get("entity_tags_target.remove", ()) or ()
    target_pair_tag_clears = (
        draft.state_delta.get("entity_pair_tags_target.clear_inbound", ()) or ()
    )
    if target_tag_adds or target_tag_removes or target_pair_tag_clears:
        if target_entity_id is None:
            raise ValueError(f"Orrery draft {draft.template_id} has no target binding")
        for tag in target_tag_adds:
            if _add_entity_tag_sync(
                cur,
                target_entity_id,
                str(tag),
                draft.template_id,
                source_chunk_id=source_chunk_id,
            ):
                tag_mutations += 1
        for tag in target_tag_removes:
            tag_mutations += _remove_entity_tag_sync(
                cur,
                target_entity_id,
                str(tag),
                draft.template_id,
                source_chunk_id=source_chunk_id,
                delta_key="entity_tags_target.remove",
            )
        for tag in target_pair_tag_clears:
            tag_mutations += _clear_inbound_pair_tags_sync(
                cur,
                object_entity_id=target_entity_id,
                tag=str(tag),
                template_id=draft.template_id,
                source_chunk_id=source_chunk_id,
            )
    outbound_pair_tag_adds = (
        draft.state_delta.get("entity_pair_tags.add_outbound", ()) or ()
    )
    if outbound_pair_tag_adds:
        if target_entity_id is None:
            raise ValueError(
                f"Orrery draft {draft.template_id} adds an outbound pair tag "
                "but has no target binding"
            )
        for tag in outbound_pair_tag_adds:
            if _add_outbound_pair_tag_sync(
                cur,
                subject_entity_id=actor_entity_id,
                object_entity_id=target_entity_id,
                tag=str(tag),
                template_id=draft.template_id,
                source_chunk_id=source_chunk_id,
            ):
                tag_mutations += 1
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
            conn,
            actor_entity_id,
            str(tag),
            draft.template_id,
            source_chunk_id=source_chunk_id,
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

    target_tag_adds = draft.state_delta.get("entity_tags_target.add", ()) or ()
    target_tag_removes = draft.state_delta.get("entity_tags_target.remove", ()) or ()
    target_pair_tag_clears = (
        draft.state_delta.get("entity_pair_tags_target.clear_inbound", ()) or ()
    )
    if target_tag_adds or target_tag_removes or target_pair_tag_clears:
        if target_entity_id is None:
            raise ValueError(f"Orrery draft {draft.template_id} has no target binding")
        for tag in target_tag_adds:
            if await _add_entity_tag_async(
                conn,
                target_entity_id,
                str(tag),
                draft.template_id,
                source_chunk_id=source_chunk_id,
            ):
                tag_mutations += 1
        for tag in target_tag_removes:
            tag_mutations += await _remove_entity_tag_async(
                conn,
                target_entity_id,
                str(tag),
                draft.template_id,
                source_chunk_id=source_chunk_id,
                delta_key="entity_tags_target.remove",
            )
        for tag in target_pair_tag_clears:
            tag_mutations += await _clear_inbound_pair_tags_async(
                conn,
                object_entity_id=target_entity_id,
                tag=str(tag),
                template_id=draft.template_id,
                source_chunk_id=source_chunk_id,
            )
    outbound_pair_tag_adds = (
        draft.state_delta.get("entity_pair_tags.add_outbound", ()) or ()
    )
    if outbound_pair_tag_adds:
        if target_entity_id is None:
            raise ValueError(
                f"Orrery draft {draft.template_id} adds an outbound pair tag "
                "but has no target binding"
            )
        for tag in outbound_pair_tag_adds:
            if await _add_outbound_pair_tag_async(
                conn,
                subject_entity_id=actor_entity_id,
                object_entity_id=target_entity_id,
                tag=str(tag),
                template_id=draft.template_id,
                source_chunk_id=source_chunk_id,
            ):
                tag_mutations += 1
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


def _destination_place_classes(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Return class-based destination selectors from a travel payload."""

    raw = (
        payload.get("destination_place_classes")
        or payload.get("destination_place_class")
        or payload.get("destination_class")
    )
    if raw is None:
        return ()
    if isinstance(raw, str):
        values = (raw,)
    elif isinstance(raw, (list, tuple)):
        values = tuple(raw)
    else:
        raise ValueError("destination place classes must be a string, list, or tuple")
    classes = tuple(dict.fromkeys(str(item) for item in values if str(item)))
    if not classes:
        raise ValueError("destination place classes cannot be empty")
    return classes


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


def _travel_intent_metadata(payload: Mapping[str, Any]) -> dict[str, str]:
    """Return normalized route-intent metadata from authored travel payloads.

    ``purpose`` identifies the behavioral route purpose that travel packages can
    branch on. ``purpose_need`` optionally names the underlying need pressure
    that caused the travel; it can diverge from purpose when one behavior is a
    means to satisfy another need.
    """

    metadata: dict[str, str] = {}
    purpose = payload.get("purpose") or payload.get("travel_purpose")
    if purpose:
        normalized_purpose = str(purpose).strip().lower()
        if normalized_purpose not in SUPPORTED_TRAVEL_PURPOSES:
            raise ValueError(f"Unsupported Orrery travel purpose: {purpose!r}")
        metadata["purpose"] = normalized_purpose
    purpose_need = payload.get("purpose_need")
    if purpose_need:
        metadata["purpose_need"] = normalize_need_type(str(purpose_need).strip())
    return metadata


def _route_graph_key(payload: Mapping[str, Any]) -> str:
    """Return the local route graph namespace requested by this travel effect."""

    return str(
        payload.get("route_graph")
        or payload.get("graph_key")
        or ROUTE_GRAPH_DEFAULT_KEY
    )


def _route_graph_max_edges_per_query() -> int:
    """Return the configured fail-fast cap for in-process graph routing."""

    from nexus.config import load_settings

    settings = load_settings()
    if settings.orrery is None:
        return DEFAULT_ROUTE_GRAPH_MAX_EDGES_PER_QUERY
    return int(settings.orrery.route_graph.max_edges_per_query)


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
    route_graph_key = _route_graph_key(data)
    world_time = _tick_world_time_sync(cur, source_chunk_id)
    origin_place_id = data.get("origin_place_id") or _actor_location_sync(
        cur, actor_entity_id
    )
    destination_place_id = data.get("destination_place_id")
    if destination_place_id is None:
        destination_anchor = data.get("destination_anchor")
        if destination_anchor is not None:
            destination_place_id = _routine_anchor_destination_sync(
                cur,
                actor_entity_id=actor_entity_id,
                anchor_type=str(destination_anchor),
            )
        else:
            destination_classes = _destination_place_classes(data)
            if destination_classes and origin_place_id is not None:
                destination_place_id = _location_class_destination_sync(
                    cur,
                    origin_place_id=int(origin_place_id),
                    location_classes=destination_classes,
                )
            else:
                destination_place_id = _planned_destination_sync(cur, actor_entity_id)
    if origin_place_id is None or destination_place_id is None:
        raise ValueError("travel.start requires origin and destination places")

    route = _select_route_sync(
        cur,
        origin_place_id=int(origin_place_id),
        destination_place_id=int(destination_place_id),
        mode=mode,
        risk=risk,
        route_graph_key=route_graph_key,
    )
    eta = _eta(world_time, route["duration_minutes"])
    progress = float(data.get("initial_progress", 0.0))
    route_metadata = dict(route["metadata"])
    route_metadata.update(_travel_intent_metadata(data))
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
            json.dumps(route_metadata),
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
    route_graph_key = _route_graph_key(data)
    world_time = await _tick_world_time_async(conn, source_chunk_id)
    origin_place_id = data.get("origin_place_id") or await _actor_location_async(
        conn, actor_entity_id
    )
    destination_place_id = data.get("destination_place_id")
    if destination_place_id is None:
        destination_anchor = data.get("destination_anchor")
        if destination_anchor is not None:
            destination_place_id = await _routine_anchor_destination_async(
                conn,
                actor_entity_id=actor_entity_id,
                anchor_type=str(destination_anchor),
            )
        else:
            destination_classes = _destination_place_classes(data)
            if destination_classes and origin_place_id is not None:
                destination_place_id = await _location_class_destination_async(
                    conn,
                    origin_place_id=int(origin_place_id),
                    location_classes=destination_classes,
                )
            else:
                destination_place_id = await _planned_destination_async(
                    conn, actor_entity_id
                )
    if origin_place_id is None or destination_place_id is None:
        raise ValueError("travel.start requires origin and destination places")

    route = await _select_route_async(
        conn,
        origin_place_id=int(origin_place_id),
        destination_place_id=int(destination_place_id),
        mode=mode,
        risk=risk,
        route_graph_key=route_graph_key,
    )
    eta = _eta(world_time, route["duration_minutes"])
    progress = float(data.get("initial_progress", 0.0))
    route_metadata = dict(route["metadata"])
    route_metadata.update(_travel_intent_metadata(data))
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
        json.dumps(route_metadata),
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


def _chunk_world_time_sync(cur: Any, source_chunk_id: int) -> Any:
    """The chunk's in-world time, or None — NEVER a wall-clock fallback.

    Provenance columns (applied_at_world_time, cleared_at_world_time) must
    stay NULL rather than lie with wall time when chunk_metadata is missing.
    """

    cur.execute(
        "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s",
        (source_chunk_id,),
    )
    row = cur.fetchone()
    return _row_get(row, "world_time", 0) if row else None


async def _chunk_world_time_async(conn: Any, source_chunk_id: int) -> Any:
    return await conn.fetchval(
        "SELECT world_time FROM chunk_metadata WHERE chunk_id = $1",
        source_chunk_id,
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
    if not _need_applies_to_entity_sync(
        cur,
        actor_entity_id=actor_entity_id,
        need_type=need_type,
    ):
        raise ValueError(
            f"Orrery need {need_type!r} does not apply to actor {actor_entity_id}"
        )

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
    if not await _need_applies_to_entity_async(
        conn,
        actor_entity_id=actor_entity_id,
        need_type=need_type,
    ):
        raise ValueError(
            f"Orrery need {need_type!r} does not apply to actor {actor_entity_id}"
        )

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


def _need_applies_to_entity_sync(
    cur: Any,
    *,
    actor_entity_id: int,
    need_type: str,
) -> bool:
    cur.execute(
        """
        SELECT etc.tag
        FROM entity_tags_current etc
        WHERE etc.entity_id = %s
        """,
        (actor_entity_id,),
    )
    return need_applies_to_tags(
        need_type,
        (str(_row_get(row, "tag", 0)) for row in cur.fetchall()),
    )


async def _need_applies_to_entity_async(
    conn: Any,
    *,
    actor_entity_id: int,
    need_type: str,
) -> bool:
    rows = await conn.fetch(
        """
        SELECT etc.tag
        FROM entity_tags_current etc
        WHERE etc.entity_id = $1
        """,
        actor_entity_id,
    )
    return need_applies_to_tags(
        need_type,
        (str(_row_get(row, "tag", 0)) for row in rows),
    )


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
        and _add_entity_tag_sync(
            cur,
            actor_entity_id,
            desired,
            template_id,
            source_chunk_id=source_chunk_id,
        )
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
        and await _add_entity_tag_async(
            conn,
            actor_entity_id,
            desired,
            template_id,
            source_chunk_id=source_chunk_id,
        )
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
    *,
    source_chunk_id: int,
) -> bool:
    tag_id = _registered_tag_id_sync(cur, tag)

    cur.execute(
        """
        INSERT INTO entity_tags (
            entity_id, tag_id, template_id, source_kind,
            applied_at_world_time, source_chunk_id
        )
        VALUES (%s, %s, %s, 'template', %s, %s)
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        (
            entity_id,
            tag_id,
            template_id,
            _chunk_world_time_sync(cur, source_chunk_id),
            source_chunk_id,
        ),
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
    *,
    source_chunk_id: int,
) -> bool:
    tag_id = await _registered_tag_id_async(conn, tag)

    inserted_id = await conn.fetchval(
        """
        INSERT INTO entity_tags (
            entity_id, tag_id, template_id, source_kind,
            applied_at_world_time, source_chunk_id
        )
        VALUES ($1, $2, $3, 'template', $4, $5)
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        entity_id,
        tag_id,
        template_id,
        await _chunk_world_time_async(conn, source_chunk_id),
        source_chunk_id,
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


def _clear_inbound_pair_tags_sync(
    cur: Any,
    *,
    object_entity_id: int,
    tag: str,
    template_id: str,
    source_chunk_id: int,
) -> int:
    cur.execute(
        """
        UPDATE entity_pair_tags ept
        SET cleared_at = now()
        FROM pair_tags pt
        WHERE ept.pair_tag_id = pt.id
          AND ept.object_entity_id = %s
          AND pt.tag = %s
          AND ept.cleared_at IS NULL
        RETURNING ept.id
        """,
        (object_entity_id, tag),
    )
    cleared_ids = [_row_get(row, "id", 0) for row in cur.fetchall()]
    world_time = _chunk_world_time_sync(cur, source_chunk_id)
    for pair_tag_row_id in cleared_ids:
        cur.execute(
            """
            INSERT INTO tag_clearance_log (
                entity_pair_tag_id, mechanism, cleared_at_world_time,
                justification, source_chunk_id
            ) VALUES (%s, 'authored', %s, %s::jsonb, %s)
            """,
            (
                pair_tag_row_id,
                world_time,
                json.dumps(
                    {
                        "template_id": template_id,
                        "state_delta": "entity_pair_tags_target.clear_inbound",
                        "tag": tag,
                    }
                ),
                source_chunk_id,
            ),
        )
    return len(cleared_ids)


def _registered_pair_tag_id_sync(cur: Any, tag: str) -> int:
    cur.execute("SELECT id FROM pair_tags WHERE tag = %s", (tag,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Orrery pair tag {tag!r} is not registered")
    return _row_get(row, "id", 0)


def _add_outbound_pair_tag_sync(
    cur: Any,
    *,
    subject_entity_id: int,
    object_entity_id: int,
    tag: str,
    template_id: str,
    source_chunk_id: int,
) -> bool:
    """Create a directed pair tag (actor -> target) from a branch outcome.

    The write mirrors _add_entity_tag_sync: template provenance, world-time
    stamp, and ON CONFLICT DO NOTHING against the unique current-row index
    so re-fires while the edge is live are no-ops.
    """

    pair_tag_id = _registered_pair_tag_id_sync(cur, tag)
    cur.execute(
        """
        INSERT INTO entity_pair_tags (
            subject_entity_id, object_entity_id, pair_tag_id,
            source_kind, applied_at_world_time, template_id, source_chunk_id
        )
        VALUES (%s, %s, %s, 'template', %s, %s, %s)
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        (
            subject_entity_id,
            object_entity_id,
            pair_tag_id,
            _chunk_world_time_sync(cur, source_chunk_id),
            template_id,
            source_chunk_id,
        ),
    )
    return cur.fetchone() is not None


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


async def _clear_inbound_pair_tags_async(
    conn: Any,
    *,
    object_entity_id: int,
    tag: str,
    template_id: str,
    source_chunk_id: int,
) -> int:
    rows = await conn.fetch(
        """
        UPDATE entity_pair_tags ept
        SET cleared_at = now()
        FROM pair_tags pt
        WHERE ept.pair_tag_id = pt.id
          AND ept.object_entity_id = $1
          AND pt.tag = $2
          AND ept.cleared_at IS NULL
        RETURNING ept.id
        """,
        object_entity_id,
        tag,
    )
    cleared_ids = [_row_get(row, "id", 0) for row in rows]
    world_time = await _chunk_world_time_async(conn, source_chunk_id)
    for pair_tag_row_id in cleared_ids:
        await conn.execute(
            """
            INSERT INTO tag_clearance_log (
                entity_pair_tag_id, mechanism, cleared_at_world_time,
                justification, source_chunk_id
            ) VALUES ($1, 'authored', $2, $3::jsonb, $4)
            """,
            pair_tag_row_id,
            world_time,
            json.dumps(
                {
                    "template_id": template_id,
                    "state_delta": "entity_pair_tags_target.clear_inbound",
                    "tag": tag,
                }
            ),
            source_chunk_id,
        )
    return len(cleared_ids)


async def _registered_pair_tag_id_async(conn: Any, tag: str) -> int:
    row = await conn.fetchrow("SELECT id FROM pair_tags WHERE tag = $1", tag)
    if not row:
        raise ValueError(f"Orrery pair tag {tag!r} is not registered")
    return _row_get(row, "id", 0)


async def _add_outbound_pair_tag_async(
    conn: Any,
    *,
    subject_entity_id: int,
    object_entity_id: int,
    tag: str,
    template_id: str,
    source_chunk_id: int,
) -> bool:
    """Async twin of _add_outbound_pair_tag_sync."""

    pair_tag_id = await _registered_pair_tag_id_async(conn, tag)
    world_time = await _chunk_world_time_async(conn, source_chunk_id)
    row = await conn.fetchrow(
        """
        INSERT INTO entity_pair_tags (
            subject_entity_id, object_entity_id, pair_tag_id,
            source_kind, applied_at_world_time, template_id, source_chunk_id
        )
        VALUES ($1, $2, $3, 'template', $4, $5, $6)
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        subject_entity_id,
        object_entity_id,
        pair_tag_id,
        world_time,
        template_id,
        source_chunk_id,
    )
    return row is not None


def _emit_world_event_sync(
    cur: Any,
    draft: OrreryResolutionDraft,
    *,
    tick_chunk_id: int,
    resolution_id: int,
    actor_entity_id: Optional[int],
    target_entity_id: Optional[int],
    world_layer: Optional[str],
    signal_detection: SignalDetection,
) -> Optional[int]:
    if not draft.event_type:
        return None

    _ensure_event_type_sync(cur, draft.event_type)
    detection_outcome: Optional[dict[str, Any]] = None
    if draft.signal_event_type:
        _ensure_event_type_sync(cur, draft.signal_event_type)
        detection_outcome = signal_detection.outcome(
            template_id=draft.template_id,
            actor_entity_id=actor_entity_id,
            target_entity_id=target_entity_id,
            tick_chunk_id=tick_chunk_id,
            event_type=draft.signal_event_type,
        )
    location_id = _actor_location_sync(cur, actor_entity_id)
    payload = {
        "proposal_id": draft.proposal_id,
        "template_id": draft.template_id,
        "binding_hash": draft.binding_hash,
        "bindings": dict(draft.bindings),
        "branch_label": draft.branch_label,
        "narrative_stub": draft.narrative_stub,
    }
    if detection_outcome is not None:
        # Recorded on the primary event either way so the audit layer can
        # show "signal went out, undetected" without a phantom event row.
        payload["signal_detection"] = detection_outcome
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
    if draft.signal_event_type and detection_outcome and detection_outcome["detected"]:
        # The act's signal: a second, additive emission with the same
        # bindings so other packages' gates can hear it (spec idea 7).
        cur.execute(
            """
            INSERT INTO world_events (
                event_type, tick_chunk_id, actor_entity_id, target_entity_id,
                location_id, world_layer, source, changed_fields, magnitude,
                resolution_id, payload
            ) VALUES (%s, %s, %s, %s, %s, %s, 'resolver', %s, %s, %s, %s::jsonb)
            """,
            (
                draft.signal_event_type,
                tick_chunk_id,
                actor_entity_id,
                target_entity_id,
                location_id,
                world_layer,
                [],
                draft.magnitude,
                resolution_id,
                json.dumps({**payload, "signal_of": draft.event_type}),
            ),
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
    signal_detection: SignalDetection,
) -> Optional[int]:
    if not draft.event_type:
        return None

    await _ensure_event_type_async(conn, draft.event_type)
    detection_outcome: Optional[dict[str, Any]] = None
    if draft.signal_event_type:
        await _ensure_event_type_async(conn, draft.signal_event_type)
        detection_outcome = signal_detection.outcome(
            template_id=draft.template_id,
            actor_entity_id=actor_entity_id,
            target_entity_id=target_entity_id,
            tick_chunk_id=tick_chunk_id,
            event_type=draft.signal_event_type,
        )
    location_id = await _actor_location_async(conn, actor_entity_id)
    payload = {
        "proposal_id": draft.proposal_id,
        "template_id": draft.template_id,
        "binding_hash": draft.binding_hash,
        "bindings": dict(draft.bindings),
        "branch_label": draft.branch_label,
        "narrative_stub": draft.narrative_stub,
    }
    if detection_outcome is not None:
        payload["signal_detection"] = detection_outcome
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
    if draft.signal_event_type and detection_outcome and detection_outcome["detected"]:
        # Same additive signal emission as the sync twin.
        await conn.execute(
            """
            INSERT INTO world_events (
                event_type, tick_chunk_id, actor_entity_id, target_entity_id,
                location_id, world_layer, source, changed_fields, magnitude,
                resolution_id, payload
            ) VALUES (
                $1, $2, $3, $4, $5, $6::world_layer_type, 'resolver',
                $7::text[], $8, $9, $10::jsonb
            )
            """,
            draft.signal_event_type,
            tick_chunk_id,
            actor_entity_id,
            target_entity_id,
            location_id,
            world_layer,
            [],
            draft.magnitude,
            resolution_id,
            json.dumps({**payload, "signal_of": draft.event_type}),
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


def _routine_anchor_destination_sync(
    cur: Any,
    *,
    actor_entity_id: int,
    anchor_type: str,
) -> Optional[int]:
    cur.execute(
        """
        SELECT place_id, zone_id, mobility_policy::text AS mobility_policy
        FROM character_routine_anchors
        WHERE character_entity_id = %s
          AND anchor_type = %s::orrery_routine_anchor_type
        """,
        (actor_entity_id, anchor_type),
    )
    row = cur.fetchone()
    if row is None:
        return None
    policy = _row_get(row, "mobility_policy", 2)
    place_id = _row_get(row, "place_id", 0)
    zone_id = _row_get(row, "zone_id", 1)
    if policy == "fixed_place":
        return place_id
    if policy == "works_from_home":
        if anchor_type == "home":
            return None
        return _routine_anchor_destination_sync(
            cur,
            actor_entity_id=actor_entity_id,
            anchor_type="home",
        )
    if policy == "zone_resolved" and zone_id is not None:
        return _routine_zone_destination_sync(
            cur, zone_id=int(zone_id), anchor_type=anchor_type
        )
    return None


def _routine_zone_destination_sync(
    cur: Any,
    *,
    zone_id: int,
    anchor_type: str,
) -> Optional[int]:
    preferred_tags = (
        ("dwelling", "haven")
        if anchor_type == "home"
        else (
            "commerce",
            "administration",
            "craft",
            "production",
            "place_medical",
            "military",
        )
    )
    cur.execute(
        """
        SELECT p.id
        FROM places p
        LEFT JOIN entity_tags_current etc
          ON etc.entity_id = p.entity_id
         AND etc.category = 'place_function'
         AND etc.tag = ANY(%s)
        WHERE p.zone = %s
        GROUP BY p.id
        ORDER BY CASE WHEN count(etc.tag) > 0 THEN 0 ELSE 1 END, p.id
        LIMIT 1
        """,
        (list(preferred_tags), zone_id),
    )
    row = cur.fetchone()
    return _row_get(row, "id", 0) if row else None


def _location_class_destination_sync(
    cur: Any,
    *,
    origin_place_id: int,
    location_classes: tuple[str, ...],
) -> Optional[int]:
    cur.execute(
        """
        SELECT p.id
        FROM places p
        LEFT JOIN places origin ON origin.id = %s
        LEFT JOIN entity_tags_current etc
          ON etc.entity_id = p.entity_id
         AND etc.category = ANY(%s)
         AND etc.tag = ANY(%s)
        WHERE p.id <> %s
          AND (p.type::text = ANY(%s) OR etc.tag IS NOT NULL)
        -- Collapse multiple matching tags per place before preferring same-zone
        -- destinations.
        GROUP BY p.id, p.zone, origin.zone
        ORDER BY CASE
                   WHEN origin.zone IS NOT NULL AND p.zone = origin.zone THEN 0
                   ELSE 1
                 END,
                 p.id
        LIMIT 1
        """,
        (
            origin_place_id,
            list(LOCATION_CLASS_TAG_CATEGORIES),
            list(location_classes),
            origin_place_id,
            list(location_classes),
        ),
    )
    row = cur.fetchone()
    return _row_get(row, "id", 0) if row else None


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


async def _routine_anchor_destination_async(
    conn: Any,
    *,
    actor_entity_id: int,
    anchor_type: str,
) -> Optional[int]:
    row = await conn.fetchrow(
        """
        SELECT place_id, zone_id, mobility_policy::text AS mobility_policy
        FROM character_routine_anchors
        WHERE character_entity_id = $1
          AND anchor_type = $2::orrery_routine_anchor_type
        """,
        actor_entity_id,
        anchor_type,
    )
    if row is None:
        return None
    policy = _row_get(row, "mobility_policy", 2)
    place_id = _row_get(row, "place_id", 0)
    zone_id = _row_get(row, "zone_id", 1)
    if policy == "fixed_place":
        return place_id
    if policy == "works_from_home":
        if anchor_type == "home":
            return None
        return await _routine_anchor_destination_async(
            conn,
            actor_entity_id=actor_entity_id,
            anchor_type="home",
        )
    if policy == "zone_resolved" and zone_id is not None:
        return await _routine_zone_destination_async(
            conn,
            zone_id=int(zone_id),
            anchor_type=anchor_type,
        )
    return None


async def _routine_zone_destination_async(
    conn: Any,
    *,
    zone_id: int,
    anchor_type: str,
) -> Optional[int]:
    preferred_tags = (
        ("dwelling", "haven")
        if anchor_type == "home"
        else (
            "commerce",
            "administration",
            "craft",
            "production",
            "place_medical",
            "military",
        )
    )
    return await conn.fetchval(
        """
        SELECT p.id
        FROM places p
        LEFT JOIN entity_tags_current etc
          ON etc.entity_id = p.entity_id
         AND etc.category = 'place_function'
         AND etc.tag = ANY($1::text[])
        WHERE p.zone = $2
        GROUP BY p.id
        ORDER BY CASE WHEN count(etc.tag) > 0 THEN 0 ELSE 1 END, p.id
        LIMIT 1
        """,
        list(preferred_tags),
        zone_id,
    )


async def _location_class_destination_async(
    conn: Any,
    *,
    origin_place_id: int,
    location_classes: tuple[str, ...],
) -> Optional[int]:
    return await conn.fetchval(
        """
        SELECT p.id
        FROM places p
        LEFT JOIN places origin ON origin.id = $1
        LEFT JOIN entity_tags_current etc
          ON etc.entity_id = p.entity_id
         AND etc.category = ANY($2::text[])
         AND etc.tag = ANY($3::text[])
        WHERE p.id <> $1
          AND (p.type::text = ANY($3::text[]) OR etc.tag IS NOT NULL)
        -- Collapse multiple matching tags per place before preferring same-zone
        -- destinations.
        GROUP BY p.id, p.zone, origin.zone
        ORDER BY CASE
                   WHEN origin.zone IS NOT NULL AND p.zone = origin.zone THEN 0
                   ELSE 1
                 END,
                 p.id
        LIMIT 1
        """,
        origin_place_id,
        list(LOCATION_CLASS_TAG_CATEGORIES),
        list(location_classes),
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
    route_graph_key: str,
) -> dict[str, Any]:
    graph_route = _osm_graph_route_sync(
        cur,
        origin_place_id=origin_place_id,
        destination_place_id=destination_place_id,
        mode=mode,
        graph_key=route_graph_key,
    )
    if graph_route is not None:
        return graph_route

    edge = _authored_route_edge_sync(
        cur,
        origin_place_id=origin_place_id,
        destination_place_id=destination_place_id,
        mode=mode,
    )
    if edge is not None:
        # Authored edges own their stored risk; caller risk only applies to
        # coordinate-estimate fallback routes.
        return _route_from_authored_edge(
            edge,
            origin_place_id=origin_place_id,
            destination_place_id=destination_place_id,
            requested_mode=mode,
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
    route_graph_key: str,
) -> dict[str, Any]:
    graph_route = await _osm_graph_route_async(
        conn,
        origin_place_id=origin_place_id,
        destination_place_id=destination_place_id,
        mode=mode,
        graph_key=route_graph_key,
    )
    if graph_route is not None:
        return graph_route

    edge = await _authored_route_edge_async(
        conn,
        origin_place_id=origin_place_id,
        destination_place_id=destination_place_id,
        mode=mode,
    )
    if edge is not None:
        # Authored edges own their stored risk; caller risk only applies to
        # coordinate-estimate fallback routes.
        return _route_from_authored_edge(
            edge,
            origin_place_id=origin_place_id,
            destination_place_id=destination_place_id,
            requested_mode=mode,
        )
    return await _estimate_route_async(
        conn,
        origin_place_id=origin_place_id,
        destination_place_id=destination_place_id,
        mode=mode,
        risk=risk,
    )


def _osm_graph_route_sync(
    cur: Any,
    *,
    origin_place_id: int,
    destination_place_id: int,
    mode: str,
    graph_key: str,
) -> Optional[dict[str, Any]]:
    if mode not in ROUTE_GRAPH_MODES:
        return None
    origin_node = _place_route_graph_node_sync(
        cur,
        place_id=origin_place_id,
        mode=mode,
        graph_key=graph_key,
    )
    destination_node = _place_route_graph_node_sync(
        cur,
        place_id=destination_place_id,
        mode=mode,
        graph_key=graph_key,
    )
    if origin_node is None or destination_node is None:
        return None
    edges = _route_graph_edges_sync(cur, mode=mode, graph_key=graph_key)
    if not edges:
        return None
    route = shortest_route(
        edges,
        origin_node_id=int(_row_get(origin_node, "node_id", 0)),
        destination_node_id=int(_row_get(destination_node, "node_id", 0)),
        requested_mode=mode,
        speed_kmh=TRAVEL_MODE_SPEED_KMH[mode],
    )
    if route is None:
        return None
    return _route_from_osm_graph(
        route,
        origin_node=origin_node,
        destination_node=destination_node,
        origin_place_id=origin_place_id,
        destination_place_id=destination_place_id,
        requested_mode=mode,
        graph_key=graph_key,
    )


async def _osm_graph_route_async(
    conn: Any,
    *,
    origin_place_id: int,
    destination_place_id: int,
    mode: str,
    graph_key: str,
) -> Optional[dict[str, Any]]:
    if mode not in ROUTE_GRAPH_MODES:
        return None
    origin_node = await _place_route_graph_node_async(
        conn,
        place_id=origin_place_id,
        mode=mode,
        graph_key=graph_key,
    )
    destination_node = await _place_route_graph_node_async(
        conn,
        place_id=destination_place_id,
        mode=mode,
        graph_key=graph_key,
    )
    if origin_node is None or destination_node is None:
        return None
    edges = await _route_graph_edges_async(conn, mode=mode, graph_key=graph_key)
    if not edges:
        return None
    route = shortest_route(
        edges,
        origin_node_id=int(_row_get(origin_node, "node_id", 0)),
        destination_node_id=int(_row_get(destination_node, "node_id", 0)),
        requested_mode=mode,
        speed_kmh=TRAVEL_MODE_SPEED_KMH[mode],
    )
    if route is None:
        return None
    return _route_from_osm_graph(
        route,
        origin_node=origin_node,
        destination_node=destination_node,
        origin_place_id=origin_place_id,
        destination_place_id=destination_place_id,
        requested_mode=mode,
        graph_key=graph_key,
    )


def _place_route_graph_node_sync(
    cur: Any,
    *,
    place_id: int,
    mode: str,
    graph_key: str,
) -> Optional[Any]:
    cur.execute(
        """
        SELECT prgn.node_id,
               prgn.travel_mode::text AS travel_mode,
               prgn.distance_m,
               prgn.source,
               prgn.metadata,
               n.node_key,
               ST_AsGeoJSON(n.coordinates) AS node_geojson
        FROM orrery_place_route_graph_nodes prgn
        JOIN orrery_route_graph_nodes n ON n.id = prgn.node_id
        WHERE prgn.place_id = %s
          AND prgn.graph_key = %s
          AND prgn.travel_mode IN (%s::orrery_travel_mode, 'mixed'::orrery_travel_mode)
        ORDER BY (prgn.travel_mode = %s::orrery_travel_mode) DESC,
                 prgn.distance_m NULLS LAST,
                 prgn.node_id
        LIMIT 1
        """,
        (place_id, graph_key, mode, mode),
    )
    return cur.fetchone()


async def _place_route_graph_node_async(
    conn: Any,
    *,
    place_id: int,
    mode: str,
    graph_key: str,
) -> Optional[Any]:
    return await conn.fetchrow(
        """
        SELECT prgn.node_id,
               prgn.travel_mode::text AS travel_mode,
               prgn.distance_m,
               prgn.source,
               prgn.metadata,
               n.node_key,
               ST_AsGeoJSON(n.coordinates) AS node_geojson
        FROM orrery_place_route_graph_nodes prgn
        JOIN orrery_route_graph_nodes n ON n.id = prgn.node_id
        WHERE prgn.place_id = $1
          AND prgn.graph_key = $2
          AND prgn.travel_mode IN ($3::orrery_travel_mode, 'mixed'::orrery_travel_mode)
        ORDER BY (prgn.travel_mode = $3::orrery_travel_mode) DESC,
                 prgn.distance_m NULLS LAST,
                 prgn.node_id
        LIMIT 1
        """,
        place_id,
        graph_key,
        mode,
    )


def _route_graph_edges_sync(
    cur: Any,
    *,
    mode: str,
    graph_key: str,
) -> list[RouteGraphEdge]:
    max_edges = _route_graph_max_edges_per_query()
    cur.execute(
        """
        SELECT id,
               from_node_id,
               to_node_id,
               travel_mode::text AS travel_mode,
               risk::text AS risk,
               bidirectional,
               distance_m,
               duration_minutes
        FROM orrery_route_graph_edges
        WHERE graph_key = %s
          AND travel_mode IN (%s::orrery_travel_mode, 'mixed'::orrery_travel_mode)
        ORDER BY id
        LIMIT %s
        """,
        (graph_key, mode, max_edges + 1),
    )
    rows = cur.fetchall()
    _raise_if_route_graph_too_large(
        rows, graph_key=graph_key, mode=mode, max_edges=max_edges
    )
    return [_route_graph_edge_from_row(row) for row in rows]


async def _route_graph_edges_async(
    conn: Any,
    *,
    mode: str,
    graph_key: str,
) -> list[RouteGraphEdge]:
    max_edges = _route_graph_max_edges_per_query()
    rows = await conn.fetch(
        """
        SELECT id,
               from_node_id,
               to_node_id,
               travel_mode::text AS travel_mode,
               risk::text AS risk,
               bidirectional,
               distance_m,
               duration_minutes
        FROM orrery_route_graph_edges
        WHERE graph_key = $1
          AND travel_mode IN ($2::orrery_travel_mode, 'mixed'::orrery_travel_mode)
        ORDER BY id
        LIMIT $3
        """,
        graph_key,
        mode,
        max_edges + 1,
    )
    _raise_if_route_graph_too_large(
        rows, graph_key=graph_key, mode=mode, max_edges=max_edges
    )
    return [_route_graph_edge_from_row(row) for row in rows]


def _raise_if_route_graph_too_large(
    rows: Any,
    *,
    graph_key: str,
    mode: str,
    max_edges: int,
) -> None:
    if len(rows) <= max_edges:
        return
    raise ValueError(
        "Orrery route graph query exceeded "
        f"{max_edges} edges for graph_key={graph_key!r}, mode={mode!r}; "
        "trim the offline extract or raise orrery.route_graph.max_edges_per_query"
    )


def _route_graph_edge_from_row(row: Any) -> RouteGraphEdge:
    return RouteGraphEdge(
        edge_id=int(_row_get(row, "id", 0)),
        from_node_id=int(_row_get(row, "from_node_id", 1)),
        to_node_id=int(_row_get(row, "to_node_id", 2)),
        travel_mode=str(_row_get(row, "travel_mode", 3)),
        risk=str(_row_get(row, "risk", 4)),
        bidirectional=bool(_row_get(row, "bidirectional", 5)),
        distance_m=float(_row_get(row, "distance_m", 6)),
        duration_minutes=_float_or_none(_row_get(row, "duration_minutes", 7)),
    )


def _route_from_osm_graph(
    route: Any,
    *,
    origin_node: Any,
    destination_node: Any,
    origin_place_id: int,
    destination_place_id: int,
    requested_mode: str,
    graph_key: str,
) -> dict[str, Any]:
    metadata = {
        "route_method": "osm_graph",
        "origin_place_id": origin_place_id,
        "destination_place_id": destination_place_id,
        "requested_travel_mode": requested_mode,
        "travel_mode": requested_mode,
        "graph_key": graph_key,
        "route_node_ids": list(route.node_ids),
        "route_edge_ids": list(route.edge_ids),
        "route_edge_count": len(route.edge_ids),
        "edge_travel_modes": list(route.edge_travel_modes),
        "origin_graph_node_id": _row_get(origin_node, "node_id", 0),
        "destination_graph_node_id": _row_get(destination_node, "node_id", 0),
        "origin_node_key": _row_get_optional(origin_node, "node_key", 5),
        "destination_node_key": _row_get_optional(destination_node, "node_key", 5),
        "origin_graph_distance_m": _float_or_none(
            _row_get_optional(origin_node, "distance_m", 2)
        ),
        "destination_graph_distance_m": _float_or_none(
            _row_get_optional(destination_node, "distance_m", 2)
        ),
    }
    origin_geojson = _decode_json_value(
        _row_get_optional(origin_node, "node_geojson", 6)
    )
    destination_geojson = _decode_json_value(
        _row_get_optional(destination_node, "node_geojson", 6)
    )
    if origin_geojson is not None:
        metadata["origin_node_geometry"] = origin_geojson
    if destination_geojson is not None:
        metadata["destination_node_geometry"] = destination_geojson
    return {
        "route_method": "osm_graph",
        "travel_mode": requested_mode,
        "risk": route.risk,
        "distance_m": route.distance_m,
        "duration_minutes": route.duration_minutes,
        "metadata": metadata,
    }


def _authored_route_edge_sync(
    cur: Any,
    *,
    origin_place_id: int,
    destination_place_id: int,
    mode: str,
) -> Optional[Any]:
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
               metadata,
               (from_place_id = %s AND to_place_id = %s) AS is_direct
        FROM orrery_travel_edges
        WHERE route_method = 'authored_edge'
          AND travel_mode IN (%s::orrery_travel_mode, 'mixed'::orrery_travel_mode)
          AND (
            (from_place_id = %s AND to_place_id = %s)
            OR (from_place_id = %s AND to_place_id = %s AND bidirectional = true)
          )
        ORDER BY (travel_mode = %s::orrery_travel_mode) DESC, is_direct DESC, id
        LIMIT 1
        """,
        (
            origin_place_id,
            destination_place_id,
            mode,
            origin_place_id,
            destination_place_id,
            destination_place_id,
            origin_place_id,
            mode,
        ),
    )
    return cur.fetchone()


async def _authored_route_edge_async(
    conn: Any,
    *,
    origin_place_id: int,
    destination_place_id: int,
    mode: str,
) -> Optional[Any]:
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
               metadata,
               (from_place_id = $1 AND to_place_id = $2) AS is_direct
        FROM orrery_travel_edges
        WHERE route_method = 'authored_edge'
          AND travel_mode IN ($3::orrery_travel_mode, 'mixed'::orrery_travel_mode)
          AND (
            (from_place_id = $1 AND to_place_id = $2)
            OR (from_place_id = $2 AND to_place_id = $1 AND bidirectional = true)
          )
        ORDER BY (travel_mode = $3::orrery_travel_mode) DESC, is_direct DESC, id
        LIMIT 1
        """,
        origin_place_id,
        destination_place_id,
        mode,
    )
    return row


def _route_from_authored_edge(
    row: Any,
    *,
    origin_place_id: int,
    destination_place_id: int,
    requested_mode: str,
) -> dict[str, Any]:
    edge_id = int(_row_get(row, "id", 0))
    edge_from_place_id = int(_row_get(row, "from_place_id", 1))
    edge_to_place_id = int(_row_get(row, "to_place_id", 2))
    edge_travel_mode = str(_row_get(row, "travel_mode", 4))
    travel_mode = requested_mode if edge_travel_mode == "mixed" else edge_travel_mode
    risk = str(_row_get(row, "risk", 5))
    route_geometry = _decode_json_value(
        _row_get_optional(row, "route_geometry_geojson", 9)
    )
    reversed_edge = not bool(_row_get(row, "is_direct", 12))
    metadata = {
        "route_method": "authored_edge",
        "origin_place_id": origin_place_id,
        "destination_place_id": destination_place_id,
        "requested_travel_mode": requested_mode,
        "travel_mode": travel_mode,
        "edge_travel_mode": edge_travel_mode,
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


def _sweep_expired_entity_tags_sync(
    cur: Any,
    *,
    source_chunk_id: int,
) -> int:
    world_time = _tick_world_time_sync(cur, source_chunk_id)
    cur.execute(
        """
        SELECT et.id, et.expires_at_world_time
        FROM entity_tags et
        WHERE et.cleared_at IS NULL
          AND et.expires_at_world_time IS NOT NULL
          AND et.expires_at_world_time <= %s
        """,
        (world_time,),
    )
    rows = cur.fetchall()
    for row in rows:
        entity_tag_id = _row_get(row, "id", 0)
        expires_at_world_time = _row_get(row, "expires_at_world_time", 1)
        cur.execute(
            "UPDATE entity_tags SET cleared_at = now() WHERE id = %s",
            (entity_tag_id,),
        )
        cur.execute(
            """
            INSERT INTO tag_clearance_log (
                entity_tag_id, cleared_at_world_time, mechanism,
                triggering_event_id, justification, source_chunk_id
            ) VALUES (%s, %s, 'time', NULL, %s::jsonb, %s)
            """,
            (
                entity_tag_id,
                world_time,
                json.dumps(
                    {
                        "expires_at_world_time": (
                            str(expires_at_world_time)
                            if expires_at_world_time is not None
                            else None
                        )
                    }
                ),
                source_chunk_id,
            ),
        )
    return len(rows)


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


async def _sweep_expired_entity_tags_async(
    conn: Any,
    *,
    source_chunk_id: int,
) -> int:
    world_time = await _tick_world_time_async(conn, source_chunk_id)
    rows = await conn.fetch(
        """
        SELECT et.id, et.expires_at_world_time
        FROM entity_tags et
        WHERE et.cleared_at IS NULL
          AND et.expires_at_world_time IS NOT NULL
          AND et.expires_at_world_time <= $1
        """,
        world_time,
    )
    for row in rows:
        entity_tag_id = _row_get(row, "id", 0)
        expires_at_world_time = _row_get(row, "expires_at_world_time", 1)
        await conn.execute(
            "UPDATE entity_tags SET cleared_at = now() WHERE id = $1",
            entity_tag_id,
        )
        await conn.execute(
            """
            INSERT INTO tag_clearance_log (
                entity_tag_id, cleared_at_world_time, mechanism,
                triggering_event_id, justification, source_chunk_id
            ) VALUES ($1, $2, 'time', NULL, $3::jsonb, $4)
            """,
            entity_tag_id,
            world_time,
            json.dumps(
                {
                    "expires_at_world_time": (
                        str(expires_at_world_time)
                        if expires_at_world_time is not None
                        else None
                    )
                }
            ),
            source_chunk_id,
        )
    return len(rows)


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
