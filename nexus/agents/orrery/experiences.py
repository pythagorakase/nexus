"""Deterministic actor-owned experience formation and scene rendering."""

from __future__ import annotations

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
from nexus.config.settings_models import OrreryExperienceSettings
from nexus.telemetry.usage import usage_context


logger = logging.getLogger("nexus.orrery.experiences")

RENDERER_VERSION = "experience-renderer-v1"
_PROMPT_PATH = (
    Path(__file__).resolve().parents[3] / "prompts" / "experience_renderer.md"
)
_CAPITALIZED_SEQUENCE = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:[ '-][A-Z][A-Za-z0-9]*)*\b")
_SENTENCE_INITIAL_ALLOWLIST = frozenset(
    {
        "a",
        "after",
        "an",
        "and",
        "as",
        "at",
        "before",
        "but",
        "by",
        "for",
        "from",
        "he",
        "i",
        "in",
        "it",
        "my",
        "once",
        "our",
        "she",
        "so",
        "that",
        "the",
        "then",
        "they",
        "this",
        "through",
        "to",
        "until",
        "we",
        "when",
        "while",
        "with",
        "without",
    }
)
_FIRST_PERSON = re.compile(r"\b(?:I|me|my|mine|we|us|our|ours)\b", re.IGNORECASE)
_SENTENCE = re.compile(r"(?<=[.!?])(?:[\"']?\s+|$)")
_ACQUISITION_RECEIPT = re.compile(
    r"\b(?:told|heard|learned|informed|received|read|listened|account|message|report)\b",
    re.IGNORECASE,
)
_ACQUISITION_WITNESS = re.compile(
    r"\b(?:saw|watched|witnessed|observed|looked on|was there)\b",
    re.IGNORECASE,
)


class ExperienceRecollection(BaseModel):
    """One provider-rendered recollection keyed to its durable seed."""

    experience_id: int = Field(gt=0)
    experience_text: str = Field(min_length=1)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class ExperienceRenderBatch(BaseModel):
    """Complete structured response for one scene roster."""

    recollections: list[ExperienceRecollection] = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")


class ExperienceLeaseLostError(RuntimeError):
    """Raised when a stale scene worker attempts a fenced write."""


class ExperienceSourceStaleError(RuntimeError):
    """Raised when a scene job's immutable seed batch no longer matches."""


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


def _active_mood(cur: Any, character_entity_id: int) -> Optional[str]:
    cur.execute(
        """
        SELECT t.tag
        FROM entity_tags et
        JOIN tags t ON t.id = et.tag_id
        WHERE et.entity_id = %s
          AND et.cleared_at IS NULL
          AND t.category = 'mood'
        ORDER BY et.applied_at DESC, et.id DESC
        LIMIT 1
        """,
        (character_entity_id,),
    )
    row = cur.fetchone()
    return str(_row_value(row, "tag", 0)) if row is not None else None


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

    payload = _json_mapping(row.get("payload"))
    if payload.get("on_screen_public") is not True:
        return frozenset()
    raw_audience = payload.get("audience_entity_ids")
    if not isinstance(raw_audience, list):
        raise ValueError(
            f"Public event {row['id']} must declare audience_entity_ids as a list"
        )
    audience: set[int] = set()
    for raw_id in raw_audience:
        if isinstance(raw_id, bool):
            raise ValueError(f"Public event {row['id']} has an invalid audience id")
        entity_id = int(raw_id)
        if entity_id <= 0:
            raise ValueError(f"Public event {row['id']} has an invalid audience id")
        audience.add(entity_id)
    return frozenset(audience)


def _event_receipts(row: Mapping[str, Any]) -> dict[int, str]:
    """Derive actor-owned receipt bases from canonical event roles and policy."""

    event_type = str(row["event_type"])
    birth_roles = CLAIM_BIRTH_ROLE_POLICY.get(event_type)
    receipts: dict[int, str] = {}
    for participant in row.get("participants") or []:
        if not isinstance(participant, Mapping):
            raise ValueError(f"Event {row['id']} has a malformed participant receipt")
        entity_id = int(participant["entity_id"])
        role = str(participant["role"])
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
    emotion: Optional[str],
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
            "emotion": emotion,
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
            %s, %s, %s, %s, %s::world_layer_type
        )
        ON CONFLICT DO NOTHING
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
            emotion,
            salience,
            source_digest,
            world_layer,
        ),
    )
    return cur.fetchone() is not None


def seed_character_experiences_sync(
    conn: Any,
    *,
    anchor_chunk_id: int,
    settings: Mapping[str, Any],
) -> int:
    """Insert deterministic participant, witness, and acquisition seeds."""

    cfg = experience_settings(settings)
    if not cfg.enabled:
        return 0
    inserted = 0
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT cm.world_time, cm.world_layer::text AS world_layer,
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
            WHERE cm.chunk_id = %s
            """,
            (anchor_chunk_id,),
        )
        metadata = cur.fetchone()
        if metadata is None:
            raise RuntimeError(
                f"Experience anchor chunk {anchor_chunk_id} has no metadata"
            )
        world_time = metadata["world_time"]
        world_layer = str(metadata["world_layer"])

        cur.execute(
            """
            SELECT e.id, e.event_type, e.actor_entity_id, e.target_entity_id,
                   e.location_id, e.magnitude, e.payload,
                   actor.name AS actor_name, target.name AS target_name,
                   place.name AS location_name, r.state_delta,
                   COALESCE(
                       jsonb_agg(
                           jsonb_build_object(
                               'entity_id', wee.entity_id,
                               'role', wee.role::text
                           )
                           ORDER BY wee.entity_id, wee.role::text
                       ) FILTER (WHERE wee.entity_id IS NOT NULL),
                       '[]'::jsonb
                   ) AS participants
            FROM world_events e
            LEFT JOIN entity_names_v actor ON actor.id = e.actor_entity_id
            LEFT JOIN entity_names_v target ON target.id = e.target_entity_id
            LEFT JOIN places place ON place.id = e.location_id
            LEFT JOIN orrery_resolutions r ON r.id = e.resolution_id
            LEFT JOIN world_event_entities wee ON wee.event_id = e.id
            WHERE e.tick_chunk_id = %s
              AND e.superseded_by_event_id IS NULL
            GROUP BY e.id, actor.name, target.name, place.name, r.state_delta
            ORDER BY e.id
            """,
            (anchor_chunk_id,),
        )
        events = [dict(row) for row in cur.fetchall()]
        receipts: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for event in events:
            for entity_id, basis in _event_receipts(event).items():
                receipts.setdefault((entity_id, basis), []).append(event)
        receipt_entity_ids = sorted({entity_id for entity_id, _basis in receipts})
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
            }
        for (character_id, basis), owned_events in sorted(receipts.items()):
            character = eligible_by_id.get(character_id)
            if character is None:
                continue
            duration = _presence_duration(
                cur,
                character_entity_id=character_id,
                anchor_chunk_id=anchor_chunk_id,
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
                    anchor_chunk_id=anchor_chunk_id,
                    world_event_ids=[int(row["id"]) for row in owned_events],
                    claim_id=None,
                    claim_awareness_id=None,
                    basis=basis,
                    location_id=location_id,
                    world_time=world_time,
                    seed_summary=seed_summary,
                    emotion=_active_mood(cur, character_id),
                    salience=_salience(
                        events=owned_events,
                        presence_duration=duration,
                        cfg=cfg,
                    ),
                    world_layer=world_layer,
                )
            )

        cur.execute(
            """
            SELECT ca.id AS awareness_id, ca.claim_id, ca.knower_entity_id,
                   ca.source_tier, ca.acquired_at_world_time,
                   c.summary AS claim_summary, c.account_label,
                   c.world_event_id AS incident_event_id,
                   character.name, character.summary, character.background,
                   character.personality,
                   delivery.id AS delivery_event_id,
                   incident.location_id
            FROM claim_awareness ca
            JOIN claims c ON c.id = ca.claim_id
            JOIN characters character ON character.entity_id = ca.knower_entity_id
            JOIN world_events incident ON incident.id = c.world_event_id
            LEFT JOIN world_events delivery
              ON delivery.tick_chunk_id = ca.source_chunk_id
             AND delivery.payload ->> 'awareness_id' = ca.id::text
            WHERE ca.source_chunk_id = %s
              AND ca.source_tier IN ('told', 'granted')
            ORDER BY ca.id
            """,
            (anchor_chunk_id,),
        )
        for acquisition in (dict(row) for row in cur.fetchall()):
            if not _eligible_character(acquisition, cfg):
                continue
            source_ids = [int(acquisition["incident_event_id"])]
            if acquisition.get("delivery_event_id") is not None:
                source_ids.append(int(acquisition["delivery_event_id"]))
            seed_summary = (
                f"{acquisition['name']} acquired the "
                f"{acquisition['account_label']} account by being "
                f"{acquisition['source_tier']}: {acquisition['claim_summary']}"
            )
            character_id = int(acquisition["knower_entity_id"])
            inserted += int(
                _insert_experience(
                    cur,
                    character_entity_id=character_id,
                    anchor_chunk_id=anchor_chunk_id,
                    world_event_ids=source_ids,
                    claim_id=int(acquisition["claim_id"]),
                    claim_awareness_id=int(acquisition["awareness_id"]),
                    basis="acquisition",
                    location_id=acquisition.get("location_id"),
                    world_time=acquisition.get("acquired_at_world_time") or world_time,
                    seed_summary=seed_summary,
                    emotion=_active_mood(cur, character_id),
                    salience=_salience(
                        events=[{"magnitude": 0.0, "state_delta": {}}],
                        presence_duration=0,
                        cfg=cfg,
                    ),
                    world_layer=world_layer,
                )
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
            """
            SELECT EXISTS (
                SELECT 1
                FROM character_experience_jobs
                WHERE boundary_chunk_id = %s
                  AND world_layer::text = %s
            ) AS already_enqueued
            """,
            (boundary_chunk_id, world_layer),
        )
        if bool(cur.fetchone()["already_enqueued"]):
            return 0
        cur.execute(
            """
            SELECT max(boundary_chunk_id) AS previous_boundary
            FROM character_experience_jobs
            WHERE world_layer::text = %s
              AND boundary_chunk_id < %s
            """,
            (world_layer, boundary_chunk_id),
        )
        previous = cur.fetchone()["previous_boundary"]
        lower_bound = int(previous) if previous is not None else 0
        cur.execute(
            """
            SELECT id, source_digest
            FROM character_experiences
            WHERE anchor_chunk_id >= %s
              AND anchor_chunk_id <= %s
              AND world_layer::text = %s
              AND invalidation_status = 'valid'
              AND experience_text IS NULL
            ORDER BY id
            """,
            (lower_bound, scene_end_chunk_id, world_layer),
        )
        rows = [dict(row) for row in cur.fetchall()]
        if not rows:
            return 0
        inserted = 0
        for batch_ordinal, start in enumerate(
            range(0, len(rows), cfg.max_seeds_per_render)
        ):
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


def _proper_noun_candidates(text: str) -> set[str]:
    candidates: set[str] = set()
    for match in _CAPITALIZED_SEQUENCE.finditer(text):
        candidate = match.group(0).strip()
        while candidate:
            first = re.match(r"^[A-Za-z0-9]+", candidate)
            if first is None or first.group(0).casefold() not in (
                _SENTENCE_INITIAL_ALLOWLIST
            ):
                break
            candidate = candidate[first.end() :].lstrip(" '-")
        if candidate:
            candidates.add(candidate)
    return candidates


def validate_render_batch(
    rows: Sequence[Mapping[str, Any]],
    batch: ExperienceRenderBatch,
    *,
    names_by_experience: Optional[Mapping[int, tuple[set[str], set[str]]]] = None,
) -> dict[int, str]:
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
    validated: dict[int, str] = {}
    for recollection in batch.recollections:
        text = recollection.experience_text.strip()
        sentences = [part.strip() for part in _SENTENCE.split(text) if part.strip()]
        if not 2 <= len(sentences) <= 4:
            raise ValueError(
                f"Experience {recollection.experience_id} must contain 2-4 sentences"
            )
        if _FIRST_PERSON.search(text) is None:
            raise ValueError(
                f"Experience {recollection.experience_id} is not first person"
            )
        source_row = next(
            row for row in rows if int(row["id"]) == recollection.experience_id
        )
        if source_row.get("basis") == "acquisition":
            if _ACQUISITION_RECEIPT.search(text) is None:
                raise ValueError(
                    f"Acquisition experience {recollection.experience_id} must "
                    "describe receiving or learning the account"
                )
            if _ACQUISITION_WITNESS.search(text) is not None:
                raise ValueError(
                    f"Acquisition experience {recollection.experience_id} "
                    "must not describe witnessing the underlying event"
                )
        known, allowed = (
            names_by_experience.get(recollection.experience_id, (set(), set()))
            if names_by_experience is not None
            else (set(), set())
        )
        disallowed_known = sorted(
            name
            for name in known - allowed
            if re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE)
        )
        allowed_casefold = {name.casefold() for name in allowed}
        capitalized = _proper_noun_candidates(text)
        invented = sorted(
            name for name in capitalized if name.casefold() not in allowed_casefold
        )
        if disallowed_known or invented:
            offenders = sorted(set(disallowed_known + invented))
            raise ValueError(
                f"Experience {recollection.experience_id} names entities absent "
                f"from its source scene: {offenders}"
            )
        validated[recollection.experience_id] = text
    return validated


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
    rows: Sequence[Mapping[str, Any]],
    rendered: Mapping[int, str],
    render_model: str,
) -> None:
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
    if (
        len(current_rows) != len(rows)
        or _batch_digest(current_rows) != job["source_digest"]
        or any(row["experience_text"] is not None for row in current_rows)
        or any(row["invalidation_status"] != "valid" for row in current_rows)
        or any(row["world_layer"] != job["world_layer"] for row in current_rows)
    ):
        raise ExperienceSourceStaleError(
            f"Experience job {job['job_id']} seed batch is stale"
        )
    generation_id = str(uuid4())
    for row in current_rows:
        experience_id = int(row["id"])
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
                rendered[experience_id],
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
    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id AS job_id, experience_ids, attempts, requested_model,
                       source_digest, world_layer::text AS world_layer, slot,
                       boundary_chunk_id, scene_end_chunk_id,
                       boundary_season, boundary_episode, boundary_scene,
                       scene_end_season, scene_end_episode, scene_end_scene
                FROM character_experience_jobs
                WHERE (
                    (state = 'queued' AND available_at <= clock_timestamp())
                    OR
                    (state = 'leased' AND lease_until < clock_timestamp())
                )
                ORDER BY CASE
                    WHEN state = 'leased' THEN lease_until ELSE available_at
                END,
                         id
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (job_limit,),
            )
            selected_jobs = cur.fetchall()
            if selected_jobs:
                # Match the hardened narration queue: provider construction
                # must succeed before any durable lease is acquired.
                renderer = provider or _experience_provider(cfg)
            jobs = []
            for selected in selected_jobs:
                job = dict(selected)
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
    failed_count = 0
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
                    rows = [dict(row) for row in cur.fetchall()]
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
            validated = validate_render_batch(rows, batch, names_by_experience=names)
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    _complete_render(
                        cur,
                        job=job,
                        rows=rows,
                        rendered=validated,
                        render_model=cfg.model,
                    )
            rendered_count += len(rows)
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
