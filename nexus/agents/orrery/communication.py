"""Deterministic read-side communication graph assembly for Orrery."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable, Literal, Mapping, Optional, Sequence, Tuple

from sqlalchemy import text

from nexus.agents.orrery.status_family import (
    STATUS_TAGS,
    level_from_status_tag,
    status_at_or_above_level,
)
from nexus.config.settings_models import OrreryContagionSettings


CommunicationEdgeKind = Literal["dyad", "channel"]
_CULTURE_CATEGORIES = frozenset({"operational_secrecy", "operational_mode"})
_DYAD_SQL = """
    /* orrery:communication_dyads */
    SELECT c1.entity_id AS teller_entity_id,
           c2.entity_id AS listener_entity_id,
           cr.relationship_type::text AS relationship_type,
           cr.valence_current
    FROM character_relationships cr
    JOIN characters c1 ON c1.id = cr.character1_id
    JOIN characters c2 ON c2.id = cr.character2_id
    JOIN entities teller ON teller.id = c1.entity_id
    JOIN entities listener ON listener.id = c2.entity_id
    WHERE teller.kind = 'character'
      AND listener.kind = 'character'
      AND teller.is_active = true
      AND listener.is_active = true
    ORDER BY c1.entity_id, c2.entity_id, cr.relationship_type::text
"""
_REGISTERED_PAIR_TAGS_SQL = """
    /* orrery:communication_registered_pair_tags */
    SELECT tag
    FROM pair_tags
    WHERE NOT deprecated
    ORDER BY tag
"""
_CHANNEL_SQL = """
    /* orrery:communication_channels */
    SELECT ept.subject_entity_id,
           subject.kind::text AS subject_kind,
           ept.object_entity_id,
           object.kind::text AS object_kind,
           pt.tag
    FROM entity_pair_tags ept
    JOIN pair_tags pt ON pt.id = ept.pair_tag_id
    JOIN entities subject ON subject.id = ept.subject_entity_id
    JOIN entities object ON object.id = ept.object_entity_id
    WHERE ept.cleared_at IS NULL
      AND NOT pt.deprecated
      AND subject.is_active = true
      AND object.is_active = true
    ORDER BY ept.subject_entity_id, ept.object_entity_id, pt.tag
"""
_CULTURE_TAGS_SQL = """
    /* orrery:communication_culture_tags */
    SELECT etc.entity_id, etc.category, etc.tag
    FROM entity_tags_current etc
    JOIN entities institution ON institution.id = etc.entity_id
    WHERE institution.kind = 'faction'
      AND institution.is_active = true
      AND etc.category IN ('operational_secrecy', 'operational_mode')
    ORDER BY etc.entity_id, etc.category, etc.tag
"""


@dataclass(frozen=True, slots=True)
class CommunicationEdge:
    """One directed, deterministic communication conduit."""

    teller_entity_id: int
    listener_entity_id: int
    latency: timedelta
    kind: CommunicationEdgeKind
    label: str
    institution_entity_id: Optional[int] = None
    culture_multiplier: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe audit representation of this edge."""

        payload: dict[str, Any] = {
            "teller_entity_id": self.teller_entity_id,
            "listener_entity_id": self.listener_entity_id,
            "latency_seconds": self.latency.total_seconds(),
            "kind": self.kind,
            "label": self.label,
        }
        if self.kind == "channel":
            payload["institution_entity_id"] = self.institution_entity_id
            payload["culture_multiplier"] = self.culture_multiplier
        return payload


@dataclass(frozen=True, slots=True)
class CommunicationGraph:
    """Immutable, stably ordered directed communication edges."""

    edges: Tuple[CommunicationEdge, ...] = ()

    def outbound(self, entity_id: int) -> Tuple[CommunicationEdge, ...]:
        """Return one entity's outbound edges in graph order."""

        return tuple(edge for edge in self.edges if edge.teller_entity_id == entity_id)

    def to_dict(self, *, entity_id: Optional[int] = None) -> dict[str, Any]:
        """Return all edges, or one entity's outbound explain view."""

        edges = self.edges if entity_id is None else self.outbound(entity_id)
        return {"edges": [edge.to_dict() for edge in edges]}


def coerce_contagion_settings(settings: Any) -> OrreryContagionSettings:
    """Normalize a Pydantic model or mapping into contagion settings."""

    if isinstance(settings, OrreryContagionSettings):
        return settings
    if hasattr(settings, "model_dump"):
        settings = settings.model_dump()
    if isinstance(settings, Mapping):
        return OrreryContagionSettings.model_validate(dict(settings))
    raise TypeError("contagion settings must be OrreryContagionSettings or a mapping")


def _fetch_mappings(session_or_cur: Any, sql: str) -> list[dict[str, Any]]:
    """Execute parameterless read SQL through SQLAlchemy or a DB-API cursor."""

    if type(session_or_cur).__module__.startswith("sqlalchemy"):
        result = session_or_cur.execute(text(sql))
        return [dict(row) for row in result.mappings()]

    result = session_or_cur.execute(sql)
    if result is not None and hasattr(result, "mappings"):
        return [dict(row) for row in result.mappings()]
    description = getattr(session_or_cur, "description", None)
    if description is None:
        raise TypeError(
            "session_or_cur must be a SQLAlchemy session/connection or DB-API cursor"
        )
    rows = session_or_cur.fetchall()
    if rows and isinstance(rows[0], Mapping):
        return [dict(row) for row in rows]
    column_names = [column[0] for column in description]
    return [dict(zip(column_names, row, strict=True)) for row in rows]


async def _fetch_mappings_async(conn: Any, sql: str) -> list[dict[str, Any]]:
    """Execute read SQL through the asyncpg commit connection."""

    return [dict(row) for row in await conn.fetch(sql)]


def _valence_tier(
    valence_current: Any,
) -> Literal["trusting", "neutral", "hostile"]:
    """Classify canonical float valence by sign, or fail loudly."""

    if isinstance(valence_current, bool) or not isinstance(
        valence_current, (Decimal, float, int)
    ):
        raise ValueError(
            f"Unparseable valence_current {valence_current!r}; expected "
            "a signed numeric value"
        )
    if isinstance(valence_current, Decimal) and not valence_current.is_finite():
        raise ValueError(
            f"Unparseable valence_current {valence_current!r}; expected "
            "a finite signed numeric value"
        )
    if isinstance(valence_current, float) and not math.isfinite(valence_current):
        raise ValueError(
            f"Unparseable valence_current {valence_current!r}; expected "
            "a finite signed numeric value"
        )
    if valence_current > 0:
        return "trusting"
    if valence_current < 0:
        return "hostile"
    if valence_current == 0:
        return "neutral"
    raise ValueError(
        f"Unparseable valence_current {valence_current!r}; expected "
        "a finite signed numeric value"
    )


def _edge_sort_key(edge: CommunicationEdge) -> tuple[Any, ...]:
    return (
        edge.teller_entity_id,
        edge.listener_entity_id,
        edge.kind,
        edge.label,
        edge.institution_entity_id if edge.institution_entity_id is not None else -1,
        edge.latency,
        edge.culture_multiplier if edge.culture_multiplier is not None else 0.0,
    )


def _registered_channel_tags(session_or_cur: Any) -> frozenset[str]:
    rows = _fetch_mappings(session_or_cur, _REGISTERED_PAIR_TAGS_SQL)
    return frozenset(str(row["tag"]) for row in rows)


async def _registered_channel_tags_async(conn: Any) -> frozenset[str]:
    rows = await _fetch_mappings_async(conn, _REGISTERED_PAIR_TAGS_SQL)
    return frozenset(str(row["tag"]) for row in rows)


def _validate_channel_registry(
    configured_tags: Iterable[str], registered_tags: frozenset[str]
) -> None:
    configured = frozenset(configured_tags)
    exact_tags = configured - {"status:*"}
    missing = sorted(exact_tags - registered_tags)
    if "status:*" in configured:
        missing_status_tags = sorted(STATUS_TAGS - registered_tags)
        if missing_status_tags:
            missing.append("status:* (missing " + ", ".join(missing_status_tags) + ")")
    if missing:
        raise ValueError(
            "orrery.contagion config references unregistered channel tags: "
            f"{missing}"
        )


def _dyad_edges(
    session_or_cur: Any, settings: OrreryContagionSettings
) -> list[CommunicationEdge]:
    return _dyad_edges_from_rows(_fetch_mappings(session_or_cur, _DYAD_SQL), settings)


async def _dyad_edges_async(
    conn: Any, settings: OrreryContagionSettings
) -> list[CommunicationEdge]:
    return _dyad_edges_from_rows(await _fetch_mappings_async(conn, _DYAD_SQL), settings)


def _dyad_edges_from_rows(
    rows: Sequence[Mapping[str, Any]], settings: OrreryContagionSettings
) -> list[CommunicationEdge]:
    row_keys = {
        (
            int(row["teller_entity_id"]),
            int(row["listener_entity_id"]),
            str(row["relationship_type"]),
        )
        for row in rows
    }
    edges: list[CommunicationEdge] = []
    for row in rows:
        teller = int(row["teller_entity_id"])
        listener = int(row["listener_entity_id"])
        relationship_type = str(row["relationship_type"])
        tier = _valence_tier(row["valence_current"])
        override = settings.dyad_overrides.get(relationship_type)
        if override is None:
            latency = getattr(settings.dyad_tiers, tier)
        else:
            matching_reverse = (listener, teller, relationship_type) in row_keys
            # character_relationships has no row id or role-orientation column.
            # For a same-type reciprocal pair, entity-id order supplies the
            # frozen stable orientation: low->high is forward, high->low is
            # the matching reverse row. A sparse row is always its own forward.
            is_reverse = matching_reverse and teller > listener
            latency = override.reverse if is_reverse else override.forward
        if latency is None:
            continue
        if teller == listener:
            raise ValueError("communication dyad produced a forbidden self-loop")
        edges.append(
            CommunicationEdge(
                teller_entity_id=teller,
                listener_entity_id=listener,
                latency=latency,
                kind="dyad",
                label=relationship_type,
            )
        )
    return edges


def _channel_rows(session_or_cur: Any) -> list[dict[str, Any]]:
    return _fetch_mappings(session_or_cur, _CHANNEL_SQL)


async def _channel_rows_async(conn: Any) -> list[dict[str, Any]]:
    return await _fetch_mappings_async(conn, _CHANNEL_SQL)


def _culture_tags_by_institution(session_or_cur: Any) -> dict[int, Tuple[str, ...]]:
    return _culture_tags_from_rows(_fetch_mappings(session_or_cur, _CULTURE_TAGS_SQL))


async def _culture_tags_by_institution_async(
    conn: Any,
) -> dict[int, Tuple[str, ...]]:
    return _culture_tags_from_rows(await _fetch_mappings_async(conn, _CULTURE_TAGS_SQL))


def _culture_tags_from_rows(
    rows: Sequence[Mapping[str, Any]],
) -> dict[int, Tuple[str, ...]]:
    tags: dict[int, list[str]] = {}
    for row in rows:
        category = str(row["category"])
        if category not in _CULTURE_CATEGORIES:
            continue
        tags.setdefault(int(row["entity_id"]), []).append(str(row["tag"]))
    return {entity_id: tuple(values) for entity_id, values in tags.items()}


def _institution_for_channel(
    row: Mapping[str, Any], *, teller_entity_id: int
) -> Optional[int]:
    if (
        row["subject_kind"] == "faction"
        and int(row["subject_entity_id"]) == teller_entity_id
    ):
        return int(row["subject_entity_id"])
    if (
        row["object_kind"] == "faction"
        and int(row["object_entity_id"]) == teller_entity_id
    ):
        return int(row["object_entity_id"])
    if row["subject_kind"] == "faction":
        return int(row["subject_entity_id"])
    if row["object_kind"] == "faction":
        return int(row["object_entity_id"])
    return None


def _culture_multiplier(
    institution_entity_id: Optional[int],
    culture_tags: Mapping[int, Sequence[str]],
    profiles: Mapping[str, float],
) -> float:
    multiplier = 1.0
    if institution_entity_id is None:
        return multiplier
    for tag in culture_tags.get(institution_entity_id, ()):
        configured = profiles.get(tag)
        if configured is not None:
            multiplier *= configured
    return multiplier


def _channel_directions(
    row: Mapping[str, Any], direction: str, min_level: Optional[str]
) -> Tuple[tuple[int, int], ...]:
    subject = int(row["subject_entity_id"])
    object_ = int(row["object_entity_id"])
    if direction == "both":
        return ((subject, object_), (object_, subject))
    if direction == "subject_to_object":
        return ((subject, object_),)
    if direction == "object_to_subject":
        return ((object_, subject),)
    if direction != "faction_to_member":
        raise ValueError(f"Unknown channel direction {direction!r}")
    if row["subject_kind"] not in ("character", "faction"):
        raise ValueError(
            f"status pair tag {row['tag']!r} has subject kind "
            f"{row['subject_kind']!r}; the registry allows character or faction"
        )
    if row["object_kind"] != "faction":
        raise ValueError(
            f"status pair tag {row['tag']!r} has object kind "
            f"{row['object_kind']!r}; the scope must be a faction"
        )
    if min_level is None:
        raise ValueError("faction_to_member channel requires min_level")
    level = level_from_status_tag(str(row["tag"]))
    if not status_at_or_above_level(level, min_level):
        return ()
    return ((object_, subject),)


def _channel_edges(
    session_or_cur: Any, settings: OrreryContagionSettings
) -> list[CommunicationEdge]:
    registered_tags = _registered_channel_tags(session_or_cur)
    culture_tags = _culture_tags_by_institution(session_or_cur)
    return _channel_edges_from_rows(
        _channel_rows(session_or_cur), registered_tags, culture_tags, settings
    )


async def _channel_edges_async(
    conn: Any, settings: OrreryContagionSettings
) -> list[CommunicationEdge]:
    registered_tags = await _registered_channel_tags_async(conn)
    culture_tags = await _culture_tags_by_institution_async(conn)
    return _channel_edges_from_rows(
        await _channel_rows_async(conn), registered_tags, culture_tags, settings
    )


def _channel_edges_from_rows(
    rows: Sequence[Mapping[str, Any]],
    registered_tags: frozenset[str],
    culture_tags: Mapping[int, Sequence[str]],
    settings: OrreryContagionSettings,
) -> list[CommunicationEdge]:
    _validate_channel_registry(settings.channels, registered_tags)
    edges: list[CommunicationEdge] = []
    for row in rows:
        tag = str(row["tag"])
        channel_key = "status:*" if tag.startswith("status:") else tag
        channel = settings.channels.get(channel_key)
        if channel is None or channel.latency is None:
            continue
        for teller, listener in _channel_directions(
            row, channel.direction, channel.min_level
        ):
            if teller == listener:
                raise ValueError("communication channel produced a forbidden self-loop")
            institution = _institution_for_channel(row, teller_entity_id=teller)
            multiplier = _culture_multiplier(
                institution,
                culture_tags,
                settings.culture_profiles,
            )
            edges.append(
                CommunicationEdge(
                    teller_entity_id=teller,
                    listener_entity_id=listener,
                    latency=channel.latency * multiplier,
                    kind="channel",
                    label=tag,
                    institution_entity_id=institution,
                    culture_multiplier=multiplier,
                )
            )
    return edges


def assemble_communication_graph(
    session_or_cur: Any,
    *,
    settings: Any,
    world_time: Optional[datetime],
) -> CommunicationGraph:
    """Assemble the immutable communication graph without database writes.

    ``world_time`` is accepted now so Stage 2c can consume the same assembly
    boundary for world-clock frontier calculations. Stage 2b performs no age
    or scope gating, so the value cannot alter the graph yet.
    """

    del world_time
    config = coerce_contagion_settings(settings)
    if not config.enabled:
        return CommunicationGraph()
    _validate_dyad_overrides(session_or_cur, config.dyad_overrides)
    edges = _dyad_edges(session_or_cur, config)
    edges.extend(_channel_edges(session_or_cur, config))
    return CommunicationGraph(edges=tuple(sorted(edges, key=_edge_sort_key)))


async def assemble_communication_graph_async(
    conn: Any,
    *,
    settings: Any,
    world_time: Optional[datetime],
) -> CommunicationGraph:
    """Asyncpg twin of :func:`assemble_communication_graph`."""

    del world_time
    config = coerce_contagion_settings(settings)
    if not config.enabled:
        return CommunicationGraph()
    await _validate_dyad_overrides_async(conn, config.dyad_overrides)
    edges = await _dyad_edges_async(conn, config)
    edges.extend(await _channel_edges_async(conn, config))
    return CommunicationGraph(edges=tuple(sorted(edges, key=_edge_sort_key)))


def communication_graph_for_settings(
    session_or_cur: Any,
    settings: Any,
    *,
    world_time: Optional[datetime] = None,
) -> CommunicationGraph:
    """Assemble the graph, or return an empty one when settings are absent.

    The single home for the "no contagion settings -> empty graph" convention
    shared by production hydration, audit, and future Stage 2c callers.
    """

    if settings is None:
        return CommunicationGraph()
    return assemble_communication_graph(
        session_or_cur, settings=settings, world_time=world_time
    )


def _validate_dyad_overrides(session_or_cur: Any, overrides: Mapping[str, Any]) -> None:
    """Reject override keys outside every known relationship vocabulary.

    Valid keys are the union of the apex RelationshipType enum, relationship
    types referenced by shipped package templates, and types present in the
    live data — so shipped defaults (captor, handler) validate on a fresh
    slot while a typo'd or retired key fails loudly instead of silently
    falling back to its valence tier.
    """

    if not overrides:
        return
    valid = _known_relationship_types()
    valid.update(
        str(row["relationship_type"])
        for row in _fetch_mappings(
            session_or_cur,
            "SELECT DISTINCT relationship_type FROM character_relationships",
        )
    )
    unknown = sorted(set(overrides) - valid)
    if unknown:
        raise ValueError(
            "orrery.contagion dyad_overrides reference unknown relationship "
            f"types {unknown}; known types: {sorted(valid)}"
        )


async def _validate_dyad_overrides_async(
    conn: Any, overrides: Mapping[str, Any]
) -> None:
    if not overrides:
        return
    valid = _known_relationship_types()
    valid.update(
        str(row["relationship_type"])
        for row in await _fetch_mappings_async(
            conn, "SELECT DISTINCT relationship_type FROM character_relationships"
        )
    )
    unknown = sorted(set(overrides) - valid)
    if unknown:
        raise ValueError(
            "orrery.contagion dyad_overrides reference unknown relationship "
            f"types {unknown}; known types: {sorted(valid)}"
        )


def _known_relationship_types() -> set[str]:
    from nexus.agents.logon.apex_enums import RelationshipType
    from nexus.agents.orrery.catalog import collect_template_vocabulary
    from nexus.agents.orrery.templates import BUILTIN_TEMPLATES

    valid = {member.value for member in RelationshipType}
    valid.update(collect_template_vocabulary(BUILTIN_TEMPLATES)["relationship_types"])
    return valid
