"""Dev-only FastAPI endpoints backing the Orrery audit dashboard.

Registered on the gateway only when ``[orrery.dashboard] enabled`` is true in
nexus.toml (see the conditional ``include_router`` in
:mod:`nexus.api.narrative`). All endpoints are read-only against slot
databases; payload assembly lives in :mod:`nexus.agents.orrery.audit` so it
can be exercised directly in tests.

Unexpected failures are allowed to propagate (500 with the real traceback in
the server log) — this is a development surface and errors should be loud.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.orrery.audit import build_catalog, entity_context, explain_dry_run
from nexus.agents.orrery.coverage import analyze_coverage, sample_anchor_ids
from nexus.agents.orrery.history import adjudication_history
from nexus.agents.orrery.overrides import (
    EventOverride,
    LocationOverride,
    NeedOverride,
    OverrideValidationError,
    PairTagOverride,
    TagOverride,
    WorldStateOverrides,
)
from nexus.agents.orrery.reconstruction import playable_narrative_predicate
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
from nexus.api.slot_utils import get_slot_db_url

logger = logging.getLogger("nexus.api.orrery_dev_endpoints")

router = APIRouter(prefix="/api/dev/orrery", tags=["orrery-dev"])


class OrreryTagOverrideModel(BaseModel):
    """Toggle one durable or ephemeral tag on one entity."""

    model_config = ConfigDict(extra="forbid")

    entity_id: int
    tag: str
    op: Literal["add", "remove"]
    ephemeral: bool = Field(
        default=False,
        description=(
            "Layer to edit; must match the tag vocabulary's is_ephemeral flag "
            "(validated server-side)."
        ),
    )


class OrreryPairTagOverrideModel(BaseModel):
    """Toggle one directed pair tag between two entities."""

    model_config = ConfigDict(extra="forbid")

    subject_entity_id: int
    object_entity_id: int
    tag: str
    op: Literal["add", "remove"]


class OrreryNeedOverrideModel(BaseModel):
    """Set one entity's debt score for one need type."""

    model_config = ConfigDict(extra="forbid")

    entity_id: int
    need_type: str
    debt_score: float = Field(ge=0)


class OrreryLocationOverrideModel(BaseModel):
    """Move one entity to a place."""

    model_config = ConfigDict(extra="forbid")

    entity_id: int
    place_id: int


class OrreryEventOverrideModel(BaseModel):
    """Inject a recent event ticks_ago ticks before the anchor tick."""

    model_config = ConfigDict(extra="forbid")

    event_type: str
    actor_entity_id: Optional[int] = None
    target_entity_id: Optional[int] = None
    location_id: Optional[int] = None
    ticks_ago: int = Field(default=0, ge=0)
    changed_fields: List[str] = Field(default_factory=list)


class OrreryOverridesModel(BaseModel):
    """What-if override set applied to a copy of the hydrated world state."""

    model_config = ConfigDict(extra="forbid")

    tags: List[OrreryTagOverrideModel] = Field(default_factory=list)
    pair_tags: List[OrreryPairTagOverrideModel] = Field(default_factory=list)
    needs: List[OrreryNeedOverrideModel] = Field(default_factory=list)
    locations: List[OrreryLocationOverrideModel] = Field(default_factory=list)
    events: List[OrreryEventOverrideModel] = Field(default_factory=list)

    def to_overrides(self) -> WorldStateOverrides:
        return WorldStateOverrides(
            tags=tuple(
                TagOverride(
                    entity_id=item.entity_id,
                    tag=item.tag,
                    op=item.op,
                    ephemeral=item.ephemeral,
                )
                for item in self.tags
            ),
            pair_tags=tuple(
                PairTagOverride(
                    subject_entity_id=item.subject_entity_id,
                    object_entity_id=item.object_entity_id,
                    tag=item.tag,
                    op=item.op,
                )
                for item in self.pair_tags
            ),
            needs=tuple(
                NeedOverride(
                    entity_id=item.entity_id,
                    need_type=item.need_type,
                    debt_score=item.debt_score,
                )
                for item in self.needs
            ),
            locations=tuple(
                LocationOverride(entity_id=item.entity_id, place_id=item.place_id)
                for item in self.locations
            ),
            events=tuple(
                EventOverride(
                    event_type=item.event_type,
                    actor_entity_id=item.actor_entity_id,
                    target_entity_id=item.target_entity_id,
                    location_id=item.location_id,
                    ticks_ago=item.ticks_ago,
                    changed_fields=tuple(item.changed_fields),
                )
                for item in self.events
            ),
        )


class OrreryResolveRequest(BaseModel):
    """Parameters for one explained dry-run tick."""

    model_config = ConfigDict(extra="forbid")

    slot: Optional[int] = Field(
        default=None,
        description="Save slot (1-5); falls back to NEXUS_SLOT when omitted.",
    )
    anchor_chunk_id: Optional[int] = Field(
        default=None,
        description=(
            "Tick anchor chunk. Defaults to the slot's latest narrative chunk, "
            "matching the turn cycle's fallback."
        ),
    )
    window_chunks: Optional[int] = Field(
        default=None,
        description="Binding window; defaults to [orrery.binding] window_chunks.",
    )
    overrides: Optional[OrreryOverridesModel] = Field(
        default=None,
        description=(
            "What-if override set. When present and non-empty the response "
            "switches to what_if mode: the tick is explained against a copy "
            "of the world state with these edits applied, and every stack "
            "carries a diff against the un-overridden baseline. Overrides "
            "never touch the database."
        ),
    )


class OrreryCoverageRequest(BaseModel):
    """Parameters for a batch coverage analysis over historical anchors."""

    model_config = ConfigDict(extra="forbid")

    slot: Optional[int] = Field(default=None)
    anchor_chunk_ids: Optional[List[int]] = Field(
        default=None,
        min_length=1,
        description=(
            "Explicit anchors to analyze. When omitted, `count`/`stride`/"
            "`end_chunk_id` sample real chunk ids walking backward from the "
            "slot head."
        ),
    )
    count: int = Field(default=10, ge=1)
    stride: int = Field(default=1, ge=1)
    end_chunk_id: Optional[int] = Field(default=None)
    window_chunks: Optional[int] = Field(
        default=None,
        description="Binding window; defaults to [orrery.binding] window_chunks.",
    )


class OrreryEntityContextRequest(BaseModel):
    """Parameters for the entity hover/context payload."""

    model_config = ConfigDict(extra="forbid")

    slot: Optional[int] = Field(default=None)
    entity_ids: List[int] = Field(min_length=1)
    anchor_chunk_id: Optional[int] = Field(
        default=None,
        description=(
            "Tick anchor for need-debt accrual and world-time readout. "
            "Defaults to the slot's latest narrative chunk."
        ),
    )
    recent_events_limit: int = Field(default=5, ge=1, le=50)


def _orrery_settings() -> dict[str, Any]:
    from nexus.config import load_settings_as_dict

    settings = load_settings_as_dict()
    orrery = settings.get("orrery")
    if not orrery:
        raise RuntimeError(
            "nexus.toml has no [orrery] section; the audit dashboard cannot "
            "resolve without binding/sunhelm configuration"
        )
    return orrery


@contextmanager
def _slot_session(slot: Optional[int]) -> Iterator[Session]:
    try:
        db_url = get_slot_db_url(slot=slot)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    engine = create_engine(db_url)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def _default_anchor_chunk_id(session: Session) -> Optional[int]:
    # Same fallback the turn cycle uses when no target chunk is in play.
    row = (
        session.execute(
            text(
                "SELECT max(nc.id) AS max_id FROM narrative_chunks nc WHERE "
                + playable_narrative_predicate("nc")
            )
        )
        .mappings()
        .first()
    )
    return row["max_id"] if row else None


@router.get("/catalog")
async def get_catalog() -> dict[str, Any]:
    """Static template catalog: bands, pseudo-templates, families, event map."""

    orrery = _orrery_settings()
    return build_catalog(
        BUILTIN_TEMPLATES,
        sunhelm_settings=orrery.get("sunhelm"),
        promote_settings=orrery.get("promote"),
    )


@router.post("/resolve")
async def post_resolve(request: OrreryResolveRequest) -> dict[str, Any]:
    """Explained dry-run tick against a real slot. Read-only."""

    orrery = _orrery_settings()
    window_chunks = (
        request.window_chunks
        if request.window_chunks is not None
        else int(orrery["binding"]["window_chunks"])
    )
    overrides = (
        request.overrides.to_overrides() if request.overrides is not None else None
    )
    with _slot_session(request.slot) as session:
        anchor_chunk_id = (
            request.anchor_chunk_id
            if request.anchor_chunk_id is not None
            else _default_anchor_chunk_id(session)
        )
        try:
            report = explain_dry_run(
                session,
                BUILTIN_TEMPLATES,
                anchor_chunk_id=anchor_chunk_id,
                window_chunks=window_chunks,
                sunhelm_settings=orrery.get("sunhelm"),
                overrides=overrides,
                selection_settings=orrery.get("selection"),
                habituation_settings=orrery.get("habituation"),
                package_selection_settings=orrery.get("package_selection"),
                project_settings=orrery.get("projects"),
                fanout_settings=orrery.get("fanout"),
            )
        except OverrideValidationError as exc:
            # Override validation (unknown vocab, no-op toggles) is caller
            # error, not a server fault; anything else propagates as 500.
            raise HTTPException(status_code=400, detail=str(exc))
    return report.to_dict()


@router.post("/context/entities")
async def post_entity_context(
    request: OrreryEntityContextRequest,
) -> dict[str, Any]:
    """Hover-audit payload for a set of entity ids. Read-only."""

    orrery = _orrery_settings()
    with _slot_session(request.slot) as session:
        anchor_chunk_id = (
            request.anchor_chunk_id
            if request.anchor_chunk_id is not None
            else _default_anchor_chunk_id(session)
        )
        return entity_context(
            session,
            request.entity_ids,
            anchor_chunk_id=anchor_chunk_id,
            recent_events_limit=request.recent_events_limit,
            sunhelm_settings=orrery.get("sunhelm"),
        )


@router.post("/coverage")
async def post_coverage(request: OrreryCoverageRequest) -> dict[str, Any]:
    """Batch coverage analysis over historical anchors. Read-only.

    Each anchor is a full explained dry-run tick, so the anchor count is
    bounded by [orrery.dashboard] coverage_max_anchors.
    """

    orrery = _orrery_settings()
    dashboard = orrery.get("dashboard", {})
    max_anchors = int(dashboard["coverage_max_anchors"])
    epoch_min = int(dashboard["coverage_epoch_min_world_times"])
    window_chunks = (
        request.window_chunks
        if request.window_chunks is not None
        else int(orrery["binding"]["window_chunks"])
    )
    requested = (
        len(request.anchor_chunk_ids)
        if request.anchor_chunk_ids is not None
        else request.count
    )
    if requested > max_anchors:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Coverage request asks for {requested} anchors; "
                f"[orrery.dashboard] coverage_max_anchors is {max_anchors}"
            ),
        )
    with _slot_session(request.slot) as session:
        anchor_chunk_ids = (
            list(request.anchor_chunk_ids)
            if request.anchor_chunk_ids is not None
            else sample_anchor_ids(
                session,
                count=request.count,
                stride=request.stride,
                end_chunk_id=request.end_chunk_id,
            )
        )
        if not anchor_chunk_ids:
            raise HTTPException(
                status_code=400,
                detail="No anchors to analyze: the slot has no narrative chunks",
            )
        return analyze_coverage(
            session,
            BUILTIN_TEMPLATES,
            anchor_chunk_ids=anchor_chunk_ids,
            window_chunks=window_chunks,
            sunhelm_settings=orrery.get("sunhelm"),
            epoch_min_world_times=epoch_min,
            selection_settings=orrery.get("selection"),
            habituation_settings=orrery.get("habituation"),
            package_selection_settings=orrery.get("package_selection"),
            project_settings=orrery.get("projects"),
            fanout_settings=orrery.get("fanout"),
        )


@router.get("/history/adjudications")
async def get_adjudication_history(
    slot: Optional[int] = None,
    template_id: Optional[str] = None,
) -> dict[str, Any]:
    """Adjudication ledger: action rates, lifecycle funnel, defer streaks.

    Read-only. Faceted by adjudication_source in the payload; epoch block
    reports how much of the ledger predates the 063 enrichment.
    """

    with _slot_session(slot) as session:
        return adjudication_history(session, template_id=template_id)


@router.get("/vocab")
async def get_vocab(slot: Optional[int] = None) -> dict[str, Any]:
    """Slot-scoped vocabularies for the what-if drawer's pickers.

    Read-only: active tag and pair-tag vocab (with layer), event types, and
    places. Entity choices come from the resolve payload's entity names.
    """

    with _slot_session(slot) as session:
        tags = [
            dict(row)
            for row in session.execute(
                text(
                    """
                    SELECT tag, category, is_ephemeral
                    FROM tags
                    WHERE NOT deprecated AND synonym_for IS NULL
                    ORDER BY category, tag
                    """
                )
            ).mappings()
        ]
        pair_tags = [
            dict(row)
            for row in session.execute(
                text(
                    """
                    SELECT tag, subject_kinds, object_kinds
                    FROM pair_tags
                    WHERE NOT deprecated
                    ORDER BY tag
                    """
                )
            ).mappings()
        ]
        event_types = [
            dict(row)
            for row in session.execute(
                text(
                    """
                    SELECT type, category
                    FROM event_types
                    WHERE NOT deprecated
                    ORDER BY type
                    """
                )
            ).mappings()
        ]
        places = [
            dict(row)
            for row in session.execute(
                text(
                    """
                    SELECT id, name
                    FROM places
                    ORDER BY name
                    """
                )
            ).mappings()
        ]
    return {
        "tags": tags,
        "pair_tags": pair_tags,
        "event_types": event_types,
        "places": places,
    }
