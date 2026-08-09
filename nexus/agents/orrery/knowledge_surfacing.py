"""Entitlement-first recall and disclosure for Storyteller world knowledge."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
import math
from typing import Any

from sqlalchemy import text

from nexus.agents.memnon.utils.embedding_tables import (
    parse_character_experience_embedding_table_dimensions,
    parse_embedding_table_dimensions,
)
from nexus.agents.orrery.reconstruction import playable_narrative_predicate
from nexus.config.settings_models import (
    OrreryDisclosureSettings,
    OrreryKnowledgeSettings,
    OrreryRecallSettings,
)


logger = logging.getLogger("nexus.orrery.knowledge_surfacing")


class KnowledgeDigest(list[dict[str, Any]]):
    """List-compatible digest carrying private truncation metadata."""

    def __init__(
        self,
        entries: Sequence[dict[str, Any]] = (),
        *,
        truncated: bool = False,
    ) -> None:
        super().__init__(entries)
        self.truncated = truncated


@dataclass(slots=True)
class _Candidate:
    """One actor-owned item that crossed the hard eligibility boundary."""

    kind: str
    candidate_id: int
    character_entity_id: int
    character_name: str
    summary: str
    source_chunk_id: int
    claim_id: int | None
    claim_scope: str | None
    source_tier: str
    immediate_source_entity_id: int | None
    immediate_source_name: str | None
    acquired_at_world_time: datetime | None
    location_id: int | None
    severity: str | None
    salience: float
    freshly_revealed: bool
    current_scene_acquisition: bool
    semantic_fit: float = 0.0
    score: float = 0.0
    mandatory: bool = False
    score_components: dict[str, Any] = field(default_factory=dict)


def _coerce_model(settings: Any, model_type: type[Any], label: str) -> Any:
    """Normalize a settings mapping or Pydantic model."""

    if isinstance(settings, model_type):
        return settings
    if hasattr(settings, "model_dump"):
        settings = settings.model_dump()
    if settings is None:
        settings = {}
    if isinstance(settings, Mapping):
        return model_type.model_validate(dict(settings))
    raise TypeError(f"Orrery {label} settings must be a mapping or Pydantic model")


def _is_sqlalchemy(session_or_cur: Any) -> bool:
    return type(session_or_cur).__module__.startswith("sqlalchemy")


def _execute(session_or_cur: Any, statement: str, parameters: Mapping[str, Any]) -> Any:
    """Execute named SQL through SQLAlchemy or a psycopg-compatible cursor."""

    if _is_sqlalchemy(session_or_cur):
        return session_or_cur.execute(text(statement), dict(parameters))
    cursor_statement = statement.replace("%", "%%")
    for name in sorted(parameters, key=len, reverse=True):
        cursor_statement = cursor_statement.replace(f":{name}", f"%({name})s")
    session_or_cur.execute(cursor_statement, dict(parameters))
    return session_or_cur


def _rows(result: Any) -> list[dict[str, Any]]:
    """Return result rows as dictionaries for either supported database API."""

    mappings = getattr(result, "mappings", None)
    if callable(mappings):
        return [dict(row) for row in mappings()]
    fetched = result.fetchall()
    if fetched and isinstance(fetched[0], Mapping):
        return [dict(row) for row in fetched]
    description = getattr(result, "description", None)
    if description is None:
        raise TypeError("Database result did not expose column metadata")
    names = [column[0] for column in description]
    return [dict(zip(names, row, strict=True)) for row in fetched]


def _eligible_rows(
    session_or_cur: Any,
    *,
    present_entity_ids: Sequence[int],
    anchor_chunk_id: int,
    recent_reveal_window_chunks: int,
) -> list[dict[str, Any]]:
    """Load only possessed claims and actor-owned, timeline-valid experiences."""

    playable_source = playable_narrative_predicate("source_nc")
    statement = f"""
        /* orrery:entitlement_first_recall */
        WITH current_meta AS (
            SELECT cm.chunk_id, cm.world_time, cm.world_layer::text AS world_layer,
                   cm.season, cm.episode, cm.scene,
                   setting.place_id AS setting_place_id
            FROM chunk_metadata cm
            LEFT JOIN LATERAL (
                SELECT pcr.place_id
                FROM place_chunk_references pcr
                WHERE pcr.chunk_id = cm.chunk_id
                  AND pcr.reference_type::text = 'setting'
                ORDER BY pcr.place_id
                LIMIT 1
            ) setting ON TRUE
            WHERE cm.chunk_id = :anchor_chunk_id
        ),
        recent_chunks AS (
            SELECT recent_nc.id
            FROM narrative_chunks recent_nc
            WHERE recent_nc.id <= :anchor_chunk_id
              AND {playable_narrative_predicate('recent_nc')}
            ORDER BY recent_nc.id DESC
            LIMIT :window_chunks
        )
        SELECT 'claim'::text AS candidate_kind,
               awareness.id AS candidate_id,
               awareness.knower_entity_id AS character_entity_id,
               present_character.name AS character_name,
               claim.summary,
               COALESCE(awareness.source_chunk_id, claim.source_chunk_id)
                   AS source_chunk_id,
               claim.id AS claim_id,
               claim.scope AS claim_scope,
               awareness.source_tier,
               awareness.immediate_source_entity_id,
               COALESCE(
                   source_character.name,
                   source_faction.name,
                   source_place.name
               ) AS immediate_source_name,
               awareness.acquired_at_world_time,
               incident.location_id,
               event_type.severity::text AS severity,
               0.0::double precision AS salience,
               EXISTS (
                   SELECT 1
                   FROM world_events reveal
                   WHERE reveal.event_type = 'backstory_revealed'
                     AND reveal.tick_chunk_id IN (SELECT id FROM recent_chunks)
                     AND (reveal.payload ->> 'claim_id')::bigint = claim.id
                     AND (
                         reveal.actor_entity_id = awareness.knower_entity_id
                         OR EXISTS (
                             SELECT 1
                             FROM jsonb_array_elements_text(
                                 COALESCE(
                                     reveal.payload ->
                                         'revealed_participant_entity_ids',
                                     '[]'::jsonb
                                 )
                             ) participant(entity_id)
                             WHERE participant.entity_id::bigint =
                                   awareness.knower_entity_id
                         )
                     )
               ) AS freshly_revealed,
               source_meta.season = current_meta.season
                   AND source_meta.episode = current_meta.episode
                   AND source_meta.scene = current_meta.scene
                   AS current_scene_acquisition,
               current_meta.world_time AS current_world_time,
               current_meta.setting_place_id
        FROM claim_awareness awareness
        JOIN claims claim ON claim.id = awareness.claim_id
        JOIN world_events incident ON incident.id = claim.world_event_id
        JOIN event_types event_type ON event_type.type = incident.event_type
        JOIN characters present_character
          ON present_character.entity_id = awareness.knower_entity_id
        JOIN entities present_entity
          ON present_entity.id = present_character.entity_id
         AND present_entity.is_active = true
        JOIN chunk_metadata source_meta
          ON source_meta.chunk_id = COALESCE(
              awareness.source_chunk_id, claim.source_chunk_id
          )
        JOIN narrative_chunks source_nc ON source_nc.id = source_meta.chunk_id
        CROSS JOIN current_meta
        LEFT JOIN characters source_character
          ON source_character.entity_id = awareness.immediate_source_entity_id
        LEFT JOIN factions source_faction
          ON source_faction.entity_id = awareness.immediate_source_entity_id
        LEFT JOIN places source_place
          ON source_place.entity_id = awareness.immediate_source_entity_id
        WHERE awareness.knower_entity_id = ANY(:present_entity_ids)
          AND source_meta.chunk_id <= :anchor_chunk_id
          AND source_meta.world_layer::text IS NOT DISTINCT FROM
              current_meta.world_layer
          AND {playable_source}
          AND (
              awareness.acquired_at_world_time IS NULL
              OR awareness.acquired_at_world_time <= current_meta.world_time
          )
          AND NOT EXISTS (
              SELECT 1
              FROM backstory_secrets secret
              WHERE secret.claim_id = claim.id AND secret.status = 'latent'
          )

        UNION ALL

        SELECT 'experience'::text AS candidate_kind,
               experience.id AS candidate_id,
               experience.character_entity_id,
               present_character.name AS character_name,
               COALESCE(experience.experience_text, experience.seed_summary)
                   AS summary,
               experience.anchor_chunk_id AS source_chunk_id,
               experience.claim_id,
               claim.scope AS claim_scope,
               experience.basis::text AS source_tier,
               awareness.immediate_source_entity_id,
               COALESCE(
                   source_character.name,
                   source_faction.name,
                   source_place.name
               ) AS immediate_source_name,
               experience.world_time AS acquired_at_world_time,
               experience.location_id,
               experience_severity.severity,
               experience.salience,
               false AS freshly_revealed,
               false AS current_scene_acquisition,
               current_meta.world_time AS current_world_time,
               current_meta.setting_place_id
        FROM character_experiences experience
        JOIN characters present_character
          ON present_character.entity_id = experience.character_entity_id
        JOIN entities present_entity
          ON present_entity.id = present_character.entity_id
         AND present_entity.is_active = true
        JOIN chunk_metadata source_meta
          ON source_meta.chunk_id = experience.anchor_chunk_id
        JOIN narrative_chunks source_nc ON source_nc.id = source_meta.chunk_id
        CROSS JOIN current_meta
        LEFT JOIN claims claim ON claim.id = experience.claim_id
        LEFT JOIN claim_awareness awareness
          ON awareness.id = experience.claim_awareness_id
        LEFT JOIN characters source_character
          ON source_character.entity_id = awareness.immediate_source_entity_id
        LEFT JOIN factions source_faction
          ON source_faction.entity_id = awareness.immediate_source_entity_id
        LEFT JOIN places source_place
          ON source_place.entity_id = awareness.immediate_source_entity_id
        LEFT JOIN LATERAL (
            SELECT event_type.severity::text AS severity
            FROM unnest(experience.world_event_ids) event_identity(event_id)
            JOIN world_events event ON event.id = event_identity.event_id
            JOIN event_types event_type ON event_type.type = event.event_type
            ORDER BY CASE event_type.severity::text
                WHEN 'critical' THEN 4
                WHEN 'major' THEN 3
                WHEN 'moderate' THEN 2
                WHEN 'minor' THEN 1
                ELSE 0
            END DESC
            LIMIT 1
        ) experience_severity ON TRUE
        WHERE experience.character_entity_id = ANY(:present_entity_ids)
          AND experience.invalidation_status = 'valid'
          AND experience.anchor_chunk_id <= :anchor_chunk_id
          AND experience.world_layer::text IS NOT DISTINCT FROM
              current_meta.world_layer
          AND source_meta.world_layer::text IS NOT DISTINCT FROM
              current_meta.world_layer
          AND {playable_source}
          AND (
              experience.world_time IS NULL
              OR experience.world_time <= current_meta.world_time
          )
          AND (
              experience.claim_awareness_id IS NULL
              OR (
                  awareness.knower_entity_id = experience.character_entity_id
                  AND awareness.claim_id = experience.claim_id
              )
          )
          AND NOT EXISTS (
              SELECT 1
              FROM backstory_secrets secret
              WHERE secret.claim_id = experience.claim_id
                AND secret.status = 'latent'
          )
        ORDER BY character_entity_id, candidate_kind, candidate_id
    """
    result = _execute(
        session_or_cur,
        statement,
        {
            "anchor_chunk_id": anchor_chunk_id,
            "window_chunks": recent_reveal_window_chunks,
            "present_entity_ids": list(present_entity_ids),
        },
    )
    return _rows(result)


def _candidate(row: Mapping[str, Any]) -> _Candidate:
    """Validate and normalize one SQL candidate row."""

    acquired = row.get("acquired_at_world_time")
    if acquired is not None and not isinstance(acquired, datetime):
        raise TypeError("Recall acquisition time must be a datetime or NULL")
    kind = str(row["candidate_kind"])
    source_tier = str(row["source_tier"])
    involvement = (
        source_tier if source_tier in {"participant", "witness"} else ("acquisition")
    )
    severity = row.get("severity")
    return _Candidate(
        kind=kind,
        candidate_id=int(row["candidate_id"]),
        character_entity_id=int(row["character_entity_id"]),
        character_name=str(row["character_name"]),
        summary=str(row["summary"]),
        source_chunk_id=int(row["source_chunk_id"]),
        claim_id=int(row["claim_id"]) if row.get("claim_id") is not None else None,
        claim_scope=(
            str(row["claim_scope"]) if row.get("claim_scope") is not None else None
        ),
        source_tier=involvement,
        immediate_source_entity_id=(
            int(row["immediate_source_entity_id"])
            if row.get("immediate_source_entity_id") is not None
            else None
        ),
        immediate_source_name=(
            str(row["immediate_source_name"])
            if row.get("immediate_source_name") is not None
            else None
        ),
        acquired_at_world_time=acquired,
        location_id=(
            int(row["location_id"]) if row.get("location_id") is not None else None
        ),
        severity=str(severity) if severity is not None else None,
        salience=float(row.get("salience") or 0.0),
        freshly_revealed=bool(row.get("freshly_revealed")),
        current_scene_acquisition=bool(row.get("current_scene_acquisition")),
    )


def _embedding_tables(session_or_cur: Any) -> list[str]:
    result = _execute(
        session_or_cur,
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND (
              table_name ~ '^chunk_embeddings_[0-9]+d$'
              OR table_name ~ '^character_experience_embeddings_[0-9]+d$'
          )
        ORDER BY table_name
        """,
        {},
    )
    return [str(row["table_name"]) for row in _rows(result)]


def _semantic_scores(
    session_or_cur: Any,
    *,
    candidates: Sequence[_Candidate],
    current_turn_chunk_id: int,
    missing_score: float,
) -> dict[tuple[str, int], float]:
    """Compare eligible corpus vectors with the stored raw-turn chunk vector."""

    tables = _embedding_tables(session_or_cur)
    chunk_tables = {
        dimensions: table_name
        for table_name in tables
        if (dimensions := parse_embedding_table_dimensions(table_name)) is not None
    }
    experience_tables = {
        dimensions: table_name
        for table_name in tables
        if (
            dimensions := parse_character_experience_embedding_table_dimensions(
                table_name
            )
        )
        is not None
    }
    accumulated: dict[tuple[str, int], list[float]] = {}
    source_chunk_ids = sorted(
        {
            candidate.source_chunk_id
            for candidate in candidates
            if candidate.kind == "claim"
        }
    )
    experience_ids = sorted(
        {
            candidate.candidate_id
            for candidate in candidates
            if candidate.kind == "experience"
        }
    )
    for dimensions, chunk_table in sorted(chunk_tables.items()):
        if source_chunk_ids:
            result = _execute(
                session_or_cur,
                f"""
                SELECT source.chunk_id AS candidate_id,
                       avg(1 - (source.embedding <=> query.embedding)) AS score
                FROM {chunk_table} source
                JOIN {chunk_table} query
                  ON query.chunk_id = :current_turn_chunk_id
                 AND query.model = source.model
                WHERE source.chunk_id = ANY(:candidate_ids)
                GROUP BY source.chunk_id
                """,
                {
                    "current_turn_chunk_id": current_turn_chunk_id,
                    "candidate_ids": source_chunk_ids,
                },
            )
            for row in _rows(result):
                accumulated.setdefault(("claim", int(row["candidate_id"])), []).append(
                    float(row["score"])
                )
        experience_table = experience_tables.get(dimensions)
        if experience_ids and experience_table is not None:
            result = _execute(
                session_or_cur,
                f"""
                SELECT source.experience_id AS candidate_id,
                       avg(1 - (source.embedding <=> query.embedding)) AS score
                FROM {experience_table} source
                JOIN {chunk_table} query
                  ON query.chunk_id = :current_turn_chunk_id
                 AND query.model = source.model
                WHERE source.experience_id = ANY(:candidate_ids)
                GROUP BY source.experience_id
                """,
                {
                    "current_turn_chunk_id": current_turn_chunk_id,
                    "candidate_ids": experience_ids,
                },
            )
            for row in _rows(result):
                accumulated.setdefault(
                    ("experience", int(row["candidate_id"])), []
                ).append(float(row["score"]))

    scores: dict[tuple[str, int], float] = {}
    for candidate in candidates:
        identity = (
            ("claim", candidate.source_chunk_id)
            if candidate.kind == "claim"
            else ("experience", candidate.candidate_id)
        )
        values = accumulated.get(identity)
        scores[(candidate.kind, candidate.candidate_id)] = (
            sum(values) / len(values) if values else missing_score
        )
    return scores


def _score_candidates(
    rows: Sequence[Mapping[str, Any]],
    *,
    session_or_cur: Any,
    current_turn_chunk_id: int,
    settings: OrreryRecallSettings,
) -> list[_Candidate]:
    candidates = [_candidate(row) for row in rows]
    semantics = _semantic_scores(
        session_or_cur,
        candidates=candidates,
        current_turn_chunk_id=current_turn_chunk_id,
        missing_score=settings.missing_embedding_score,
    )
    for candidate, row in zip(candidates, rows, strict=True):
        current_time = row.get("current_world_time")
        if current_time is not None and not isinstance(current_time, datetime):
            raise TypeError("Recall anchor world time must be a datetime or NULL")
        if current_time is not None and candidate.acquired_at_world_time is not None:
            age_hours = max(
                0.0,
                (current_time - candidate.acquired_at_world_time).total_seconds()
                / 3600.0,
            )
            recency = max(0.0, 1.0 - age_hours / settings.recency_horizon_hours)
            decay = math.pow(0.5, age_hours / settings.decay_half_life_hours)
        else:
            age_hours = None
            recency = 0.0
            decay = 1.0
        severity = settings.severity_scores.get(candidate.severity or "", 0.0)
        involvement = settings.involvement_scores[candidate.source_tier]
        setting_place_id = row.get("setting_place_id")
        place_match = float(
            setting_place_id is not None
            and candidate.location_id is not None
            and int(setting_place_id) == candidate.location_id
        )
        semantic = semantics[(candidate.kind, candidate.candidate_id)]
        raw_score = (
            settings.semantic_fit_weight * semantic
            + settings.event_severity_weight * severity
            + settings.actor_involvement_weight * involvement
            + settings.emotional_salience_weight * candidate.salience
            + settings.recency_weight * recency
            + settings.place_match_weight * place_match
        )
        candidate.semantic_fit = semantic
        candidate.score = round(raw_score * decay, 8)
        candidate.mandatory = bool(
            candidate.kind == "claim"
            and candidate.severity == "critical"
            and candidate.current_scene_acquisition
        )
        candidate.score_components = {
            "semantic_fit": round(semantic, 8),
            "event_severity": round(severity, 8),
            "actor_involvement": round(involvement, 8),
            "emotional_salience": round(candidate.salience, 8),
            "recency": round(recency, 8),
            "place_match": round(place_match, 8),
            "age_world_hours": round(age_hours, 8) if age_hours is not None else None,
            "raw_score": round(raw_score, 8),
            "decay_modifier": round(decay, 8),
        }
    return candidates


def _rank_key(candidate: _Candidate) -> tuple[Any, ...]:
    acquired = candidate.acquired_at_world_time
    return (
        -candidate.score,
        -(acquired.timestamp() if acquired is not None else float("-inf")),
        candidate.kind,
        -candidate.candidate_id,
    )


def _round_robin(
    candidates: Sequence[_Candidate],
    *,
    limit: int,
    per_character_limit: int,
    initial_counts: Mapping[int, int] | None = None,
) -> list[_Candidate]:
    """Select fairly across characters while respecting per-character caps."""

    grouped: dict[int, list[_Candidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.character_entity_id, []).append(candidate)
    for values in grouped.values():
        values.sort(key=_rank_key)
    counts = dict(initial_counts or {})
    selected: list[_Candidate] = []
    while len(selected) < limit:
        progressed = False
        for character_id in sorted(grouped):
            if len(selected) >= limit:
                break
            if counts.get(character_id, 0) >= per_character_limit:
                continue
            values = grouped[character_id]
            if not values:
                continue
            selected.append(values.pop(0))
            counts[character_id] = counts.get(character_id, 0) + 1
            progressed = True
        if not progressed:
            break
    return selected


def _select_ranked(
    candidates: Sequence[_Candidate],
    *,
    shared_limit: int,
    settings: OrreryRecallSettings,
) -> tuple[list[_Candidate], dict[tuple[str, int], str]]:
    mandatory = [candidate for candidate in candidates if candidate.mandatory]
    reserved = _round_robin(
        mandatory,
        limit=min(shared_limit, settings.mandatory_reserved_entries),
        per_character_limit=settings.per_character_max_entries,
    )
    selected_ids = {(item.kind, item.candidate_id) for item in reserved}
    counts: dict[int, int] = {}
    for item in reserved:
        counts[item.character_entity_id] = counts.get(item.character_entity_id, 0) + 1
    remaining = [
        candidate
        for candidate in candidates
        if (candidate.kind, candidate.candidate_id) not in selected_ids
    ]
    ranked = _round_robin(
        remaining,
        limit=shared_limit - len(reserved),
        per_character_limit=settings.per_character_max_entries,
        initial_counts=counts,
    )
    selected = reserved + ranked
    for item in ranked:
        counts[item.character_entity_id] = counts.get(item.character_entity_id, 0) + 1
    selected_ids = {(item.kind, item.candidate_id) for item in selected}
    excluded: dict[tuple[str, int], str] = {}
    for candidate in candidates:
        identity = (candidate.kind, candidate.candidate_id)
        if identity in selected_ids:
            continue
        reason = (
            "per_character_cap"
            if counts.get(candidate.character_entity_id, 0)
            >= settings.per_character_max_entries
            else "shared_budget"
        )
        excluded[identity] = reason
    return selected, excluded


def _present_character_ids(
    session_or_cur: Any, present_entity_ids: Sequence[int]
) -> tuple[int, ...]:
    result = _execute(
        session_or_cur,
        """
        SELECT character.entity_id
        FROM characters character
        JOIN entities entity ON entity.id = character.entity_id
        WHERE character.entity_id = ANY(:present_entity_ids)
          AND entity.is_active = true
        ORDER BY character.entity_id
        """,
        {"present_entity_ids": list(present_entity_ids)},
    )
    return tuple(int(row["entity_id"]) for row in _rows(result))


def _disclosure_context(
    session_or_cur: Any,
    *,
    character_ids: Sequence[int],
) -> tuple[
    dict[tuple[int, int], float],
    dict[int, set[int]],
    dict[int, set[int]],
    set[tuple[int, int]],
]:
    if not character_ids:
        return {}, {}, {}, set()
    relationship_result = _execute(
        session_or_cur,
        """
        SELECT source_entity_id, target_entity_id, valence_current
        FROM entity_relationships_v
        WHERE relationship_scope = 'character'
          AND source_entity_id = ANY(:character_ids)
          AND target_entity_id = ANY(:character_ids)
        """,
        {"character_ids": list(character_ids)},
    )
    valences = {
        (int(row["source_entity_id"]), int(row["target_entity_id"])): float(
            row["valence_current"]
        )
        for row in _rows(relationship_result)
        if row.get("valence_current") is not None
    }
    edge_result = _execute(
        session_or_cur,
        """
        SELECT edge.subject_entity_id, edge.object_entity_id, pair_tag.tag,
               subject.kind::text AS subject_kind,
               object.kind::text AS object_kind
        FROM entity_pair_tags edge
        JOIN pair_tags pair_tag ON pair_tag.id = edge.pair_tag_id
        JOIN entities subject ON subject.id = edge.subject_entity_id
        JOIN entities object ON object.id = edge.object_entity_id
        WHERE edge.cleared_at IS NULL
          AND NOT pair_tag.deprecated
          AND (pair_tag.tag LIKE 'status:%' OR pair_tag.tag = 'obligation')
          AND (
              edge.subject_entity_id = ANY(:character_ids)
              OR edge.object_entity_id = ANY(:character_ids)
          )
        """,
        {"character_ids": list(character_ids)},
    )
    affiliations: dict[int, set[int]] = {value: set() for value in character_ids}
    obligations: dict[int, set[int]] = {value: set() for value in character_ids}
    direct_status_edges: set[tuple[int, int]] = set()
    for row in _rows(edge_result):
        subject_id = int(row["subject_entity_id"])
        object_id = int(row["object_entity_id"])
        tag = str(row["tag"])
        if tag.startswith("status:"):
            if row["subject_kind"] == "character" and row["object_kind"] == "faction":
                affiliations.setdefault(subject_id, set()).add(object_id)
            elif row["subject_kind"] == "faction" and row["object_kind"] == "character":
                affiliations.setdefault(object_id, set()).add(subject_id)
            elif (
                row["subject_kind"] == "character" and row["object_kind"] == "character"
            ):
                direct_status_edges.add((subject_id, object_id))
        elif (
            tag == "obligation"
            and row["subject_kind"] == "character"
            and row["object_kind"] == "faction"
        ):
            obligations.setdefault(subject_id, set()).add(object_id)
    return valences, affiliations, obligations, direct_status_edges


def _disclosure_decision(
    candidate: _Candidate,
    *,
    present_character_ids: Sequence[int],
    valences: Mapping[tuple[int, int], float],
    affiliations: Mapping[int, set[int]],
    obligations: Mapping[int, set[int]],
    direct_status_edges: set[tuple[int, int]],
    settings: OrreryDisclosureSettings,
) -> tuple[bool, str, dict[str, Any]]:
    audience = [
        entity_id
        for entity_id in present_character_ids
        if entity_id != candidate.character_entity_id
    ]
    if not audience:
        return (
            True,
            "disclosed",
            {
                "audience_count": 0,
                "secrecy_marker": float(candidate.claim_scope == "private"),
                "relationship_valence": 1.0,
                "status_edge_match": 1.0,
                "role_obligation_risk": 0.0,
                "score": 1.0,
                "threshold": settings.minimum_score,
            },
        )
    relationship = min(
        valences.get(
            (candidate.character_entity_id, audience_id),
            settings.missing_relationship_valence,
        )
        for audience_id in audience
    )
    owner_affiliations = affiliations.get(candidate.character_entity_id, set())
    status_edge_match = sum(
        bool(
            owner_affiliations & affiliations.get(audience_id, set())
            or (candidate.character_entity_id, audience_id) in direct_status_edges
        )
        for audience_id in audience
    ) / len(audience)
    owner_obligations = obligations.get(candidate.character_entity_id, set())
    obligation_risk = float(
        bool(owner_obligations)
        and any(
            not owner_obligations.issubset(affiliations.get(audience_id, set()))
            for audience_id in audience
        )
    )
    secrecy = float(candidate.claim_scope == "private")
    disclosure_score = (
        settings.relationship_valence_weight * relationship
        + settings.shared_status_bonus * status_edge_match
        - settings.secrecy_penalty * secrecy
        - settings.role_obligation_penalty * obligation_risk
    )
    threshold = (
        settings.private_claim_minimum_score if secrecy else settings.minimum_score
    )
    components = {
        "audience_count": len(audience),
        "secrecy_marker": secrecy,
        "relationship_valence": round(relationship, 8),
        "status_edge_match": round(status_edge_match, 8),
        "role_obligation_risk": obligation_risk,
        "score": round(disclosure_score, 8),
        "threshold": threshold,
    }
    if disclosure_score >= threshold:
        return True, "disclosed", components
    if secrecy:
        reason = "secrecy_threshold"
    elif obligation_risk:
        reason = "role_obligation_threshold"
    elif relationship < 0:
        reason = "relationship_threshold"
    else:
        reason = "disclosure_threshold"
    return False, reason, components


def _acquisition(candidate: _Candidate) -> dict[str, Any]:
    if candidate.source_tier in {"participant", "witness"}:
        return {"kind": "firsthand"}
    if candidate.immediate_source_entity_id is not None:
        if not candidate.immediate_source_name:
            raise ValueError(
                "Told knowledge has no display name for immediate source entity "
                f"{candidate.immediate_source_entity_id}"
            )
        return {
            "kind": "told",
            "source_entity_id": candidate.immediate_source_entity_id,
            "source_name": candidate.immediate_source_name,
        }
    return {"kind": "granted"}


def _entry(candidate: _Candidate) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "character_entity_id": candidate.character_entity_id,
        "character_name": candidate.character_name,
        "summary": candidate.summary,
        "acquisition": _acquisition(candidate),
        "acquired_at_world_time": (
            candidate.acquired_at_world_time.isoformat()
            if candidate.acquired_at_world_time is not None
            else None
        ),
        "source": {
            "kind": candidate.kind,
            "id": (
                candidate.claim_id
                if candidate.kind == "claim"
                else candidate.candidate_id
            ),
        },
    }
    if candidate.claim_id is not None:
        entry["claim_id"] = candidate.claim_id
    if candidate.kind == "experience":
        entry["experience_id"] = candidate.candidate_id
    if candidate.freshly_revealed:
        entry["freshly_revealed"] = True
    return entry


def _final_order(entry: Mapping[str, Any]) -> tuple[Any, ...]:
    acquired = entry["acquired_at_world_time"]
    source = entry["source"]
    return (
        int(entry["character_entity_id"]),
        acquired is not None,
        acquired or "",
        str(source["kind"]),
        int(source["id"]),
    )


def _write_trace(
    session_or_cur: Any,
    *,
    turn_id: str,
    anchor_chunk_id: int,
    candidates: Sequence[_Candidate],
    decisions: Mapping[tuple[str, int], tuple[str, str]],
    trace_rows_per_character: int,
) -> None:
    for candidate in candidates:
        decision, reason = decisions[(candidate.kind, candidate.candidate_id)]
        _execute(
            session_or_cur,
            """
            INSERT INTO orrery_recall_trace (
                turn_id, anchor_chunk_id, character_entity_id,
                candidate_kind, candidate_id, claim_id, decision, reason,
                mandatory, score, score_components
            ) VALUES (
                :turn_id, :anchor_chunk_id, :character_entity_id,
                :candidate_kind, :candidate_id, :claim_id, :decision, :reason,
                :mandatory, :score, CAST(:score_components AS jsonb)
            )
            ON CONFLICT (
                turn_id, character_entity_id, candidate_kind, candidate_id
            ) DO UPDATE SET
                anchor_chunk_id = EXCLUDED.anchor_chunk_id,
                claim_id = EXCLUDED.claim_id,
                decision = EXCLUDED.decision,
                reason = EXCLUDED.reason,
                mandatory = EXCLUDED.mandatory,
                score = EXCLUDED.score,
                score_components = EXCLUDED.score_components,
                created_at = now()
            """,
            {
                "turn_id": turn_id,
                "anchor_chunk_id": anchor_chunk_id,
                "character_entity_id": candidate.character_entity_id,
                "candidate_kind": candidate.kind,
                "candidate_id": candidate.candidate_id,
                "claim_id": candidate.claim_id,
                "decision": decision,
                "reason": reason,
                "mandatory": candidate.mandatory,
                "score": candidate.score,
                "score_components": json.dumps(
                    candidate.score_components, sort_keys=True
                ),
            },
        )
    character_ids = sorted({item.character_entity_id for item in candidates})
    if character_ids:
        _execute(
            session_or_cur,
            """
            DELETE FROM orrery_recall_trace
            WHERE id IN (
                SELECT id
                FROM (
                    SELECT id,
                           row_number() OVER (
                               PARTITION BY character_entity_id
                               ORDER BY id DESC
                           ) AS retention_rank
                    FROM orrery_recall_trace
                    WHERE character_entity_id = ANY(:character_ids)
                ) ranked
                WHERE retention_rank > :retention_cap
            )
            """,
            {
                "character_ids": character_ids,
                "retention_cap": trace_rows_per_character,
            },
        )


def build_knowledge_digest_sync(
    session_or_cur: Any,
    *,
    present_entity_ids: Sequence[int],
    anchor_chunk_id: int,
    settings: Any,
    recall_settings: Any = None,
    disclosure_settings: Any = None,
    turn_id: str | None = None,
    current_turn_chunk_id: int | None = None,
) -> list[dict[str, Any]]:
    """Build ranked, audience-filtered knowledge for present characters.

    SPOILER DISCIPLINE -- THIS IS THE GOVERNING CONSTRAINT:
    Eligibility begins with possessed claim-awareness rows and actor-owned
    character experiences only. Global MEMNON results, account payloads,
    sibling accounts, canonical answers, and latent secrets never enter this
    pipeline. Recall decay changes scores only; possession rows are read-only.
    """

    knowledge = _coerce_model(settings, OrreryKnowledgeSettings, "knowledge")
    recall = _coerce_model(recall_settings, OrreryRecallSettings, "recall")
    disclosure = _coerce_model(
        disclosure_settings, OrreryDisclosureSettings, "disclosure"
    )
    if not knowledge.enabled:
        return KnowledgeDigest()
    anchor = int(anchor_chunk_id)
    if anchor <= 0:
        raise ValueError("anchor_chunk_id must be positive")
    present_ids = tuple(sorted({int(entity_id) for entity_id in present_entity_ids}))
    if not present_ids:
        return KnowledgeDigest()
    trace_turn_id = turn_id or f"anchor:{anchor}"
    if not trace_turn_id.strip():
        raise ValueError("turn_id must be nonempty")
    raw_turn_chunk_id = int(current_turn_chunk_id or anchor)

    eligible = _eligible_rows(
        session_or_cur,
        present_entity_ids=present_ids,
        anchor_chunk_id=anchor,
        recent_reveal_window_chunks=knowledge.recent_reveal_window_chunks,
    )
    candidates = _score_candidates(
        eligible,
        session_or_cur=session_or_cur,
        current_turn_chunk_id=raw_turn_chunk_id,
        settings=recall,
    )
    ranked, excluded = _select_ranked(
        candidates,
        shared_limit=knowledge.max_entries,
        settings=recall,
    )
    character_ids = _present_character_ids(session_or_cur, present_ids)
    valences, affiliations, obligations, direct_status_edges = _disclosure_context(
        session_or_cur, character_ids=character_ids
    )
    decisions: dict[tuple[str, int], tuple[str, str]] = {
        identity: ("excluded", reason) for identity, reason in excluded.items()
    }
    included: list[_Candidate] = []
    for candidate in ranked:
        allowed, reason, components = _disclosure_decision(
            candidate,
            present_character_ids=character_ids,
            valences=valences,
            affiliations=affiliations,
            obligations=obligations,
            direct_status_edges=direct_status_edges,
            settings=disclosure,
        )
        candidate.score_components["disclosure"] = components
        identity = (candidate.kind, candidate.candidate_id)
        if allowed:
            decisions[identity] = ("included", reason)
            included.append(candidate)
        else:
            decisions[identity] = ("suppressed", reason)
    for candidate in candidates:
        if (candidate.kind, candidate.candidate_id) in excluded:
            candidate.score_components["disclosure"] = {"evaluated": False}
    _write_trace(
        session_or_cur,
        turn_id=trace_turn_id,
        anchor_chunk_id=anchor,
        candidates=candidates,
        decisions=decisions,
        trace_rows_per_character=recall.trace_rows_per_character,
    )

    truncated = bool(excluded)
    if truncated:
        logger.debug(
            "World knowledge capped at %d entries with a per-character cap of %d; "
            "dropping oldest acquisitions or lower recall scores",
            knowledge.max_entries,
            recall.per_character_max_entries,
        )
    entries = sorted((_entry(candidate) for candidate in included), key=_final_order)
    return KnowledgeDigest(entries, truncated=truncated)
