"""Deterministic actor-owned experience formation and scene rendering."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Optional, Sequence
from uuid import uuid4

from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, ConfigDict, Field

from nexus.agents.orrery.epistemics import (
    CLAIM_BIRTH_ROLE_POLICY,
    PARTICIPANT_ROLES,
    WITNESS_ROLES,
)
from nexus.agents.orrery.player_identity import canonical_player_entity_id
from nexus.config.settings_models import OrreryExperienceSettings
from nexus.telemetry.usage import usage_context


logger = logging.getLogger("nexus.orrery.experiences")

RENDERER_VERSION = "experience-renderer-v1"
_POSTGRES_BIGINT_MAX = 9_223_372_036_854_775_807
_PLAYER_EXCLUSION_JOB_ERROR = (
    "Experience render job contains a player-owned seed while "
    "include_player_character is false"
)
_PROMPT_PATH = (
    Path(__file__).resolve().parents[3] / "prompts" / "experience_renderer.md"
)
_CAPITALIZED_SEQUENCE = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:[ '-][A-Z][A-Za-z0-9]*)*\b")
_SENTENCE_INITIAL_ALLOWLIST = frozenset(
    {
        "a",
        "above",
        "across",
        "after",
        "afternoon",
        "again",
        "against",
        "all",
        "almost",
        "along",
        "already",
        "although",
        "always",
        "among",
        "an",
        "and",
        "around",
        "as",
        "at",
        "away",
        "back",
        "before",
        "behind",
        "below",
        "beside",
        "between",
        "beyond",
        "because",
        "both",
        "but",
        "by",
        "despite",
        "down",
        "during",
        "each",
        "early",
        "either",
        "even",
        "evening",
        "ever",
        "every",
        "everything",
        "except",
        "first",
        "for",
        "from",
        "he",
        "here",
        "how",
        "i",
        "if",
        "in",
        "inside",
        "instead",
        "into",
        "it",
        "just",
        "last",
        "later",
        "less",
        "like",
        "maybe",
        "more",
        "morning",
        "much",
        "my",
        "near",
        "nearly",
        "neither",
        "never",
        "next",
        "night",
        "no",
        "none",
        "not",
        "nothing",
        "now",
        "once",
        "of",
        "often",
        "on",
        "only",
        "out",
        "outside",
        "over",
        "our",
        "perhaps",
        "please",
        "quite",
        "rather",
        "she",
        "since",
        "some",
        "someone",
        "something",
        "sometimes",
        "soon",
        "so",
        "still",
        "that",
        "the",
        "there",
        "then",
        "they",
        "this",
        "though",
        "through",
        "throughout",
        "today",
        "tomorrow",
        "tonight",
        "to",
        "too",
        "toward",
        "towards",
        "until",
        "unless",
        "under",
        "up",
        "upon",
        "badly",
        "being",
        "oddly",
        "sadly",
        "truly",
        "very",
        "we",
        "well",
        "what",
        "when",
        "whenever",
        "where",
        "wherever",
        "whether",
        "while",
        "who",
        "why",
        "within",
        "with",
        "without",
        "yes",
        "yesterday",
        "yet",
    }
)
# Short inflectional suffixes exempt a sentence-initial token only when the
# token is long enough that the suffix is a real inflection: "Sitting" and
# "Finally" are ordinary words, "Molly", "Ned", and "King" are names
# (automated Claude review on PR #739).
_SHORT_NON_NAME_SUFFIXES = ("ing", "ed", "ly")
_SHORT_SUFFIX_MIN_LENGTH = 6
_LONG_NON_NAME_SUFFIXES = (
    "tion",
    "sion",
    "ness",
    "ment",
    "ward",
    "wards",
    "ever",
    "where",
    "thing",
    "body",
    "one",
)


def _has_non_name_suffix(token: str) -> bool:
    if token.endswith(_SHORT_NON_NAME_SUFFIXES):
        return len(token) >= _SHORT_SUFFIX_MIN_LENGTH
    return token.endswith(_LONG_NON_NAME_SUFFIXES)


_CONTRACTION_SUFFIX = re.compile(r"['’](?:d|ll|m|re|s|ve)\b", re.IGNORECASE)
_FIRST_PERSON = re.compile(r"\b(?:I|me|my|mine|we|us|our|ours)\b", re.IGNORECASE)
_SENTENCE = re.compile(r"(?<=[.!?])(?:[\"']?\s+|$)")
_ACQUISITION_RECEIPT = re.compile(
    r"\b(?:told|heard|learned|informed|received|read|listened|account|"
    r"message|report)\b",
    re.IGNORECASE,
)
_ACQUISITION_WITNESS = re.compile(
    r"\b(?:saw|watched|witnessed|observed|looked on|was there)\b",
    re.IGNORECASE,
)
_ACQUISITION_CANDIDATES_SQL = """
    SELECT ca.id AS awareness_id, ca.claim_id, ca.knower_entity_id,
           ca.source_tier, ca.acquired_at_world_time,
           ca.source_chunk_id AS anchor_chunk_id,
           c.summary AS claim_summary, c.account_label,
           c.world_event_id AS incident_event_id,
           character.name, character.summary, character.background,
           character.personality,
           delivery.id AS delivery_event_id,
           incident.location_id,
           metadata.world_time AS anchor_world_time,
           metadata.world_layer::text AS anchor_world_layer
    FROM claim_awareness ca
    JOIN claims c ON c.id = ca.claim_id
    JOIN characters character ON character.entity_id = ca.knower_entity_id
    JOIN world_events incident ON incident.id = c.world_event_id
    JOIN chunk_metadata metadata ON metadata.chunk_id = ca.source_chunk_id
    LEFT JOIN LATERAL (
        SELECT event.id
        FROM world_events event
        WHERE event.tick_chunk_id = ca.source_chunk_id
          AND event.payload ->> 'awareness_id' = ca.id::text
        ORDER BY event.id
        LIMIT 1
    ) delivery ON TRUE
    LEFT JOIN character_experiences existing
      ON existing.claim_awareness_id = ca.id
    WHERE ca.source_chunk_id <= %s
      AND ca.source_tier IN ('told', 'granted')
      AND existing.id IS NULL
    ORDER BY ca.id
    FOR UPDATE OF ca
"""
_ENQUEUE_CANDIDATES_SQL = """
    SELECT experience.id, experience.source_digest
    FROM character_experiences experience
    WHERE experience.anchor_chunk_id <= %s
      AND experience.world_layer::text = %s
      AND experience.invalidation_status = 'valid'
      AND experience.experience_text IS NULL
      AND (%s IS NULL OR experience.character_entity_id <> %s)
      AND NOT EXISTS (
          SELECT 1
          FROM character_experience_jobs prior_job
          WHERE prior_job.experience_ids @> ARRAY[experience.id]::bigint[]
            AND prior_job.state IN ('queued', 'leased', 'failed')
      )
    ORDER BY experience.id
"""


class ExperienceRecollection(BaseModel):
    """One provider-rendered recollection keyed to its durable seed."""

    experience_id: int = Field(gt=0)
    experience_text: str = Field(min_length=1)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class ExperienceRenderBatch(BaseModel):
    """Complete structured response for one scene roster."""

    recollections: list[ExperienceRecollection] = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class RenderValidation:
    """Per-experience content validation outcome for one structured batch."""

    validated: dict[int, str]
    rejected: dict[int, str]


class ExperienceLeaseLostError(RuntimeError):
    """Raised when a stale scene worker attempts a fenced write."""


class ExperienceSourceStaleError(RuntimeError):
    """Raised when a scene job's immutable seed batch no longer matches."""


class MalformedExperienceEventError(ValueError):
    """A canonical event row cannot yield a safe experience receipt."""

    def __init__(
        self,
        *,
        event_id: int,
        reason_code: str,
        reason: str,
    ) -> None:
        self.event_id = event_id
        self.reason_code = reason_code
        self.reason = reason
        super().__init__(reason)


def experience_settings(settings: Mapping[str, Any]) -> OrreryExperienceSettings:
    """Validate the experience subsection from a full settings mapping."""

    orrery = settings.get("orrery") if "orrery" in settings else settings
    raw = (orrery or {}).get("experiences") or {}
    if isinstance(raw, OrreryExperienceSettings):
        return raw
    return OrreryExperienceSettings.model_validate(raw)


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, Mapping):
        return row[key]
    return row[index]


def _json_mapping(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, Mapping):
        raise ValueError(f"Expected JSON object, got {type(value).__name__}")
    return value


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _eligible_character(row: Mapping[str, Any], cfg: OrreryExperienceSettings) -> bool:
    return sum(
        bool(str(row.get(field) or "").strip()) for field in cfg.dossier_fields
    ) >= (cfg.minimum_dossier_fields)


def _numeric_valences(value: Any, *, parent_key: str = "") -> Iterable[float]:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            yield from _numeric_valences(nested, parent_key=str(key))
        return
    if isinstance(value, list):
        for nested in value:
            yield from _numeric_valences(nested, parent_key=parent_key)
        return
    if "valence" not in parent_key.casefold() or isinstance(value, bool):
        return
    match = re.match(r"\s*([+-]?\d+(?:\.\d+)?)", str(value))
    if match:
        numeric = abs(float(match.group(1)))
        yield min(1.0, numeric if numeric <= 1.0 else numeric / 5.0)


def _presence_duration(
    cur: Any,
    *,
    character_entity_id: int,
    anchor_chunk_id: int,
    world_layer: str,
    cap: int,
) -> int:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM chunk_character_references ccr
            JOIN characters c ON c.id = ccr.character_id
            WHERE ccr.chunk_id = recent.chunk_id
              AND ccr.reference::text = 'present'
              AND c.entity_id = %s
        ) AS present
        FROM (
            SELECT cm.chunk_id
            FROM chunk_metadata cm
            WHERE cm.chunk_id <= %s
              AND cm.world_layer::text = %s
            ORDER BY cm.chunk_id DESC
            LIMIT %s
        ) AS recent
        ORDER BY recent.chunk_id DESC
        """,
        (character_entity_id, anchor_chunk_id, world_layer, cap),
    )
    duration = 0
    for row in cur.fetchall():
        if not bool(_row_value(row, "present", 0)):
            break
        duration += 1
    return duration


def _salience(
    *,
    events: Sequence[Mapping[str, Any]],
    presence_duration: int,
    cfg: OrreryExperienceSettings,
) -> float:
    magnitude = max(
        (abs(float(row.get("magnitude") or 0.0)) for row in events), default=0.0
    )
    valence = max(
        (
            candidate
            for row in events
            for candidate in _numeric_valences(_json_mapping(row.get("state_delta")))
        ),
        default=0.0,
    )
    presence = min(1.0, presence_duration / cfg.presence_duration_cap_chunks)
    return round(
        min(
            1.0,
            cfg.magnitude_weight * min(1.0, magnitude)
            + cfg.valence_delta_weight * valence
            + cfg.presence_duration_weight * presence,
        ),
        6,
    )


def _event_fact(row: Mapping[str, Any]) -> str:
    actor = str(row.get("actor_name") or "an unnamed actor")
    target = row.get("target_name")
    location = row.get("location_name")
    payload = _json_mapping(row.get("payload"))
    detail = payload.get("narrative_stub") or payload.get("branch_label")
    fact = f"{row['event_type']}: {actor}"
    if target:
        fact += f" affected {target}"
    if location:
        fact += f" at {location}"
    if detail:
        fact += f" ({str(detail).strip()})"
    return fact + "."


def _public_audience_entity_ids(row: Mapping[str, Any]) -> frozenset[int]:
    """Return an emitter-declared audience only for explicitly public events."""

    event_id = int(row["id"])
    raw_payload = row.get("payload")
    if raw_payload is None:
        raise MalformedExperienceEventError(
            event_id=event_id,
            reason_code="malformed_payload",
            reason=f"Event {event_id} payload must be a JSON object, not null",
        )
    try:
        payload = _json_mapping(raw_payload)
    except (TypeError, ValueError) as exc:
        raise MalformedExperienceEventError(
            event_id=event_id,
            reason_code="malformed_payload",
            reason=f"Event {event_id} payload must be a JSON object: {exc}",
        ) from exc
    if payload.get("on_screen_public") is not True:
        return frozenset()
    raw_audience = payload.get("audience_entity_ids")
    if not isinstance(raw_audience, list):
        raise MalformedExperienceEventError(
            event_id=event_id,
            reason_code="malformed_audience_container",
            reason=(
                f"Public event {event_id} must declare audience_entity_ids as a list"
            ),
        )
    audience: set[int] = set()
    for index, raw_id in enumerate(raw_audience):
        if isinstance(raw_id, bool):
            raise MalformedExperienceEventError(
                event_id=event_id,
                reason_code="invalid_audience_id",
                reason=(
                    f"Public event {event_id} audience index {index} has invalid "
                    f"entity id {raw_id!r}"
                ),
            )
        try:
            entity_id = int(raw_id)
        except (TypeError, ValueError, OverflowError) as exc:
            raise MalformedExperienceEventError(
                event_id=event_id,
                reason_code="invalid_audience_id",
                reason=(
                    f"Public event {event_id} audience index {index} has invalid "
                    f"entity id {raw_id!r}"
                ),
            ) from exc
        if entity_id <= 0 or entity_id > _POSTGRES_BIGINT_MAX:
            raise MalformedExperienceEventError(
                event_id=event_id,
                reason_code="invalid_audience_id",
                reason=(
                    f"Public event {event_id} audience index {index} has invalid "
                    f"entity id {raw_id!r}"
                ),
            )
        audience.add(entity_id)
    return frozenset(audience)


def _event_receipts(row: Mapping[str, Any]) -> dict[int, str]:
    """Derive actor-owned receipt bases from canonical event roles and policy."""

    event_id = int(row["id"])
    event_type = str(row["event_type"])
    birth_roles = CLAIM_BIRTH_ROLE_POLICY.get(event_type)
    receipts: dict[int, str] = {}
    raw_participants = row.get("participants")
    if raw_participants is None:
        raw_participants = []
    if not isinstance(raw_participants, list):
        raise MalformedExperienceEventError(
            event_id=event_id,
            reason_code="malformed_participant_receipt",
            reason=f"Event {event_id} participants must be a list",
        )
    for index, participant in enumerate(raw_participants):
        if not isinstance(participant, Mapping):
            raise MalformedExperienceEventError(
                event_id=event_id,
                reason_code="malformed_participant_receipt",
                reason=(
                    f"Event {event_id} participant index {index} must be an object"
                ),
            )
        try:
            raw_entity_id = participant["entity_id"]
            raw_role = participant["role"]
            if isinstance(raw_entity_id, bool):
                raise ValueError("boolean entity id")
            entity_id = int(raw_entity_id)
            role = str(raw_role).strip()
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise MalformedExperienceEventError(
                event_id=event_id,
                reason_code="malformed_participant_receipt",
                reason=(
                    f"Event {event_id} participant index {index} has malformed "
                    "entity_id or role"
                ),
            ) from exc
        if entity_id <= 0 or entity_id > _POSTGRES_BIGINT_MAX or not role:
            raise MalformedExperienceEventError(
                event_id=event_id,
                reason_code="malformed_participant_receipt",
                reason=(
                    f"Event {event_id} participant index {index} has malformed "
                    "entity_id or role"
                ),
            )
        if role in PARTICIPANT_ROLES and (birth_roles is None or role in birth_roles):
            receipts[entity_id] = "participant"
        elif role in WITNESS_ROLES and birth_roles is not None and role in birth_roles:
            receipts.setdefault(entity_id, "witness")
    for entity_id in _public_audience_entity_ids(row):
        receipts.setdefault(entity_id, "witness")
    return receipts


def _insert_experience(
    cur: Any,
    *,
    character_entity_id: int,
    anchor_chunk_id: int,
    world_event_ids: Sequence[int],
    claim_id: Optional[int],
    claim_awareness_id: Optional[int],
    basis: str,
    location_id: Optional[int],
    world_time: Any,
    seed_summary: str,
    salience: float,
    world_layer: str,
) -> bool:
    canonical_ids = sorted(set(int(value) for value in world_event_ids))
    source_digest = _digest(
        {
            "character_entity_id": character_entity_id,
            "anchor_chunk_id": anchor_chunk_id,
            "world_event_ids": canonical_ids,
            "claim_id": claim_id,
            "claim_awareness_id": claim_awareness_id,
            "basis": basis,
            "location_id": location_id,
            "world_time": world_time,
            "seed_summary": seed_summary,
            # Mechanical mood rows are destructively reapplied. They cannot
            # participate in a seed whose identity must derive only from
            # append-only event and receipt state.
            "emotion": None,
            "salience": salience,
            "world_layer": world_layer,
        }
    )
    cur.execute(
        """
        INSERT INTO character_experiences (
            character_entity_id, anchor_chunk_id, world_event_ids,
            claim_id, claim_awareness_id, basis, location_id, world_time,
            seed_summary, emotion, salience, source_digest, world_layer
        ) VALUES (
            %s, %s, %s, %s, %s, %s::character_experience_basis, %s, %s,
            %s, NULL, %s, %s, %s::world_layer_type
        )
        RETURNING id
        """,
        (
            character_entity_id,
            anchor_chunk_id,
            canonical_ids,
            claim_id,
            claim_awareness_id,
            basis,
            location_id,
            world_time,
            seed_summary,
            salience,
            source_digest,
            world_layer,
        ),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("Experience insert returned no durable row")
    return True


def seed_character_experiences_sync(
    conn: Any,
    *,
    anchor_chunk_id: int,
    settings: Mapping[str, Any],
    warning_sink: Optional[list[dict[str, Any]]] = None,
) -> int:
    """Sweep and seed every unformed event at or before an accepted chunk."""

    cfg = experience_settings(settings)
    if not cfg.enabled:
        return 0
    inserted = 0
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT 1 FROM chunk_metadata WHERE chunk_id = %s",
            (anchor_chunk_id,),
        )
        if cur.fetchone() is None:
            raise RuntimeError(
                f"Experience anchor chunk {anchor_chunk_id} has no metadata"
            )
        player_entity_id = (
            None if cfg.include_player_character else canonical_player_entity_id(cur)
        )

        # Lock the complete direct-seed event closure before reading owner
        # coverage. Supersession takes this same ordered lock set before it
        # invalidates a seed, so coverage and formation stamps cannot race that
        # invalidation transaction.
        cur.execute(
            """
            WITH candidate_events AS MATERIALIZED (
                SELECT id
                FROM world_events
                WHERE tick_chunk_id <= %s
                  AND experiences_formed_at IS NULL
                  AND experiences_quarantined_at IS NULL
                  AND superseded_by_event_id IS NULL
            ),
            affected_event_ids AS (
                SELECT candidate.id
                FROM candidate_events candidate

                UNION

                SELECT source.event_id
                FROM character_experiences experience
                CROSS JOIN LATERAL unnest(experience.world_event_ids)
                    source(event_id)
                WHERE experience.claim_awareness_id IS NULL
                  AND experience.invalidation_status = 'valid'
                  AND EXISTS (
                      SELECT 1
                      FROM candidate_events candidate
                      WHERE experience.world_event_ids
                          @> ARRAY[candidate.id]::bigint[]
                  )
            )
            SELECT event.id, candidate.id IS NOT NULL AS is_candidate
            FROM world_events event
            JOIN affected_event_ids affected ON affected.id = event.id
            LEFT JOIN candidate_events candidate ON candidate.id = event.id
            ORDER BY event.id
            FOR UPDATE OF event
            """,
            (anchor_chunk_id,),
        )
        locked_rows = list(cur.fetchall())
        candidate_event_ids = [
            int(row["id"]) for row in locked_rows if bool(row["is_candidate"])
        ]

        cur.execute(
            """
            SELECT e.id, e.tick_chunk_id, e.event_type, e.actor_entity_id,
                   e.target_entity_id, e.location_id, e.magnitude, e.payload,
                   e.resolution_id, e.source::text AS event_source,
                   e.world_layer::text AS event_world_layer,
                   actor.name AS actor_name, target.name AS target_name,
                   place.name AS location_name, r.state_delta,
                   metadata.world_time AS anchor_world_time,
                   metadata.world_layer::text AS anchor_world_layer,
                   setting.place_id AS setting_place_id,
                   COALESCE(participants.rows, '[]'::jsonb) AS participants
            FROM world_events e
            JOIN chunk_metadata metadata ON metadata.chunk_id = e.tick_chunk_id
            LEFT JOIN LATERAL (
                SELECT pcr.place_id
                FROM place_chunk_references pcr
                WHERE pcr.chunk_id = e.tick_chunk_id
                  AND pcr.reference_type::text = 'setting'
                ORDER BY pcr.place_id
                LIMIT 1
            ) setting ON TRUE
            LEFT JOIN LATERAL (
                SELECT jsonb_agg(
                           jsonb_build_object(
                               'entity_id', wee.entity_id,
                               'role', wee.role::text
                           )
                           ORDER BY wee.entity_id, wee.role::text
                       ) AS rows
                FROM world_event_entities wee
                WHERE wee.event_id = e.id
            ) participants ON TRUE
            LEFT JOIN entity_names_v actor ON actor.id = e.actor_entity_id
            LEFT JOIN entity_names_v target ON target.id = e.target_entity_id
            LEFT JOIN places place ON place.id = e.location_id
            LEFT JOIN orrery_resolutions r ON r.id = e.resolution_id
            WHERE e.id = ANY(%s::bigint[])
              AND e.experiences_formed_at IS NULL
              AND e.experiences_quarantined_at IS NULL
              AND e.superseded_by_event_id IS NULL
            ORDER BY e.id
            """,
            (candidate_event_ids,),
        )
        events = [dict(row) for row in cur.fetchall()]
        receipt_owners_by_event: dict[int, dict[int, str]] = {}
        processable_events: list[dict[str, Any]] = []
        for event in events:
            event_id = int(event["id"])
            try:
                receipt_owners_by_event[event_id] = _event_receipts(event)
            except MalformedExperienceEventError as exc:
                cur.execute(
                    """
                    UPDATE world_events
                    SET experiences_quarantined_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND experiences_formed_at IS NULL
                      AND experiences_quarantined_at IS NULL
                    RETURNING id
                    """,
                    (event_id,),
                )
                quarantined = cur.fetchone()
                if quarantined is None or int(quarantined["id"]) != event_id:
                    raise RuntimeError(
                        "Malformed experience event changed while being "
                        f"quarantined: {event_id}"
                    )
                warning = {
                    "code": "experience_event_quarantined",
                    "message": (
                        f"Experience formation quarantined malformed world event "
                        f"{event_id}: {exc.reason}"
                    ),
                    "world_event_id": event_id,
                    "event_type": str(event["event_type"]),
                    "reason_code": exc.reason_code,
                    "reason": exc.reason,
                }
                logger.error(
                    "Quarantined malformed Orrery experience event %s (%s): %s",
                    event_id,
                    exc.reason_code,
                    exc.reason,
                    extra={
                        "event": "orrery_experience_event_quarantined",
                        "world_event_id": event_id,
                        "world_event_type": str(event["event_type"]),
                        "world_event_tick_chunk_id": int(event["tick_chunk_id"]),
                        "world_event_actor_entity_id": event.get("actor_entity_id"),
                        "world_event_target_entity_id": event.get("target_entity_id"),
                        "world_event_location_id": event.get("location_id"),
                        "world_event_resolution_id": event.get("resolution_id"),
                        "world_event_source": event.get("event_source"),
                        "world_event_world_layer": event.get("event_world_layer"),
                        "quarantine_reason_code": exc.reason_code,
                        "quarantine_reason": exc.reason,
                    },
                )
                if warning_sink is not None:
                    warning_sink.append(warning)
                continue
            processable_events.append(event)
        events = processable_events
        represented_pairs: set[tuple[int, int]] = set()
        if events:
            cur.execute(
                """
                SELECT candidate.event_id, experience.character_entity_id
                FROM unnest(%s::bigint[]) candidate(event_id)
                JOIN character_experiences experience
                  ON experience.claim_awareness_id IS NULL
                 AND experience.invalidation_status = 'valid'
                 AND experience.world_event_ids @> ARRAY[candidate.event_id]
                GROUP BY candidate.event_id, experience.character_entity_id
                ORDER BY candidate.event_id, experience.character_entity_id
                """,
                ([int(event["id"]) for event in events],),
            )
            represented_pairs = {
                (int(row["event_id"]), int(row["character_entity_id"]))
                for row in cur.fetchall()
            }
        receipts: dict[tuple[int, int, str], list[dict[str, Any]]] = {}
        for event in events:
            event_id = int(event["id"])
            for entity_id, basis in receipt_owners_by_event[event_id].items():
                if (event_id, entity_id) in represented_pairs:
                    continue
                key = (int(event["tick_chunk_id"]), entity_id, basis)
                receipts.setdefault(key, []).append(event)
        receipt_entity_ids = sorted(
            {entity_id for _event_anchor, entity_id, _basis in receipts}
        )
        eligible_by_id: dict[int, dict[str, Any]] = {}
        if receipt_entity_ids:
            cur.execute(
                """
                SELECT entity_id, name, summary, background, personality
                FROM characters
                WHERE entity_id = ANY(%s)
                ORDER BY entity_id
                """,
                (receipt_entity_ids,),
            )
            eligible_by_id = {
                int(row["entity_id"]): dict(row)
                for row in cur.fetchall()
                if _eligible_character(row, cfg)
                and (
                    player_entity_id is None
                    or int(row["entity_id"]) != player_entity_id
                )
            }
        ordered_receipts = sorted(
            receipts.items(),
            key=lambda item: (
                min(int(event["id"]) for event in item[1]),
                item[0][1],
                item[0][2],
            ),
        )
        for (event_anchor, character_id, basis), owned_events in ordered_receipts:
            character = eligible_by_id.get(character_id)
            if character is None:
                continue
            metadata = owned_events[0]
            world_time = metadata.get("anchor_world_time")
            world_layer = str(metadata["anchor_world_layer"])
            duration = _presence_duration(
                cur,
                character_entity_id=character_id,
                anchor_chunk_id=event_anchor,
                world_layer=world_layer,
                cap=cfg.presence_duration_cap_chunks,
            )
            location_id = next(
                (
                    int(row["location_id"])
                    for row in owned_events
                    if row.get("location_id")
                ),
                metadata.get("setting_place_id"),
            )
            basis_phrase = "participated in" if basis == "participant" else "witnessed"
            facts = " ".join(_event_fact(row) for row in owned_events)
            seed_summary = (
                f"{character['name']} {basis_phrase} the accepted scene at "
                f"{world_time.isoformat() if world_time else 'an unknown world time'}. "
                f"{facts}"
            )
            inserted += int(
                _insert_experience(
                    cur,
                    character_entity_id=character_id,
                    anchor_chunk_id=event_anchor,
                    world_event_ids=[int(row["id"]) for row in owned_events],
                    claim_id=None,
                    claim_awareness_id=None,
                    basis=basis,
                    location_id=location_id,
                    world_time=world_time,
                    seed_summary=seed_summary,
                    salience=_salience(
                        events=owned_events,
                        presence_duration=duration,
                        cfg=cfg,
                    ),
                    world_layer=world_layer,
                )
            )

        cur.execute(
            _ACQUISITION_CANDIDATES_SQL,
            (anchor_chunk_id,),
        )
        for acquisition in (dict(row) for row in cur.fetchall()):
            if not _eligible_character(acquisition, cfg):
                continue
            character_id = int(acquisition["knower_entity_id"])
            if player_entity_id is not None and character_id == player_entity_id:
                continue
            source_ids = [int(acquisition["incident_event_id"])]
            if acquisition.get("delivery_event_id") is not None:
                source_ids.append(int(acquisition["delivery_event_id"]))
            seed_summary = (
                f"{acquisition['name']} acquired the "
                f"{acquisition['account_label']} account by being "
                f"{acquisition['source_tier']}: {acquisition['claim_summary']}"
            )
            acquisition_anchor = int(acquisition["anchor_chunk_id"])
            acquisition_world_time = acquisition.get("anchor_world_time")
            inserted += int(
                _insert_experience(
                    cur,
                    character_entity_id=character_id,
                    anchor_chunk_id=acquisition_anchor,
                    world_event_ids=source_ids,
                    claim_id=int(acquisition["claim_id"]),
                    claim_awareness_id=int(acquisition["awareness_id"]),
                    basis="acquisition",
                    location_id=acquisition.get("location_id"),
                    world_time=(
                        acquisition.get("acquired_at_world_time")
                        or acquisition_world_time
                    ),
                    seed_summary=seed_summary,
                    salience=_salience(
                        events=[{"magnitude": 0.0, "state_delta": {}}],
                        presence_duration=0,
                        cfg=cfg,
                    ),
                    world_layer=str(acquisition["anchor_world_layer"]),
                )
            )
        if events:
            event_ids = [int(event["id"]) for event in events]
            cur.execute(
                """
                UPDATE world_events
                SET experiences_formed_at = CURRENT_TIMESTAMP
                WHERE id = ANY(%s)
                  AND experiences_formed_at IS NULL
                  AND experiences_quarantined_at IS NULL
                RETURNING id
                """,
                (event_ids,),
            )
            stamped_ids = sorted(int(row["id"]) for row in cur.fetchall())
            if stamped_ids != sorted(event_ids):
                raise RuntimeError(
                    "Experience formation stamp mismatch: expected event ids "
                    f"{sorted(event_ids)}, stamped {stamped_ids}"
                )
    return inserted


def _batch_digest(rows: Sequence[Mapping[str, Any]]) -> str:
    return _digest(
        [
            {"id": int(row["id"]), "source_digest": str(row["source_digest"])}
            for row in sorted(rows, key=lambda item: int(item["id"]))
        ]
    )


def enqueue_scene_experience_job_sync(
    conn: Any,
    *,
    boundary_chunk_id: int,
    scene_end_chunk_id: int,
    world_layer: str,
    slot: Optional[int],
    settings: Mapping[str, Any],
) -> int:
    """Enqueue bounded immutable prior-scene seed batches at a scene reset."""

    cfg = experience_settings(settings)
    if not cfg.enabled or scene_end_chunk_id <= 0:
        return 0
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        player_entity_id = (
            None if cfg.include_player_character else canonical_player_entity_id(cur)
        )
        cur.execute(
            """
            SELECT boundary.season AS boundary_season,
                   boundary.episode AS boundary_episode,
                   boundary.scene AS boundary_scene,
                   boundary.world_layer::text AS boundary_world_layer,
                   scene_end.season AS scene_end_season,
                   scene_end.episode AS scene_end_episode,
                   scene_end.scene AS scene_end_scene,
                   scene_end.world_layer::text AS scene_end_world_layer
            FROM chunk_metadata boundary
            JOIN chunk_metadata scene_end ON scene_end.chunk_id = %s
            WHERE boundary.chunk_id = %s
            FOR UPDATE OF boundary
            FOR SHARE OF scene_end
            """,
            (scene_end_chunk_id, boundary_chunk_id),
        )
        timeline = cur.fetchone()
        if timeline is None:
            raise RuntimeError(
                "Experience boundary or scene-end anchor lacks timeline metadata"
            )
        if (
            timeline["boundary_world_layer"] != world_layer
            or timeline["scene_end_world_layer"] != world_layer
        ):
            raise ValueError(
                "Experience boundary and scene-end anchor must match the requested "
                f"world layer {world_layer!r}"
            )
        cur.execute(
            _ENQUEUE_CANDIDATES_SQL,
            (
                scene_end_chunk_id,
                world_layer,
                player_entity_id,
                player_entity_id,
            ),
        )
        rows = [dict(row) for row in cur.fetchall()]
        if not rows:
            return 0
        cur.execute(
            """
            SELECT COALESCE(max(batch_ordinal) + 1, 0) AS next_batch_ordinal
            FROM character_experience_jobs
            WHERE boundary_chunk_id = %s
              AND world_layer::text = %s
            """,
            (boundary_chunk_id, world_layer),
        )
        next_batch_ordinal = int(cur.fetchone()["next_batch_ordinal"])
        inserted = 0
        for batch_offset, start in enumerate(
            range(0, len(rows), cfg.max_seeds_per_render)
        ):
            batch_ordinal = next_batch_ordinal + batch_offset
            batch_rows = rows[start : start + cfg.max_seeds_per_render]
            cur.execute(
                """
                INSERT INTO character_experience_jobs (
                    boundary_chunk_id, scene_end_chunk_id, world_layer,
                    boundary_season, boundary_episode, boundary_scene,
                    scene_end_season, scene_end_episode, scene_end_scene,
                    batch_ordinal, experience_ids, slot, requested_model,
                    source_digest
                ) VALUES (
                    %s, %s, %s::world_layer_type, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (
                    boundary_chunk_id, world_layer, batch_ordinal
                ) DO NOTHING
                RETURNING id
                """,
                (
                    boundary_chunk_id,
                    scene_end_chunk_id,
                    world_layer,
                    timeline["boundary_season"],
                    timeline["boundary_episode"],
                    timeline["boundary_scene"],
                    timeline["scene_end_season"],
                    timeline["scene_end_episode"],
                    timeline["scene_end_scene"],
                    batch_ordinal,
                    [int(row["id"]) for row in batch_rows],
                    str(slot) if slot is not None else "default",
                    cfg.model,
                    _batch_digest(batch_rows),
                ),
            )
            inserted += int(cur.fetchone() is not None)
        return inserted


def _known_and_allowed_names(
    cur: Any, row: Mapping[str, Any]
) -> tuple[set[str], set[str]]:
    cur.execute("SELECT name FROM entity_names_v WHERE name IS NOT NULL")
    known = {str(item["name"]) for item in cur.fetchall() if str(item["name"]).strip()}
    if row["basis"] == "acquisition":
        cur.execute(
            """
            SELECT claim.summary, claim.account_payload, claim.account_label,
                   owner.name AS owner_name,
                   immediate.name AS immediate_source_name,
                   root.name AS root_source_name
            FROM claims claim
            JOIN claim_awareness awareness ON awareness.id = %s
            JOIN entity_names_v owner ON owner.id = %s
            LEFT JOIN entity_names_v immediate
              ON immediate.id = awareness.immediate_source_entity_id
            LEFT JOIN entity_names_v root
              ON root.id = awareness.root_source_entity_id
            WHERE claim.id = %s
            """,
            (
                row["claim_awareness_id"],
                row["character_entity_id"],
                row["claim_id"],
            ),
        )
        account = cur.fetchone()
        if account is None:
            raise ExperienceSourceStaleError(
                f"Acquisition experience {row['id']} lost its delivered account"
            )
        scope = " ".join(
            (
                str(account.get("summary") or ""),
                json.dumps(account.get("account_payload"), default=str),
                str(account.get("account_label") or ""),
            )
        )
        allowed = {
            str(name)
            for name in (
                account.get("owner_name"),
                account.get("immediate_source_name"),
                account.get("root_source_name"),
            )
            if name
        }
        allowed.update(
            name
            for name in known
            if re.search(rf"\b{re.escape(name)}\b", scope, re.IGNORECASE)
        )
        return known, allowed
    cur.execute(
        """
        SELECT DISTINCT names.name
        FROM (
            SELECT owner.name
            FROM characters owner
            WHERE owner.entity_id = %s
            UNION ALL
            SELECT entity_name.name
            FROM world_event_entities wee
            JOIN entity_names_v entity_name ON entity_name.id = wee.entity_id
            WHERE wee.event_id = ANY(%s)
            UNION ALL
            SELECT actor.name
            FROM world_events event
            JOIN entity_names_v actor ON actor.id = event.actor_entity_id
            WHERE event.id = ANY(%s)
            UNION ALL
            SELECT target.name
            FROM world_events event
            JOIN entity_names_v target ON target.id = event.target_entity_id
            WHERE event.id = ANY(%s)
            UNION ALL
            SELECT place.name
            FROM places place
            WHERE place.id = %s
        ) names
        WHERE names.name IS NOT NULL
        """,
        (
            row["character_entity_id"],
            row["world_event_ids"],
            row["world_event_ids"],
            row["world_event_ids"],
            row.get("location_id"),
        ),
    )
    allowed = {str(item["name"]) for item in cur.fetchall()}
    return known, allowed


def _entity_name_pattern(name: str) -> re.Pattern[str]:
    possessive = r"(?:['’]s|')?" if name.casefold().endswith("s") else r"(?:['’]s)?"
    return re.compile(rf"(?<!\w){re.escape(name)}{possessive}(?!\w)")


def _mask_allowed_names(text: str, allowed_names: Iterable[str]) -> str:
    masked = text
    for name in sorted(
        {name for name in allowed_names if name}, key=lambda item: (-len(item), item)
    ):
        masked = _entity_name_pattern(name).sub(
            lambda match: "x" * len(match.group(0)), masked
        )
    return masked


def _is_sentence_initial(text: str, start: int) -> bool:
    prefix = text[:start]
    prefix = prefix.rstrip()
    opener_peeled = False
    while prefix and prefix[-1] in {'"', "“", "‘", "'", "(", "[", "{"}:
        opener_peeled = True
        prefix = prefix[:-1]
    if opener_peeled and (
        not prefix
        or prefix[-1].isspace()
        or prefix[-1] in {",", ":", ";", "—", "–", "(", "["}
    ):
        return True
    prefix = prefix.rstrip()
    if not prefix or prefix[-1] in {".", "!", "?", "…", ":", "—", "–"}:
        return True
    while prefix and prefix[-1] in {'"', "”", "’", "'", ")", "]", "}"}:
        prefix = prefix[:-1].rstrip()
    return bool(prefix and prefix[-1] in {".", "!", "?", "…"})


def _token_occurs_outside_match(
    token: str,
    *,
    text: str,
    start: int,
    end: int,
    source_context: str,
) -> bool:
    # The exemption needs a genuinely LOWERCASE occurrence: a hallucinated name
    # that opens two sentences must not vouch for itself (Codex review, PR #739).
    token_pattern = re.compile(rf"(?<!\w){re.escape(token.lower())}(?!\w)")
    outside_match = text[:start] + (" " * (end - start)) + text[end:]
    return bool(
        token_pattern.search(outside_match) or token_pattern.search(source_context)
    )


def _proper_noun_candidates(
    text: str,
    *,
    allowed_names: Iterable[str] = (),
    source_context: str = "",
) -> set[str]:
    masked_text = _mask_allowed_names(text, allowed_names)
    candidates: set[str] = set()
    for match in _CAPITALIZED_SEQUENCE.finditer(masked_text):
        candidate = match.group(0).strip()
        if candidate == "I":
            continue
        if candidate in {"I", "We"} and _CONTRACTION_SUFFIX.match(
            masked_text, match.end()
        ):
            continue
        if not _is_sentence_initial(masked_text, match.start()):
            candidates.add(candidate)
            continue
        first = re.match(r"^[A-Za-z0-9]+", candidate)
        if first is None:
            continue
        first_token = first.group(0)
        remainder = candidate[first.end() :].lstrip(" '-")
        if remainder:
            candidates.add(remainder)
        first_lower = first_token.casefold()
        first_start = match.start()
        first_end = first_start + first.end()
        if (
            first_lower not in _SENTENCE_INITIAL_ALLOWLIST
            and not _has_non_name_suffix(first_lower)
            and not _token_occurs_outside_match(
                first_token,
                text=text,
                start=first_start,
                end=first_end,
                source_context=source_context,
            )
        ):
            candidates.add(first_token)
    return candidates


def validate_render_batch(
    rows: Sequence[Mapping[str, Any]],
    batch: ExperienceRenderBatch,
    *,
    names_by_experience: Optional[Mapping[int, tuple[set[str], set[str]]]] = None,
) -> RenderValidation:
    """Validate completeness, perspective, length, and source-scene entities."""

    expected = {int(row["id"]) for row in rows}
    actual = [item.experience_id for item in batch.recollections]
    if len(actual) != len(set(actual)):
        raise ValueError("Experience renderer returned duplicate experience ids")
    if set(actual) != expected:
        raise ValueError(
            f"Experience renderer ids mismatch; expected={sorted(expected)}, "
            f"actual={sorted(actual)}"
        )
    rows_by_id = {int(row["id"]): row for row in rows}
    validated: dict[int, str] = {}
    rejected: dict[int, str] = {}
    for recollection in batch.recollections:
        experience_id = recollection.experience_id
        text = recollection.experience_text.strip()
        known, allowed = (
            names_by_experience.get(experience_id, (set(), set()))
            if names_by_experience is not None
            else (set(), set())
        )
        masked_text = _mask_allowed_names(text, allowed)
        sentences = [
            part.strip() for part in _SENTENCE.split(masked_text) if part.strip()
        ]
        if not 2 <= len(sentences) <= 4:
            rejected[experience_id] = (
                f"Experience {experience_id} must contain 2-4 sentences"
            )
            continue
        if _FIRST_PERSON.search(text) is None:
            rejected[experience_id] = f"Experience {experience_id} is not first person"
            continue
        source_row = rows_by_id[experience_id]
        if source_row.get("basis") == "acquisition":
            if _ACQUISITION_RECEIPT.search(text) is None:
                rejected[experience_id] = (
                    f"Acquisition experience {experience_id} must "
                    "describe receiving or learning the account"
                )
                continue
            if _ACQUISITION_WITNESS.search(text) is not None:
                rejected[experience_id] = (
                    f"Acquisition experience {experience_id} "
                    "must not describe witnessing the underlying event"
                )
                continue
        disallowed_known = sorted(
            name for name in known - allowed if _entity_name_pattern(name).search(text)
        )
        # The lowercase-occurrence exemption is scoped to THIS experience's
        # seed: a sibling's seed must not vouch for an unrelated scene
        # (automated Claude review on PR #739).
        source_context = " ".join(
            str(value)
            for value in (
                source_row.get("seed_summary"),
                source_row.get("character_name"),
                source_row.get("location_name"),
            )
            if value
        )
        invented = sorted(
            _proper_noun_candidates(
                text,
                allowed_names=allowed,
                source_context=source_context,
            )
        )
        if disallowed_known or invented:
            offenders = sorted(set(disallowed_known + invented))
            rejected[experience_id] = (
                f"Experience {experience_id} names entities absent "
                f"from its source scene: {offenders}"
            )
            continue
        validated[experience_id] = text
    return RenderValidation(validated=validated, rejected=rejected)


def _render_prompt(rows: Sequence[Mapping[str, Any]]) -> str:
    prompt = _PROMPT_PATH.read_text(encoding="utf-8").strip()
    records = [
        {
            "experience_id": int(row["id"]),
            "character": row["character_name"],
            "basis": row["basis"],
            "world_time": row["world_time"],
            "location": row.get("location_name"),
            "seed": row["seed_summary"],
        }
        for row in rows
    ]
    return (
        prompt
        + "\n\nScene seed records:\n"
        + json.dumps(records, ensure_ascii=False, sort_keys=True, default=str)
    )


def _experience_provider(cfg: OrreryExperienceSettings) -> Any:
    from nexus.api.config_utils import get_wizard_retry_budget
    from nexus.api.native_structured_output import build_native_structured_provider

    prompt = _PROMPT_PATH.read_text(encoding="utf-8").strip()
    return build_native_structured_provider(
        model=cfg.model,
        max_tokens=cfg.max_output_tokens,
        system_prompt=prompt,
        structured_output_retries=get_wizard_retry_budget(),
        seat="experience_renderer",
    )


def _lease_matches(
    current: Optional[Mapping[str, Any]], leased: Mapping[str, Any]
) -> bool:
    return bool(
        current
        and current.get("state") == "leased"
        and current.get("locked_by") == leased.get("locked_by")
        and str(current.get("lease_nonce")) == str(leased.get("lease_nonce"))
        and bool(current.get("lease_live"))
    )


def _complete_render(
    cur: Any,
    *,
    job: Mapping[str, Any],
    source_rows: Sequence[Mapping[str, Any]],
    validation: RenderValidation,
    render_model: str,
    cfg: OrreryExperienceSettings,
) -> bool:
    cur.execute(
        """
        SELECT state::text AS state, locked_by, lease_nonce,
               lease_until >= clock_timestamp() AS lease_live,
               source_digest, world_layer::text AS world_layer,
               boundary_chunk_id, scene_end_chunk_id,
               boundary_season, boundary_episode, boundary_scene,
               scene_end_season, scene_end_episode, scene_end_scene,
               requested_model
        FROM character_experience_jobs
        WHERE id = %s
        FOR UPDATE
        """,
        (job["job_id"],),
    )
    current = cur.fetchone()
    if not _lease_matches(current, job):
        raise ExperienceLeaseLostError(
            f"Experience job {job['job_id']} no longer owns its live lease"
        )
    if current["source_digest"] != job["source_digest"]:
        raise ExperienceSourceStaleError(
            f"Experience job {job['job_id']} source digest changed"
        )
    frozen_fields = (
        "world_layer",
        "boundary_chunk_id",
        "scene_end_chunk_id",
        "boundary_season",
        "boundary_episode",
        "boundary_scene",
        "scene_end_season",
        "scene_end_episode",
        "scene_end_scene",
        "requested_model",
    )
    if any(current[field] != job[field] for field in frozen_fields):
        raise ExperienceSourceStaleError(
            f"Experience job {job['job_id']} frozen timeline identity changed"
        )
    cur.execute(
        """
        SELECT boundary.season AS boundary_season,
               boundary.episode AS boundary_episode,
               boundary.scene AS boundary_scene,
               boundary.world_layer::text AS boundary_world_layer,
               scene_end.season AS scene_end_season,
               scene_end.episode AS scene_end_episode,
               scene_end.scene AS scene_end_scene,
               scene_end.world_layer::text AS scene_end_world_layer
        FROM chunk_metadata boundary
        JOIN chunk_metadata scene_end ON scene_end.chunk_id = %s
        WHERE boundary.chunk_id = %s
        FOR SHARE OF boundary, scene_end
        """,
        (job["scene_end_chunk_id"], job["boundary_chunk_id"]),
    )
    timeline = cur.fetchone()
    if timeline is None or any(
        (
            timeline.get("boundary_world_layer") != job["world_layer"],
            timeline.get("scene_end_world_layer") != job["world_layer"],
            timeline.get("boundary_season") != job["boundary_season"],
            timeline.get("boundary_episode") != job["boundary_episode"],
            timeline.get("boundary_scene") != job["boundary_scene"],
            timeline.get("scene_end_season") != job["scene_end_season"],
            timeline.get("scene_end_episode") != job["scene_end_episode"],
            timeline.get("scene_end_scene") != job["scene_end_scene"],
        )
    ):
        raise ExperienceSourceStaleError(
            f"Experience job {job['job_id']} boundary timeline is stale"
        )
    cur.execute(
        """
        SELECT id, source_digest, experience_text,
               invalidation_status::text AS invalidation_status,
               world_layer::text AS world_layer
        FROM character_experiences
        WHERE id = ANY(%s)
        ORDER BY id
        FOR UPDATE
        """,
        (job["experience_ids"],),
    )
    current_rows = [dict(row) for row in cur.fetchall()]
    rows_by_id = {int(row["id"]): row for row in current_rows}
    expected_render_ids = {
        int(experience_id) for experience_id in job["render_experience_ids"]
    }
    renderable_ids = {
        int(experience_id) for experience_id in job["renderable_experience_ids"]
    }
    completion_ids = set(validation.validated) | set(validation.rejected)
    if (
        len(current_rows) != len(source_rows)
        or _batch_digest(current_rows) != job["source_digest"]
        or any(row["invalidation_status"] != "valid" for row in current_rows)
        or any(row["world_layer"] != job["world_layer"] for row in current_rows)
        or any(
            rows_by_id[experience_id]["experience_text"] is not None
            for experience_id in expected_render_ids
        )
        or any(
            rows_by_id[experience_id]["experience_text"] is None
            for experience_id in renderable_ids - expected_render_ids
        )
    ):
        raise ExperienceSourceStaleError(
            f"Experience job {job['job_id']} seed batch is stale"
        )
    if completion_ids != expected_render_ids or set(validation.validated) & set(
        validation.rejected
    ):
        raise ExperienceSourceStaleError(
            f"Experience job {job['job_id']} completion ids changed; "
            f"expected={sorted(expected_render_ids)}, "
            f"actual={sorted(completion_ids)}"
        )
    generation_id = str(uuid4())
    for experience_id, experience_text in validation.validated.items():
        row = rows_by_id[experience_id]
        cur.execute(
            """
            UPDATE character_experiences
            SET experience_text = %s,
                render_model = %s,
                renderer_version = %s,
                render_generation_id = %s
            WHERE id = %s
              AND source_digest = %s
              AND experience_text IS NULL
              AND invalidation_status = 'valid'
            """,
            (
                experience_text,
                render_model,
                RENDERER_VERSION,
                generation_id,
                experience_id,
                row["source_digest"],
            ),
        )
        if cur.rowcount != 1:
            raise ExperienceSourceStaleError(
                f"Experience {experience_id} changed during fenced completion"
            )
    if validation.rejected:
        error = "Experience render validation rejected: " + "; ".join(
            f"{experience_id}: {reason}"
            for experience_id, reason in sorted(validation.rejected.items())
        )
        _fail_render(cur, job=job, error=error, cfg=cfg)
        return False
    cur.execute(
        """
        UPDATE character_experience_jobs
        SET state = 'succeeded', lease_until = NULL, locked_by = NULL,
            lease_nonce = NULL, last_error = NULL, updated_at = now()
        WHERE id = %s AND state = 'leased' AND locked_by = %s
          AND lease_nonce = %s AND lease_until >= clock_timestamp()
        """,
        (job["job_id"], job["locked_by"], job["lease_nonce"]),
    )
    if cur.rowcount != 1:
        raise ExperienceLeaseLostError(
            f"Experience job {job['job_id']} lost its lease at completion"
        )
    return True


def _fail_render(
    cur: Any,
    *,
    job: Mapping[str, Any],
    error: str,
    cfg: OrreryExperienceSettings,
) -> None:
    next_state = "failed" if int(job["attempts"]) + 1 >= cfg.max_attempts else "queued"
    cur.execute(
        """
        UPDATE character_experience_jobs
        SET state = %s::orrery_job_state,
            available_at = CASE WHEN %s = 'queued'
                THEN clock_timestamp() + (%s * interval '1 second')
                ELSE available_at END,
            lease_until = NULL, locked_by = NULL, lease_nonce = NULL,
            last_error = %s, updated_at = now()
        WHERE id = %s AND state = 'leased' AND locked_by = %s
          AND lease_nonce = %s AND lease_until >= clock_timestamp()
        """,
        (
            next_state,
            next_state,
            cfg.retry_delay_seconds,
            error,
            job["job_id"],
            job["locked_by"],
            job["lease_nonce"],
        ),
    )
    if cur.rowcount != 1:
        raise ExperienceLeaseLostError(
            f"Experience job {job['job_id']} lost its lease before failure write"
        )


def _reject_stale_source(
    cur: Any,
    *,
    job: Mapping[str, Any],
    error: str,
) -> None:
    cur.execute(
        """
        UPDATE character_experience_jobs
        SET state = 'stale_rejected', lease_until = NULL, locked_by = NULL,
            lease_nonce = NULL, last_error = %s, updated_at = now()
        WHERE id = %s AND state = 'leased' AND locked_by = %s
          AND lease_nonce = %s AND lease_until >= clock_timestamp()
        """,
        (error, job["job_id"], job["locked_by"], job["lease_nonce"]),
    )
    if cur.rowcount != 1:
        raise ExperienceLeaseLostError(
            f"Experience job {job['job_id']} lost its lease before stale rejection"
        )


def load_experience_status_sync(cur: Any) -> dict[str, Any]:
    """Return experience-render queue counts and non-terminal jobs."""

    cur.execute(
        """
        SELECT
            jsonb_build_object(
                'queued', count(*) FILTER (WHERE state = 'queued'),
                'leased', count(*) FILTER (WHERE state = 'leased'),
                'succeeded', count(*) FILTER (WHERE state = 'succeeded'),
                'failed', count(*) FILTER (WHERE state = 'failed'),
                'stale_rejected', count(*) FILTER (WHERE state = 'stale_rejected')
            ) AS counts,
            COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'id', id,
                        'queue', 'experience_render',
                        'state', state::text,
                        'attempts', attempts,
                        'available_at', available_at,
                        'lease_until', lease_until,
                        'last_error', last_error,
                        'boundary_chunk_id', boundary_chunk_id,
                        'scene_end_chunk_id', scene_end_chunk_id,
                        'batch_ordinal', batch_ordinal,
                        'experience_ids', experience_ids
                    ) ORDER BY id
                ) FILTER (WHERE state IN ('queued', 'leased')),
                '[]'::jsonb
            ) AS non_terminal_jobs
        FROM character_experience_jobs
        """
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("Experience status query returned no row")
    raw_counts = _row_value(row, "counts", 0)
    raw_jobs = _row_value(row, "non_terminal_jobs", 1)
    if not isinstance(raw_counts, Mapping) or not isinstance(raw_jobs, list):
        raise RuntimeError("Experience status query returned an invalid shape")
    counts = {
        state: int(raw_counts.get(state, 0))
        for state in ("queued", "leased", "succeeded", "failed", "stale_rejected")
    }
    return {"counts": counts, "non_terminal_jobs": raw_jobs}


def drain_experience_render_jobs_sync(
    *,
    slot: Optional[int],
    settings: Mapping[str, Any],
    conn: Any,
    provider: Optional[Any] = None,
    limit: Optional[int] = None,
) -> tuple[int, int]:
    """Lease, render, validate, and fence scene-batch experience jobs."""

    cfg = experience_settings(settings)
    if not cfg.enabled:
        return (0, 0)
    job_limit = (
        cfg.max_jobs_per_drain if limit is None else min(limit, cfg.max_jobs_per_drain)
    )
    if job_limit < 0:
        raise ValueError("Experience render job limit must be non-negative")
    if job_limit == 0:
        return (0, 0)
    owner = f"experience:{slot if slot is not None else 'default'}:{uuid4()}"
    renderer: Any = None
    failed_count = 0
    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            player_entity_id = (
                None
                if cfg.include_player_character
                else canonical_player_entity_id(cur)
            )
            cur.execute(
                """
                SELECT job.id AS job_id, job.experience_ids, job.attempts,
                       job.requested_model,
                       source_digest, world_layer::text AS world_layer, slot,
                       boundary_chunk_id, scene_end_chunk_id,
                       boundary_season, boundary_episode, boundary_scene,
                       scene_end_season, scene_end_episode, scene_end_scene,
                       ARRAY(
                           SELECT experience.id
                           FROM character_experiences experience
                           WHERE experience.id = ANY(job.experience_ids)
                             AND experience.character_entity_id = %s
                           ORDER BY experience.id
                       ) AS excluded_player_experience_ids,
                       ARRAY(
                           SELECT experience.id
                           FROM character_experiences experience
                           WHERE experience.id = ANY(job.experience_ids)
                             AND experience.experience_text IS NOT NULL
                           ORDER BY experience.id
                       ) AS rendered_experience_ids
                FROM character_experience_jobs job
                WHERE (
                    (job.state = 'queued'
                     AND job.available_at <= clock_timestamp())
                    OR
                    (job.state = 'leased'
                     AND job.lease_until < clock_timestamp())
                )
                ORDER BY CASE
                    WHEN job.state = 'leased'
                    THEN job.lease_until ELSE job.available_at
                END,
                         job.id
                LIMIT %s
                FOR UPDATE OF job SKIP LOCKED
                """,
                (player_entity_id, job_limit),
            )
            selected_jobs = cur.fetchall()
            renderable_jobs = []
            for selected in selected_jobs:
                job = dict(selected)
                excluded_ids = [
                    int(value) for value in job.pop("excluded_player_experience_ids")
                ]
                already_rendered_ids = {
                    int(value) for value in job.pop("rendered_experience_ids")
                }
                renderable_ids = [
                    int(value)
                    for value in job["experience_ids"]
                    if int(value) not in set(excluded_ids)
                ]
                render_ids = [
                    experience_id
                    for experience_id in renderable_ids
                    if experience_id not in already_rendered_ids
                ]
                if excluded_ids and not renderable_ids:
                    cur.execute(
                        """
                        UPDATE character_experience_jobs
                        SET state = 'stale_rejected', lease_until = NULL,
                            locked_by = NULL, lease_nonce = NULL,
                            last_error = %s, updated_at = now()
                        WHERE id = %s
                        """,
                        (_PLAYER_EXCLUSION_JOB_ERROR, job["job_id"]),
                    )
                    if cur.rowcount != 1:
                        raise RuntimeError(
                            "Failed to stale-reject player-owned experience job "
                            f"{job['job_id']}"
                        )
                    logger.error(
                        "Stale-rejected experience job %s because player-owned "
                        "seeds %s are excluded by config",
                        job["job_id"],
                        excluded_ids,
                    )
                    failed_count += 1
                    continue
                if not render_ids:
                    nonce = str(uuid4())
                    cur.execute(
                        """
                        UPDATE character_experience_jobs
                        SET state = 'leased',
                            lease_until = clock_timestamp()
                                + (%s * interval '1 second'),
                            locked_by = %s, lease_nonce = %s,
                            attempts = attempts + 1, updated_at = now()
                        WHERE id = %s
                        """,
                        (cfg.lease_duration_seconds, owner, nonce, job["job_id"]),
                    )
                    if cur.rowcount != 1:
                        raise RuntimeError(
                            "Failed to lease already-rendered experience job "
                            f"{job['job_id']}"
                        )
                    job["locked_by"] = owner
                    job["lease_nonce"] = nonce
                    if int(job["attempts"]) == 0:
                        error = (
                            f"Experience job {job['job_id']} is stale because "
                            "seeds were already rendered: "
                            f"{sorted(already_rendered_ids)}"
                        )
                        _reject_stale_source(cur, job=job, error=error)
                        failed_count += 1
                        continue
                    cur.execute(
                        """
                        SELECT id, source_digest,
                               invalidation_status::text AS invalidation_status
                        FROM character_experiences
                        WHERE id = ANY(%s)
                        ORDER BY id
                        FOR UPDATE
                        """,
                        (job["experience_ids"],),
                    )
                    current_rows = [dict(row) for row in cur.fetchall()]
                    expected_ids = {
                        int(experience_id) for experience_id in job["experience_ids"]
                    }
                    if (
                        {int(row["id"]) for row in current_rows} != expected_ids
                        or _batch_digest(current_rows) != job["source_digest"]
                        or any(
                            row["invalidation_status"] != "valid"
                            for row in current_rows
                        )
                    ):
                        _reject_stale_source(
                            cur,
                            job=job,
                            error=(
                                f"Experience job {job['job_id']} "
                                "already-rendered seed batch is stale"
                            ),
                        )
                        failed_count += 1
                        continue
                    cur.execute(
                        """
                        UPDATE character_experience_jobs
                        SET state = 'succeeded', lease_until = NULL,
                            locked_by = NULL, lease_nonce = NULL,
                            last_error = NULL, updated_at = now()
                        WHERE id = %s AND state = 'leased' AND locked_by = %s
                          AND lease_nonce = %s
                          AND lease_until >= clock_timestamp()
                        """,
                        (job["job_id"], job["locked_by"], job["lease_nonce"]),
                    )
                    if cur.rowcount != 1:
                        raise ExperienceLeaseLostError(
                            f"Experience job {job['job_id']} lost its lease "
                            "while completing already-rendered seeds"
                        )
                    continue
                if excluded_ids:
                    logger.warning(
                        "Filtered player-owned experience seeds %s from job %s; "
                        "rendering eligible seeds %s",
                        excluded_ids,
                        job["job_id"],
                        render_ids,
                    )
                job["renderable_experience_ids"] = renderable_ids
                job["render_experience_ids"] = render_ids
                renderable_jobs.append(job)
            if renderable_jobs:
                # Match the hardened narration queue: provider construction
                # must succeed before any durable lease is acquired.
                renderer = provider or _experience_provider(cfg)
            jobs = []
            for job in renderable_jobs:
                nonce = str(uuid4())
                cur.execute(
                    """
                    UPDATE character_experience_jobs
                    SET state = 'leased',
                        lease_until = clock_timestamp() + (%s * interval '1 second'),
                        locked_by = %s, lease_nonce = %s,
                        attempts = attempts + 1, updated_at = now()
                    WHERE id = %s
                    """,
                    (cfg.lease_duration_seconds, owner, nonce, job["job_id"]),
                )
                job["locked_by"] = owner
                job["lease_nonce"] = nonce
                jobs.append(job)
    rendered_count = 0
    for job in jobs:
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT experience.id, experience.character_entity_id,
                               experience.world_event_ids,
                               experience.claim_id,
                               experience.claim_awareness_id,
                               experience.basis::text AS basis,
                               experience.location_id, experience.world_time,
                               experience.seed_summary, experience.source_digest,
                               character.name AS character_name,
                               place.name AS location_name
                        FROM character_experiences experience
                        JOIN characters character
                          ON character.entity_id = experience.character_entity_id
                        LEFT JOIN places place ON place.id = experience.location_id
                        WHERE experience.id = ANY(%s)
                        ORDER BY experience.id
                        """,
                        (job["experience_ids"],),
                    )
                    source_rows = [dict(row) for row in cur.fetchall()]
                    render_id_set = {
                        int(experience_id)
                        for experience_id in job["render_experience_ids"]
                    }
                    rows = [
                        row for row in source_rows if int(row["id"]) in render_id_set
                    ]
                    if {int(row["id"]) for row in rows} != render_id_set:
                        raise ExperienceSourceStaleError(
                            f"Experience job {job['job_id']} lost renderable seeds"
                        )
                    names = {
                        int(row["id"]): _known_and_allowed_names(cur, row)
                        for row in rows
                    }
            prompt = _render_prompt(rows)
            with usage_context(
                seat="experience_renderer",
                slot=(int(job["slot"]) if str(job["slot"]).isdigit() else slot),
                run_id=str(job["job_id"]),
            ):
                response = renderer.get_structured_completion(
                    prompt, ExperienceRenderBatch
                )
            batch = response[0] if isinstance(response, tuple) else response
            if not isinstance(batch, ExperienceRenderBatch):
                batch = ExperienceRenderBatch.model_validate(batch)
            validation = validate_render_batch(rows, batch, names_by_experience=names)
            if validation.rejected:
                logger.warning(
                    "Experience render job %s rejected recollections: %s",
                    job["job_id"],
                    "; ".join(
                        f"{experience_id}: {reason}"
                        for experience_id, reason in sorted(validation.rejected.items())
                    ),
                )
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    completed = _complete_render(
                        cur,
                        job=job,
                        source_rows=source_rows,
                        validation=validation,
                        render_model=cfg.model,
                        cfg=cfg,
                    )
            rendered_count += len(validation.validated)
            if not completed:
                failed_count += 1
        except ExperienceLeaseLostError:
            failed_count += 1
            logger.exception("Rejected stale experience render job %s", job["job_id"])
        except ExperienceSourceStaleError as exc:
            failed_count += 1
            try:
                with conn:
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        _reject_stale_source(cur, job=job, error=str(exc))
            except ExperienceLeaseLostError:
                logger.exception(
                    "Rejected stale-source write for experience render job %s",
                    job["job_id"],
                )
            logger.exception("Rejected stale experience source %s", job["job_id"])
        except Exception as exc:
            failed_count += 1
            try:
                with conn:
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        _fail_render(cur, job=job, error=str(exc), cfg=cfg)
            except ExperienceLeaseLostError:
                logger.exception(
                    "Rejected failure write for experience render job %s",
                    job["job_id"],
                )
            logger.exception("Failed experience render job %s", job["job_id"])
    return rendered_count, failed_count
