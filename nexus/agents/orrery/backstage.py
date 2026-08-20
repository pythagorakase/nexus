"""Read-only payload assembly for the IRIS Backstage drawer."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from psycopg2.extras import RealDictCursor
from sqlalchemy import text
from sqlalchemy.orm import Session

from nexus.agents.orrery.drift import derived_rung
from nexus.agents.orrery.history import adjudication_history
from nexus.agents.orrery.reconstruction import playable_narrative_predicate
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
from nexus.memory.correspondence import read_accepted_correspondence


class BackstagePayloadError(ValueError):
    """Expected request-boundary failure while assembling Backstage data."""

    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class BackstageLetter(BaseModel):
    """One committed private letter from a storyteller seat."""

    model_config = ConfigDict(extra="forbid")

    seat: Literal["writer", "gaia", "single_pass"]
    body: str


class BackstageExchange(BaseModel):
    """One committed correspondence exchange."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: int
    turn_label: str
    letters: list[BackstageLetter]


class BackstageHeldThread(BaseModel):
    """One still-open Orrery deferral streak."""

    model_config = ConfigDict(extra="forbid")

    template_id: str
    actor_name: Optional[str] = None
    streak_length: int
    start_tick: int
    start_turn_label: str


class BackstageCorrespondence(BaseModel):
    """Committed storyteller correspondence visible only behind the dev gate."""

    model_config = ConfigDict(extra="forbid")

    digest: Optional[str] = None
    compacted_through_chunk_id: Optional[int] = None
    digest_fresh: bool = False
    exchanges: list[BackstageExchange] = Field(default_factory=list)
    held_threads: list[BackstageHeldThread] = Field(default_factory=list)


class BackstageWrite(BaseModel):
    """One durable state mutation attributed to a committed chunk."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["character", "relation", "place", "faction"]
    label: str
    field: str
    old_value: Any = None
    new_value: Any = None
    operation: Literal["set", "bestow", "clear"] = "set"
    mechanism: Optional[str] = None
    held: bool = False


class BackstageHistoryLine(BaseModel):
    """Counts for one prior committed chunk."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: int
    turn_label: str
    writes: Optional[int] = None
    fired: Optional[int] = None
    pressures: Optional[int] = None
    events: Optional[int] = None


class BackstageStateWrites(BaseModel):
    """Chunk-attributed durable state writes and two-turn history."""

    model_config = ConfigDict(extra="forbid")

    rows: list[BackstageWrite] = Field(default_factory=list)
    history: list[BackstageHistoryLine] = Field(default_factory=list)


class BackstageOrreryRow(BaseModel):
    """One persisted Orrery resolution and its optional emitted event."""

    model_config = ConfigDict(extra="forbid")

    template_id: str
    actor_name: Optional[str] = None
    target_name: Optional[str] = None
    magnitude: Optional[float] = None
    brief: Optional[str] = None
    branch_label: Optional[str] = None
    event_type: Optional[str] = None
    drive_band: Optional[str] = None


class BackstageCounts(BaseModel):
    """Real per-chunk Orrery activity counts."""

    model_config = ConfigDict(extra="forbid")

    fired: int
    pressures: int
    events: int


class BackstageOrrery(BaseModel):
    """Orrery activity for a committed chunk and two-turn history."""

    model_config = ConfigDict(extra="forbid")

    rows: list[BackstageOrreryRow] = Field(default_factory=list)
    counts: BackstageCounts
    history: list[BackstageHistoryLine] = Field(default_factory=list)


class BackstageHeader(BaseModel):
    """Identity and live-generation state for the drawer header."""

    model_config = ConfigDict(extra="forbid")

    slot: int
    chunk_id: int
    chunk_label: str
    turn_label: str
    world_time: Optional[datetime] = None
    skald_status: Literal["writing", "idle"]


class BackstageTurnResponse(BaseModel):
    """Complete read-only Backstage snapshot for one committed turn."""

    model_config = ConfigDict(extra="forbid")

    header: BackstageHeader
    correspondence: BackstageCorrespondence
    state_writes: BackstageStateWrites
    orrery: BackstageOrrery


class BackstageHealthResponse(BaseModel):
    """Gate-discovery response served only when Backstage is registered."""

    model_config = ConfigDict(extra="forbid")

    ok: Literal[True] = True


def _entity_label_sql(alias: str) -> str:
    return f"""
        COALESCE(
            (SELECT c.name FROM characters c WHERE c.entity_id = {alias}.id),
            (SELECT p.name FROM places p WHERE p.entity_id = {alias}.id),
            (SELECT f.name FROM factions f WHERE f.entity_id = {alias}.id),
            {alias}.kind::text || ' #' || {alias}.id::text
        )
    """


def _committed_chunks(
    session: Session, chunk_id: Optional[int]
) -> list[dict[str, Any]]:
    requested_clause = "AND nc.id = :chunk_id" if chunk_id is not None else ""
    playable = playable_narrative_predicate("nc")
    ordinal_playable = playable_narrative_predicate("ordinal")
    row = (
        session.execute(
            text(
                f"""
                SELECT nc.id, cm.slug, cm.world_time,
                       (SELECT count(*) FROM narrative_chunks ordinal
                        WHERE ordinal.id <= nc.id
                          AND {ordinal_playable}) AS turn_number
                FROM narrative_chunks nc
                LEFT JOIN chunk_metadata cm ON cm.chunk_id = nc.id
                WHERE nc.id <= COALESCE(:chunk_id, nc.id)
                  AND {playable}
                {requested_clause}
                ORDER BY nc.id DESC
                LIMIT 1
                """
            ),
            {"chunk_id": chunk_id},
        )
        .mappings()
        .first()
    )
    if row is None:
        if chunk_id is None:
            raise BackstagePayloadError(
                status_code=404, detail="The slot has no committed story turns"
            )
        raise BackstagePayloadError(
            status_code=404,
            detail=f"Committed chunk {chunk_id} does not exist in this slot",
        )
    selected_id = int(row["id"])
    rows = [dict(row)]
    prior = session.execute(
        text(
            f"""
            SELECT nc.id, cm.slug, cm.world_time,
                   (SELECT count(*) FROM narrative_chunks ordinal
                    WHERE ordinal.id <= nc.id
                      AND {ordinal_playable}) AS turn_number
            FROM narrative_chunks nc
            LEFT JOIN chunk_metadata cm ON cm.chunk_id = nc.id
            WHERE nc.id < :chunk_id
              AND {playable}
            ORDER BY nc.id DESC
            LIMIT 2
            """
        ),
        {"chunk_id": selected_id},
    ).mappings()
    rows.extend(dict(prior_row) for prior_row in prior)
    return rows


def _turn_labels(session: Session, chunk_ids: list[int]) -> dict[int, str]:
    """Map persisted chunk IDs to canonical playable-rank labels."""

    if not chunk_ids:
        return {}
    playable = playable_narrative_predicate("nc")
    ordinal_playable = playable_narrative_predicate("ordinal")
    rows = session.execute(
        text(
            f"""
            SELECT nc.id,
                   (SELECT count(*) FROM narrative_chunks ordinal
                    WHERE ordinal.id <= nc.id
                      AND {ordinal_playable}) AS turn_number
            FROM narrative_chunks nc
            WHERE nc.id = ANY(:chunk_ids)
              AND {playable}
            """
        ),
        {"chunk_ids": chunk_ids},
    ).mappings()
    return {int(row["id"]): f"t.{int(row['turn_number'])}" for row in rows}


def _correspondence(session: Session, *, chunk_id: int) -> BackstageCorrespondence:
    connection = session.connection().connection
    driver_connection = getattr(connection, "driver_connection", connection)
    with driver_connection.cursor(cursor_factory=RealDictCursor) as cur:
        context = read_accepted_correspondence(cur, through_chunk_id=chunk_id)
    history = adjudication_history(session, through_tick=chunk_id)
    exchange_ids = [exchange.chunk_id for exchange in context.exchanges[-3:]]
    open_streaks = [
        streak for streak in history["defer_streaks"] if streak["outcome"] == "open"
    ]
    labels = _turn_labels(
        session,
        exchange_ids + [int(streak["start_tick"]) for streak in open_streaks],
    )
    held_threads = [
        BackstageHeldThread(
            template_id=str(streak["template_id"]),
            actor_name=streak.get("actor_name"),
            streak_length=int(streak["length"]),
            start_tick=int(streak["start_tick"]),
            start_turn_label=labels[int(streak["start_tick"])],
        )
        for streak in open_streaks
    ]
    return BackstageCorrespondence(
        digest=context.digest,
        compacted_through_chunk_id=context.compacted_through_chunk_id,
        digest_fresh=context.digest_accepting_chunk_id == chunk_id,
        exchanges=[
            BackstageExchange(
                chunk_id=exchange.chunk_id,
                turn_label=labels[exchange.chunk_id],
                letters=[
                    BackstageLetter(seat=seat, body=body)
                    for seat, body in exchange.letters
                ],
            )
            for exchange in context.exchanges[-3:]
        ],
        held_threads=held_threads,
    )


def _scalar_writes(session: Session, chunk_id: int) -> list[BackstageWrite]:
    rows = session.execute(
        text(
            f"""
            SELECT e.kind::text AS kind,
                   {_entity_label_sql('e')} AS label,
                   delta.field, delta.old_value, delta.new_value
            FROM state_delta_log delta
            LEFT JOIN entities e ON e.id = delta.entity_id
            WHERE delta.source_chunk_id = :chunk_id
              AND delta.writer = 'skald_state_update'
            ORDER BY delta.id
            """
        ),
        {"chunk_id": chunk_id},
    ).mappings()
    result: list[BackstageWrite] = []
    for row in rows:
        kind = (
            row["kind"]
            if row["kind"] in {"character", "place", "faction"}
            else "character"
        )
        result.append(
            BackstageWrite(
                kind=kind,
                label=row["label"] or "world",
                field=str(row["field"]),
                old_value=row["old_value"],
                new_value=row["new_value"],
            )
        )
    return result


def _relationship_writes(session: Session, chunk_id: int) -> list[BackstageWrite]:
    rows = session.execute(
        text(
            """
            SELECT version.old_row,
                   COALESCE(successor.old_row, to_jsonb(current)) AS new_row,
                   first_character.name AS first_name,
                   second_character.name AS second_name
            FROM relationship_versions version
            LEFT JOIN LATERAL (
                SELECT later.old_row
                FROM relationship_versions later
                WHERE later.relationship_table = 'character_relationships'
                  AND later.id > version.id
                  AND later.old_row ->> 'character1_id' =
                      version.old_row ->> 'character1_id'
                  AND later.old_row ->> 'character2_id' =
                      version.old_row ->> 'character2_id'
                ORDER BY later.id
                LIMIT 1
            ) successor ON TRUE
            LEFT JOIN character_relationships current
              ON current.character1_id =
                    (version.old_row ->> 'character1_id')::bigint
             AND current.character2_id =
                    (version.old_row ->> 'character2_id')::bigint
            LEFT JOIN characters first_character
              ON first_character.id =
                    (version.old_row ->> 'character1_id')::bigint
            LEFT JOIN characters second_character
              ON second_character.id =
                    (version.old_row ->> 'character2_id')::bigint
            WHERE version.source_chunk_id = :chunk_id
              AND version.relationship_table = 'character_relationships'
              AND version.operation = 'update'
              AND version.old_row ? 'valence_current'
            ORDER BY version.id
            """
        ),
        {"chunk_id": chunk_id},
    ).mappings()
    result: list[BackstageWrite] = []
    for row in rows:
        old_row = row["old_row"]
        new_row = row["new_row"]
        if new_row is None:
            raise RuntimeError("Attributed relationship update has no successor row")
        label = f"{row['first_name']} → {row['second_name']}"
        for field, storage_field in (
            ("valence", "valence_current"),
            ("relationship_type", "relationship_type"),
            ("dynamic", "dynamic"),
            ("recent_events", "recent_events"),
        ):
            old_value = old_row.get(storage_field)
            new_value = new_row.get(storage_field)
            if old_value == new_value:
                continue
            held = False
            if field == "valence":
                old_valence = Decimal(str(old_value))
                new_valence = Decimal(str(new_value))
                old_value = float(old_valence)
                new_value = float(new_valence)
                held = derived_rung(old_valence) == derived_rung(new_valence)
            result.append(
                BackstageWrite(
                    kind="relation",
                    label=label,
                    field=field,
                    old_value=old_value,
                    new_value=new_value,
                    held=held,
                )
            )
    return result


def _tag_writes(session: Session, chunk_id: int) -> list[BackstageWrite]:
    rows = session.execute(
        text(
            f"""
            SELECT bestowed.kind, bestowed.label, bestowed.tag,
                   bestowed.operation, bestowed.mechanism
            FROM (
                SELECT entity.kind::text AS kind,
                       {_entity_label_sql('entity')} AS label,
                       tag.tag, 'bestow'::text AS operation,
                       NULL::text AS mechanism, entity_tag.id AS sort_id
                FROM entity_tags entity_tag
                JOIN entities entity ON entity.id = entity_tag.entity_id
                JOIN tags tag ON tag.id = entity_tag.tag_id
                WHERE entity_tag.source_chunk_id = :chunk_id
                UNION ALL
                SELECT 'relation'::text AS kind,
                       ({_entity_label_sql('subject')} || ' → ' ||
                        {_entity_label_sql('object')}) AS label,
                       pair_tag.tag, 'bestow'::text AS operation,
                       NULL::text AS mechanism, pair.id AS sort_id
                FROM entity_pair_tags pair
                JOIN entities subject ON subject.id = pair.subject_entity_id
                JOIN entities object ON object.id = pair.object_entity_id
                JOIN pair_tags pair_tag ON pair_tag.id = pair.pair_tag_id
                WHERE pair.source_chunk_id = :chunk_id
                UNION ALL
                SELECT entity.kind::text AS kind,
                       {_entity_label_sql('entity')} AS label,
                       tag.tag, 'clear'::text AS operation,
                       clearance.mechanism::text, clearance.id AS sort_id
                FROM tag_clearance_log clearance
                JOIN entity_tags entity_tag ON entity_tag.id = clearance.entity_tag_id
                JOIN entities entity ON entity.id = entity_tag.entity_id
                JOIN tags tag ON tag.id = entity_tag.tag_id
                WHERE clearance.source_chunk_id = :chunk_id
                UNION ALL
                SELECT 'relation'::text AS kind,
                       ({_entity_label_sql('subject')} || ' → ' ||
                        {_entity_label_sql('object')}) AS label,
                       pair_tag.tag, 'clear'::text AS operation,
                       clearance.mechanism::text, clearance.id AS sort_id
                FROM tag_clearance_log clearance
                JOIN entity_pair_tags pair
                  ON pair.id = clearance.entity_pair_tag_id
                JOIN entities subject ON subject.id = pair.subject_entity_id
                JOIN entities object ON object.id = pair.object_entity_id
                JOIN pair_tags pair_tag ON pair_tag.id = pair.pair_tag_id
                WHERE clearance.source_chunk_id = :chunk_id
            ) bestowed
            ORDER BY bestowed.operation, bestowed.sort_id
            """
        ),
        {"chunk_id": chunk_id},
    ).mappings()
    return [
        BackstageWrite(
            kind=row["kind"],
            label=str(row["label"]),
            field=str(row["tag"]),
            new_value=str(row["tag"]) if row["operation"] == "bestow" else None,
            operation=row["operation"],
            mechanism=row["mechanism"],
        )
        for row in rows
    ]


def _write_count(session: Session, chunk_id: int) -> int:
    return int(
        session.execute(
            text(
                """
                SELECT
                    (SELECT count(*) FROM state_delta_log
                     WHERE source_chunk_id = :chunk_id
                       AND writer = 'skald_state_update') +
                    (SELECT count(*) FROM relationship_versions
                     WHERE source_chunk_id = :chunk_id) +
                    (SELECT count(*) FROM entity_tags
                     WHERE source_chunk_id = :chunk_id) +
                    (SELECT count(*) FROM entity_pair_tags
                     WHERE source_chunk_id = :chunk_id) +
                    (SELECT count(*) FROM tag_clearance_log
                     WHERE source_chunk_id = :chunk_id)
                """
            ),
            {"chunk_id": chunk_id},
        ).scalar_one()
    )


def _orrery_counts(session: Session, chunk_id: int) -> BackstageCounts:
    row = (
        session.execute(
            text(
                """
            SELECT
                (SELECT count(*) FROM orrery_resolutions
                 WHERE tick_chunk_id = :chunk_id) AS fired,
                (SELECT count(*) FROM orrery_scene_pressures
                 WHERE tick_chunk_id = :chunk_id) AS pressures,
                (SELECT count(*) FROM world_events
                 WHERE tick_chunk_id = :chunk_id) AS events
            """
            ),
            {"chunk_id": chunk_id},
        )
        .mappings()
        .one()
    )
    return BackstageCounts(**row)


def _orrery(
    session: Session,
    *,
    chunk_id: int,
    prior_chunks: list[dict[str, Any]],
) -> BackstageOrrery:
    band_by_template = {
        template.id: template.drive_band.value for template in BUILTIN_TEMPLATES
    }
    rows = session.execute(
        text(
            f"""
            SELECT resolution.template_id,
                   {_entity_label_sql('actor')} AS actor_name,
                   COALESCE({_entity_label_sql('direct_target')},
                            {_entity_label_sql('participant_target')}) AS target_name,
                   resolution.magnitude, resolution.brief,
                   pressure.branch_label, event.event_type
            FROM orrery_resolutions resolution
            LEFT JOIN entities actor ON actor.id = resolution.actor_entity_id
            LEFT JOIN world_events event
              ON event.resolution_id = resolution.id
             AND event.tick_chunk_id = resolution.tick_chunk_id
            LEFT JOIN entities direct_target
              ON direct_target.id = event.target_entity_id
            LEFT JOIN LATERAL (
                SELECT participant.entity_id
                FROM world_event_entities participant
                WHERE participant.event_id = event.id
                  AND participant.role = 'target'
                ORDER BY participant.entity_id
                LIMIT 1
            ) target_participant ON TRUE
            LEFT JOIN entities participant_target
              ON participant_target.id = target_participant.entity_id
            LEFT JOIN orrery_scene_pressures pressure
              ON pressure.tick_chunk_id = resolution.tick_chunk_id
             AND pressure.template_id = resolution.template_id
             AND pressure.binding_hash = resolution.binding_hash
            WHERE resolution.tick_chunk_id = :chunk_id
            ORDER BY resolution.id, event.id
            """
        ),
        {"chunk_id": chunk_id},
    ).mappings()
    history: list[BackstageHistoryLine] = []
    for chunk in prior_chunks:
        counts = _orrery_counts(session, int(chunk["id"]))
        history.append(
            BackstageHistoryLine(
                chunk_id=int(chunk["id"]),
                turn_label=f"t.{int(chunk['turn_number'])}",
                fired=counts.fired,
                pressures=counts.pressures,
                events=counts.events,
            )
        )
    return BackstageOrrery(
        rows=[
            BackstageOrreryRow(
                template_id=str(row["template_id"]),
                actor_name=row["actor_name"],
                target_name=row["target_name"],
                magnitude=(
                    float(row["magnitude"]) if row["magnitude"] is not None else None
                ),
                brief=row["brief"],
                branch_label=row["branch_label"],
                event_type=row["event_type"],
                drive_band=band_by_template.get(str(row["template_id"])),
            )
            for row in rows
        ],
        counts=_orrery_counts(session, chunk_id),
        history=history,
    )


def build_backstage_turn(
    session: Session,
    *,
    slot: int,
    chunk_id: Optional[int] = None,
) -> BackstageTurnResponse:
    """Assemble the latest or requested committed Backstage turn snapshot."""

    chunks = _committed_chunks(session, chunk_id)
    selected = chunks[0]
    selected_id = int(selected["id"])
    writing = bool(
        session.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM narrative_generation_lease lease
                    JOIN narrative_generation_sessions generation
                      ON generation.session_id = lease.session_id
                    WHERE lease.id = TRUE
                      AND lease.expires_at > now()
                      AND generation.status = 'initiated'
                )
                """
            )
        ).scalar_one()
    )
    writes = (
        _scalar_writes(session, selected_id)
        + _relationship_writes(session, selected_id)
        + _tag_writes(session, selected_id)
    )
    write_history = [
        BackstageHistoryLine(
            chunk_id=int(chunk["id"]),
            turn_label=f"t.{int(chunk['turn_number'])}",
            writes=_write_count(session, int(chunk["id"])),
        )
        for chunk in chunks[1:]
    ]
    return BackstageTurnResponse(
        header=BackstageHeader(
            slot=slot,
            chunk_id=selected_id,
            chunk_label=selected["slug"] or f"chunk {selected_id}",
            turn_label=f"t.{int(selected['turn_number'])}",
            world_time=selected["world_time"],
            skald_status="writing" if writing else "idle",
        ),
        correspondence=_correspondence(session, chunk_id=selected_id),
        state_writes=BackstageStateWrites(rows=writes, history=write_history),
        orrery=_orrery(session, chunk_id=selected_id, prior_chunks=chunks[1:]),
    )
